"""Universe discovery — the path to 10x. SPARQL bulk-lists each vertical's Korean entities; the
discovered Q-id is fetched DIRECTLY (no same-name search drift) and run through the SAME cross-verify
pipeline (only verified kept). The query builder + the qid fast-path are pure/offline-tested here;
the live SPARQL runs on the open-network runner (like sweep). Also covers load_latest accumulation.
"""

from __future__ import annotations

import asyncio
import tempfile

from koreaapi import admin
from koreaapi.sources.wikidata import _DISCOVER, WikidataSource, build_discover_query


def test_discover_query_has_class_country_and_pagination():
    q = build_discover_query("drama", limit=400, offset=800)
    assert "wd:Q5398426" in q          # television series
    assert "wd:Q884" in q and "wdt:P495" in q  # origin = South Korea
    assert "LIMIT 400" in q and "OFFSET 800" in q and "ORDER BY ?item" in q


def test_discover_food_uses_korean_cuisine_filter():
    q = build_discover_query("food")
    assert "wdt:P2012" in q and "wd:Q234138" in q  # cuisine = Korean cuisine
    # every vertical has a query that names its filter property
    for v in _DISCOVER:
        assert "?item" in build_discover_query(v)


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
