"""K-drama & K-film verticals: the SAME verified engine, namespace-switched.

A `drama:`/`film:` entity is cross-verified by name like an artist, but the source props switch
(air/release date P577 instead of debut P571; CAST P161 instead of members P527; no 소속사) and the
JSON-LD type becomes TVSeries / Movie (with actor) instead of MusicGroup. Pure/offline — no network.
"""

from __future__ import annotations

from datetime import datetime, timezone

from koreaapi import admin
from koreaapi.models import Name, Provenance, Record
from koreaapi.sources.wikidata import parse_entity


def _video_raw(ko: str, en: str):
    return {"entities": {"Q1": {"labels": {"ko": {"value": ko}, "en": {"value": en}},
            "claims": {
                "P577": [{"mainsnak": {"snaktype": "value",
                    "datavalue": {"value": {"time": "+2021-09-17T00:00:00Z"}}}}],
                "P161": [{"mainsnak": {"snaktype": "value", "datavalue": {"value": {"id": "QACTOR"}}}}],  # cast
                "P449": [{"mainsnak": {"snaktype": "value", "datavalue": {"value": {"id": "QNET"}}}}],   # network
                "P57": [{"mainsnak": {"snaktype": "value", "datavalue": {"value": {"id": "QDIR"}}}}],    # director
                # music props must be IGNORED for drama/film:
                "P264": [{"mainsnak": {"snaktype": "value", "datavalue": {"value": {"id": "QLABEL"}}}}],
                "P527": [{"mainsnak": {"snaktype": "value", "datavalue": {"value": {"id": "QMEMBER"}}}}],
            }}}}


def test_video_parse_uses_air_release_date_and_cast_not_music_props():
    for eid in ("drama:squidgame", "film:parasite"):
        p = parse_entity(_video_raw("오징어 게임", "Squid Game"), eid, "facts")
        assert p["debut"] == "2021-09-17"        # P577 air/release date
        assert p["agency_qids"] == ["QNET"]       # original network from P449 (music P264 ignored)
        assert p["member_qids"] == ["QACTOR"]     # CAST from P161, NOT P527 members
        assert p["director_qids"] == ["QDIR"]     # director from P57


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


def test_film_jsonld_node_is_movie_with_cast():
    now = datetime.now(timezone.utc)
    rec = Record(
        entity_id="film:traintobusan", kind="facts",
        name=Name(ko="부산행", en_official="Train to Busan"), snapshot_at=now,
        summary_en="Train to Busan — verified Korean film. Released 2016. 2 verified cast.",
        data={"debut": "2016", "members": ["Gong Yoo", "Ma Dong-seok"]},
        provenance=Provenance(sources=["Wikidata Q1", "Wikipedia Train to Busan"], fetched_at=now,
                              skill_score=1.0, confidence="high"),
    )
    node = admin._entity_node(rec)
    assert node["@type"] == "Movie"
    assert node.get("datePublished") == "2016"
    assert [a["name"] for a in node.get("actor", [])] == ["Gong Yoo", "Ma Dong-seok"]


def _webtoon_raw(ko: str, en: str):
    return {"entities": {"Q1": {"labels": {"ko": {"value": ko}, "en": {"value": en}},
            "claims": {
                "P577": [{"mainsnak": {"snaktype": "value",
                    "datavalue": {"value": {"time": "+2018-03-04T00:00:00Z"}}}}],
                "P50": [{"mainsnak": {"snaktype": "value", "datavalue": {"value": {"id": "QAUTH"}}}}],   # author
                "P123": [{"mainsnak": {"snaktype": "value", "datavalue": {"value": {"id": "QPUB"}}}}],   # publisher
                # music/video props must be IGNORED for a webtoon:
                "P264": [{"mainsnak": {"snaktype": "value", "datavalue": {"value": {"id": "QLABEL"}}}}],
                "P161": [{"mainsnak": {"snaktype": "value", "datavalue": {"value": {"id": "QCAST"}}}}],
                "P57": [{"mainsnak": {"snaktype": "value", "datavalue": {"value": {"id": "QDIR"}}}}],
            }}}}


