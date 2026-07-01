"""KOSIS (국가통계포털 / Korean Statistical Information Service) source — OFFICIAL government
statistics for REGIONS. Attaches the resident-registration population (주민등록인구, KOSIS table
DT_1B040A3, 통계청 orgId 101) to `region:` entities as a supplementary attr with a government
citation — the institutional-authority tier for regions, like KTO is for places.

Key-gated on KOSIS_API_KEY (free at kosis.kr → 공유서비스 → OpenAPI); INERT until set (ships
dormant, self-activates once the key lands in repo secrets). Self-filters to `region:`.

Identity-guarded by the region's KOREAN NAME: the response carries the region name (C1_NM), and a
row only counts if it starts with the expected Korean prefix AND its item name (ITM_NM) is a
population item. Administrative codes DO drift (강원 42→51, 전북 45→52, 제주 49→50 after the
special-self-governing renames), so the NAME is the contract — a wrong/drifted code fails to a
miss, never a wrong number. Parse + guard are pure/offline-tested; the live call needs the key.
"""

from __future__ import annotations

import asyncio
import os
import urllib.parse
from datetime import datetime, timezone

from ..roster import NAMES
from .wikidata import _http_get_json

KOSIS = "https://kosis.kr/openapi/Param/statisticsParameterData.do"
_UA = {"User-Agent": "KoreaAPI/0.1 (https://github.com/kwangdol-star/koreaapi)"}

# region entity -> (objL1 administrative code, accepted Korean-name prefixes). The prefixes are the
# guard: whatever the code returns must NAME itself as this region (post-rename forms included).
REGIONS = {
    "region:southkorea": ("00", ("전국",)),
    "region:seoul": ("11", ("서울",)),
    "region:busan": ("26", ("부산",)),
    "region:daegu": ("27", ("대구",)),
    "region:incheon": ("28", ("인천",)),
    "region:gwangju": ("29", ("광주",)),
    "region:daejeon": ("30", ("대전",)),
    "region:ulsan": ("31", ("울산",)),
    "region:sejong": ("36", ("세종",)),
    "region:gyeonggi": ("41", ("경기",)),
    "region:gangwon": ("51", ("강원",)),
    "region:northchungcheong": ("43", ("충청북", "충북")),
    "region:southchungcheong": ("44", ("충청남", "충남")),
    "region:northjeolla": ("52", ("전라북", "전북")),
    "region:southjeolla": ("46", ("전라남", "전남")),
    "region:northgyeongsang": ("47", ("경상북", "경북")),
    "region:southgyeongsang": ("48", ("경상남", "경남")),
    "region:jeju": ("50", ("제주",)),
}


def parse_kosis(raw, entity_id: str, expected_prefixes: tuple[str, ...]) -> dict:
    """Pure: a KOSIS getList JSON response (a list of rows) -> our payload, guarded by the region's
    Korean name AND a population item name. Raises when nothing safely matches (miss, never wrong)."""
    rows = raw if isinstance(raw, list) else []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("C1_NM") or "")
        if not name or not any(name.startswith(p) for p in expected_prefixes):
            continue  # a drifted code returns some OTHER region -> refuse it
        if "인구" not in str(row.get("ITM_NM") or ""):
            continue  # not a population item (e.g. 세대수) -> refuse it
        val = str(row.get("DT") or "").replace(",", "")
        try:
            pop = int(float(val))
        except ValueError:
            continue
        period = str(row.get("PRD_DE") or "")
        en = NAMES.get(entity_id) or entity_id.split(":", 1)[-1]
        shown = f"{pop:,}" + (f" ({period})" if period else "")
        return {
            "name_ko": name,  # the official administrative name (e.g. 서울특별시)
            "name_en_official": en,
            "name_romanized": None,
            "name_en_source": "official",
            "name_en_confidence": "high",
            "attrs": {"Population": shown},
            "kosis_period": period,
            "summary_en": f"{en} - population {pop:,} (KOSIS resident registration, {period}).",
            "summary_ko": f"{name} - 인구 {pop:,}명 (KOSIS 주민등록인구, {period}).",
        }
    raise ValueError(f"KOSIS: no guarded population row for {entity_id}")


class KOSISSource:
    name = "KOSIS"
    is_fallback = False

    def __init__(self, aliases: dict[str, str] | None = None) -> None:
        self._aliases = aliases or {}

    def _url(self, code: str, key: str) -> str:
        params = urllib.parse.urlencode({
            "method": "getList", "apiKey": key, "orgId": "101", "tblId": "DT_1B040A3",
            "itmId": "T20", "objL1": code, "format": "json", "jsonVD": "Y",
            "prdSe": "M", "newEstPrdCnt": "1",  # latest monthly period only
        })
        return f"{KOSIS}?{params}"

    def _http_get(self, url: str) -> dict:
        return _http_get_json(url, _UA)

    async def fetch(self, entity_id: str, kind: str) -> dict:
        if not entity_id.startswith("region:"):
            raise ValueError("KOSIS covers regions only")  # graceful drop for other verticals
        key = os.environ.get("KOSIS_API_KEY")
        if not key:
            raise ValueError("KOSIS_API_KEY not set")  # inert until a free kosis.kr key is added
        code, prefixes = REGIONS.get(entity_id, (None, ()))
        if not code:
            raise ValueError(f"no KOSIS region code for {entity_id}")
        raw = await asyncio.to_thread(self._http_get, self._url(code, key))
        payload = parse_kosis(raw, entity_id, prefixes)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        return {"payload": payload,
                "citation": f"KOSIS 주민등록인구 DT_1B040A3 {payload.get('kosis_period') or '?'} {ts}"}
