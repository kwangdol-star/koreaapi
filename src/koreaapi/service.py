"""Agent-face service logic (transport-agnostic).

Reads the append-only store and returns decision-ready dicts. Every item carries
provenance + Skill Score (invariant 2). server.py wraps these as MCP tools; tests
exercise them directly with no transport dependency or network.

Each call also logs a best-effort BEHAVIORAL SIGNAL (engine 2 raw material): usage -
what agents query / intend to buy - is the proprietary signal a latecomer cannot
reconstruct. Logging is best-effort and never breaks a read.
"""

from __future__ import annotations

import json
import re

from . import integrity
from .license import LICENSE
from .pipeline import store
from .reconcile import external_ids, match_score, name_keys
from .roster import CERTIFIED

_CALENDAR_KINDS = ("comeback", "release", "concert")


async def _log(kind: str, key: str, db_path: str | None) -> None:
    """Best-effort behavioral-signal capture; a logging failure must never break a read."""
    try:
        await store.log_signal(kind, key, db_path=db_path)
    except Exception:
        pass


def _citation(rec) -> str:
    """Ready-to-cite line (source + freshness + Skill Score) an agent can reproduce verbatim.

    AEO/GEO: every served fact carries how to cite it - the original source AND KoreaAPI -
    so answer engines surface us as the verifiable origin.
    """
    name = rec.name.en_official or rec.name.ko
    ko = f" ({rec.name.ko})" if rec.name.ko and rec.name.ko != name else ""
    sources = "; ".join(rec.provenance.sources) or "unsourced"
    return (
        f"{name}{ko} - {rec.kind} (as of {rec.snapshot_at.date()}). "
        f"Source: {sources}. Skill Score {rec.provenance.skill_score:.2f} "
        f"({rec.provenance.confidence}). via KoreaAPI."
    )


def _item(rec) -> dict:
    """Decision-ready, bilingual projection of a stored Record (with provenance)."""
    return {
        "kind": rec.kind,
        "name": {
            "ko": rec.name.ko,
            "en_official": rec.name.en_official,
            "romanized": rec.name.romanized,
        },
        "summary_en": rec.summary_en,
        "summary_ko": rec.summary_ko,
        "data": rec.data,
        "snapshot_at": rec.snapshot_at.isoformat(),
        "provenance": {
            "sources": rec.provenance.sources,
            "skill_score": rec.provenance.skill_score,
            "confidence": rec.provenance.confidence,
            "translation": rec.provenance.translation.source,
            "fetched_at": rec.provenance.fetched_at.isoformat(),
        },
        "citation": _citation(rec),
    }


async def artist_status(artist_id: str, *, db_path: str | None = None) -> dict:
    """Latest verified status across kinds for one artist. artist_id e.g. 'artist:bts'."""
    await _log("query", artist_id, db_path)  # behavioral signal: even a miss is demand signal
    ents = [e for e in await store.entities(db_path=db_path) if e["entity_id"] == artist_id]
    if not ents:
        return {"artist_id": artist_id, "found": False, "note": "no verified snapshot yet"}
    items: list[dict] = []
    best: tuple[float, dict] | None = None
    for e in ents:
        rec = await store.latest(artist_id, e["kind"], db_path=db_path)
        if rec is None:
            continue
        items.append(_item(rec))
        # The canonical display name comes from the best-verified record (the cross-verified
        # 'facts' snapshot), not whichever kind happens to sort first - so a 'release' record's
        # placeholder name (ko set to the English stage name) never overrides 방탄소년단.
        cand = {"ko": rec.name.ko, "en_official": rec.name.en_official, "romanized": rec.name.romanized}
        if best is None or rec.provenance.skill_score > best[0]:
            best = (rec.provenance.skill_score, cand)
    name = best[1] if best else None
    return {"artist_id": artist_id, "found": True, "name": name, "status": items, "license": LICENSE}


async def kculture_calendar(window_days: int = 30, *, db_path: str | None = None) -> dict:
    """Recent verified Korean culture events (comebacks, releases, concerts) with provenance.

    Phase 1: `window_days` is advisory (echoed, not yet a hard filter) - date-window filtering
    activates once upcoming-event dates are ingested; today this returns the recent verified
    event snapshots so the response never silently claims a filter it doesn't apply.
    """
    await _log("query", "kculture_calendar", db_path)
    recs = await store.recent(500, db_path=db_path)
    items = [_item(r) for r in recs if r.kind in _CALENDAR_KINDS]
    return {
        "window_days": window_days,
        "count": len(items),
        "items": items,
        "note": "Recent verified events; window_days is advisory at Phase 1 (not yet a hard filter).",
        "license": LICENSE,
    }


