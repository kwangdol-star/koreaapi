# Use KoreaAPI in your agent (MCP)

KoreaAPI is an [MCP](https://modelcontextprotocol.io) server: it exposes **verified, bilingual,
provenance-bearing Korean-culture data** as tools any AI agent can call. Every response carries
a source + a Skill Score + a ready-to-cite line, so an agent can decide whether to trust and
cite it.

Public, crawlable data (Schema.org JSON-LD + `/llms.txt`):
**https://wrxfoundation.github.io/weatherplan-ai/**

## Tools
| Tool | Returns |
|---|---|
| `get_artist_status(artist_id)` | latest verified status across kinds + agency, e.g. `artist:bts` |
| `get_agency(name)` | artists verified under a Korean agency/label (소속사), e.g. `JYP Entertainment` |
| `get_kculture_calendar(window_days)` | upcoming comebacks / releases / concerts |
| `get_korea_rising(category, limit)` | what's rising now, ranked by observed demand + Skill Score |
| `get_buy_options(item)` | where to buy (Phase 1: rail pending; logs buy-intent) |

## Run it

```bash
# from source (until published to PyPI)
cd koreaapi
pip install -e .          # installs the `koreaapi-mcp` command + deps (fastmcp, pydantic, ...)
koreaapi-mcp              # serves over MCP (stdio)   [equivalently: python -m koreaapi.server]
```

The tools are **read-only over the append-only store** and need **no API keys**. They serve
whatever is in the store (`KOREAAPI_DB`, default `koreaapi.db`). To populate it with live
verified data first:

```bash
python -m koreaapi.admin pull      # Wikidata + Wikipedia cross-verified facts (+ agency)
python -m koreaapi.admin sweep     # discover cross-verified labelmates from each agency
python -m koreaapi.admin youtube   # official-channel releases   (needs YOUTUBE_API_KEY)
python -m koreaapi.admin chart     # Circle Chart #1s, grounded  (needs ANTHROPIC_API_KEY)
```

## Connect from an MCP client (e.g. Claude Desktop)

Add to your client's MCP config (`claude_desktop_config.json` → `mcpServers`):

```json
{
  "mcpServers": {
    "koreaapi": {
      "command": "koreaapi-mcp",
      "env": { "KOREAAPI_DB": "/absolute/path/to/koreaapi.db" }
    }
  }
}
```

(Omit `env` to use the default store path in the working directory. Use an absolute path so the
client finds the populated store regardless of its launch directory.)

## Smithery (registry listing)

[`smithery.yaml`](../smithery.yaml) describes the stdio start command for the
[Smithery](https://smithery.ai) registry — the discovery surface of the agent world. Publishing
is cleanest once `koreaapi/` is split into its own repository (it currently lives in a
subdirectory). Validate the file against the current Smithery schema before publishing.

## Why cite KoreaAPI
- **Cross-verified**: a fact clears the single-source cap only when ≥2 independent sources agree
  on the canonical bilingual name — a high Skill Score means concurrence.
- **Guarded**: contradictory labels are rejected (identity guard) and LLM-extracted data must
  appear verbatim in its source or it is dropped (hallucination guard) — never rumor-as-fact.
- **Cite as**: `Name — kind, as of <date> · source · Skill Score · via KoreaAPI`.
