"""Offline tests for engine 2 behavioral-signal capture.

Usage is the proprietary signal: every agent query / buy-intent is appended (append-only),
and top_signals ranks what's asked for most - the trend-product seed. Service calls capture
it best-effort (a logging failure never breaks a read). No network/credentials.

Run:  PYTHONPATH=src python -m pytest tests/test_signal.py -q
"""

from __future__ import annotations

import asyncio
import os
import tempfile

from koreaapi import service
from koreaapi.pipeline import store


def _tmp_db() -> str:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(path)
    return path


def test_log_and_top_signals_rank_by_count():
    db = _tmp_db()

    async def run():
        await store.log_signal("query", "artist:bts", db_path=db)
        await store.log_signal("query", "artist:bts", db_path=db)
        await store.log_signal("query", "artist:aespa", db_path=db)
        await store.log_signal("buy_intent", "BTS album", db_path=db)
        return await store.top_signals(db_path=db), await store.top_signals(kind="buy_intent", db_path=db)

    top, buys = asyncio.run(run())
    assert top[0] == {"kind": "query", "key": "artist:bts", "count": 2}  # most-asked first
    assert buys == [{"kind": "buy_intent", "key": "BTS album", "count": 1}]  # filter by kind


def test_service_calls_capture_signal():
    db = _tmp_db()

    async def run():
        await service.artist_status("artist:bts", db_path=db)  # logs a query (even though not found)
        await service.buy_options("BTS lightstick", db_path=db)  # logs buy-intent
        return await store.top_signals(db_path=db)

    top = asyncio.run(run())
    assert any(s["kind"] == "query" and s["key"] == "artist:bts" for s in top)
    assert any(s["kind"] == "buy_intent" and s["key"] == "BTS lightstick" for s in top)


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
