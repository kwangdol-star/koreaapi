"""Offline tests for the Wikidata identity guard (the "Arborka" defense).

A curated anchor (e.g. artist:bts = Q484203) carries its known identity, so `fetch()`
must REJECT a response whose label contradicts it (invariant 2: no unverifiable data
ships). These run fully offline: parse + verify on fixtures, and fetch/ingest with the
HTTP call monkeypatched - proving the poisoned payload never reaches the append-only
store. `wikidata_poisoned_bts.json` is the exact bad payload that surfaced the gap.

Run:  PYTHONPATH=src python -m pytest tests/test_wikidata_verify.py -q
"""

from __future__ import annotations

import asyncio
import json
import pathlib

import pytest

from koreaapi.pipeline import store
from koreaapi.pipeline.ingest import ingest_one
from koreaapi.sources.wikidata import (
    WikidataSource,
    _CURATED,
    _verify_identity,
    parse_entity,
)

FIX = pathlib.Path(__file__).parent / "fixtures"
GOOD = json.loads((FIX / "wikidata_bts.json").read_text(encoding="utf-8"))
POISON = json.loads((FIX / "wikidata_poisoned_bts.json").read_text(encoding="utf-8"))


def test_verify_accepts_real_bts():
    _verify_identity(parse_entity(GOOD, "artist:bts", "facts"), _CURATED["artist:bts"])


def test_verify_rejects_poisoned_label():
    payload = parse_entity(POISON, "artist:bts", "facts")
    assert payload["name_en_official"] == "Arborka"  # parser stays faithful to the bytes...
    with pytest.raises(ValueError, match="identity mismatch"):  # ...the guard rejects it
        _verify_identity(payload, _CURATED["artist:bts"])


def test_fetch_rejects_poisoned_response(monkeypatch):
    src = WikidataSource()
    monkeypatch.setattr(src, "_http_get", lambda url: POISON)  # no network; curated qid
    with pytest.raises(ValueError, match="identity mismatch"):
        asyncio.run(src.fetch("artist:bts", "facts"))


def test_ingest_does_not_poison_store(monkeypatch, tmp_path):
    src = WikidataSource()
    monkeypatch.setattr(src, "_http_get", lambda url: POISON)
    db = str(tmp_path / "t.db")

    rec = asyncio.run(ingest_one("facts", "artist:bts", [src], db_path=db))

    assert rec is None  # poisoned single source dropped by graceful degradation
    assert asyncio.run(store.count("artist:bts", "facts", db_path=db)) == 0  # nothing appended


if __name__ == "__main__":
    test_verify_accepts_real_bts()
    test_verify_rejects_poisoned_label()
    print("wikidata identity-guard tests passed (run pytest for monkeypatch cases)")
