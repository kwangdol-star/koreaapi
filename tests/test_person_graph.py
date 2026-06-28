"""Person / credit knowledge graph: pivot verified works by PERSON into citable hub pages.

Pure aggregation over already-verified records (no new fetch, no new trust surface): a director
becomes a hub linking the films they made, cast/members link works to people, and same-agency /
same-network edges link entity to entity. These tests pin the qualification rules (who earns a
page), the cross-link resolution (entity vs person vs plain text), the Schema.org Person node, and
the hub-edge ("related") logic — all offline.
"""

from __future__ import annotations

from datetime import datetime, timezone

from koreaapi import admin
from koreaapi.models import Name, Provenance, Record


def _rec(entity_id: str, ko: str, en: str, data: dict, sources: list[str]) -> Record:
    now = datetime(2026, 6, 27, tzinfo=timezone.utc)
    return Record(
        entity_id=entity_id, kind="facts",
        name=Name(ko=ko, en_official=en), snapshot_at=now,
        summary_en=f"{en} — verified.", data=data,
        provenance=Provenance(sources=sources, fetched_at=now, skill_score=1.0, confidence="high"),
    )


def _by_entity() -> dict:
    return {
        eid: {"facts": rec}
        for eid, rec in {
            # Bong Joon-ho directs 2 films (a cross-work hub); Song Kang-ho is cast in 2 (connective).
            "film:parasite": _rec("film:parasite", "기생충", "Parasite",
                {"directors": ["Bong Joon-ho"], "members": ["Song Kang-ho", "Choi Woo-shik"]},
                ["Wikidata Q61448040", "Wikipedia Parasite"]),
            "film:memoriesofmurder": _rec("film:memoriesofmurder", "살인의 추억", "Memories of Murder",
                {"directors": ["Bong Joon-ho"], "members": ["Song Kang-ho"]},
                ["Wikidata Q487604", "Wikipedia Memories of Murder"]),
            # Two Netflix dramas -> same-network related edge; a Korean-only-named actor in both.
            "drama:squidgame": _rec("drama:squidgame", "오징어 게임", "Squid Game",
                {"agency_en": "Netflix", "members": ["정호연", "Lee Jung-jae"]},
                ["Wikidata Q1", "Wikipedia Squid Game"]),
            "drama:allofusaredead": _rec("drama:allofusaredead", "지금 우리 학교는", "All of Us Are Dead",
                {"agency_en": "Netflix", "members": ["정호연"]},
                ["Wikidata Q2", "Wikipedia All of Us Are Dead"]),
            # Two Big Hit artists -> same-agency related edge. IU is a soloist whose person-slug
            # collides with her own entity slug (links to the entity page, no separate person page).
            "artist:bts": _rec("artist:bts", "방탄소년단", "BTS",
                {"agency_en": "Big Hit Music", "members": ["RM", "Jin"]}, ["Wikidata Q13580495"]),
            "artist:txt": _rec("artist:txt", "투모로우바이투게더", "Tomorrow X Together",
                {"agency_en": "Big Hit Music", "members": ["Soobin"]}, ["Wikidata Q3"]),
            "artist:iu": _rec("artist:iu", "아이유", "IU", {"members": ["IU"]}, ["Wikidata Q4"]),
        }.items()
    }


def test_collect_credits_pivots_works_by_person():
    people = admin._collect_credits(_by_entity())
    bong = people["Bong Joon-ho"]
    assert {c["work_name"] for c in bong["credits"]} == {"Parasite", "Memories of Murder"}
    assert all(c["role"] == "director" for c in bong["credits"])
    # cast role for a film member; member role for an artist member
    assert people["Song Kang-ho"]["credits"][0]["role"] == "cast"
    assert people["RM"]["credits"][0]["role"] == "member"
    assert people["Song Kang-ho"]["credits"][0]["kind"] == "film"


def test_qualification_rules():
    people = admin._collect_credits(_by_entity())
    q = admin._qualifies_for_person_page
    assert q(people["Bong Joon-ho"]["credits"])      # director (even though 2 here) -> page
    assert q(people["Song Kang-ho"]["credits"])      # in 2 works -> page
    assert not q(people["Choi Woo-shik"]["credits"])  # 1 cast credit -> stays a plain name
    assert not q(people["RM"]["credits"])             # 1 member credit -> no page


