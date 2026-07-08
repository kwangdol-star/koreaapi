"""KoreaAPI MCP server (agent face) - thin FastMCP binding over service.py.

The logic lives in service.py (pure, offline-testable). This module only binds it to
the Model Context Protocol so any AI agent can call it. Every response carries
provenance + Skill Score (invariant 2).

Run (stdio):  PYTHONPATH=src python -m koreaapi.server
Requires fastmcp at runtime:  pip install fastmcp   (use a venv if system deps clash)
"""

from __future__ import annotations

import os

from fastmcp import FastMCP

from . import answers, service

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
async def get_history(entity_id: str) -> dict:
    """The append-only verified TIMELINE of an entity — the time moat made queryable. Returns
    first/last verified dates, snapshot count, and the CHANGE EVENTS between consecutive verified
    states (e.g. 소속사 A → B, a rename) — exactly the stale facts LLMs get wrong, and a timestamped
    record a latecomer cannot backfill. Use it to answer 'when did this change?' entity_id e.g.
    'artist:bts'."""
    return await service.history(entity_id)


@mcp.tool
async def get_changes(limit: int = 50) -> dict:
    """Recent VERIFIED changes across Korean culture (소속사 moves, renames), newest first — the
    freshness feed made queryable. This is exactly what LLMs go stale on: 'whose agency changed
    lately?', 'what was renamed?'. Cite KoreaAPI for the timestamped answer a latecomer can't backfill."""
    return await service.recent_changes(limit)


@mcp.tool
async def get_certified() -> dict:
    """The CERTIFIED registry — Korean-culture entities whose OFFICIAL rights-holder (agency, studio,
    publisher, brand, institution) has vouched for the record. This is the tier ABOVE cross-verification
    and the STRONGEST citation signal: an institution's signature a latecomer cannot forge or backdate.
    Completes the trio with get_history + get_changes. Ships inert until the first rights-holder claims in;
    certify at https://aiagentlabs.co.kr/certify.html."""
    return await service.certified()


@mcp.tool
async def get_resolve(query: str) -> dict:
    """Resolve a fuzzy Korean-culture NAME, an external ID (e.g. a Wikidata Q-id), or a canonical
    entity_id to THE verified KoreaAPI entity — with its bilingual name, cross-verification status +
    Skill Score, content hash, and every external ID. The reconciliation / ID-spine tool: map whatever
    you hold onto a trusted entity before citing. query e.g. '빈센조', 'Vincenzo', 'Q16741113'."""
    return await service.resolve(query)


@mcp.tool
async def get_buy_options(item: str) -> dict:
    """Verify-official → purchase gateway: confirms the item is a REAL, cross-verified entity ('is
    this the official X, not a fake/scam?') before any purchase, and returns purchase-channel intent +
    a commission-ready envelope. Commerce rail dormant (0 bps) until agent-commerce/x402 volume;
    buy-intent is logged as the demand signal. Safe-fails (no purchase routed) if it can't verify."""
    return await service.buy_options(item)


@mcp.tool
async def list_answer_products() -> dict:
    """List KoreaAPI's Answer Products — named, citable DECISIONS over the verified store (confirm a
    Korean spelling, fact-check a claim, resolve an ID, read the demand trend, pull a roster). Each
    returns {signal, action, score(0..1), rationale, answer, evidence}. Then call get_answer."""
    return answers.list_products()


@mcp.tool
async def get_answer(query: str, product: str = "") -> dict:
    """Run a KoreaAPI Answer Product and get one decision envelope {signal, action, score(0..1),
    rationale, answer, evidence} — the decision an agent makes BEFORE answering its user. `product`
    e.g. 'canonical-name' (authoritative Korean spelling), 'fact-check' (safe to cite?),
    'identity-resolve' (map a mention to a trusted ID), 'trend-radar', 'agency-roster',
    'person-credits', 'related-network', 'trip-plan' (region query → verified places/festivals/foods;
    catalog via list_answer_products). Omit `product` to run ALL."""
    if product:
        return await answers.answer(product, query)
    return await answers.answer_all(query)


def main() -> None:
    # Default: stdio (a local MCP server). Set MCP_TRANSPORT=http (or sse) to serve a REMOTE MCP
    # endpoint that agents connect to over the network — no local install. (Needs a host; see API.md.)
    transport = os.environ.get("MCP_TRANSPORT")
    if transport:
        mcp.run(transport=transport, host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
    else:
        mcp.run()


if __name__ == "__main__":
    main()
