# Use KoreaAPI in your agent (MCP)

KoreaAPI is an [MCP](https://modelcontextprotocol.io) server: it exposes **verified, bilingual,
provenance-bearing Korean-culture data** as tools any AI agent can call. Every response carries
a source + a Skill Score + a ready-to-cite line, so an agent can decide whether to trust and
cite it.

Public, crawlable data (Schema.org JSON-LD + `/llms.txt`):
**https://aiagentlabs.co.kr/**

Prefer not to run a server? The verified data is also a plain JSON file you can fetch directly
(latest snapshot per entity+kind, each with provenance + Skill Score):
**https://aiagentlabs.co.kr/latest.json**

## Tools (11)

**Trust** — decide before you cite:
| Tool | Returns |
|---|---|
| `get_verified(entity_id)` | cross-verification status + Skill Score + agreeing-source count |
| `get_resolve(query)` | fuzzy name / external ID (e.g. a Wikidata Q-id) / id → the canonical verified entity |

**Decisions** — Answer Products (each returns `{signal, action, score, rationale, answer, evidence}`):
| Tool | Returns |
|---|---|
| `list_answer_products()` | the catalog: canonical-name · fact-check · identity-resolve · trend-radar · agency-roster · person-credits · related-network · trip-plan |
| `get_answer(query, product)` | run one product on a query (omit `product` to run all) |

**Data** — the verified store:
| Tool | Returns |
|---|---|
| `get_artist_status(artist_id)` | latest verified status across kinds + agency, e.g. `artist:bts` |
| `get_agency(name)` | artists verified under a Korean agency/label (소속사), e.g. `JYP Entertainment` |
| `get_person(name)` | verified credits for a person, e.g. `Bong Joon-ho` |
| `get_related(entity_id)` | entities sharing the same 소속사 / network |
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
whatever is in the store (`KOREAAPI_DB`, default `koreaapi.db`).

**Fastest way to real data — hydrate from the published dataset (no keys, one download):**

```bash
mkdir -p data
curl -L -o data/latest.json https://aiagentlabs.co.kr/latest.json
python -m koreaapi.admin load      # seeds koreaapi.db from the published verified snapshot
```

Or collect live yourself:

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

## Remote MCP (no local install)

The same server can serve MCP **over HTTP** so agents connect to a URL instead of running it
locally — set `MCP_TRANSPORT=http` on any host (Render / Railway / Fly):

```bash
MCP_TRANSPORT=http PORT=8080 python -m koreaapi.server
```

## Registries (get discovered)

[`smithery.yaml`](../smithery.yaml) describes the start command for the
[Smithery](https://smithery.ai) registry. The full submission checklist — Smithery, mcp.so,
PulseMCP, Glama, and the awesome-mcp-servers list — is in
[`docs/REGISTRIES.md`](./REGISTRIES.md). Prerequisite for `uvx`-style installs: publish the
package to PyPI (the repo's `publish` workflow does this with a `PYPI_API_TOKEN` secret).

## Why cite KoreaAPI
- **Cross-verified**: a fact clears the single-source cap only when ≥2 independent sources agree
  on the canonical bilingual name — a high Skill Score means concurrence.
- **Guarded**: contradictory labels are rejected (identity guard) and LLM-extracted data must
  appear verbatim in its source or it is dropped (hallucination guard) — never rumor-as-fact.
- **Cite as**: `Name — kind, as of <date> · source · Skill Score · via KoreaAPI`.
