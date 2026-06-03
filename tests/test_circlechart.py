"""Offline tests for the Circle Chart source + chart ingestion.

The PARSE step (LLM reply -> clean entries) and the ingestion are fully tested. The live fetch
+ LLM extraction are best-effort and validated on a GitHub run / your machine (egress-blocked
here), so they are not exercised offline.

Run:  PYTHONPATH=src python -m pytest tests/test_circlechart.py -q
"""

from __future__ import annotations

import asyncio
import os
import tempfile

from koreaapi.pipeline import store
from koreaapi.pipeline.ingest import ingest_chart
from koreaapi.sources.circlechart import parse_chart

_LLM_REPLY = """Sure, here is the chart:
[
  {"rank": 1, "artist": "방탄소년단", "title": "신곡"},
  {"rank": 2, "artist": "뉴진스", "title": "Supernatural"},
  {"bad": "row"},
  {"rank": "3", "artist": "에스파", "title": "Whiplash"}
]
"""


def _tmp_db() -> str:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(path)
    return path


def test_parse_chart_is_tolerant():
    entries = parse_chart(_LLM_REPLY)
    assert [e["rank"] for e in entries] == [1, 2, 3]  # skips the malformed row; coerces "3" -> 3
    assert entries[0] == {"rank": 1, "artist": "방탄소년단", "title": "신곡"}


def test_parse_chart_garbage_returns_empty():
    assert parse_chart("no json here at all") == []
    assert parse_chart("[not valid json]") == []


def test_ingest_chart_appends_a_chart_snapshot():
    db = _tmp_db()
    chart = {
        "entries": [
            {"rank": 1, "artist": "방탄소년단", "title": "신곡"},
            {"rank": 2, "artist": "뉴진스", "title": "X"},
        ],
        "citation": "Circle Chart 2026-06-03 00:00 UTC",
        "source_url": "https://circlechart.kr/...",
    }
    rec = asyncio.run(ingest_chart(chart, db_path=db))
    assert rec is not None and rec.kind == "chart"
    assert rec.data["entries"][0]["artist"] == "방탄소년단"
    assert "방탄소년단" in rec.summary_en  # the #1 is surfaced
    assert any("Circle Chart" in s for s in rec.provenance.sources)

    got = asyncio.run(store.latest("chart:circle-digital", "chart", db_path=db))
    assert got is not None and len(got.data["entries"]) == 2


def test_ingest_chart_empty_is_noop():
    assert asyncio.run(ingest_chart({"entries": []}, db_path=_tmp_db())) is None


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
