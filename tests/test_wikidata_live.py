"""Live smoke test: actually pull real data from Wikidata (real source #1).

This is the end-to-end check that the adapter works against the live API. It needs
network egress; in the web/dev sandbox egress is allowlist-gated and Wikidata is
blocked (HTTP 403, `x-deny-reason: host_not_allowed`), so the test AUTO-SKIPS rather
than failing. The instant `*.wikidata.org` is allowlisted (or on deploy) it runs and
asserts real data.

A genuine 403 WITHOUT the egress deny header (e.g. a Wikimedia User-Agent block) is NOT
skipped - it fails, because that is a real adapter problem to fix.

Run:  PYTHONPATH=src python -m pytest tests/test_wikidata_live.py -q
"""

from __future__ import annotations

import asyncio
import urllib.error

import pytest

from koreaapi.sources.wikidata import WikidataSource


def _live_fetch(entity_id: str, kind: str) -> dict:
    """Run the real adapter; translate "egress unavailable" into a pytest skip."""
    try:
        return asyncio.run(WikidataSource().fetch(entity_id, kind))
    except urllib.error.HTTPError as e:
        deny = e.headers.get("x-deny-reason") if e.headers else None
        if deny or e.code in (429, 500, 502, 503, 504):
            pytest.skip(f"Wikidata egress unavailable (HTTP {e.code}: {deny or e.reason})")
        raise  # a real 403/4xx (e.g. UA policy) is a genuine failure, not a skip
    except urllib.error.URLError as e:  # DNS / connection refused / blocked at socket
        pytest.skip(f"Wikidata unreachable (no egress): {e.reason}")


def test_live_pull_bts_is_real_and_bilingual():
    res = _live_fetch("artist:bts", "facts")
    payload = res["payload"]
    assert payload["name_ko"] == "방탄소년단"
    assert payload["name_en_official"] == "BTS"  # Wikidata label = official EN name
    assert payload["name_en_source"] == "official"
    assert res["citation"].startswith("Wikidata Q484203")


def test_live_search_resolves_unmapped_entity():
    # 'artist:blackpink' is NOT in the curated _QID map -> exercises live wbsearchentities.
    res = _live_fetch("artist:blackpink", "facts")
    assert res["payload"]["name_en_official"]  # got a real official label back
    assert res["citation"].startswith("Wikidata Q")
