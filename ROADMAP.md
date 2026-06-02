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
| Two faces: MCP server (agent) + admin console (human) | ✅ |
| Wikidata adapter (real source #1): live `wbsearchentities` + Wikimedia-compliant UA | ✅ |
| **Cross-verification (real source #2 = Wikipedia)**: ingest agrees on the canonical name (not prose) → two independent sources concur → Skill Score clears the 0.7 single-source cap (→ ~1.0) | ✅ — the verification moat, live |
| **Identity guard** (anti-poison): reject a label that contradicts a curated anchor | ✅ — caught a real bug in production |
| Live-verified Q-ids | ✅ BTS `Q13580495` · NewJeans `Q113189277` · aespa `Q100877982` |
| `admin pull` — turnkey live ingestion | ✅ first real external data ingested (3/3) |
| AEO/GEO surface: JSON-LD in `report.html` + `citation` field in MCP output | ✅ |
| Cold-start data infra: `admin export` (JSONL + latest.json) + daily GitHub Actions collector | ✅ (collector runs on open-network runners → solves the sandbox egress block) |
| **Public GEO page deployed (GitHub Pages, built from live data)** | ✅ **LIVE → https://wrxfoundation.github.io/weatherplan-ai/** |
| **Behavioral signal capture (engine ②)**: queries + buy-intent logged append-only → trend raw material (`admin signals`) | ✅ foundation |
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
