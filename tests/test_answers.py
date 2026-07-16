"""Answer Products (engine 3) — each turns the verified store into one decision envelope
{signal, action, score, rationale, answer, evidence}. Mirrors the sibling oracle's
decision-products pattern, adapted to culture data. Offline: no keys, no network, no chain."""

from __future__ import annotations

import asyncio
import tempfile
from datetime import datetime, timezone

from koreaapi import answers
from koreaapi.models import Name, Provenance, Record
from koreaapi.pipeline import store

NOW = datetime(2026, 6, 28, tzinfo=timezone.utc)


def _add(db: str, eid: str, ko: str, en: str, *, sources: list[str], agree: int, skill: float,
         data: dict | None = None) -> None:
    asyncio.run(store.append_record(Record(
        entity_id=eid, kind="facts", name=Name(ko=ko, en_official=en), snapshot_at=NOW,
        summary_en=en, data=data or {}, provenance=Provenance(
            sources=sources, fetched_at=NOW, skill_score=skill,
            confidence="high" if agree >= 2 else "low", agreeing_sources=agree)), db_path=db))


def _seed() -> str:
    db = tempfile.mktemp(suffix=".db")
    _add(db, "drama:vincenzo", "빈센조", "Vincenzo",
         sources=["Wikidata Q16741113", "TMDB 96162", "Wikipedia (ko)"], agree=3, skill=1.0)
    _add(db, "artist:newjeans", "뉴진스", "NewJeans", sources=["Wikidata Q1"], agree=1, skill=0.7)
    return db


def test_canonical_name_confirmed():
    out = asyncio.run(answers.answer("canonical-name", "Vincenzo", db_path=_seed()))
    assert out["signal"] == "CONFIRMED"
    assert out["answer"]["ko"] == "빈센조"      # the 빈첸초 bug, now a guarded product
    assert out["score"] >= 0.9


def test_canonical_name_unverified_single_source():
    out = asyncio.run(answers.answer("canonical-name", "NewJeans", db_path=_seed()))
    assert out["signal"] == "UNVERIFIED"        # one source -> don't assert the spelling


def test_canonical_name_not_found():
    out = asyncio.run(answers.answer("canonical-name", "Nonexistent Thing", db_path=_seed()))
    assert out["signal"] == "NOT_FOUND"
    assert out["score"] == 0.0


def test_fact_check_triple_verified_is_citable():
    out = asyncio.run(answers.answer("fact-check", "빈센조", db_path=_seed()))
    assert out["signal"] == "TRIPLE_VERIFIED"
    assert "cite" in out["action"].lower()
    assert out["answer"]["id"] == "drama:vincenzo"


def test_fact_check_single_source_not_citable():
    out = asyncio.run(answers.answer("fact-check", "NewJeans", db_path=_seed()))
    assert out["signal"] == "UNVERIFIED"
    assert "do not cite" in out["action"].lower()


def test_identity_resolve_exact():
    out = asyncio.run(answers.answer("identity-resolve", "drama:vincenzo", db_path=_seed()))
    assert out["signal"] == "RESOLVED"
    assert out["answer"]["id"] == "drama:vincenzo"
    assert out["answer"]["content_hash"]          # ID spine carries the content hash


def test_answer_all_runs_every_product():
    out = asyncio.run(answers.answer_all("Vincenzo", db_path=_seed()))
    assert out["count"] == len(answers.list_products()["products"])
    sigs = {a["product"]: a["signal"] for a in out["answers"]}
    assert sigs["canonical-name"] == "CONFIRMED"
    assert sigs["fact-check"] == "TRIPLE_VERIFIED"
    # every envelope carries the uniform decision keys
    for a in out["answers"]:
        assert {"product", "signal", "action", "score", "rationale", "answer", "evidence"} <= set(a)


