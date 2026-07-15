"""abstract_ko — real Korean prose for the /ko/ pages (Naver's crawl surface). The Wikipedia source
already resolves the Korean article title (langlink); a second, best-effort fetch pulls the KOREAN
lead. It rides as supplementary data (never enters name cross-verification), renders as the /ko/
설명 + the grounded '무엇인가요?' FAQ answer + the Korean node's JSON-LD description. A missing ko
article or a failed second call ships the payload without it — never fails the source."""

from __future__ import annotations

import asyncio
import tempfile

from koreaapi import admin
from koreaapi.pipeline.ingest import ingest_one
from koreaapi.sources.mock import MockSource
from koreaapi.sources.wikipedia import WikipediaSource, parse_ko_extract

_ABS_KO = "경복궁은 조선 왕조의 법궁이다. 1395년에 창건되었다."


def test_parse_ko_extract():
    assert parse_ko_extract({"query": {"pages": [{"extract": " 경복궁은  조선의 법궁이다. "}]}}) \
        == "경복궁은 조선의 법궁이다."
    assert parse_ko_extract({"query": {"pages": [{"missing": True}]}}) is None
    assert parse_ko_extract({}) is None


def test_fetch_pulls_the_korean_lead_best_effort(monkeypatch):
    src = WikipediaSource()

    def fake_get(url):
        if "ko.wikipedia.org" in url:
            return {"query": {"pages": [{"extract": _ABS_KO}]}}
        return {"query": {"pages": [{"title": "Gyeongbokgung",
                                     "langlinks": [{"lang": "ko", "title": "경복궁"}],
                                     "extract": "Gyeongbokgung is a royal palace."}]}}

    monkeypatch.setattr(src, "_http_get", fake_get)
    out = asyncio.run(src.fetch("place:gyeongbokgung", "facts"))
    p = out["payload"]
    assert p["abstract_ko"] == _ABS_KO and p["abstract_en"].startswith("Gyeongbokgung is")
    assert "_ko_title" not in p                                   # internal key popped, never stored


def test_fetch_survives_a_failed_korean_call(monkeypatch):
    src = WikipediaSource()

    def fake_get(url):
        if "ko.wikipedia.org" in url:
            raise OSError("ko wiki down")
        return {"query": {"pages": [{"title": "Gyeongbokgung",
                                     "langlinks": [{"lang": "ko", "title": "경복궁"}]}]}}

    monkeypatch.setattr(src, "_http_get", fake_get)
    p = asyncio.run(src.fetch("place:gyeongbokgung", "facts"))["payload"]
    assert "abstract_ko" not in p and p["name_ko"] == "경복궁"     # supplementary: fetch still succeeds


def test_ko_page_faq_and_jsonld_lead_with_the_korean_abstract(tmp_path):
    db = tempfile.mktemp(suffix=".db")
    payload = {"name_ko": "경복궁", "name_en_official": "Gyeongbokgung", "name_en_source": "official",
               "agency_en": "Seoul", "abstract_en": "Gyeongbokgung is a royal palace in Seoul.",
               "abstract_ko": _ABS_KO}
    asyncio.run(ingest_one("facts", "place:gyeongbokgung",
                           [MockSource("Wikidata", payload), MockSource("Wikipedia", payload)], db_path=db))
    out_dir = str(tmp_path / "site")
    asyncio.run(admin.entity_pages(db_path=db, out_dir=out_dir))

    ko = (tmp_path / "site" / "ko" / "artist" / "gyeongbokgung.html").read_text(encoding="utf-8")
    assert "경복궁은 조선 왕조의 법궁이다" in ko                    # real Korean prose in 설명
    assert "한국어 위키백과" in ko                                  # attributed to the ko lead
    assert "영문 출처: Wikipedia" not in ko                        # no English-with-an-apology fallback
    # the grounded 무엇인가요? uses the FIRST SENTENCE of the Korean lead
    assert "무엇인가요?" in ko and "법궁이다. (한국어 위키백과 lead" in ko
    jsonld = ko.split('application/ld+json">', 1)[1].split("</script>", 1)[0]
    assert "법궁" in jsonld                                        # the Korean node describes in Korean

    en = (tmp_path / "site" / "artist" / "gyeongbokgung.html").read_text(encoding="utf-8")
    assert "royal palace" in en                                    # the English page keeps the EN lead


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
