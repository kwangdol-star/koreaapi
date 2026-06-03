"""Circle Chart source (real source #3, decision-gated outcome data).

Circle Chart is Korea's OFFICIAL music chart - the authoritative, public, settlement-grade
source for chart-position outcomes (the prediction-market vertical). No official API, so we
fetch the public weekly chart page and LLM-EXTRACT the entries ("cheap AI as collection
labor"; LLM extraction absorbs layout drift). Provenance cites Circle Chart + the week.

The PARSE step (`parse_chart`) is pure + fixture-tested offline. The HTTP + LLM steps are
best-effort and need the open network + ANTHROPIC_API_KEY (GitHub runners / deploy); a no-key
/ blocked / changed-page run returns [] (never breaks). URL is overridable via CIRCLECHART_URL.

NOTE: the live fetch is unverifiable from the egress-blocked sandbox - validate on a GitHub run
(or your own machine). If the page is JS-rendered, swap CIRCLECHART_URL for a data endpoint.
"""

from __future__ import annotations

import asyncio
import json
import os
import urllib.request
from datetime import datetime, timezone

# Official Circle digital chart (weekly). Overridable; e.g. global.circle?termGbn=week.
CIRCLECHART_URL = os.environ.get(
    "CIRCLECHART_URL", "https://circlechart.kr/page_chart/onoff.circle?serviceGbn=ALL"
)
_UA = {
    "User-Agent": "KoreaAPI/0.1 (https://github.com/wrxfoundation/weatherplan-ai) python-urllib"
}
_MODEL = "claude-haiku-4-5-20251001"  # cheap extraction labor
_SYSTEM = (
    "You extract a music chart from raw HTML. Output ONLY a JSON array of the chart entries, each "
    '{"rank": <int>, "artist": "<name>", "title": "<song title>"}, copied VERBATIM from the HTML. '
    "If the HTML contains no visible chart, output []. Never invent entries or recall them from "
    "memory - extract only what is literally present. No prose, no code fence."
)


def parse_chart(text: str, *, limit: int = 100) -> list[dict]:
    """Pure: turn the LLM's reply into a clean [{rank, artist, title}] list (tolerant)."""
    start, end = text.find("["), text.rfind("]")
    if start < 0 or end <= start:
        return []
    try:
        arr = json.loads(text[start : end + 1])
    except (ValueError, TypeError):
        return []
    out: list[dict] = []
    for e in arr if isinstance(arr, list) else []:
        if not isinstance(e, dict) or e.get("artist") in (None, "") or e.get("rank") is None:
            continue
        try:
            rank = int(e["rank"])
        except (ValueError, TypeError):
            continue
        out.append(
            {"rank": rank, "artist": str(e["artist"]).strip(), "title": str(e.get("title", "")).strip()}
        )
    return out[:limit]


def _grounded(entries: list[dict], html: str, *, limit: int = 100) -> list[dict]:
    """Anti-hallucination guard: keep only entries whose artist AND title literally appear in the
    source HTML. A JS-rendered page carries no chart in its HTML, so a model that invents entries
    from training memory (e.g. a stale '#1') is rejected here - verification over trust, the same
    doctrine as the identity guard. Without this, LLM extraction can fabricate a chart."""
    hay = html.casefold()
    out = [
        e
        for e in entries
        if (a := (e.get("artist") or "").casefold().strip())
        and (t := (e.get("title") or "").casefold().strip())
        and a in hay
        and t in hay
    ]
    return out[:limit]


def extract_chart(html: str, *, limit: int = 20) -> list[dict]:
    """Best-effort: LLM-extract chart entries from HTML, then GROUND them against the HTML (drop
    anything not literally present). [] without a key / on any failure / when nothing is grounded."""
    if not html or not os.environ.get("ANTHROPIC_API_KEY"):
        return []
    try:
        import anthropic

        msg = anthropic.Anthropic().messages.create(
            model=_MODEL,
            max_tokens=2000,
            system=_SYSTEM,
            messages=[{"role": "user", "content": html[:40000]}],
        )
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        return _grounded(parse_chart(text, limit=limit), html, limit=limit)  # reject hallucinations
    except Exception:
        return []


class CircleChartSource:
    name = "Circle Chart"

    def _http_get_html(self, url: str) -> str:
        req = urllib.request.Request(url, headers=_UA)
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.read().decode("utf-8", errors="replace")

    async def fetch_chart(self, *, limit: int = 20) -> dict:
        """Fetch the public chart page + LLM-extract entries. Best-effort: {} entries on failure."""
        try:
            html = await asyncio.to_thread(self._http_get_html, CIRCLECHART_URL)
        except Exception:
            html = ""
        entries = await asyncio.to_thread(extract_chart, html, limit=limit)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        return {
            "entries": entries,
            "citation": f"Circle Chart {ts}",
            "source_url": CIRCLECHART_URL,
            "html_len": len(html),  # diagnostic: 0 = fetch blocked; large but 0 entries = JS-rendered
        }
