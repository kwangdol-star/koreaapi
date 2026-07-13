"""Offline tests for LLM enrichment (grounded facts + aliases from the Wikipedia lead).

The PARSE (LLM reply -> dict) and GROUND (anti-hallucination gate) steps are pure and fully
tested; the live LLM call is best-effort and validated on a GitHub run (egress-blocked here), so
it is not exercised offline. At ingest, enrichment GAP-FILLS attrs (never overrides a structured
source) and adds grounded aliases — both via the (here monkeypatched) enricher.

Run:  PYTHONPATH=src python -m pytest tests/test_enrich.py -q
"""

from __future__ import annotations

import asyncio
import os
import tempfile

from koreaapi import enrich as emod
from koreaapi.enrich import enrich, ground_enrichment, parse_enrichment
from koreaapi.pipeline import ingest
from koreaapi.sources.mock import MockSource

_ABSTRACT = ("Seoul Arts Center (SAC, 예술의전당) is a performing-arts complex in Seoul, "
             "South Korea. It was founded in 1988 and opened fully in 1993.")


def _tmp_db() -> str:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(path)
    return path


def test_enrich_returns_empty_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert enrich(_ABSTRACT) == {"attrs": {}, "aliases": []}
    assert enrich(None) == {"attrs": {}, "aliases": []}
    assert enrich("   ") == {"attrs": {}, "aliases": []}


def test_parse_enrichment_is_tolerant():
    reply = ('Sure! ```json\n{"attrs": {"Founded": "1988", "Bad": null, "Opened": 1993}, '
             '"aliases": ["SAC", 7, "예술의전당"]}\n``` done')
    p = parse_enrichment(reply)
    assert p["attrs"] == {"Founded": "1988", "Opened": "1993"}  # null dropped; number coerced to str
    assert p["aliases"] == ["SAC", "예술의전당"]                 # non-string alias dropped


def test_parse_enrichment_garbage_returns_empty():
    assert parse_enrichment("no json at all") == {"attrs": {}, "aliases": []}
    assert parse_enrichment("{not valid json}") == {"attrs": {}, "aliases": []}


def test_ground_rejects_hallucinations_and_gapfills():
    parsed = {"attrs": {"Founded": "1988", "Location": "Seoul", "Capacity": "9999"},
              "aliases": ["SAC", "예술의전당", "Made Up Name"]}
    out = ground_enrichment(parsed, _ABSTRACT,
                            existing_keys=("Location",),          # already carried -> gap-fill skips it
                            known_names=("Seoul Arts Center",))
    # Founded=1988 is literally in the text -> kept. Location excluded (existing). Capacity 9999 NOT
    # in the text -> dropped (hallucination gate).
    assert out["attrs"] == {"Founded": "1988"}
    # SAC + 예술의전당 are literally in the text -> kept; 'Made Up Name' isn't -> dropped.
    assert out["aliases"] == ["SAC", "예술의전당"]


def test_ground_caps_apply():
    parsed = {"attrs": {f"K{i}": "1988" for i in range(20)}, "aliases": ["SAC"] * 20}
    out = ground_enrichment(parsed, _ABSTRACT)
    assert len(out["attrs"]) <= 6 and len(out["aliases"]) <= 4


def test_ingest_gapfills_attrs_and_adds_aliases(monkeypatch):
    monkeypatch.setattr(ingest, "enrich",
                        lambda abstract, existing_keys=(), known_names=(): {
                            "attrs": {"Founded": "1988"}, "aliases": ["SAC"]})
    payload = {"name_ko": "예술의전당", "name_en_official": "Seoul Arts Center",
               "name_en_source": "official", "summary_en": "x",
               "abstract_en": _ABSTRACT, "attrs": {"Genre": "opera"}}
    rec = asyncio.run(
        ingest.ingest_one("facts", "theater:sac", [MockSource("Wikidata", payload)], db_path=_tmp_db())
    )
    assert rec.data["attrs"]["Genre"] == "opera"    # the structured-source attr is preserved
    assert rec.data["attrs"]["Founded"] == "1988"   # gap-filled from grounded enrichment
    assert rec.data["aliases"] == ["SAC"]


