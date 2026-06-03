"""Offline tests for LLM romanization (best-effort, cheap AI as collection labor).

No `ANTHROPIC_API_KEY` -> returns None (so dev/sandbox/CI-without-secret skip it cleanly). At
ingest, an empty `romanized` is filled by the (here monkeypatched) romanizer; an existing one
is never overwritten and never triggers an LLM call.

Run:  PYTHONPATH=src python -m pytest tests/test_romanize.py -q
"""

from __future__ import annotations

import asyncio
import os
import tempfile

from koreaapi import romanize as rmod
from koreaapi.pipeline import ingest
from koreaapi.sources.mock import MockSource


def _tmp_db() -> str:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(path)
    return path


def test_romanize_returns_none_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert rmod.romanize("방탄소년단") is None
    assert rmod.romanize(None) is None
    assert rmod.romanize("   ") is None


def test_ingest_fills_empty_romanized_via_llm(monkeypatch):
    monkeypatch.setattr(ingest, "romanize", lambda ko: "Bangtan Sonyeondan" if ko else None)
    payload = {"name_ko": "방탄소년단", "name_en_official": "BTS",
               "name_en_source": "official", "summary_en": "x"}  # no romanized
    rec = asyncio.run(
        ingest.ingest_one("facts", "artist:bts", [MockSource("Wikidata", payload)], db_path=_tmp_db())
    )
    assert rec.name.romanized == "Bangtan Sonyeondan"


def test_ingest_keeps_existing_romanized_and_skips_llm(monkeypatch):
    calls = {"n": 0}

    def fake(ko):
        calls["n"] += 1
        return "SHOULD-NOT-BE-USED"

    monkeypatch.setattr(ingest, "romanize", fake)
    payload = {"name_ko": "방탄소년단", "name_en_official": "BTS",
               "name_romanized": "Bangtan Sonyeondan", "name_en_source": "official", "summary_en": "x"}
    rec = asyncio.run(
        ingest.ingest_one("facts", "artist:bts", [MockSource("Wikidata", payload)], db_path=_tmp_db())
    )
    assert rec.name.romanized == "Bangtan Sonyeondan"
    assert calls["n"] == 0  # existing romanization -> no LLM call


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
