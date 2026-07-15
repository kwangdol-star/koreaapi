"""The freshness engine: admin.refresh re-verifies the STALEST verified entities, oldest first.

pull covers only the curated roster and sweep/discover only ADD — so a discovered entity used to get
exactly one snapshot and age past the facts TTL forever ('everything is stale'). refresh closes that:
bounded per run, threshold at half-TTL (refresh-before-stale), the memoized Wikidata Q-id from
provenance as the re-ingest context, a failed refresh appends nothing (retried next run). Offline via
injected sources."""

from __future__ import annotations

import asyncio
import tempfile
from datetime import datetime, timedelta, timezone

from koreaapi import admin
from koreaapi.models import Name, Provenance, Record
from koreaapi.pipeline import store
from koreaapi.sources.mock import MockSource

NOW = datetime.now(timezone.utc)


def _add(db: str, eid: str, ko: str, en: str, *, age_days: float, qid: str = "Q1") -> None:
    at = NOW - timedelta(days=age_days)
    asyncio.run(store.append_record(Record(
        entity_id=eid, kind="facts", name=Name(ko=ko, en_official=en), snapshot_at=at,
        summary_en=en, data={}, provenance=Provenance(
            sources=[f"Wikidata {qid} 2026-01-01 00:00 UTC", "Wikipedia x 2026-01-01 00:00 UTC"],
            fetched_at=at, skill_score=1.0, confidence="high", agreeing_sources=2)), db_path=db))


class _Boom:
    name = "Wikidata"
    is_fallback = False

    async def fetch(self, entity_id: str, kind: str) -> dict:
        raise ValueError("network down")


def test_refresh_targets_stalest_first_and_appends_new_snapshots():
    db = tempfile.mktemp(suffix=".db")
    _add(db, "place:old", "옛곳", "Old Place", age_days=20)      # stalest -> first
    _add(db, "temple:mid", "중간", "Mid Temple", age_days=10)    # stale -> second
    _add(db, "artist:fresh", "신곡", "Fresh Artist", age_days=1)  # inside half-TTL -> untouched

    p = {"name_ko": "옛곳", "name_en_official": "Old Place", "name_en_source": "official", "summary_en": "x"}
    src = [MockSource("Wikidata", p), MockSource("Wikipedia", p)]
    out = asyncio.run(admin.refresh(db_path=db, max_n=1, sources=src))
    assert out["attempted"] == ["place:old"]                     # oldest FIRST, bounded by max_n
    assert out["refreshed"] == ["place:old"] and out["stale"] == 2
    latest = asyncio.run(store.latest("place:old", "facts", db_path=db))
    assert (NOW - latest.snapshot_at.replace(tzinfo=timezone.utc)).total_seconds() < 3600  # re-verified now

    fresh = asyncio.run(store.latest("artist:fresh", "facts", db_path=db))
    assert (NOW - fresh.snapshot_at.replace(tzinfo=timezone.utc)).days >= 1  # fresh one untouched


def test_refresh_failure_appends_nothing_and_stays_in_the_pool():
    db = tempfile.mktemp(suffix=".db")
    _add(db, "place:old", "옛곳", "Old Place", age_days=20)
    out = asyncio.run(admin.refresh(db_path=db, max_n=5, sources=[_Boom()]))
    assert out["failed"] == ["place:old"] and out["refreshed"] == []
    latest = asyncio.run(store.latest("place:old", "facts", db_path=db))
    assert (NOW - latest.snapshot_at.replace(tzinfo=timezone.utc)).days >= 19  # unchanged -> retried next run


def test_refresh_threshold_is_half_ttl_by_default():
    db = tempfile.mktemp(suffix=".db")
    _add(db, "place:aging", "노화", "Aging Place", age_days=4)    # > 3.5d (half of 7d) -> in the pool
    _add(db, "place:young", "젊음", "Young Place", age_days=3)    # < 3.5d -> not yet
    p = {"name_ko": "노화", "name_en_official": "Aging Place", "name_en_source": "official", "summary_en": "x"}
    out = asyncio.run(admin.refresh(db_path=db, max_n=10,
                                    sources=[MockSource("Wikidata", p), MockSource("Wikipedia", p)]))
    assert out["attempted"] == ["place:aging"]                    # refresh-BEFORE-stale, not after


