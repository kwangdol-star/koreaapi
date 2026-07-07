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
from .wikidata import _http_get_json, _name_match, _norm

MB_API = "https://musicbrainz.org/ws/2/artist"
MB_RECORDING = "https://musicbrainz.org/ws/2/recording"  # song: — a recording = a released track
_UA = {
    "User-Agent": "KoreaAPI/0.1 (https://github.com/kwangdol-star/koreaapi) python-urllib"
}


def _ko_alias(hit: dict) -> str | None:
    """The Korean-locale alias of a MusicBrainz artist hit, if any (e.g. BTS -> 방탄소년단)."""
    for a in hit.get("aliases") or []:
        if isinstance(a, dict) and (a.get("locale") or "").startswith("ko") and a.get("name"):
            return a["name"]
    return None


def _name_set(hit: dict) -> set[str]:
    """Every normalized name MusicBrainz knows for a hit (name + sort-name + all aliases)."""
    names = {hit.get("name"), hit.get("sort-name")}
    names.update(a.get("name") for a in hit.get("aliases") or [] if isinstance(a, dict))
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
    matches = [h for h in hits if isinstance(h, dict) and _name_match(want, _name_set(h))]
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


def _rec_names(hit: dict) -> set[str]:
    names = {hit.get("title")}
    names.update(a.get("name") for a in hit.get("aliases") or [] if isinstance(a, dict))
    return {_norm(n) for n in names if n}


def parse_mb_recording(raw: dict, expected_en: str) -> dict:
    """Pure: a MusicBrainz recording search response -> our payload, identity-guarded by the song
    title (title / aliases, normalized). English-title corroboration + performing artist as an attr;
    a title drift misses (never a wrong record). Recordings carry no country, so relevance order wins."""
    hits = raw.get("recordings") or []
    if not hits:
        raise ValueError("no MusicBrainz recording in response")
    want = _norm(expected_en)
    matches = [h for h in hits if isinstance(h, dict) and _name_match(want, _rec_names(h))]
    if not matches:
        raise ValueError(f"MusicBrainz identity mismatch: no recording matches {expected_en!r}")
    hit = matches[0]
    title = hit.get("title")
    if not title:
        raise ValueError("MusicBrainz recording has no title")
    ko = _ko_alias(hit)
    artist = ", ".join(ac["name"] for ac in hit.get("artist-credit") or []
                       if isinstance(ac, dict) and ac.get("name"))
    out = {
        "name_ko": ko or title,
        "name_en_official": title,
        "name_romanized": None,
        "name_en_source": "official",
        "name_en_confidence": "high",
        "mbid": hit.get("id"),
        "summary_en": f"{title} - song (MusicBrainz).",
        "summary_ko": f"{ko or title} - 곡 (뮤직브레인즈).",
    }
    if artist:
        out["attrs"] = {"Artist": artist}
    return out


class MusicBrainzSource:
    name = "MusicBrainz"
    is_fallback = False

    def __init__(self, aliases: dict[str, str] | None = None) -> None:
        self._aliases = aliases or {}

    def _term(self, entity_id: str) -> str:
        return NAMES.get(entity_id) or self._aliases.get(entity_id) or entity_id.split(":", 1)[-1]

    def _url(self, term: str, base: str = MB_API) -> str:
        q = urllib.parse.urlencode({"query": term, "fmt": "json", "limit": "5"})
        return f"{base}/?{q}"

    def _http_get(self, url: str) -> dict:
        return _http_get_json(url, _UA)

    async def fetch(self, entity_id: str, kind: str) -> dict:
        ns = entity_id.split(":", 1)[0]
        term = self._term(entity_id)
        if ns == "artist":
            raw = await asyncio.to_thread(self._http_get, self._url(term))
            payload = parse_mb_artist(raw, term)
        elif ns == "song":
            raw = await asyncio.to_thread(self._http_get, self._url(term, MB_RECORDING))
            payload = parse_mb_recording(raw, term)
        else:
            raise ValueError("MusicBrainz covers artists & songs only")  # graceful drop
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        return {"payload": payload, "citation": f"MusicBrainz {payload.get('mbid') or '?'} {ts}"}
