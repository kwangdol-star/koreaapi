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

from . import answers, service
from .license import LICENSE
from .payments import stripe, x402

PREMIUM_DESC = "KoreaAPI korea-rising — verified Korean-culture demand signal (queries + buy-intent)"

_OK = {"200": {"description": ("verified JSON — carries provenance (which independent sources agreed), a "
                              "Skill Score (0–1), a ready cite line, and the machine-readable license.")}}


def _op(summary: str, description: str, params: list | None = None, extra: dict | None = None) -> dict:
    op = {"summary": summary, "description": description, "responses": dict(_OK)}
    if params:
        op["parameters"] = params
    if extra:
        op["responses"] = {**op["responses"], **extra}
    return {"get": op}


def _pp(name: str, example: str) -> dict:  # path parameter
    return {"name": name, "in": "path", "required": True, "schema": {"type": "string"}, "example": example}


def _qp(name: str, typ: str = "string", desc: str = "") -> dict:  # query parameter (optional)
    return {"name": name, "in": "query", "required": False, "description": desc, "schema": {"type": typ}}


def openapi_spec() -> dict:
    """OpenAPI 3.1 description of the HTTP API — so KoreaAPI is auto-consumable by the whole OpenAPI
    ecosystem (ChatGPT Actions, LangChain tools, generated clients): 'callable by any AI agent' beyond
    MCP. Served at GET /openapi.json and published static (crawl-discoverable)."""
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "KoreaAPI",
            "summary": "The verifiable data layer for Korean culture — callable by any AI agent.",
            "description": ("Verified, bilingual Korean-culture data. Every response carries provenance (which "
                            "independent sources agreed), a Skill Score (0–1), and a machine-readable license. "
                            "Free verified endpoints are open (crawl + cite them); the korea-rising demand "
                            "signal is x402-metered (USDC on Base)."),
            "version": "1.0",
            "license": {"name": LICENSE["id"], "url": LICENSE["url"]},
            "x-attribution": LICENSE["attribution"],
            "contact": {"url": "https://aiagentlabs.co.kr/for-agents.html"},
        },
        "servers": [{"url": "/", "description": "the live KoreaAPI HTTP host"}],
        "paths": {
            "/v1/verified/{entity_id}": _op(
                "Cross-verification status of an entity",
                "How many INDEPENDENT sources agreed + Skill Score + cross/triple-verified flags — decide "
                "trust before citing.", [_pp("entity_id", "artist:bts")]),
            "/v1/resolve/{query}": _op(
                "Resolve a name / external ID to the canonical verified entity",
                "Map a fuzzy Korean name, a Wikidata Q-id, or an entity_id onto THE trusted entity (with "
                "sameAs) before citing.", [_pp("query", "빈센조")]),
            "/v1/artist/{artist_id}": _op(
                "Latest verified artist status", "Comeback / chart / agency, with provenance.",
                [_pp("artist_id", "artist:bts")]),
            "/v1/person/{name}": _op(
                "Verified credits for a person", "What a director / actor / idol member is credited on.",
                [_pp("name", "Bong Joon-ho")]),
            "/v1/related/{entity_id}": _op(
                "Related entities via the same hub edge", "Same 소속사 (artists) or network (drama / film).",
                [_pp("entity_id", "artist:bts")]),
            "/v1/agency/{name}": _op(
                "Artists under a Korean agency / label (소속사)", "The agency roster, cross-verified.",
                [_pp("name", "HYBE")]),
            "/v1/calendar": _op(
                "Recent verified K-culture events", "Comebacks, releases, concerts.",
                [_qp("window_days", "integer", "advisory window (Phase 1)")]),
            "/v1/history/{entity_id}": _op(
                "Append-only verified timeline + change events (the time moat)",
                "First / last verified, snapshot count, and the change events (소속사 A→B, renames) a latecomer "
                "cannot backfill.", [_pp("entity_id", "artist:bts")]),
            "/v1/changes": _op(
                "Recent verified changes across K-culture (the freshness feed)",
                "소속사 moves and renames, newest first — exactly what stale models get wrong. Pass "
                "?since=YYYY-MM-DD for incremental sync (only the delta after that cursor).",
                [_qp("limit", "integer", "max changes (default 50)"),
                 _qp("since", "string", "cursor — ISO date or full timestamp; only changes after it (sub-day precise; pass back next_since)"),
                 _qp("offset", "integer", "skip N (drain a delta bigger than limit: loop offset=next_offset until null)")]),
            "/v1/batch": _op(
                "Batch verify / resolve — the agent-throughput lane",
                "Verify or resolve MANY entities in ONE round-trip: ?ids=a,b,c (comma-separated ids or "
                "names, up to 100) → a result map keyed by input. op=verified (default) or resolve.",
                [_qp("ids", "string", "comma-separated entity_ids or names (up to 100)"),
                 _qp("op", "string", "'verified' (default) or 'resolve'")]),
            "/v1/certified": _op(
                "Officially certified entities (the tier above cross-verification)",
                "Entities an official rights-holder has vouched for — the strongest citation signal."),
            "/v1/metrics": _op(
                "Agent-consumption metrics",
                "How much agents have pulled KoreaAPI — usage totals + the most-requested signals."),
            "/v1/buy-options/{item}": _op(
                "Verify-official → purchase gateway",
                "Confirm the item is the REAL, cross-verified entity before a purchase; logs buy-intent.",
                [_pp("item", "artist:bts")]),
            "/v1/answer": _op(
                "Answer Products — named, citable decisions over the verified store",
                "No params → the catalog; ?product=&q= runs one decision; ?q= runs all.",
                [_qp("product", "string", "e.g. canonical-name, fact-check, identity-resolve"),
                 _qp("q", "string", "the query")]),
            "/v1/korea-rising": {"get": {
                "summary": "PREMIUM — Korea-rising verified demand signal (x402-metered)",
                "description": ("The proprietary demand signal (queries + buy-intent). Metered per call via "
                                "x402 (USDC on Base): send the request, and on HTTP 402 pay per the challenge "
                                "and retry with an X-PAYMENT header. Served free while the receiving wallet is "
                                "unset (dormant)."),
                "parameters": [_qp("category", "string", "a vertical or 'all'"),
                               _qp("limit", "integer", "top-N (default 10)")],
                "responses": {**_OK, "402": {"description": ("Payment Required — x402 challenge (pay USDC on "
                                                            "Base, retry with X-PAYMENT)")}},
            }},
        },
    }


