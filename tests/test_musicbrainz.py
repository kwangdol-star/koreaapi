"""MusicBrainz — a TRULY independent 3rd source (artists). Wikidata + Wikipedia are correlated;
MusicBrainz is a separate DB, so it (a) raises the trust tier to ‘triple cross-verified’ when it
agrees, and (b) RESCUES an artist whose Wikipedia cross-check failed (it + Wikidata still make >=2
agreeing -> clears the single-source cap). Parse + identity guard are pure/offline; it self-filters
to artists. Live fetch is exercised on the open network (not here)."""

from __future__ import annotations

import asyncio
import os
import tempfile

import pytest

from koreaapi.pipeline.ingest import ingest_one
from koreaapi.sources.mock import MockSource
from koreaapi.sources.musicbrainz import MusicBrainzSource, parse_mb_artist


def _tmp_db() -> str:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(path)
    return path


def test_parse_mb_picks_korean_act_and_ko_alias():
    raw = {"artists": [
        {"id": "kr", "name": "BTS", "sort-name": "BTS", "country": "KR", "score": 100,
         "aliases": [{"name": "방탄소년단", "locale": "ko"}, {"name": "Bangtan Boys", "locale": "en"}]},
        {"id": "us", "name": "BTS", "country": "US", "aliases": []},  # a same-name foreign act
    ]}
    p = parse_mb_artist(raw, "BTS")
    assert p["name_en_official"] == "BTS" and p["name_ko"] == "방탄소년단"  # KR act + ko alias
    assert p["mbid"] == "kr" and p["name_en_source"] == "official"


def test_parse_mb_rejects_same_name_drift():
    # search returns only an unrelated act -> no hit matches the expected name -> raise (miss, not wrong)
    raw = {"artists": [{"id": "x", "name": "Some Other Band", "country": "US", "aliases": []}]}
    with pytest.raises(ValueError, match="identity mismatch"):
        parse_mb_artist(raw, "BTS")


def test_mb_self_filters_to_artists():
    # for a non-artist vertical it raises immediately (no network) -> ingest drops it gracefully
    with pytest.raises(ValueError, match="artists only"):
        asyncio.run(MusicBrainzSource().fetch("drama:squidgame", "facts"))


def test_three_agreeing_sources_set_triple_verified():
    p = {"name_ko": "방탄소년단", "name_en_official": "BTS", "name_en_source": "official", "summary_en": "x"}
    rec = asyncio.run(ingest_one("facts", "artist:bts",
        [MockSource("Wikidata", p), MockSource("Wikipedia", p), MockSource("MusicBrainz", p)],
        db_path=_tmp_db()))
    assert rec.provenance.agreeing_sources == 3        # all three agreed -> triple-verified tier
    assert rec.provenance.confidence == "high"


def test_third_source_rescues_a_failed_wikipedia_crosscheck():
    # Wikipedia resolved to the WRONG entity; Wikidata + MusicBrainz still agree -> >=2 agreeing,
    # so the record CLEARS the single-source 0.7 cap (which a WD-only record would have hit).
    wd = {"name_ko": "방탄소년단", "name_en_official": "BTS", "name_en_source": "official", "summary_en": "a"}
    wp = {"name_ko": "에스파", "name_en_official": "aespa", "name_en_source": "official", "summary_en": "b"}
    mb = {"name_ko": "방탄소년단", "name_en_official": "BTS", "name_en_source": "official", "summary_en": "c"}
    rec = asyncio.run(ingest_one("facts", "artist:bts",
        [MockSource("WD", wd), MockSource("WP", wp), MockSource("MB", mb)], db_path=_tmp_db()))
    assert rec.provenance.agreeing_sources == 2        # WD + MB
    assert rec.provenance.skill_score >= 0.8 and rec.provenance.confidence == "high"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
