"""YouTube Data API v3 source (real source #3.5) — live-state event data, NOT name verification.

Role (deliberate): YouTube does **not** vote in the bilingual `ko|en` name-agreement scorer.
An artist's official channel is English/brand-titled (BTS's is "BANGTANTV"), so feeding it into
the cross-verification key would *lower* the 1.00 scores Wikidata+Wikipedia already earn — the
Spotify lesson. YouTube's unique value is **live-state**: official-channel stats + latest
release = settlement-grade event data for the prediction-market vertical and a velocity signal
for engine ②. So it appends a `kind="release"` snapshot (single official source → honestly
single-source-capped), separate from the name scorer.

Channel resolution mirrors Wikidata's doctrine: a curated, LIVE-VERIFIED channel map is the
high-precision path; otherwise resolve live via `search.list` and an **identity guard** — the
channel's title must equal one of the artist's known aliases — so a fan / impostor channel is
never ingested (invariant 2: unverifiable = not ingested). No channel id is hardcoded blind
(the Arborka lesson); `_CHANNELS` is filled only after a verified run.

Pure PARSE steps (`parse_search` / `parse_channel` / `parse_latest`) + the guard are
fixture-tested offline. The HTTP layer needs `YOUTUBE_API_KEY` + egress (GitHub runner / your
machine); no key, a blocked response, or a channel that fails the guard → nothing ingested
(graceful, never breaks). The key travels only in the request URL — never logged or printed.
"""

from __future__ import annotations

import asyncio
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from ..roster import ARTISTS

API = "https://www.googleapis.com/youtube/v3"
_UA = {
    "User-Agent": "KoreaAPI/0.1 (https://github.com/wrxfoundation/weatherplan-ai) python-urllib"
}

# entity_id -> LIVE-VERIFIED official channel id (high-precision fast path). Empty by default:
# promote an id here only after a verified run confirms it (never hardcode blind — Arborka).
_CHANNELS: dict[str, str] = {}

# entity_id -> extra known-official channel display titles beyond the roster name. The roster
# name already covers exact-title channels (NewJeans, aespa, BLACKPINK, Stray Kids); add only a
# title whose channel is the artist's OWN (not a multi-artist label), and verify it live first.
_ALIASES: dict[str, tuple[str, ...]] = {
    "artist:bts": ("BANGTANTV",),  # BTS's official channel display title (verify on a live run)
}


def _norm(s: str | None) -> str:
    """Normalize a title for identity comparison: drop case and spaces (same as the sources)."""
    return (s or "").casefold().replace(" ", "")


def parse_search(raw: dict) -> list[dict]:
    """Pure: channel candidates from a `search.list` (type=channel) response."""
    out: list[dict] = []
    for it in raw.get("items", []):
        cid = (it.get("id") or {}).get("channelId")
        title = (it.get("snippet") or {}).get("title")
        if cid and title:
            out.append({"channel_id": cid, "title": title})
    return out


def _to_int(x) -> int | None:
    try:
        return int(x)
    except (TypeError, ValueError):
        return None


def parse_channel(raw: dict) -> dict:
    """Pure: channel stats + the uploads playlist id from a `channels.list` response."""
    items = raw.get("items") or []
    if not items:
        raise ValueError("no channel in YouTube response")
    it = items[0]
    sn = it.get("snippet") or {}
    st = it.get("statistics") or {}
    cd = it.get("contentDetails") or {}
    subs = None if st.get("hiddenSubscriberCount") else _to_int(st.get("subscriberCount"))
    return {
        "channel_id": it.get("id"),
        "title": sn.get("title"),
        "subscribers": subs,
        "views": _to_int(st.get("viewCount")),
        "videos": _to_int(st.get("videoCount")),
        "uploads_playlist": (cd.get("relatedPlaylists") or {}).get("uploads"),
    }