def test_trip_plan_matches_region_and_packs_foods():
    db = tempfile.mktemp(suffix=".db")
    for i, (eid, ko, en) in enumerate([("place:haeundae", "해운대", "Haeundae"),
                                       ("place:gamcheon", "감천문화마을", "Gamcheon Culture Village"),
                                       ("place:jagalchi", "자갈치시장", "Jagalchi Market")]):
        _add(db, eid, ko, en, sources=["Wikidata Q1", "Wikipedia x"], agree=2, skill=1.0 - i * 0.01,
             data={"agency_en": "Busan"})  # located-in hub edge = the region match
    _add(db, "festival:busaniff", "부산국제영화제", "Busan International Film Festival",
         sources=["Wikidata Q2", "Wikipedia y"], agree=2, skill=1.0, data={"agency_en": "Busan"})
    _add(db, "place:gyeongbokgung", "경복궁", "Gyeongbokgung",
         sources=["Wikidata Q3"], agree=2, skill=1.0, data={"agency_en": "Seoul"})  # other region
    _add(db, "food:bibimbap", "비빔밥", "Bibimbap", sources=["Wikidata Q4"], agree=2, skill=1.0)
    out = asyncio.run(answers.answer("trip-plan", "Busan", db_path=db))
    assert out["signal"] == "PLAN_READY"
    ids = [p["id"] for p in out["answer"]["places"]]
    assert "place:haeundae" in ids and "place:gyeongbokgung" not in ids   # region-filtered
    assert out["answer"]["festivals"][0]["id"] == "festival:busaniff"
    assert out["answer"]["foods"][0]["id"] == "food:bibimbap"             # national picks ride along
    assert asyncio.run(answers.answer("trip-plan", "Nowhereville", db_path=db))["signal"] == "THIN"


def test_trip_plan_pulls_all_geo_verticals_grouped_by_type():
    # The trip plan draws on EVERY geo vertical verified in the region (not just place:) — the breadth
    # this session added (parks, temples, ski resorts, beaches…) turned into one region itinerary.
    db = tempfile.mktemp(suffix=".db")
    for eid, ko, en in [("park:seoraksan", "설악산국립공원", "Seoraksan National Park"),
                        ("beach:gyeongpo", "경포해수욕장", "Gyeongpo Beach"),
                        ("skiresort:yongpyong", "용평리조트", "Yongpyong Resort"),
                        ("temple:naksansa", "낙산사", "Naksansa")]:
        _add(db, eid, ko, en, sources=["Wikidata Q1", "Wikipedia x"], agree=2, skill=1.0,
             data={"agency_en": "Gangwon"})  # located-in region edge
    _add(db, "park:jirisan", "지리산", "Jirisan National Park",
         sources=["Wikidata Q2"], agree=2, skill=1.0, data={"agency_en": "South Gyeongsang"})  # other region
    out = asyncio.run(answers.answer("trip-plan", "Gangwon", db_path=db))
    assert out["signal"] == "PLAN_READY"
    ids = {p["id"] for p in out["answer"]["places"]}
    assert {"park:seoraksan", "beach:gyeongpo", "skiresort:yongpyong", "temple:naksansa"} <= ids
    assert "park:jirisan" not in ids                       # region-filtered
    bt = out["answer"]["by_type"]
    assert set(bt) == {"park", "beach", "skiresort", "temple"}   # grouped by vertical type
    assert bt["park"][0]["id"] == "park:seoraksan"


