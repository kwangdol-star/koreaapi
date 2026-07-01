"""한국관광공사 (Korea Tourism Organization) TourAPI source — the OFFICIAL government tourism
authority for PLACES. Being listed in KTO's tourism database is an official endorsement (the same
authority the KTO Data Lab is built on), independent of Wikidata/Wikipedia/OSM — so it strengthens a
place's provenance with a government source and surfaces an "official tourism authority" badge.

Key-gated on TOURAPI_KEY (a free data.go.kr serviceKey); INERT until set (like TMDB) — ships dormant
and self-activates once the key is added to repo secrets. Self-filters to `place:`. EngService returns
the English title, so it corroborates the name + stamps the KTO authority (it doesn't carry the Korean
name, so it adds a source + official badge rather than boosting the bilingual agreement count).
Parse + identity guard are pure/offline-tested; the live call only runs where the key is set.
"""

from __future__ import annotations

import asyncio
import os
import urllib.parse
from datetime import datetime, timezone

from ..roster import NAMES
from .wikidata import _http_get_json, _name_match, _norm

TOURAPI = "https://apis.data.go.kr/B551011/EngService1/searchKeyword1"
_UA = {"User-Agent": "KoreaAPI/0.1 (https://github.com/kwangdol-star/koreaapi)"}


def _items(raw: dict) -> list:
    """The item list from a TourAPI JSON response (it returns a dict for 1 result, a list for many)."""
    body = (raw.get("response") or {}).get("body") or {}
    items = body.get("items") or {}
    if not isinstance(items, dict):  # "" when no results
        return []
    it = items.get("item") or []
    return it if isinstance(it, list) else [it]


def parse_tourapi(raw: dict, expected_en: str) -> dict:
    """Pure: a TourAPI searchKeyword response -> our payload, identity-guarded against the expected
    English name. Raises if no KTO listing matches (miss, never wrong)."""
    want = _norm(expected_en)
    for it in _items(raw):
        if isinstance(it, dict) and it.get("title") and _name_match(want, {_norm(it.get("title"))}):
            title = it["title"]
            # Official practical facts (address / tel / geo) ride along as attrs — they UNION with
            # the Wikidata attrs at ingest, giving the place page KTO-grade visiting detail.
            attrs = {k: v for k, v in (("Address", it.get("addr1")), ("Tel", it.get("tel"))) if v}
            if it.get("mapy") and it.get("mapx"):
                attrs["Coordinates"] = f"{it['mapy']},{it['mapx']}"  # lat,lon (KTO WGS84)
            out = {
                "name_ko": title,  # EngService has only the English title; folds (no Korean to verify)
                "name_en_official": title,
                "name_romanized": None,
                "name_en_source": "official",
                "name_en_confidence": "high",
                "tour_id": it.get("contentid"),
                "summary_en": f"{title} - place (한국관광공사 / KTO).",
                "summary_ko": f"{title} - 장소 (한국관광공사).",
            }
            if attrs:
                out["attrs"] = attrs
            return out
    raise ValueError(f"KTO TourAPI: no official listing matches {expected_en!r}")


class TourAPISource:
    name = "KTO"
    is_fallback = False

    def __init__(self, aliases: dict[str, str] | None = None) -> None:
        self._aliases = aliases or {}

    def _term(self, entity_id: str) -> str:
        return NAMES.get(entity_id) or self._aliases.get(entity_id) or entity_id.split(":", 1)[-1]

    def _url(self, term: str, key: str) -> str:
        params = urllib.parse.urlencode({
            "numOfRows": 5, "pageNo": 1, "MobileOS": "ETC", "MobileApp": "KoreaAPI",
            "_type": "json", "listYN": "Y", "arrange": "A", "keyword": term,
        })
        # serviceKey is appended RAW — data.go.kr keys are already URL-encoded; urlencode would double it.
        return f"{TOURAPI}?serviceKey={key}&{params}"

    def _http_get(self, url: str) -> dict:
        return _http_get_json(url, _UA)

    async def fetch(self, entity_id: str, kind: str) -> dict:
        if not entity_id.startswith("place:"):
            raise ValueError("KTO TourAPI covers places only")  # graceful drop for other verticals
        key = os.environ.get("TOURAPI_KEY")
        if not key:
            raise ValueError("TOURAPI_KEY not set")  # inert until a free data.go.kr key is added
        term = self._term(entity_id)
        raw = await asyncio.to_thread(self._http_get, self._url(term, key))
        payload = parse_tourapi(raw, term)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        return {"payload": payload, "citation": f"KTO (한국관광공사) {payload.get('tour_id') or '?'} {ts}"}
