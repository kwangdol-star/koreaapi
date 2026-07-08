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


def test_export_writes_changes_feed(tmp_path):
    # The store-wide freshness feed: a 소속사 move must show up in changes.json (newest-first).
    import json
    db = tempfile.mktemp(suffix=".db")
    _snap(db, 1, "ADOR")
    _snap(db, 9, "HYBE")   # agency moved
    asyncio.run(admin.export(db_path=db, out_dir=str(tmp_path)))
    feed = json.load(open(tmp_path / "changes.json", encoding="utf-8"))
    assert feed["count"] == 1
    c = feed["changes"][0]
    assert c["entity_id"] == "artist:newjeans" and c["from"] == "ADOR" and c["to"] == "HYBE"
    assert feed["license"]["id"] == "CC-BY-4.0"
    # and the manifest advertises the feed
    assert "changes_feed" in admin._agents_manifest()["data"]


def test_recent_changes_store_wide(tmp_path):
    # store-wide freshness query: a 소속사 move surfaces in recent_changes (newest-first).
    db = tempfile.mktemp(suffix=".db")
    _snap(db, 1, "ADOR")
    _snap(db, 9, "HYBE")
    out = asyncio.run(service.recent_changes(db_path=db))
    assert out["count"] == 1
    c = out["changes"][0]
    assert c["entity_id"] == "artist:newjeans" and c["to"] == "HYBE"
    assert out["license"]["id"] == "CC-BY-4.0"


def test_entity_page_renders_verification_history(tmp_path):
    # The time moat, made VISIBLE + citable on the CRAWLED entity page: the first-verified depth + the
    # 소속사 change event an answer engine can lift ("when did NewJeans' agency change?").
    db = tempfile.mktemp(suffix=".db")
    _snap(db, 1, "ADOR")
    _snap(db, 8, "HYBE")   # 소속사 moved -> a change event on the timeline
    asyncio.run(admin.entity_pages(db_path=db, out_dir=str(tmp_path / "site")))
    page = (tmp_path / "site" / "artist" / "newjeans.html").read_text(encoding="utf-8")
    assert "Verification history" in page
    assert "tracked since" in page and "2026-05-01" in page        # first-verified anchor
    assert "ADOR → HYBE" in page and "as of 2026-05-08" in page    # the timestamped change event
    assert "get_history(&quot;artist:newjeans&quot;)" in page      # machine-readable pointer
    assert "/changes.json" in page                                 # full feed link


def test_entity_page_hides_history_without_depth(tmp_path):
    # A single verified snapshot (no temporal depth, no change) must NOT render a thin history section.
    db = tempfile.mktemp(suffix=".db")
    _snap(db, 1, "ADOR")
    asyncio.run(admin.entity_pages(db_path=db, out_dir=str(tmp_path / "site")))
    page = (tmp_path / "site" / "artist" / "newjeans.html").read_text(encoding="utf-8")
    assert "Verification history" not in page


def test_ko_entity_page_renders_verification_history(tmp_path):
    # hreflang parity: the Korean answer page (/ko, for Naver / 국내 질의) surfaces the same time moat.
    db = tempfile.mktemp(suffix=".db")
    _snap(db, 1, "ADOR")
    _snap(db, 8, "HYBE")   # 소속사 이동
    asyncio.run(admin.entity_pages(db_path=db, out_dir=str(tmp_path / "site")))
    page = (tmp_path / "site" / "ko" / "artist" / "newjeans.html").read_text(encoding="utf-8")
    assert "검증 이력" in page
    assert "부터 추적" in page and "2026-05-01" in page              # 최초검증 기준점
    assert "소속사" in page and "ADOR → HYBE" in page and "2026-05-08 기준" in page  # 변경 이벤트
    assert "get_history(&quot;artist:newjeans&quot;)" in page       # 기계 판독 포인터
