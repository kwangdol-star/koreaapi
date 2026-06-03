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
    name: dict | None = None
    for e in ents:
        rec = await store.latest(artist_id, e["kind"], db_path=db_path)
        if rec is None:
            continue
        items.append(_item(rec))
        if name is None:
            name = {
                "ko": rec.name.ko,
                "en_official": rec.name.en_official,
                "romanized": rec.name.romanized,
            }
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
    behavioral signal) then Skill Score - engine 2 turning usage into the trend product."""
    await _log("query", f"rising:{category}", db_path)
    recs = await store.recent(500, db_path=db_path)
    signals = await store.top_signals(1000, kind="query", db_path=db_path)
    demand = {s["key"]: s["count"] for s in signals}  # entity_id -> queries observed
    ranked = sorted(
        recs,
        key=lambda r: (demand.get(r.entity_id, 0), r.provenance.skill_score, r.snapshot_at),
        reverse=True,
    )
    items = []
    for r in ranked[:limit]:
        it = _item(r)
        it["demand_signal"] = demand.get(r.entity_id, 0)  # engine 2: queries seen for this entity
        items.append(it)
    return {
        "category": category,
        "items": items,
        "note": (
            "Ranked by observed demand (behavioral signal) then Skill Score; only verified "
            "snapshots are surfaced. demand_signal = queries seen for that entity."
        ),
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
