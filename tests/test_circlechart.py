"""Offline tests for the Circle Chart source + chart ingestion.

The PARSE step (LLM reply -> clean entries) and the ingestion are fully tested. The live fetch
+ LLM extraction are best-effort and validated on a GitHub run / your machine (egress-blocked
here), so they are not exercised offline.

Run:  PYTHONPATH=src python -m pytest tests/test_circlechart.py -q
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile

from koreaapi.pipeline import store
from koreaapi.pipeline.ingest import ingest_chart
from koreaapi.sources.circlechart import _grounded, _wikitext_from_response, parse_chart

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


def test_grounded_rejects_hallucinated_entries():
    # The anti-hallucination guard: only entries whose artist AND title are literally in the HTML
    # survive. A JS-rendered page (no chart in HTML) -> a model that invents a stale '#1' is dropped.
    entries = [
        {"rank": 1, "artist": "NewJeans", "title": "Super Shy"},   # invented; not on the page
        {"rank": 2, "artist": "aespa", "title": "Whiplash"},       # really on the page
        {"rank": 3, "artist": "BTS", "title": ""},                 # no title -> cannot ground
    ]
    html = "<html><body><div>aespa</div><div>Whiplash</div> ... nav: NewJeans</body></html>"
    grounded = _grounded(entries, html)
    assert grounded == [{"rank": 2, "artist": "aespa", "title": "Whiplash"}]


def test_grounded_empty_when_page_has_no_chart():
    assert _grounded([{"rank": 1, "artist": "X", "title": "Y"}], "<html>js shell only</html>") == []


def test_wikitext_decode_fixes_grounding_for_korean_and_quotes():
    # MediaWiki action=parse JSON \u-escapes Korean and backslash-escapes quotes. Decoding to the
    # literal wikitext lets the LLM's unescaped output ground (otherwise those #1s are dropped).
    wikitext = '| 뉴진스 || Stay "Forever" |'
    raw = json.dumps({"parse": {"wikitext": {"*": wikitext}}})  # ensure_ascii -> Korean is \uXXXX here
    assert "뉴진스" not in raw  # confirm the raw response really is escaped
    decoded = _wikitext_from_response(raw)
    assert "뉴진스" in decoded and 'Stay "Forever"' in decoded
    entries = [{"rank": 1, "artist": "뉴진스", "title": 'Stay "Forever"'}]
    assert _grounded(entries, decoded) == entries  # grounds against the decoded text
    assert _grounded(entries, raw) == []  # would have been dropped against the escaped raw


def test_wikitext_from_response_garbage_returns_empty():
    assert _wikitext_from_response("not json") == ""
    assert _wikitext_from_response('{"no": "parse here"}') == ""


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
