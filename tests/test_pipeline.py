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


def test_foreign_title_uses_official_korean_name_not_wikidata_label():
    # REGRESSION (빈첸초 bug): for a foreign-origin title, Wikidata's community ko label can be a WRONG
    # transliteration ('빈첸초'); the Korean Wikipedia langlink + TMDB original_title carry the official
    # '빈센조'. The verified record must (1) use '빈센조', (2) keep a clean English name (no '(TV series)'),
    # (3) PRESERVE Wikidata's structured data, (4) merge the Wikipedia abstract, (5) count WP+TMDB as agreeing.
    wd = {"name_ko": "빈첸초", "name_en_official": "Vincenzo", "name_en_source": "official",
          "agency_en": "tvN", "debut": "2021", "members": ["Song Joong-ki"], "summary_en": "x"}
    wp = {"name_ko": "빈센조", "name_en_official": "Vincenzo (TV series)", "name_en_source": "official",
          "abstract_en": "Vincenzo is a 2021 South Korean television series.", "summary_en": "y"}
    tmdb = {"name_ko": "빈센조", "name_en_official": "Vincenzo", "name_en_source": "official", "summary_en": "z"}
    rec = asyncio.run(ingest_one("facts", "drama:vincenzo",
        [MockSource("Wikidata", wd), MockSource("Wikipedia", wp), MockSource("TMDB", tmdb)], db_path=_tmp_db()))
    assert rec.name.ko == "빈센조"                              # official, NOT Wikidata's '빈첸초'
    assert rec.name.en_official == "Vincenzo"                  # clean, no '(TV series)' suffix
    assert rec.data.get("agency_en") == "tvN"                  # Wikidata's structured data preserved
    assert (rec.data.get("abstract_en") or "").startswith("Vincenzo is a 2021")  # Wikipedia abstract merged
    assert rec.provenance.agreeing_sources == 2                # WP + TMDB agree (suffix stripped)


def test_wikipedia_langlink_beats_wikidata_label_when_no_official_source():
    # Even without TMDB, the Korean Wikipedia article title (langlink) outranks Wikidata's label for the
    # canonical Korean name, while Wikidata's structured data is still kept.
    wd = {"name_ko": "빈첸초", "name_en_official": "Vincenzo", "name_en_source": "official",
          "agency_en": "tvN", "summary_en": "x"}
    wp = {"name_ko": "빈센조", "name_en_official": "Vincenzo (TV series)", "name_en_source": "official", "summary_en": "y"}
    rec = asyncio.run(ingest_one("facts", "drama:vincenzo",
        [MockSource("Wikidata", wd), MockSource("Wikipedia", wp)], db_path=_tmp_db()))
    assert rec.name.ko == "빈센조"               # Korean Wikipedia article title, not Wikidata's label
    assert rec.data.get("agency_en") == "tvN"    # Wikidata structured data still kept


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
