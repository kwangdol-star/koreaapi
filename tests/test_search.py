"""Client-side site search — /search-index.json (slim name index: ko · en · romanized · grounded
aliases) + /search.html (+ /ko/) that filters it in-browser. Zero backend (static GEO host); the
index doubles as a lightweight machine name-lookup. Built by entity_pages; copied explicitly by the
Pages workflow (the *.html glob misses .json)."""

from __future__ import annotations

import asyncio
import json
import tempfile

from koreaapi import admin
from koreaapi.pipeline.ingest import ingest_one
from koreaapi.sources.mock import MockSource


def _seed(db: str) -> None:
    for eid, p in [
        ("artist:bts", {"name_ko": "방탄소년단", "name_en_official": "BTS",
                        "name_romanized": "Bangtan Sonyeondan", "name_en_source": "official"}),
        ("place:gyeongbokgung", {"name_ko": "경복궁", "name_en_official": "Gyeongbokgung",
                                 "name_en_source": "official", "aliases": ["Gyeongbok Palace"]}),
    ]:
        asyncio.run(ingest_one("facts", eid, [MockSource("Wikidata", p), MockSource("Wikipedia", p)],
                               db_path=db))


def test_search_index_and_pages_are_written(tmp_path):
    db = tempfile.mktemp(suffix=".db")
    _seed(db)
    out_dir = str(tmp_path / "site")
    res = asyncio.run(admin.entity_pages(db_path=db, out_dir=out_dir))
    assert res["search_index"] == 2

    idx = json.load(open(tmp_path / "site" / "search-index.json", encoding="utf-8"))
    by_slug = {e["s"]: e for e in idx}
    assert by_slug["bts"]["ko"] == "방탄소년단" and by_slug["bts"]["en"] == "BTS"
    assert by_slug["bts"]["r"] == "Bangtan Sonyeondan"          # romanized searchable
    assert "Gyeongbok Palace" in by_slug["gyeongbokgung"]["a"]  # grounded alias widens search recall
    assert all(e["k"] for e in idx)                              # kind carried for the result label

    en = (tmp_path / "site" / "search.html").read_text(encoding="utf-8")
    assert "search-index.json" in en and 'id=q' in en            # the page fetches the index, has the box
    assert "artist/" in en and "BASE=''" in en                   # results link into entity pages, root-based
    ko = (tmp_path / "site" / "ko" / "search.html").read_text(encoding="utf-8")
    assert 'lang="ko"' in ko and "BASE='../'" in ko              # Korean twin fetches the ROOT index (../)
    assert "search-index.json" in ko

    sm = tempfile.mktemp(suffix=".xml")
    asyncio.run(admin.sitemap(db_path=db, out_path=sm))
    smt = open(sm, encoding="utf-8").read()
    assert "/search.html" in smt and "/ko/search.html" in smt


def test_pages_workflow_copies_the_search_index():
    # The deploy copies site/*.html by glob — a .json at site root must be copied explicitly, or search
    # 404s in production while passing every offline test. Guard the workflow line itself.
    wf = open("/home/user/koreaapi-build/.github/workflows/pages.yml", encoding="utf-8").read()
    assert "cp site/search-index.json _site/" in wf


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
