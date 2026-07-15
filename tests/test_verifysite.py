"""Pre-deploy gate (admin.verify_site) + the custom 404. verifysite validates the ASSEMBLED site dir
right before upload, so a generator regression or a lost DB cache fails the build loudly — GitHub Pages
then keeps serving the previous good deployment (freeze beats broken). Offline over a real build."""

from __future__ import annotations

import asyncio
import os
import tempfile

from koreaapi import admin
from koreaapi.pipeline.ingest import ingest_one
from koreaapi.sources.mock import MockSource


def _build(tmp_path) -> str:
    db = tempfile.mktemp(suffix=".db")
    for eid, ko, en in [("artist:bts", "방탄소년단", "BTS"), ("place:gyeongbokgung", "경복궁", "Gyeongbokgung")]:
        p = {"name_ko": ko, "name_en_official": en, "name_en_source": "official"}
        asyncio.run(ingest_one("facts", eid, [MockSource("Wikidata", p), MockSource("Wikipedia", p)],
                               db_path=db))
    site = str(tmp_path / "site")
    asyncio.run(admin.entity_pages(db_path=db, out_dir=site))
    asyncio.run(admin.report_html(db_path=db, out_path=os.path.join(site, "index.html")))
    asyncio.run(admin.sitemap(db_path=db, out_path=os.path.join(site, "sitemap.xml")))
    asyncio.run(admin.llms_txt(db_path=db, out_path=os.path.join(site, "llms.txt")))
    asyncio.run(admin.llms_full_txt(db_path=db, out_path=os.path.join(site, "llms-full.txt")))
    asyncio.run(admin.reconcile_json(db_path=db, out_path=os.path.join(site, "reconcile.json")))
    asyncio.run(admin.status_json(db_path=db, out_path=os.path.join(site, "status.json")))
    return site


def test_verify_site_passes_a_complete_build(tmp_path):
    site = _build(tmp_path)
    out = admin.verify_site(site, min_entities=2)
    assert out["ok"], out["failures"]
    assert out["stats"]["search_entries"] >= 2 and out["stats"]["sitemap_urls"] >= 2


def test_verify_site_fails_loudly_on_a_broken_build(tmp_path):
    site = _build(tmp_path)
    os.remove(os.path.join(site, "search-index.json"))              # a generator regression
    out = admin.verify_site(site, min_entities=2)
    assert not out["ok"] and any("search-index.json" in f for f in out["failures"])
    thin = admin.verify_site(site, min_entities=9999)               # skeleton build (lost DB cache)
    assert not thin["ok"] and any("entity pages" in f for f in thin["failures"])


def test_pages_workflow_gates_the_deploy():
    wf = open("/home/user/koreaapi-build/.github/workflows/pages.yml", encoding="utf-8").read()
    assert "koreaapi.admin verifysite _site" in wf                   # the gate runs before upload
    assert wf.index("verifysite _site") < wf.index("upload-pages-artifact")


def test_custom_404_recovers_into_search(tmp_path):
    site = _build(tmp_path)
    t = open(os.path.join(site, "404.html"), encoding="utf-8").read()
    assert "noindex" in t                                            # a 404 must not be indexed
    assert 'href="/search.html"' in t and 'href="/guides.html"' in t  # root-absolute: works at any depth
    assert 'hreflang' not in t                                       # no hreflang-to-nowhere on a 404


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
