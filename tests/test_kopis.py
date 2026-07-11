"""KOPIS source (공연예술통합전산망) — the official Korean performing-arts VENUE registry, an independent
government source for the theater vertical. Ships DORMANT (key-gated, no KOPIS_API_KEY on the live build)
so it never touches current ingest; the parse + identity guard are pure and offline-tested here."""

from __future__ import annotations

import asyncio

import pytest

from koreaapi.sources.kopis import KopisSource, parse_kopis

_XML = ("<dbs><db><mt10id>FC000001</mt10id><fcltynm>예술의전당</fcltynm>"
        "<sidonm>서울특별시</sidonm><opende>1988</opende></db>"
        "<db><mt10id>FC000009</mt10id><fcltynm>다른 공연장</fcltynm></db></dbs>")


def test_parse_kopis_matches_and_carries_official_facts():
    out = parse_kopis(_XML, "예술의전당")
    assert out["name_ko"] == "예술의전당" and out["kopis_id"] == "FC000001"
    assert out["name_en_official"] is None                       # KOPIS is Korean-only (adds a source + authority)
    assert out["attrs"]["Opened"] == "1988" and out["attrs"]["Region"] == "서울특별시"
    assert "KOPIS" in out["summary_en"] and "공연시설" in out["summary_ko"]


def test_parse_kopis_no_match_raises_a_miss_not_a_wrong_record():
    with pytest.raises(ValueError, match="no venue matches"):
        parse_kopis("<dbs><db><fcltynm>엉뚱한 곳</fcltynm></db></dbs>", "예술의전당")
    with pytest.raises(ValueError, match="unparseable XML"):
        parse_kopis("not xml", "예술의전당")


def test_kopis_source_is_theater_scoped_and_dormant(monkeypatch):
    monkeypatch.delenv("KOPIS_API_KEY", raising=False)
    src = KopisSource()
    with pytest.raises(ValueError, match="theater:"):            # self-scoped: drops non-theater entities
        asyncio.run(src.fetch("place:gyeongbokgung", "facts"))
    with pytest.raises(ValueError, match="no KOPIS Korean name"):  # a theater without a mapped 시설명 -> skip
        asyncio.run(src.fetch("theater:unmapped", "facts"))
    with pytest.raises(ValueError, match="KOPIS_API_KEY not set"):  # mapped, but inert until a key is added
        asyncio.run(src.fetch("theater:sac", "facts"))


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