def _norm_name(s: str | None) -> str:
    return (s or "").casefold().replace(" ", "")


def _family(eid: str) -> str:
    """The relatedness family that legitimately shares the `agency_en` hub slot: artists (소속사),
    video (drama+film share a network/platform), and every other vertical only with its OWN kind —
    so `related('place:…')` (region slot) never returns a university/hospital that reused the slot."""
    kind = eid.split(":", 1)[0]
    return "video" if kind in ("drama", "film") else kind


async def agency(name: str, *, db_path: str | None = None) -> dict:
    """Artists verified under a 소속사/label - the agency HUB made queryable. `name` matches the
    agency recorded on each artist (Wikidata P264 label), e.g. 'JYP Entertainment' or 'JYP'.
    Powers 'who is under HYBE/SM/JYP?' for an agent; every member carries provenance + citation."""
    await _log("query", f"agency:{name}", db_path)
    target = _norm_name(name)
    members: list[dict] = []
    if target:
        seen: set[str] = set()
        for e in await store.entities(db_path=db_path):
            if e["entity_id"] in seen:
                continue
            rec = await store.latest(e["entity_id"], e["kind"], db_path=db_path)
            if rec is None:
                continue
            ag_en, ag_ko = _norm_name(rec.data.get("agency_en")), _norm_name(rec.data.get("agency_ko"))
            # Prefix match, not substring: "SM" matches "SM Entertainment" but NOT "Cosmic ... Agency"
            # (whose normalized form happens to contain "sm"). Agency queries lead with the brand.
            if (ag_en and ag_en.startswith(target)) or (ag_ko and ag_ko.startswith(target)):
                seen.add(e["entity_id"])
                members.append(_item(rec))
    return {"agency": name, "count": len(members), "members": members, "license": LICENSE}


async def korea_rising(category: str = "all", limit: int = 10, *, db_path: str | None = None) -> dict:
    """What is rising in Korea now: verified snapshots ranked by observed DEMAND (the captured
    behavioral signal) then Skill Score — engine 2 turning usage into the trend product (the
    proprietary signal a latecomer can't reconstruct). `category` drills into one vertical
    ('artist', 'drama', 'food', …) or 'all'. Demand blends queries + buy-intent (weighted higher)."""
    await _log("query", f"rising:{category}", db_path)
    recs = await store.recent(500, db_path=db_path)
    if category and category != "all":  # drill into one vertical (was previously ignored)
        recs = [r for r in recs if r.entity_id.startswith(f"{category}:")]
    # Query signals are logged under heterogeneous keys: a bare entity_id (artist_status) or
    # "<verb>:<entity_id>" (verified/history/related). Fold the entity-addressed verbs back onto the
    # entity_id so demand reflects EVERY way an agent reached an entity, not only artist_status.
    _entity_verbs = ("verified:", "history:", "related:")

    def _demand_key(k: str) -> str:
        for v in _entity_verbs:
            if k.startswith(v):
                return k[len(v):]
        return k

    queries: dict[str, int] = {}
    for s in await store.top_signals(1000, kind="query", db_path=db_path):
        dk = _demand_key(s["key"])
        queries[dk] = queries.get(dk, 0) + s["count"]
    buys = {s["key"]: s["count"] for s in await store.top_signals(1000, kind="buy_intent", db_path=db_path)}

    def demand(eid: str) -> int:  # buy-intent is a stronger signal than a lookup -> weight it 3x
        return queries.get(eid, 0) + 3 * buys.get(eid, 0)

    # Collapse to one row per entity (best-verified snapshot) so the top-N isn't filled with duplicate
    # snapshots/kinds of the same entity all carrying its identical demand score.
    best: dict = {}
    for r in recs:
        cur = best.get(r.entity_id)
        if cur is None or (r.provenance.skill_score, r.snapshot_at) > (cur.provenance.skill_score, cur.snapshot_at):
            best[r.entity_id] = r
    ranked = sorted(
        best.values(),
        key=lambda r: (demand(r.entity_id), r.provenance.skill_score, r.snapshot_at),
        reverse=True,
    )
    items = []
    for r in ranked[:limit]:
        it = _item(r)
        it["demand_signal"] = demand(r.entity_id)  # engine 2: blended queries + 3×buy-intent
        it["queries"] = queries.get(r.entity_id, 0)
        it["buy_intent"] = buys.get(r.entity_id, 0)
        items.append(it)
    return {
        "category": category,
        "count": len(items),
        "items": items,
        "note": (
            "Ranked by observed demand (queries + 3×buy-intent) then Skill Score; only verified "
            "snapshots surfaced. category drills into one vertical or 'all'."
        ),
        "license": LICENSE,
    }


