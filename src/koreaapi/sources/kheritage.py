"""국가유산청 (Korea Heritage Service, formerly 문화재청 / Cultural Heritage Administration) source — the
OFFICIAL Korean registry of 국가유산 (national heritage: historic sites, temples, palaces). Being listed is
a government endorsement, independent of Wikidata/Wikipedia/OSM — so it strengthens a heritage/temple/
palace record's provenance with an official source AND corroborates the KOREAN name (KHS is Korean-indexed).

Key-gated on KHERITAGE_API_KEY; INERT until set — ships DORMANT (no key on the deploy build, so it never
runs live) and self-activates once a key is added. The endpoint follows the classic CHA open API
(SearchKindOpenapiList); the agency was renamed 국가유산청 (khs.go.kr) in 2024, so KHERITAGE_URL is
env-overridable — point it at the current endpoint and VERIFY the field mapping (ccbaMnm1 / ccbaCtcdNm /
ccmaName) on first activation. The parse + identity guard are pure and offline-tested; a wrong guess
degrades to a MISS (never a wrong record). Scoped to heritage: / temple: / place: (palaces); searches by
the Korean 국가유산명 (roster.KHERITAGE_NAMES).
"""

from __future__ import annotations

import asyncio
import os
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from ..roster import KHERITAGE_NAMES
from .wikidata import _name_match, _norm

_DEFAULT_URL = "http://www.cha.go.kr/cha/SearchKindOpenapiList.do"  # classic CHA list endpoint (override on activation)
_UA = {"User-Agent": "KoreaAPI/0.1 (https://github.com/kwangdol-star/koreaapi)"}
_SCOPE = ("heritage", "temple", "place")


def parse_kheritage(xml_text: str, expected_ko: str) -> dict:
    """Pure: a CHA/KHS list XML response -> our payload, identity-guarded against the expected Korean
    heritage name. Raises if no KHS listing matches (miss, never wrong)."""
    want = _norm(expected_ko)
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        raise ValueError(f"KHS: unparseable XML ({e})") from e
    for item in root.iter("item"):
        name = (item.findtext("ccbaMnm1") or "").strip()
        if name and _name_match(want, {_norm(name)}):
            region = (item.findtext("ccbaCtcdNm") or "").strip() or None
            desig = (item.findtext("ccmaName") or "").strip() or None  # 국보 / 보물 / 사적 / 명승 …
            attrs = {k: v for k, v in (("Region", region), ("Designation", desig)) if v}
            out = {
                "name_ko": name,           # KHS carries the Korean 국가유산명 -> corroborates the Korean name
                "name_en_official": None,  # KHS is Korean-only (adds a source + official authority)
                "name_romanized": None,
                "name_en_source": None,
                "heritage_id": (item.findtext("ccbaAsno") or "").strip() or None,
                "summary_en": f"{name} - national heritage (국가유산청 / Korea Heritage Service).",
                "summary_ko": f"{name} - 국가유산 (국가유산청).",
            }
            if attrs:
                out["attrs"] = attrs
            return out
    raise ValueError(f"KHS: no heritage item matches {expected_ko!r}")


def _http_get_text(url: str) -> str:
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310 (fixed http/https host, no user scheme)
        return resp.read().decode("utf-8", "replace")


class KHeritageSource:
    name = "KHS"
    is_fallback = False

    def __init__(self, aliases: dict[str, str] | None = None) -> None:
        self._aliases = aliases or {}

    def _term(self, entity_id: str) -> str | None:
        return KHERITAGE_NAMES.get(entity_id) or self._aliases.get(entity_id)

    def _url(self, term: str, key: str) -> str:
        base = os.environ.get("KHERITAGE_URL") or _DEFAULT_URL
        params = urllib.parse.urlencode({"ccbaMnm1": term, "pageUnit": 10, "pageIndex": 1})
        sep = "&" if "?" in base else "?"
        # serviceKey appended raw (data.go.kr variants require it; the direct cha.go.kr endpoint ignores it).
        return f"{base}{sep}serviceKey={key}&{params}"

    def _http_get(self, url: str) -> str:
        return _http_get_text(url)

    async def fetch(self, entity_id: str, kind: str) -> dict:
        if entity_id.split(":", 1)[0] not in _SCOPE:
            raise ValueError("KHS covers national heritage (heritage:/temple:/place:) only")  # graceful drop
        term = self._term(entity_id)
        if not term:
            raise ValueError(f"no KHS Korean name for {entity_id}")  # graceful skip (name not mapped)
        key = os.environ.get("KHERITAGE_API_KEY")
        if not key:
            raise ValueError("KHERITAGE_API_KEY not set")  # inert until a service key is added
        raw = await asyncio.to_thread(self._http_get, self._url(term, key))
        payload = parse_kheritage(raw, term)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        return {"payload": payload, "citation": f"KHS (국가유산청) {payload.get('heritage_id') or '?'} {ts}"}
