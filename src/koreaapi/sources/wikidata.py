"""Wikidata source adapter (real source #1).

Fetches an item's bilingual labels (Korean + English). Wikidata's `label` is the
canonical common name, so the EN label is treated as the official English name
(invariant 3: official names over translation).

Network egress is required at runtime (blocked in the dev sandbox), so the HTTP call
is kept thin and the PARSE step is pure + fixture-tested offline. On deploy (with
egress) `fetch()` works; here, tests exercise `parse_entity()` against a saved fixture.
"""

from __future__ import annotations

import asyncio
import json
import urllib.request
from datetime import datetime, timezone

WIKIDATA_API = "https://www.wikidata.org/w/api.php"
_UA = {"User-Agent": "KoreaAPI/0.1 (https://koreaapi.dev)"}

# Phase 1 entity -> Wikidata Q-id map (replace with live search once egress is available).
_QID = {
    "artist:bts": "Q484203",
    "artist:newjeans": "Q110343458",
    "artist:aespa": "Q97287573",
}


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


class WikidataSource:
    name = "Wikidata"
    is_fallback = False

    def _url(self, qid: str) -> str:
        return (
            f"{WIKIDATA_API}?action=wbgetentities&ids={qid}"
            "&props=labels|aliases&languages=ko|en&format=json"
        )

    async def fetch(self, entity_id: str, kind: str) -> dict:
        qid = _QID.get(entity_id)
        if not qid:
            raise ValueError(f"no Wikidata Q-id mapped for {entity_id}")

        def _get() -> dict:
            req = urllib.request.Request(self._url(qid), headers=_UA)
            with urllib.request.urlopen(req, timeout=10) as r:
                return json.load(r)

        raw = await asyncio.to_thread(_get)
        payload = parse_entity(raw, entity_id, kind)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        return {"payload": payload, "citation": f"Wikidata {qid} {ts}"}