def _person_key(s: str | None) -> str:
    """Match key for a person across name/slug forms: 'Bong Joon-ho' == 'bong-joon-ho' == 'BONGJOONHO'."""
    return "".join(c for c in (s or "").lower() if c.isalnum())


async def person(name: str, *, db_path: str | None = None) -> dict:
    """Verified credits for ONE Korean-culture person (director / actor / idol member), aggregated
    across every work that credits them — the person face of the knowledge graph. `name` may be the
    display name or a slug ('Bong Joon-ho' / 'bong-joon-ho'). Each credit carries the work's
    provenance + Skill Score; the person edge is asserted by those works' own verified records."""
    await _log("query", f"person:{name}", db_path)  # behavioral signal (a miss is still demand)
    key = _person_key(name)
    if not key:
        return {"query": name, "found": False, "note": "empty query"}
    credits: list[dict] = []
    sources: set[str] = set()
    display: str | None = None
    for e in await store.entities(db_path=db_path):
        if e["kind"] != "facts":
            continue
        rec = await store.latest(e["entity_id"], "facts", db_path=db_path)
        if rec is None:
            continue
        is_video = rec.entity_id.startswith(("drama:", "film:"))
        roles = [("cast" if is_video else "member", n) for n in (rec.data.get("members") or [])]
        roles += [("director", n) for n in (rec.data.get("directors") or [])]
        for role, nm in roles:
            if _person_key(nm) != key:
                continue
            display = display or nm
            sources.update(rec.provenance.sources)
            credits.append({
                "role": role,
                "work": {
                    "entity_id": rec.entity_id,
                    "name": {"ko": rec.name.ko, "en_official": rec.name.en_official},
                },
                "skill_score": rec.provenance.skill_score,
                "sources": rec.provenance.sources,
                "as_of": rec.snapshot_at.date().isoformat(),
            })
    if not credits:
        return {"query": name, "found": False, "note": "no verified credit for this person yet"}
    cite = (f"{display} — {len(credits)} verified credit(s). "
            f"Source: {'; '.join(sorted(sources)) or 'unsourced'}. via KoreaAPI.")
    return {
        "query": name, "found": True, "name": display, "count": len(credits),
        "credits": credits, "provenance": {"sources": sorted(sources)}, "citation": cite,
        "license": LICENSE,
    }


async def related(entity_id: str, *, limit: int = 12, db_path: str | None = None) -> dict:
    """Entities related to a verified entity via the same HUB edge — artists sharing a 소속사, or
    dramas/films sharing an original network/platform (the same Wikidata P264/P449 value). The
    graph edge made queryable ('what else is on Netflix / under HYBE?'); each carries provenance."""
    await _log("query", f"related:{entity_id}", db_path)
    rec = await store.latest(entity_id, "facts", db_path=db_path)
    if rec is None:
        return {"entity_id": entity_id, "found": False, "note": "no verified facts for this entity"}
    label = rec.data.get("agency_en") or rec.data.get("agency_ko")
    key = _norm_name(label)
    is_artist = entity_id.startswith("artist:")
    if not key:
        return {"entity_id": entity_id, "found": True, "related_by": None, "key": None,
                "count": 0, "related": [], "note": "no agency/network edge on this entity"}
    out: list[dict] = []
    seen: set[str] = set()
    for e in await store.entities(db_path=db_path):
        oid = e["entity_id"]
        # keep related within the same family (artist↔artist, drama↔film, place↔place …); dedupe
        if oid == entity_id or oid in seen or _family(oid) != _family(entity_id):
            continue
        r = await store.latest(oid, "facts", db_path=db_path)
        if r is None:
            continue
        if _norm_name(r.data.get("agency_en") or r.data.get("agency_ko")) == key:
            seen.add(oid)
            out.append(_item(r))
    out.sort(key=lambda it: (it["name"]["en_official"] or it["name"]["ko"] or "").lower())
    return {
        "entity_id": entity_id, "found": True,
        "related_by": ("agency" if is_artist else "network" if _family(entity_id) == "video" else "hub"),
        "key": label, "count": len(out), "related": out[:limit],
        "license": LICENSE,
    }


