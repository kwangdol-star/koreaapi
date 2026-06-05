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
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from ..roster import ARTISTS

API = "https://www.googleapis.com/youtube/v3"
_UA = {
    "User-Agent": "KoreaAPI/0.1 (https://github.com/kwangdol-star/koreaapi) python-urllib"
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
    """Pick the first search candidate that passes the identity guard (else None — drop it).

    Defensive: skip non-dict entries, so passing a raw (un-parsed) response degrades to "no
    match" instead of crashing on a stray string."""
    for c in candidates:
        if isinstance(c, dict) and _channel_ok(c.get("title"), alias_norms):
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
        cands = parse_search(self._get(self._search_url(term)))  # parse BEFORE picking (not raw)
        picked = pick_channel(cands, _alias_norms(entity_id))
        return picked["channel_id"] if picked else None

    def _fetch_sync(self, entity_id: str) -> dict | None:
        """Resolve -> channels.list -> latest -> payload, synchronously. Mirrors diagnose's proven
        chain exactly (run in one thread by fetch). Returns None only when the channel can't be
        resolved; a real API/parse failure raises so fetch can surface the cause."""
        channel_id = self._resolve_channel(entity_id)
        if not channel_id:
            return None
        ch = parse_channel(self._get(self._channels_url(channel_id)))
        # A search-resolved channel already passed pick_channel's identity guard. A curated
        # _CHANNELS id is operator-verified, so it's trusted as-is - re-checking its title against
        # the alias set would false-reject a brand-titled official channel (e.g. BTS's "BANGTANTV");
        # parse_channel already confirms it resolved to a real channel.
        latest = None
        if ch.get("uploads_playlist"):
            try:
                latest = parse_latest(self._get(self._uploads_url(ch["uploads_playlist"])))
            except Exception:
                latest = None  # release info is optional; never fail the whole fetch for it
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

    async def fetch(self, entity_id: str) -> dict | None:
        """Resolve the official channel + pull stats/latest release. None on any failure (the loop
        never breaks); the cause is printed key-scrubbed so a 0-ingested run stays debuggable."""
        if not os.environ.get("YOUTUBE_API_KEY"):
            return None
        try:
            return await asyncio.to_thread(self._fetch_sync, entity_id)
        except Exception as e:
            key = os.environ.get("YOUTUBE_API_KEY") or ""
            msg = f"{type(e).__name__}: {e}"
            if key:
                msg = msg.replace(key, "<key>")  # never leak the key (it can appear in a URL)
            print(f"  youtube fetch failed for {entity_id}: {msg}", file=sys.stderr)
            return None

    def diagnose(self, entity_id: str) -> dict:
        """Walk the full fetch chain and report the exact step that fails. Reports key presence
        (boolean only - never the value), what search returned, the pick, and - critically - the
        channels.list result, so a 0-ingested run pinpoints keyless vs API-disabled vs guard-skip
        vs a downstream channels.list failure (the step `fetch` otherwise swallows)."""
        info: dict = {
            "entity": entity_id,
            "key_present": bool(os.environ.get("YOUTUBE_API_KEY")),
            "aliases": sorted(_alias_norms(entity_id)),
            "candidates": [],
            "picked": None,
            "channel_title": None,
            "subscribers": None,
            "step": "no_key",
            "error": None,
        }
        if not info["key_present"]:
            return info
        try:
            info["step"] = "search"
            term = ARTISTS.get(entity_id) or entity_id.split(":", 1)[-1].strip()
            cands = parse_search(self._get(self._search_url(term)))
            info["candidates"] = [c["title"] for c in cands]
            picked = pick_channel(cands, _alias_norms(entity_id))
            info["picked"] = picked["title"] if picked else None
            if not picked:
                info["step"] = "guard_skip"
                return info
            info["step"] = "channels.list"
            ch = parse_channel(self._get(self._channels_url(picked["channel_id"])))
            info["channel_title"] = ch.get("title")
            info["subscribers"] = ch.get("subscribers")
            info["step"] = "ok"  # search-resolved + channels.list succeeded -> fetch will ingest
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", "replace")[:300]
            except Exception:
                pass
            info["error"] = f"HTTP {e.code} at {info['step']}: {body or e.reason}"  # 'API not enabled' etc.
        except Exception as e:
            info["error"] = f"{type(e).__name__} at {info['step']}: {e}"
        return info
