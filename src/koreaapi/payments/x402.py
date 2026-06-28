"""x402 payment rail — the agent-native monetization for KoreaAPI.

x402 (the revived HTTP 402 "Payment Required") lets ANY AI agent pay PER CALL in USDC
stablecoin, settled on Base (an Ethereum L2), with no account and no API key. That fits
KoreaAPI's whole premise — "callable by any AI agent" — so the premium endpoint (the
proprietary korea-rising demand signal) can charge agents directly.

This module is the PURE server side of the protocol:
  • challenge()   builds the 402 body (the PaymentRequirements an agent must satisfy)
  • settle()      verifies + settles a returned payment via an external FACILITATOR

The facilitator does the on-chain crypto (verify the signature, broadcast the transfer),
exactly like our data sources delegate to Wikidata/TMDB — we NEVER hold a private key here.
We only need a receiving wallet ADDRESS to be paid to.

DORMANT BY DEFAULT: with no X402_PAY_TO wallet set, is_active() is False and the gate
serves the premium endpoint FREE (ships safe; self-activates when a receiving wallet is
added — same pattern as TMDB_API_KEY / TOURAPI_KEY).

Env:
  X402_PAY_TO          receiving wallet address (EVM, on Base). UNSET => dormant.
  X402_NETWORK         "base-sepolia" (testnet, default) | "base" (mainnet, real USDC)
  X402_FACILITATOR_URL verify/settle service (default: the public testnet facilitator;
                       mainnet needs a mainnet facilitator, e.g. Coinbase CDP)
  X402_PRICE_USD       price per premium call in USD (default "0.01")
"""

from __future__ import annotations

import base64
import json
import os
from decimal import Decimal

import httpx

X402_VERSION = 1

# Circle USDC per network: contract address (6 decimals) + EIP-712 domain `name` (must equal the
# token's on-chain name() for the agent's transferWithAuthorization signature to verify). The testnet
# USDC names itself "USDC"; Base-mainnet native USDC names itself "USD Coin". Confirm on activation —
# a domain mismatch only makes a signature unverifiable (the facilitator rejects it: fails safe).
USDC = {
    "base":         {"address": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913", "name": "USD Coin"},
    "base-sepolia": {"address": "0x036CbD53842c5426634e7929541eC2318f3dCF7e", "name": "USDC"},
}
_DEFAULT_FACILITATOR = "https://x402.org/facilitator"  # public, testnet (base-sepolia)
_UA = {"User-Agent": "KoreaAPI/0.1 (https://github.com/kwangdol-star/koreaapi)"}


def pay_to() -> str | None:
    return os.environ.get("X402_PAY_TO") or None


def network() -> str:
    return os.environ.get("X402_NETWORK", "base-sepolia")


def facilitator() -> str:
    return os.environ.get("X402_FACILITATOR_URL", _DEFAULT_FACILITATOR).rstrip("/")


def default_price_usd() -> str:
    return os.environ.get("X402_PRICE_USD", "0.01")


def is_active() -> bool:
    """The gate is live only when a receiving wallet is configured (else: serve free)."""
    return bool(pay_to())


def usdc_atomic(usd: str | float) -> str:
    """Dollars -> USDC atomic units (6 decimals), as the protocol's string amount."""
    return str(int((Decimal(str(usd)) * 1_000_000).to_integral_value()))


def _asset(net: str) -> dict:
    return USDC.get(net, USDC["base-sepolia"])


def requirement(resource: str, price_usd: str | float, description: str) -> dict:
    """One PaymentRequirements entry — the 'exact' scheme on USDC/Base."""
    net = network()
    asset = _asset(net)
    return {
        "scheme": "exact",
        "network": net,
        "maxAmountRequired": usdc_atomic(price_usd),
        "resource": resource,
        "description": description,
        "mimeType": "application/json",
        "payTo": pay_to() or "",
        "maxTimeoutSeconds": 60,
        "asset": asset["address"],
        "extra": {"name": asset["name"], "version": "2"},  # USDC EIP-712 domain (transferWithAuthorization)
    }


def challenge(resource: str, price_usd: str | float, description: str,
              error: str = "X-PAYMENT header is required") -> dict:
    """The full HTTP 402 body: the protocol version + the accepted ways to pay."""
    return {
        "x402Version": X402_VERSION,
        "error": error,
        "accepts": [requirement(resource, price_usd, description)],
    }


def _decode_payment(x_payment: str) -> dict:
    """base64(JSON) X-PAYMENT header -> the payment payload object."""
    return json.loads(base64.b64decode(x_payment))


def _encode_response(settle_body: dict) -> str:
    """settle result -> base64(JSON) for the X-PAYMENT-RESPONSE header."""
    return base64.b64encode(json.dumps(settle_body).encode()).decode()


async def _post_json(url: str, body: dict) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(url, json=body, headers=_UA)
        r.raise_for_status()
        return r.json()


async def settle(x_payment: str, req: dict) -> dict:
    """Verify then settle a returned payment via the facilitator.

    Returns {"ok": True, "response_b64": <X-PAYMENT-RESPONSE>, "payer": ...} on success,
    or {"ok": False, "error": ...} (the caller then re-issues the 402). The facilitator
    performs the on-chain verify + settle; we never touch a private key.
    """
    try:
        payload = _decode_payment(x_payment)
    except Exception:
        return {"ok": False, "error": "invalid X-PAYMENT header (expected base64 JSON)"}
    body = {"x402Version": X402_VERSION, "paymentPayload": payload, "paymentRequirements": req}
    try:
        verified = await _post_json(f"{facilitator()}/verify", body)
    except Exception as e:  # facilitator down / network -> block (never serve unpaid)
        return {"ok": False, "error": f"facilitator verify failed: {e}"}
    if not verified.get("isValid"):
        return {"ok": False, "error": verified.get("invalidReason") or "payment not valid"}
    try:
        settled = await _post_json(f"{facilitator()}/settle", body)
    except Exception as e:
        return {"ok": False, "error": f"facilitator settle failed: {e}"}
    if not settled.get("success"):
        return {"ok": False, "error": settled.get("errorReason") or "settlement failed"}
    return {
        "ok": True,
        "response_b64": _encode_response(settled),
        "payer": settled.get("payer") or verified.get("payer"),
    }
