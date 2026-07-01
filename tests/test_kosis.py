"""KOSIS (국가통계포털) region-population source — offline. The identity guard is the whole point:
administrative codes DRIFT (강원 42→51, 전북 45→52, 제주 49→50), so a row only counts when the
region NAMES itself as expected AND the item is a population item. Wrong code -> miss, never wrong."""

from __future__ import annotations

import asyncio

import pytest

from koreaapi.sources.kosis import REGIONS, KOSISSource, parse_kosis


def _row(name="서울특별시", itm="총인구수", dt="9386034", prd="202605") -> dict:
    return {"C1_NM": name, "ITM_NM": itm, "DT": dt, "PRD_DE": prd, "TBL_NM": "주민등록인구현황"}


def test_parse_population_row_with_guard():
    out = parse_kosis([_row()], "region:seoul", ("서울",))
    assert out["attrs"]["Population"] == "9,386,034 (202605)"
    assert out["name_ko"] == "서울특별시" and out["name_en_official"] == "Seoul"
    assert "9,386,034" in out["summary_ko"] and "주민등록인구" in out["summary_ko"]


def test_guard_rejects_wrong_region_name():
    # a drifted code returns some OTHER region -> refuse (miss, never a wrong number)
    with pytest.raises(ValueError):
        parse_kosis([_row(name="부산광역시")], "region:seoul", ("서울",))


def test_guard_rejects_non_population_item():
    with pytest.raises(ValueError):
        parse_kosis([_row(itm="세대수")], "region:seoul", ("서울",))


def test_renamed_provinces_accept_both_prefixes():
    out = parse_kosis([_row(name="전북특별자치도", dt="1754757")], "region:northjeolla",
                      REGIONS["region:northjeolla"][1])
    assert out["attrs"]["Population"].startswith("1,754,757")


def test_source_is_inert_without_key_and_scoped_to_regions(monkeypatch):
    monkeypatch.delenv("KOSIS_API_KEY", raising=False)
    src = KOSISSource()
    with pytest.raises(ValueError, match="KOSIS_API_KEY"):
        asyncio.run(src.fetch("region:seoul", "facts"))
    with pytest.raises(ValueError, match="regions only"):
        asyncio.run(src.fetch("artist:bts", "facts"))


def test_every_region_entity_has_a_code():
    from koreaapi.roster import REGION
    assert set(REGION) == set(REGIONS)  # every region: entity is fetchable (and none dangles)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
