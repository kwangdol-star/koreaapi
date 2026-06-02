# KoreaAPI — accounts & API keys (one-pass setup)

> A single shopping list so you can gather everything in one sitting; then I wire it all at
> once. Variable names match [`.env.example`](../.env.example). When you have a value, put it in
> `.env` (local, gitignored) **and** as a GitHub Actions **secret** (repo Settings → Secrets and
> variables → Actions) so the `collect` / `pages` workflows can use it. Ping me with which ones
> you've set and I'll wire the adapters + workflows in one pass.

**Legend:** ✅ done · 🟢 do now (free) · 🟡 Phase-1 revenue (light approval) · 🔵 Phase-2 / later · ⚪ optional

---

## ✅ Already working — no key needed
- **Wikidata · Wikipedia** — credential-free (a compliant User-Agent only). 6 artists live + cross-verified.

## 🟢 Now — free; sharpen the magnet & verification
| Service | What it buys us | Cost | Sign up | Env var |
|---|---|---|---|---|
| **Anthropic (Claude)** | LLM extract + bilingual translation at ingest (cheap collection labor; Haiku) | usage (cheap) | console.anthropic.com → API keys | `ANTHROPIC_API_KEY` |
| **Spotify for Developers** | artist / album / popularity = a 3rd independent verified source | free | developer.spotify.com/dashboard → Create app | `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET` |
| **YouTube Data API v3** | views / release signals (verified source) | free quota | console.cloud.google.com → enable "YouTube Data API v3" → API key | `YOUTUBE_API_KEY` |

## 🟡 Phase-1 revenue — light approval (site review, no sales threshold)
| Service | What it buys us | Cost | Sign up | Env var |
|---|---|---|---|---|
| **Skimlinks** (or Sovrn) | affiliate links in `get_buy_options` → commission + buy-intent signal | free; site review | skimlinks.com | `SKIMLINKS_PUBLISHER_ID` |
| **Amazon Associates** | affiliate for global goods | free; site review | affiliate-program.amazon.com | `AMAZON_ASSOCIATES_TAG` |
| **Beehiiv** | "Korea Rising" digest (engine ② seed + marketing) | free tier | beehiiv.com | `BEEHIIV_API_KEY`, `BEEHIIV_PUBLICATION_ID` |

## 🔵 Phase-2 — agent payments (x402); wire only when traffic qualifies
| Service | What it buys us | Cost | Sign up | Env var |
|---|---|---|---|---|
| **Coinbase Developer Platform** | x402 facilitator — agents pay per call in USDC | usage | portal.cdp.coinbase.com | `CDP_API_KEY_ID`, `CDP_API_KEY_SECRET` |
| **USDC wallet (Base)** | receiving address for agent payments | — | any Base wallet | `KOREAAPI_PAYOUT_ADDRESS` |

> ROADMAP guardrails: payment rail = **USDC + x402**, *not* "receive BNB"; do **not** launch a token.

## 🔵 Prediction-market vertical (candidate) — mostly NO keys
We are the **oracle** (markets/agents query *us*), so no keys are needed to start. Only if we
later *read* markets to cross-reference: Polymarket (on-chain, public), Kalshi (API + account),
오피니언/Opinion (KR, TBD).

## ⚪ Infra / scale — later
| Service | What it buys us | Cost | Sign up | Env var |
|---|---|---|---|---|
| **Postgres** (Supabase / Neon) | production append-only DB (swap from SQLite) | free tier | supabase.com / neon.tech | `DATABASE_URL` |
| **Domain** (e.g. koreaapi.dev) | agent-facing site + the User-Agent contact | ~$12/yr | any registrar | — |
| **MCP registry** (Smithery) | agent discovery / GEO | free | smithery.ai | — |

---

## If you only do a few now (highest leverage)
1. **Spotify** (free) → a 3rd cross-verification source → Skill Scores + trust ↑
2. **Anthropic** → LLM extraction → unlocks *event/outcome* data (comebacks / charts) = the
   live-state moat **and** the prediction-market vertical
3. **Beehiiv** (free) → first "Korea Rising" digest → traffic → unlocks affiliate approval

Set any of these → drop in `.env` + GitHub Actions secrets → ping me; I wire them in one pass.
