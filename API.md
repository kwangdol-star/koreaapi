# KoreaAPI — paid HTTP API (x402)

The agent-callable, **paid** face of KoreaAPI. Same verified data as the MCP server, over
HTTP/JSON, with the premium endpoint gated by **x402** (agents pay per call in USDC on Base).

> Static GitHub Pages can't return an HTTP 402, so this runs as a **live ASGI server** —
> separate from the public pages site.

## Endpoints

**Free** (kept open on purpose — this is the AEO/GEO authority that gets us cited):
- `GET /v1/verified/{entity_id}` — cross-verification status + Skill Score
- `GET /v1/artist/{artist_id}` — latest verified artist status
- `GET /v1/person/{name}` — verified credits for a person
- `GET /v1/related/{entity_id}` — entities sharing a 소속사 / network
- `GET /v1/agency/{name}` — artists under an agency
- `GET /v1/calendar` — recent verified K-culture events
- `GET /v1/buy-options/{item}` — where-to-buy (logs buy-intent)

**Premium (x402-gated):**
- `GET /v1/korea-rising` — the proprietary demand signal (queries + buy-intent). The one
  thing not re-derivable from Wikipedia, so it's the one thing worth charging for.

**Meta:** `GET /` (index), `GET /healthz` (rail status), `POST /billing/stripe/checkout` (skeleton).

## Run locally

```bash
KOREAAPI_DB=koreaapi.db uv run --extra web python -m koreaapi.api   # uvicorn on :8000
curl localhost:8000/healthz
```

With no wallet set, the premium endpoint is served **free** (dormant) — safe to run as-is.

## Activate x402 (turn on payments)

Set env on the host. **Dormant until `X402_PAY_TO` is set** (same pattern as the data-source keys).

| env | meaning | default |
|---|---|---|
| `X402_PAY_TO` | your receiving wallet address (EVM, on Base). **Unset = free/dormant.** | — |
| `X402_NETWORK` | `base-sepolia` (testnet) or `base` (mainnet, real USDC) | `base-sepolia` |
| `X402_FACILITATOR_URL` | verify/settle service | public testnet facilitator |
| `X402_PRICE_USD` | price per premium call | `0.01` |

**Recommended path:**
1. **Testnet first** — set only `X402_PAY_TO` to a wallet address. Network defaults to
   `base-sepolia` and uses the free public facilitator. Confirm a paying agent gets 200 +
   `X-PAYMENT-RESPONSE`, and an unpaid call gets a 402 with `accepts`.
2. **Mainnet (real money)** — set `X402_NETWORK=base` and `X402_FACILITATOR_URL` to a
   mainnet facilitator (e.g. Coinbase CDP; it may need its own auth). USDC now lands in
   your wallet per call.

We never hold a private key — the **facilitator** does the on-chain verify/settle; we only
need the receiving address. (If the EIP-712 `extra` domain ever mismatches the live token,
the signature simply won't verify — it fails safe, no funds at risk.)

## Deploy

Any ASGI host (Railway / Render / Fly / Vercel). The host needs the accumulated
`koreaapi.db` — ship a snapshot with the deploy or point `KOREAAPI_DB` at it.

```bash
uv run --extra web uvicorn koreaapi.api:app --host 0.0.0.0 --port $PORT
```

## Fiat (Stripe) — skeleton only

`payments/stripe.py` is scaffolded but **inert** (`is_configured()` is False until
`STRIPE_SECRET_KEY` is set and the SDK calls are filled in). The plans/prices are decided;
the plumbing is deferred until a buyer wants an invoice. x402 is the live rail.
