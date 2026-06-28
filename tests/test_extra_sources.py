"""Two more independent 3rd sources, each self-scoped to its verticals:
- Nominatim/OSM (places): separate DB, returns name:ko + name:en -> works with bilingual cross-verify.
- TMDB (drama/film/animation): carries the Korean original_title; key-gated (inert without TMDB_API_KEY).
Parse + identity guards are pure/offline; live fetch runs on the open network."""

from __future__ import annotations

import asyncio
import os

import pytest

from koreaapi.sources.nominatim import NominatimSource, parse_nominatim
from koreaapi.sources.tmdb import TMDBSource, parse_tmdb
from koreaapi.sources.wikidata import _name_match


def test_name_match_rejects_loose_substrings():
    # QA regression: the bilingual-guard-less sources use _name_match — exact, or long-contain only.
    assert _name_match("hanriver", {"hanriver"})                 # exact
    assert _name_match("gyeongbokgung", {"gyeongbokgungpalace"})  # expected ⊂ candidate (long) OK
    assert not _name_match("han", {"hanriver"})    # candidate ⊃ expected but expected too short -> NO
    assert not _name_match("iu", {"iusportsclub"})  # short want, not exact -> NO (was the loose bug)
    assert _name_match("iu", {"iu"})               # exact short still OK
    assert not _name_match("", {"anything"})        # empty expected -> never matches


def test_nominatim_parses_bilingual_place():
    res = [{"osm_id": 123, "display_name": "Gyeongbokgung, Jongno-gu, Seoul",
            "lat": "37.57", "lon": "126.97",
            "namedetails": {"name": "경복궁", "name:ko": "경복궁", "name:en": "Gyeongbokgung"}}]
    p = parse_nominatim(res, "Gyeongbokgung")
    assert p["name_en_official"] == "Gyeongbokgung" and p["name_ko"] == "경복궁"  # ko from name:ko
    assert p["osm_id"] == 123


def test_nominatim_rejects_drift_and_self_filters():
    res = [{"osm_id": 1, "display_name": "Somewhere Else", "namedetails": {"name": "Somewhere Else"}}]
    with pytest.raises(ValueError, match="identity mismatch"):
        parse_nominatim(res, "Gyeongbokgung")
    with pytest.raises(ValueError, match="places only"):
        asyncio.run(NominatimSource().fetch("artist:bts", "facts"))


def test_tmdb_prefers_korean_original_title():
    raw = {"results": [
        {"id": 1, "media_type": "tv", "name": "Squid Game",
         "original_name": "오징어 게임", "original_language": "ko"},
        {"id": 2, "name": "Squid Game", "original_language": "en"},  # a same-name non-Korean show
    ]}
    p = parse_tmdb(raw, "Squid Game")
    assert p["name_en_official"] == "Squid Game" and p["name_ko"] == "오징어 게임"  # ko original
    assert p["tmdb_id"] == 1


def test_tmdb_rejects_drift_self_filters_and_is_key_gated():
    with pytest.raises(ValueError, match="identity mismatch"):
        parse_tmdb({"results": [{"id": 9, "title": "Some Other Movie", "original_language": "en"}]},
                   "Squid Game")
    with pytest.raises(ValueError, match="drama/film/animation only"):
        asyncio.run(TMDBSource().fetch("artist:bts", "facts"))
    # video vertical but no key -> inert (graceful raise, dropped by ingest)
    os.environ.pop("TMDB_API_KEY", None)
    with pytest.raises(ValueError, match="not set"):
        asyncio.run(TMDBSource().fetch("drama:squidgame", "facts"))


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
