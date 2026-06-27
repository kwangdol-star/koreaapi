"""The append-only store is the moat. Two load-bearing invariants that were previously untested:
(1) ordering is CHRONOLOGICAL — `latest` returns the newest snapshot and `recent` is newest-first
even when rows are inserted out of order (relies on UTC-normalized ISO timestamps sorting lexically);
(2) APPEND-ONLY — re-ingesting never overwrites; the prior snapshot stays retrievable, byte-identical.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from datetime import datetime, timedelta, timezone

from koreaapi.models import Name, Provenance, Record
from koreaapi.pipeline import store


def _tmp_db() -> str:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(path)
    return path


def _rec(summary: str, when: datetime, data: dict) -> Record:
    return Record(
        entity_id="artist:bts", kind="facts",
        name=Name(ko="방탄소년단", en_official="BTS"), snapshot_at=when,
        summary_en=summary, data=data,
        provenance=Provenance(sources=["Wikidata Q1", "Wikipedia BTS"], fetched_at=when,
                              skill_score=1.0, confidence="high"),
    )


def test_latest_and_recent_are_chronological_despite_insert_order():
    db = _tmp_db()
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    older = _rec("older", base, {"v": 1})
    newer = _rec("newer", base + timedelta(days=10), {"v": 2})
    # insert NEWER first, then OLDER — ordering must come from snapshot_at, not insert order
    asyncio.run(store.append_record(newer, db_path=db))
    asyncio.run(store.append_record(older, db_path=db))
    latest = asyncio.run(store.latest("artist:bts", "facts", db_path=db))
    assert latest.summary_en == "newer"                       # newest by snapshot_at, not last inserted
    recents = asyncio.run(store.recent(10, db_path=db))
    assert [r.summary_en for r in recents] == ["newer", "older"]  # strictly newest-first


def test_append_only_preserves_the_prior_snapshot():
    db = _tmp_db()
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    v1 = _rec("v1", base, {"agency_en": "Big Hit Entertainment"})
    v2 = _rec("v2", base + timedelta(days=30), {"agency_en": "Big Hit Music"})  # agency renamed
    asyncio.run(store.append_record(v1, db_path=db))
    asyncio.run(store.append_record(v2, db_path=db))
    recents = asyncio.run(store.recent(10, db_path=db))
    assert len(recents) == 2                                   # nothing overwritten
    by_summary = {r.summary_en: r for r in recents}
    assert by_summary["v1"].data["agency_en"] == "Big Hit Entertainment"  # history intact, unchanged
    assert by_summary["v2"].data["agency_en"] == "Big Hit Music"
    assert asyncio.run(store.latest("artist:bts", "facts", db_path=db)).summary_en == "v2"


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
