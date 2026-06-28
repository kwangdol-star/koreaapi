"""Agent-face service logic (transport-agnostic).

Reads the append-only store and returns decision-ready dicts. Every item carries
provenance + Skill Score (invariant 2). server.py wraps these as MCP tools; tests
exercise them directly with no transport dependency or network.

Each call also logs a best-effort BEHAVIORAL SIGNAL (engine 2 raw material): usage -
what agents query / intend to buy - is the proprietary signal a latecomer cannot
reconstruct. Logging is best-effort and never breaks a read.
"""

from __future__ import annotations

from .pipeline import store
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
    return {"artist_id": artist_id, "found": True, "name": name, "status": items}


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
    }


def _norm_name(s: str | None) -> str:
    return (s or "").casefold().replace(" ", "")


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
    return {"agency": name, "count": len(members), "members": members}


async def korea_rising(category: str = "all", limit: int = 10, *, db_path: str | None = None) -> dict:
    """What is rising in Korea now: verified snapshots ranked by observed DEMAND (the captured
    behavioral signal) then Skill Score — engine 2 turning usage into the trend product (the
    proprietary signal a latecomer can't reconstruct). `category` drills into one vertical
    ('artist', 'drama', 'food', …) or 'all'. Demand blends queries + buy-intent (weighted higher)."""
    await _log("query", f"rising:{category}", db_path)
    recs = await store.recent(500, db_path=db_path)
    if category and category != "all":  # drill into one vertical (was previously ignored)
        recs = [r for r in recs if r.entity_id.startswith(f"{category}:")]
    queries = {s["key"]: s["count"] for s in await store.top_signals(1000, kind="query", db_path=db_path)}
    buys = {s["key"]: s["count"] for s in await store.top_signals(1000, kind="buy_intent", db_path=db_path)}

    def demand(eid: str) -> int:  # buy-intent is a stronger signal than a lookup -> weight it 3x
        return queries.get(eid, 0) + 3 * buys.get(eid, 0)

    ranked = sorted(
        recs,
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
        # keep related within the same family (artist↔artist, video↔video); dedupe by entity_id
        if oid == entity_id or oid in seen or oid.startswith("artist:") != is_artist:
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
        "related_by": "agency" if is_artist else "network",
        "key": label, "count": len(out), "related": out[:limit],
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
        "certified_by": cert["by"] if cert else None,
        "certified_date": cert.get("date") if cert else None,
        "sources": p.sources,
        "as_of": rec.snapshot_at.date().isoformat(),
        "citation": _citation(rec),
        "note": (f"officially certified by {cert['by']} — the tier above cross-verification" if cert
                 else "triple cross-verified — ≥3 independent sources agreed" if n >= 3
                 else "cross-verified — ≥2 independent sources agreed" if n >= 2
                 else "single-source / uncorroborated — Skill Score capped at 0.7"),
    }


async def buy_options(item: str, *, db_path: str | None = None) -> dict:
    """Where to buy a release/ticket/goods. Phase 1: commerce rail pending; logs buy-intent."""
    await _log("buy_intent", item, db_path)  # the buy-intent signal accrues even at $0 commission
    # Honest cold-start stub: no monetized links yet, but the request itself is the
    # behavioral signal that seeds engine 2 (SCOPE S3/S6). Affiliate links (Skimlinks/
    # Amazon) activate once traffic qualifies.
    return {
        "item": item,
        "options": [],
        "note": (
            "Phase 1: commerce rail not wired (cold-start). buy-intent is captured as "
            "the behavioral signal; affiliate links activate once traffic qualifies."
        ),
    }
