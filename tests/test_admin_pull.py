"""Offline test for `admin pull` (the turnkey live-ingestion command), HTTP monkeypatched.

`pull` ingests REAL Wikidata snapshots with one command; it needs egress at runtime. Here
we patch the HTTP call so the full wiring - adapter -> parse -> identity-verify -> ingest
-> append - is proven without network. With a real open network the same command pulls
live data.

Run:  PYTHONPATH=src python -m pytest tests/test_admin_pull.py -q
"""

from __future__ import annotations

import asyncio
import json
import pathlib

from koreaapi import admin
from koreaapi.pipeline import store
from koreaapi.sources.wikidata import WikidataSource

GOOD = json.loads(
    (pathlib.Path(__file__).parent / "fixtures" / "wikidata_bts.json").read_text(encoding="utf-8")
)


def test_pull_ingests_real_shaped_snapshot(monkeypatch, tmp_path):
    # Patch the only network call; resolve_qid uses the curated map (no network) for bts.
    monkeypatch.setattr(WikidataSource, "_http_get", lambda self, url: GOOD)
    db = str(tmp_path / "pull.db")

    out = asyncio.run(admin.pull(["artist:bts"], db_path=db))

    assert out["ingested"] == ["artist:bts"]
    assert out["failed"] == []

    rec = asyncio.run(store.latest("artist:bts", "facts", db_path=db))
    assert rec is not None
    assert rec.name.en_official == "BTS"
    assert rec.name.ko == "방탄소년단"
    assert any("Wikidata" in s for s in rec.provenance.sources)  # provenance cites Wikidata
    # single live source -> cross-verification impossible -> Skill Score capped (honest)
    assert rec.provenance.skill_score <= 0.7


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
