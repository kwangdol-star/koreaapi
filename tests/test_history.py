"""get_history — the append-only TIMELINE + change detection (the time moat made queryable). A
latecomer can copy today's row but not these timestamped past states. Offline."""

from __future__ import annotations

import asyncio
import tempfile
from datetime import datetime, timezone

from koreaapi import admin, service
from koreaapi.models import Name, Provenance, Record


def _snap(db: str, day: int, agency: str, en: str = "NewJeans", ko: str = "뉴진스") -> None:
    now = datetime(2026, 5, day, tzinfo=timezone.utc)
    asyncio.run(admin.store.append_record(Record(
        entity_id="artist:newjeans", kind="facts", name=Name(ko=ko, en_official=en),
        snapshot_at=now, summary_en=en, data={"agency_en": agency},
        provenance=Provenance(sources=["Wikidata Q1", "Wikipedia x"], fetched_at=now,
                              skill_score=1.0, confidence="high", agreeing_sources=2)), db_path=db))


def test_history_detects_agency_change_and_keeps_timeline():
    db = tempfile.mktemp(suffix=".db")
    _snap(db, 1, "ADOR")           # first verified state
    _snap(db, 2, "ADOR")           # unchanged (re-verified) -> no change event
    _snap(db, 8, "HYBE")           # 소속사 moved -> ONE change event
    out = asyncio.run(service.history("artist:newjeans", db_path=db))
    assert out["found"] and out["snapshots"] == 3
    assert out["first_verified"] == "2026-05-01" and out["last_verified"] == "2026-05-08"
    assert len(out["changes"]) == 1
    c = out["changes"][0]
    assert c["from"] == "ADOR" and c["to"] == "HYBE" and c["as_of"] == "2026-05-08"
    assert "소속사" in c["field"] or "agency" in c["field"]
    assert out["current"]["agency"] == "HYBE" and out["license"]["id"] == "CC-BY-4.0"


def test_history_missing_entity_is_safe():
    db = tempfile.mktemp(suffix=".db")
    out = asyncio.run(service.history("artist:nobody", db_path=db))
    assert out["found"] is False


def test_history_no_changes_still_shows_depth():
    db = tempfile.mktemp(suffix=".db")
    _snap(db, 1, "ADOR")
    _snap(db, 2, "ADOR")
    out = asyncio.run(service.history("artist:newjeans", db_path=db))
    assert out["snapshots"] == 2 and out["changes"] == [] and "depth" in out["note"]


def test_history_tool_registered_in_manifest():
    assert any(t[0] == "get_history" for t in admin._MCP_TOOLS)


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