def test_trip_plan_is_map_ready_with_walkable_clusters():
    # Items carry verified coordinates (agents can plot/route) and close spots form walkable clusters
    # (≤3 km, greedy from the highest-skill anchor) — day-plan raw material, pure math.
    db = tempfile.mktemp(suffix=".db")
    _add(db, "place:jagalchi", "자갈치시장", "Jagalchi Market", sources=["Wikidata Q1", "Wikipedia a"],
         agree=2, skill=1.0, data={"agency_en": "Busan", "geo": {"lat": 35.0966, "lon": 129.0306}})
    _add(db, "place:gamcheon", "감천문화마을", "Gamcheon Culture Village", sources=["Wikidata Q2", "Wikipedia b"],
         agree=2, skill=0.99, data={"agency_en": "Busan", "geo": {"lat": 35.0975, "lon": 129.0106}})  # ~1.8 km
    _add(db, "beach:haeundae", "해운대", "Haeundae Beach", sources=["Wikidata Q3", "Wikipedia c"],
         agree=2, skill=0.98, data={"agency_en": "Busan", "geo": {"lat": 35.1587, "lon": 129.1604}})  # ~13 km
    _add(db, "temple:nocoords", "무좌표사", "No Coords Temple", sources=["Wikidata Q4", "Wikipedia d"],
         agree=2, skill=0.97, data={"agency_en": "Busan"})

    out = asyncio.run(answers.answer("trip-plan", "Busan", db_path=db))
    assert out["signal"] == "PLAN_READY"
    by_id = {p["id"]: p for p in out["answer"]["places"]}
    assert by_id["place:jagalchi"]["geo"]["lat"] == 35.0966          # coordinates ride on the item
    assert "geo" not in by_id["temple:nocoords"]                     # absent stays absent (no invention)
    clusters = out["answer"]["walkable_clusters"]
    assert len(clusters) == 1                                        # haeundae + nocoords form no group
    assert clusters[0]["anchor"]["id"] == "place:jagalchi"           # highest-skill spot anchors
    spots = clusters[0]["spots"]
    assert [s["id"] for s in spots] == ["place:gamcheon"] and 0 < spots[0]["km_from_anchor"] < 3.0
    assert "walkable cluster" in out["rationale"]


def test_trip_plan_geo_namespaces_stay_in_sync_with_the_geo_node_types():
    # A new geo vertical must join the trip plan too (else a whole category of verified spots silently
    # never surfaces in a region itinerary). _GEO_NS must match admin's geo-node type map exactly.
    from koreaapi.admin import _GEO_NODE_TYPE
    from koreaapi.answers import _GEO_NS
    assert set(_GEO_NS) == set(_GEO_NODE_TYPE)


def test_food_guide_filters_by_dietary_and_spice():
    # Foreigner meal filter: verified dishes filtered by the editorial spice + dietary tags. The dish
    # name is cross-verified; the tag is clearly labeled editorial (never presented as cross-verified).
    db = tempfile.mktemp(suffix=".db")
    for eid, ko, en in [("food:japchae", "잡채", "Japchae"),          # editorial: mild, vegetarian
                        ("food:tteokbokki", "떡볶이", "Tteokbokki"),   # hot, vegetarian (often)
                        ("food:bulgogi", "불고기", "Bulgogi"),         # mild, contains meat
                        ("food:hoe", "회", "Hoe")]:                     # none, contains seafood
        _add(db, eid, ko, en, sources=["Wikidata Q1", "Wikipedia x"], agree=2, skill=1.0)
    veg = asyncio.run(answers.answer("food-guide", "vegetarian", db_path=db))
    veg_ids = {d["id"] for d in veg["answer"]["dishes"]}
    assert veg["signal"] == "MATCHES"
    assert "food:japchae" in veg_ids and "food:bulgogi" not in veg_ids and "food:hoe" not in veg_ids
    assert "editorial" in veg["rationale"].lower()                    # the tag is labeled editorial
    mild_ids = {d["id"] for d in asyncio.run(answers.answer("food-guide", "not spicy", db_path=db))["answer"]["dishes"]}
    assert "food:tteokbokki" not in mild_ids and "food:japchae" in mild_ids   # hot excluded, mild kept
    noseafood = asyncio.run(answers.answer("food-guide", "no seafood", db_path=db))
    assert "food:hoe" not in {d["id"] for d in noseafood["answer"]["dishes"]}  # seafood excluded


