# KoreaAPI — Phase 1 Scope (Locked)

> **Positioning:** The verifiable data layer for Korean culture & commerce, callable by any AI agent.
> **Tagline:** The MCP gateway to Korea — *verifiable*.
> **Status:** Phase 1 spec locked. Cold-start build.

---

## 1. Strategic thesis
Weather and raw public-data wrapping are **commodities** — already crowded (20+ Korean MCP servers exist on GitHub; one at 278★). An API wrapper is replicable in a weekend, so it is **not** a moat.

Our moat is the combination competitors are **not** doing:
- **Aggregation** of fragmented Korean culture/commerce sources
- **Verification** (Skill Score + provenance) — strongest exactly where LLMs confidently hallucinate (K-pop facts, dates, members)
- **Append-only accumulated time-series** — a latecomer cannot reconstruct our history
- **Proprietary behavioral signal** — what agents query/buy *through us* becomes trend data no one else has

First defensible claim: **not** "first Korean MCP" (taken) but **"first verifiable K-culture/entertainment + commerce data layer for AI agents."**

## 2. Customer model
- **Consumer = the AI agent.** Design for machine consumption: structured, decision-ready, token-efficient, machine-readable provenance.
- **Payer = human builders / brands / enterprises** (or the agent wallet via x402, later).
- The product **is** the MCP tool surface + verified data + Skill Score. The landing page is sales collateral for the human builder.

## 3. Revenue flywheel (engines ① + ②)
K-culture/entertainment current-state = the **magnet** (attention, citations, "Korea = us" default).

```
magnet → buy-intent signal → ① commerce commission
                          ↘  ② trend intelligence (B2B subscription)
② improves ①'s conversion · ①'s transactions generate ②'s raw signal · ②'s accumulation is itself the product
```

Competitors with raw wrappers have **no transactions → no behavioral signal → cannot build the trend product.** That is the compounding moat.

**Cold-start sequence (no gatekeeper first):**
1. Magnet + signal capture + Beehiiv "Korea Rising" digest — **zero approvals** (free official APIs + Beehiiv).
2. Light commerce rails — Skimlinks/Sovrn + Amazon Associates links (no sales threshold; site review only). Commission optional; **buy-intent signal accrues even at $0 commission.**
3. Once traffic qualifies → Coupang Partners API, ticketing partnerships, paid trend API/subscription.

## 4. Phase 1 components
| # | Component | Role |
|---|---|---|
| **A** | Ingestion pipeline (scheduled · tiered · LLM-extract + cross-verify · **append-only** · Skill Score per record) | Asset-accumulation engine — **the heart** |
| **B** | Accumulation DB (append-only time-series: releases, charts, events, prices + behavioral signal) | Moat + trend raw material |
| **C** | MCP server, 4 tools (agent product surface) | Every response carries provenance + Skill Score |
| **D** | Landing + Beehiiv waitlist | Traffic + unlocks affiliate approval |
| **E** | "Korea Rising" weekly digest (generated from B) | Trend product seed + marketing |

### MCP tools (4)
1. `get_kculture_calendar(window)` — comebacks, releases, concerts, fan events, awards. Verified, sourced, confidence-scored. **[magnet]**
2. `get_artist_status(artist)` — chart positions, latest release, next event, verified facts (members, agency, debut). **[magnet + anti-hallucination]**
3. `get_buy_options(item)` — where to buy + price + availability + affiliate link. **[commerce → commission; buy-intent signal]**
4. `get_korea_rising(category)` — what is rising in Korea now, from aggregated + behavioral signal. **[trend → subscription]**

### Data sources (Phase 1 — zero / light approval)
Spotify (KR) · YouTube · Wikidata/Wikipedia · Circle Chart (public) · public announcements via **LLM extraction + cross-verification**.
Official APIs first; **scraping minimized / last-resort** — gray-source data undermines the verification moat and can be cut off.

### Accumulation cadence — **append, don't overwrite**
> Overwrite = wrapper. Append timestamped snapshots = an asset a latecomer cannot reconstruct.

| Data | Cadence | Why |
|---|---|---|
| Charts / rankings | **Daily (1–2×)** | high-velocity / freshness |
| Schedule / events | **Daily sweep** | catch announcements & changes |
| Facts (members, discography, agency) | Weekly / on-change | slow, stable |
| Price / availability | Daily or on-query + cache | commerce |
| Behavioral signal (queries, clicks) | **Continuous** | trend raw material |

Unattended (cron) + **graceful degradation**: if a source fails, lower confidence and record it — don't break. Daily collection ≠ daily babysitting.

## 5. Bilingual / global data model
**Yes — keep both, structured, per record. Korean = canonical source-of-truth (provenance anchor); English = distribution/consumption layer.**

