"""Tamper-evident integrity: a STABLE per-record fingerprint, an order-independent dataset hash, an
append-only hash chain, and the /integrity.json manifest export() publishes. This turns the
"verifiable" claim into a property anyone can recompute. Offline."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile

from koreaapi import admin, integrity
from koreaapi.pipeline.ingest import ingest_one
from koreaapi.sources.mock import MockSource


def _rec() -> dict:
    return {"entity_id": "artist:bts", "kind": "facts",
            "name": {"ko": "방탄소년단", "en_official": "BTS", "romanized": None},
            "summary_en": "x", "summary_ko": "y", "data": {"agency_en": "Big Hit"},
            "provenance": {"skill_score": 0.9, "agreeing_sources": 2,
                           "sources": ["Wikidata Q1 2026-06-28 11:00 UTC",
                                       "Wikipedia BTS 2026-06-28 11:00 UTC"]}}


def test_fingerprint_stable_across_fetch_timestamps_but_changes_on_content():
    a = integrity.record_fingerprint(_rec())
    # same content, different fetch timestamps -> SAME fingerprint (the verified facts didn't change)
    b = _rec()
    b["provenance"]["sources"] = ["Wikidata Q1 2030-01-01 09:00 UTC", "Wikipedia BTS 2030-01-01 09:00 UTC"]
    assert integrity.record_fingerprint(b) == a
    # an already-present content_hash field is ignored (no self-reference)
    c = _rec()
    c["content_hash"] = "deadbeef"
    assert integrity.record_fingerprint(c) == a
    # a changed verified fact -> DIFFERENT fingerprint
    d = _rec()
    d["data"]["agency_en"] = "Other"
    assert integrity.record_fingerprint(d) != a


def test_dataset_hash_is_order_independent():
    r1 = {"entity_id": "a", "kind": "facts", "name": {}, "provenance": {"sources": []}}
    r2 = {"entity_id": "b", "kind": "facts", "name": {}, "provenance": {"sources": []}}
    assert integrity.dataset_hash([r1, r2]) == integrity.dataset_hash([r2, r1])
    assert integrity.dataset_hash([r1]) != integrity.dataset_hash([r1, r2])


def test_chain_detects_tampering_and_extension(tmp_path):
    p = tmp_path / "snap.jsonl"
    p.write_text('{"a":1}\n{"a":2}\n{"a":3}\n', encoding="utf-8")
    h1, n = integrity.chain_head(str(p))
    assert n == 3 and h1
    p.write_text('{"a":1}\n{"a":99}\n{"a":3}\n', encoding="utf-8")   # tamper a PAST line
    assert integrity.chain_head(str(p))[0] != h1                      # -> head changes (detectable)
    p.write_text('{"a":1}\n{"a":2}\n{"a":3}\n{"a":4}\n', encoding="utf-8")  # append-only extension
    h3, n3 = integrity.chain_head(str(p))
    assert n3 == 4 and h3 != h1
    assert integrity.chain_head(str(tmp_path / "missing.jsonl")) == (None, 0)


def test_export_writes_manifest_and_reproducible_dataset_hash(tmp_path):
    db = tempfile.mktemp(suffix=".db")
    p = {"name_ko": "방탄소년단", "name_en_official": "BTS", "name_en_source": "official",
         "agency_en": "Big Hit Music"}
    asyncio.run(ingest_one("facts", "artist:bts",
                           [MockSource("Wikidata", p), MockSource("Wikipedia", p)], db_path=db))
    out = str(tmp_path / "data")
    res = asyncio.run(admin.export(db_path=db, out_dir=out))
    man = json.load(open(os.path.join(out, "integrity.json"), encoding="utf-8"))
    assert man["algorithm"] == "sha256" and man["dataset_hash"] and man["chain_head"]
    assert man["entities"] == 1 and man["snapshots"] >= 1
    latest = json.load(open(os.path.join(out, "latest.json"), encoding="utf-8"))
    assert latest and all("content_hash" in r for r in latest)
    # the published dataset_hash is REPRODUCIBLE from latest.json (the verifiability claim, checkable)
    assert integrity.dataset_hash(latest) == man["dataset_hash"] == res["dataset_hash"]
    # each record's published content_hash matches a fresh recomputation
    assert all(r["content_hash"] == integrity.record_fingerprint(r) for r in latest)


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