def _int(request: Request, name: str, default: int) -> int:
    """Parse an int query param, falling back to `default` on missing/garbage — so a bad `?limit=abc`
    is a clean default, not an unhandled ValueError → HTTP 500 (this API has no exception handler)."""
    try:
        return int(request.query_params.get(name, default))
    except (TypeError, ValueError):
        return default


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
    return JSONResponse(await service.kculture_calendar(_int(request, "window_days", 30)))


async def buy_options(request: Request) -> JSONResponse:
    return JSONResponse(await service.buy_options(request.path_params["item"]))


async def resolve(request: Request) -> JSONResponse:
    return JSONResponse(await service.resolve(request.path_params["query"]))


async def history(request: Request) -> JSONResponse:
    return JSONResponse(await service.history(request.path_params["entity_id"]))


async def changes(request: Request) -> JSONResponse:
    return JSONResponse(await service.recent_changes(
        _int(request, "limit", 50), since=request.query_params.get("since"),
        offset=_int(request, "offset", 0)))


async def batch(request: Request) -> JSONResponse:
    """Throughput lane: verify / resolve a comma-separated list of ids or names in one round-trip.
    GET /v1/batch?ids=artist:bts,artist:newjeans&op=verified (op defaults to 'verified')."""
    raw = request.query_params.get("ids", "")
    ids = [s.strip() for s in raw.split(",") if s.strip()]
    return JSONResponse(await service.batch(ids, op=request.query_params.get("op", "verified")))


async def certified(request: Request) -> JSONResponse:
    return JSONResponse(await service.certified())


async def metrics(request: Request) -> JSONResponse:
    return JSONResponse(await service.metrics())


async def answer(request: Request) -> JSONResponse:
    """Answer Products (engine 3). No params -> the catalog. ?q= -> run ALL products on the query.
    ?product=&q= -> run one. ?product=auto&q= -> natural-language ROUTE the free-text question to the
    right product (best-effort LLM; keyword fallback). Free; korea-rising is x402-metered separately."""
    product = request.query_params.get("product")
    q = request.query_params.get("q", "")
    if not product and not q:
        return JSONResponse(answers.list_products())
    if product == "auto":  # NL routing: pick the product from the free-text question, then run it
        return JSONResponse(await answers.ask(q))
    if product:
        return JSONResponse(await answers.answer(product, q))
    return JSONResponse(await answers.answer_all(q))


# ---- premium endpoint (x402-gated) ----
async def korea_rising(request: Request) -> JSONResponse:
    gate = await _gate(request, x402.default_price_usd(), PREMIUM_DESC)
    if isinstance(gate, JSONResponse):
        return gate  # 402: blocked
    category = request.query_params.get("category", "all")
    resp = JSONResponse(await service.korea_rising(category, _int(request, "limit", 10)))
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
            "GET /v1/resolve/{query}": "resolve a name / external ID / id -> the canonical verified entity",
            "GET /v1/history/{entity_id}": "append-only verified timeline + change events (the time moat)",
            "GET /v1/changes": "recent verified changes across K-culture (소속사 moves, renames) — the freshness feed; ?since=YYYY-MM-DD for the incremental delta",
            "GET /v1/batch": "verify/resolve up to 100 ids or names in one round-trip — ?ids=a,b,c&op=verified (the agent-throughput lane)",
            "GET /v1/certified": "entities officially certified by their rights-holder (the tier above cross-verification)",
            "GET /v1/metrics": "how much agents have consumed KoreaAPI (usage totals + most-requested signals)",
            "GET /v1/answer": "Answer Products catalog; ?product=&q= runs one decision, ?q= runs all",
            "GET /openapi.json": "OpenAPI 3.1 spec — auto-generate a client (ChatGPT Actions, LangChain, …)",
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


async def openapi(request: Request) -> JSONResponse:
    return JSONResponse(openapi_spec())


routes = [
    Route("/", index),
    Route("/healthz", health),
    Route("/openapi.json", openapi),
    Route("/v1/verified/{entity_id}", verified),
    Route("/v1/artist/{artist_id}", artist),
    Route("/v1/person/{name}", person),
    Route("/v1/related/{entity_id}", related),
    Route("/v1/agency/{name}", agency),
    Route("/v1/calendar", calendar),
    Route("/v1/buy-options/{item}", buy_options),
    Route("/v1/resolve/{query}", resolve),
    Route("/v1/history/{entity_id}", history),
    Route("/v1/changes", changes),
    Route("/v1/batch", batch),
    Route("/v1/certified", certified),
    Route("/v1/metrics", metrics),
    Route("/v1/answer", answer),
    Route("/v1/korea-rising", korea_rising),
    Route("/billing/stripe/checkout", stripe_checkout, methods=["POST"]),
]

app = Starlette(routes=routes)


def main() -> None:
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))


if __name__ == "__main__":
    main()