def parse_latest(raw: dict) -> dict | None:
    """Pure: the most recent upload from a `playlistItems.list` response (None if empty)."""
    items = raw.get("items") or []
    if not items:
        return None
    sn = items[0].get("snippet") or {}
    cd = items[0].get("contentDetails") or {}
    vid = (sn.get("resourceId") or {}).get("videoId") or cd.get("videoId")
    title = sn.get("title")
    published = cd.get("videoPublishedAt") or sn.get("publishedAt")
    if not vid and not title:
        return None
    return {"video_id": vid, "title": title, "published_at": published}


def _alias_norms(entity_id: str) -> set[str]:
    """Normalized accepted titles for an artist: the roster name + any curated aliases."""
    names = {ARTISTS.get(entity_id, "")} | set(_ALIASES.get(entity_id, ()))
    return {_norm(n) for n in names if n}


def _channel_ok(title: str | None, alias_norms: set[str]) -> bool:
    """Identity guard: accept a channel only if its title exactly matches a known alias."""
    return bool(alias_norms) and _norm(title) in alias_norms


def pick_channel(candidates: list[dict], alias_norms: set[str]) -> dict | None:
    """Pick the first search candidate that passes the identity guard (else None — drop it)."""
    for c in candidates:
        if _channel_ok(c.get("title"), alias_norms):
            return c
    return None


class YouTubeSource:
    name = "YouTube"

    def _key(self) -> str:
        return os.environ["YOUTUBE_API_KEY"]  # presence checked by caller before fetch

    def _get(self, url: str) -> dict:
        req = urllib.request.Request(url, headers=_UA)
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.load(r)

    def _search_url(self, term: str) -> str:
        q = urllib.parse.urlencode(
            {"part": "snippet", "type": "channel", "q": term, "maxResults": 5, "key": self._key()}
        )
        return f"{API}/search?{q}"

    def _channels_url(self, channel_id: str) -> str:
        q = urllib.parse.urlencode(
            {"part": "snippet,statistics,contentDetails", "id": channel_id, "key": self._key()}
        )
        return f"{API}/channels?{q}"

    def _uploads_url(self, playlist_id: str) -> str:
        q = urllib.parse.urlencode(
            {
                "part": "snippet,contentDetails",
                "playlistId": playlist_id,
                "maxResults": 1,
                "key": self._key(),
            }
        )
        return f"{API}/playlistItems?{q}"

    def _resolve_channel(self, entity_id: str) -> str | None:
        """Curated verified id first (precision); else live search + identity guard."""
        if entity_id in _CHANNELS:
            return _CHANNELS[entity_id]
        term = ARTISTS.get(entity_id) or entity_id.split(":", 1)[-1].strip()
        if not term:
            return None
        picked = pick_channel(self._get(self._search_url(term)), _alias_norms(entity_id))
        return picked["channel_id"] if picked else None

    async def fetch(self, entity_id: str) -> dict | None:
        """Resolve the official channel, then pull stats + latest release. None on any failure."""
        if not os.environ.get("YOUTUBE_API_KEY"):
            return None
        try:
            channel_id = await asyncio.to_thread(self._resolve_channel, entity_id)
            if not channel_id:
                return None
            ch = parse_channel(await asyncio.to_thread(self._get, self._channels_url(channel_id)))
            if not _channel_ok(ch.get("title"), _alias_norms(entity_id)):
                return None  # guard a wrong curated id too (invariant 2)
            latest = None
            if ch.get("uploads_playlist"):
                try:
                    raw = await asyncio.to_thread(self._get, self._uploads_url(ch["uploads_playlist"]))
                    latest = parse_latest(raw)
                except Exception:
                    latest = None
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            return {
                "channel_id": ch["channel_id"],
                "title": ch.get("title"),
                "subscribers": ch.get("subscribers"),
                "views": ch.get("views"),
                "videos": ch.get("videos"),
                "latest": latest,
                "name_en": ARTISTS.get(entity_id) or entity_id.split(":", 1)[-1],
                "citation": f"YouTube {ch.get('title')} {ts}",
                "source_url": f"https://www.youtube.com/channel/{ch['channel_id']}",
            }
        except Exception:
            return None  # graceful degradation: never break the loop
