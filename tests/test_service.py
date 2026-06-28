"""Offline tests for the agent-face service (no fastmcp, no network).

Proves the agent face serves verified, bilingual, provenance-bearing data from the
append-only store - the same store the human console reads.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from datetime import datetime, timezone

from koreaapi import service
from koreaapi.admin import seed
from koreaapi.models import Name, Provenance, Record
from koreaapi.pipeline import store


def _seeded_db() -> str:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(path)
    asyncio.run(seed(db_path=path))
    return path


def _agency_db() -> str:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(path)
    now = datetime.now(timezone.utc)
    rows = [
        ("artist:straykids", "스트레이키즈", "Stray Kids", "JYP Entertainment"),
        ("artist:2pm", "투피엠", "2PM", "JYP Entertainment"),
        ("artist:aespa", "에스파", "aespa", "SM Entertainment"),
        # "Cosmic Music" normalizes to "cosmicmusic" which *contains* "sm" - a substring match would
        # wrongly attribute this act to a query of "SM". A prefix match must not.
        ("artist:bandx", "밴드엑스", "BandX", "Cosmic Music"),
    ]
    for eid, ko, en, agency in rows:
        rec = Record(
            entity_id=eid, kind="facts", name=Name(ko=ko, en_official=en),
            snapshot_at=now, summary_en=f"{en} - facts.", data={"agency_en": agency},
            provenance=Provenance(sources=["Wikidata Q1"], fetched_at=now, skill_score=0.9, confidence="high"),
        )
        asyncio.run(store.append_record(rec, db_path=path))
    return path


def test_artist_status_is_verified_and_bilingual():
    db = _seeded_db()
    out = asyncio.run(service.artist_status("artist:bts", db_path=db))

    assert out["found"] is True
    assert out["name"]["en_official"] == "BTS"
    assert out["name"]["ko"] == "방탄소년단"
    assert out["status"], "should have at least one status item"
    item = out["status"][0]
    assert item["provenance"]["skill_score"] >= 0.8
    assert item["provenance"]["sources"]


def test_korea_rising_ranks_high_skill_first():
    db = _seeded_db()
    out = asyncio.run(service.korea_rising(limit=10, db_path=db))

    scores = [i["provenance"]["skill_score"] for i in out["items"]]
    assert scores == sorted(scores, reverse=True)
    # BTS/NewJeans (1.0) outrank aespa (0.7, single-source)
    assert scores[0] >= scores[-1]


def test_agency_lists_only_that_agencys_verified_members():
    db = _agency_db()
    out = asyncio.run(service.agency("JYP", db_path=db))  # prefix match on the label
    names = {m["name"]["en_official"] for m in out["members"]}
    assert names == {"Stray Kids", "2PM"} and out["count"] == 2  # SM/Cosmic excluded
    assert out["members"][0]["provenance"]["sources"]  # provenance carried
    # the full label name resolves the same; an unknown agency returns nobody
    assert asyncio.run(service.agency("JYP Entertainment", db_path=db))["count"] == 2
    assert asyncio.run(service.agency("YG", db_path=db))["count"] == 0


def test_agency_prefix_match_excludes_substring_false_positives():
    db = _agency_db()
    out = asyncio.run(service.agency("SM", db_path=db))  # must match "SM Entertainment" only
    names = {m["name"]["en_official"] for m in out["members"]}
    assert names == {"aespa"}  # NOT BandX ("Cosmic Music" merely *contains* "sm")


def test_artist_status_name_comes_from_best_verified_record():
    fd, db = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(db)
    now = datetime.now(timezone.utc)
    # a 'release' record (single-source 0.7, English placeholder in the ko field) ...
    asyncio.run(store.append_record(Record(
        entity_id="artist:bts", kind="release", name=Name(ko="BTS", en_official="BTS"),
        snapshot_at=now, summary_en="release", data={},
        provenance=Provenance(sources=["YouTube"], fetched_at=now, skill_score=0.7, confidence="medium"),
    ), db_path=db))
    # ... and the cross-verified 'facts' record (1.0, canonical Korean name).
    asyncio.run(store.append_record(Record(
        entity_id="artist:bts", kind="facts",
        name=Name(ko="방탄소년단", en_official="BTS", romanized="Bangtan Sonyeondan"),
        snapshot_at=now, summary_en="facts", data={},
        provenance=Provenance(sources=["Wikidata", "Wikipedia"], fetched_at=now, skill_score=1.0, confidence="high"),
    ), db_path=db))
    out = asyncio.run(service.artist_status("artist:bts", db_path=db))
    assert out["name"] == {"ko": "방탄소년단", "en_official": "BTS", "romanized": "Bangtan Sonyeondan"}


def _graph_db() -> str:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(path)
    now = datetime.now(timezone.utc)
    rows = [
        ("film:parasite", "기생충", "Parasite", {"directors": ["Bong Joon-ho"], "members": ["Song Kang-ho"]}),
        ("film:memoriesofmurder", "살인의 추억", "Memories of Murder",
         {"directors": ["Bong Joon-ho"], "members": ["Song Kang-ho"]}),
        ("drama:squidgame", "오징어 게임", "Squid Game", {"agency_en": "Netflix"}),
        ("drama:allofusaredead", "지금 우리 학교는", "All of Us Are Dead", {"agency_en": "Netflix"}),
        ("artist:straykids", "스트레이키즈", "Stray Kids", {"agency_en": "JYP Entertainment"}),
        ("artist:itzy", "있지", "ITZY", {"agency_en": "JYP Entertainment"}),
        ("artist:aespa", "에스파", "aespa", {"agency_en": "SM Entertainment"}),
    ]
    for eid, ko, en, data in rows:
        asyncio.run(store.append_record(Record(
            entity_id=eid, kind="facts", name=Name(ko=ko, en_official=en), snapshot_at=now,
            summary_en=f"{en} - facts.", data=data,
            provenance=Provenance(sources=["Wikidata Q1", "Wikipedia"], fetched_at=now,
                                  skill_score=1.0, confidence="high"),
        ), db_path=path))
    return path


def test_person_aggregates_credits_across_works():
    db = _graph_db()
    out = asyncio.run(service.person("Bong Joon-ho", db_path=db))
    assert out["found"] is True and out["count"] == 2          # a cross-work director hub
    assert {c["work"]["entity_id"] for c in out["credits"]} == {"film:parasite", "film:memoriesofmurder"}
    assert all(c["role"] == "director" for c in out["credits"])
    assert out["provenance"]["sources"] and "via KoreaAPI" in out["citation"]
    # a slug-form query resolves to the same person (name == slug); cast role aggregates too
    slug_form = asyncio.run(service.person("bong-joon-ho", db_path=db))
    assert slug_form["found"] is True and slug_form["name"] == "Bong Joon-ho" and slug_form["count"] == 2
    assert asyncio.run(service.person("song-kang-ho", db_path=db))["count"] == 2  # cast credits


def test_person_unknown_is_honest_miss():
    db = _graph_db()
    out = asyncio.run(service.person("Nobody At All", db_path=db))
    assert out["found"] is False


def test_related_by_agency_and_network_within_family():
    db = _graph_db()
    sk = asyncio.run(service.related("artist:straykids", db_path=db))
    assert sk["related_by"] == "agency" and sk["key"] == "JYP Entertainment"
    names = {m["name"]["en_official"] for m in sk["related"]}
    assert names == {"ITZY"}                                   # same 소속사; aespa (SM) + dramas excluded
    sg = asyncio.run(service.related("drama:squidgame", db_path=db))
    assert sg["related_by"] == "network" and sg["key"] == "Netflix"
    assert {m["name"]["en_official"] for m in sg["related"]} == {"All of Us Are Dead"}


def test_related_without_edge_is_empty_not_error():
    db = _graph_db()
    out = asyncio.run(service.related("film:parasite", db_path=db))  # theatrical film, no network edge
    assert out["found"] is True and out["count"] == 0


def test_buy_options_phase1_stub_is_honest():
    db = _seeded_db()
    out = asyncio.run(service.buy_options("BTS album", db_path=db))

    assert out["options"] == []
    assert "buy-intent" in out["note"]


def test_korea_rising_category_filter_and_buy_intent_weight():
    db = _agency_db()  # seeds 4 artists
    asyncio.run(store.log_signal("query", "artist:aespa", db_path=db))
    asyncio.run(store.log_signal("buy_intent", "artist:straykids", db_path=db))
    out = asyncio.run(service.korea_rising(category="artist", db_path=db))
    assert out["count"] >= 2
    # buy-intent (×3) outranks a single query -> Stray Kids tops aespa
    assert out["items"][0]["name"]["en_official"] == "Stray Kids" and out["items"][0]["buy_intent"] == 1
    # category drill-down actually filters (was previously ignored): no dramas seeded -> empty
    assert asyncio.run(service.korea_rising(category="drama", db_path=db))["count"] == 0


def test_verified_reports_cross_verification_status():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(path)
    now = datetime.now(timezone.utc)
    rec = Record(entity_id="artist:bts", kind="facts", name=Name(ko="방탄소년단", en_official="BTS"),
                 snapshot_at=now, summary_en="BTS — verified.", data={},
                 provenance=Provenance(sources=["Wikidata Q1", "Wikipedia BTS", "MusicBrainz mbid"],
                                       fetched_at=now, skill_score=1.0, confidence="high",
                                       agreeing_sources=3))
    asyncio.run(store.append_record(rec, db_path=path))
    out = asyncio.run(service.verified("artist:bts", db_path=path))
    assert out["found"] and out["triple_verified"] and out["cross_verified"]
    assert out["agreeing_sources"] == 3 and len(out["sources"]) == 3 and "triple" in out["note"]
    miss = asyncio.run(service.verified("artist:nope", db_path=path))
    assert miss["found"] is False


def test_certification_is_top_tier_in_verified_and_on_page(tmp_path):
    from koreaapi import admin
    from koreaapi.roster import CERTIFIED
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(path)
    now = datetime.now(timezone.utc)
    rec = Record(entity_id="artist:bts", kind="facts", name=Name(ko="방탄소년단", en_official="BTS"),
                 snapshot_at=now, summary_en="BTS — verified.", data={},
                 provenance=Provenance(sources=["Wikidata Q1", "Wikipedia BTS"], fetched_at=now,
                                       skill_score=1.0, confidence="high", agreeing_sources=2))
    asyncio.run(store.append_record(rec, db_path=path))
    CERTIFIED["artist:bts"] = {"by": "HYBE", "date": "2026-06-01"}  # seed a certification for the test
    try:
        out = asyncio.run(service.verified("artist:bts", db_path=path))
        assert out["officially_certified"] and out["certified_by"] == "HYBE"
        assert "officially certified by HYBE" in out["note"]  # ranks above cross-verified
        d = str(tmp_path / "site")
        asyncio.run(admin.entity_pages(db_path=path, out_dir=d))
        page = open(os.path.join(d, "artist", "bts.html"), encoding="utf-8").read()
        assert "Official certification" in page and "Certified by <b>HYBE</b>" in page
        assert "officially certified by HYBE" in page  # the header badge
    finally:
        CERTIFIED.pop("artist:bts", None)


if __name__ == "__main__":
    test_artist_status_is_verified_and_bilingual()
    test_korea_rising_ranks_high_skill_first()
    test_buy_options_phase1_stub_is_honest()
    print("all service tests passed")
