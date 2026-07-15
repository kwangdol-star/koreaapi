# KoreaAPI

**The verifiable data layer for Korean culture & commerce, callable by any AI agent.**
*The MCP gateway to Korea — verifiable.*

KoreaAPI exposes Korean culture, entertainment, and commerce data to AI agents (via Anthropic's
Model Context Protocol and a plain HTTP API) and to answer engines (as a crawlable, JSON-LD-bearing
site). Every response carries machine-readable **provenance** and a **Skill Score** so an agent can
decide whether to trust and cite it — verification, not brand.

> **Live:** **https://aiagentlabs.co.kr/** (한국어: [/ko/](https://aiagentlabs.co.kr/ko/)) ·
> live health/coverage: [/status.json](https://aiagentlabs.co.kr/status.json)
> **Deploy repo:** [`kwangdol-star/koreaapi`](https://github.com/kwangdol-star/koreaapi)
> **Docs:** what we believe [`PRINCIPLES.md`](./PRINCIPLES.md) · the locked spec [`SCOPE.md`](./SCOPE.md) ·
> decision log [`ROADMAP.md`](./ROADMAP.md) · **how it runs itself [`OPERATIONS.md`](./OPERATIONS.md)** ·
> visual doctrine [`DESIGN_HERITAGE.md`](./DESIGN_HERITAGE.md)

## What's live (as of 2026-07)

- **5,000+ verified entities across 40 vertical hubs** — K-pop artists · dramas · films · webtoons ·
  places · food · companies · brands · books · history · heritage · folklore · hospitals · regions ·
  games · shows · animation · universities · classics · fashion · festivals · awards · holidays ·
  liquor · parks · museums · temples · stadiums · airports · theaters · theme parks · ski resorts ·
  islands · hot springs · beaches · athletes · actors · songs · concepts · people. Live counts:
  [homepage](https://aiagentlabs.co.kr/) / `status.json`.
- **A knowledge graph, not a flat list** — entities ↔ **people** (1,600+ credit hubs) ↔ **labels**
  (250+ 소속사/network hubs, EN + `/ko/`) ↔ **regions**, plus a **physical-proximity graph**: verified
  coordinates (Wikidata P625) power `nearby` (great-circle km), **walkable clusters** (≤3 km of an
  anchor), and map-ready trip plans — grounded spatial data for embodied agents.
- **Verification as the product** — a fact clears the single-source cap only when ≥2 INDEPENDENT
  sources agree on the canonical bilingual name; ≥3 = triple-verified; rights-holder **certification**
  sits above that. Identity/hallucination guards fail to a MISS, never a wrong record. Where sources
  disagree, the page SHOWS the reconciliation (source-disagreement notes). Every record carries a
  content hash chained in a tamper-evident, Bitcoin-anchorable [integrity log](https://aiagentlabs.co.kr/integrity.json).
- **Callable by agents** — **16 MCP tools** + HTTP `/v1/*` (OpenAPI 3.1), including `ask` (free-text →
  routed to one of **11 Answer Products**: canonical-name · fact-check · identity-resolve · trend-radar ·
  agency-roster · person-credits · related-network · trip-plan · food-guide · **compare** ·
  **evidence-pack**). Batch lane (`/v1/batch`, ≤100 ids), machine-actionable errors, autonomous-agent
  terms in [`agents.json → autonomous_use`](https://aiagentlabs.co.kr/agents.json), x402 pay-per-call
  rail (dormant until a wallet key is set).
- **Citable by answer engines (AEO/GEO)** — per-entity/person/label pages (EN + `/ko/`) with typed
  Schema.org JSON-LD (+ FAQPage led by a grounded "What is X?", sameAs, alternateName, dateModified,
  isPartOf Dataset, license, TouristTrip on guides), **region & dietary food guides**, `/whats-new.html`
  (verified change events — the freshness moat), **site search** over every entity/person/label,
  `/llms.txt` + full corpus `/llms-full.txt` + per-vertical `/llms-<vertical>.txt` chunks, RSS/JSON
  feeds, daily sitemap, embeddable "Verified by KoreaAPI" badges.

## Why this exists

Raw Korean API wrappers are a commodity (20+ on GitHub). The moat is the combination:
**aggregation** of fragmented sources · **verification** (provenance + Skill Score exactly where LLMs
hallucinate) · an **append-only time-series** a latecomer can't backfill · **behavioral signal**
(what agents ask becomes the trend product). The customer is the AI agent; humans/brands pay.
See [`PRINCIPLES.md`](./PRINCIPLES.md).

## The heart: append-only ingestion

```
fetch → cross-verify (identity-guarded) → bilingual-normalize → enrich (grounded) → append + Skill Score
```

**Overwrite = wrapper. Append timestamped snapshots = an asset.** Korean is canonical; English is the
distribution layer (`ko` / `en_official` / `romanized` on every name).

Cross-check sources (each self-scoped to the verticals it's competent in): **Wikidata · Wikipedia ·
MusicBrainz · OpenStreetMap · TMDB · KTO TourAPI · KOSIS · Open Library**, plus dormant official
rails that self-activate when a key is added: **KOPIS** (공연예술통합전산망, theaters) and **KHS**
(국가유산청, heritage). YouTube (official-channel live state) and Circle Chart (LLM-extracted with a
verbatim grounding guard) ride alongside. LLM labor (Haiku) is used ONLY where grounding can gate it:
romanization, Wikipedia-lead fact/alias extraction, chart extraction, free-text routing.

## Self-running operations (see [`OPERATIONS.md`](./OPERATIONS.md))

- **collect** (GitHub Actions, every 6h) — roster pull + **refresh of the stalest 400** discovered
  entities (half-TTL threshold, stride-sampled so a dead upstream can't starve the pool, no-downgrade
  floor) + SPARQL/bulk discovery + store-wide type audit + prune. The DB accumulates via the Actions
  cache (out of git).
- **pages** (on push + daily + after collect) — regenerates every surface from the live store, then a
  **pre-deploy gate** (`verifysite`) validates the assembled site and fails the build rather than
  deploy a broken/skeleton site (Pages keeps the last good deployment).
- Freshness is observable: `status.json → stale / refresh_pool / oldest_snapshot_days / geo_coverage`.

## Quickstart

```bash
uv sync                                        # or: pip install -e .
PYTHONPATH=src python -m pytest tests -q       # ~350 offline tests, no keys/network needed

PYTHONPATH=src python -m koreaapi.admin seed   # offline sample data
PYTHONPATH=src python -m koreaapi.admin report # -> report.html (the public page, locally)
PYTHONPATH=src python -m koreaapi.server       # the MCP server (stdio)
PYTHONPATH=src uvicorn koreaapi.api:app        # the HTTP API (see /openapi.json)
```

Agent-side install (Claude Desktop config, Smithery): [`docs/MCP_INSTALL.md`](./docs/MCP_INSTALL.md).
Live collection commands (`pull` / `refresh` / `sweep` / `discover` / `audit` / `verifysite` …) and
what they do: [`OPERATIONS.md`](./OPERATIONS.md).

## MCP tools (16)

| Group | Tools |
|---|---|
| Trust | `get_verified` · `get_resolve` · `get_certified` · `get_history` (append-only timeline) |
| Decisions | `ask` (free-text router) · `get_answer` (11 Answer Products) · `list_answer_products` |
| Data | `get_artist_status` · `get_agency` · `get_person` · `get_related` (+`nearby` km) · `get_kculture_calendar` |
| Signal | `get_korea_rising` (demand-ranked) · `get_changes` (freshness feed) · `get_metrics` · `get_buy_options` |

Logic lives in `service.py` / `answers.py` (pure, offline-tested); `server.py` / `api.py` are thin
bindings over the same store.

## Layout

```
koreaapi/
├── OPERATIONS.md / PRINCIPLES.md / SCOPE.md / ROADMAP.md / DESIGN_HERITAGE.md
├── .github/workflows/       # collect (6h) · pages (build + verifysite gate) · test · publish
└── src/koreaapi/
    ├── models.py             # bilingual records + Provenance (the data contract)
    ├── skill_score.py        # transparent 0–1 quality score
    ├── pipeline/             # append-only store (+ latest_all batch reads) · ingest · cadence
    ├── sources/              # Wikidata · Wikipedia · MusicBrainz · OSM · TMDB · KTO · KOSIS ·
    │                         #   OpenLibrary · KOPIS/KHS (dormant) · YouTube · CircleChart
    ├── service.py            # the verified read layer (resolve/related/nearby/…)
    ├── answers.py            # Answer Products + the ask router
    ├── enrich.py/romanize.py # grounded LLM labor
    ├── certify.py/integrity.py/badge.py/license.py
    ├── admin.py              # console + the entire static-site generator
    └── api.py / server.py    # HTTP + MCP faces
```
