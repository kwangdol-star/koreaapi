"""Reconciliation index (/reconcile.json) — the ID spine: resolve a fuzzy NAME or an EXTERNAL ID to
the canonical KoreaAPI entity, with the bilingual name, external IDs, sameAs, Skill Score, and
content_hash. Offline (custom sources with realistic citations to exercise external-ID parsing)."""

from __future__ import annotations

import asyncio
import json
import tempfile

from koreaapi import admin
from koreaapi.pipeline.ingest import ingest_one


class _Src:
    is_fallback = False

    def __init__(self, name: str, citation: str, payload: dict) -> None:
        self.name = name
        self._c = citation
        self._p = payload

    async def fetch(self, entity_id: str, kind: str) -> dict:
        return {"payload": self._p, "citation": self._c}


def test_reconcile_resolves_name_and_external_id(tmp_path):
    db = tempfile.mktemp(suffix=".db")
    p = {"name_ko": "방탄소년단", "name_en_official": "BTS", "name_en_source": "official",
         "agency_en": "Big Hit Music"}
    asyncio.run(ingest_one("facts", "artist:bts", [
        _Src("Wikidata", "Wikidata Q13580495 2026-06-28 11:00 UTC", p),
        _Src("Wikipedia", "Wikipedia BTS 2026-06-28 11:00 UTC", p),
    ], db_path=db))
    out = str(tmp_path / "reconcile.json")
    asyncio.run(admin.reconcile_json(db_path=db, out_path=out))
    doc = json.load(open(out, encoding="utf-8"))

    assert doc["count"] == 1
    e = doc["entities"][0]
    assert e["id"] == "artist:bts" and e["ko"] == "방탄소년단" and e["en"] == "BTS"
    assert "bts" in e["aliases"] and "방탄소년단" in e["aliases"]    # fuzzy-name match keys
    assert e["ids"]["wikidata"] == "Q13580495"                       # external ID parsed from provenance
    assert e["ids"]["wikipedia"] == "BTS"
    assert e["content_hash"] and isinstance(e["sameAs"], list) and e["sameAs"]
    assert e["url"].endswith("/artist/bts.html")
    assert doc["by_wikidata"]["Q13580495"] == "artist:bts"          # reverse: Wikidata Q-id -> our entity


def test_name_keys_strips_disambiguator():
    from koreaapi import reconcile
    k = reconcile.name_keys("Vincenzo (TV series)", "빈센조", None)
    assert "vincenzo" in k and "vincenzo(tvseries)" in k and "빈센조" in k


def test_match_score_ranks_overlap():
    from koreaapi import reconcile
    assert reconcile.match_score("vincenzo", {"vincenzo"}) == 100        # exact
    assert 0 < reconcile.match_score("vince", {"vincenzo"}) < 100        # partial
    assert reconcile.match_score("zzz", {"vincenzo"}) == 0               # no overlap


def test_reconcile_empty_store_keeps_static_file():
    sentinel = tempfile.mktemp(suffix=".json")
    with open(sentinel, "w", encoding="utf-8") as f:
        f.write("STATIC")
    asyncio.run(admin.reconcile_json(db_path=tempfile.mktemp(suffix=".db"), out_path=sentinel))
    assert open(sentinel, encoding="utf-8").read() == "STATIC"


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
