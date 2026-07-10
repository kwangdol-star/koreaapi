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
    # root-authority markup: an enriched Dataset (with downloads) + WebSite + Organization nodes
    assert '"@type": "Dataset"' in t and '"@type": "DataDownload"' in t
    assert '"@type": "WebSite"' in t and '"@type": "Organization"' in t


def test_homepage_caps_sections_to_a_preview():
    # The homepage is a PREVIEW: each vertical section caps its rows and links to the full hub, so
    # 5000+ entities don't stutter the browser (the complete crawlable list lives on /<vertical>.html).
    import re
    db = tempfile.mktemp(suffix=".db")
    for i in range(20):
        p = {"name_ko": f"가수{i}", "name_en_official": f"Artist {i:02d}", "name_en_source": "official"}
        asyncio.run(ingest_one("facts", f"artist:test{i:02d}",
                               [MockSource("Wikidata", p), MockSource("Wikipedia", p)], db_path=db))
    out = tempfile.mktemp(suffix=".html")
    asyncio.run(admin.report_html(db_path=db, out_path=out))
    t = open(out, encoding="utf-8").read()
    assert len(re.findall(r"artist/test\d\d\.html", t)) == 18   # capped preview (not all 20)
    assert "see all 20" in t and "./artists.html" in t          # links to the full hub


def test_entity_page_has_embeddable_verified_badge(tmp_path):
    # The citation flywheel as a viral artifact: a static SVG badge per entity + a copy-paste embed
    # snippet on the page (backlink + via-KoreaAPI mark that spreads the citation standard).
    import os
    db = tempfile.mktemp(suffix=".db")
    _seed(db)
    out_dir = str(tmp_path / "site")
    asyncio.run(admin.entity_pages(db_path=db, out_dir=out_dir))
    assert os.path.exists(os.path.join(out_dir, "badge", "parasite.svg"))   # static badge written
    svg = open(os.path.join(out_dir, "badge", "parasite.svg"), encoding="utf-8").read()
    assert svg.startswith("<svg") and "KoreaAPI" in svg
    page = (tmp_path / "site" / "artist" / "parasite.html").read_text(encoding="utf-8")
    assert "Verified badge" in page and "/badge/parasite.svg" in page       # inline + embed snippet


def test_entity_and_person_pages_have_social_meta_and_breadcrumb(tmp_path):
    db = tempfile.mktemp(suffix=".db")
    _seed(db)
    out_dir = str(tmp_path / "site")
    asyncio.run(admin.entity_pages(db_path=db, out_dir=out_dir))
    par = (tmp_path / "site" / "artist" / "parasite.html").read_text(encoding="utf-8")
    bong = (tmp_path / "site" / "person" / "bong-joon-ho.html").read_text(encoding="utf-8")
    for page in (par, bong):
        assert 'property="og:title"' in page and 'name="twitter:card"' in page
        assert '"@type": "BreadcrumbList"' in page  # Home > vertical > current
    assert "/films.html" in par   # entity breadcrumb middle points at the vertical hub (3-level)


def _label_seed(db: str) -> None:
    facts = [
        ("artist:bts", {"name_ko": "방탄소년단", "name_en_official": "BTS",
                        "name_en_source": "official", "agency_en": "Big Hit Music"}),
        ("artist:txt", {"name_ko": "투모로우바이투게더", "name_en_official": "Tomorrow X Together",
                        "name_en_source": "official", "agency_en": "Big Hit Music"}),
        ("artist:aespa", {"name_ko": "에스파", "name_en_official": "aespa",
                          "name_en_source": "official", "agency_en": "SM Entertainment"}),  # only 1 -> no page
    ]
    for eid, p in facts:
        asyncio.run(ingest_one("facts", eid, [MockSource("Wikidata", p), MockSource("Wikipedia", p)], db_path=db))


def test_label_hub_pages_and_crosslinks(tmp_path):
    db = tempfile.mktemp(suffix=".db")
    _label_seed(db)
    out_dir = str(tmp_path / "site")
    res = asyncio.run(admin.entity_pages(db_path=db, out_dir=out_dir))
    # a label with >=2 entities gets a hub; a single-artist label (SM) does not
    names = {L["name"]: L["count"] for L in res["labels"]}
    assert names == {"Big Hit Music": 2}
    page = (tmp_path / "site" / "label" / "big-hit-music.html").read_text(encoding="utf-8")
    assert "../artist/bts.html" in page and "../artist/txt.html" in page  # lists its roster
    assert '"@type": "Organization"' in page and '"@type": "ItemList"' in page
    bts = (tmp_path / "site" / "artist" / "bts.html").read_text(encoding="utf-8")
    assert "../label/big-hit-music.html" in bts  # entity links to its label hub
    sm = tempfile.mktemp(suffix=".xml")
    asyncio.run(admin.sitemap(db_path=db, out_path=sm))
    assert "/label/big-hit-music.html" in open(sm, encoding="utf-8").read()


def test_vertical_hub_pages_with_itemlist(tmp_path):
    db = tempfile.mktemp(suffix=".db")
    _seed(db)
    out_dir = str(tmp_path / "site")
    res = asyncio.run(admin.entity_pages(db_path=db, out_dir=out_dir))
    assert {h["vertical"] for h in res["hubs"]} == {"artist", "drama", "film", "webtoon", "place",
                                                    "food", "company", "brand", "book", "history",
                                                    "heritage", "folklore", "medical", "region",
                                                    "game", "show", "animation", "university",
                                                    "classic", "fashion", "festival", "award", "holiday",
                                                    "liquor", "park", "museum", "temple", "venue", "people", "sports",
                                                    "actor", "song", "concept"}
    films = (tmp_path / "site" / "films.html").read_text(encoding="utf-8")
    assert '"@type": "ItemList"' in films and '"@type": "BreadcrumbList"' in films
    assert "artist/parasite.html" in films          # hub links into the per-entity pages
    people = (tmp_path / "site" / "people.html").read_text(encoding="utf-8")
    assert "person/bong-joon-ho.html" in people and '"@type": "ItemList"' in people
    sm = tempfile.mktemp(suffix=".xml")
    asyncio.run(admin.sitemap(db_path=db, out_path=sm))
    smt = open(sm, encoding="utf-8").read()
    assert all(f"/{f}" in smt for f in ("artists.html", "dramas.html", "films.html", "people.html"))


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
