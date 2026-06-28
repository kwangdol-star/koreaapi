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


def test_extras_extracted_per_vertical_label_str_qty():
    # Depth: per-vertical extra attrs. label-typed (genre/language) defer to fetch() as Q-ids; qty
    # (episodes) resolves inline to a clean number. A vertical with no _EXTRAS yields neither key.
    raw = {"entities": {"Q1": {"labels": {"ko": {"value": "오징어 게임"}, "en": {"value": "Squid Game"}},
           "claims": {
               "P136": [{"mainsnak": {"snaktype": "value", "datavalue": {"value": {"id": "QGENRE"}}}}],
               "P1113": [{"mainsnak": {"snaktype": "value", "datavalue": {"value": {"amount": "+9"}}}}],
               "P364": [{"mainsnak": {"snaktype": "value", "datavalue": {"value": {"id": "QKOREAN"}}}}],
           }}}}
    p = parse_entity(raw, "drama:squidgame", "facts")
    assert p["extra_label_qids"]["Genre"] == ["QGENRE"]
    assert p["extra_label_qids"]["Original language"] == ["QKOREAN"]
    assert p["attrs"]["Episodes"] == "9"           # qty amount, sign + .0 stripped
    # folklore has no _EXTRAS -> no extra keys at all (rely on the abstract for substance)
    fp = parse_entity({"entities": {"Q2": {"labels": {"en": {"value": "Dokkaebi"}}}}}, "folklore:x", "facts")
    assert "attrs" not in fp and "extra_label_qids" not in fp


def test_attrs_render_as_citable_qa():
    now = datetime.now(timezone.utc)
    rec = Record(entity_id="drama:squidgame", kind="facts",
                 name=Name(ko="오징어 게임", en_official="Squid Game"), snapshot_at=now,
                 summary_en="Squid Game — verified Korean drama.",
                 data={"attrs": {"Genre": "thriller", "Episodes": "9"}},
                 provenance=Provenance(sources=["Wikidata Q1", "Wikipedia Squid Game"], fetched_at=now,
                                       skill_score=1.0, confidence="high"))
    qmap = dict(admin._entity_qa("Squid Game", rec, {"facts": rec}))
    assert "What is Squid Game's genre?" in qmap and "Genre: thriller" in qmap["What is Squid Game's genre?"]
    assert "What is Squid Game's episodes?" in qmap


def test_classic_parses_author_designation_and_routes_through_book_node():
    raw = {"entities": {"Q1": {"labels": {"ko": {"value": "삼국사기"}, "en": {"value": "Samguk Sagi"}},
           "claims": {
               "P50": [{"mainsnak": {"snaktype": "value", "datavalue": {"value": {"id": "QAUTH"}}}}],
               "P577": [{"mainsnak": {"snaktype": "value",
                   "datavalue": {"value": {"time": "+1145-00-00T00:00:00Z"}}}}],
               "P1435": [{"mainsnak": {"snaktype": "value", "datavalue": {"value": {"id": "QNT"}}}}],
           }}}}
    p = parse_entity(raw, "classic:samguksagi", "facts")
    assert p["member_qids"] == ["QAUTH"] and p["debut"] == "1145"           # author P50 + date
    assert p["extra_label_qids"]["Heritage designation"] == ["QNT"]          # P1435 -> Details
    now = datetime.now(timezone.utc)
    rec = Record(entity_id="classic:samguksagi", kind="facts",
                 name=Name(ko="삼국사기", en_official="Samguk Sagi"), snapshot_at=now,
                 summary_en="Samguk Sagi — verified Korean classic / historical text.",
                 data={"debut": "1145", "members": ["Kim Bu-sik"]},
                 provenance=Provenance(sources=["Wikidata Q1", "Wikipedia Samguk sagi"], fetched_at=now,
                                       skill_score=1.0, confidence="high"))
    node = admin._entity_node(rec)
    assert node["@type"] == "Book"  # classics route through the Book node
    assert [a["name"] for a in node.get("author", [])] == ["Kim Bu-sik"]


def test_food_diet_is_editorial_qa():
    now = datetime.now(timezone.utc)
    rec = Record(entity_id="food:bulgogi", kind="facts", name=Name(ko="불고기", en_official="Bulgogi"),
                 snapshot_at=now, summary_en="Bulgogi — verified Korean dish / food.",
                 data={"diet": "contains meat (beef)"},
                 provenance=Provenance(sources=["Wikidata Q1", "Wikipedia Bulgogi"], fetched_at=now,
                                       skill_score=1.0, confidence="high"))
    qmap = dict(admin._entity_qa("Bulgogi", rec, {"facts": rec}))
    assert "Is Bulgogi vegetarian?" in qmap and "contains meat" in qmap["Is Bulgogi vegetarian?"]


