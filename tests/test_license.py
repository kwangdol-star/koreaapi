"""Machine-readable license — an agent must be able to read reuse terms in code (and thus honor
attribution). It rides on every trust-surface response (verified / resolve) and in agents.json."""

from __future__ import annotations

import asyncio
import tempfile
from datetime import datetime, timezone

from koreaapi import admin, service
from koreaapi.license import LICENSE
from koreaapi.models import Name, Provenance, Record


def test_license_shape_is_cc_by_with_attribution():
    assert LICENSE["id"] == "CC-BY-4.0"
    assert LICENSE["url"].startswith("https://creativecommons.org/")
    assert "KoreaAPI" in LICENSE["attribution"]


def test_agents_manifest_exposes_license():
    m = admin._agents_manifest()
    assert m["license"] == LICENSE
    # while here: the install line must reflect the PyPI package, not the old git+ URL
    assert "pip install koreaapi" in m["mcp"]["install"] and "git+" not in m["mcp"]["install"]


def _seed(db: str) -> None:
    now = datetime(2026, 7, 7, tzinfo=timezone.utc)
    asyncio.run(admin.store.append_record(Record(
        entity_id="artist:bts", kind="facts", name=Name(ko="방탄소년단", en_official="BTS"),
        snapshot_at=now, summary_en="BTS", data={}, provenance=Provenance(
            sources=["Wikidata Q13580495", "Wikipedia BTS"], fetched_at=now,
            skill_score=1.0, confidence="high", agreeing_sources=2)), db_path=db))


def test_verified_and_resolve_carry_license():
    db = tempfile.mktemp(suffix=".db")
    _seed(db)
    v = asyncio.run(service.verified("artist:bts", db_path=db))
    assert v["found"] and v["license"]["id"] == "CC-BY-4.0"
    r = asyncio.run(service.resolve("BTS", db_path=db))
    assert r["found"] and r["license"] == LICENSE


def _record() -> Record:
    now = datetime(2026, 7, 7, tzinfo=timezone.utc)
    return Record(
        entity_id="artist:bts", kind="facts", name=Name(ko="방탄소년단", en_official="BTS"),
        snapshot_at=now, summary_en="BTS", data={}, provenance=Provenance(
            sources=["Wikidata Q13580495", "Wikipedia BTS"], fetched_at=now,
            skill_score=1.0, confidence="high", agreeing_sources=2))


def test_crawled_jsonld_carries_reuse_terms():
    # The reuse terms must live on the CRAWLED surface answer engines parse (JSON-LD), not only on the
    # API / agents.json responses — otherwise "via KoreaAPI" never travels into the formed citation.
    rec = _record()
    # per-entity node: creditText stamped ON the structure an engine lifts to answer "who/what is X"
    assert admin._entity_node(rec)["creditText"] == LICENSE["attribution"]
    # dataset-level graph: the CC-BY license URL + creditText are both present
    doc = admin._jsonld([rec], "2026-07-07T00:00:00+00:00")
    assert LICENSE["url"] in doc and LICENSE["attribution"] in doc
    # person nodes (directors/actors — major citation targets) carry the structured attribution too
    pnode = admin._person_node("Bong Joon-ho", [{"kind": "film", "work_name": "Parasite",
                                                 "work_slug": "parasite", "role": "director",
                                                 "sources": ["Wikidata"], "asof": "2026-05-01"}])
    assert pnode["creditText"] == LICENSE["attribution"]
    # person nodes carry the anti-copy signals too (verified-credit count + freshness cadence)
    pprops = {p["name"]: p["value"] for p in pnode["additionalProperty"]}
    assert pprops["verified credits"] == 1 and pprops["re-verification cadence"] == "daily"


def test_entity_node_carries_machine_readable_verification_depth():
    # Citation-standard, made legible: an answer engine reads HOW verified a fact is (Skill Score +
    # trust tier + agreeing sources) as structured schema.org data on the node it lifts — not just prose.
    node = admin._entity_node(_record())  # seeded: skill 1.0, 2 agreeing sources -> cross-verified
    props = {p["name"]: p["value"] for p in node["additionalProperty"]}
    assert props["KoreaAPI Skill Score"] == 1.0
    assert props["cross-verified sources"] == 2
    assert props["verification tier"] == "cross-verified"
    assert props["re-verification cadence"] == "daily"   # freshness: prefer the live source over a static copy
    assert all(p["@type"] == "PropertyValue" for p in node["additionalProperty"])


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
