"""Agent throughput — the highway convenience store. One call serves a whole watchlist (batch
verify/resolve), and get_changes(since=…) lets an agent re-pull only the delta. Offline."""

from __future__ import annotations

import asyncio
import tempfile
from datetime import datetime, timezone

from koreaapi import admin, service
from koreaapi.models import Name, Provenance, Record


def _seed(db: str, eid: str, ko: str, en: str, day: int = 7, agency: str | None = None) -> None:
    now = datetime(2026, 5, day, tzinfo=timezone.utc)
    asyncio.run(admin.store.append_record(Record(
        entity_id=eid, kind="facts", name=Name(ko=ko, en_official=en),
        snapshot_at=now, summary_en=en, data=({"agency_en": agency} if agency else {}),
        provenance=Provenance(sources=["Wikidata Q1", "Wikipedia x"], fetched_at=now,
                              skill_score=1.0, confidence="high", agreeing_sources=2)), db_path=db))


def test_batch_verifies_many_in_one_call():
    # The throughput win: an agent sweeps a watchlist in ONE round-trip, keyed by input (a miss is
    # still keyed — never crashes the whole batch).
    db = tempfile.mktemp(suffix=".db")
    _seed(db, "artist:bts", "방탄소년단", "BTS")
    _seed(db, "artist:newjeans", "뉴진스", "NewJeans")
    out = asyncio.run(service.batch(["artist:bts", "artist:newjeans", "artist:nobody"], db_path=db))
    assert out["op"] == "verified" and out["count"] == 3
    assert out["results"]["artist:bts"]["found"] and out["results"]["artist:bts"]["cross_verified"]
    assert out["results"]["artist:nobody"]["found"] is False
    assert out["license"]["id"] == "CC-BY-4.0"


def test_batch_resolve_maps_names_to_canonical():
    db = tempfile.mktemp(suffix=".db")
    _seed(db, "artist:bts", "방탄소년단", "BTS")
    out = asyncio.run(service.batch(["BTS", "방탄소년단"], op="resolve", db_path=db))
    assert out["op"] == "resolve" and out["count"] == 2
    assert out["results"]["BTS"]["id"] == "artist:bts"
    assert out["results"]["방탄소년단"]["id"] == "artist:bts"


def test_batch_dedupes_caps_and_guards_unknown_op():
    db = tempfile.mktemp(suffix=".db")
    _seed(db, "artist:bts", "방탄소년단", "BTS")
    # duplicate + blank keys collapse: requested 3, one distinct real key
    dup = asyncio.run(service.batch(["artist:bts", "artist:bts", "  "], db_path=db))
    assert dup["requested"] == 3 and dup["count"] == 1 and dup["truncated"] is False
    # over the cap -> truncated flag set (not silently dropped), still safe
    many = asyncio.run(service.batch([f"artist:x{i}" for i in range(service._BATCH_MAX + 5)], db_path=db))
    assert many["truncated"] is True and many["count"] == service._BATCH_MAX
    # an unknown op safe-fails (no crash, empty results) rather than 500-ing
    bad = asyncio.run(service.batch(["artist:bts"], op="delete", db_path=db))
    assert bad["found"] is False and bad["count"] == 0 and bad["results"] == {}


def test_recent_changes_since_returns_only_the_delta():
    # incremental sync: an agent caches the feed, then re-pulls only changes AFTER its cursor.
    db = tempfile.mktemp(suffix=".db")
    _seed(db, "artist:newjeans", "뉴진스", "NewJeans", day=1, agency="ADOR")
    _seed(db, "artist:newjeans", "뉴진스", "NewJeans", day=9, agency="HYBE")  # 소속사 moved on 05-09
    full = asyncio.run(service.recent_changes(db_path=db))
    assert full["count"] == 1 and full["since"] is None
    at_cursor = asyncio.run(service.recent_changes(since="2026-05-09", db_path=db))
    assert at_cursor["count"] == 0 and at_cursor["since"] == "2026-05-09"  # nothing strictly after
    before_cursor = asyncio.run(service.recent_changes(since="2026-05-01", db_path=db))
    assert before_cursor["count"] == 1  # the 05-09 change is after the 05-01 cursor


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
