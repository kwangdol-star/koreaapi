"""Freshness feeds — RSS 2.0 (/feed.xml) + JSON Feed 1.1 (/feed.json) over the most recently verified
entities. A freshness signal for answer engines/crawlers + a subscribe surface. Offline (seeded DB)."""

from __future__ import annotations

import asyncio
import json
import tempfile

from koreaapi import admin
from koreaapi.pipeline.ingest import ingest_one
from koreaapi.sources.mock import MockSource


def _seed(db: str) -> None:
    for eid, p in [
        ("artist:bts", {"name_ko": "방탄소년단", "name_en_official": "BTS", "name_en_source": "official"}),
        ("drama:squidgame", {"name_ko": "오징어 게임", "name_en_official": "Squid Game", "name_en_source": "official"}),
    ]:
        asyncio.run(ingest_one("facts", eid, [MockSource("Wikidata", p), MockSource("Wikipedia", p)], db_path=db))


def test_feed_xml_lists_recent_verified():
    db, out = tempfile.mktemp(suffix=".db"), tempfile.mktemp(suffix=".xml")
    _seed(db)
    asyncio.run(admin.feed_xml(db_path=db, out_path=out))
    text = open(out, encoding="utf-8").read()
    assert text.startswith("<?xml") and '<rss version="2.0"' in text
    assert "<title>KoreaAPI — recently verified</title>" in text
    assert "BTS" in text and "Squid Game" in text
    assert "<pubDate>" in text and "/artist/bts.html" in text   # item link -> entity page
    assert 'rel="self"' in text                                  # atom self link (valid feed)


def test_feed_json_is_valid_jsonfeed():
    db, out = tempfile.mktemp(suffix=".db"), tempfile.mktemp(suffix=".json")
    _seed(db)
    asyncio.run(admin.feed_json(db_path=db, out_path=out))
    feed = json.load(open(out, encoding="utf-8"))
    assert feed["version"].startswith("https://jsonfeed.org/version/1.1")
    titles = [it["title"] for it in feed["items"]]
    assert any("BTS" in t for t in titles) and any("Squid Game" in t for t in titles)
    it = feed["items"][0]
    assert it["url"].endswith(".html") and it["date_published"].endswith("Z")
    assert "skill_score" in it["_koreaapi"] and "sources" in it["_koreaapi"]


def test_feed_empty_store_keeps_static_files():
    # a blocked pull (empty store) must NOT overwrite the committed static feed files with empties
    for fn in (admin.feed_xml, admin.feed_json):
        sentinel = tempfile.mktemp(suffix=".out")
        with open(sentinel, "w", encoding="utf-8") as f:
            f.write("STATIC")
        asyncio.run(fn(db_path=tempfile.mktemp(suffix=".db"), out_path=sentinel))
        assert open(sentinel, encoding="utf-8").read() == "STATIC"


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
