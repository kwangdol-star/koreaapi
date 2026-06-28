"""KoreaAPI HTTP API — the paid, agent-callable face (x402 monetization).

Wraps the SAME service.py logic the MCP server exposes, over HTTP/JSON, and gates the
PREMIUM endpoint (korea-rising — the proprietary demand signal) behind x402: an agent
pays per call in USDC on Base. Basic verified data stays FREE — we WANT it crawled and
cited (that's the AEO/GEO authority that makes KoreaAPI the source answer engines name).

x402 is the live rail; Stripe (payments/stripe.py) is a scaffolded fiat skeleton.

Run locally:  KOREAAPI_DB=koreaapi.db uv run python -m koreaapi.api   (uvicorn on :8000)
Deploy:       any ASGI host (Railway / Render / Fly / Vercel) — NOT GitHub Pages, which
              is static and can't return a 402. The host needs the accumulated koreaapi.db
              (ship a snapshot or point KOREAAPI_DB at it).
"""

from __future__ import annotations

import os

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from . import service
from .payments import stripe, x402

PREMIUM_DESC = "KoreaAPI korea-rising — verified Korean-culture demand signal (queries + buy-intent)"


async def _gate(request: Request, price_usd: str, description: str):
    """x402 premium gate. Returns one of:
      • JSONResponse(402)  -> block (payment required / invalid)
      • str                -> paid; the base64 X-PAYMENT-RESPONSE to echo on the 200
      • None               -> proceed free (gate dormant: no X402_PAY_TO wallet set)
    """
    if not x402.is_active():
        return None  # dormant => premium served free (safe default, self-activates with a wallet)
    resource = str(request.url)
    req = x402.requirement(resource, price_usd, description)
    header = request.headers.get("X-PAYMENT")
    if not header:
        return JSONResponse(x402.challenge(resource, price_usd, description), status_code=402)
    result = await x402.settle(header, req)
    if not result.get("ok"):
        return JSONResponse(
            x402.challenge(resource, price_usd, description,
                           error=result.get("error") or "payment required"),
            status_code=402,
        )
    return result.get("response_b64") or ""


# ---- free endpoints (verified data — kept open for AEO/GEO authority) ----
async def verified(request: Request) -> JSONResponse:
    return JSONResponse(await service.verified(request.path_params["entity_id"]))


async def artist(request: Request) -> JSONResponse:
    return JSONResponse(await service.artist_status(request.path_params["artist_id"]))


async def person(request: Request) -> JSONResponse:
    return JSONResponse(await service.person(request.path_params["name"]))


async def related(request: Request) -> JSONResponse:
    return JSONResponse(await service.related(request.path_params["entity_id"]))


async def agency(request: Request) -> JSONResponse:
    return JSONResponse(await service.agency(request.path_params["name"]))


async def calendar(request: Request) -> JSONResponse:
    days = int(request.query_params.get("window_days", 30))
    return JSONResponse(await service.kculture_calendar(days))


async def buy_options(request: Request) -> JSONResponse:
    return JSONResponse(await service.buy_options(request.path_params["item"]))


# ---- premium endpoint (x402-gated) ----
async def korea_rising(request: Request) -> JSONResponse:
    gate = await _gate(request, x402.default_price_usd(), PREMIUM_DESC)
    if isinstance(gate, JSONResponse):
        return gate  # 402: blocked
    category = request.query_params.get("category", "all")
    limit = int(request.query_params.get("limit", 10))
    resp = JSONResponse(await service.korea_rising(category, limit))
    if isinstance(gate, str) and gate:  # paid -> echo the settlement receipt
        resp.headers["X-PAYMENT-RESPONSE"] = gate
    return resp


# ---- billing skeleton (Stripe — inert) ----
async def stripe_checkout(request: Request) -> JSONResponse:
    body: dict = {}
    try:
        body = await request.json()
    except Exception:
        pass
    out = stripe.create_checkout_session(body.get("plan", "pro"))
    return JSONResponse(out, status_code=200 if out.get("ok") else 501)


# ---- meta ----
async def health(request: Request) -> JSONResponse:
    return JSONResponse({
        "ok": True,
        "db": os.environ.get("KOREAAPI_DB", "koreaapi.db"),
        "x402_active": x402.is_active(),
        "x402_network": x402.network() if x402.is_active() else None,
        "stripe_configured": stripe.is_configured(),
    })


async def index(request: Request) -> JSONResponse:
    return JSONResponse({
        "name": "KoreaAPI",
        "tagline": "The verifiable data layer for Korean culture — callable by any AI agent.",
        "free": {
            "GET /v1/verified/{entity_id}": "cross-verification status + Skill Score",
            "GET /v1/artist/{artist_id}": "latest verified artist status",
            "GET /v1/person/{name}": "verified credits for a person",
            "GET /v1/related/{entity_id}": "entities sharing a 소속사 / network",
            "GET /v1/agency/{name}": "artists under an agency",
            "GET /v1/calendar": "recent verified K-culture events",
            "GET /v1/buy-options/{item}": "where-to-buy (logs buy-intent)",
        },
        "premium_x402": {
            "endpoint": "GET /v1/korea-rising",
            "description": PREMIUM_DESC,
            "price_usd": x402.default_price_usd(),
            "active": x402.is_active(),
            "network": x402.network(),
            "how": "send the request; on HTTP 402, pay USDC per the x402 protocol and retry with X-PAYMENT",
        },
        "billing_fiat": {"configured": stripe.is_configured(), "plans": list(stripe.PLANS)},
    })


routes = [
    Route("/", index),
    Route("/healthz", health),
    Route("/v1/verified/{entity_id}", verified),
    Route("/v1/artist/{artist_id}", artist),
    Route("/v1/person/{name}", person),
    Route("/v1/related/{entity_id}", related),
    Route("/v1/agency/{name}", agency),
    Route("/v1/calendar", calendar),
    Route("/v1/buy-options/{item}", buy_options),
    Route("/v1/korea-rising", korea_rising),
    Route("/billing/stripe/checkout", stripe_checkout, methods=["POST"]),
]

app = Starlette(routes=routes)


def main() -> None:
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))


if __name__ == "__main__":
    main()
