"""Offline test for `admin export` - the committable data asset (cold-start 'database').

Proves the verified snapshots serialize to a diffable/crawlable text asset: snapshots.jsonl
(full history, appended) + latest.json (current state per entity). The scheduled collector
runs pull + export on GitHub's runners so this accumulates in git.

Run:  PYTHONPATH=src python -m pytest tests/test_export.py -q
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile

from koreaapi.admin import export, seed


def _seeded_db() -> str:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(path)
    asyncio.run(seed(db_path=path))
    return path


def test_export_writes_history_and_current_state(tmp_path):
    out = asyncio.run(export(db_path=_seeded_db(), out_dir=str(tmp_path)))
    assert out == {"appended": 3, "entities": 3}

    lines = (tmp_path / "snapshots.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3
    rec0 = json.loads(lines[0])
    assert "entity_id" in rec0 and "provenance" in rec0  # full record with provenance

    latest = json.loads((tmp_path / "latest.json").read_text(encoding="utf-8"))
    assert len(latest) == 3
    assert any(e["name"]["en_official"] == "BTS" for e in latest)


def test_export_appends_history_but_overwrites_latest(tmp_path):
    db = _seeded_db()
    asyncio.run(export(db_path=db, out_dir=str(tmp_path)))
    asyncio.run(export(db_path=db, out_dir=str(tmp_path)))

    lines = (tmp_path / "snapshots.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 6  # history APPENDED (time-series grows), not overwritten

    latest = json.loads((tmp_path / "latest.json").read_text(encoding="utf-8"))
    assert len(latest) == 3  # current state OVERWRITTEN (still one row per entity)


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
