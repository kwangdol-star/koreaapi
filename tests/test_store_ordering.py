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


def _rec2(eid: str, summary: str, when: datetime, kind: str = "facts") -> Record:
    return Record(
        entity_id=eid, kind=kind, name=Name(ko="이름", en_official=summary), snapshot_at=when,
        summary_en=summary, data={},
        provenance=Provenance(sources=["Wikidata Q1", "Wikipedia x"], fetched_at=when,
                              skill_score=1.0, confidence="high"),
    )


def test_latest_all_matches_per_entity_latest():
    # latest_all is the ONE-query batch companion the serving paths use; it must agree with latest()
    # exactly — newest snapshot per entity (kind-filtered) / per (entity, kind) when kind is None.
    db = _tmp_db()
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    asyncio.run(store.append_record(_rec2("artist:a", "a-old", base), db_path=db))
    asyncio.run(store.append_record(_rec2("artist:a", "a-new", base + timedelta(days=3)), db_path=db))
    asyncio.run(store.append_record(_rec2("place:b", "b-only", base + timedelta(days=1)), db_path=db))
    asyncio.run(store.append_record(_rec2("artist:a", "a-chart", base + timedelta(days=5), kind="chart"),
                                    db_path=db))

    facts = asyncio.run(store.latest_all("facts", db_path=db))
    assert set(facts) == {"artist:a", "place:b"}
    assert facts["artist:a"].summary_en == "a-new"          # newest facts snapshot, chart NOT leaked in
    for eid in facts:                                        # agrees with the per-entity path exactly
        assert facts[eid].summary_en == asyncio.run(store.latest(eid, "facts", db_path=db)).summary_en

    every = asyncio.run(store.latest_all(None, db_path=db))
    assert every[("artist:a", "chart")].summary_en == "a-chart"   # kind=None keys by (entity, kind)
    assert list(every)[0] == ("artist:a", "chart")                # newest-first order (matches entities())


def test_resolve_scan_is_single_query_not_n_plus_1(monkeypatch):
    # Regression guard for the N+1 collapse: a NAME resolve over the store must not call the
    # per-entity latest() at all (5,300 SQLite round-trips per MCP/HTTP request at live scale).
    from koreaapi import service
    db = _tmp_db()
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i in range(5):
        asyncio.run(store.append_record(_rec2(f"artist:e{i}", f"Entity {i}", base), db_path=db))
    calls = {"n": 0}
    real = store.latest

    async def counting(*a, **k):
        calls["n"] += 1
        return await real(*a, **k)

    monkeypatch.setattr(service.store, "latest", counting)
    out = asyncio.run(service.resolve("Entity 3", db_path=db))
    assert out["found"] and out["id"] == "artist:e3"
    assert calls["n"] == 0                                   # the scan went through latest_all only
