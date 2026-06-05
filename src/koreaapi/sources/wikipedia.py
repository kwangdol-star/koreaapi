"""Wikipedia source adapter (real source #2) — an independent cross-check for the name.

Fetches an article's English title + its Korean interlanguage link via the MediaWiki action
API (credential-free, same egress pattern as Wikidata; works on deploy / GitHub runners).
Pairing this with Wikidata lets the ingestion CROSS-VERIFY the bilingual name from two
independent sources — when they agree the Skill Score clears the single-source cap
(verification is the product). The PARSE step is pure + fixture-tested offline.
"""

from __future__ import annotations

import asyncio
import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone

WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
_UA = {
    "User-Agent": "KoreaAPI/0.1 (https://github.com/kwangdol-star/koreaapi) python-urllib"
}

# entity_id -> English Wikipedia article title (curated fast path; else derive from the id).
_TITLES = {
    "artist:bts": "BTS",
    "artist:newjeans": "NewJeans",
    "artist:aespa": "Aespa",
    "artist:blackpink": "Blackpink",
    "artist:lesserafim": "Le Sserafim",
    "artist:straykids": "Stray Kids",
}


def parse_page(raw: dict, entity_id: str, kind: str) -> dict:
    """Pure: turn a MediaWiki `query` response (title + ko langlink) into our payload shape."""
    pages = raw.get("query", {}).get("pages", [])
    if not pages:
        raise ValueError("no page in Wikipedia response")
    page = pages[0]
    if page.get("missing"):
        raise ValueError("Wikipedia page missing")
    en = page.get("title")
    ko = None
    for ll in page.get("langlinks", []):
        if ll.get("lang") == "ko":
            ko = ll.get("title")
            break
    if not en and not ko:
        raise ValueError("no title in Wikipedia response")
    return {
        "name_ko": ko or en,
        "name_en_official": en,
        "name_romanized": None,
        "name_en_source": "official" if en else "llm",
        "name_en_confidence": "high" if en else "low",
        "summary_en": f"{en or ko} - {kind} (Wikipedia).",
        "summary_ko": f"{ko or en} - {kind} (위키백과).",
    }


class WikipediaSource:
    name = "Wikipedia"
    is_fallback = False

    def __init__(self, aliases: dict[str, str] | None = None) -> None:
        # entity_id -> article title for ids outside the curated map (e.g. swept labelmates).
        self._aliases: dict[str, str] = aliases or {}

    def _title(self, entity_id: str) -> str:
        return _TITLES.get(entity_id) or self._aliases.get(entity_id) or entity_id.split(":", 1)[-1].strip()

    def _url(self, title: str) -> str:
        query = urllib.parse.urlencode(
            {
                "action": "query",
                "titles": title,
                "prop": "langlinks",
                "lllang": "ko",
                "lllimit": "1",
                "redirects": "1",
                "format": "json",
                "formatversion": "2",
            }
        )
        return f"{WIKIPEDIA_API}?{query}"

    def _http_get(self, url: str) -> dict:
        req = urllib.request.Request(url, headers=_UA)
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.load(r)

    async def fetch(self, entity_id: str, kind: str) -> dict:
        title = self._title(entity_id)
        raw = await asyncio.to_thread(self._http_get, self._url(title))
        payload = parse_page(raw, entity_id, kind)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        return {"payload": payload, "citation": f"Wikipedia {payload['name_en_official']} {ts}"}
