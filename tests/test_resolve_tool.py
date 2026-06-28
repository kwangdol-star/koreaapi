"""The `resolve` MCP tool — the ID-spine resolver: a fuzzy NAME, an EXTERNAL ID, or a canonical
entity_id -> THE verified entity (bilingual name + verification + external IDs). Offline."""

from __future__ import annotations

import asyncio
import tempfile

from koreaapi import service
from koreaapi.pipeline.ingest import ingest_one


class _Src:
    is_fallback = False

    def __init__(self, name: str, citation: str, payload: dict) -> None:
        self.name = name
        self._c = citation
        self._p = payload

    async def fetch(self, entity_id: str, kind: str) -> dict:
        return {"payload": self._p, "citation": self._c}


def _seed() -> str:
    db = tempfile.mktemp(suffix=".db")
    p = {"name_ko": "빈센조", "name_en_official": "Vincenzo", "name_en_source": "official", "agency_en": "tvN"}
    asyncio.run(ingest_one("facts", "drama:vincenzo", [
        _Src("Wikidata", "Wikidata Q16741113 2026-06-28 11:00 UTC", p),
        _Src("Wikipedia", "Wikipedia Vincenzo (TV series) 2026-06-28 11:00 UTC", p),
    ], db_path=db))
    return db


def test_resolve_by_korean_name():
    out = asyncio.run(service.resolve("빈센조", db_path=_seed()))
    assert out["found"] and out["id"] == "drama:vincenzo" and out["matched_by"] == "name"
    assert out["name"]["en_official"] == "Vincenzo" and out["content_hash"]
    assert out["ids"]["wikidata"] == "Q16741113"          # external ID surfaced
    assert out["cross_verified"] is True                  # WD + WP agreed


def test_resolve_by_wikidata_id():
    out = asyncio.run(service.resolve("Q16741113", db_path=_seed()))
    assert out["found"] and out["id"] == "drama:vincenzo" and out["matched_by"] == "wikidata"


def test_resolve_by_canonical_id():
    out = asyncio.run(service.resolve("drama:vincenzo", db_path=_seed()))
    assert out["found"] and out["matched_by"] == "entity_id"


def test_resolve_miss_returns_not_found():
    out = asyncio.run(service.resolve("nonexistent xyz", db_path=_seed()))
    assert out["found"] is False


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