def test_ingest_enrich_never_overrides_a_structured_attr(monkeypatch):
    # Even if the enricher returns a key that already exists, gap-fill (setdefault) keeps the
    # cross-verified structured value — "verification over trust".
    monkeypatch.setattr(ingest, "enrich",
                        lambda abstract, existing_keys=(), known_names=(): {
                            "attrs": {"Genre": "WRONG"}, "aliases": []})
    payload = {"name_ko": "예술의전당", "name_en_official": "Seoul Arts Center",
               "name_en_source": "official", "summary_en": "x",
               "abstract_en": _ABSTRACT, "attrs": {"Genre": "opera"}}
    rec = asyncio.run(
        ingest.ingest_one("facts", "theater:sac", [MockSource("Wikidata", payload)], db_path=_tmp_db())
    )
    assert rec.data["attrs"]["Genre"] == "opera"


def test_ingest_skips_enrich_without_an_abstract(monkeypatch):
    calls = {"n": 0}

    def fake(abstract, existing_keys=(), known_names=()):
        calls["n"] += 1
        return {"attrs": {}, "aliases": []}

    monkeypatch.setattr(ingest, "enrich", fake)
    payload = {"name_ko": "방탄소년단", "name_en_official": "BTS", "summary_en": "x"}  # no abstract_en
    asyncio.run(
        ingest.ingest_one("facts", "artist:bts", [MockSource("Wikidata", payload)], db_path=_tmp_db())
    )
    assert calls["n"] == 0  # no abstract -> no LLM call


def test_ingested_alias_resolves_via_the_resolve_tool(monkeypatch):
    # The payoff: a grounded alias from the abstract widens recall — an agent that queries the
    # alternate name still maps onto the canonical verified entity.
    from koreaapi import service

    monkeypatch.setattr(ingest, "enrich",
                        lambda abstract, existing_keys=(), known_names=(): {
                            "attrs": {}, "aliases": ["SAC"]})
    db = _tmp_db()
    payload = {"name_ko": "예술의전당", "name_en_official": "Seoul Arts Center",
               "name_en_source": "official", "summary_en": "x", "abstract_en": _ABSTRACT}
    asyncio.run(
        ingest.ingest_one("facts", "theater:sac", [MockSource("Wikidata", payload)], db_path=db)
    )
    r = asyncio.run(service.resolve("SAC", db_path=db))
    assert r["found"] and r["id"] == "theater:sac" and r["matched_by"] == "name"


def test_ingest_enrich_runs_once_then_carries_forward(monkeypatch):
    calls = {"n": 0}

    def fake(abstract, existing_keys=(), known_names=()):
        calls["n"] += 1
        return {"attrs": {"Founded": "1988"}, "aliases": ["SAC"]}

    monkeypatch.setattr(ingest, "enrich", fake)
    db = _tmp_db()
    payload = {"name_ko": "예술의전당", "name_en_official": "Seoul Arts Center",
               "name_en_source": "official", "summary_en": "x", "abstract_en": _ABSTRACT}
    src = [MockSource("Wikidata", payload)]
    asyncio.run(ingest.ingest_one("facts", "theater:sac", src, db_path=db))
    r2 = asyncio.run(ingest.ingest_one("facts", "theater:sac", src, db_path=db))
    assert calls["n"] == 1  # derived once; the second build carried the stored extract forward (no LLM)
    assert r2.data["attrs"]["Founded"] == "1988" and r2.data["aliases"] == ["SAC"]  # carried forward
    assert r2.data["enrichment"]["aliases"] == ["SAC"]  # provenance block persisted


def test_ingest_enrich_empty_result_still_marks_run_once(monkeypatch):
    # An entity whose abstract grounds nothing must ALSO be marked, or it re-calls the LLM every build.
    calls = {"n": 0}

    def fake(abstract, existing_keys=(), known_names=()):
        calls["n"] += 1
        return {"attrs": {}, "aliases": []}

    monkeypatch.setattr(ingest, "enrich", fake)
    db = _tmp_db()
    payload = {"name_ko": "방탄소년단", "name_en_official": "BTS", "name_en_source": "official",
               "summary_en": "x", "abstract_en": _ABSTRACT}
    src = [MockSource("Wikidata", payload)]
    asyncio.run(ingest.ingest_one("facts", "artist:bts", src, db_path=db))
    asyncio.run(ingest.ingest_one("facts", "artist:bts", src, db_path=db))
    assert calls["n"] == 1  # empty extract persisted as a marker -> no re-derivation next build


def test_enrich_module_uses_haiku():
    assert emod._MODEL == "claude-haiku-4-5-20251001"  # cheap; enrichment is best-effort labor


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