async def verified(entity_id: str, *, db_path: str | None = None) -> dict:
    """The cross-verification status of one entity — the moat made queryable. Returns how many
    INDEPENDENT sources agreed on the bilingual name, the Skill Score + confidence, the source list,
    and cross_verified / triple_verified flags — so an agent can decide trust BEFORE it cites.
    entity_id e.g. 'artist:bts' or 'place:gyeongbokgung'."""
    await _log("query", f"verified:{entity_id}", db_path)
    rec = await store.latest(entity_id, "facts", db_path=db_path)
    if rec is None:
        return {"entity_id": entity_id, "found": False, "note": "no verified facts for this entity yet"}
    p = rec.provenance
    n = getattr(p, "agreeing_sources", 0)
    cert = CERTIFIED.get(entity_id)  # institutional certification = the tier ABOVE cross-verification
    return {
        "entity_id": entity_id,
        "found": True,
        "name": {"ko": rec.name.ko, "en_official": rec.name.en_official, "romanized": rec.name.romanized},
        "skill_score": p.skill_score,
        "confidence": p.confidence,
        "agreeing_sources": n,
        "cross_verified": n >= 2,
        "triple_verified": n >= 3,
        "officially_certified": bool(cert),
        "certified_by": cert.get("by") if cert else None,
        "certified_date": cert.get("date") if cert else None,
        "sources": p.sources,
        "license": LICENSE,
        "as_of": rec.snapshot_at.date().isoformat(),
        "citation": _citation(rec),
        "note": (f"officially certified by {cert.get('by')} — the tier above cross-verification" if cert
                 else "triple cross-verified — ≥3 independent sources agreed" if n >= 3
                 else "cross-verified — ≥2 independent sources agreed" if n >= 2
                 else "single-source / uncorroborated — Skill Score capped at 0.7"),
    }


def _hist_state(rec) -> dict:
    return {"name_ko": rec.name.ko, "name_en": rec.name.en_official,
            "agency": rec.data.get("agency_en") or rec.data.get("agency_ko"),
            "skill_score": rec.provenance.skill_score}


async def history(entity_id: str, *, db_path: str | None = None) -> dict:
    """The append-only verified TIMELINE of one entity — the time moat made queryable. Returns first/
    last verified dates, snapshot count, and the CHANGE EVENTS (소속사 move, rename …) detected between
    consecutive verified states — exactly the stale facts LLMs get wrong, and a record a latecomer
    cannot backfill. entity_id e.g. 'artist:bts'."""
    await _log("query", f"history:{entity_id}", db_path)
    recs = await store.history(entity_id, "facts", db_path=db_path)
    if not recs:
        return {"entity_id": entity_id, "found": False, "note": "no verified history for this entity yet"}
    tracked = [("agency", "agency/network (소속사)"), ("name_ko", "Korean name"), ("name_en", "English name")]
    changes: list[dict] = []
    prev = None
    for rec in recs:
        st = _hist_state(rec)
        if prev is not None:
            for field, label in tracked:
                if st[field] and prev[field] and st[field] != prev[field]:
                    changes.append({"as_of": rec.snapshot_at.date().isoformat(), "field": label,
                                    "from": prev[field], "to": st[field]})
        prev = st
    return {
        "entity_id": entity_id,
        "found": True,
        "first_verified": recs[0].snapshot_at.date().isoformat(),
        "last_verified": recs[-1].snapshot_at.date().isoformat(),
        "snapshots": len(recs),
        "changes": changes,
        "current": _hist_state(recs[-1]),
        "license": LICENSE,
        "note": (f"append-only verified history — {len(changes)} tracked change(s) recorded; "
                 "timestamped snapshots a latecomer cannot backfill." if changes
                 else "append-only verified history — no tracked changes yet; the timestamped depth is the asset."),
    }