def test_place_parses_coordinates_and_node_emits_geocoordinates():
    raw = {"entities": {"Q1": {"labels": {"ko": {"value": "경복궁"}, "en": {"value": "Gyeongbokgung"}},
           "claims": {"P625": [{"mainsnak": {"snaktype": "value",
               "datavalue": {"value": {"latitude": 37.579621, "longitude": 126.977041}}}}]}}}}
    p = parse_entity(raw, "place:gyeongbokgung", "facts")
    assert p["geo"] == {"lat": 37.57962, "lon": 126.97704}  # rounded
    now = datetime.now(timezone.utc)
    rec = Record(entity_id="place:gyeongbokgung", kind="facts",
                 name=Name(ko="경복궁", en_official="Gyeongbokgung"), snapshot_at=now,
                 summary_en="Gyeongbokgung — verified Korean place.",
                 data={"geo": {"lat": 37.57962, "lon": 126.97704}},
                 provenance=Provenance(sources=["Wikidata Q1"], fetched_at=now, skill_score=1.0,
                                       confidence="high"))
    node = admin._entity_node(rec)
    assert node["geo"] == {"@type": "GeoCoordinates", "latitude": 37.57962, "longitude": 126.97704}


def test_food_spice_is_editorial_qa_and_stays_out_of_verified_facts():
    now = datetime.now(timezone.utc)
    rec = Record(entity_id="food:tteokbokki", kind="facts",
                 name=Name(ko="떡볶이", en_official="Tteokbokki"), snapshot_at=now,
                 summary_en="Tteokbokki — verified Korean dish / food.", data={"spice_level": "hot"},
                 provenance=Provenance(sources=["Wikidata Q1", "Wikipedia Tteokbokki"], fetched_at=now,
                                       skill_score=1.0, confidence="high"))
    qmap = dict(admin._entity_qa("Tteokbokki", rec, {"facts": rec}))
    assert "Is Tteokbokki spicy?" in qmap
    assert "hot" in qmap["Is Tteokbokki spicy?"] and "editorial" in qmap["Is Tteokbokki spicy?"]
    assert "spice" not in rec.summary_en.lower()  # editorial rating never pollutes the verified facts


def test_region_parses_stable_infobox_facts_and_excludes_volatile():
    # The country: parse_entity pulls STABLE facts (capital P36 / language P37 / currency P38 entity
    # Q-ids + ISO P297 / calling code P474 strings) and IGNORES volatile stats (population P1082).
    raw = {"entities": {"Q884": {"labels": {"ko": {"value": "대한민국"}, "en": {"value": "South Korea"}},
           "claims": {
               "P36": [{"mainsnak": {"snaktype": "value", "datavalue": {"value": {"id": "QSEOUL"}}}}],
               "P37": [{"mainsnak": {"snaktype": "value", "datavalue": {"value": {"id": "QKOREAN"}}}}],
               "P38": [{"mainsnak": {"snaktype": "value", "datavalue": {"value": {"id": "QWON"}}}}],
               "P297": [{"mainsnak": {"snaktype": "value", "datavalue": {"value": "KR"}}}],
               "P474": [{"mainsnak": {"snaktype": "value", "datavalue": {"value": "+82"}}}],
               "P1082": [{"mainsnak": {"snaktype": "value",  # population — must NOT be captured
                   "datavalue": {"value": {"amount": "+51000000"}}}}],
           }}}}
    p = parse_entity(raw, "region:southkorea", "facts")
    assert p["capital_qids"] == ["QSEOUL"] and p["lang_qids"] == ["QKOREAN"] and p["currency_qids"] == ["QWON"]
    assert p["iso_code"] == "KR" and p["calling_code"] == "+82"
    assert "population" not in p and "P1082" not in p  # volatile stat excluded (off-model)


def test_country_node_is_country_with_infobox_additionalproperty():
    now = datetime.now(timezone.utc)
    rec = Record(entity_id="region:southkorea", kind="facts",
                 name=Name(ko="대한민국", en_official="South Korea"), snapshot_at=now,
                 summary_en="South Korea — verified region. Capital: Seoul.",
                 data={"capital_en": "Seoul", "language_en": "Korean", "currency_en": "South Korean won",
                       "iso_code": "KR", "calling_code": "+82"},
                 provenance=Provenance(sources=["Wikidata Q884", "Wikipedia South Korea"],
                                       fetched_at=now, skill_score=1.0, confidence="high"))
    node = admin._entity_node(rec)
    assert node["@type"] == "Country"  # the country gets Country; provinces get AdministrativeArea
    props = {p["name"]: p["value"] for p in node.get("additionalProperty", [])}
    assert props["Capital"] == "Seoul" and props["Official language"] == "Korean"
    assert props["Currency"] == "South Korean won" and props["ISO 3166-1"] == "KR"
    assert props["Country calling code"] == "+82"
    # a province is a plain AdministrativeArea
    prov = Record(entity_id="region:jeju", kind="facts", name=Name(ko="제주", en_official="Jeju Province"),
                  snapshot_at=now, summary_en="Jeju Province — verified region.", data={},
                  provenance=Provenance(sources=["Wikidata Q1"], fetched_at=now, skill_score=1.0,
                                        confidence="high"))
    assert admin._entity_node(prov)["@type"] == "AdministrativeArea"


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
