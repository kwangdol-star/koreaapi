"""TMDB (The Movie Database) source adapter — independent 3rd source for drama / film / animation.

TMDB is a separate community film/TV database, and it carries the ORIGINAL (Korean) title alongside
the English one — so it works with our strict bilingual cross-verification for the video verticals
(drama 33 + film 25 + animation 13 = the second-biggest cluster after artists).

Key-gated: reads TMDB_API_KEY from the env. If unset it's INERT (raises -> gracefully dropped),
exactly like the existing ANTHROPIC_API_KEY / YOUTUBE_API_KEY best-effort pattern — so this adapter
ships dormant and ‘turns on’ the moment a free TMDB key is added to the repo secrets. Self-filters to
the video verticals. Parse + identity guard are pure/offline-tested.
"""

from __future__ import annotations

import asyncio
import os
import urllib.parse
from datetime import datetime, timezone

from ..roster import NAMES
from .wikidata import _http_get_json, _name_match, _norm

TMDB_API = "https://api.themoviedb.org/3/search/multi"
_UA = {"User-Agent": "KoreaAPI/0.1 (https://github.com/kwangdol-star/koreaapi)"}
_VIDEO = ("drama:", "film:", "animation:")


def _hit_names(r: dict) -> set[str]:
    raw = {r.get("name"), r.get("title"), r.get("original_name"), r.get("original_title")}
    return {_norm(n) for n in raw if n}


def parse_tmdb(raw: dict, expected_en: str) -> dict:
    """Pure: a TMDB search/multi response -> our payload, identity-guarded. Prefers a Korean-original
    (original_language='ko') hit matching the expected title; raises if none match (miss, never wrong)."""
    results = raw.get("results") or []
    want = _norm(expected_en)
    matches = [r for r in results if isinstance(r, dict) and _name_match(want, _hit_names(r))]
    if not matches:
        raise ValueError(f"TMDB identity mismatch: no title matches {expected_en!r}")
    # prefer a Korean-origin title, then TMDB's own relevance order
    hit = sorted(matches, key=lambda r: (0 if r.get("original_language") == "ko" else 1))[0]
    en = hit.get("name") or hit.get("title")
    orig = hit.get("original_name") or hit.get("original_title")
    ko = orig if hit.get("original_language") == "ko" else None
    if not en:
        raise ValueError("TMDB hit has no English title")
    return {
        "name_ko": ko or en,
        "name_en_official": en,
        "name_romanized": None,
        "name_en_source": "official",
        "name_en_confidence": "high",
        "tmdb_id": hit.get("id"),
        "summary_en": f"{en} - {hit.get('media_type', 'title')} (TMDB).",
        "summary_ko": f"{ko or en} - 영상 (TMDB).",
    }


class TMDBSource:
    name = "TMDB"
    is_fallback = False

    def __init__(self, aliases: dict[str, str] | None = None) -> None:
        self._aliases = aliases or {}

    def _term(self, entity_id: str) -> str:
        return NAMES.get(entity_id) or self._aliases.get(entity_id) or entity_id.split(":", 1)[-1]

    def _url(self, term: str, key: str) -> str:
        q = urllib.parse.urlencode({"api_key": key, "query": term, "include_adult": "false"})
        return f"{TMDB_API}?{q}"

    def _http_get(self, url: str) -> dict:
        return _http_get_json(url, _UA)

    async def fetch(self, entity_id: str, kind: str) -> dict:
        if not entity_id.startswith(_VIDEO):
            raise ValueError("TMDB covers drama/film/animation only")  # graceful drop
        key = os.environ.get("TMDB_API_KEY")
        if not key:
            raise ValueError("TMDB_API_KEY not set")  # inert until a free key is added (graceful)
        term = self._term(entity_id)
        raw = await asyncio.to_thread(self._http_get, self._url(term, key))
        payload = parse_tmdb(raw, term)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        return {"payload": payload, "citation": f"TMDB {payload.get('tmdb_id') or '?'} {ts}"}