async def recent_changes(limit: int = 50, *, db_path: str | None = None) -> dict:
    """Store-wide RECENT verified changes (소속사 moves, renames), newest first — the freshness feed
    made queryable, so an agent can ask 'what changed lately?' and cite us on exactly the facts LLMs
    go stale on. Computed from the append-only store (bounded scan)."""
    await _log("query", "recent_changes", db_path)
    recs = await store.recent(30000, db_path=db_path)
    by_ent: dict[str, list] = {}
    for r in recs:
        if r.kind == "facts":
            by_ent.setdefault(r.entity_id, []).append(r)
    changes: list[dict] = []
    for eid, rs in by_ent.items():
        prev = None
        for r in sorted(rs, key=lambda r: r.snapshot_at):
            st = {"agency": r.data.get("agency_en") or r.data.get("agency_ko"),
                  "name_ko": r.name.ko, "name_en": r.name.en_official}
            if prev is not None:
                for field, label in (("agency", "agency/network (소속사)"), ("name_ko", "Korean name"),
                                     ("name_en", "English name")):
                    if st[field] and prev[field] and st[field] != prev[field]:
                        changes.append({"entity_id": eid, "as_of": r.snapshot_at.date().isoformat(),
                                        "field": label, "from": prev[field], "to": st[field]})
            prev = st
    changes.sort(key=lambda c: c["as_of"], reverse=True)
    return {"count": len(changes), "changes": changes[:limit], "license": LICENSE,
            "note": "verified change events across KoreaAPI — timestamped, newest first (a latecomer cannot backfill)"}


async def certified(*, db_path: str | None = None) -> dict:
    """The CERTIFIED registry — entities an official rights-holder has vouched for (the tier ABOVE
    cross-verification), queryable by agents. Non-replicable: a latecomer can copy data, not an
    institution's signature or its date. Ships INERT (empty) until the first institution claims in; this
    completes the symmetry with get_history / get_changes — three verified feeds on the agent surface."""
    await _log("query", "certified", db_path)
    out: list[dict] = []
    for eid, c in CERTIFIED.items():
        rec = await store.latest(eid, "facts", db_path=db_path)
        name = ({"ko": rec.name.ko, "en_official": rec.name.en_official, "romanized": rec.name.romanized}
                if rec is not None else None)
        out.append({"entity_id": eid, "name": name, "certified_by": c.get("by"),
                    "certified_date": c.get("date"), "url": c.get("url"),
                    "tier": c.get("tier", "certified"), "in_store": rec is not None})
    out.sort(key=lambda x: (x["certified_date"] or ""), reverse=True)
    return {
        "count": len(out),
        "certified": out,
        "license": LICENSE,
        "how_to_certify": "https://aiagentlabs.co.kr/certify.html",
        "note": ("official rights-holder certifications — the tier above cross-verification (an institution "
                 "vouched; a latecomer cannot forge or backdate it). Empty until the first institution claims in."),
    }


async def metrics(*, top: int = 10, db_path: str | None = None) -> dict:
    """How much agents have CONSUMED the verified layer — the usage signal rolled up. Every read logs a
    query and every buy-intent logs a buy signal (append-only), so this reports total pulls, distinct
    signals, and the most-requested queries + buy-intents. This is the usage moat made legible: a
    latecomer starts this counter at zero, and it's the demand evidence behind korea-rising. Read-only —
    it does NOT log a query of its own (so measuring consumption never inflates it)."""
    q = await store.top_signals(100000, kind="query", db_path=db_path)
    b = await store.top_signals(100000, kind="buy_intent", db_path=db_path)
    total_q = sum(s["count"] for s in q)
    total_b = sum(s["count"] for s in b)
    return {
        "total_agent_pulls": total_q + total_b,
        "total_queries": total_q,
        "total_buy_intent": total_b,
        "distinct_query_signals": len(q),
        "distinct_buy_signals": len(b),
        "top_queries": [{"signal": s["key"], "count": s["count"]} for s in q[:top]],
        "top_buy_intent": [{"item": s["key"], "count": s["count"]} for s in b[:top]],
        "license": LICENSE,
        "note": ("agent consumption of the verified layer — every read + buy-intent is appended "
                 "(append-only); the usage moat, and a latecomer starts this counter at zero."),
    }


def _resolved(entity_id: str, rec, matched_by: str) -> dict:
    """Shape a resolved entity for the `resolve` tool — canonical id + verification + external IDs."""
    p = rec.provenance
    n = getattr(p, "agreeing_sources", 0)
    return {
        "found": True,
        "matched_by": matched_by,
        "id": entity_id,
        "kind": entity_id.split(":", 1)[0],
        "name": {"ko": rec.name.ko, "en_official": rec.name.en_official, "romanized": rec.name.romanized},
        "skill_score": p.skill_score,
        "confidence": p.confidence,
        "agreeing_sources": n,
        "cross_verified": n >= 2,
        "triple_verified": n >= 3,
        "content_hash": integrity.record_fingerprint(json.loads(rec.model_dump_json())),
        "ids": external_ids(p.sources),
        "sources": p.sources,
        "license": LICENSE,
        "as_of": rec.snapshot_at.date().isoformat(),
        "citation": _citation(rec),
    }


