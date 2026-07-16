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
from datetime import datetime, timedelta, timezone
from math import asin, cos, radians, sin, sqrt

from . import certify, integrity
from .license import LICENSE
from .pipeline import store
from .reconcile import external_ids, match_score, name_keys
from .roster import CERTIFIED, GEO_NAMESPACES

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

    `window_days` is a REAL filter: only event snapshots verified within the last N days are
    returned (snapshot-dated — these are verified recent events; forward-looking 'upcoming' dates
    activate when an upcoming-events source lands, and the note says which one you're getting)."""
    await _log("query", "kculture_calendar", db_path)
    window = max(1, int(window_days))
    horizon = datetime.now(timezone.utc) - timedelta(days=window)
    # kind-filtered IN SQL: calendar kinds are appended once daily while facts land by the hundreds
    # per tick — an unfiltered recent(500) window would push them out within hours.
    recs = await store.recent(500, kinds=_CALENDAR_KINDS, db_path=db_path)
    items = []
    for r in recs:
        at = r.snapshot_at if r.snapshot_at.tzinfo else r.snapshot_at.replace(tzinfo=timezone.utc)
        if at >= horizon:
            items.append(_item(r))
    return {
        "window_days": window,
        "count": len(items),
        "items": items,
        "note": (f"Verified event snapshots from the last {window} day(s) (snapshot-dated). "
                 "Forward-looking dates activate when an upcoming-events source lands."),
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
        # ONE query, not N+1: latest snapshot per (entity, kind), newest-first (matches the old
        # entities() order, so the first kind seen per entity wins exactly as before).
        for (eid, _kind), rec in (await store.latest_all(None, db_path=db_path)).items():
            if eid in seen:
                continue
            ag_en, ag_ko = _norm_name(rec.data.get("agency_en")), _norm_name(rec.data.get("agency_ko"))
            # Prefix match, not substring: "SM" matches "SM Entertainment" but NOT "Cosmic ... Agency"
            # (whose normalized form happens to contain "sm"). Agency queries lead with the brand.
            if (ag_en and ag_en.startswith(target)) or (ag_ko and ag_ko.startswith(target)):
                seen.add(eid)
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
    my_works: list[tuple[str, list[str]]] = []   # P's works -> everyone credited on each (collab graph)
    person_works: dict[str, set] = {}            # person key -> set of work ids (the recurring-collab filter)
    people_display: dict[str, str] = {}          # person key -> a display name
    for _eid, rec in (await store.latest_all("facts", db_path=db_path)).items():  # ONE query, not N+1
        is_video = rec.entity_id.startswith(("drama:", "film:"))
        roles = [("cast" if is_video else "member", n) for n in (rec.data.get("members") or [])]
        roles += [("director", n) for n in (rec.data.get("directors") or [])]
        for _role, nm in roles:  # global credit graph — how many works each person is credited on
            k = _person_key(nm)
            if k:
                person_works.setdefault(k, set()).add(rec.entity_id)
                people_display.setdefault(k, nm)
        credited = False
        for role, nm in roles:
            if _person_key(nm) != key:
                continue
            credited = True
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
        if credited:
            my_works.append((rec.name.en_official or rec.name.ko, [nm for _r, nm in roles]))
    if not credits:
        return {"query": name, "found": False, "note": "no verified credit for this person yet"}
    # Collaborators: other RECURRING people (credited on >=2 works) who share a verified work with P,
    # ranked by #shared works — the differentiated "who does X repeatedly work with?" graph edge. Already
    # on the crawled person page (Schema.org `colleague`); this brings it to the AGENT surface too.
    shared: dict[str, set] = {}
    for wname, ppl in my_works:
        for nm in ppl:
            k = _person_key(nm)
            if k and k != key:
                shared.setdefault(k, set()).add(wname)
    collaborators = [
        {"name": people_display.get(k, k), "shared_count": len(w), "shared_works": sorted(w)}
        for k, w in sorted(shared.items(), key=lambda kv: (-len(kv[1]), people_display.get(kv[0], kv[0])))
        if len(person_works.get(k, ())) >= 2
    ][:12]
    cite = (f"{display} — {len(credits)} verified credit(s). "
            f"Source: {'; '.join(sorted(sources)) or 'unsourced'}. via KoreaAPI.")
    return {
        "query": name, "found": True, "name": display, "count": len(credits),
        "credits": credits, "collaborators": collaborators,
        "provenance": {"sources": sorted(sources)}, "citation": cite, "license": LICENSE,
    }


_NEARBY_KM = 30.0  # nearby radius: same city / day-trip distance


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km between two WGS84 points (pure math; used for the nearby graph)."""
    rlat1, rlon1, rlat2, rlon2 = map(radians, (lat1, lon1, lat2, lon2))
    a = sin((rlat2 - rlat1) / 2) ** 2 + cos(rlat1) * cos(rlat2) * sin((rlon2 - rlon1) / 2) ** 2
    return 2 * 6371.0088 * asin(sqrt(a))


def _coords(rec) -> tuple[float, float] | None:
    """Verified P625 coordinates of a record as (lat, lon) floats, or None (defensive coercion)."""
    g = rec.data.get("geo") or {}
    try:
        return float(g["lat"]), float(g["lon"])
    except (KeyError, TypeError, ValueError):
        return None


def cluster_walkable(items: list, *, radius_km: float = 3.0, max_clusters: int = 4,
                     max_spots: int = 6) -> list[dict]:
    """Greedy proximity clusters over (entity_id, record) pairs (assumed relevance-sorted): the first
    unassigned spot with verified coordinates anchors a group of everything within radius_km of it —
    'walkable together' day-plan raw material. Pure math over verified P625 coords (records without
    coordinates are skipped, never guessed); a spot with no close neighbor forms NO cluster (a
    singleton is not a 'walkable together' statement). Shared by the trip-plan Answer Product and the
    crawlable region-guide pages, so the two surfaces never drift.
    Returns [{"anchor": (eid, rec), "spots": [(eid, rec, km)], "radius_km": r}], spots distance-sorted."""
    pool = [(eid, r, c) for eid, r in items if (c := _coords(r)) is not None]
    out: list[dict] = []
    while pool and len(out) < max_clusters:
        eid0, r0, c0 = pool.pop(0)
        near = [(eid, r, haversine_km(c0[0], c0[1], c[0], c[1])) for eid, r, c in pool]
        group = sorted((t for t in near if t[2] <= radius_km), key=lambda t: t[2])
        gids = {eid for eid, _r, _km in group}
        pool = [t for t in pool if t[0] not in gids]
        if group:
            out.append({"anchor": (eid0, r0), "spots": group[:max_spots], "radius_km": radius_km})
    return out


async def related(entity_id: str, *, limit: int = 12, db_path: str | None = None) -> dict:
    """Entities related to a verified entity via the same HUB edge — artists sharing a 소속사, or
    dramas/films sharing an original network/platform (the same Wikidata P264/P449 value). The
    graph edge made queryable ('what else is on Netflix / under HYBE?'); each carries provenance.
    Geo entities with verified coordinates (P625) additionally get `nearby`: physically close verified
    spots across ALL geo verticals, distance-ranked with km — 'what's near Gyeongbokgung?'."""
    await _log("query", f"related:{entity_id}", db_path)
    rec = await store.latest(entity_id, "facts", db_path=db_path)
    if rec is None:
        return {"entity_id": entity_id, "found": False, "note": "no verified facts for this entity"}
    label = rec.data.get("agency_en") or rec.data.get("agency_ko")
    key = _norm_name(label)
    is_artist = entity_id.startswith("artist:")
    fam = _family(entity_id)
    is_geo = entity_id.split(":", 1)[0] in GEO_NAMESPACES
    anchor = _coords(rec) if is_geo else None  # verified P625 -> physical-proximity edge
    if not key and anchor is None:  # no hub edge AND no coordinates -> nothing to relate on
        return {"entity_id": entity_id, "found": True, "related_by": None, "key": None,
                "count": 0, "related": [], "note": "no agency/network edge on this entity"}
    out: list[dict] = []       # same-KIND hub edge (소속사 / network / place↔place)
    seen: set[str] = set()
    same_region: list[dict] = []   # same-REGION neighbors ACROSS the geo verticals (region-edge based)
    seen_sr: set[str] = set()
    nearby: list[dict] = []        # physically close (haversine ≤ _NEARBY_KM), across the geo verticals
    for oid, r in (await store.latest_all("facts", db_path=db_path)).items():  # ONE query, not N+1
        if oid == entity_id:
            continue
        other_geo = oid.split(":", 1)[0] in GEO_NAMESPACES
        related_hit = bool(key) and oid not in seen and _family(oid) == fam      # same family, dedup
        region_hit = bool(key) and is_geo and oid not in seen_sr and other_geo   # any geo vertical
        nearby_hit = anchor is not None and other_geo
        if not (related_hit or region_hit or nearby_hit):
            continue
        if (related_hit or region_hit) and \
                _norm_name(r.data.get("agency_en") or r.data.get("agency_ko")) == key:
            if related_hit:
                seen.add(oid)
                out.append(_item(r))
            if region_hit:
                seen_sr.add(oid)
                same_region.append(_item(r))
        if nearby_hit:
            pt = _coords(r)
            if pt is not None:
                km = haversine_km(anchor[0], anchor[1], pt[0], pt[1])
                if km <= _NEARBY_KM:
                    nearby.append({**_item(r), "km": round(km, 1)})
    out.sort(key=lambda it: (it["name"]["en_official"] or it["name"]["ko"] or "").lower())
    same_region.sort(key=lambda it: (it["name"]["en_official"] or it["name"]["ko"] or "").lower())
    nearby.sort(key=lambda it: it["km"])
    return {
        "entity_id": entity_id, "found": True,
        "related_by": (("agency" if is_artist else "network" if fam == "video" else "hub") if key else None),
        "key": label, "count": len(out), "related": out[:limit],
        # nearby verified spots in the same region, across ALL geo verticals (park·temple·museum·beach…)
        # — the per-entity companion to the region trip-plan. Empty for non-geo entities.
        "same_region": same_region[:limit], "same_region_count": len(same_region),
        # physically close verified spots (verified P625 coords, great-circle km, ≤30 km) — distance-ranked.
        "nearby": nearby[:limit], "nearby_count": len(nearby),
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


async def recent_changes(limit: int = 50, *, since: str | None = None, offset: int = 0,
                         db_path: str | None = None) -> dict:
    """Store-wide RECENT verified changes (소속사 moves, renames), newest first — the freshness feed
    made queryable, so an agent can ask 'what changed lately?' and cite us on exactly the facts LLMs
    go stale on. Computed from the append-only store (bounded scan). Pass `since` (an ISO date, e.g.
    '2026-05-01') to get ONLY changes after that cursor — incremental sync, so an agent caches the feed
    then re-pulls just the delta instead of the whole thing each poll. `since` is a full TIMESTAMP cursor
    (sub-day precise) — pass back `next_since` to resume EXACTLY (no same-day event lost), or an ISO date
    to include that whole day. A delta larger than `limit` is drained with offset paging: loop
    `offset = next_offset` until it is null (`total` says how many). A malformed `since` is ignored
    (never silently zeroes the feed), not applied."""
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
                                        "at": r.snapshot_at.isoformat(),  # full-timestamp cursor key (sub-day precise)
                                        "field": label, "from": prev[field], "to": st[field]})
            prev = st
    # newest first, ties broken deterministically (entity_id, field) so OFFSET paging is stable across
    # calls and same-timestamp events are never split/lost at a page boundary.
    changes.sort(key=lambda c: (c["at"], c["entity_id"], c["field"]), reverse=True)
    since_note = ""
    if since:
        try:
            datetime.fromisoformat(since)  # accept an ISO date (2026-05-09) OR a full timestamp cursor
        except (ValueError, TypeError):
            # a malformed cursor must NOT silently filter everything out (that reads as "no changes",
            # the exact staleness this feed fixes) — ignore it and say so.
            since_note = f"; ignored malformed since='{since}' (expected an ISO date or timestamp)"
            since = None
    if since:  # incremental cursor: only the delta strictly after the agent's last-seen timestamp
        changes = [c for c in changes if c["at"] > since]
    total = len(changes)
    offset = max(0, offset)
    page = changes[offset:offset + limit]
    more = offset + limit < total
    next_since = changes[0]["at"] if changes else since  # newest event overall (for the next incremental poll)
    return {"count": len(page), "total": total, "offset": offset, "truncated": more,
            "next_offset": (offset + limit) if more else None, "since": since,
            "next_since": next_since, "changes": page, "license": LICENSE,
            "note": ("verified change events across KoreaAPI — newest first (a latecomer cannot backfill). "
                     "The since cursor is a full TIMESTAMP (sub-day precise): pass back next_since to resume "
                     "exactly, or an ISO date to include that whole day. Drain a delta bigger than limit "
                     "with offset paging: loop offset=next_offset until it is null"
                     + (f"; delta since {since}" if since else "") + since_note)}


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
    alias_hit: tuple | None = None  # a grounded-alias exact-match; used only if NO canonical name matches
    for eid, rec in (await store.latest_all("facts", db_path=db_path)).items():  # ONE query, not N+1
        if is_qid and external_ids(rec.provenance.sources).get("wikidata", "").lower() == q.lower():
            return {"query": query, **_resolved(eid, rec, "wikidata")}
        # Canonical NAME exact-match returns in-loop -> a real name ALWAYS wins. Grounded alternate names
        # (enrich.py, from the Wikipedia lead) widen recall but are a FALLBACK: an alias exact-match is
        # remembered and used only if NO entity has a canonical exact-match, and is labeled matched_by=
        # "alias" (never "name") — so an alias can't shadow another entity's real name nor overstate its
        # confidence. <2-char junk keys ('Han' problem) are dropped.
        name_only = name_keys(rec.name.ko, rec.name.en_official, rec.name.romanized)
        if qn in name_only:  # exact (disambiguator-insensitive: 'Vincenzo (TV series)' == 'Vincenzo')
            return {"query": query, **_resolved(eid, rec, "name")}
        alias_keys = {k for k in name_keys(*(rec.data.get("aliases") or [])) - name_only if len(k) >= 2}
        if alias_hit is None and qn in alias_keys:
            alias_hit = (eid, rec)  # remember; a later canonical exact-match still takes priority
        sc = match_score(qn, name_only | alias_keys)
        if sc:
            candidates.append((sc, rec.provenance.skill_score, eid, rec))
    if alias_hit is not None:  # no canonical exact-match anywhere -> the grounded-alias exact-match is next
        return {"query": query, **_resolved(alias_hit[0], alias_hit[1], "alias")}
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


_BATCH_MAX = 100
_BATCH_OPS = ("verified", "resolve")


async def batch(ids: list[str], *, op: str = "verified", db_path: str | None = None) -> dict:
    """Verify / resolve MANY entities in ONE call — the agent-throughput lane (highway convenience
    store: one stop serves the whole watchlist). An agent pays a single round-trip instead of N: pass
    up to 100 ids or names and get a result map keyed by the exact input. op='verified' (trust status,
    the default + fastest) or 'resolve' (name / external ID → canonical entity). Pairs with
    get_changes(since=…): sweep the list once, then re-pull only what changed. Duplicates collapse; a
    miss is still keyed (never crashes); over-cap requests are truncated (flagged, not silently dropped)."""
    await _log("query", f"batch:{op}", db_path)
    if op not in _BATCH_OPS:
        return {"op": op, "found": False, "count": 0, "requested": len(ids or []), "results": {},
                "license": LICENSE, "note": f"unknown op '{op}' — use one of {list(_BATCH_OPS)}"}
    fn = verified if op == "verified" else resolve
    keys: list[str] = []
    seen: set[str] = set()
    for k in ids or []:
        if isinstance(k, str) and k.strip() and k not in seen:
            seen.add(k)
            keys.append(k)
    truncated = len(keys) > _BATCH_MAX
    keys = keys[:_BATCH_MAX]
    results: dict[str, dict] = {}
    for k in keys:  # per-item isolation: one corrupt/legacy record must not sink the whole batch
        try:
            results[k] = await fn(k, db_path=db_path)
        except Exception as exc:
            results[k] = {"found": False, "error": "lookup failed", "detail": type(exc).__name__}
    return {
        "op": op,
        "requested": len(ids or []),
        "count": len(results),
        "truncated": truncated,
        "max": _BATCH_MAX,
        "results": results,
        "license": LICENSE,
        "note": ("verified/resolved a batch in one round-trip — the throughput lane; each key is also "
                 "logged as demand. Pair with get_changes(since=…) to re-pull only what changed."),
    }


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
    # Commerce routes money, so the bar is stricter than "found": require CROSS-VERIFICATION (≥2 sources)
    # AND an exact (non-fuzzy) resolve. A single-source or fuzzy/substring match is exactly the same-name
    # scam vector this gate exists to stop — so it safe-fails rather than green-lighting a purchase.
    ok = bool(r.get("found")) and bool(r.get("cross_verified")) and r.get("matched_by") != "fuzzy"
    options: list[dict] = []
    canonical = caution = None
    gateway = {"status": "unverified", "route_to": None,
               "note": ("not a cross-verified official entity (single-source, fuzzy, or unknown) — "
                        "refusing to route a purchase (safe-fail)")}
    if ok:
        rec = await store.latest(r["id"], "facts", db_path=db_path)
        official_url = rec.data.get("official_url") if rec is not None else None
        if official_url:  # the entity's OWN official site (Wikidata P856) — the authoritative first-party channel
            options.append({"type": "official-website", "url": official_url, "verified": True,
                            "note": "the entity's OFFICIAL website (cross-referenced via Wikidata P856) — the "
                                    "authoritative first-party source to buy from / confirm against"})
        agency = (rec.data.get("agency_en") or rec.data.get("agency_ko")) if rec is not None else None
        if agency:  # WHO officially sells/represents — cross-verified, so its official store is authoritative
            options.append({"type": "official-representative", "name": agency, "verified": True,
                            "note": ("the cross-verified official label / publisher / agency — its official "
                                     "store is the authoritative place to buy")})
        # the anti-same-name-scam key: match a store listing against THIS verified name + IDs before buying
        canonical = {"name": r["name"], "id": r["id"], "external_ids": r.get("ids"),
                     "cross_verified": r.get("cross_verified"), "skill_score": r.get("skill_score")}
        caution = ("Buy from the official representative (or its official store), and match a listing against "
                   "this canonical verified name / IDs — a same-name listing from an unverified seller may be "
                   "a counterfeit. This is the real entity.")
        # the GATEWAY: the ONE green-lit route an agent acts on (status + destination + anti-scam key),
        # anchored on the same official domain the certification rail proves control of.
        dom = certify.official_domain(official_url)
        if dom:  # first-party official site (P856), domain-normalized -> route here
            gateway = {"status": "verified-official", "route_to": official_url, "official_domain": dom,
                       "canonical": canonical,
                       "note": ("route to the entity's OWN official site (domain from Wikidata P856); match "
                                "any listing to the canonical key before paying")}
        elif agency:  # no first-party URL, but a cross-verified official representative sells / represents
            gateway = {"status": "verified-representative", "route_to": None, "representative": agency,
                       "canonical": canonical,
                       "note": ("buy from the cross-verified official representative's official store; no "
                                "first-party URL on record — match the canonical key, avoid same-name sellers")}
        else:  # verified entity, but no official channel captured yet -> still safe-fail on routing
            gateway = {"status": "verified-entity-no-channel", "route_to": None, "canonical": canonical,
                       "note": ("entity verified but no official channel on record yet — do not route to an "
                                "unverified seller (safe-fail)")}
    return {
        "item": item,
        "verified_official": ok,
        "entity": ({"id": r["id"], "name": r["name"], "skill_score": r.get("skill_score"),
                    "cross_verified": r.get("cross_verified")} if ok else None),
        "canonical": canonical,   # the safe key to search official stores with (anti same-name scam)
        "gateway": gateway,       # the ONE green-lit route (status + destination + canonical key) an agent acts on
        "options": options,       # verified official channels (the representative now; direct rails as volume arrives)
        "caution": caution,
        "commission": {"model": "bps on settled agent purchases", "rate_bps": 0, "status": "dormant",
                       "note": "activates with agent-commerce / x402 settlement volume"},
        "license": LICENSE,
        "note": ("verified the REAL, cross-verified official entity (the anti-fake step that is our commerce "
                 "value) and returned its official representative + a canonical key to buy safely; commerce "
                 "rail dormant (0 bps) until agent-commerce volume — buy-intent logged as the demand signal."
                 if ok else
                 "could not verify this as an official KoreaAPI entity — refusing to route a purchase "
                 "(safe-fail); buy-intent still logged as the demand signal."),
    }
