"""Offline test of the Wikidata adapter's PARSE step (no network).

Live fetch() needs egress (blocked in this sandbox); on deploy it works. Here we
verify the parser turns a saved Wikidata response into a correct bilingual payload.
"""

from __future__ import annotations

import json
import pathlib

from koreaapi.sources.wikidata import (
    _claim_qids,
    build_labelmates_query,
    parse_entity,
    parse_label,
    parse_labelmates,
    parse_search,
)

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "wikidata_bts.json"
SEARCH_FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "wikidata_search_bts.json"
AGENCY_FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "wikidata_bts_agency.json"
LABEL_FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "wikidata_label_bighit.json"
LABELMATES_FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "wikidata_labelmates.json"


def test_parse_extracts_bilingual_official_name():
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload = parse_entity(raw, "artist:bts", "comeback")

    assert payload["name_ko"] == "방탄소년단"
    assert payload["name_en_official"] == "BTS"  # Wikidata label = canonical/official
    assert payload["name_en_source"] == "official"
    assert payload["name_en_confidence"] == "high"


def test_parse_search_picks_top_hit():
    raw = json.loads(SEARCH_FIXTURE.read_text(encoding="utf-8"))
    assert parse_search(raw) == "Q13580495"  # top wbsearchentities hit


def test_parse_search_no_hit_returns_none():
    assert parse_search({"search": []}) is None


def test_parse_entity_extracts_agency_qids():
    raw = json.loads(AGENCY_FIXTURE.read_text(encoding="utf-8"))
    payload = parse_entity(raw, "artist:bts", "facts")
    assert payload["agency_qids"] == ["Q50602100"]  # P264 (record label) -> resolved in fetch()


def test_parse_entity_without_claims_has_no_agency():
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))  # no claims in this fixture
    assert parse_entity(raw, "artist:bts", "facts")["agency_qids"] == []


def test_parse_label_extracts_bilingual_name():
    raw = json.loads(LABEL_FIXTURE.read_text(encoding="utf-8"))
    assert parse_label(raw) == {"ko": "빅히트 뮤직", "en": "Big Hit Music"}


def test_parse_labelmates_dedups_and_slugs():
    raw = json.loads(LABELMATES_FIXTURE.read_text(encoding="utf-8"))
    mates = parse_labelmates(raw)
    assert [m["slug"] for m in mates] == ["redvelvet", "nct"]  # dup dropped, blank-uri dropped
    assert mates[0] == {"qid": "Q484939", "en": "Red Velvet", "ko": "레드벨벳", "slug": "redvelvet"}
    assert mates[1]["ko"] is None  # ko is optional


def test_build_labelmates_query_targets_the_label():
    q = build_labelmates_query("Q50602100", limit=5)
    assert "wdt:P264 wd:Q50602100" in q and "LIMIT 5" in q


def test_claim_qids_prefers_preferred_rank_and_skips_novalue():
    item = {
        "claims": {
            "P264": [
                {"mainsnak": {"snaktype": "value", "datavalue": {"value": {"id": "Q2"}}}, "rank": "normal"},
                {"mainsnak": {"snaktype": "value", "datavalue": {"value": {"id": "Q1"}}}, "rank": "preferred"},
                {"mainsnak": {"snaktype": "novalue"}, "rank": "normal"},
            ]
        }
    }
    assert _claim_qids(item, "P264") == ["Q1", "Q2"]  # preferred first; novalue dropped


if __name__ == "__main__":
    test_parse_extracts_bilingual_official_name()
    test_parse_search_picks_top_hit()
    test_parse_search_no_hit_returns_none()
    print("wikidata parse tests passed")
