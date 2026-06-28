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


_PAREN = re.compile(r"\s*\([^)]*\)\s*$")  # 'Vincenzo (TV series)' -> 'Vincenzo'


def norm(s: str | None) -> str:
    """Casefold + strip spaces — the alias match key (e.g. 'Big Hit' == 'big hit' == 'BIGHIT')."""
    return (s or "").casefold().replace(" ", "")


def name_keys(*names: str | None) -> set[str]:
    """Normalized match keys for an entity's names — each name casefolded+spaceless, PLUS a
    disambiguator-stripped variant ('Vincenzo (TV series)' -> 'vincenzo'), so a title with a suffix
    still resolves. Used for both /reconcile.json aliases and the resolve tool's matching."""
    keys: set[str] = set()
    for n in names:
        if n:
            keys.add(norm(n))
            keys.add(norm(_PAREN.sub("", n)))
    keys.discard("")
    return keys


def match_score(query_norm: str, keys: set[str]) -> int:
    """A 0–100 fuzzy score between a normalized query and an entity's name keys: 100 = exact,
    else a length-ratio of the longest containment (0 = no overlap). Cheap + dependency-free."""
    if not query_norm:
        return 0
    best = 0
    for k in keys:
        if not k:
            continue
        if query_norm == k:
            return 100
        if query_norm in k or k in query_norm:
            best = max(best, round(100 * min(len(query_norm), len(k)) / max(len(query_norm), len(k))))
    return best
