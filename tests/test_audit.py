"""Store-wide type audit — offline (batch P31 HTTP monkeypatched). Roster entities self-heal on
every pull, but DISCOVERED entities are ingested once, so the audit is what catches a poisoned one
retroactively (the 'Sweet Home' sweep) and `fix` removes it: miss, never wrong."""

from __future__ import annotations

import asyncio
import tempfile
from datetime import datetime, timezone

from koreaapi import admin
from koreaapi.models import Name, Provenance, Record

NOW = datetime(2026, 7, 6, tzinfo=timezone.utc)


def test_audit_flags_and_fix_removes_cross_vertical_impostor(monkeypatch):
    import koreaapi.sources.wikidata as wd
    db = tempfile.mktemp(suffix=".db")

    def add(eid, ko, en, sources):
        asyncio.run(admin.store.append_record(Record(
            entity_id=eid, kind="facts", name=Name(ko=ko, en_official=en), snapshot_at=NOW,
            summary_en=en, data={}, provenance=Provenance(
                sources=sources, fetched_at=NOW, skill_score=0.7, confidence="low")), db_path=db))

    add("webtoon:sweethome", "스위트홈", "Sweet Home", ["Wikidata Q7777 2026-07-06"])   # poisoned
    add("drama:vincenzo", "빈센조", "Vincenzo", ["Wikidata Q8888 2026-07-06"])          # healthy
    add("folklore:dokkaebi", "도깨비", "Dokkaebi", ["Wikipedia Dokkaebi 2026-07-06"])    # no Q-id -> skipped

    def fake_get(url, headers):  # one batch: the game is game-typed, the drama drama-typed
        assert "wbgetentities" in url and "Q7777" in url and "Q8888" in url
        return {"entities": {
            "Q7777": {"claims": {"P31": [{"mainsnak": {"datavalue": {"value": {"id": "Q7889"}}}}]}},
            "Q8888": {"claims": {"P31": [{"mainsnak": {"datavalue": {"value": {"id": "Q5398426"}}}}]}},
        }}

    monkeypatch.setattr(wd, "_http_get_json", fake_get)
    out = asyncio.run(admin.audit(db_path=db))            # report-only first
    assert out["checked"] == 2 and out["skipped"] == 1
    assert [v["entity_id"] for v in out["violations"]] == ["webtoon:sweethome"]
    assert out["removed"] == []                            # nothing deleted without fix
    assert asyncio.run(admin.store.latest("webtoon:sweethome", "facts", db_path=db)) is not None

    out = asyncio.run(admin.audit(db_path=db, fix=True))   # now heal
    assert out["removed"] == ["webtoon:sweethome"]
    assert asyncio.run(admin.store.latest("webtoon:sweethome", "facts", db_path=db)) is None
    assert asyncio.run(admin.store.latest("drama:vincenzo", "facts", db_path=db)) is not None


def test_audit_survives_a_failed_batch(monkeypatch):
    import koreaapi.sources.wikidata as wd
    db = tempfile.mktemp(suffix=".db")
    asyncio.run(admin.store.append_record(Record(
        entity_id="drama:vincenzo", kind="facts", name=Name(ko="빈센조", en_official="Vincenzo"),
        snapshot_at=NOW, summary_en="v", data={}, provenance=Provenance(
            sources=["Wikidata Q1 2026"], fetched_at=NOW, skill_score=1.0, confidence="high")),
        db_path=db))

    def boom(url, headers):
        raise OSError("egress blocked")

    monkeypatch.setattr(wd, "_http_get_json", boom)
    out = asyncio.run(admin.audit(db_path=db, fix=True))
    assert out["checked"] == 1 and out["violations"] == [] and out["removed"] == []  # unaudited ≠ removed


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
