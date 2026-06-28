"""Monetization rails — offline tests (no network, no chain).

x402's pure server side (challenge shape + facilitator verify/settle, with the facilitator
HTTP monkeypatched) and the Stripe skeleton's inertness. Plus the Starlette API gate:
DORMANT serves the premium endpoint free; once a wallet is set, an unpaid call gets a
spec-shaped 402. The facilitator (the actual crypto) is never called in tests.
"""

from __future__ import annotations

import asyncio
import base64
import json

import pytest

from koreaapi.payments import stripe, x402


def _b64(obj: dict) -> str:
    return base64.b64encode(json.dumps(obj).encode()).decode()


# ---------------- x402 pure protocol ----------------

def test_usdc_atomic_math():
    assert x402.usdc_atomic("0.01") == "10000"     # USDC = 6 decimals
    assert x402.usdc_atomic("1") == "1000000"
    assert x402.usdc_atomic(0.005) == "5000"


def test_requirement_shape_mainnet(monkeypatch):
    monkeypatch.setenv("X402_PAY_TO", "0xWallet")
    monkeypatch.setenv("X402_NETWORK", "base")
    r = x402.requirement("https://api.koreaapi/v1/korea-rising", "0.01", "desc")
    assert r["scheme"] == "exact" and r["network"] == "base"
    assert r["payTo"] == "0xWallet"
    assert r["asset"] == x402.USDC["base"]["address"]
    assert r["maxAmountRequired"] == "10000"
    assert r["mimeType"] == "application/json"
    assert r["extra"] == {"name": "USD Coin", "version": "2"}  # native USDC EIP-712 domain


def test_challenge_structure(monkeypatch):
    monkeypatch.setenv("X402_PAY_TO", "0xWallet")
    c = x402.challenge("https://api.koreaapi/x", "0.01", "desc")
    assert c["x402Version"] == x402.X402_VERSION
    assert c["error"]
    assert isinstance(c["accepts"], list) and c["accepts"][0]["payTo"] == "0xWallet"


def test_is_active_dormant_then_live(monkeypatch):
    monkeypatch.delenv("X402_PAY_TO", raising=False)
    assert x402.is_active() is False            # dormant => premium served free
    monkeypatch.setenv("X402_PAY_TO", "0xWallet")
    assert x402.is_active() is True


def test_settle_happy_path(monkeypatch):
    seen = []

    async def fake_post(url, body):
        seen.append(url)
        if url.endswith("/verify"):
            return {"isValid": True, "payer": "0xPayer"}
        return {"success": True, "transaction": "0xTx", "payer": "0xPayer"}

    monkeypatch.setattr(x402, "_post_json", fake_post)
    out = asyncio.run(x402.settle(_b64({"scheme": "exact"}), {"scheme": "exact"}))
    assert out["ok"] is True and out["response_b64"] and out["payer"] == "0xPayer"
    assert any(u.endswith("/verify") for u in seen) and any(u.endswith("/settle") for u in seen)


def test_settle_rejects_invalid_payment(monkeypatch):
    async def fake_post(url, body):
        assert url.endswith("/verify")  # must NOT reach /settle on an invalid payment
        return {"isValid": False, "invalidReason": "insufficient_funds"}

    monkeypatch.setattr(x402, "_post_json", fake_post)
    out = asyncio.run(x402.settle(_b64({}), {}))
    assert out["ok"] is False and "insufficient_funds" in out["error"]


def test_settle_rejects_garbage_header():
    out = asyncio.run(x402.settle("!!!not-base64!!!", {}))
    assert out["ok"] is False and "X-PAYMENT" in out["error"]


# ---------------- stripe skeleton ----------------

def test_stripe_skeleton_is_inert(monkeypatch):
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    assert stripe.is_configured() is False
    out = stripe.create_checkout_session("pro")
    assert out["ok"] is False and out["error"] == "stripe_not_configured"
    assert stripe.create_checkout_session("nope")["error"].startswith("unknown plan")


# ---------------- Starlette API gate ----------------

def _client(monkeypatch, tmp_path):
    from starlette.testclient import TestClient

    from koreaapi.api import app
    monkeypatch.setenv("KOREAAPI_DB", str(tmp_path / "t.db"))
    return TestClient(app)


def test_free_endpoint_serves_even_on_empty_db(monkeypatch, tmp_path):
    monkeypatch.delenv("X402_PAY_TO", raising=False)
    r = _client(monkeypatch, tmp_path).get("/v1/verified/artist:bts")
    assert r.status_code == 200 and r.json()["entity_id"] == "artist:bts"


def test_resolve_route_is_wired(monkeypatch, tmp_path):
    monkeypatch.delenv("X402_PAY_TO", raising=False)
    r = _client(monkeypatch, tmp_path).get("/v1/resolve/빈센조")   # empty db -> miss, but route works
    assert r.status_code == 200 and r.json()["found"] is False


def test_premium_is_free_when_dormant(monkeypatch, tmp_path):
    monkeypatch.delenv("X402_PAY_TO", raising=False)
    r = _client(monkeypatch, tmp_path).get("/v1/korea-rising")
    assert r.status_code == 200  # dormant gate => served free


def test_premium_returns_spec_402_when_active_and_unpaid(monkeypatch, tmp_path):
    monkeypatch.setenv("X402_PAY_TO", "0xWallet")
    monkeypatch.setenv("X402_NETWORK", "base")
    r = _client(monkeypatch, tmp_path).get("/v1/korea-rising")
    assert r.status_code == 402
    body = r.json()
    assert body["x402Version"] == 1
    acc = body["accepts"][0]
    assert acc["payTo"] == "0xWallet" and acc["asset"] == x402.USDC["base"]["address"]


def test_healthz_reports_rail_state(monkeypatch, tmp_path):
    monkeypatch.delenv("X402_PAY_TO", raising=False)
    r = _client(monkeypatch, tmp_path).get("/healthz")
    assert r.status_code == 200
    j = r.json()
    assert j["ok"] is True and j["x402_active"] is False and j["stripe_configured"] is False


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