1. **Keep the Korean original.** Verification cites what the source *actually* said; English-only would break provenance. Korean is authoritative for names/announcements and enables re-verification.
2. **English-first output** for human-readable fields (`summary`, `recommendation`, descriptions) — global agents consume in English; this is how the data *spreads* and gets cited.
3. **Names carry three forms:** `name_ko`, `name_en_official`, `name_romanized`. Prefer the **official** English/stage name (방탄소년단 → "BTS"), never naive translation; romanization for search/pronunciation.
4. **Translation provenance:** every translated field tagged `source: official | llm | human` + confidence → feeds Skill Score. Official names score higher than LLM-guessed.
5. **Translate at ingest, cache forever** (append-only). LLM (Haiku) does it once inside pipeline A — cheap, never at query time.
6. **Discovery layer in English:** `llms.txt`, tool names/descriptions, docs, landing — so global agents find and choose us.

**Why this is itself a moat:** correct Korean↔English (official names, romanization, disambiguation, cultural terms) is genuinely hard — global competitors mishandle it, Korea-only players don't build for global. A wrong translated fact that spreads = reputational damage; a correct, sourced one = citation moat. **Bilingual-verified IS the product.**

Example record (conceptual):
```json
{
  "entity_id": "artist:bts",
  "name_ko": "방탄소년단",
  "name_en_official": "BTS",
  "name_romanized": "Bangtan Sonyeondan",
  "event": { "type": "comeback", "date": "2026-06-13",
             "title_ko": "…", "title_en": "…", "title_en_source": "official" },
  "summary_en": "BTS comeback scheduled 2026-06-13; …",
  "provenance": {
    "sources": ["Circle Chart 2026-06-01 KST", "agency notice"],
    "skill_score": 0.92, "confidence": "high",
    "translation": { "source": "official", "confidence": "high" },
    "fetched_at": "2026-06-02T00:00:00Z"
  }
}
```

## 6. Revenue wiring (Phase 1 = prove, not perfect)
- **Commerce:** Skimlinks/Amazon links in `get_buy_options`; capture buy-intent even at $0 commission.
- **Trend:** Beehiiv "Korea Rising" digest seeds the subscription; promote to API/paid later.

## 7. Out of scope (later layers)
Coupang Partners API · ticketing / Circle Chart official partnerships · K-beauty · **travel/local verticals — restaurant (맛집) reservations = designated first travel-local vertical, hung off the K-culture magnet (concert venue → nearby restaurant → booking commission); reuses the same Name/Provenance/append-only contract** · enterprise (KYB, English-DART, MFDS compliance) · x402 micropayments · full geocoding · weather (free hook only).

> **Phase 2 plan (web3 agent-payments via x402, GEO, portable reputation) → [`ROADMAP.md`](./ROADMAP.md).**
> Grounded in the 2026-05-27 Agent×Blockchain conference: x402 proves *payment*, not
> *fulfilment* — KoreaAPI's Skill Score is that missing proof, so agent payments **reinforce**
> the verification moat rather than dilute it. (Payment rail = USDC + x402, not "receive BNB";
> do **not** launch a token.)

*Candidate tooling (revisit at the noted phase, vet first): `postgres` skill + Composio Supabase/Vercel connectors for deploy; Composio Stripe/Shopify + analytics (PostHog/Segment) for the commerce / behavioral-signal engines - but prefer **direct SDKs for core payment rails** (control, margin, moat); use connectors only for non-core, long-tail integrations.*

## 8. Definition of Done (Phase 1)
- [ ] Daily ingestion running unattended; verified snapshots **appended** (time-series asset begins)
- [ ] 4 MCP tools live; every response has Skill Score + provenance + **bilingual fields**
- [ ] Landing live + waitlist; first "Korea Rising" digest sent
- [ ] ≥1 commerce link rail active (Skimlinks/Amazon); buy-intent captured

## 9. Cost & maintenance principle
Near-zero data cost (free official APIs); ~$50–150/mo infra+LLM early. The only real maintenance is source drift, capped by: LLM extraction (absorbs layout change) · official sources first · append-only · graceful degradation. **Money is not the risk; the append-only asset is the point.**

## 10. Two faces over one source of truth
The product is agent-facing, but the owner needs a cockpit. Build **one source of
truth** (the append-only store + provenance) with two read faces:
- **Agent face** = the MCP server (decision-ready, machine-readable).
- **Human face** = a read-only ops console: browse snapshots, watch data quality
  (Skill Score / freshness / source agreement), spot-correct (a human override writes
  a NEW snapshot tagged `translation.source = human` - still append-only).

Never a second data path. Phase 1 console: `python -m koreaapi.admin report` (static
`report.html`) + `datasette koreaapi.db`; later a proper dashboard and a trends /
behavioral-signal view (engine ②).

---

> **Hosting note:** Temporarily committed inside the `weatherplan-ai` repo under `koreaapi/`
> because this session's GitHub token cannot create a new repo. Move to a dedicated
> `koreaapi` repository when available (git history transfer or subtree split).
