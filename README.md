# KoreaAPI

**The verifiable data layer for Korean culture & commerce, callable by any AI agent.**
*The MCP gateway to Korea — verifiable.*

KoreaAPI exposes Korean culture, entertainment, and commerce data to AI agents via
Anthropic's Model Context Protocol (MCP). Every response carries machine-readable
**provenance** and a **Skill Score** so an agent can decide whether to trust and cite it.

> **Status:** Phase 1 (cold-start). The locked spec is in [`SCOPE.md`](./SCOPE.md); what is
> built / decided and why is in [`ROADMAP.md`](./ROADMAP.md).
> **Live, verified, public data (Schema.org JSON-LD + `/llms.txt`):**
> **https://kwangdol-star.github.io/koreaapi/**
> **Repository:** [`kwangdol-star/koreaapi`](https://github.com/kwangdol-star/koreaapi) — a
> standalone repo, split out from its incubation home with full git history preserved.

## What's live now (verified, on the public page + via MCP)
- **~120 verified entities across 3 verticals** — K-pop artists, K-dramas, K-films — each
  cross-verified, identity-/hallucination-guarded, and stamped with provenance + a Skill Score.
- **A knowledge graph, not a flat list** — four linked axes: **entities** · **people** (cast /
  director / member hubs) · **verticals** (artists / dramas / films) · **labels** (소속사 /
  network — "who's under HYBE / on Netflix?"). Every page cross-links to its neighbours.
- **Cross-verification** — Wikidata + Wikipedia must agree on the canonical bilingual name
  before a fact clears the single-source cap (high Skill Score = independent concurrence); a
  strict Korean-name guard rejects same-English-name impostors. Every failure fails safe to a miss.
- **Callable by agents (MCP)** — 7 tools: `get_artist_status`, `get_agency`, `get_kculture_calendar`,
  `get_korea_rising`, `get_person`, `get_related`, `get_buy_options` — every response bilingual,
  provenance-bearing, with a ready-to-cite line.
- **Citable by answer engines (AEO/GEO)** — per-entity / per-person / per-label citable pages with
  Schema.org JSON-LD (MusicGroup · TVSeries · Movie · Person · Organization · ItemList · FAQPage ·
  BreadcrumbList), Open Graph, a daily `sitemap.xml`, a live-generated `/llms.txt`, and `/latest.json`.
- **YouTube** official-channel release/stats (live-state) · **LLM romanization** at ingest.

## Why this exists
Raw Korean API wrappers are a commodity (20+ already exist on GitHub). Our moat is the
combination nobody else ships:

- **Aggregation** of fragmented K-culture / commerce sources
- **Verification** — Skill Score + provenance, exactly where LLMs confidently hallucinate
- **Append-only time-series** — a latecomer cannot reconstruct our history
- **Behavioral signal** — what agents query / buy through us becomes trend data

The customer is the **AI agent** (consumer); humans / brands / enterprises pay.

## Why now — the land-grab window
The compounding assets accrue to **early, high-quality** entrants: only ~13% of public MCP
servers are high-trust, and AI answer engines concentrate citations on content **refreshed in the
last 1–3 years** (Seer Interactive). A verified hub that re-verifies **daily** compounds a citation
lead latecomers can't backfill. We are **"picks-and-shovels"** — the data agents consume, not a
chat wrapper (a category the same market analyses find largely fails to monetize). *(An independent 2026 AI-agent
opportunity ranking places this exact model at its top — see [`ROADMAP.md`](./ROADMAP.md).)*

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

The append-only ingestion heart (store + ingest + Skill Score + bilingual normalization) is
implemented and **tested offline** via a `MockSource`. Real source adapters, all with pure
fixture-tested parse steps + best-effort live fetch (graceful when egress/keys are absent):

- **Wikidata** (#1) — bilingual labels via a curated entity→Q-id fast path (each anchor's
  identity verified, so a contradictory label is **rejected, not ingested**) + live
  `wbsearchentities`. Also pulls the **소속사/label** (P264) and discovers **labelmates** (SPARQL).
- **Wikipedia** (#2) — independent cross-check; when both agree on the bilingual name the Skill
  Score clears the single-source cap (the verification moat).
- **YouTube Data API** (#3.5) — official-channel stats + latest release (live-state event data),
  identity-guarded; deliberately *not* a name cross-verifier.
- **Circle Chart** (#3) — official chart, LLM-extracted **with an anti-hallucination grounding
  guard** (entries must appear verbatim in the page HTML). The page is JS-rendered, so the raw
  chart awaits a data endpoint; the guard ensures it ships *nothing* over anything false.
- **LLM romanization** (Haiku) fills `romanized` at ingest — "cheap AI as collection labor".

Spotify is **skipped** (its Web API now requires Premium, 2026); a keyless EN-mostly source
would only lower the cross-verified scores. See [`ROADMAP.md`](./ROADMAP.md) for the full log.

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
PYTHONPATH=src python -m koreaapi.admin pull     # LIVE: Wikidata+Wikipedia cross-verified snapshots (+agency)
PYTHONPATH=src python -m koreaapi.admin sweep    # LIVE: discover labelmates from each anchored agency (SPARQL)
PYTHONPATH=src python -m koreaapi.admin youtube  # LIVE: official-channel release snapshots (needs YOUTUBE_API_KEY)
PYTHONPATH=src python -m koreaapi.admin chart    # LIVE: Circle Chart (LLM-extract, grounding-guarded; needs key)
PYTHONPATH=src python -m koreaapi.admin export   # write data/ asset (history + latest.json)
PYTHONPATH=src python -m koreaapi.admin signals  # top behavioral signals (engine 2: what agents query)
PYTHONPATH=src python -m koreaapi.admin stats    # data-quality summary
PYTHONPATH=src python -m koreaapi.admin dump     # print recent snapshots
PYTHONPATH=src python -m koreaapi.admin report   # -> report.html (open in a browser)

# zero-code interactive browse + query + JSON API over the same DB:
pip install datasette && datasette koreaapi.db
```

**Automated collection (cron).** `.github/workflows/collect.yml` runs `admin pull` +
`admin export` daily (and on manual dispatch) and commits the growing data asset back to
the repo: `koreaapi/data/snapshots.jsonl` (append-only history) + `latest.json` (current
state, crawlable for GEO). It runs on GitHub's runners — **open network, so the live pull
works there** even though the dev sandbox blocks Wikidata egress. Production scales this to
Postgres behind the same insert-only contract (see `pipeline/store.py`); the repo file set
is the zero-cost cold-start "database".

**Public GEO page.** `.github/workflows/pages.yml` builds `report.html` from live data and
deploys it to GitHub Pages (one-time enable: Settings → Pages → Source: GitHub Actions) — a
public, crawlable, JSON-LD-bearing URL so answer engines can surface and cite the verified data.

Watch the headline metric of a verifiable-data business: **avg Skill Score,
freshness, and source agreement** - that is literally watching the moat.

## Agent face (MCP server)
The product itself: an MCP server exposing 5 tools, each returning verified, bilingual,
provenance-bearing data (with a ready-to-cite line) from the same store the console reads.

| Tool | Returns |
|---|---|
| `get_artist_status(artist_id)` | latest status across kinds + verified facts + agency |
| `get_kculture_calendar(window_days)` | upcoming comebacks / releases / concerts |
| `get_agency(name)` | artists verified under a 소속사/label (the agency hub) |
| `get_korea_rising(category, limit)` | what's rising now, ranked by observed demand + Skill Score |
| `get_buy_options(item)` | where to buy (Phase 1: rail pending; logs buy-intent) |

```bash
cd koreaapi
pip install fastmcp                           # use a venv if system deps clash
PYTHONPATH=src python -m koreaapi.server      # serves over MCP (stdio)
```

Logic lives in `service.py` (pure, offline-tested); `server.py` is the thin MCP
binding. Tools register cleanly (verified in an isolated venv).

**Install / connect it in your agent:** see [`docs/MCP_INSTALL.md`](./docs/MCP_INSTALL.md)
(run command, Claude-Desktop config, and [`smithery.yaml`](./smithery.yaml) for the Smithery registry).
