"""Offline test of the Wikidata adapter's PARSE step (no network).

Live fetch() needs egress (blocked in this sandbox); on deploy it works. Here we
verify the parser turns a saved Wikidata response into a correct bilingual payload.
"""

from __future__ import annotations

import json
import pathlib

from koreaapi.sources.wikidata import parse_entity

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "wikidata_bts.json"


def test_parse_extracts_bilingual_official_name():
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload = parse_entity(raw, "artist:bts", "comeback")

    assert payload["name_ko"] == "방탄소년단"
    assert payload["name_en_official"] == "BTS"  # Wikidata label = canonical/official
    assert payload["name_en_source"] == "official"
    assert payload["name_en_confidence"] == "high"


if __name__ == "__main__":
    test_parse_extracts_bilingual_official_name()
    print("wikidata parse test passed")
