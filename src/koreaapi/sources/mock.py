"""Offline fixture source so the pipeline runs end-to-end without network or API keys.

Real adapters (Spotify, Wikidata, Circle Chart) implement the same Source protocol
(see base.py). MockSource lets tests and demos exercise the full
ingest -> verify -> append flow deterministically.
"""

from __future__ import annotations

from datetime import datetime, timezone


class MockSource:
    is_fallback = False

    def __init__(self, name: str, payload: dict, *, is_fallback: bool = False):
        self.name = name
        self._payload = payload
        self.is_fallback = is_fallback

    async def fetch(self, entity_id: str, kind: str) -> dict:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        return {"payload": self._payload, "citation": f"{self.name} {ts}"}
