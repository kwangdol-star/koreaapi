"""Live smoke test: real Wikipedia fetch (source #2). Auto-skips when egress is blocked.

Same pattern as test_wikidata_live: needs network; in the sandbox egress is allowlist-gated
so it SKIPS rather than failing. On deploy / GitHub runners it runs and asserts real data.

Run:  PYTHONPATH=src python -m pytest tests/test_wikipedia_live.py -q
"""

from __future__ import annotations

import asyncio
import urllib.error

import pytest

from koreaapi.sources.wikipedia import WikipediaSource


def _live_fetch(entity_id: str, kind: str) -> dict:
    try:
        return asyncio.run(WikipediaSource().fetch(entity_id, kind))
    except urllib.error.HTTPError as e:
        deny = e.headers.get("x-deny-reason") if e.headers else None
        if deny or e.code in (429, 500, 502, 503, 504):
            pytest.skip(f"Wikipedia egress unavailable (HTTP {e.code}: {deny or e.reason})")
        raise
    except urllib.error.URLError as e:
        pytest.skip(f"Wikipedia unreachable (no egress): {e.reason}")


def test_live_wikipedia_bts_is_bilingual():
    res = _live_fetch("artist:bts", "facts")
    payload = res["payload"]
    assert payload["name_en_official"] == "BTS"
    assert payload["name_ko"] == "방탄소년단"  # ko interlanguage link
    assert res["citation"].startswith("Wikipedia BTS")
