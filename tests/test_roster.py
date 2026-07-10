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


def test_every_roster_artist_has_an_agency_hint():
    # Don't add an artist without its 소속사 hint. The hint lives in AGENCY_HINTS (distinctive acts)
    # OR in wikidata._CURATED's `agency` field (collision-prone acts pinned bilingually) — fetch()
    # reads `_CURATED.agency or AGENCY_HINTS`, so an artist is covered if it's in either.
    from koreaapi.roster import AGENCY_HINTS
    from koreaapi.sources.wikidata import _CURATED
    curated_with_agency = {eid for eid, m in _CURATED.items() if m.get("agency")}
    assert set(ARTISTS) <= (set(AGENCY_HINTS) | curated_with_agency)


def test_strict_ko_guard_rejects_same_en_label_impostor(monkeypatch):
    # 'TREASURE' the group shares its English name with 보물 the concept. Search drifts to the
    # concept (en 'Treasure', ko '보물'); the en overlaps so the old guard would pass it. The strict
    # KO guard rejects it because the Korean label (보물) contradicts the pinned ko (트레저) -> miss,
    # never a wrong record (the Korean name would have been stored as 보물).
    monkeypatch.setattr(WikidataSource, "_http_get", _fake_http_get("Q-concept", "Treasure", "보물"))
    with pytest.raises(ValueError, match="ko identity mismatch"):
        asyncio.run(WikidataSource().fetch("artist:treasure", "facts"))


def test_strict_ko_guard_accepts_the_real_collision_act(monkeypatch):
    # The real TREASURE (ko 트레저) passes — search collision is rejected, the true act is kept.
    monkeypatch.setattr(WikidataSource, "_http_get", _fake_http_get("Q-treasure", "Treasure", "트레저"))
    res = asyncio.run(WikidataSource().fetch("artist:treasure", "facts"))
    assert res["payload"]["name_ko"] == "트레저"
    assert res["payload"]["name_en_official"] == "Treasure"


def test_strict_ko_guard_allows_latin_ko_label(monkeypatch):
    # Some acts carry a latin (English) Korean-language label on Wikidata (e.g. NCT). A ko label that
    # equals the expected EN name must NOT be rejected by the strict KO guard (it's not an impostor).
    monkeypatch.setattr(WikidataSource, "_http_get", _fake_http_get("Q-nct", "NCT", "NCT"))
    res = asyncio.run(WikidataSource().fetch("artist:nct", "facts"))
    assert res["payload"]["name_en_official"] == "NCT"


def test_roster_agency_hint_applies_to_noncurated(monkeypatch):
    # A roster (non-curated) artist also gets the agency hint: pick JYP, not the foreign label first.
    def http_get(self, url: str) -> dict:
        if "wbsearchentities" in url:
            return {"search": [{"id": "QITZY"}]}
        if "QFOREIGN" in url:
            return {"entities": {"QFOREIGN": {"labels": {"en": {"value": "Republic Records"}}}}}
        if "QJYP" in url:
            return {"entities": {"QJYP": {"labels": {"en": {"value": "JYP Entertainment"}, "ko": {"value": "JYP엔터테인먼트"}}}}}
        return {"entities": {"QITZY": {"id": "QITZY", "labels": {"en": {"value": "ITZY"}},
                "claims": {"P264": [
                    {"mainsnak": {"snaktype": "value", "datavalue": {"value": {"id": "QFOREIGN"}}}},
                    {"mainsnak": {"snaktype": "value", "datavalue": {"value": {"id": "QJYP"}}}},
                ]}}}}
    monkeypatch.setattr(WikidataSource, "_http_get", http_get)
    res = asyncio.run(WikidataSource().fetch("artist:itzy", "facts"))
    assert res["payload"]["agency_en"] == "JYP Entertainment"  # roster hint disambiguated


def test_every_name_has_a_wikipedia_title():
    # The Wikipedia title is what makes cross-verification reliable (the second independent source).
    # An entity in NAMES without a _TITLES entry would silently degrade to single-source — block that.
    from koreaapi.roster import NAMES
    from koreaapi.sources.wikipedia import _TITLES
    assert set(NAMES) <= set(_TITLES)


