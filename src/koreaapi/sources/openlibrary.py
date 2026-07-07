"""Open Library source adapter — an independent third source for BOOKS (Phase 2 Tier A).

Open Library (openlibrary.org, by the Internet Archive) is the open, credential-free bibliographic
database — same egress pattern as Wikidata/Wikipedia (works on deploy / GitHub runners). It corrobo-
rates a book's English title and stamps a work id + author + first-published year, so `book:` gains a
third independent source (Wikidata + Wikipedia + Open Library) beyond the two wiki sources.

Scope: BOOKS only. Its search returns the English title (no Korean), so — like KTO/Nominatim's
English-only corroboration — it adds a source + bibliographic attrs rather than boosting the bilingual
agreement count; identity is guarded by the expected English title (a drift -> miss, never wrong).
Parse + guard are pure/offline-tested; the live fetch runs on the open network.
"""

from __future__ import annotations

import asyncio
import urllib.parse
from datetime import datetime, timezone

from ..roster import NAMES
from .wikidata import _http_get_json, _name_match, _norm

OPENLIBRARY_API = "https://openlibrary.org/search.json"
_UA = {"User-Agent": "KoreaAPI/0.1 (https://github.com/kwangdol-star/koreaapi) python-urllib"}


def parse_openlibrary(raw: dict, expected_en: str) -> dict:
    """Pure: an Open Library search response -> our payload, identity-guarded against the expected
    English title. Picks the first doc whose title matches; raises if none does (miss, never wrong)."""
    want = _norm(expected_en)
    for doc in raw.get("docs") or []:
        if not isinstance(doc, dict):
            continue
        title = doc.get("title")
        if not title or not _name_match(want, {_norm(title)}):
            continue
        attrs = {}
        authors = [a for a in (doc.get("author_name") or []) if a]
        if authors:
            attrs["Author"] = ", ".join(authors[:3])
        if doc.get("first_publish_year"):
            attrs["First published"] = str(doc["first_publish_year"])
        out = {
            "name_ko": title,  # OL carries only the English title -> folds (no Korean to verify)
            "name_en_official": title,
            "name_romanized": None,
            "name_en_source": "official",
            "name_en_confidence": "high",
            "olid": doc.get("key"),  # e.g. /works/OL123W
            "summary_en": f"{title} - book (Open Library).",
            "summary_ko": f"{title} - 도서 (오픈 라이브러리).",
        }
        if attrs:
            out["attrs"] = attrs
        return out
    raise ValueError(f"Open Library: no work matches {expected_en!r}")


class OpenLibrarySource:
    name = "Open Library"
    is_fallback = False

    def __init__(self, aliases: dict[str, str] | None = None) -> None:
        self._aliases = aliases or {}

    def _term(self, entity_id: str) -> str:
        return NAMES.get(entity_id) or self._aliases.get(entity_id) or entity_id.split(":", 1)[-1]

    def _url(self, term: str) -> str:
        q = urllib.parse.urlencode({"q": term, "limit": "5",
                                    "fields": "key,title,author_name,first_publish_year"})
        return f"{OPENLIBRARY_API}?{q}"

    def _http_get(self, url: str) -> dict:
        return _http_get_json(url, _UA)

    async def fetch(self, entity_id: str, kind: str) -> dict:
        if not entity_id.startswith("book:"):
            raise ValueError("Open Library covers books only")  # graceful drop for other verticals
        term = self._term(entity_id)
        raw = await asyncio.to_thread(self._http_get, self._url(term))
        payload = parse_openlibrary(raw, term)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        return {"payload": payload, "citation": f"Open Library {payload.get('olid') or '?'} {ts}"}
