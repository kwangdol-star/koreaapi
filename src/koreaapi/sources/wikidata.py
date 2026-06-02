"""Wikidata source adapter (real source #1).

Fetches an item's bilingual labels (Korean + English). Wikidata's `label` is the
canonical common name, so the EN label is treated as the official English name
(invariant 3: official names over translation).

Two PARSE steps are pure and fixture-tested offline: `parse_entity` (labels) and
`parse_search` (entity lookup). The thin HTTP layer needs network egress at runtime.
A curated entity->Q-id map gives the hot Phase-1 artists a high-precision fast path and
carries each anchor's expected identity, so `fetch()` rejects a contradictory label
instead of ingesting it (invariant 2: no unverifiable data ships); anything else is
resolved live via `wbsearchentities` (egress required). On deploy with egress this runs
end-to-end; `tests/test_wikidata_live.py` is a live smoke test that auto-skips when
egress is blocked (sandbox allowlist -> HTTP 403 host_not_allowed).
"""

from __future__ import annotations

import asyncio
import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone

WIKIDATA_API = "https://www.wikidata.org/w/api.php"
# Wikimedia User-Agent policy: descriptive client/version + a contact URL + library.
# https://meta.wikimedia.org/wiki/User-Agent_policy  (repo URL is the reachable contact)
_UA = {
    "User-Agent": "KoreaAPI/0.1 (https://github.com/wrxfoundation/weatherplan-ai) python-urllib"
}

# Curated anchors: entity_id -> Q-id + expected identity (our highest-trust pins).
# The expected names let fetch() VERIFY the live response really is the entity we pinned
# and REJECT a contradictory label (invariant 2) instead of stamping a wrong name as
# 'official'. Anything not listed here is resolved live via wbsearchentities.
_CURATED = {
    "artist:bts": {"qid": "Q484203", "ko": "방탄소년단", "en": "BTS"},
    "artist:newjeans": {"qid": "Q110343458", "ko": "뉴진스", "en": "NewJeans"},
    "artist:aespa": {"qid": "Q97287573", "ko": "에스파", "en": "aespa"},
}
# Back-compat: plain entity_id -> Q-id view (used by resolve_qid's fast path).
_QID = {eid: meta["qid"] for eid, meta in _CURATED.items()}


def parse_entity(raw: dict, entity_id: str, kind: str) -> dict:
    """Pure: turn a Wikidata `wbgetentities` response into our payload shape."""
    ents = raw.get("entities", {})
    if not ents:
        raise ValueError("no entity in Wikidata response")
    item = next(iter(ents.values()))
    labels = item.get("labels", {})
    ko = labels.get("ko", {}).get("value")
    en = labels.get("en", {}).get("value")
    if not ko and not en:
        raise ValueError("no ko/en label in Wikidata response")
    return {
        "name_ko": ko or en,
        "name_en_official": en,
        "name_romanized": None,  # Wikidata rarely carries clean romanization; filled elsewhere
        "name_en_source": "official" if en else "llm",
        "name_en_confidence": "high" if en else "low",
        "summary_en": f"{en or ko} - {kind} (Wikidata labels).",
        "summary_ko": f"{ko or en} - {kind} (위키데이터 라벨).",
    }


def parse_search(raw: dict) -> str | None:
    """Pure: pick the top hit's Q-id from a `wbsearchentities` response (None if no hit)."""
    hits = raw.get("search", [])
    if not hits:
        return None
    return hits[0].get("id")


def _verify_identity(payload: dict, expected: dict) -> None:
    """Reject a curated anchor whose fetched label contradicts its known identity.

    Invariant 2 (PRINCIPLES.md): no unverifiable data ships. For entities we pinned by
    Q-id we KNOW who they are, so a label matching neither the expected Korean nor English
    name (e.g. BTS coming back as something else) signals a wrong/stale Q-id or a corrupted
    response - raise so the pipeline drops it instead of poisoning the append-only store.
    """
    got = {
        (payload.get("name_ko") or "").strip().casefold(),
        (payload.get("name_en_official") or "").strip().casefold(),
    }
    got.discard("")
    want = {
        (expected.get("ko") or "").strip().casefold(),
        (expected.get("en") or "").strip().casefold(),
    }
    want.discard("")
    if want and got.isdisjoint(want):
        raise ValueError(
            f"identity mismatch: fetched {sorted(got)} matches none of expected {sorted(want)}"
        )


class WikidataSource:
    name = "Wikidata"
    is_fallback = False

    def __init__(self) -> None:
        # entity_id -> Q-id discovered via live search (memoized to spare the API).
        self._discovered: dict[str, str] = {}

    def _entity_url(self, qid: str) -> str:
        return (
            f"{WIKIDATA_API}?action=wbgetentities&ids={qid}"
            "&props=labels|aliases&languages=ko|en&format=json"
        )

    def _search_url(self, term: str) -> str:
        query = urllib.parse.urlencode(
            {
                "action": "wbsearchentities",
                "search": term,
                "language": "en",
                "uselang": "en",
                "type": "item",
                "limit": 1,
                "format": "json",
            }
        )
        return f"{WIKIDATA_API}?{query}"

    def _http_get(self, url: str) -> dict:
        req = urllib.request.Request(url, headers=_UA)
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.load(r)

    async def resolve_qid(self, entity_id: str) -> str:
        """entity_id -> Q-id. Curated map first (precision), then memoized live search."""
        if entity_id in _QID:
            return _QID[entity_id]
        if entity_id in self._discovered:
            return self._discovered[entity_id]
        term = entity_id.split(":", 1)[-1].strip()
        if not term:
            raise ValueError(f"cannot derive a search term from entity_id {entity_id!r}")
        raw = await asyncio.to_thread(self._http_get, self._search_url(term))
        qid = parse_search(raw)
        if not qid:
            raise ValueError(f"no Wikidata match for {entity_id!r} (searched {term!r})")
        self._discovered[entity_id] = qid
        return qid

    async def fetch(self, entity_id: str, kind: str) -> dict:
        qid = await self.resolve_qid(entity_id)
        raw = await asyncio.to_thread(self._http_get, self._entity_url(qid))
        payload = parse_entity(raw, entity_id, kind)
        expected = _CURATED.get(entity_id)
        if expected:
            _verify_identity(payload, expected)  # reject contradictory data (invariant 2)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        return {"payload": payload, "citation": f"Wikidata {qid} {ts}"}
