"""Source disagreement surfacing — "verification over trust" made visible. When independent sources
give a DIFFERENT canonical name, ingest records which source differed (and the one we chose by source
authority) instead of silently dropping it; the entity page shows a Source-reconciliation note and
status.json counts it. The 빈센조(not 빈첸초) reconciliation, now legible."""

from __future__ import annotations

import asyncio
import json
import tempfile

from koreaapi import admin
from koreaapi.pipeline.ingest import ingest_one
from koreaapi.sources.mock import MockSource


def _tmp(suffix: str) -> str:
    return tempfile.mktemp(suffix=suffix)


def test_ingest_records_name_disagreement_with_the_chosen_value():
    db = _tmp(".db")
    wikidata = {"name_ko": "빈첸초", "name_en_official": "Vincenzo",  # structured base, but wrong ko label
                "name_en_source": "official", "agency_en": "Netflix"}
    tmdb = {"name_ko": "빈센조", "name_en_official": "Vincenzo", "name_en_source": "official"}  # authority
    rec = asyncio.run(ingest_one("facts", "drama:vincenzo",
                                 [MockSource("Wikidata", wikidata), MockSource("TMDB", tmdb)], db_path=db))
    assert rec.name.ko == "빈센조"                                  # TMDB authority wins the display name
    dis = rec.data["source_disagreements"]
    assert any(d["source"] == "Wikidata" and d["field"] == "name_ko"
               and d["value"] == "빈첸초" and d["chosen"] == "빈센조" for d in dis)


def test_no_disagreement_when_sources_agree():
    db = _tmp(".db")
    p = {"name_ko": "방탄소년단", "name_en_official": "BTS", "name_en_source": "official"}
    rec = asyncio.run(ingest_one("facts", "artist:bts",
                                 [MockSource("Wikidata", p), MockSource("Wikipedia", p)], db_path=db))
    assert "source_disagreements" not in rec.data                  # agreement -> no note (no false positive)


def test_disagreement_surfaces_on_page_and_in_status(tmp_path):
    db = _tmp(".db")
    wikidata = {"name_ko": "빈첸초", "name_en_official": "Vincenzo",
                "name_en_source": "official", "agency_en": "Netflix"}
    tmdb = {"name_ko": "빈센조", "name_en_official": "Vincenzo", "name_en_source": "official"}
    asyncio.run(ingest_one("facts", "drama:vincenzo",
                           [MockSource("Wikidata", wikidata), MockSource("TMDB", tmdb)], db_path=db))
    out_dir = str(tmp_path / "site")
    asyncio.run(admin.entity_pages(db_path=db, out_dir=out_dir))
    page = (tmp_path / "site" / "artist" / "vincenzo.html").read_text(encoding="utf-8")
    assert "Source reconciliation" in page and "빈첸초" in page and "빈센조" in page
    ko_page = (tmp_path / "site" / "ko" / "artist" / "vincenzo.html").read_text(encoding="utf-8")
    assert "출처 조정" in ko_page and "빈첸초" in ko_page   # Korean-surface parity for the trust signal

    st = _tmp(".json")
    asyncio.run(admin.status_json(db_path=db, out_path=st))
    doc = json.load(open(st, encoding="utf-8"))
    assert doc["source_disagreements"] >= 1


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
