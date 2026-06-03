"""Offline tests for the YouTube source (parse + identity guard) and the release ingest.

The PARSE steps and the identity guard are fully tested with saved YouTube Data API v3
responses. The live HTTP fetch needs YOUTUBE_API_KEY + egress (GitHub run / your machine), so
it is not exercised offline.

Run:  PYTHONPATH=src python -m pytest tests/test_youtube.py -q
"""

from __future__ import annotations

import asyncio
import json
import os
import pathlib
import tempfile

from koreaapi.pipeline import store
from koreaapi.pipeline.ingest import ingest_youtube
from koreaapi.sources.youtube import (
    _alias_norms,
    parse_channel,
    parse_latest,
    parse_search,
    pick_channel,
)

FIX = pathlib.Path(__file__).parent / "fixtures"
SEARCH = json.loads((FIX / "youtube_search_bts.json").read_text(encoding="utf-8"))
CHANNEL = json.loads((FIX / "youtube_channel_bts.json").read_text(encoding="utf-8"))
LATEST = json.loads((FIX / "youtube_latest_bts.json").read_text(encoding="utf-8"))


def _tmp_db() -> str:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(path)
    return path


def test_parse_search_lists_channels():
    cands = parse_search(SEARCH)
    assert [c["title"] for c in cands] == ["BANGTANTV", "BTS Army Fanbase"]
    assert cands[0]["channel_id"] == "UCLkAepWjdylmXSltofFvsYQ"


def test_identity_guard_picks_official_skips_fan():
    # BTS's official channel is titled "BANGTANTV" (alias), the fan channel is not -> picked.
    picked = pick_channel(parse_search(SEARCH), _alias_norms("artist:bts"))
    assert picked is not None and picked["channel_id"] == "UCLkAepWjdylmXSltofFvsYQ"


def test_identity_guard_rejects_when_no_alias_matches():
    # aespa's aliases don't match BANGTANTV or the fan channel -> nothing accepted (never poison).
    assert pick_channel(parse_search(SEARCH), _alias_norms("artist:aespa")) is None


def test_pick_channel_tolerates_non_dict_entries():
    # Regression: a raw (un-parsed) response yields string keys; pick_channel must not crash on
    # them (the bug that made fetch silently return None for every artist).
    assert pick_channel(["kind", "items", {"title": "BANGTANTV"}], _alias_norms("artist:bts")) == {
        "title": "BANGTANTV"
    }
    assert pick_channel(["kind", "items"], _alias_norms("artist:bts")) is None


def test_parse_channel_extracts_stats_and_uploads():
    ch = parse_channel(CHANNEL)
    assert ch["channel_id"] == "UCLkAepWjdylmXSltofFvsYQ"
    assert ch["subscribers"] == 77100000
    assert ch["views"] == 23456789012
    assert ch["uploads_playlist"] == "UULkAepWjdylmXSltofFvsYQ"


def test_parse_channel_hides_hidden_subscriber_count():
    raw = {"items": [{"id": "X", "snippet": {"title": "X"},
                      "statistics": {"hiddenSubscriberCount": True, "viewCount": "10"}}]}
    ch = parse_channel(raw)
    assert ch["subscribers"] is None and ch["views"] == 10


def test_parse_latest_extracts_video():
    latest = parse_latest(LATEST)
    assert latest is not None
    assert latest["video_id"] == "abc123XYZ45"
    assert latest["published_at"] == "2026-06-01T09:00:00Z"


def test_parse_latest_empty_returns_none():
    assert parse_latest({"items": []}) is None


def test_ingest_youtube_appends_release_snapshot():
    db = _tmp_db()
    payload = {
        "channel_id": "UCLkAepWjdylmXSltofFvsYQ",
        "title": "BANGTANTV",
        "subscribers": 77100000,
        "views": 23456789012,
        "videos": 2345,
        "latest": {"video_id": "abc123XYZ45", "title": "Spring Day 2026 MV",
                   "published_at": "2026-06-01T09:00:00Z"},
        "name_en": "BTS",
        "citation": "YouTube BANGTANTV 2026-06-03 00:00 UTC",
        "source_url": "https://www.youtube.com/channel/UCLkAepWjdylmXSltofFvsYQ",
    }
    rec = asyncio.run(ingest_youtube("artist:bts", payload, db_path=db))
    assert rec is not None and rec.kind == "release"
    assert rec.provenance.skill_score <= 0.7  # single official source -> capped (honest)
    assert "77,100,000 subscribers" in rec.summary_en
    assert "Spring Day 2026 MV" in rec.summary_en
    assert rec.data["channel_id"] == "UCLkAepWjdylmXSltofFvsYQ"

    got = asyncio.run(store.latest("artist:bts", "release", db_path=db))
    assert got is not None and got.data["subscribers"] == 77100000


def test_ingest_youtube_none_payload_is_noop():
    assert asyncio.run(ingest_youtube("artist:bts", None, db_path=_tmp_db())) is None
    assert asyncio.run(ingest_youtube("artist:bts", {"title": "x"}, db_path=_tmp_db())) is None


def test_diagnose_reports_missing_key_without_network(monkeypatch):
    from koreaapi.sources.youtube import YouTubeSource

    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    d = YouTubeSource().diagnose("artist:bts")
    assert d["key_present"] is False  # no network touched when the key is absent
    assert d["candidates"] == [] and d["picked"] is None and d["error"] is None
    assert "bangtantv" in d["aliases"]  # roster name + curated alias, normalized


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
