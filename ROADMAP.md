# KoreaAPI — Roadmap & Decisions Log

> Durable memory for the project. Companion to [`SCOPE.md`](./SCOPE.md) (locked Phase 1
> spec) and [`PRINCIPLES.md`](./PRINCIPLES.md) (doctrine). This file records **what is
> built, what was decided and why, and what is next** — so the rationale survives across
> sessions. Append, don't rewrite history (same spirit as the data store).

---

## Phase 1 — status (built & verified)

| Area | Status |
|---|---|
| Append-only ingestion heart + Skill Score + bilingual model | ✅ implemented, offline-tested |
| Two faces: MCP server (agent, smoke-tested) + admin console (human) | ✅ |
| Wikidata adapter (real source #1): live `wbsearchentities` + Wikimedia-compliant UA | ✅ |
| **Cross-verification (real source #2 = Wikipedia)**: ingest agrees on the canonical name (not prose) → two independent sources concur → Skill Score clears the 0.7 single-source cap (→ ~1.0) | ✅ — the verification moat, live |
| **Identity guard** (anti-poison): reject a label that contradicts a curated anchor | ✅ — caught a real bug in production |
| Live-verified Q-ids | ✅ BTS `Q13580495` · NewJeans `Q113189277` · aespa `Q100877982` |
| **Artist roster (6)**: + BLACKPINK · LE SSERAFIM · Stray Kids — Q-ids resolved LIVE on GitHub (never hardcoded), identity-guarded against the roster name | ✅ |
| **LLM romanization** (Haiku fills `romanized` at ingest — "cheap AI as collection labor"; best-effort, skipped without key) | ✅ |
| `admin pull` — turnkey live ingestion | ✅ first real external data ingested (3/3) |
| AEO/GEO surface: JSON-LD in `report.html` + `citation` field in MCP output | ✅ |
| Cold-start data infra: `admin export` (JSONL + latest.json) + daily GitHub Actions collector | ✅ (collector runs on open-network runners → solves the sandbox egress block) |
| **Public GEO page deployed (GitHub Pages, built from live data)** | ✅ **LIVE → https://wrxfoundation.github.io/weatherplan-ai/** |
| **Behavioral signal (engine ②)**: queries + buy-intent logged append-only; `korea_rising` ranks by observed demand; `admin signals` | ✅ |
| **CI**: `.github/workflows/test.yml` runs `pytest` + `ruff` on push (the suite is now gated) | ✅ |
| Production Postgres backend (behind the same insert-only contract) | ⬜ planned (scale step) |

Tests: 18 passed, 2 live-skip (egress); ruff clean. Tracked on PR #1.

---

## Key decisions (and why)

1. **Verification is the product, not the data.** Wikidata labels are a commodity the model
   already knows; the value is the guard that caught `Q484203 = "Arborka"` (a wrong curated
   Q-id) before it could poison the store. — PRINCIPLES invariant 2.
2. **Don't compete with Wikipedia on static facts** (we'd lose — free + in every training
   set). Win on *live-state + verification + append-only history + behavioral signal +
   transaction-attached revenue*.
3. **Community data (theqoo / Threads / forums) = a trend SIGNAL, not a verified fact.**
   Ingest as `confidence: low` + `provenance: community, unverified`; cross-verify against an
   official source before promoting to fact. Scraping is last-resort (gray source — see
   SCOPE §4). The signal feeds engine ② (trend), it never ships as ground truth.
4. **Cold-start sequence first** (free magnet + GEO + affiliate buy-intent signal). Money
   rails come after traffic/agent demand exists.

---

## Phase 2 — web3 agent-payments, GEO, reputation (LATER; trigger = traffic / agent demand)

> **Source & rationale:** *AI Agent × Blockchain Economy* conference, 2026-05-27
> (`docs/research/agent-blockchain-conference-2026-05-27.html`) + SCOPE §2/§7. x402 was
> already in SCOPE's "later" list; this section makes the plan explicit.

### Why it fits us (the key insight)
- The customer is the **AI agent**, and agents pay natively on-chain via **x402** (Coinbase's
  HTTP-402 agent-payment standard; per-call **USDC** stablecoin), not human credit cards.
- 🔑 **The gap that makes us valuable:** x402 proves *that payment happened*, **not that the
  response was correct or fulfilled** (conference, 하이블록 presentation). KoreaAPI's
  **Skill Score + provenance IS that missing proof-of-fulfilment layer.** So agent payments
  *reinforce* our verification moat instead of being a bolt-on — we are the layer that makes
  paying an agent for data *trustworthy*.

### Plan (sequenced — do NOT pull these forward)
1. **Now:** cold-start. Free magnet + **GEO (done)** + affiliate buy-intent signal. No payment rail.
2. **On traffic / agent demand:** x402 paywall on premium endpoints — agents auto-pay USDC
   per verified-data call; Skill Score is the fulfilment proof.
3. **Reputation:** give "KoreaAPI as a verified source" a portable reputation
   (ERC-8004 / BEP-78-style soul-bound token) so agents trust + cite us → reinforces GEO.

### Rail clarifications (avoid the common confusion)
- **Payment rail = USDC stablecoin + x402** (Base-centric). It is **NOT** "receive BNB token".
- **BNB Chain** is relevant for the **reputation** layer (BEP-78), not as the payment token.

### ⛔ Guardrails (load-bearing)
- **Do NOT launch a token / coin.** Regulatory risk + off-mission; violates PRINCIPLES "DON'T".
  The conference is about payment *rails* and trust *mechanisms* (x402, escrow, staking /
  slashing, reputation) — never about issuing your own coin.
- A bare "BNB wallet / donation address" is a **tip jar, not revenue**, and dilutes the
  verified-data trust brand. Avoid.

### Korea-gap (positioning)
The conference's closing signal: Korea is under-invested in agent×crypto → an open market;
Korean B2B trade payment and Korean RWA are empty niches. **KoreaAPI = "Korea + agents"** sits
exactly in that gap.

---

## Vertical (candidate, decision-gated) — Prediction-market settlement oracle

> Source: user idea (2026-06-02) + the conference's core claim — agents pay for *trustworthy
> real-world input + the right to act*. Betting agents are the **purest buyers of verified
> ground truth**: they need it both to inform a bet and to settle it.

### The fit (on-thesis)
- Prediction markets — **Polymarket** (on-chain), **Kalshi** (regulated US, fiat),
  **오피니언/Opinion** (KR) — resolve on real-world outcomes; their #1 need is a **trustworthy
  settlement/reference source**. KoreaAPI's provenance + Skill Score = *settlement-grade*.
- K-culture markets ("BTS comeback on 6/13?", "NewJeans #1 this week?", "MAMA winner?") have
  **no machine-readable verified source today** — the gap we own.
- Agents query per-bet → **engine ② signal + per-call payment (x402, Phase 2)**. A settlement
  oracle is premium + sticky (you don't switch the source your bets settle on).

### What it requires (design draft)
1. **Outcome/Claim record** (not just a Name) — a *resolvable assertion*, reusing the
   Name/Provenance/append-only contract:
   ```json
   { "entity_id": "artist:bts", "claim": "comeback on 2026-06-13",
     "resolution_date": "2026-06-13",
     "status": "announced",            // rumored | announced | confirmed | resolved
     "result": null,                   // set on resolution (true/false/value)
     "provenance": { "sources": ["agency notice 2026-06-01"], "skill_score": 0.9 } }
   ```
2. **Status discipline** — `rumored | announced | confirmed | resolved`. For betting,
   mislabelling rumor as fact = liability, so this tightens the existing translation.source /
   confidence model. The verification moat matters MORE here.
3. **Outcome sources — DECIDED (2026-06-03):** primary = **Circle Chart** (the official Korean
   chart; public; the authoritative *settlement* source for chart-position outcomes; LLM-extract
   the public weekly charts = "cheap AI as collection labor"). Complement = **YouTube Data API**
   (free key) for official-channel release / view-milestone events. **Avoid**: news APIs (rumor ≠
   settlement) and agency-site / social scraping (fragile, gray, undermines the moat); Spotify
   gated (skip). Rationale: official source first + live-state + verifiable settlement (the 대명제).
4. **Settlement output**: extend the existing `citation` field into a machine-citable
   *"verified claim, as-of <date>, source X, Skill Score Y, status Z"* an agent attaches to a bet.
5. **MCP tool**: `get_claim_status(claim_id)` / `resolve_outcome(...)` → verified outcome +
   provenance, for an agent to inform or settle a bet.

### ⛔ Guardrails (load-bearing)
- KoreaAPI is the **data / oracle layer, NOT a gambling operator** — no hosting bets, no wager
  intake, no odds-making. Verifiable reference/settlement data only. (Korean gambling law is
  strict; stay clearly on the data side.)
- **Never ship rumor as fact.** `status` + Skill Score are the trust contract; honest
  uncertainty over false confidence.

### Sequencing
Decision-gated. Slots **after / with** the live-state event data (SCOPE's comeback/chart/concert
kinds) + engine ②; monetized via x402 (Phase 2). **Do not build the data layer until the
outcome-source decision is made.**

---

## GEO — public deploy (✅ LIVE)
**Live: https://wrxfoundation.github.io/weatherplan-ai/** — first verified, real Wikidata data
published publicly (2026-06-02): BTS/NewJeans/aespa with Skill Score, provenance (correct
Q-ids), and Schema.org JSON-LD (`sameAs` the Wikidata entity) + meta description. MCP output
carries a matching `citation`. Built + deployed by **`.github/workflows/pages.yml`** on
GitHub Pages — the pull runs on GitHub's open-network runner (so it works despite the sandbox
egress block); auto-refreshes on push + daily.

**Enablement gotchas (both one-time, owner-only):**
1. Settings → Pages → Source: **GitHub Actions**.
2. Deploying from a **non-default branch** also needs it allowed in the `github-pages`
   environment (Settings → Environments → github-pages → Deployment branches → No restriction),
   else the deploy is blocked at the environment gate (instant ~2s failure). Unnecessary once
   merged to the default branch.

(Production may later move this to the product domain / a Postgres-backed renderer — Phase 2.)
