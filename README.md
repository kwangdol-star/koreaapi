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
normalization) is implemented and **tested offline** via a `MockSource`. Source
adapters (Spotify / Wikidata / Circle Chart) and the MCP server are next.
