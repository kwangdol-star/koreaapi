"""Tests for the AEO/GEO surface: JSON-LD in report.html + citation field in service output.

Offline (seeded sample DB). Proves crawlable Schema.org structured data and a ready-to-cite
string travel with the verified records, so answer engines can surface and cite KoreaAPI as
the verifiable origin.

Run:  PYTHONPATH=src python -m pytest tests/test_geo.py -q
"""

from __future__ import annotations

import asyncio
import os
import tempfile

from koreaapi import admin, service
from koreaapi.admin import _wikidata_url, seed


def _seeded_db() -> str:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(path)
    asyncio.run(seed(db_path=path))
    return path


def test_wikidata_url_extracted_from_citation():
    assert (
        _wikidata_url(["Wikidata Q13580495 2026-06-02 00:00 UTC"])
        == "https://www.wikidata.org/entity/Q13580495"
    )
    assert _wikidata_url(["Circle Chart 2026-06-01 KST"]) is None


def test_report_emits_jsonld_structured_data(tmp_path):
    out = str(tmp_path / "report.html")
    asyncio.run(admin.report_html(db_path=_seeded_db(), out_path=out))
    page = open(out, encoding="utf-8").read()

    assert 'type="application/ld+json"' in page  # crawlable structured data block
    assert "schema.org" in page
    assert '"@type": "MusicGroup"' in page
    assert 'name="description"' in page  # AEO meta for answer engines
    assert "BTS" in page  # a verified entity surfaced as structured data
    assert '"recordLabel"' in page  # the verified artist -> 소속사 edge, citable by engines
    assert "Big Hit Music" in page  # the agency name surfaced in the structured data


def test_service_item_carries_reproducible_citation():
    out = asyncio.run(service.artist_status("artist:bts", db_path=_seeded_db()))
    item = out["status"][0]

    assert "citation" in item
    c = item["citation"]
    assert "BTS" in c and "KoreaAPI" in c and "Skill Score" in c  # cite source + us


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
