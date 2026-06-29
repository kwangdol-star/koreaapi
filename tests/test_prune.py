"""prune — the narrow maintenance cleanup for mis-discovered entities (a bad discovery class once
matched K-pop singles as 'webtoon'). Deletes discovered webtoons (not in the roster) + a denylist;
keeps roster + legit discovered items. The store is otherwise append-only. Offline."""

from __future__ import annotations

import asyncio
import tempfile
from datetime import datetime, timezone

from koreaapi import admin
from koreaapi.models import Name, Provenance, Record


def _add(db: str, eid: str) -> None:
    now = datetime(2026, 6, 28, tzinfo=timezone.utc)
    asyncio.run(admin.store.append_record(Record(
        entity_id=eid, kind="facts", name=Name(ko="x", en_official="x"), snapshot_at=now,
        summary_en="x", data={}, provenance=Provenance(
            sources=["Wikidata Q1"], fetched_at=now, skill_score=1.0, confidence="high")), db_path=db))


def test_prune_removes_bad_keeps_good():
    db = tempfile.mktemp(suffix=".db")
    for eid in ("webtoon:sololeveling", "webtoon:gangnamstyle", "food:shizuokaoden",
                "food:bibimbap", "place:gyeongbokgung"):
        _add(db, eid)
    out = asyncio.run(admin.prune(db_path=db))
    assert "webtoon:gangnamstyle" in out["removed"]      # discovered webtoon (not roster) = song pollution
    assert "food:shizuokaoden" in out["removed"]         # explicit denylist
    assert asyncio.run(admin.store.latest("webtoon:gangnamstyle", "facts", db_path=db)) is None
    for eid in ("webtoon:sololeveling", "food:bibimbap", "place:gyeongbokgung"):  # roster/legit kept
        assert asyncio.run(admin.store.latest(eid, "facts", db_path=db)) is not None


def test_prune_is_idempotent():
    db = tempfile.mktemp(suffix=".db")
    _add(db, "webtoon:gangnamstyle")
    assert asyncio.run(admin.prune(db_path=db))["removed"] == ["webtoon:gangnamstyle"]
    assert asyncio.run(admin.prune(db_path=db))["removed"] == []   # nothing left -> no-op


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
