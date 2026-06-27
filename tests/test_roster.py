"""Offline test: uncurated roster artists resolve via live search + are identity-guarded.

Roster (non-curated) artists have NO hardcoded Q-id - the id is resolved live via
wbsearchentities on the open network (GitHub runners). Here the HTTP is monkeypatched. The
fetched name is checked against the roster's canonical name, so a wrong resolution is
rejected (graceful degradation), never ingested - the same guard that caught 'Arborka'.

Run:  PYTHONPATH=src python -m pytest tests/test_roster.py -q
"""

from __future__ import annotations

import asyncio

import pytest

from koreaapi.roster import ARTISTS
from koreaapi.sources.wikidata import WikidataSource, _QID


def _fake_http_get(entity_q: str, en: str, ko: str | None = None):
    """Return a search hit then a labels response, regardless of which URL is requested."""

    def http_get(self, url: str) -> dict:
        if "wbsearchentities" in url:
            return {"search": [{"id": entity_q}]}
        labels = {"en": {"language": "en", "value": en}}
        if ko:
            labels["ko"] = {"language": "ko", "value": ko}
        return {"entities": {entity_q: {"id": entity_q, "labels": labels}}}

    return http_get


def test_roster_has_extras_beyond_the_curated_qids():
    # the extras are roster-only (no hardcoded Q-id) -> resolved live
    assert "artist:blackpink" in ARTISTS and "artist:blackpink" not in _QID


def test_roster_artist_resolves_via_search_and_passes_guard(monkeypatch):
    monkeypatch.setattr(WikidataSource, "_http_get", _fake_http_get("Q24987224", "BLACKPINK", "블랙핑크"))
    res = asyncio.run(WikidataSource().fetch("artist:blackpink", "facts"))
    assert res["payload"]["name_en_official"] == "BLACKPINK"
    assert res["payload"]["name_ko"] == "블랙핑크"
    assert res["citation"].startswith("Wikidata Q24987224")  # id came from live search


def test_roster_artist_wrong_resolution_is_rejected(monkeypatch):
    # search resolves to an entity whose name is NOT blackpink -> identity guard rejects it
    monkeypatch.setattr(WikidataSource, "_http_get", _fake_http_get("Q999", "Some Other Thing"))
    with pytest.raises(ValueError, match="identity mismatch"):
        asyncio.run(WikidataSource().fetch("artist:blackpink", "facts"))


def test_curated_agency_hint_picks_the_real_label(monkeypatch):
    # BTS's Wikidata P264 lists a foreign distribution label BEFORE Big Hit; the curated agency
    # hint must pick Big Hit (the 소속사), not the first value. The value still comes from Wikidata.
    def http_get(self, url: str) -> dict:
        if "QAVEX" in url:
            return {"entities": {"QAVEX": {"labels": {"en": {"value": "Avex Trax"}, "ko": {"value": "에이벡스 트랙스"}}}}}
        if "QBIGHIT" in url:
            return {"entities": {"QBIGHIT": {"labels": {"en": {"value": "Big Hit Music"}, "ko": {"value": "빅히트 뮤직"}}}}}
        # the BTS entity itself: two record labels, the wrong (foreign) one first
        return {"entities": {"Q13580495": {"id": "Q13580495",
                "labels": {"ko": {"value": "방탄소년단"}, "en": {"value": "BTS"}},
                "claims": {"P264": [
                    {"mainsnak": {"snaktype": "value", "datavalue": {"value": {"id": "QAVEX"}}}},
                    {"mainsnak": {"snaktype": "value", "datavalue": {"value": {"id": "QBIGHIT"}}}},
                ]}}}}
    monkeypatch.setattr(WikidataSource, "_http_get", http_get)
    res = asyncio.run(WikidataSource().fetch("artist:bts", "facts"))
    assert res["payload"]["agency_en"] == "Big Hit Music"  # hint disambiguated, not the first value
    assert res["payload"]["agency_source"] == "Wikidata QBIGHIT"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
