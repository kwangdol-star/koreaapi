"""Disaster-recovery self-heal (admin.bootstrap): the accumulated DB lives in the Actions cache, and an
eviction silently resets ~5k discovered entities to the roster. The current state is already public
(/latest.json on the deployed site) — bootstrap detects a reset store and re-seeds from it, BEFORE the
collect steps run. Cold-start (no live site yet) reports and continues; never crashes the tick."""

from __future__ import annotations

import asyncio
import io
import json
import tempfile
import urllib.request
from datetime import datetime, timezone

from koreaapi import admin
from koreaapi.models import Name, Provenance, Record
from koreaapi.pipeline import store


def _record(eid: str, ko: str, en: str) -> dict:
    return json.loads(Record(
        entity_id=eid, kind="facts", name=Name(ko=ko, en_official=en),
        snapshot_at=datetime(2026, 6, 1, tzinfo=timezone.utc), summary_en=en, data={},
        provenance=Provenance(sources=["Wikidata Q1", "Wikipedia x"], fetched_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
                              skill_score=1.0, confidence="high", agreeing_sources=2)).model_dump_json())


def test_bootstrap_heals_a_reset_store_from_the_live_site(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)                                  # data/latest.json lands in a sandbox
    db = tempfile.mktemp(suffix=".db")
    payload = json.dumps([_record("artist:bts", "방탄소년단", "BTS"),
                          _record("place:gyeongbokgung", "경복궁", "Gyeongbokgung")]).encode()
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=60: io.BytesIO(payload))

    out = asyncio.run(admin.bootstrap(db_path=db, min_entities=1000))
    assert out["healed"] is True and out["restored"] == 2 and out["facts_before"] == 0
    rec = asyncio.run(store.latest("artist:bts", "facts", db_path=db))
    assert rec.name.ko == "방탄소년단"
    assert rec.snapshot_at.date().isoformat() == "2026-06-01"    # file timestamps preserved, not re-stamped


def test_bootstrap_skips_a_healthy_store_without_fetching(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db = tempfile.mktemp(suffix=".db")
    asyncio.run(store.append_record(Record.model_validate(_record("artist:bts", "방탄소년단", "BTS")),
                                    db_path=db))

    def boom(req, timeout=60):
        raise AssertionError("must not fetch when the store is healthy")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    out = asyncio.run(admin.bootstrap(db_path=db, min_entities=1))
    assert out["healed"] is False and "healthy" in out["note"]


def test_bootstrap_cold_start_reports_and_continues(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db = tempfile.mktemp(suffix=".db")

    def down(req, timeout=60):
        raise OSError("no live site yet")

    monkeypatch.setattr(urllib.request, "urlopen", down)
    out = asyncio.run(admin.bootstrap(db_path=db, min_entities=1000))
    assert out["healed"] is False and "continuing cold" in out["note"]   # a first-ever run stays calm


def test_collect_workflow_self_heals_before_collecting():
    wf = open("/home/user/koreaapi-build/.github/workflows/collect.yml", encoding="utf-8").read()
    assert "koreaapi.admin bootstrap" in wf
    assert wf.index("admin bootstrap") < wf.index("admin pull")          # heal FIRST, then collect


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
