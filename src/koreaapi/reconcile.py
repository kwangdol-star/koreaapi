"""Shared reconciliation helpers — parse external IDs from provenance citations (the cross-source ID
spine) + a name-match normalizer. Used by BOTH the /reconcile.json builder (admin) and the MCP
`resolve` tool (service), so the two never drift. Pure: regex + string only."""

from __future__ import annotations

import re

_RE = {
    "wikidata": re.compile(r"Wikidata (Q\d+)"),
    "tmdb": re.compile(r"TMDB (\d+)"),
    "musicbrainz": re.compile(r"MusicBrainz ([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"),
    "wikipedia": re.compile(r"Wikipedia (.+?) \d{4}-\d{2}-\d{2}"),
}


def external_ids(sources: list[str]) -> dict:
    """Best-effort external IDs parsed from the provenance citations (wikidata / tmdb / musicbrainz /
    wikipedia) — lets an agent map whatever ID it holds onto the canonical KoreaAPI entity."""
    ids: dict[str, str] = {}
    for s in sources or []:
        for key, rx in _RE.items():
            if key not in ids:
                m = rx.search(s)
                if m:
                    ids[key] = m.group(1)
    return ids


def norm(s: str | None) -> str:
    """Casefold + strip spaces — the alias match key (e.g. 'Big Hit' == 'big hit' == 'BIGHIT')."""
    return (s or "").casefold().replace(" ", "")
