"""Nominatim / OpenStreetMap source adapter (independent 3rd source for PLACES).

OSM is a wholly separate community database from Wikidata/Wikipedia, so it's a genuine cross-check.
Via `namedetails` it returns both the Korean (name:ko) and English (name:en) names — so it works with
our strict bilingual cross-verification — plus coordinates (an independent corroboration of P625).
Free, credential-free (descriptive User-Agent required by OSM policy). Self-filters to `place:` —
raises for other verticals so it's safely added to every source list. Parse + guard are pure/offline.
"""

from __future__ import annotations

import asyncio
import urllib.parse
from datetime import datetime, timezone

from ..roster import NAMES
from .wikidata import _http_get_json, _norm

NOMINATIM_API = "https://nominatim.openstreetmap.org/search"
_UA = {
    "User-Agent": "KoreaAPI/0.1 (https://github.com/kwangdol-star/koreaapi) verified-culture-data"
}


def _hit_names(r: dict) -> set[str]:
    nd = r.get("namedetails") or {}
    raw = {nd.get("name"), nd.get("name:en"), nd.get("name:ko"),
           (r.get("display_name") or "").split(",")[0]}
    return {_norm(n) for n in raw if n}


def parse_nominatim(results: list, expected_en: str) -> dict:
    """Pure: an OSM Nominatim search response -> our payload shape, identity-guarded. Picks the hit
    whose name (ko/en/display) matches the expected name; raises if none do (miss, never wrong)."""
    want = _norm(expected_en)
    matches = [r for r in (results or [])
               if want and any(want in n or n in want for n in _hit_names(r) if n)]
    if not matches:
        raise ValueError(f"Nominatim identity mismatch: no Korean place matches {expected_en!r}")
    hit = matches[0]
    nd = hit.get("namedetails") or {}
    en = nd.get("name:en") or nd.get("name") or (hit.get("display_name") or "").split(",")[0]
    ko = nd.get("name:ko")
    if not en:
        raise ValueError("Nominatim hit has no usable name")
    return {
        "name_ko": ko or en,
        "name_en_official": en,
        "name_romanized": None,
        "name_en_source": "official",
        "name_en_confidence": "high",
        "osm_id": hit.get("osm_id"),
        "summary_en": f"{en} - place (OpenStreetMap).",
        "summary_ko": f"{ko or en} - 장소 (오픈스트리트맵).",
    }


class NominatimSource:
    name = "OpenStreetMap"
    is_fallback = False

    def __init__(self, aliases: dict[str, str] | None = None) -> None:
        self._aliases = aliases or {}

    def _term(self, entity_id: str) -> str:
        return NAMES.get(entity_id) or self._aliases.get(entity_id) or entity_id.split(":", 1)[-1]

    def _url(self, term: str) -> str:
        q = urllib.parse.urlencode({
            "q": term, "format": "jsonv2", "limit": "5",
            "namedetails": "1", "countrycodes": "kr", "accept-language": "en",
        })
        return f"{NOMINATIM_API}?{q}"

    def _http_get(self, url: str):
        return _http_get_json(url, _UA)

    async def fetch(self, entity_id: str, kind: str) -> dict:
        if not entity_id.startswith("place:"):
            raise ValueError("OpenStreetMap covers places only")  # graceful drop for other verticals
        term = self._term(entity_id)
        raw = await asyncio.to_thread(self._http_get, self._url(term))
        payload = parse_nominatim(raw, term)  # jsonv2 returns a list
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        return {"payload": payload, "citation": f"OpenStreetMap {payload.get('osm_id') or '?'} {ts}"}
