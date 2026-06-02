"""Agent-face service logic (pure, transport-agnostic).

Reads the append-only store and returns decision-ready dicts. Every item carries
provenance + Skill Score (invariant 2). server.py wraps these as MCP tools; tests
exercise them directly with no transport dependency or network.
"""

from __future__ import annotations

from .pipeline import store

_CALENDAR_KINDS = ("comeback", "release", "concert")


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
    }


async def artist_status(artist_id: str, *, db_path: str | None = None) -> dict:
    """Latest verified status across kinds for one artist. artist_id e.g. 'artist:bts'."""
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
    """Upcoming Korean culture events (comebacks, releases, concerts) with provenance."""
    recs = await store.recent(500, db_path=db_path)
    items = [_item(r) for r in recs if r.kind in _CALENDAR_KINDS]
    return {"window_days": window_days, "count": len(items), "items": items}


async def korea_rising(category: str = "all", limit: int = 10, *, db_path: str | None = None) -> dict:
    """What is rising in Korea now, ranked from accumulated verified snapshots (engine 2 seed)."""
    recs = await store.recent(500, db_path=db_path)
    ranked = sorted(
        recs, key=lambda r: (r.provenance.skill_score, r.snapshot_at), reverse=True
    )
    return {
        "category": category,
        "items": [_item(r) for r in ranked[:limit]],
        "note": (
            "Phase 1: ranked from accumulated verified snapshots; behavioral signal "
            "(queries/clicks) folds in once live."
        ),
    }


async def buy_options(item: str, *, db_path: str | None = None) -> dict:
    """Where to buy a release/ticket/goods. Phase 1: commerce rail pending; logs buy-intent."""
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