async def resolve(query: str, *, db_path: str | None = None) -> dict:
    """Resolve a fuzzy NAME, an EXTERNAL ID (e.g. a Wikidata Q-id), or a canonical entity_id to THE
    verified KoreaAPI entity — the reconciliation / ID-spine tool. Returns the canonical id, bilingual
    name, cross-verification status + Skill Score, content_hash, and every parsed external ID, so an
    agent can map whatever it holds onto a trusted entity BEFORE it cites. `query` e.g. '빈센조',
    'Vincenzo', 'Q16741113', or 'drama:vincenzo'."""
    await _log("query", f"resolve:{query}", db_path)
    q = (query or "").strip()
    if not q:
        return {"query": query, "found": False, "note": "empty query"}
    qn = _norm_name(q)
    is_qid = bool(re.fullmatch(r"[Qq]\d+", q))
    if ":" in q:  # canonical entity_id fast path
        rec = await store.latest(q, "facts", db_path=db_path)
        if rec is not None:
            return {"query": query, **_resolved(q, rec, "entity_id")}
    candidates: list[tuple[int, float, str, object]] = []  # (fuzzy score, skill, entity_id, rec)
    for e in await store.entities(db_path=db_path):
        if e["kind"] != "facts":
            continue
        rec = await store.latest(e["entity_id"], "facts", db_path=db_path)
        if rec is None:
            continue
        if is_qid and external_ids(rec.provenance.sources).get("wikidata", "").lower() == q.lower():
            return {"query": query, **_resolved(e["entity_id"], rec, "wikidata")}
        keys = name_keys(rec.name.ko, rec.name.en_official, rec.name.romanized)
        if qn in keys:  # exact (disambiguator-insensitive: 'Vincenzo (TV series)' == 'Vincenzo')
            return {"query": query, **_resolved(e["entity_id"], rec, "name")}
        sc = match_score(qn, keys)
        if sc:
            candidates.append((sc, rec.provenance.skill_score, e["entity_id"], rec))
    if candidates:
        candidates.sort(key=lambda c: (c[0], c[1]), reverse=True)
        _, _, eid, rec = candidates[0]
        out = {"query": query, **_resolved(eid, rec, "fuzzy")}
        out["candidates"] = [  # ranked alternates so the agent can disambiguate a fuzzy hit
            {"id": c[2], "name": {"ko": c[3].name.ko, "en_official": c[3].name.en_official},
             "skill_score": c[1], "match": c[0]}
            for c in candidates[:5]
        ]
        return out
    return {"query": query, "found": False, "note": "no verified entity matches this name/ID yet"}


async def buy_options(item: str, *, db_path: str | None = None) -> dict:
    """The VERIFY-OFFICIAL → purchase gateway — the commerce-commission seed (the biggest revenue
    bet). Before routing any purchase it VERIFIES the item resolves to a real, cross-verified entity
    ('is this the official X, not a fake/scam?' — the anti-fake step that IS our value in commerce),
    then returns purchase-channel intent + a commission-ready envelope. The rail is DORMANT (0 bps)
    until agent-commerce / x402 settlement volume arrives; buy-intent is logged as the demand signal
    and the seed of the future commission ledger. Deliberately safe-fails (no purchase routed) when
    the item can't be verified as official."""
    await _log("buy_intent", item, db_path)  # demand signal + future commission-ledger seed (accrues at $0)
    r = await resolve(item, db_path=db_path)  # verify: is this a real, official entity?
    ok = bool(r.get("found"))
    return {
        "item": item,
        "verified_official": ok,
        "entity": ({"id": r["id"], "name": r["name"], "skill_score": r.get("skill_score"),
                    "cross_verified": r.get("cross_verified")} if ok else None),
        "options": [],  # official purchase channels attach here once the rail is live
        "commission": {"model": "bps on settled agent purchases", "rate_bps": 0, "status": "dormant",
                       "note": "activates with agent-commerce / x402 settlement volume"},
        "license": LICENSE,
        "note": ("verified the entity is real/official before purchase (the anti-fake step); commerce "
                 "rail dormant (0 bps) until agent-commerce volume arrives — buy-intent logged as demand signal."
                 if ok else
                 "could not verify this as an official KoreaAPI entity — refusing to route a purchase "
                 "(safe-fail); buy-intent still logged as the demand signal."),
    }
