"""ko.wikipedia as the cross-check for Korean-local entities. An entity with NO English article
(유성온천, 향토주, 지역 공연장 …) previously lost the Wikipedia source forever -> permanently capped at
single-source 0.7. Now the EN miss falls back to the KOREAN article (SEARCH_KO / the threaded stored
한국어명): Wikidata + ko.wikipedia agreeing on the 한국어명 IS two independent sources. Offline."""

from __future__ import annotations

import asyncio
import tempfile

import pytest

from koreaapi.pipeline.ingest import ingest_one
from koreaapi.sources.mock import MockSource
from koreaapi.sources.wikipedia import WikipediaSource, parse_ko_page

_KO_RAW = {"query": {"pages": [{"title": "유성온천",
                                "langlinks": [],
                                "extract": "유성온천은 대전 유성구에 있는 온천이다."}]}}
_EN_MISS = {"query": {"pages": [{"missing": True}]}}


def test_parse_ko_page_korean_only_article():
    p = parse_ko_page(_KO_RAW, "facts")
    assert p["name_ko"] == "유성온천" and p["name_en_official"] is None
    assert p["abstract_ko"].startswith("유성온천은")
    assert "한국어 위키백과" in p["summary_ko"]
    with pytest.raises(ValueError, match="missing"):
        parse_ko_page(_EN_MISS, "facts")


def test_fetch_falls_back_to_ko_wikipedia_on_en_miss(monkeypatch):
    src = WikipediaSource()          # hotspring:yuseong rides roster.SEARCH_KO — no threading needed

    def fake_get(url):
        if "ko.wikipedia.org" in url:
            return _KO_RAW
        return _EN_MISS              # no English article

    monkeypatch.setattr(src, "_http_get", fake_get)
    out = asyncio.run(src.fetch("hotspring:yuseong", "facts"))
    assert out["payload"]["name_ko"] == "유성온천"
    assert out["citation"].startswith("Wikipedia(ko) 유성온천")   # honestly attributed to the ko article


def test_fetch_without_a_korean_term_still_raises(monkeypatch):
    src = WikipediaSource()
    monkeypatch.setattr(src, "_http_get", lambda url: _EN_MISS)
    with pytest.raises(ValueError):                               # no ko term -> the original miss
        asyncio.run(src.fetch("artist:noterm", "facts"))


def test_threaded_ko_alias_enables_the_fallback(monkeypatch):
    # discover/refresh thread the stored 한국어명 through ko_aliases — entities beyond SEARCH_KO heal too.
    src = WikipediaSource(ko_aliases={"beach:x": "임의해수욕장"})
    calls = []

    def fake_get(url):
        calls.append(url)
        if "ko.wikipedia.org" in url:
            return {"query": {"pages": [{"title": "임의해수욕장", "langlinks": [], "extract": "설명."}]}}
        return _EN_MISS

    monkeypatch.setattr(src, "_http_get", fake_get)
    out = asyncio.run(src.fetch("beach:x", "facts"))
    assert out["payload"]["name_ko"] == "임의해수욕장"
    assert any("ko.wikipedia.org" in u for u in calls)


def test_ko_only_entity_becomes_cross_verified():
    # The point of it all: Wikidata + Wikipedia(ko) agreeing on the 한국어명 = 2 independent sources ->
    # the record clears the single-source cap instead of sitting at 0.7 forever.
    db = tempfile.mktemp(suffix=".db")
    wd = {"name_ko": "유성온천", "name_en_official": None, "summary_en": "x"}
    wp = {"name_ko": "유성온천", "name_en_official": None, "summary_en": "x",
          "abstract_ko": "유성온천은 대전 유성구에 있는 온천이다."}
    rec = asyncio.run(ingest_one("facts", "hotspring:yuseong",
                                 [MockSource("Wikidata", wd), MockSource("Wikipedia", wp)], db_path=db))
    assert rec.provenance.agreeing_sources == 2                   # cross-verified on the Korean name
    assert rec.provenance.skill_score > 0.7                       # the single-source cap is cleared
    assert rec.data["abstract_ko"].startswith("유성온천은")        # the Korean lead rides along


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
