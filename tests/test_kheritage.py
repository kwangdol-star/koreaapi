"""KHS / 국가유산청 (Korea Heritage Service, formerly 문화재청) source — the official Korean registry of
national heritage (historic sites, temples, palaces), an independent government source for the heritage/
temple/place verticals. Ships DORMANT (key-gated, no KHERITAGE_API_KEY on the live build), so it never
touches current ingest; the parse + identity guard are pure and offline-tested here. The endpoint moved
to 국가유산청 (khs.go.kr) in 2024 — KHERITAGE_URL is env-overridable; verify the field shape on activation."""

from __future__ import annotations

import asyncio

import pytest

from koreaapi.sources.kheritage import KHeritageSource, parse_kheritage

_XML = ("<result><item><ccbaAsno>0001</ccbaAsno><ccbaMnm1>경복궁</ccbaMnm1>"
        "<ccbaCtcdNm>서울특별시</ccbaCtcdNm><ccmaName>사적</ccmaName></item>"
        "<item><ccbaMnm1>다른 유산</ccbaMnm1></item></result>")


def test_parse_kheritage_matches_and_carries_official_facts():
    out = parse_kheritage(_XML, "경복궁")
    assert out["name_ko"] == "경복궁" and out["heritage_id"] == "0001"
    assert out["name_en_official"] is None                          # KHS is Korean-only (adds a source + authority)
    assert out["attrs"]["Region"] == "서울특별시" and out["attrs"]["Designation"] == "사적"
    assert "Korea Heritage Service" in out["summary_en"] and "국가유산" in out["summary_ko"]


def test_parse_kheritage_no_match_raises_a_miss_not_a_wrong_record():
    with pytest.raises(ValueError, match="no heritage item matches"):
        parse_kheritage("<result><item><ccbaMnm1>엉뚱한 곳</ccbaMnm1></item></result>", "경복궁")
    with pytest.raises(ValueError, match="unparseable XML"):
        parse_kheritage("not xml", "경복궁")


def test_kheritage_source_is_scoped_and_dormant(monkeypatch):
    monkeypatch.delenv("KHERITAGE_API_KEY", raising=False)
    src = KHeritageSource()
    with pytest.raises(ValueError, match="heritage"):               # self-scoped: drops non-heritage entities
        asyncio.run(src.fetch("artist:bts", "facts"))
    with pytest.raises(ValueError, match="no KHS Korean name"):     # a scoped entity without a mapped name -> skip
        asyncio.run(src.fetch("temple:unmapped", "facts"))
    with pytest.raises(ValueError, match="KHERITAGE_API_KEY not set"):  # mapped, but inert until a key is added
        asyncio.run(src.fetch("place:gyeongbokgung", "facts"))


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
