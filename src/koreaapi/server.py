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
async def get_agency(name: str) -> dict:
    """Artists verified under a Korean agency/label (소속사), e.g. 'JYP Entertainment' or 'HYBE'.
    The agency hub: answers 'who is under <agency>?' from cross-verified records, with provenance."""
    return await service.agency(name)


@mcp.tool
async def get_korea_rising(category: str = "all", limit: int = 10) -> dict:
    """What is rising in Korea now, ranked from accumulated verified snapshots."""
    return await service.korea_rising(category, limit)


@mcp.tool
async def get_person(name: str) -> dict:
    """Verified credits for a Korean-culture person (director / actor / idol member), aggregated
    across every work that credits them, each with provenance + Skill Score. Answers 'what did
    X direct / act in?'. `name` e.g. 'Bong Joon-ho' (display name or slug)."""
    return await service.person(name)


@mcp.tool
async def get_related(entity_id: str) -> dict:
    """Entities related via the same hub edge — artists sharing a 소속사, or dramas/films sharing an
    original network/platform — with provenance. Answers 'what else is on Netflix / under HYBE?'.
    entity_id e.g. 'artist:bts' or 'drama:squidgame'."""
    return await service.related(entity_id)


@mcp.tool
async def get_verified(entity_id: str) -> dict:
    """Cross-verification status of an entity — the trust moat made queryable. Returns how many
    INDEPENDENT sources agreed (Wikidata · Wikipedia · MusicBrainz · OpenStreetMap · TMDB), the
    Skill Score + confidence, the source list, and cross_verified / triple_verified flags, so an
    agent can decide trust before citing. entity_id e.g. 'artist:bts' or 'place:gyeongbokgung'."""
    return await service.verified(entity_id)


@mcp.tool
async def get_resolve(query: str) -> dict:
    """Resolve a fuzzy Korean-culture NAME, an external ID (e.g. a Wikidata Q-id), or a canonical
    entity_id to THE verified KoreaAPI entity — with its bilingual name, cross-verification status +
    Skill Score, content hash, and every external ID. The reconciliation / ID-spine tool: map whatever
    you hold onto a trusted entity before citing. query e.g. '빈센조', 'Vincenzo', 'Q16741113'."""
    return await service.resolve(query)


@mcp.tool
async def get_buy_options(item: str) -> dict:
    """Where to buy a release/ticket/goods (Phase 1: commerce rail pending; logs buy-intent)."""
    return await service.buy_options(item)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
