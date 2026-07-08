"""Offline smoke test for the MCP server - the agent product surface.

server.py is a thin FastMCP binding over service.py; this verifies the tools register and
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
    "get_agency",
    "get_korea_rising",
    "get_person",
    "get_related",
    "get_verified",
    "get_history",         # the time moat: append-only timeline + change events
    "get_changes",         # the freshness feed, queryable
    "get_certified",       # the supply-side lock: official rights-holder certifications
    "get_resolve",
    "get_buy_options",
    "list_answer_products",  # engine 3: the Answer Products catalog
    "get_answer",            # engine 3: run one product (or all) -> decision envelope
}


def _tool_names() -> set[str]:
    res = server.mcp.list_tools()
    if inspect.isawaitable(res):
        res = asyncio.run(res)
    return {t.name for t in res}


def test_server_registers_its_tools():
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


def test_graph_tools_are_bound_and_callable(monkeypatch, tmp_path):
    # The new graph tools register and return a well-formed dict end to end (empty store -> not
    # found, but no crash). Behavior is covered in depth by test_service.py.
    monkeypatch.setenv("KOREAAPI_DB", str(tmp_path / "empty.db"))
    out_p = asyncio.run(server.get_person("Bong Joon-ho"))
    out_r = asyncio.run(server.get_related("artist:bts"))
    assert out_p["found"] is False and out_r["found"] is False


def test_answer_product_tools_are_bound(monkeypatch, tmp_path):
    # engine 3: the catalog lists products, and get_answer returns the decision envelope end to end
    # (empty store -> NOT_FOUND, but a well-formed envelope, no crash). Depth in test_answers.py.
    monkeypatch.setenv("KOREAAPI_DB", str(tmp_path / "empty.db"))
    cat = asyncio.run(server.list_answer_products())
    assert cat["count"] >= 5 and any(p["id"] == "canonical-name" for p in cat["products"])
    env = asyncio.run(server.get_answer("Vincenzo", "canonical-name"))
    assert env["signal"] == "NOT_FOUND" and env["product"] == "canonical-name"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
