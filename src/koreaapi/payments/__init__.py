"""Monetization rails for KoreaAPI.

- x402  : the PRIMARY rail — agents pay per call in USDC on Base (HTTP 402). Live.
- stripe: a SKELETON — fiat subscriptions, scaffolded but intentionally inert until
          demand wants an invoice (see payments/stripe.py).

Both ship DORMANT and self-activate from env (the same key-gating pattern as the
data sources: TMDB_API_KEY / TOURAPI_KEY). No secret in code, ever.
"""
