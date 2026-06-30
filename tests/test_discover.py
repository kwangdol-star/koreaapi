"""Universe discovery — the path to 10x. SPARQL bulk-lists each vertical's Korean entities; the
discovered Q-id is fetched DIRECTLY (no same-name search drift) and run through the SAME cross-verify
pipeline (only verified kept). The query builder + the qid fast-path are pure/offline-tested here;
the live SPARQL runs on the open-network runner (like sweep). Also covers load_latest accumulation.
"""

from __future__ import annotations

import asyncio
import tempfile

from koreaapi import admin
from koreaapi.sources.wikidata import _DISCOVER, WikidataSource, build_discover_search


def test_discover_search_targets_class_and_country():
    q = build_discover_search("drama")  # CirrusSearch (haswbstatement) on the working API endpoint
    assert "P31=Q5398426" in q                    # television series
    assert "haswbstatement:P495=Q884" in q         # origin = South Korea


def test_discover_food_uses_korean_cuisine_filter():
    q = build_discover_search("food")
    assert "P2012=Q234138" in q  # cuisine = Korean cuisine
    # every vertical builds a haswbstatement query
    for v in _DISCOVER:
        assert build_discover_search(v).startswith("haswbstatement:")


def test_fetch_discover_forwards_full_limit_not_clamped(monkeypatch):
    # Regression (the +0-new plateau): fetch_discover used to clamp the limit to min(limit, 50),
    # which silently defeated _discover_candidates' internal 50/request pagination — discovery only
    # ever saw the FIRST 50 candidates per vertical (all already ingested -> 0 new forever). It must
    # pass the full limit through so the paginating walker reaches the long tail.
    import koreaapi.sources.wikidata as wd

    captured: dict = {}

    def fake(search: str, *, limit: int) -> list:
        captured["limit"] = limit
        return []

    monkeypatch.setattr(wd, "_discover_candidates", fake)
    wd.fetch_discover("artist", limit=400)
    assert captured["limit"] == 400  # not 50


def test_injected_qid_is_fetched_without_search(monkeypatch):
    # A SPARQL-discovered qid is fetched directly — resolve_qid must NOT hit wbsearchentities.
    calls = {"search": 0}

    def http_get(self, url: str) -> dict:
        if "wbsearchentities" in url:
            calls["search"] += 1
            return {"search": [{"id": "QWRONG"}]}
        return {"entities": {"QGOOD": {"id": "QGOOD",
                "labels": {"ko": {"value": "오징어 게임"}, "en": {"value": "Squid Game"}}}}}

    monkeypatch.setattr(WikidataSource, "_http_get", http_get)
    src = WikidataSource(aliases={"drama:x": "Squid Game"}, qids={"drama:x": "QGOOD"})
    res = asyncio.run(src.fetch("drama:x", "facts"))
    assert res["citation"].startswith("Wikidata QGOOD")  # fetched the injected qid
    assert calls["search"] == 0                            # search was skipped entirely


def test_load_latest_round_trips_for_accumulation(tmp_path):
    # export -> load must restore the records, so a fresh-per-run collector accumulates across runs.
    from koreaapi.models import Name, Provenance, Record
    from datetime import datetime, timezone
    db1 = tempfile.mktemp(suffix=".db")
    now = datetime(2026, 6, 27, tzinfo=timezone.utc)
    asyncio.run(admin.store.append_record(Record(
        entity_id="food:bibimbap", kind="facts", name=Name(ko="비빔밥", en_official="Bibimbap"),
        snapshot_at=now, summary_en="Bibimbap — verified Korean dish.", data={},
        provenance=Provenance(sources=["Wikidata Q1", "Wikipedia Bibimbap"], fetched_at=now,
                              skill_score=1.0, confidence="high")), db_path=db1))
    asyncio.run(admin.export(db_path=db1, out_dir=str(tmp_path)))
    db2 = tempfile.mktemp(suffix=".db")
    n = asyncio.run(admin.load_latest(in_path=str(tmp_path / "latest.json"), db_path=db2))
    assert n >= 1
    rec = asyncio.run(admin.store.latest("food:bibimbap", "facts", db_path=db2))
    assert rec is not None and rec.name.en_official == "Bibimbap"


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
