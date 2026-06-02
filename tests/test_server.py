"""Offline smoke test for the MCP server - the agent product surface.

server.py is a thin FastMCP binding over service.py; this verifies the 4 tools register and
that a bound tool returns verified, provenance-bearing data end to end. fastmcp is a project
dependency; the test skips cleanly if it isn't installed (e.g. a pydantic-only minimal env).

Run:  PYTHONPATH=src python -m pytest tests/test_server.py -q
"""

from __future__ import annotations

import asyncio
import inspect

import pytest

pytest.importorskip("fastmcp")  # the agent surface needs fastmcp; skip if absent

from koreaapi import server  # noqa: E402  (imported after importorskip by design)
from koreaapi.admin import seed  # noqa: E402

EXPECTED_TOOLS = {
    "get_artist_status",
    "get_kculture_calendar",
    "get_korea_rising",
    "get_buy_options",
}


def _tool_names() -> set[str]:
    res = server.mcp.list_tools()
    if inspect.isawaitable(res):
        res = asyncio.run(res)
    return {t.name for t in res}


def test_server_registers_the_four_tools():
    assert _tool_names() == EXPECTED_TOOLS


def test_bound_tool_returns_verified_data(monkeypatch, tmp_path):
    db = str(tmp_path / "mcp.db")
    monkeypatch.setenv("KOREAAPI_DB", db)  # service reads this when db_path is None
    asyncio.run(seed(db_path=db))

    out = asyncio.run(server.get_artist_status("artist:bts"))

    assert out["found"] is True
    assert out["name"]["en_official"] == "BTS"
    item = out["status"][0]
    assert item["provenance"]["skill_score"] >= 0.8 and item["provenance"]["sources"]
    assert "citation" in item  # AEO/GEO citation travels through the MCP tool surface


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
