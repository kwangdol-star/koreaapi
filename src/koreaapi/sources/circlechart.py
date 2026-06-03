"""Circle Chart settlement source (real source #3, prediction-market outcome data).

Circle Chart is Korea's OFFICIAL music chart - the settlement-grade source for chart-position
outcomes. Its own site (circlechart.kr) is **JS-rendered** (the HTML carries no chart), and it
403-blocks automated fetchers, so we cannot read it server-side. But the settlement-grade datum
- the **weekly #1** - is maintained, server-rendered and verifiable on Wikipedia's "List of
Circle Digital Chart number ones of <year>". So we fetch that via the MediaWiki API (compact
wikitext), LLM-EXTRACT the weekly #1s, and **GROUND** every entry against the fetched text
(`_grounded`) so a hallucinated/stale entry is dropped - verification over trust.

`parse_chart` + `_grounded` are pure + fixture-tested offline. The HTTP + LLM steps are
best-effort and need open network + ANTHROPIC_API_KEY (GitHub runners / deploy); no key /
blocked / nothing-grounded returns [] (never breaks). `CIRCLECHART_URL` is overridable - point
it at circlechart.kr's real XHR/JSON endpoint (from the site's Network tab) for the full daily
top-100; the grounding guard then applies there too.
"""

from __future__ import annotations

import asyncio
import json
import os
import urllib.request
from datetime import datetime, timezone

# Settlement source: Circle Digital Chart weekly #1s, server-rendered on Wikipedia, fetched as
# compact wikitext via the MediaWiki API. Overridable (e.g. circlechart.kr's own XHR endpoint).
_CIRCLE_NO1_PAGE = "List_of_Circle_Digital_Chart_number_ones_of_2026"
CIRCLECHART_URL = os.environ.get(
    "CIRCLECHART_URL",
    f"https://en.wikipedia.org/w/api.php?action=parse&page={_CIRCLE_NO1_PAGE}"
    "&prop=wikitext&format=json",
)
_UA = {
    "User-Agent": "KoreaAPI/0.1 (https://github.com/wrxfoundation/weatherplan-ai) python-urllib"
}
_MODEL = "claude-haiku-4-5-20251001"  # cheap extraction labor
_SYSTEM = (
    "You extract Korean music chart number-one songs from the page content (e.g. a Wikipedia "
    "table of weekly Circle Digital Chart #1s). Output ONLY a JSON array, each "
    '{"rank": 1, "artist": "<name>", "title": "<song title>"}, copied VERBATIM from the content, '
    "ordered MOST RECENT FIRST. If the content has no such chart/list, output []. Never invent "
    "entries or recall them from memory - extract only what is literally present. No prose, no code fence."
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
        """Fetch the #1-list source + LLM-extract + ground the entries. Best-effort: [] on failure."""
        try:
            html = await asyncio.to_thread(self._http_get_html, CIRCLECHART_URL)
        except Exception:
            html = ""
        entries = await asyncio.to_thread(extract_chart, html, limit=limit)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        via_wiki = "wikipedia.org" in CIRCLECHART_URL
        citation = f"Circle Digital Chart #1 (via Wikipedia) {ts}" if via_wiki else f"Circle Chart {ts}"
        source_url = (
            f"https://en.wikipedia.org/wiki/{_CIRCLE_NO1_PAGE}" if via_wiki else CIRCLECHART_URL
        )
        return {
            "entries": entries,
            "citation": citation,
            "source_url": source_url,  # human-readable origin (the article, not the API URL)
            "html_len": len(html),  # diagnostic: 0 = fetch blocked; large but 0 entries = not grounded
        }
