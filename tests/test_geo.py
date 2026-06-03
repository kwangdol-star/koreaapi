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
from datetime import datetime, timezone

from koreaapi import admin, service
from koreaapi.admin import _wikidata_url, seed
from koreaapi.models import Name, Provenance, Record
from koreaapi.pipeline import store


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


def test_markdown_digest_renders_verified_snapshot(tmp_path):
    db = str(tmp_path / "d.db")
    now = datetime.now(timezone.utc)
    asyncio.run(store.append_record(Record(
        entity_id="artist:bts", kind="facts", name=Name(ko="방탄소년단", en_official="BTS"),
        snapshot_at=now, summary_en="BTS - facts.", data={"agency_en": "Big Hit Music"},
        provenance=Provenance(sources=["Wikidata Q13580495", "Wikipedia BTS"], fetched_at=now,
                              skill_score=1.0, confidence="high"),
    ), db_path=db))
    asyncio.run(store.append_record(Record(
        entity_id="chart:circle-digital", kind="chart",
        name=Name(ko="써클 디지털 차트", en_official="Circle Digital Chart"), snapshot_at=now,
        summary_en="Circle Digital Chart.", data={"entries": [{"rank": 1, "artist": "Cortis", "title": "RedRed"}]},
        provenance=Provenance(sources=["Circle Digital Chart #1 (via Wikipedia)"], fetched_at=now,
                              skill_score=0.7, confidence="medium"),
    ), db_path=db))
    out = str(tmp_path / "korea-rising.md")
    asyncio.run(admin.markdown_digest(db_path=db, out_path=out))
    md = open(out, encoding="utf-8").read()

    assert "Korea Rising" in md and "via KoreaAPI" in md  # title + cite line
    assert "Cortis" in md and "current #1" in md  # settlement headline
    assert "Big Hit Music" in md and "BTS" in md  # verified roster by agency


def test_service_item_carries_reproducible_citation():
    out = asyncio.run(service.artist_status("artist:bts", db_path=_seeded_db()))
    item = out["status"][0]

    assert "citation" in item
    c = item["citation"]
    assert "BTS" in c and "KoreaAPI" in c and "Skill Score" in c  # cite source + us


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
