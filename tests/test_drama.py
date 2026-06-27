"""K-drama vertical: the SAME verified engine, namespace-switched.

A `drama:` entity is cross-verified by name like an artist, but the source props switch
(air date P577 instead of debut P571; CAST P161 instead of members P527; no 소속사) and the
JSON-LD type becomes TVSeries (with actor) instead of MusicGroup. Pure/offline — no network.
"""

from __future__ import annotations

from datetime import datetime, timezone

from koreaapi import admin
from koreaapi.models import Name, Provenance, Record
from koreaapi.sources.wikidata import parse_entity


def test_drama_parse_uses_air_date_and_cast_not_music_props():
    raw = {"entities": {"Q1": {"labels": {"ko": {"value": "오징어 게임"}, "en": {"value": "Squid Game"}},
            "claims": {
                "P577": [{"mainsnak": {"snaktype": "value",
                    "datavalue": {"value": {"time": "+2021-09-17T00:00:00Z"}}}}],
                "P161": [{"mainsnak": {"snaktype": "value", "datavalue": {"value": {"id": "QACTOR"}}}}],  # cast
                # music props must be IGNORED for a drama:
                "P264": [{"mainsnak": {"snaktype": "value", "datavalue": {"value": {"id": "QLABEL"}}}}],
                "P527": [{"mainsnak": {"snaktype": "value", "datavalue": {"value": {"id": "QMEMBER"}}}}],
            }}}}
    p = parse_entity(raw, "drama:squidgame", "facts")
    assert p["debut"] == "2021-09-17"        # P577 first air date
    assert p["agency_qids"] == []             # no 소속사 (P264 ignored)
    assert p["member_qids"] == ["QACTOR"]     # CAST from P161, NOT P527 members


def test_drama_jsonld_node_is_tvseries_with_cast():
    now = datetime.now(timezone.utc)
    rec = Record(
        entity_id="drama:squidgame", kind="facts",
        name=Name(ko="오징어 게임", en_official="Squid Game"), snapshot_at=now,
        summary_en="Squid Game — verified Korean drama (TV series). Aired 2021. 3 verified cast.",
        data={"debut": "2021", "members": ["Lee Jung-jae", "Park Hae-soo", "Wi Ha-joon"]},
        provenance=Provenance(sources=["Wikidata Q1", "Wikipedia Squid Game"], fetched_at=now,
                              skill_score=1.0, confidence="high"),
    )
    node = admin._entity_node(rec)
    assert node["@type"] == "TVSeries"
    assert node.get("datePublished") == "2021"
    assert [a["name"] for a in node.get("actor", [])] == ["Lee Jung-jae", "Park Hae-soo", "Wi Ha-joon"]
    assert "recordLabel" not in node and "member" not in node  # not an artist


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