def test_curated_anchors_are_bilingual():
    # Every curated anchor must carry both ko + en so the strict identity guard can run (a qid-less
    # anchor relies entirely on the bilingual guard; a wrong one then fails SAFE to a miss).
    from koreaapi.sources.wikidata import _CURATED
    assert all(m.get("ko") and m.get("en") for m in _CURATED.values())


def test_roster_breadth():
    # Guard the asset's breadth (25 verticals, 400+ entities) so a bad edit that drops rows is caught.
    from koreaapi.roster import (ACTORS, AIRPORTS, ANIMATIONS, ARTISTS, AWARDS, BOOKS, BRANDS, CLASSICS,
                                 COMPANIES, CONCEPTS, DRAMAS, FASHION, FESTIVALS, FILMS, FOLKLORE, FOODS,
                                 GAMES, HERITAGE, HISTORY, HOLIDAYS, HOTSPRINGS, ISLANDS, LIQUORS, MEDICAL,
                                 MUSEUMS, NAMES, PARKS, PLACES, REGION, SHOWS, SKIRESORTS, SONGS, SPORTS,
                                 TEMPLES, THEATERS, THEMEPARKS, UNIVERSITIES, VENUES, WEBTOONS)
    assert len(ARTISTS) >= 50 and len(DRAMAS) >= 18 and len(FILMS) >= 15
    assert len(WEBTOONS) >= 5 and len(PLACES) >= 10 and len(FOODS) >= 12
    assert len(COMPANIES) >= 8 and len(BRANDS) >= 8 and len(BOOKS) >= 6 and len(HISTORY) >= 8
    assert len(HERITAGE) >= 8 and len(FOLKLORE) >= 8
    assert len(MEDICAL) >= 6 and len(REGION) >= 15 and len(GAMES) >= 8
    assert len(SHOWS) >= 8 and len(ANIMATIONS) >= 6 and len(UNIVERSITIES) >= 8 and len(CLASSICS) >= 10
    assert len(FASHION) >= 6 and len(FESTIVALS) >= 6 and len(AWARDS) >= 12 and len(HOLIDAYS) >= 12
    assert len(LIQUORS) >= 12 and len(PARKS) >= 20 and len(MUSEUMS) >= 12 and len(TEMPLES) >= 12
    assert len(VENUES) >= 10 and len(AIRPORTS) >= 8 and len(THEATERS) >= 8 and len(THEMEPARKS) >= 6
    assert len(SKIRESORTS) >= 6 and len(ISLANDS) >= 5 and len(HOTSPRINGS) >= 5
    assert len(SPORTS) >= 12 and len(ACTORS) >= 15 and len(SONGS) >= 8 and len(CONCEPTS) >= 12
    assert len(NAMES) >= 400
    assert len(NAMES) == sum(map(len, (ARTISTS, DRAMAS, FILMS, WEBTOONS, PLACES, FOODS, COMPANIES,
                                       BRANDS, BOOKS, HISTORY, HERITAGE, FOLKLORE, MEDICAL, REGION,
                                       GAMES, SHOWS, ANIMATIONS, UNIVERSITIES, CLASSICS, FASHION,
                                       FESTIVALS, AWARDS, HOLIDAYS, LIQUORS, PARKS, MUSEUMS, TEMPLES,
                                       VENUES, AIRPORTS, THEATERS, THEMEPARKS, SKIRESORTS, ISLANDS,
                                       HOTSPRINGS, SPORTS, ACTORS, SONGS, CONCEPTS)))


def test_food_editorial_tags_cover_every_dish():
    # every food carries a spice + dietary editorial tag (so a new dish can't silently miss them)
    from koreaapi.roster import FOOD_SPICE, FOOD_VEG, FOODS
    assert set(FOODS) <= set(FOOD_SPICE), set(FOODS) - set(FOOD_SPICE)
    assert set(FOODS) <= set(FOOD_VEG), set(FOODS) - set(FOOD_VEG)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
