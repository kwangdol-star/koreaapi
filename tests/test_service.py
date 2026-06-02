"""Offline tests for the agent-face service (no fastmcp, no network).

Proves the agent face serves verified, bilingual, provenance-bearing data from the
append-only store - the same store the human console reads.
"""

from __future__ import annotations

import asyncio
import os
import tempfile

from koreaapi import service
from koreaapi.admin import seed


def _seeded_db() -> str:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(path)
    asyncio.run(seed(db_path=path))
    return path


def test_artist_status_is_verified_and_bilingual():
    db = _seeded_db()
    out = asyncio.run(service.artist_status("artist:bts", db_path=db))

    assert out["found"] is True
    assert out["name"]["en_official"] == "BTS"
    assert out["name"]["ko"] == "방탄소년단"
    assert out["status"], "should have at least one status item"
    item = out["status"][0]
    assert item["provenance"]["skill_score"] >= 0.8
    assert item["provenance"]["sources"]


def test_korea_rising_ranks_high_skill_first():
    db = _seeded_db()
    out = asyncio.run(service.korea_rising(limit=10, db_path=db))

    scores = [i["provenance"]["skill_score"] for i in out["items"]]
    assert scores == sorted(scores, reverse=True)
    # BTS/NewJeans (1.0) outrank aespa (0.7, single-source)
    assert scores[0] >= scores[-1]


def test_buy_options_phase1_stub_is_honest():
    db = _seeded_db()
    out = asyncio.run(service.buy_options("BTS album", db_path=db))

    assert out["options"] == []
    assert "buy-intent" in out["note"]


if __name__ == "__main__":
    test_artist_status_is_verified_and_bilingual()
    test_korea_rising_ranks_high_skill_first()
    test_buy_options_phase1_stub_is_honest()
    print("all service tests passed")
