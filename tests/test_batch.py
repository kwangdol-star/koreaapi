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


def test_batch_isolates_a_failing_item(monkeypatch):
    # one raising lookup (a corrupt/legacy record) must NOT sink the whole batch — it's keyed as an error.
    db = tempfile.mktemp(suffix=".db")
    _seed(db, "artist:bts", "방탄소년단", "BTS")
    real = service.verified

    async def flaky(entity_id, *, db_path=None):
        if entity_id == "artist:boom":
            raise RuntimeError("corrupt record")
        return await real(entity_id, db_path=db_path)

    monkeypatch.setattr(service, "verified", flaky)
    out = asyncio.run(service.batch(["artist:bts", "artist:boom"], db_path=db))
    assert out["count"] == 2
    assert out["results"]["artist:bts"]["found"] is True
    assert out["results"]["artist:boom"]["found"] is False and out["results"]["artist:boom"]["error"] == "lookup failed"


def test_recent_changes_since_validation_and_cursor():
    # A malformed cursor is IGNORED, not silently zeroed (that would read as "no changes" — the exact
    # staleness this feed fixes); the reply advances the agent via next_since.
    db = tempfile.mktemp(suffix=".db")
    _seed(db, "artist:newjeans", "뉴진스", "NewJeans", day=1, agency="ADOR")
    _seed(db, "artist:newjeans", "뉴진스", "NewJeans", day=9, agency="HYBE")
    bad = asyncio.run(service.recent_changes(since="garbage", db_path=db))
    assert bad["count"] == 1 and bad["since"] is None and "ignored malformed" in bad["note"]
    ok = asyncio.run(service.recent_changes(db_path=db))
    assert ok["next_since"].startswith("2026-05-09T") and ok["truncated"] is False  # full timestamp cursor


def test_recent_changes_cursor_is_sub_day_precise():
    # (e) the timestamp cursor: two changes on the SAME calendar day must BOTH be recoverable — a
    # day-granular cursor would silently drop the second. Seed distinct intraday snapshot times.
    db = tempfile.mktemp(suffix=".db")

    def snap(eid, ko, en, when, agency):
        asyncio.run(admin.store.append_record(Record(
            entity_id=eid, kind="facts", name=Name(ko=ko, en_official=en), snapshot_at=when,
            summary_en=en, data={"agency_en": agency}, provenance=Provenance(
                sources=["Wikidata Q1", "Wikipedia x"], fetched_at=when,
                skill_score=1.0, confidence="high", agreeing_sources=2)), db_path=db))

    def at(hour):
        return datetime(2026, 5, 9, hour, tzinfo=timezone.utc)

    snap("artist:a", "에이", "A", at(1), "L1")
    snap("artist:a", "에이", "A", at(2), "L2")   # a change @ 02:00
    snap("artist:b", "비", "B", at(1), "M1")
    snap("artist:b", "비", "B", at(6), "M2")     # another change @ 06:00 — same day
    out = asyncio.run(service.recent_changes(db_path=db))
    assert out["count"] == 2                                  # both same-day changes present, newest first
    earliest = min(c["at"] for c in out["changes"])          # the 02:00 change's full timestamp
    resume = asyncio.run(service.recent_changes(since=earliest, db_path=db))
    assert resume["count"] == 1 and resume["changes"][0]["to"] == "M2"  # the later same-day change survived


def test_recent_changes_since_returns_only_the_delta():
    # incremental sync: an agent caches the feed, then re-pulls only changes AFTER its cursor.
    db = tempfile.mktemp(suffix=".db")
    _seed(db, "artist:newjeans", "뉴진스", "NewJeans", day=1, agency="ADOR")
    _seed(db, "artist:newjeans", "뉴진스", "NewJeans", day=9, agency="HYBE")  # 소속사 moved on 05-09
    full = asyncio.run(service.recent_changes(db_path=db))
    assert full["count"] == 1 and full["since"] is None
    # resume from the EXACT timestamp cursor -> nothing strictly after it
    resume = asyncio.run(service.recent_changes(since=full["next_since"], db_path=db))
    assert resume["count"] == 0
    # a DATE cursor is inclusive of that whole day (so a same-day change is never dropped)
    same_day = asyncio.run(service.recent_changes(since="2026-05-09", db_path=db))
    assert same_day["count"] == 1
    before = asyncio.run(service.recent_changes(since="2026-05-01", db_path=db))
    assert before["count"] == 1  # the 05-09 change is after the 05-01 cursor


def test_recent_changes_offset_paginates_without_loss():
    # (G) a delta LARGER than `limit` must be fully drainable via offset paging — no event silently
    # dropped by a bare [:limit]. Loop offset=next_offset until it is null.
    db = tempfile.mktemp(suffix=".db")
    for i, ag in enumerate(["ADOR", "L1", "L2", "L3", "L4", "L5"], start=1):
        _seed(db, "artist:x", "엑스", "X", day=i, agency=ag)  # 5 change events (days 2..6)
    first = asyncio.run(service.recent_changes(limit=2, db_path=db))
    assert first["total"] == 5 and first["count"] == 2 and first["truncated"] is True
    assert first["next_offset"] == 2
    seen: list[str] = []
    offset, guard = 0, 0
    while offset is not None and guard < 10:
        guard += 1
        pg = asyncio.run(service.recent_changes(limit=2, offset=offset, db_path=db))
        seen += [c["to"] for c in pg["changes"]]
        offset = pg["next_offset"]
    assert sorted(seen) == ["L1", "L2", "L3", "L4", "L5"] and len(seen) == 5  # every event, exactly once


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
