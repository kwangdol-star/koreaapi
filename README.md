# KoreaAPI

**The verifiable data layer for Korean culture & commerce, callable by any AI agent.**
*The MCP gateway to Korea — verifiable.*

KoreaAPI exposes Korean culture, entertainment, and commerce data to AI agents via
Anthropic's Model Context Protocol (MCP). Every response carries machine-readable
**provenance** and a **Skill Score** so an agent can decide whether to trust and cite it.

> **Status:** Phase 1 (cold-start). The locked spec is in [`SCOPE.md`](./SCOPE.md).
> **Hosting:** Temporarily inside the `weatherplan-ai` repo under `koreaapi/`; to be
> moved to its own repository later.

## Why this exists
Raw Korean API wrappers are a commodity (20+ already exist on GitHub). Our moat is the
combination nobody else ships:

- **Aggregation** of fragmented K-culture / commerce sources
- **Verification** — Skill Score + provenance, exactly where LLMs confidently hallucinate
- **Append-only time-series** — a latecomer cannot reconstruct our history
- **Behavioral signal** — what agents query / buy through us becomes trend data

The customer is the **AI agent** (consumer); humans / brands / enterprises pay.

## Revenue flywheel (engines ① + ②)
K-culture current-state is the magnet. ① commerce commission + ② trend-intelligence
subscription reinforce each other: transactions generate the behavioral signal that
becomes the trend product, which improves commerce conversion. See [`SCOPE.md`](./SCOPE.md) §3.

## The heart: append-only ingestion (component A)
```
fetch → LLM-extract → cross-verify → bilingual-normalize → append (+ Skill Score)
```
**Overwrite = wrapper. Append timestamped snapshots = an asset.**

## Bilingual by design
Korean = canonical (provenance anchor). English = distribution layer.
Names carry `ko` / `en_official` / `romanized`. See [`SCOPE.md`](./SCOPE.md) §5.

## Layout
```
koreaapi/
├── SCOPE.md                 # locked Phase 1 spec
├── llms.txt                 # agent-facing description
├── pyproject.toml
└── src/koreaapi/
    ├── models.py            # bilingual records + Provenance (the data contract)
    ├── skill_score.py       # transparent 0–1 quality score
    ├── pipeline/            # component A: append-only ingestion (the heart)
    │   ├── ingest.py        # fetch→extract→verify→translate→append
    │   ├── store.py         # APPEND-ONLY store (the moat)
    │   └── scheduler.py     # tiered collection cadence
    └── sources/             # source adapters (official APIs first)
        └── base.py
```

## Dev
```bash
cd koreaapi
uv sync                      # or: pip install pydantic pytest

# run the offline end-to-end pipeline test (no API keys / network needed)
PYTHONPATH=src python -m pytest tests -q
```

The append-only ingestion heart (store + ingest + Skill Score + bilingual
normalization) is implemented and **tested offline** via a `MockSource`. The first
real adapter — **Wikidata** — is implemented: a curated entity→Q-id fast path plus
live `wbsearchentities` resolution, with both PARSE steps fixture-tested offline and a
**live smoke test** (`tests/test_wikidata_live.py`) that auto-skips when egress is
unavailable. Spotify / Circle Chart adapters are next.

> **Egress note:** the live pull needs outbound access to `*.wikidata.org`. In the
> web/sandbox environment egress is allowlist-gated — if Wikidata isn't allowlisted the
> live test skips (HTTP 403 `host_not_allowed`) while the offline parser tests still
> cover correctness.

## Viewing & managing it (human console)
The product is agent-facing (MCP), but you (human) need a cockpit. There are
**two faces over one source of truth** (the append-only store): the MCP server for
agents, and a read-only console for you.

```bash
cd koreaapi
PYTHONPATH=src python -m koreaapi.admin seed     # populate koreaapi.db (offline sample)
PYTHONPATH=src python -m koreaapi.admin stats    # data-quality summary
PYTHONPATH=src python -m koreaapi.admin dump     # print recent snapshots
PYTHONPATH=src python -m koreaapi.admin report   # -> report.html (open in a browser)

# zero-code interactive browse + query + JSON API over the same DB:
pip install datasette && datasette koreaapi.db
```

Watch the headline metric of a verifiable-data business: **avg Skill Score,
freshness, and source agreement** - that is literally watching the moat.

## Agent face (MCP server)
The product itself: an MCP server exposing 4 tools, each returning verified, bilingual,
provenance-bearing data from the same store the console reads.

| Tool | Returns |
|---|---|
| `get_artist_status(artist_id)` | latest comeback/chart status + verified facts |
| `get_kculture_calendar(window_days)` | upcoming comebacks / releases / concerts |
| `get_korea_rising(category, limit)` | what's rising now, ranked from accumulated snapshots |
| `get_buy_options(item)` | where to buy (Phase 1: rail pending; logs buy-intent) |

```bash
cd koreaapi
pip install fastmcp                           # use a venv if system deps clash
PYTHONPATH=src python -m koreaapi.server      # serves over MCP (stdio)
```

Logic lives in `service.py` (pure, offline-tested); `server.py` is the thin MCP
binding. Tools register cleanly (verified in an isolated venv).