def test_webtoon_parse_uses_author_publisher_publication_date():
    p = parse_entity(_webtoon_raw("나 혼자만 레벨업", "Solo Leveling"), "webtoon:sololeveling", "facts")
    assert p["debut"] == "2018-03-04"      # P577 publication date
    assert p["agency_qids"] == ["QPUB"]     # publisher P123 (not music P264)
    assert p["member_qids"] == ["QAUTH"]    # author P50 (not cast P161 / members P527)
    assert p["director_qids"] == []         # webtoons carry no director


def test_webtoon_jsonld_node_is_comicseries_with_author_and_publisher():
    now = datetime.now(timezone.utc)
    rec = Record(
        entity_id="webtoon:sololeveling", kind="facts",
        name=Name(ko="나 혼자만 레벨업", en_official="Solo Leveling"), snapshot_at=now,
        summary_en="Solo Leveling — verified Korean webtoon. Published 2018. By Chugong.",
        data={"debut": "2018", "members": ["Chugong"], "agency_en": "Kakao"},
        provenance=Provenance(sources=["Wikidata Q1", "Wikipedia Solo Leveling"], fetched_at=now,
                              skill_score=1.0, confidence="high"),
    )
    node = admin._entity_node(rec)
    assert node["@type"] == "ComicSeries"
    assert node.get("datePublished") == "2018"
    assert [a["name"] for a in node.get("author", [])] == ["Chugong"]
    assert node.get("publisher", {}).get("name") == "Kakao"
    assert "actor" not in node and "recordLabel" not in node  # not a video / not a group


def test_place_parses_location_and_inception_and_node_is_touristattraction():
    raw = {"entities": {"Q1": {"labels": {"ko": {"value": "경복궁"}, "en": {"value": "Gyeongbokgung"}},
           "claims": {
               "P131": [{"mainsnak": {"snaktype": "value", "datavalue": {"value": {"id": "QSEOUL"}}}}],
               "P571": [{"mainsnak": {"snaktype": "value",
                   "datavalue": {"value": {"time": "+1395-00-00T00:00:00Z"}}}}],
           }}}}
    p = parse_entity(raw, "place:gyeongbokgung", "facts")
    assert p["agency_qids"] == ["QSEOUL"] and p["debut"] == "1395"
    assert p["member_qids"] == [] and p["director_qids"] == []
    now = datetime.now(timezone.utc)
    rec = Record(entity_id="place:gyeongbokgung", kind="facts",
                 name=Name(ko="경복궁", en_official="Gyeongbokgung"), snapshot_at=now,
                 summary_en="Gyeongbokgung — verified Korean place / attraction. In Seoul.",
                 data={"agency_en": "Seoul", "debut": "1395"},
                 provenance=Provenance(sources=["Wikidata Q1", "Wikipedia Gyeongbokgung"],
                                       fetched_at=now, skill_score=1.0, confidence="high"))
    node = admin._entity_node(rec)
    assert node["@type"] == "TouristAttraction"
    assert node.get("containedInPlace", {}).get("name") == "Seoul"


def test_food_is_name_only_and_node_is_thing():
    raw = {"entities": {"Q1": {"labels": {"ko": {"value": "비빔밥"}, "en": {"value": "Bibimbap"}},
           "claims": {  # even if music/video props existed they'd be ignored for food
               "P264": [{"mainsnak": {"snaktype": "value", "datavalue": {"value": {"id": "QX"}}}}]}}}}
    p = parse_entity(raw, "food:bibimbap", "facts")
    assert p["agency_qids"] == [] and p["member_qids"] == [] and p["debut"] is None
    now = datetime.now(timezone.utc)
    rec = Record(entity_id="food:bibimbap", kind="facts",
                 name=Name(ko="비빔밥", en_official="Bibimbap"), snapshot_at=now,
                 summary_en="Bibimbap — verified Korean dish / food.", data={},
                 provenance=Provenance(sources=["Wikidata Q1", "Wikipedia Bibimbap"],
                                       fetched_at=now, skill_score=1.0, confidence="high"))
    node = admin._entity_node(rec)
    assert node["@type"] == "Thing"
    assert "recordLabel" not in node and "actor" not in node


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