def test_evidence_pack_is_cite_ready_for_cross_verified():
    out = asyncio.run(answers.answer("evidence-pack", "Vincenzo", db_path=_seed()))
    assert out["signal"] == "CITE_READY"
    a = out["answer"]
    assert a["id"] == "drama:vincenzo" and a["tier"] == "triple-verified" and a["citable"] is True
    assert a["content_hash"]                                              # tamper-evident hash rides along
    assert "https://www.wikidata.org/entity/Q16741113" in a["same_as"]    # reconciled sameAs link
    assert "빈센조" in a["citation"]["ko"] and "via KoreaAPI" in a["citation"]["en"]


def test_evidence_pack_single_source_is_cautioned():
    out = asyncio.run(answers.answer("evidence-pack", "NewJeans", db_path=_seed()))
    assert out["signal"] == "CITE_WITH_CAUTION"
    assert out["answer"]["citable"] is False and out["answer"]["tier"] == "single-source"


def test_evidence_pack_not_found():
    out = asyncio.run(answers.answer("evidence-pack", "Nonexistent Thing", db_path=_seed()))
    assert out["signal"] == "NOT_FOUND" and out["score"] == 0.0


def test_compare_two_verified_entities_side_by_side():
    out = asyncio.run(answers.answer("compare", "Vincenzo vs NewJeans", db_path=_seed()))
    assert out["signal"] == "COMPARED"
    a, b = out["answer"]["a"], out["answer"]["b"]
    assert a["id"] == "drama:vincenzo" and b["id"] == "artist:newjeans"
    assert a["tier"] == "triple-verified" and b["tier"] == "single-source"
    assert out["answer"]["better_verified"]["id"] == "drama:vincenzo"   # = more agreeing sources
    assert "editorial" in out["rationale"]                              # never a taste judgment
    assert out["answer"]["same_kind"] is False and "different kinds" in out["action"]
    assert out["score"] == b["skill_score"]                             # min(): the weaker side gates


def test_compare_needs_exactly_two_and_names_the_missing_one():
    assert asyncio.run(answers.answer("compare", "Vincenzo", db_path=_seed()))["signal"] == "NEED_TWO"
    out = asyncio.run(answers.answer("compare", "Vincenzo vs Nonexistent Thing", db_path=_seed()))
    assert out["signal"] == "NOT_FOUND" and out["answer"]["missing"] == "Nonexistent Thing"


def test_compare_routes_from_free_text(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert answers.route("경복궁 vs 창덕궁")["product"] == "compare"
    assert answers.route("difference between bibimbap and bulgogi")["product"] == "compare"


def test_person_credits_surfaces_collaborators():
    db = tempfile.mktemp(suffix=".db")
    for eid, ko, en in [("film:parasite", "기생충", "Parasite"),
                        ("film:memoriesofmurder", "살인의 추억", "Memories of Murder")]:
        _add(db, eid, ko, en, sources=["Wikidata Q1", "Wikipedia x"], agree=2, skill=1.0,
             data={"directors": ["Bong Joon-ho"], "members": ["Song Kang-ho"]})
    out = asyncio.run(answers.answer("person-credits", "Bong Joon-ho", db_path=db))
    assert out["signal"] == "FOUND"
    collabs = out["answer"]["collaborators"]                    # crawl<->agent parity for the person graph
    assert [c["name"] for c in collabs] == ["Song Kang-ho"] and collabs[0]["shared_count"] == 2


def test_catalog_is_bilingual():
    cat = answers.list_products()
    assert all(p.get("name_ko") and p.get("about_ko") for p in cat["products"])
    assert "note_ko" in cat


def test_unknown_product_errors():
    out = asyncio.run(answers.answer("nope", "x", db_path=_seed()))
    assert "error" in out
    assert "canonical-name" in out["available"]


def test_list_products_shape():
    cat = answers.list_products()
    assert cat["count"] >= 5
    assert all({"id", "name", "sector", "inputs", "about"} <= set(p) for p in cat["products"])


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
