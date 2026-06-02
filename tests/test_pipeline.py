"""End-to-end test for the append-only ingestion heart (component A).

Runs fully offline (MockSource) - no API keys or network. Proves:
  - bilingual normalization keeps the OFFICIAL English name (not a translation)
  - provenance + Skill Score are attached
  - the store is APPEND-ONLY (re-ingest -> a new snapshot, not an overwrite)

Run:  PYTHONPATH=src python -m pytest tests -q
  or: PYTHONPATH=src python tests/test_pipeline.py
"""

from __future__ import annotations

import asyncio
import os
import tempfile

from koreaapi.pipeline import store
from koreaapi.pipeline.ingest import ingest_one
from koreaapi.sources.mock import MockSource

BTS = {
    "name_ko": "방탄소년단",
    "name_en_official": "BTS",
    "name_romanized": "Bangtan Sonyeondan",
    "name_en_source": "official",
    "name_en_confidence": "high",
    "title_ko": "신곡",
    "title_en": "New Single",
    "title_en_source": "official",
    "date": "2026-06-13",
    "summary_en": "BTS comeback scheduled 2026-06-13.",
    "summary_ko": "방탄소년단 컴백 2026-06-13.",
}


def _tmp_db() -> str:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(path)  # let the store create it fresh
    return path


def test_ingest_appends_bilingual_verified_snapshot():
    db = _tmp_db()
    sources = [MockSource("Circle Chart", BTS), MockSource("Wikidata", BTS)]

    rec = asyncio.run(ingest_one("comeback", "artist:bts", sources, db_path=db))

    assert rec is not None
    assert rec.name.ko == "방탄소년단"
    assert rec.name.en_official == "BTS"  # official name, not a translation
    assert rec.name.romanized == "Bangtan Sonyeondan"
    assert rec.provenance.skill_score >= 0.8  # two agreeing official sources, fresh
    assert rec.provenance.confidence == "high"
    assert len(rec.provenance.sources) == 2
    assert rec.provenance.translation.source == "official"

    got = asyncio.run(store.latest("artist:bts", "comeback", db_path=db))
    assert got is not None and got.name.en_official == "BTS"


def test_store_is_append_only():
    db = _tmp_db()
    sources = [MockSource("Circle Chart", BTS)]

    asyncio.run(ingest_one("comeback", "artist:bts", sources, db_path=db))
    asyncio.run(ingest_one("comeback", "artist:bts", sources, db_path=db))

    n = asyncio.run(store.count("artist:bts", "comeback", db_path=db))
    assert n == 2  # appended, not overwritten -> the moat


if __name__ == "__main__":
    test_ingest_appends_bilingual_verified_snapshot()
    test_store_is_append_only()
    print("all tests passed")
