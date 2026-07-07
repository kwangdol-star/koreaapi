"""More independent 3rd sources, each self-scoped to its verticals:
- Nominatim/OSM (places): separate DB, returns name:ko + name:en -> works with bilingual cross-verify.
- TMDB (drama/film/animation): carries the Korean original_title; key-gated (inert without TMDB_API_KEY).
- KTO/TourAPI (places): the official government tourism authority; key-gated (inert without TOURAPI_KEY).
Parse + identity guards are pure/offline; live fetch runs on the open network."""

from __future__ import annotations

import asyncio
import os

import pytest

from koreaapi.sources.nominatim import NominatimSource, parse_nominatim
from koreaapi.sources.tmdb import TMDBSource, parse_tmdb
from koreaapi.sources.tourapi import TourAPISource, parse_tourapi
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


def _tourapi_raw(item):
    # TourAPI nests: response.body.items.item is a list for many, a bare dict for one result.
    return {"response": {"body": {"items": {"item": item}}}}


def test_tourapi_parses_official_listing():
    raw = _tourapi_raw([{"title": "Gyeongbokgung Palace", "contentid": "264337"}])
    p = parse_tourapi(raw, "Gyeongbokgung")  # expected ⊂ official title (long-contain) -> matches
    assert p["name_en_official"] == "Gyeongbokgung Palace" and p["tour_id"] == "264337"
    assert p["name_en_source"] == "official"  # KTO is a government authority


def test_tourapi_accepts_single_item_dict():
    # one result comes back as a bare dict (not a list) — _items must still find it
    raw = _tourapi_raw({"title": "Bukchon Hanok Village", "contentid": "264386"})
    p = parse_tourapi(raw, "Bukchon Hanok Village")
    assert p["tour_id"] == "264386"


def test_tourapi_rejects_drift_self_filters_and_is_key_gated():
    with pytest.raises(ValueError, match="no official listing"):
        parse_tourapi(_tourapi_raw([{"title": "Somewhere Else", "contentid": "1"}]), "Gyeongbokgung")
    with pytest.raises(ValueError, match="no official listing"):  # empty results ("" body)
        parse_tourapi({"response": {"body": {"items": ""}}}, "Gyeongbokgung")
    with pytest.raises(ValueError, match="places & festivals only"):
        asyncio.run(TourAPISource().fetch("artist:bts", "facts"))
    # place vertical but no key -> inert (graceful raise, dropped by ingest)
    os.environ.pop("TOURAPI_KEY", None)
    with pytest.raises(ValueError, match="not set"):
        asyncio.run(TourAPISource().fetch("place:gyeongbokgung", "facts"))


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))


def test_tourapi_official_attrs_ride_along():
    # KTO practical facts (address/tel/geo) become attrs that UNION with Wikidata attrs at ingest.
    raw = _tourapi_raw({"title": "Gyeongbokgung Palace", "contentid": "264337",
                        "addr1": "161, Sajik-ro, Jongno-gu, Seoul", "tel": "+82-2-3700-3900",
                        "mapx": "126.9769930325", "mapy": "37.5788222356"})
    p = parse_tourapi(raw, "Gyeongbokgung")
    assert p["attrs"]["Address"].startswith("161, Sajik-ro")
    assert p["attrs"]["Tel"].startswith("+82")
    assert p["attrs"]["Coordinates"] == "37.5788222356,126.9769930325"  # lat,lon
    # and a bare listing (no addr/tel/geo) carries NO attrs key at all
    assert "attrs" not in parse_tourapi(_tourapi_raw({"title": "Bukchon Hanok Village",
                                                      "contentid": "264386"}), "Bukchon Hanok Village")


def test_tourapi_covers_festivals_too():
    # Tier A-1: KTO's keyword search lists festivals as well — festival: passes the vertical gate
    # (and without a key fails on the KEY, proving the gate let it through). Other verticals drop.
    os.environ.pop("TOURAPI_KEY", None)
    with pytest.raises(ValueError, match="not set"):
        asyncio.run(TourAPISource().fetch("festival:boryeongmud", "facts"))
    with pytest.raises(ValueError, match="places"):
        asyncio.run(TourAPISource().fetch("artist:bts", "facts"))