def test_linked_person_slugs_excludes_collisions_and_nonascii():
    by_entity = _by_entity()
    people = admin._collect_credits(by_entity)
    entity_slugs = {admin._slug(eid) for eid in by_entity}
    linked = admin._linked_person_slugs(people, entity_slugs)
    assert "bong-joon-ho" in linked and "song-kang-ho" in linked
    assert "iu" not in linked            # collides with the artist:iu entity slug -> link to entity
    assert "정호연" not in linked          # qualifies (2 works) but non-ascii slug -> no page (clean URLs)
    assert "choi-woo-shik" not in linked  # didn't qualify


def test_credit_link_resolves_entity_then_person_then_plain():
    by_entity = _by_entity()
    people = admin._collect_credits(by_entity)
    entity_slugs = {admin._slug(eid) for eid in by_entity}
    linked = admin._linked_person_slugs(people, entity_slugs)
    assert '../person/bong-joon-ho.html' in admin._credit_link("Bong Joon-ho", entity_slugs, linked)
    assert '../artist/iu.html' in admin._credit_link("IU", entity_slugs, linked)  # soloist -> entity
    assert admin._credit_link("Choi Woo-shik", entity_slugs, linked) == "Choi Woo-shik"  # plain


def test_person_node_is_schema_person_with_typed_knownfor():
    people = admin._collect_credits(_by_entity())
    node = admin._person_node("Bong Joon-ho", people["Bong Joon-ho"]["credits"])
    assert node["@type"] == "Person"
    assert {k["@type"] for k in node["knownFor"]} == {"Movie"}
    assert all(k["url"].endswith(".html") for k in node["knownFor"])


def test_person_qa_groups_by_role():
    people = admin._collect_credits(_by_entity())
    qa_dir = dict(admin._person_qa("Bong Joon-ho", people["Bong Joon-ho"]["credits"]))
    assert any("direct" in q.lower() for q in qa_dir)
    qa_cast = dict(admin._person_qa("Song Kang-ho", people["Song Kang-ho"]["credits"]))
    assert any("acting" in q.lower() for q in qa_cast)


def test_collaborators_link_people_who_share_verified_works():
    by_entity = _by_entity()
    people = admin._collect_credits(by_entity)
    linked = admin._linked_person_slugs(people, {admin._slug(e) for e in by_entity})
    work_people: dict[str, set] = {}
    for nm, p in people.items():
        for c in p["credits"]:
            work_people.setdefault(c["work_slug"], set()).add(nm)
    linked_names = {nm for nm, p in people.items() if p["slug"] in linked}
    collabs = admin._collaborators("Bong Joon-ho", people["Bong Joon-ho"]["credits"],
                                   work_people, linked_names)
    cmap = {o: set(w) for o, _s, w in collabs}
    # Song Kang-ho shares BOTH films with Bong -> a collaborator, both shared works listed
    assert cmap.get("Song Kang-ho") == {"Parasite", "Memories of Murder"}
    assert "Bong Joon-ho" not in cmap          # self excluded
    assert "Choi Woo-shik" not in cmap          # only 1 credit -> not a linked person -> excluded
    # the edge surfaces in the Person node (colleague) + Q&A (FAQPage)
    node = admin._person_node("Bong Joon-ho", people["Bong Joon-ho"]["credits"], collabs)
    assert node["colleague"][0]["name"] == "Song Kang-ho"
    qmap = dict(admin._person_qa("Bong Joon-ho", people["Bong Joon-ho"]["credits"], collabs))
    assert "Song Kang-ho" in qmap.get("Who has Bong Joon-ho worked with?", "")


def test_related_same_agency_and_network_within_family():
    by_entity = _by_entity()
    bts_related = admin._related("artist:bts", by_entity["artist:bts"]["facts"], by_entity)
    assert ("Tomorrow X Together", "txt") in bts_related       # same 소속사
    assert all(s != "squidgame" for _n, s in bts_related)      # artists don't relate to dramas
    sg_related = admin._related("drama:squidgame", by_entity["drama:squidgame"]["facts"], by_entity)
    assert ("All of Us Are Dead", "allofusaredead") in sg_related  # same network (Netflix)


def test_related_empty_without_agency():
    by_entity = _by_entity()
    # Parasite has no network/agency -> no hub edge (theatrical film, P449 empty)
    assert admin._related("film:parasite", by_entity["film:parasite"]["facts"], by_entity) == []


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
