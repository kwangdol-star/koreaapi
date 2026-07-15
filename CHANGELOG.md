# Changelog

## 0.3.0 — 2026-07

The agent-economy release: grounded AI labor, a free-text front door, the physical-proximity graph,
Korean-surface parity, a self-healing freshness engine, and deploy safety.

### Agent surface
- **`ask`** — free-text question → routed to the right Answer Product and run (LLM router with a pure
  keyword fallback; the routing decision is logged as demand signal).
- New Answer Products: **evidence-pack** (the paste-ready citation bundle), **compare** (X vs Y, side
  by side, strictly from verified records), **trip-plan** is now map-ready (verified coordinates on
  items + walkable ≤3 km clusters), **related** gains `nearby` (great-circle km from verified P625).
- Machine-actionable HTTP errors (404/405/500 carry the next action), cache headers for agent fleets,
  `agents.json → autonomous_use` (terms for autonomous/spawned agents, incl. downstream
  re-verification via content_hash + integrity chain), the manifest also at `/.well-known/agent.json`.
- ~18x faster serving reads: every store scan collapsed to one window-function query
  (`store.latest_all`).

### Grounded AI labor (never a hallucination path)
- **enrich.py** — structured facts + alternate names extracted from the cited Wikipedia lead; every
  value must appear literally in the abstract; run-once per entity with self-healing on transient
  failures. Aliases widen `resolve`, site search, and JSON-LD `alternateName`, and render as
  "Also known as" (EN/KO).

### Crawlable/citable surfaces (AEO/GEO)
- Region travel guides + dietary food guides (EN + `/ko/`), walkable-cluster sections with honest
  anchor-relative geometry + schema.org **TouristTrip**, `/whats-new.html` (verified change events),
  **site search** over every entity/person/label hub (+ `?q=` deep links), per-vertical corpus chunks
  (`/llms-<vertical>.txt`), grounded "What is X?" FAQ on every entity page, richer JSON-LD
  (dateModified · isPartOf · license · identifier · alternateName), custom 404, source-disagreement
  notes ("shown, not hidden"), Korean label hubs (`/ko/label/`) and full KO-page parity.

### Data engine & ops
- **refresh** — re-verifies the stalest discovered entities every collect tick (half-TTL threshold,
  oldest-first, stride-sampled against starvation, a no-downgrade ≥2-source floor, verified-geo
  carry-forward). Fixes the "everything goes stale" failure mode.
- **verifysite** — a pre-deploy gate on the assembled site; a broken/skeleton build fails instead of
  deploying (Pages keeps the last good deployment).
- New dormant official source: **KHS (국가유산청)** for heritage/temples/palaces (key-gated, inert).
- `status.json` freshness + geo-coverage observability; OPERATIONS.md (the operator's map); README
  rewritten to match the shipped system.

## 0.2.0 and earlier

See `ROADMAP.md` for the decision log (Phase 1 → Phase 2 source expansion, verification tiers,
integrity chain, certification rail, x402, the geo verticals, discovery engine).
