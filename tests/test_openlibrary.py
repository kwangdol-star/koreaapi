"""Open Library adapter (Phase 2 Tier A: 3rd source for books) — offline. Parse + identity guard are
pure; the live fetch runs on the open network. English-title corroboration + bibliographic attrs; a
title drift misses (never a wrong record), and the source self-filters to book: only."""

from __future__ import annotations

import asyncio

import pytest

from koreaapi.sources.openlibrary import OpenLibrarySource, parse_openlibrary


def _raw(*docs: dict) -> dict:
    return {"docs": list(docs)}


def test_parse_matches_title_and_carries_bibliographic_attrs():
    raw = _raw({"key": "/works/OL1W", "title": "The Vegetarian",
                "author_name": ["Han Kang"], "first_publish_year": 2007})
    p = parse_openlibrary(raw, "The Vegetarian")
    assert p["name_en_official"] == "The Vegetarian" and p["olid"] == "/works/OL1W"
    assert p["attrs"]["Author"] == "Han Kang" and p["attrs"]["First published"] == "2007"
    assert p["name_en_source"] == "official"


def test_parse_skips_unrelated_first_hit_and_walks_to_the_match():
    # first hit shares no name with the query -> skipped; the loop walks to the real match
    raw = _raw({"key": "/works/OLX", "title": "Deep Learning"},
               {"key": "/works/OL9W", "title": "Almond"})
    p = parse_openlibrary(raw, "Almond")
    assert p["olid"] == "/works/OL9W"


def test_parse_rejects_drift():
    with pytest.raises(ValueError, match="no work matches"):
        parse_openlibrary(_raw({"key": "/works/OLZ", "title": "Something Unrelated"}), "Pachinko")
    with pytest.raises(ValueError, match="no work matches"):
        parse_openlibrary({"docs": []}, "Pachinko")


def test_source_self_filters_to_books():
    with pytest.raises(ValueError, match="books only"):
        asyncio.run(OpenLibrarySource().fetch("artist:bts", "facts"))


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
