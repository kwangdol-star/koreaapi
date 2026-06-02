"""Source adapter protocol.

Official APIs preferred; gray scraping undermines the verification moat (you cannot
cite what you had no right to fetch). Each source returns a raw payload plus a
citation string that lands verbatim in Provenance.sources.
"""

from __future__ import annotations

from typing import Protocol


class Source(Protocol):
    name: str  # cited verbatim in Provenance.sources, e.g. "Circle Chart"

    async def fetch(self, entity_id: str, kind: str) -> dict:
        """Return {"payload": ..., "citation": "<source> <timestamp KST>"}."""
        ...
