"""/llms.txt is generated LIVE from the verified store (the agent-discoverable AEO index).

The prose is stable; the Coverage section must reflect the ACTUAL roster (counts by vertical) and
the person graph, and point crawlers at the per-entity/per-person pages + sitemap. A blocked pull
(empty store) must leave the committed static file untouched rather than zero out coverage.
"""

from __future__ import annotations

import asyncio
import os
import tempfile

from koreaapi import admin
from koreaapi.pipeline.ingest import ingest_one
from koreaapi.sources.mock import MockSource


def _sources(payload: dict) -> list:
    return [MockSource("Wikidata", payload), MockSource("Wikipedia", payload)]  # agree -> cross-verified


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
        asyncio.run(ingest_one("facts", eid, _sources(p), db_path=db))


def test_llms_coverage_reflects_live_roster_and_graph():
    db = tempfile.mktemp(suffix=".db")
    out = tempfile.mktemp(suffix=".txt")
    _seed(db)
    asyncio.run(admin.llms_txt(db_path=db, out_path=out))
    text = open(out, encoding="utf-8").read()
    assert "## Coverage (live" in text
    assert "1 artists, 1 K-dramas, 2 K-films" in text   # counts by vertical
    assert "Bong Joon-ho" not in text                   # people are summarized as a COUNT, not listed
    assert "1 verified people" in text                  # Bong directed 2 films -> 1 qualifying hub
    assert "BTS" in text and "Squid Game" in text and "Parasite" in text  # vertical samples
    assert "/person/<slug>.html" in text and "/sitemap.xml" in text       # discovery pointers


def test_llms_empty_store_keeps_static_file():
    # A blocked pull (empty store) must NOT overwrite the committed static llms.txt with zeros.
    sentinel = tempfile.mktemp(suffix=".txt")
    with open(sentinel, "w", encoding="utf-8") as f:
        f.write("STATIC-FALLBACK")
    asyncio.run(admin.llms_txt(db_path=tempfile.mktemp(suffix=".db"), out_path=sentinel))
    assert open(sentinel, encoding="utf-8").read() == "STATIC-FALLBACK"
    os.remove(sentinel)


def test_llms_full_corpus_has_every_entity_block_with_cite_and_url():
    db = tempfile.mktemp(suffix=".db")
    out = tempfile.mktemp(suffix=".txt")
    _seed(db)
    asyncio.run(admin.llms_full_txt(db_path=db, out_path=out))
    text = open(out, encoding="utf-8").read()
    assert "full verified corpus" in text.lower()
    # every seeded entity appears as its own bilingual block ...
    for en, ko in [("BTS", "방탄소년단"), ("Squid Game", "오징어 게임"), ("Parasite", "기생충")]:
        assert f"### {en} — {ko}" in text
    # ... grouped by vertical, each with a Skill Score, a ready Cite line, and the canonical URL
    assert "## K-films (2)" in text
    assert "Verified: Skill" in text and "via KoreaAPI" in text
    assert "/artist/parasite.html" in text


def test_llms_full_empty_store_keeps_static_file():
    # A blocked pull (empty store) must NOT overwrite the committed static llms-full.txt with zeros.
    sentinel = tempfile.mktemp(suffix=".txt")
    with open(sentinel, "w", encoding="utf-8") as f:
        f.write("STATIC-FALLBACK")
    asyncio.run(admin.llms_full_txt(db_path=tempfile.mktemp(suffix=".db"), out_path=sentinel))
    assert open(sentinel, encoding="utf-8").read() == "STATIC-FALLBACK"
    os.remove(sentinel)


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
