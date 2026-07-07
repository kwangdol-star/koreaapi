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
| **Circle Chart settlement source #3** — circlechart.kr is JS-rendered + 403-blocks fetchers, so we read the settlement datum (the **weekly #1**) from Wikipedia's server-rendered "List of Circle Digital Chart number ones of 2026" via the **MediaWiki API (wikitext)**, LLM-extract most-recent-first, and **GROUND** every entry against the fetched text (anti-hallucination — caught Haiku fabricating a stale '#1' live). Cited honestly as "via Wikipedia". | ✅ built (autonomous, grounded); validating live. `CIRCLECHART_URL` overridable → point at circlechart.kr's real XHR endpoint for the full daily top-100 (owner-only; guard still applies) |
| **YouTube source #3.5** (official-channel stats + latest release → `admin youtube` → `kind='release'` live-state event; identity-guarded; **NOT** a name cross-verifier — channels are EN/brand-titled, would lower scores = the Spotify lesson) | ✅ **LIVE (2026-06-03)** — 6/6 release snapshots on the public page (BANGTANTV 84.6M · BLACKPINK 101M · Stray Kids 23.9M · aespa 8.45M · NewJeans 8.39M · LE SSERAFIM 7.47M subs). Wired into `pages`/`collect`; `YOUTUBE_API_KEY` set |
| **Agency anchor (소속사)**: artist → label/agency from Wikidata **P264** (record label), resolved to ko/en and shown on the public page; a verified **hub**. Verifiable, **no scraping**. | ✅ built + LIVE on the page |
| **Agency SWEEP (roster discovery)**: each anchored agency → SPARQL `wdt:P264 wd:<label>` (direct labelmates) → run through the SAME Wikidata+Wikipedia cross-verification → only verified ones join ("정보가 계속 나온다"). `admin sweep`; in pages/collect. ⚠️ A **family (P749) + per-agency-cap + ORDER BY** variant was tried and **reverted** — it over-broadened to obscure sub-unit members and *lowered* quality (10 real K-pop acts → 2 obscure names). Lesson: direct labelmates > clever broadening. Balanced cross-agency coverage + relevance-ordering deferred (Q-id order ≠ fame). | ✅ **LIVE** — grows the roster from the hub (direct labelmates) |
| **MCP `get_agency(name)`**: the agency hub made agent-queryable ("who's under JYP/HYBE?") from cross-verified records, with provenance | ✅ built (5 MCP tools now) |
| **K-pop depth (verified profile)**: members (Wikidata **P527**, batch-resolved to names) · debut/formation (**P571**) · active status (**P576**) — cross-verified, in the agent data + summary + JSON-LD (`member`/`foundingDate`, so answer engines can cite "who's in X?" / "when did X debut?") | ✅ |
| `admin pull` — turnkey live ingestion | ✅ first real external data ingested (3/3) |
| AEO/GEO surface: JSON-LD in `report.html` (now incl. `recordLabel` = the verified artist→소속사 edge) + `citation` in MCP output + **`llms.txt` published at the site root** (`/llms.txt`, lists the 5 tools + verification story) | ✅ |
| **Open data endpoint** — `/latest.json` published on the site (latest record per entity+kind, full records w/ provenance + Skill Score). Verified data is now callable **3 ways**: MCP (agents) · JSON-LD (answer engines) · plain `/latest.json` fetch (any dev/agent, no setup) | ✅ |
| Cold-start data infra: `admin export` (JSONL + latest.json) + daily GitHub Actions collector | ✅ (collector runs on open-network runners → solves the sandbox egress block) |
| **Public GEO page deployed (GitHub Pages, built from live data)** | ✅ **LIVE → https://aiagentlabs.co.kr/** |
| **Behavioral signal (engine ②)**: queries + buy-intent logged append-only; `korea_rising` ranks by observed demand; `admin signals` | ✅ |
| **CI**: `.github/workflows/test.yml` runs `pytest` + `ruff` on push (the suite is now gated) | ✅ |
| **MCP discovery prep** (distribution): `smithery.yaml` (registry start command) + `docs/MCP_INSTALL.md` (run + Claude-Desktop config + tools); server already packaged (`koreaapi-mcp` entry point, no secrets to serve) | ✅ ready to list (cleanest after the own-repo split) |
| **"Korea Rising" digest + launch copy** (distribution): `admin digest` → shareable `data/korea-rising.md` (current Circle #1 + latest releases + verified roster by agency, all cited), published at `/korea-rising.md`; `docs/LAUNCH.md` = ready-to-post copy. The free, linkable magnet (earned citations > bought backlinks). | ✅ |
| **Own-repo migration kit**: `scripts/split-koreaapi.sh` (history-preserving `git subtree split`) + `docs/MIGRATION.md` (push to e.g. `kwangdol-star/koreaapi` + post-migration fixes: workflow paths, secrets, Pages, public URLs, User-Agent, Smithery) | ✅ ready (owner runs it) |
| **Pre-launch hardening** (self-review, 3 finder passes): fixed a JSON-LD `</script>` injection on the public page; `agency()` substring → **prefix** match (no cross-agency false positives); Circle Chart now **decodes the MediaWiki JSON → wikitext** so Korean + quoted #1s ground (were silently dropped); timestamps normalized to **aware UTC** in the model (no naive/aware sort crash, correct `latest()` ordering); sweep dedups by **Q-id** (no duplicate entities); + defensive `.get`/curated-channel/calendar-honesty fixes | ✅ |
| **Data-quality pass (agent-facing context)**: `artist_status` shows the **canonical** name (from the best-verified record, not a release placeholder); `facts` summary is a natural bilingual sentence (`"BTS (방탄소년단) — verified Korean artist. Agency: …"`) not dev-jargon; YouTube Korean summary is **actually Korean** (구독자/조회수) + borrows the canonical 한글 name from the facts record; redundant prose dropped from `data` | ✅ |
| **Human monitor cockpit**: `admin monitor` → `monitor.html` (Skill-Score distribution, cross-verification rate, per-source/per-kind, daily accumulation, recent activity, watch-list); published at `/monitor.html` (noindex) | ✅ |
| Production Postgres backend (behind the same insert-only contract) | ⬜ planned (scale step) |

Tests: 56 passed, 3 live-skip (egress / key); ruff clean. Tracked on PR #1.

---

## External validation & absorbed strategy — "2026 AI-agent opportunity" research

An independent 100-opportunity ranking (sorted by *first-mover advantage × compounding moat ×
2026 feasibility*; sources: a16z *Big Ideas 2026*, Seer Interactive AEO citation analysis 2025-10,
Profound, Coinbase x402 stats, MCP adoption data) lands KoreaAPI on its **top squares** — this is
validation, not a pivot:

- **#1 vertical answer-authority hub (AEO)** = our public GEO page + JSON-LD + ready-to-cite line
- **#2 first-party data / benchmark publisher** = verified records + `/latest.json`
- **#3 vertical MCP server** = our 5 tools
- **#4 x402 paid data feed** = the Phase-2 commerce rail (planned)
- **#10 llms.txt / agent content layer** = `/llms.txt` (shipped)
- **#28 Korean / multilingual agent-data localization** = our bilingual ko-canonical + romanization (this *is* our wedge)
- primitives of **#25 vertical knowledge graph** (agency P264 hub), **#67 agent trust score** (Skill Score), **#70 content provenance verification** (provenance + hallucination guard)

**The four moats it names → what we already accrue:** (1) *citation asset* → GEO page + freshness
(daily collector; "AI citations concentrate on content refreshed in the last 1–3 yrs" — Seer); (2)
*data asset* → append-only time-series ("history is the moat"); (3) *distribution asset* → Smithery
listing + being high-trust **early** (only ~13% of public MCP servers are high-trust — quality early
entrants take the distribution); (4) *workflow lock-in* → not us by design — we are
**picks-and-shovels**, the asset the report says compounds, not an "AI wrapper" (wrappers ≈ $0 rev).

**Absorbed proof points (for positioning copy):** high-trust MCP ≈13% · citation freshness 1–3 yr
(Seer) · x402 ~160M+ cumulative payments in ~1 yr · MCP 10k+ public servers — *the land-grab window
is now*.

**Added to the roadmap (adjacent, compounding, substrate already exists):**

| Add | Why (rank) | Hooks into |
|---|---|---|
| **Crawler-citation tracking** (GPTBot / ClaudeBot hits + answer-engine citations) | report's 3–9 mo "measure the compounding moat" step (#29) | **started**: `robots.txt` explicitly welcomes AI crawlers + daily `sitemap.xml` (crawl-enablement + freshness signal). Hit-level logging deferred — GitHub Pages exposes no server logs; revisit behind a logging proxy / Cloudflare, or lean on the MCP-side demand signal |
| **x402-gated premium feed** | #4 / #16 / #61 — per-call USDC over verified data | meter `/latest.json` → paid endpoint (Phase 2) |
| **Machine-readable K-commerce product cards** (albums / merch / tickets) | #6 / #9 / #31 / #94 — ACO for AI shopping agents | the rail behind `get_buy_options` |

**Discipline (report's "avoid" + caveats):** the moat is the **data + citation incumbency, not the
OSS MCP server itself** (an open-source server alone has weak direct-revenue moat) — don't drift into
wrapper / single-feature territory. Agentic commerce today is **discovery/conversion-first**:
consumer trust in autonomous payment is low and x402 volume is partly test/memecoin, so the commerce
rail leads with *where-to-buy discovery*, not autonomous checkout. Regulated verticals
(health/legal/finance) are out of lane.

---

## K-culture breadth — one platform, many verticals (K-pop is the wedge, not the ceiling)

The 대명제 is **"Korean culture & commerce"** (SCOPE positioning). K-pop is the **Phase-1 wedge**
(go deep on one vertical first — cold-start strategy), NOT the scope limit. What's built is
deliberately K-pop-first; the **foundation is domain-agnostic** and the same pipeline extends to
every K-culture vertical.

**Domain-agnostic core (reused as-is by every vertical):** append-only store · cross-verification
(≥2 sources agree on the canonical name) · Skill Score + provenance · bilingual (ko canonical /
en + romanization) · identity + hallucination guards · GEO/JSON-LD + `/llms.txt` · MCP tools ·
behavioral signal. `entity_id` is already namespaced (`artist:` → `drama:` / `film:` / `brand:` /
`place:` …), and Wikidata + Wikipedia + YouTube are **universal** sources (any entity).

**Per-vertical extension pattern** = namespace + sources + a "hub" anchor + an outcome/"chart" +
a commerce rail:

| Vertical | entity_id | hub anchor (K-pop's `agency`/P264 analog) | outcome / "chart" | commerce |
|---|---|---|---|---|
| **K-pop** (NOW) | `artist:` | agency / label (Wikidata **P264**) | Circle Chart #1 · YouTube releases | goods / tickets |
| **K-drama / film** (next) | `drama:` / `film:` | studio / network / distributor (**P272/P449**) | Netflix Top-10 · viewership · box office | streaming / merch |
| **K-beauty** | `brand:` / `product:` | parent company (**P749**) | rankings / bestsellers | affiliate (Skimlinks/Amazon) |
| **Travel-local (맛집)** — SCOPE's designated first travel vertical | `place:` / `restaurant:` | area / near-venue | verified open + reservation availability | booking commission |

**Generalization the surfaces still need** (when the 2nd vertical lands, not before — avoid
diluting the K-pop wedge now): rename/extend `get_artist_status` → a generic `get_entity_status`
(keep an artist alias), generalize the `agency` hub to a per-domain org property, and shift the
page/digest framing from "artists/agency" to "K-culture entities". Until then the framing stays
honestly K-pop-content (no claiming drama/film data we don't yet have).

---

## Key decisions (and why)

1. **Verification is the product, not the data.** Wikidata labels are a commodity the model
   already knows; the value is the guard that caught `Q484203 = "Arborka"` (a wrong curated
   Q-id) before it could poison the store. — PRINCIPLES invariant 2.
2. **Don't compete with Wikipedia on static facts** (we'd lose — free + in every training
   set). Win on *live-state + verification + append-only history + behavioral signal +
   transaction-attached revenue*.
3. **Community + social (theqoo 더쿠 / instiz 인스티즈 / Threads) = a trend SIGNAL, not a verified
   fact** (refined 2026-06-03 from user Q). Two tiers by defensibility:
   - **(a) Threads API** = an *official* Meta API (NOT scraping). Official artist/agency accounts
     post teasers/announcements + carry engagement → defensible, **preferred**. Use for
     early-announcement + buzz signal (needs a Meta app + token; Phase-2).
   - **(b) theqoo / instiz** = no official API → scraping is **last-resort** (gray, fragile,
     ToS/IP risk — SCOPE §4). Pure buzz signal only; lowest priority.
   BOTH ingest as `confidence: low` + `provenance: community, unverified`, feed **engine ②
   (rising/buzz)**, and must **cross-verify against an official source before promoting to fact**.
   For the **prediction-market vertical**: community tells you *what's hot to bet on* (demand
   signal) but is **never the settlement source** (rumor ≠ settlement — settle on Circle Chart /
   YouTube / Wikidata-anchored agency). It must never pollute the verified store — that's the moat.
4. **Cold-start sequence first** (free magnet + GEO + affiliate buy-intent signal). Money
   rails come after traffic/agent demand exists.
5. **소속사/Agency is a HUB, not just a field** (user insight 2026-06-03). K-culture info radiates
   from the agency: comebacks, contract/renewal news, new debuts, roster. So we **anchor** the
   verified `artist → agency` edge now (Wikidata P264 — verifiable, no scraping), and **sweep**
   later: treat an agency as a first-class entity and enumerate its roster (Wikidata SPARQL
   "label = X") to auto-discover rising/new artists (engine ② coverage) and to attribute
   official announcements. The anchor is cheap and immediately useful; the sweep is the
   "정보가 계속 나온다" discovery engine. ⛔ Still no agency-site scraping (gray; undermines the moat) —
   anchor on Wikidata/official channels, not fragile HTML.

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
   (free key) for official-channel release / view-milestone events — **BUILT 2026-06-03**
   (`sources/youtube.py` + `admin youtube`, `kind='release'`; identity-guarded so a fan/impostor
   channel is never ingested; deliberately NOT a name cross-verifier; set `YOUTUBE_API_KEY` to
   activate, then promote live-verified channel ids into `_CHANNELS`). **Avoid**: news APIs
   (rumor ≠ settlement) and agency-site / social scraping (fragile, gray, undermines the moat);
   Spotify gated (skip). Rationale: official source first + live-state + verifiable settlement
   (the 대명제).
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
**Live: https://aiagentlabs.co.kr/** — first verified, real Wikidata data
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

### Backlinks / off-site authority (reviewed, 2026-06-03)
Traditional SEO backlinks help the web/GEO surface a *little* (authority → citation likelihood)
but are NOT the main lever for an agent-first product. The agent-era equivalents matter more:
- **MCP registry / directory listings** (Smithery, etc.) = the discovery "backlinks" of the agent world.
- **Citations by answer engines / agents** = the new backlink; compounds with our provenance moat.
- **llms.txt + JSON-LD** (done) = how engines find + trust us.

⛔ **No black-hat** (link farms, PBNs, paid/spam links) — antithetical to a *verifiable / trust*
brand and a penalty risk. ✅ **Earn** citations by being the verifiable default (provenance + Skill
Score + the public GEO page + a genuinely useful free "Korea Rising" digest people link/share).
Earned ≫ bought → prioritise registry listings + citation-worthiness, not a backlink campaign.
