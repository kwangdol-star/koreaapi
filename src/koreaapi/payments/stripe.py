"""Stripe billing — SKELETON ONLY (intentionally inert).

Decision (this session): x402 is the primary rail; Stripe is scaffolded so the FIAT
option exists the day a buyer wants an invoice/subscription, WITHOUT committing to the
integration now. Every function is a no-op stub until STRIPE_SECRET_KEY is set AND the
real SDK calls are filled in; is_configured() stays False so the API honestly reports
the fiat rail as unavailable rather than pretending.

To activate later: add `stripe` to deps, set STRIPE_SECRET_KEY + STRIPE_WEBHOOK_SECRET,
and implement create_checkout_session / handle_webhook against the Stripe SDK.
"""

from __future__ import annotations

import os

# The paid tiers we WILL sell over fiat (mirrors the x402 premium scope). Defined here so the
# product shape is decided even though billing is not wired — the price tag, not the plumbing.
PLANS = {
    "pro": {
        "name": "KoreaAPI Pro",
        "usd_month": 49,
        "includes": ["korea-rising demand signal", "higher rate limit", "freshness SLA"],
    },
    "scale": {
        "name": "KoreaAPI Scale",
        "usd_month": 199,
        "includes": ["everything in Pro", "bulk export", "priority support"],
    },
}


def is_configured() -> bool:
    """Live only when a Stripe secret is present (it is not — skeleton)."""
    return bool(os.environ.get("STRIPE_SECRET_KEY"))


def create_checkout_session(plan: str) -> dict:
    """SKELETON: would create a Stripe Checkout subscription session for `plan`."""
    if plan not in PLANS:
        return {"ok": False, "error": f"unknown plan {plan!r}", "plans": list(PLANS)}
    if not is_configured():
        return {
            "ok": False,
            "error": "stripe_not_configured",
            "note": "fiat rail is scaffolded but inert; set STRIPE_SECRET_KEY + implement to enable",
            "plan": PLANS[plan],
        }
    # TODO(activate): stripe.checkout.Session.create(mode="subscription", line_items=[...], ...)
    raise NotImplementedError("Stripe checkout not implemented yet (skeleton)")


def handle_webhook(payload: bytes, signature: str | None) -> dict:
    """SKELETON: would verify the signature and fulfill subscription lifecycle events."""
    if not is_configured():
        return {"ok": False, "error": "stripe_not_configured"}
    # TODO(activate): stripe.Webhook.construct_event(payload, signature, STRIPE_WEBHOOK_SECRET)
    raise NotImplementedError("Stripe webhook not implemented yet (skeleton)")
