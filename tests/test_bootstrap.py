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

    out = asyncio.run(admin.bootstrap(db_path=db, min_entities=2))  # live corpus must itself be >= threshold
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


def test_bootstrap_refuses_a_truncated_live_corpus(tmp_path, monkeypatch):
    # A truncated live latest.json (e.g. after a bad deploy) must not be echoed back in on every tick.
    monkeypatch.chdir(tmp_path)
    db = tempfile.mktemp(suffix=".db")
    payload = json.dumps([_record("artist:bts", "방탄소년단", "BTS")]).encode()   # 1 << threshold
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=60: io.BytesIO(payload))
    out = asyncio.run(admin.bootstrap(db_path=db, min_entities=1000))
    assert out["healed"] is False and "refusing to heal" in out["note"]


def test_pages_workflow_self_heals_and_gates_at_corpus_scale():
    # The cache-eviction disaster: without bootstrap, a pages build on a fresh DB would be roster-only,
    # PASS a 100-entity gate, and OVERWRITE the live /latest.json — destroying bootstrap's own recovery
    # source. pages must heal first AND gate above roster size.
    wf = open("/home/user/koreaapi-build/.github/workflows/pages.yml", encoding="utf-8").read()
    assert "koreaapi.admin bootstrap" in wf and wf.index("admin bootstrap") < wf.index("admin pull")
    assert "verifysite _site 1000" in wf                      # 1000 > the ~658-entity roster


def test_every_documented_dormant_key_is_wired_in_the_workflows():
    # 'Activation is adding a repo secret' (OPERATIONS) is only true if the workflow maps the secret
    # into env — KOPIS/KHERITAGE once weren't. Pin every documented rail key into BOTH workflows.
    keys = ("TMDB_API_KEY", "TOURAPI_KEY", "KOSIS_API_KEY", "KOPIS_API_KEY",
            "KHERITAGE_API_KEY", "YOUTUBE_API_KEY", "ANTHROPIC_API_KEY")
    for wf in ("collect.yml", "pages.yml"):
        text = open(f"/home/user/koreaapi-build/.github/workflows/{wf}", encoding="utf-8").read()
        missing = [k for k in keys if f"secrets.{k}" not in text]
        assert not missing, f"{wf} missing env mapping for: {missing}"


def test_collect_workflow_self_heals_before_collecting():
    wf = open("/home/user/koreaapi-build/.github/workflows/collect.yml", encoding="utf-8").read()
    assert "koreaapi.admin bootstrap" in wf
    assert wf.index("admin bootstrap") < wf.index("admin pull")          # heal FIRST, then collect


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
