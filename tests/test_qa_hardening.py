"""Regression guards for the hardening fixes from the QA audit:
- `_fresh` tolerates a naive stored timestamp instead of crashing `stats`.
- `ingest_one` drops a source returning a malformed dict (missing keys) instead of breaking the run.
- `entity_pages` never emits two entries / a phantom page for two ids that normalize to one slug.
"""

from __future__ import annotations

import asyncio
import glob
import os
import tempfile

from koreaapi import admin
from koreaapi.pipeline.ingest import ingest_one
from koreaapi.sources.mock import MockSource


def test_fresh_tolerates_naive_timestamp_without_crashing():
    # A naive ISO (no offset) previously raised TypeError (aware - naive) and crashed `stats`.
    assert isinstance(admin._fresh("2026-06-27T00:00:00", "facts"), bool)   # no crash
    assert admin._fresh("not-a-timestamp", "facts") is False                # malformed -> False


class _BadSource:
    name = "Bad"
    is_fallback = False

    async def fetch(self, entity_id: str, kind: str) -> dict:
        return {}  # malformed: missing "payload"/"citation"


def test_ingest_drops_malformed_source_and_keeps_going():
    db = tempfile.mktemp(suffix=".db")
    good = {"name_ko": "방탄소년단", "name_en_official": "BTS", "name_en_source": "official"}
    rec = asyncio.run(ingest_one("facts", "artist:bts",
                                 [_BadSource(), MockSource("Wikidata", good)], db_path=db))
    assert rec is not None                       # the malformed source didn't break the run
    assert len(rec.provenance.sources) == 1      # only the good source contributed
    assert rec.provenance.skill_score <= 0.7     # single source -> honestly capped


def test_entity_pages_dedupe_colliding_slugs(tmp_path):
    db = tempfile.mktemp(suffix=".db")
    # two distinct entity_ids that both normalize to the slug "new-jeans"
    for eid, ko in (("artist:new-jeans", "뉴진스"), ("artist:new.jeans", "뉴진스투")):
        p = {"name_ko": ko, "name_en_official": eid.split(":")[1], "name_en_source": "official"}
        asyncio.run(ingest_one("facts", eid, [MockSource("Wikidata", p), MockSource("Wikipedia", p)], db_path=db))
    out_dir = str(tmp_path / "site")
    res = asyncio.run(admin.entity_pages(db_path=db, out_dir=out_dir))
    slugs = [e["slug"] for e in res["entities"]]
    assert slugs.count("new-jeans") == 1                                  # no phantom duplicate entry
    assert len(glob.glob(os.path.join(out_dir, "artist", "new-jeans.html"))) == 1  # one file on disk


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
