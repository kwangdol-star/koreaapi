"""Offline test for `admin pull` (turnkey live ingestion), HTTP monkeypatched.

`pull` uses TWO independent sources (Wikidata + Wikipedia); patching both HTTP calls to
fixtures proves the full wiring - adapter -> parse -> identity-verify -> CROSS-VERIFY ->
ingest -> append - and that two sources agreeing on the name clear the single-source cap.

Run:  PYTHONPATH=src python -m pytest tests/test_admin_pull.py -q
"""

from __future__ import annotations

import asyncio
import json
import pathlib

from koreaapi import admin
from koreaapi.pipeline import store
from koreaapi.sources.wikidata import WikidataSource
from koreaapi.sources.wikipedia import WikipediaSource

FIX = pathlib.Path(__file__).parent / "fixtures"
WD = json.loads((FIX / "wikidata_bts.json").read_text(encoding="utf-8"))
WP = json.loads((FIX / "wikipedia_bts.json").read_text(encoding="utf-8"))


def test_pull_cross_verifies_two_live_sources(monkeypatch, tmp_path):
    monkeypatch.setattr(WikidataSource, "_http_get", lambda self, url: WD)
    monkeypatch.setattr(WikipediaSource, "_http_get", lambda self, url: WP)
    db = str(tmp_path / "pull.db")

    out = asyncio.run(admin.pull(["artist:bts"], db_path=db))

    assert out["ingested"] == ["artist:bts"]
    assert out["failed"] == []

    rec = asyncio.run(store.latest("artist:bts", "facts", db_path=db))
    assert rec is not None
    assert rec.name.en_official == "BTS" and rec.name.ko == "방탄소년단"
    assert len(rec.provenance.sources) == 2  # Wikidata + Wikipedia cited
    assert rec.provenance.skill_score >= 0.8  # cross-verified -> clears single-source cap
    assert rec.provenance.confidence == "high"


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
