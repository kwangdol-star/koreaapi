"""Offline tests for the Wikipedia adapter (real source #2) + cross-verification.

parse_page is fixture-tested (no network). Integration tests prove that two INDEPENDENT
sources agreeing on the NAME (even with different summaries, as Wikidata vs Wikipedia really
are) cross-verify -> Skill Score clears the single-source 0.7 cap; and that sources naming
different entities do not. Live fetch is in test_wikipedia_live.py (auto-skips offline).
"""

from __future__ import annotations

import asyncio
import json
import os
import pathlib
import tempfile

from koreaapi.pipeline.ingest import ingest_one
from koreaapi.sources.mock import MockSource
from koreaapi.sources.wikipedia import parse_page

WP = json.loads(
    (pathlib.Path(__file__).parent / "fixtures" / "wikipedia_bts.json").read_text(encoding="utf-8")
)


def _tmp_db() -> str:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(path)
    return path


def test_parse_page_extracts_bilingual_name():
    payload = parse_page(WP, "artist:bts", "facts")
    assert payload["name_en_official"] == "BTS"
    assert payload["name_ko"] == "방탄소년단"  # from the ko interlanguage link
    assert payload["name_en_source"] == "official"


def test_two_sources_agreeing_on_name_cross_verify():
    # same NAME, deliberately DIFFERENT summaries (the real Wikidata vs Wikipedia case)
    wd = {"name_ko": "방탄소년단", "name_en_official": "BTS", "name_en_source": "official",
          "summary_en": "BTS - facts (Wikidata labels)."}
    wp = {"name_ko": "방탄소년단", "name_en_official": "BTS", "name_en_source": "official",
          "summary_en": "BTS - facts (Wikipedia)."}
    rec = asyncio.run(
        ingest_one("facts", "artist:bts",
                   [MockSource("Wikidata", wd), MockSource("Wikipedia", wp)], db_path=_tmp_db())
    )
    assert rec is not None
    assert len(rec.provenance.sources) == 2
    assert rec.provenance.skill_score >= 0.8  # cross-verified -> clears the single-source cap
    assert rec.provenance.confidence == "high"


def test_parse_page_extracts_and_cleans_lead_description():
    # The substance fix: the lead extract becomes a real, attributed description (collapsed whitespace).
    raw = {"query": {"pages": [{"title": "Dokkaebi",
            "langlinks": [{"lang": "ko", "title": "도깨비"}],
            "extract": "A  dokkaebi  is a\ntype of deity or spirit in Korean folklore. Mischievous."}]}}
    p = parse_page(raw, "folklore:dokkaebi", "facts")
    assert p["name_en_official"] == "Dokkaebi" and p["name_ko"] == "도깨비"
    assert p["abstract_en"].startswith("A dokkaebi is a type of deity or spirit in Korean folklore.")
    assert "  " not in p["abstract_en"] and "\n" not in p["abstract_en"]  # whitespace collapsed
    # a page with no extract still parses (the abstract is supplementary, never required)
    no_ext = {"query": {"pages": [{"title": "X", "langlinks": []}]}}
    assert parse_page(no_ext, "folklore:x", "facts")["abstract_en"] is None


def test_clean_extract_caps_on_sentence_boundary_and_handles_blank():
    from koreaapi.sources.wikipedia import _clean_extract
    out = _clean_extract("Sentence one is here. " * 60, cap=80)
    assert len(out) <= 84 and out.endswith((".", "…"))
    assert _clean_extract("   ") is None and _clean_extract(None) is None


def test_abstract_from_wikipedia_enriches_the_verified_record():
    # Wikidata wins the NAME vote (chosen) but carries NO abstract; Wikipedia carries the description.
    # The merge pulls it across so the verified record has real substance (the monetizable bit), while
    # the Skill Score still reflects only the NAME cross-verification (abstract can't inflate it).
    wd = {"name_ko": "도깨비", "name_en_official": "Dokkaebi", "name_en_source": "official",
          "summary_en": "Dokkaebi - facts (Wikidata labels)."}
    wp = {"name_ko": "도깨비", "name_en_official": "Dokkaebi", "name_en_source": "official",
          "summary_en": "Dokkaebi - facts (Wikipedia).",
          "abstract_en": "A dokkaebi is a type of deity or spirit in Korean folklore."}
    rec = asyncio.run(ingest_one("facts", "folklore:dokkaebi",
                      [MockSource("Wikidata", wd), MockSource("Wikipedia", wp)], db_path=_tmp_db()))
    assert rec.data.get("abstract_en") == "A dokkaebi is a type of deity or spirit in Korean folklore."
    assert rec.provenance.skill_score >= 0.8  # name still cross-verified; abstract doesn't change it


def test_two_sources_disagreeing_on_name_do_not_fully_verify():
    a = {"name_ko": "방탄소년단", "name_en_official": "BTS", "name_en_source": "official", "summary_en": "x"}
    b = {"name_ko": "에스파", "name_en_official": "aespa", "name_en_source": "official", "summary_en": "y"}
    rec = asyncio.run(
        ingest_one("facts", "artist:bts",
                   [MockSource("A", a), MockSource("B", b)], db_path=_tmp_db())
    )
    assert rec is not None
    # naming different entities is NOT a cross-verify: must be capped at the single-source level and
    # never read "high" (regression guard — this used to score 0.85/high, beating a clean source).
    assert rec.provenance.skill_score <= 0.7
    assert rec.provenance.confidence != "high"


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
