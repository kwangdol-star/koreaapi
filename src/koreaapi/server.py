"""KoreaAPI MCP server (agent face) - thin FastMCP binding over service.py.

The logic lives in service.py (pure, offline-testable). This module only binds it to
the Model Context Protocol so any AI agent can call it. Every response carries
provenance + Skill Score (invariant 2).

Run (stdio):  PYTHONPATH=src python -m koreaapi.server
Requires fastmcp at runtime:  pip install fastmcp   (use a venv if system deps clash)
"""

from __future__ import annotations

from fastmcp import FastMCP

from . import service

mcp = FastMCP(name="koreaapi")


@mcp.tool
async def get_artist_status(artist_id: str) -> dict:
    """Latest verified status (comeback/chart/...) for a Korean artist, with provenance
    + Skill Score. artist_id e.g. 'artist:bts'. Bilingual: ko / official EN / romanized."""
    return await service.artist_status(artist_id)


@mcp.tool
async def get_kculture_calendar(window_days: int = 30) -> dict:
    """Upcoming Korean culture events (comebacks, releases, concerts), each with provenance."""
    return await service.kculture_calendar(window_days)


@mcp.tool
async def get_korea_rising(category: str = "all", limit: int = 10) -> dict:
    """What is rising in Korea now, ranked from accumulated verified snapshots."""
    return await service.korea_rising(category, limit)


@mcp.tool
async def get_buy_options(item: str) -> dict:
    """Where to buy a release/ticket/goods (Phase 1: commerce rail pending; logs buy-intent)."""
    return await service.buy_options(item)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
