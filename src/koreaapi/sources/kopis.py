"""KOPIS (공연예술통합전산망 / Korea Performing Arts Box Office Information System) source — the OFFICIAL
Korean registry of performing-arts VENUES (공연시설). Being listed in KOPIS is a government endorsement,
independent of Wikidata/Wikipedia/OSM — so it strengthens a theater's provenance with an official source
AND corroborates the KOREAN name (KOPIS is Korean-indexed, unlike KTO's English EngService).

Key-gated on KOPIS_API_KEY (a free kopis.or.kr service key); INERT until set — ships DORMANT (no key in
the deploy secrets, so it never runs on the live build) and self-activates once a key is added. Scoped
to `theater:` (KOPIS is 공연시설, not sports stadiums); searches by the Korean 시설명 (roster.KOPIS_NAMES).
The XML field mapping follows the KOPIS openapi `prfplc` spec — the parse + identity guard are pure and
offline-tested, and a wrong guess degrades to a MISS (never a wrong record); verify the live shape when
the key is first set.
"""

from __future__ import annotations

import asyncio
import os
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from ..roster import KOPIS_NAMES
from .wikidata import _name_match, _norm

KOPIS = "http://www.kopis.or.kr/openApi/restful/prfplc"
_UA = {"User-Agent": "KoreaAPI/0.1 (https://github.com/kwangdol-star/koreaapi)"}


def parse_kopis(xml_text: str, expected_ko: str) -> dict:
    """Pure: a KOPIS prfplc XML response -> our payload, identity-guarded against the expected Korean
    facility name. Raises if no KOPIS venue matches (miss, never wrong)."""
    want = _norm(expected_ko)
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        raise ValueError(f"KOPIS: unparseable XML ({e})") from e
    for db in root.iter("db"):
        fclty = (db.findtext("fcltynm") or "").strip()
        if fclty and _name_match(want, {_norm(fclty)}):
            region = (db.findtext("sidonm") or "").strip() or None
            opened = (db.findtext("opende") or "").strip() or None
            attrs = {k: v for k, v in (("Region", region), ("Opened", opened)) if v}
            out = {
                "name_ko": fclty,           # KOPIS carries the Korean 시설명 -> corroborates the Korean name
                "name_en_official": None,   # KOPIS has no English name (adds a source + official authority)
                "name_romanized": None,
                "name_en_source": None,
                "kopis_id": (db.findtext("mt10id") or "").strip() or None,
                "summary_en": f"{fclty} - performing-arts venue (KOPIS / 공연예술통합전산망).",
                "summary_ko": f"{fclty} - 공연시설 (KOPIS).",
            }
            if attrs:
                out["attrs"] = attrs
            return out
    raise ValueError(f"KOPIS: no venue matches {expected_ko!r}")


def _http_get_text(url: str) -> str:
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310 (fixed https/http host, no user input in scheme)
        return resp.read().decode("utf-8", "replace")


class KopisSource:
    name = "KOPIS"
    is_fallback = False

    def __init__(self, aliases: dict[str, str] | None = None) -> None:
        self._aliases = aliases or {}

    def _term(self, entity_id: str) -> str | None:
        return KOPIS_NAMES.get(entity_id) or self._aliases.get(entity_id)

    def _url(self, term: str, key: str) -> str:
        params = urllib.parse.urlencode({"service": key, "cpage": 1, "rows": 10, "shprfnmfct": term})
        return f"{KOPIS}?{params}"

    def _http_get(self, url: str) -> str:
        return _http_get_text(url)

    async def fetch(self, entity_id: str, kind: str) -> dict:
        if not entity_id.startswith("theater:"):
            raise ValueError("KOPIS covers performing-arts venues (theater:) only")  # graceful drop
        term = self._term(entity_id)
        if not term:
            raise ValueError(f"no KOPIS Korean name for {entity_id}")  # graceful skip (name not mapped)
        key = os.environ.get("KOPIS_API_KEY")
        if not key:
            raise ValueError("KOPIS_API_KEY not set")  # inert until a free kopis.or.kr key is added
        raw = await asyncio.to_thread(self._http_get, self._url(term, key))
        payload = parse_kopis(raw, term)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        return {"payload": payload, "citation": f"KOPIS (공연예술통합전산망) {payload.get('kopis_id') or '?'} {ts}"}