def test_refresh_stride_spreads_the_budget_past_zombies():
    # A permanently-failing entity (deleted/renamed upstream) must not monopolize the head slot every
    # run and starve the pool behind it: the budget is STRIDE-sampled across all eligible entities.
    db = tempfile.mktemp(suffix=".db")
    _add(db, "place:zombie", "좀비", "Zombie Oldest", age_days=30)
    _add(db, "temple:mid", "중간", "Mid", age_days=20)
    _add(db, "beach:young", "영", "Young Eligible", age_days=10)
    p = {"name_ko": "영", "name_en_official": "Young Eligible", "name_en_source": "official", "summary_en": "x"}
    out = asyncio.run(admin.refresh(db_path=db, max_n=2,
                                    sources=[MockSource("Wikidata", p), MockSource("Wikipedia", p)]))
    # stride ceil(3/2)=2 -> indexes 0 and 2: the zombie costs ONE slot, but the tail still gets served
    assert out["attempted"] == ["place:zombie", "beach:young"]


def test_refresh_never_downgrades_a_cross_verified_record(monkeypatch):
    # Partial-outage guard: a cross-verified record refreshes only when >=2 sources answer this cycle —
    # a single-source cycle would silently downgrade the tier (and drop source-specific fields).
    db = tempfile.mktemp(suffix=".db")
    _add(db, "place:rich", "부자", "Rich Place", age_days=20)          # agree=2 (cross-verified)
    p = {"name_ko": "부자", "name_en_official": "Rich Place", "name_en_source": "official", "summary_en": "x"}
    out = asyncio.run(admin.refresh(db_path=db, max_n=5,
                                    sources=[MockSource("Wikidata", p), _Boom()]))  # only ONE succeeds
    assert out["failed"] == ["place:rich"] and out["refreshed"] == []
    latest = asyncio.run(store.latest("place:rich", "facts", db_path=db))
    assert latest.provenance.agreeing_sources == 2                     # tier preserved; retried next run


def test_ingest_carries_verified_geo_forward_when_the_coord_source_fails():
    # Wikidata is the only geo writer: if it fails a cycle but others succeed, the previous verified
    # P625 coords ride forward — the entity must not flap out of nearby/clusters until the next
    # healthy refresh. The carried value is the same verified fact, never a guess.
    from koreaapi.pipeline.ingest import ingest_one
    db = tempfile.mktemp(suffix=".db")
    p1 = {"name_ko": "궁", "name_en_official": "Palace", "name_en_source": "official", "summary_en": "x",
          "geo": {"lat": 37.5796, "lon": 126.977}}
    asyncio.run(ingest_one("facts", "place:p", [MockSource("Wikidata", p1), MockSource("Wikipedia", p1)],
                           db_path=db))
    p2 = {"name_ko": "궁", "name_en_official": "Palace", "name_en_source": "official", "summary_en": "x"}
    rec = asyncio.run(ingest_one("facts", "place:p", [MockSource("Wikidata", p2), MockSource("Wikipedia", p2)],
                                 db_path=db))
    assert rec.data["geo"] == {"lat": 37.5796, "lon": 126.977}         # carried forward, not lost


def test_status_json_reports_the_stale_pool(tmp_path):
    # Operator observability for the freshness engine: status.json exposes stale (past TTL),
    # refresh_pool (past half-TTL — what refresh targets next), and the oldest snapshot age.
    import json
    db = tempfile.mktemp(suffix=".db")
    _add(db, "place:old", "옛곳", "Old Place", age_days=20)     # past the 7d TTL -> stale
    _add(db, "temple:mid", "중간", "Mid Temple", age_days=5)    # past half-TTL only -> pool, not stale
    _add(db, "artist:new", "신곡", "Fresh Artist", age_days=1)  # fresh
    out = str(tmp_path / "status.json")
    asyncio.run(admin.status_json(db_path=db, out_path=out))
    doc = json.load(open(out, encoding="utf-8"))
    assert doc["stale"] == 1
    assert doc["refresh_pool"] == 2
    assert doc["oldest_snapshot_days"] >= 19


def test_collect_workflow_runs_refresh_every_tick():
    wf = open("/home/user/koreaapi-build/.github/workflows/collect.yml", encoding="utf-8").read()
    assert "koreaapi.admin refresh" in wf                         # the freshness engine is wired into collect


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
