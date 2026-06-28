"""MusicBrainz source adapter (real source #3) — a TRULY independent cross-check for artists.

Wikidata + Wikipedia are not fully independent (Wikipedia infoboxes feed Wikidata), so a third
source from a SEPARATE community/database materially strengthens the cross-verification. MusicBrainz
is the open music encyclopedia: free, credential-free JSON API (same egress pattern as Wikidata /
Wikipedia; works on deploy / GitHub runners), with Korean aliases for K-pop acts.

Scope: ARTISTS only (it's a music DB). For other verticals the third source is a different adapter
(roadmap: TMDB for drama/film/animation, Open Library for book/classic, Nominatim for place) — wire
them the same way in admin.pull via the namespace-aware source list. The PARSE + identity guard are
pure + fixture-tested offline; the live fetch runs on the open network (auto-skipped offline).
"""

from __future__ import annotations

import asyncio
import urllib.parse
from datetime import datetime, timezone

from ..roster import NAMES
from .wikidata import _http_get_json, _norm

MB_API = "https://musicbrainz.org/ws/2/artist"
_UA = {
    "User-Agent": "KoreaAPI/0.1 (https://github.com/kwangdol-star/koreaapi) python-urllib"
}


def _ko_alias(hit: dict) -> str | None:
    """The Korean-locale alias of a MusicBrainz artist hit, if any (e.g. BTS -> 방탄소년단)."""
    for a in hit.get("aliases") or []:
        if (a.get("locale") or "").startswith("ko") and a.get("name"):
            return a["name"]
    return None


def _name_set(hit: dict) -> set[str]:
    """Every normalized name MusicBrainz knows for a hit (name + sort-name + all aliases)."""
    names = {hit.get("name"), hit.get("sort-name")}
    names.update(a.get("name") for a in hit.get("aliases") or [])
    return {_norm(n) for n in names if n}


def parse_mb_artist(raw: dict, expected_en: str) -> dict:
    """Pure: a MusicBrainz artist search response -> our payload shape, identity-guarded.

    Picks the best hit that MATCHES the expected name (name / sort-name / any alias, normalized),
    preferring a Korean (country=KR) act. If nothing matches the expected name, raise — the search
    drifted to a same-name foreign artist, so we miss (graceful) rather than store a wrong record.
    """
    hits = raw.get("artists") or []
    if not hits:
        raise ValueError("no MusicBrainz artist in response")
    want = _norm(expected_en)
    matches = [h for h in hits if want and (want in _name_set(h)
               or any(want in n or n in want for n in _name_set(h) if n))]
    if not matches:
        raise ValueError(f"MusicBrainz identity mismatch: no hit matches {expected_en!r}")
    # prefer a Korean act, then MusicBrainz's own relevance order
    hit = sorted(matches, key=lambda h: (0 if h.get("country") == "KR" else 1))[0]
    en = hit.get("name")
    if not en:
        raise ValueError("MusicBrainz hit has no name")
    ko = _ko_alias(hit)
    return {
        "name_ko": ko or en,
        "name_en_official": en,
        "name_romanized": None,
        "name_en_source": "official",
        "name_en_confidence": "high",
        "mbid": hit.get("id"),
        "summary_en": f"{en} - artist (MusicBrainz).",
        "summary_ko": f"{ko or en} - 아티스트 (뮤직브레인즈).",
    }


class MusicBrainzSource:
    name = "MusicBrainz"
    is_fallback = False

    def __init__(self, aliases: dict[str, str] | None = None) -> None:
        self._aliases = aliases or {}

    def _term(self, entity_id: str) -> str:
        return NAMES.get(entity_id) or self._aliases.get(entity_id) or entity_id.split(":", 1)[-1]

    def _url(self, term: str) -> str:
        q = urllib.parse.urlencode({"query": term, "fmt": "json", "limit": "5"})
        return f"{MB_API}/?{q}"

    def _http_get(self, url: str) -> dict:
        return _http_get_json(url, _UA)

    async def fetch(self, entity_id: str, kind: str) -> dict:
        if not entity_id.startswith("artist:"):
            raise ValueError("MusicBrainz covers artists only")  # graceful drop for other verticals
        term = self._term(entity_id)
        raw = await asyncio.to_thread(self._http_get, self._url(term))
        payload = parse_mb_artist(raw, term)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        mbid = payload.get("mbid") or "?"
        return {"payload": payload, "citation": f"MusicBrainz {mbid} {ts}"}
