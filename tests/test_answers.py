"""Answer Products (engine 3) — each turns the verified store into one decision envelope
{signal, action, score, rationale, answer, evidence}. Mirrors the sibling oracle's
decision-products pattern, adapted to culture data. Offline: no keys, no network, no chain."""

from __future__ import annotations

import asyncio
import tempfile
from datetime import datetime, timezone

from koreaapi import answers
from koreaapi.models import Name, Provenance, Record
from koreaapi.pipeline import store

NOW = datetime(2026, 6, 28, tzinfo=timezone.utc)


def _add(db: str, eid: str, ko: str, en: str, *, sources: list[str], agree: int, skill: float) -> None:
    asyncio.run(store.append_record(Record(
        entity_id=eid, kind="facts", name=Name(ko=ko, en_official=en), snapshot_at=NOW,
        summary_en=en, data={}, provenance=Provenance(
            sources=sources, fetched_at=NOW, skill_score=skill,
            confidence="high" if agree >= 2 else "low", agreeing_sources=agree)), db_path=db))


def _seed() -> str:
    db = tempfile.mktemp(suffix=".db")
    _add(db, "drama:vincenzo", "빈센조", "Vincenzo",
         sources=["Wikidata Q16741113", "TMDB 96162", "Wikipedia (ko)"], agree=3, skill=1.0)
    _add(db, "artist:newjeans", "뉴진스", "NewJeans", sources=["Wikidata Q1"], agree=1, skill=0.7)
    return db


def test_canonical_name_confirmed():
    out = asyncio.run(answers.answer("canonical-name", "Vincenzo", db_path=_seed()))
    assert out["signal"] == "CONFIRMED"
    assert out["answer"]["ko"] == "빈센조"      # the 빈첸초 bug, now a guarded product
    assert out["score"] >= 0.9


def test_canonical_name_unverified_single_source():
    out = asyncio.run(answers.answer("canonical-name", "NewJeans", db_path=_seed()))
    assert out["signal"] == "UNVERIFIED"        # one source -> don't assert the spelling


def test_canonical_name_not_found():
    out = asyncio.run(answers.answer("canonical-name", "Nonexistent Thing", db_path=_seed()))
    assert out["signal"] == "NOT_FOUND"
    assert out["score"] == 0.0


def test_fact_check_triple_verified_is_citable():
    out = asyncio.run(answers.answer("fact-check", "빈센조", db_path=_seed()))
    assert out["signal"] == "TRIPLE_VERIFIED"
    assert "cite" in out["action"].lower()
    assert out["answer"]["id"] == "drama:vincenzo"


def test_fact_check_single_source_not_citable():
    out = asyncio.run(answers.answer("fact-check", "NewJeans", db_path=_seed()))
    assert out["signal"] == "UNVERIFIED"
    assert "do not cite" in out["action"].lower()


def test_identity_resolve_exact():
    out = asyncio.run(answers.answer("identity-resolve", "drama:vincenzo", db_path=_seed()))
    assert out["signal"] == "RESOLVED"
    assert out["answer"]["id"] == "drama:vincenzo"
    assert out["answer"]["content_hash"]          # ID spine carries the content hash


def test_answer_all_runs_every_product():
    out = asyncio.run(answers.answer_all("Vincenzo", db_path=_seed()))
    assert out["count"] == len(answers.list_products()["products"])
    sigs = {a["product"]: a["signal"] for a in out["answers"]}
    assert sigs["canonical-name"] == "CONFIRMED"
    assert sigs["fact-check"] == "TRIPLE_VERIFIED"
    # every envelope carries the uniform decision keys
    for a in out["answers"]:
        assert {"product", "signal", "action", "score", "rationale", "answer", "evidence"} <= set(a)


def test_unknown_product_errors():
    out = asyncio.run(answers.answer("nope", "x", db_path=_seed()))
    assert "error" in out
    assert "canonical-name" in out["available"]


def test_list_products_shape():
    cat = answers.list_products()
    assert cat["count"] >= 5
    assert all({"id", "name", "sector", "inputs", "about"} <= set(p) for p in cat["products"])


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
