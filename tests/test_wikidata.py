"""Offline test of the Wikidata adapter's PARSE step (no network).

Live fetch() needs egress (blocked in this sandbox); on deploy it works. Here we
verify the parser turns a saved Wikidata response into a correct bilingual payload.
"""

from __future__ import annotations

import json
import pathlib

from koreaapi.sources.wikidata import (
    _claim_qids,
    _claim_time,
    build_labelmates_search,
    parse_entity,
    parse_label,
    parse_member_names,
    parse_search,
)

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "wikidata_bts.json"
SEARCH_FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "wikidata_search_bts.json"
AGENCY_FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "wikidata_bts_agency.json"
LABEL_FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "wikidata_label_bighit.json"
LABELMATES_FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "wikidata_labelmates.json"
FULL_FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "wikidata_bts_full.json"
MEMBERS_FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "wikidata_members.json"


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


def test_parse_entity_extracts_debut_active_and_member_qids():
    raw = json.loads(FULL_FIXTURE.read_text(encoding="utf-8"))
    p = parse_entity(raw, "artist:bts", "facts")
    assert p["debut"] == "2013-06-13"  # P571 inception, full date
    assert p["active"] == "active"  # no P576 dissolution
    assert p["member_qids"] == ["Q494528", "Q494529"]  # P527, resolved to names in fetch()
    assert p["agency_qids"] == ["Q50602100"]


def test_claim_time_year_only_and_disbanded():
    year_only = {"claims": {"P571": [{"mainsnak": {"snaktype": "value",
                "datavalue": {"value": {"time": "+2013-00-00T00:00:00Z"}}}}]}}
    assert _claim_time(year_only, "P571") == "2013"  # month/day 00 -> year only
    assert _claim_time({"claims": {}}, "P576") is None


def test_parse_member_names_resolves_in_order_and_drops_missing():
    raw = json.loads(MEMBERS_FIXTURE.read_text(encoding="utf-8"))
    assert parse_member_names(raw, ["Q494528", "Q494529"]) == ["RM", "Jin"]
    assert parse_member_names(raw, ["Q494528", "Q_missing"]) == ["RM"]  # unresolved dropped


def test_build_labelmates_search_targets_the_label():
    # discovery/sweep moved off WDQS SPARQL (which 429s on the runner) to CirrusSearch on the API
    q = build_labelmates_search("Q50602100")
    assert "haswbstatement:P264=Q50602100" in q   # artists ON this record label
    assert "P31=Q215380" in q and "P31=Q5" in q   # group / human classes (OR-ed)


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
