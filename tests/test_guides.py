"""Region GUIDE pages — the trip-plan decision as a crawlable, cited GEO asset. A region with >=3
verified geo spots gets /guide-<region>.html (every spot links to its verified entity page, with
ItemList + FAQPage JSON-LD); a thin region gets none; a /guides.html index is always written so the
homepage 'Guides' pill never 404s. The exact guide set is shared with the sitemap (no phantom URL)."""

from __future__ import annotations

import asyncio
import tempfile

from koreaapi import admin
from koreaapi.pipeline.ingest import ingest_one
from koreaapi.sources.mock import MockSource


def _ingest(db: str, eid: str, ko: str, en: str, *, region: str | None = None) -> None:
    p = {"name_ko": ko, "name_en_official": en, "name_en_source": "official"}
    if region:
        p["agency_en"] = region  # located-in region (P131) — the guide's grouping edge
    asyncio.run(ingest_one("facts", eid, [MockSource("Wikidata", p), MockSource("Wikipedia", p)], db_path=db))


def test_region_guide_generates_for_a_covered_region(tmp_path):
    db = tempfile.mktemp(suffix=".db")
    for eid, ko, en in [("place:haeundae", "해운대", "Haeundae"),
                        ("beach:gwangalli", "광안리해수욕장", "Gwangalli Beach"),
                        ("temple:beomeosa", "범어사", "Beomeosa")]:
        _ingest(db, eid, ko, en, region="Busan")
    _ingest(db, "festival:biff", "부산국제영화제", "Busan International Film Festival", region="Busan")
    _ingest(db, "place:gyeongbokgung", "경복궁", "Gyeongbokgung", region="Seoul")  # only 1 in Seoul

    out_dir = str(tmp_path / "site")
    res = asyncio.run(admin.entity_pages(db_path=db, out_dir=out_dir))
    guides = {g["slug"]: g for g in res["guides"]}
    assert "busan" in guides and guides["busan"]["count"] == 3
    assert "seoul" not in guides                        # <3 verified spots -> no thin page

    page = (tmp_path / "site" / "guide-busan.html").read_text(encoding="utf-8")
    assert "artist/haeundae.html" in page and "artist/beomeosa.html" in page   # links to verified pages
    assert "artist/biff.html" in page                                          # festival listed
    assert '"@type": "ItemList"' in page and '"@type": "FAQPage"' in page       # crawlable structured data
    assert "Busan" in page and "None" not in page                              # region named, no None-leak

    idx = (tmp_path / "site" / "guides.html").read_text(encoding="utf-8")
    assert "guide-busan.html" in idx                    # the index links the guide

    sm = tempfile.mktemp(suffix=".xml")
    asyncio.run(admin.sitemap(db_path=db, out_path=sm))
    smt = open(sm, encoding="utf-8").read()
    assert "/guide-busan.html" in smt and "/guides.html" in smt   # sitemap ⊇ the exact guide set


def test_food_guide_pages_generate_and_label_editorial_tags(tmp_path, monkeypatch):
    # Tags live in the roster; patch them so the test is deterministic (not tied to roster values).
    monkeypatch.setattr(admin, "FOOD_VEG", {"food:japchae": "vegetarian", "food:kimchi": "vegan",
                                            "food:bulgogi": "contains meat", "food:hoe": "contains seafood"})
    monkeypatch.setattr(admin, "FOOD_SPICE", {"food:japchae": "mild", "food:kimchi": "mild",
                                              "food:bulgogi": "mild", "food:hoe": "none"})
    db = tempfile.mktemp(suffix=".db")
    for eid, ko, en in [("food:japchae", "잡채", "Japchae"), ("food:kimchi", "김치", "Kimchi"),
                        ("food:bulgogi", "불고기", "Bulgogi"), ("food:hoe", "회", "Hoe")]:
        _ingest(db, eid, ko, en)

    out_dir = str(tmp_path / "site")
    res = asyncio.run(admin.entity_pages(db_path=db, out_dir=out_dir))
    fg = {g["slug"]: g for g in res["food_guides"]}
    assert "vegetarian" in fg              # japchae (vegetarian) + kimchi (vegan⊂vegetarian) -> 2 dishes

    veg = (tmp_path / "site" / "food-vegetarian.html").read_text(encoding="utf-8")
    assert "artist/japchae.html" in veg and "artist/kimchi.html" in veg
    assert "artist/bulgogi.html" not in veg and "artist/hoe.html" not in veg   # meat + seafood excluded
    assert "editorial" in veg.lower()                                          # tags labeled, not verified
    assert '"@type": "ItemList"' in veg and '"@type": "FAQPage"' in veg and "None" not in veg

    idx = (tmp_path / "site" / "guides.html").read_text(encoding="utf-8")
    assert "food-vegetarian.html" in idx and "By diet" in idx                  # index links the food guide
    sm = tempfile.mktemp(suffix=".xml")
    asyncio.run(admin.sitemap(db_path=db, out_path=sm))
    assert "/food-vegetarian.html" in open(sm, encoding="utf-8").read()        # sitemap ⊇ the food set


def test_guides_index_written_even_with_no_regions(tmp_path):
    db = tempfile.mktemp(suffix=".db")
    _ingest(db, "artist:bts", "방탄소년단", "BTS")       # no geo entities -> no guides
    out_dir = str(tmp_path / "site")
    res = asyncio.run(admin.entity_pages(db_path=db, out_dir=out_dir))
    assert res["guides"] == []
    assert (tmp_path / "site" / "guides.html").exists()  # index still written (homepage pill never 404s)


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
