"""The homepage (report.html -> index.html) is the public AEO magnet. It must read as a browsable
catalogue grouped by vertical (artists / dramas / films), surface the person-graph hubs, and emit
Schema.org for BOTH entities and people. Built from a seeded store, offline."""

from __future__ import annotations

import asyncio
import tempfile

from koreaapi import admin
from koreaapi.pipeline.ingest import ingest_one
from koreaapi.sources.mock import MockSource


def _seed(db: str) -> None:
    facts = [
        ("artist:bts", {"name_ko": "방탄소년단", "name_en_official": "BTS",
                        "name_en_source": "official", "agency_en": "Big Hit Music", "members": ["RM"]}),
        ("drama:squidgame", {"name_ko": "오징어 게임", "name_en_official": "Squid Game",
                             "name_en_source": "official", "agency_en": "Netflix"}),
        ("film:parasite", {"name_ko": "기생충", "name_en_official": "Parasite",
                           "name_en_source": "official", "directors": ["Bong Joon-ho"]}),
        ("film:memoriesofmurder", {"name_ko": "살인의 추억", "name_en_official": "Memories of Murder",
                                   "name_en_source": "official", "directors": ["Bong Joon-ho"]}),
    ]
    for eid, p in facts:
        asyncio.run(ingest_one("facts", eid, [MockSource("Wikidata", p), MockSource("Wikipedia", p)], db_path=db))


def test_homepage_groups_by_vertical_and_surfaces_people():
    db = tempfile.mktemp(suffix=".db")
    out = tempfile.mktemp(suffix=".html")
    _seed(db)
    asyncio.run(admin.report_html(db_path=db, out_path=out))
    t = open(out, encoding="utf-8").read()
    assert "K-pop artists (1)" in t and "K-dramas (1)" in t and "K-films (2)" in t
    assert "Verified people" in t and "person/bong-joon-ho.html" in t   # the graph hub, on the homepage
    assert "artist/parasite.html" in t                                  # links to the per-entity page
    assert '"@type": "Person"' in t and '"@type": "Movie"' in t          # Schema.org for people + films
    assert 'property="og:title"' in t and 'name="twitter:card"' in t     # social preview meta


def test_entity_and_person_pages_have_social_meta_and_breadcrumb(tmp_path):
    db = tempfile.mktemp(suffix=".db")
    _seed(db)
    out_dir = str(tmp_path / "site")
    asyncio.run(admin.entity_pages(db_path=db, out_dir=out_dir))
    par = (tmp_path / "site" / "artist" / "parasite.html").read_text(encoding="utf-8")
    bong = (tmp_path / "site" / "person" / "bong-joon-ho.html").read_text(encoding="utf-8")
    for page in (par, bong):
        assert 'property="og:title"' in page and 'name="twitter:card"' in page
        assert '"@type": "BreadcrumbList"' in page  # Home > current


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
