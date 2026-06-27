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
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from ..roster import AGENCY_HINTS, NAMES


def _http_get_json(url: str, headers: dict, *, attempts: int = 4, timeout: int = 20,
                   net_attempts: int = 2) -> dict:
    """GET JSON, retrying on Wikimedia THROTTLING so a big batch never loses its tail.

    At ~100 entities the live pull fires hundreds of Wikidata calls; without this, throttling
    (HTTP 429/503) silently drops the entities that sort last (dramas/films) — so a throttle must
    back off (honoring Retry-After) and retry, up to `attempts`. A hard network error (URLError /
    timeout: DNS, connection-refused, a blocked-egress sandbox) is unlikely to clear, so it retries
    only `net_attempts` times quickly — keeping offline runs fast. Sync (run in a thread); the final
    failure still raises so the caller degrades gracefully for that one entity (never the batch)."""
    for i in range(attempts):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:  # subclass of URLError -> catch first
            if e.code in (429, 503) and i < attempts - 1:  # explicit "retry later"
                ra = e.headers.get("Retry-After") if e.headers else None
                time.sleep(min(float(ra) if (ra and ra.isdigit()) else 2 ** i, 10))
                continue
            raise  # 403/404/UA-block etc. won't clear on retry
        except (urllib.error.URLError, TimeoutError):  # hard network error: retry briefly, then give up
            if i < net_attempts - 1:
                time.sleep(1)
                continue
            raise

WIKIDATA_API = "https://www.wikidata.org/w/api.php"
WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"  # agency-hub roster discovery (sweep)
# Wikimedia User-Agent policy: descriptive client/version + a contact URL + library.
# https://meta.wikimedia.org/wiki/User-Agent_policy  (repo URL is the reachable contact)
_UA = {
    "User-Agent": "KoreaAPI/0.1 (https://github.com/kwangdol-star/koreaapi) python-urllib"
}

# Curated anchors: entity_id -> Q-id + expected identity (our highest-trust pins).
# Q-ids verified against LIVE Wikidata (2026-06-02) via wbsearchentities - the earlier
# offline-guessed ids were all wrong (e.g. Q484203 is "Arborka", not BTS), which the
# identity guard caught. The expected names let fetch() VERIFY the live response really is
# the entity we pinned and REJECT a contradictory label (invariant 2) instead of stamping a
# wrong name as 'official'. Anything not listed here is resolved live via wbsearchentities.
# `agency` is a disambiguation HINT: Wikidata's P264 can list several labels (e.g. a foreign
# distribution label alongside the primary 소속사), so for a known artist the hint picks the RIGHT
# one among the LIVE values - it never fabricates (same spirit as the identity guard).
_CURATED = {
    "artist:bts": {"qid": "Q13580495", "ko": "방탄소년단", "en": "BTS", "agency": "Big Hit"},
    "artist:newjeans": {"qid": "Q113189277", "ko": "뉴진스", "en": "NewJeans", "agency": "ADOR"},
    "artist:aespa": {"qid": "Q100877982", "ko": "에스파", "en": "aespa", "agency": "SM Entertainment"},
    # Collision-prone but important — NO qid (resolved live by search), but the bilingual identity is
    # pinned so the strict guard rejects a same-EN-label impostor by its Korean name (TREASURE -> 보물,
    # the concept; Parasite the film vs 기생충 the organism). Worst case a miss, never a wrong record.
    "artist:twice": {"ko": "트와이스", "en": "TWICE", "agency": "JYP"},
    "artist:seventeen": {"ko": "세븐틴", "en": "Seventeen", "agency": "Pledis"},
    "artist:redvelvet": {"ko": "레드벨벳", "en": "Red Velvet", "agency": "SM Entertainment"},
    "artist:treasure": {"ko": "트레저", "en": "Treasure", "agency": "YG"},
    "artist:ive": {"ko": "아이브", "en": "IVE", "agency": "Starship"},
    "artist:nct": {"ko": "엔시티", "en": "NCT", "agency": "SM Entertainment"},
    "artist:exo": {"ko": "엑소", "en": "EXO", "agency": "SM Entertainment"},
    "artist:iu": {"ko": "아이유", "en": "IU", "agency": "EDAM"},
    # Generic-but-essential film title: pinned by VERIFIED Q-id (Parasite, 2019) so search can't drift
    # to 기생충 the organism (which shares both names). A wrong qid would be caught by the guard -> miss.
    "film:parasite": {"qid": "Q61448040", "ko": "기생충", "en": "Parasite"},
    "film:oldboy": {"ko": "올드보이", "en": "Oldboy"},
    # Batch 2 — collision-prone names (a real word / real person shares the English): bilingual pin so
    # the strict KO guard rejects the impostor. No qid -> resolved live by search, then guarded.
    "artist:kissoflife": {"ko": "키스오브라이프", "en": "Kiss of Life", "agency": "S2"},
    "artist:ohmygirl": {"ko": "오마이걸", "en": "Oh My Girl", "agency": "WM"},
    "artist:everglow": {"ko": "에버글로우", "en": "EVERGLOW", "agency": "Yuehua"},
    "artist:zico": {"ko": "지코", "en": "Zico", "agency": "KOZ"},
    "artist:boynextdoor": {"ko": "보이넥스트도어", "en": "BOYNEXTDOOR", "agency": "KOZ"},
    "film:ahardday": {"ko": "끝까지 간다", "en": "A Hard Day"},
    "film:svaha": {"ko": "사바하", "en": "Svaha"},
}
# Back-compat: plain entity_id -> Q-id view (used by resolve_qid's fast path). Only entries that
# actually pin a Q-id; bilingual-only anchors fall through to live search + the strict identity guard.
_QID = {eid: meta["qid"] for eid, meta in _CURATED.items() if meta.get("qid")}


def _claim_qids(item: dict, prop: str) -> list[str]:
    """Pure: the entity Q-ids a property points to, 'preferred'-rank first (e.g. P264 label)."""
    ranked: list[tuple[int, str]] = []
    for claim in item.get("claims", {}).get(prop, []):
        ms = claim.get("mainsnak", {})
        if ms.get("snaktype") != "value":
            continue  # skip 'novalue'/'somevalue'
        qid = ((ms.get("datavalue") or {}).get("value") or {}).get("id")
        if qid:
            ranked.append((0 if claim.get("rank") == "preferred" else 1, qid))
    ranked.sort(key=lambda r: r[0])
    return [q for _, q in ranked]


def _claim_time(item: dict, prop: str) -> str | None:
    """Pure: a date string ('2013' or '2013-06-13') from a time-valued claim (e.g. P571 inception)."""
    for claim in item.get("claims", {}).get(prop, []):
        ms = claim.get("mainsnak", {})
        if ms.get("snaktype") != "value":
            continue
        t = ((ms.get("datavalue") or {}).get("value") or {}).get("time")  # "+2013-06-13T00:00:00Z"
        if not t:
            continue
        date = t.lstrip("+").split("T")[0]  # "2013-06-13" or "2013-00-00"
        y, m, d = (date.split("-") + ["00", "00"])[:3]
        if not y or y == "0000":
            continue
        return y if m in ("00", "") else (f"{y}-{m}" if d in ("00", "") else f"{y}-{m}-{d}")
    return None


def parse_entity(raw: dict, entity_id: str, kind: str) -> dict:
    """Pure: turn a Wikidata `wbgetentities` response into our payload shape (incl. verified K-pop
    facts an agent/fan asks for: agency, debut, active status, member Q-ids)."""
    ents = raw.get("entities", {})
    if not ents:
        raise ValueError("no entity in Wikidata response")
    item = next(iter(ents.values()))
    labels = item.get("labels", {})
    ko = labels.get("ko", {}).get("value")
    en = labels.get("en", {}).get("value")
    if not ko and not en:
        raise ValueError("no ko/en label in Wikidata response")
    is_video = entity_id.startswith(("drama:", "film:"))  # drama/film: air-or-release date + cast
    return {
        "name_ko": ko or en,
        "name_en_official": en,
        "name_romanized": None,  # Wikidata rarely carries clean romanization; filled elsewhere
        "name_en_source": "official" if en else "llm",
        "name_en_confidence": "high" if en else "low",
        # Music: 소속사 (P264), members (P527), debut (P571). Drama/film: original network/platform
        # (P449, e.g. Netflix/tvN — reusing the agency machinery), air/release date (P577), cast (P161).
        "agency_qids": _claim_qids(item, "P449") if is_video else _claim_qids(item, "P264"),
        "debut": _claim_time(item, "P577" if is_video else "P571"),
        "active": "active" if is_video else ("disbanded" if _claim_time(item, "P576") else "active"),
        "member_qids": _claim_qids(item, "P161") if is_video else _claim_qids(item, "P527"),
        "director_qids": _claim_qids(item, "P57") if is_video else [],  # drama/film director(s)
        "summary_en": f"{en or ko} - {kind} (Wikidata labels).",
        "summary_ko": f"{ko or en} - {kind} (위키데이터 라벨).",
    }


def parse_member_names(raw: dict, qids: list[str]) -> list[str]:
    """Pure: resolve member Q-ids -> EN (or KO) names from a batched wbgetentities labels response,
    preserving the P527 order and dropping any that didn't resolve."""
    ents = raw.get("entities", {})
    out: list[str] = []
    for q in qids:
        labels = (ents.get(q) or {}).get("labels", {})
        nm = labels.get("en", {}).get("value") or labels.get("ko", {}).get("value")
        if nm:
            out.append(nm)
    return out


def parse_label(raw: dict) -> dict:
    """Pure: the ko/en label of a resolved Wikidata entity (e.g. an agency/label item)."""
    item = next(iter(raw.get("entities", {}).values()), {})
    labels = item.get("labels", {})
    return {"ko": labels.get("ko", {}).get("value"), "en": labels.get("en", {}).get("value")}


def parse_search(raw: dict) -> str | None:
    """Pure: pick the top hit's Q-id from a `wbsearchentities` response (None if no hit)."""
    hits = raw.get("search", [])
    if not hits:
        return None
    return hits[0].get("id")


def _norm(s: str | None) -> str:
    """Normalize a name for identity comparison: drop case and spaces (NewJeans == New Jeans)."""
    return (s or "").casefold().replace(" ", "")


def _verify_identity(payload: dict, expected: dict) -> None:
    """Reject a fetched record whose label contradicts the entity's known identity.

    Invariant 2 (PRINCIPLES.md): no unverifiable data ships. Two checks:

    1. OVERLAP — the fetched ko/en must match at least one expected name (else the search/Q-id
       resolved to a different entity entirely; e.g. BTS coming back as something else). This is
       all we can assert for distinctive names (expected = {en} only).

    2. STRICT KO — when we KNOW the Korean name (collision-prone anchors carry both ko+en) and the
       fetched record carries a Korean label that is neither the expected ko NOR the expected en,
       the search drifted to a SAME-EN-LABEL impostor (TREASURE the group -> 보물 the concept;
       Parasite the film -> 기생충 the organism). Reject by the Korean name. (A romanized/latin ko
       label that equals the English name is allowed — some acts label ko in latin, e.g. "NCT".)
       NB: this catches an impostor that carries its OWN contradicting ko label; an impostor with
       NO ko label (ko folds to en) can still pass here — its backstop is cross-verification +
       the uncorroborated Skill-Score cap, which keep such a record honest (never high-confidence).

    Either failure raises so the pipeline drops it (graceful degradation) instead of poisoning the
    append-only store. Both fail SAFE: the outcome is a miss, never a wrong record.
    """
    got_ko, got_en = _norm(payload.get("name_ko")), _norm(payload.get("name_en_official"))
    want_ko, want_en = _norm(expected.get("ko")), _norm(expected.get("en"))
    want = {want_ko, want_en}
    want.discard("")
    got = {got_ko, got_en}
    got.discard("")
    if want and got.isdisjoint(want):
        raise ValueError(
            f"identity mismatch: fetched {sorted(got)} matches none of expected {sorted(want)}"
        )
    if want_ko and got_ko and got_ko != want_ko and got_ko != want_en:
        raise ValueError(
            f"ko identity mismatch: fetched ko {payload.get('name_ko')!r} "
            f"contradicts expected {expected.get('ko')!r} (same-EN-label impostor)"
        )


class WikidataSource:
    name = "Wikidata"
    is_fallback = False

    def __init__(self, aliases: dict[str, str] | None = None) -> None:
        # entity_id -> Q-id discovered via live search (memoized to spare the API).
        self._discovered: dict[str, str] = {}
        # entity_id -> search name for ids outside the curated roster (e.g. swept labelmates),
        # so discovered artists resolve + identity-guard against their known name too.
        self._aliases: dict[str, str] = aliases or {}

    def _entity_url(self, qid: str) -> str:
        return (
            f"{WIKIDATA_API}?action=wbgetentities&ids={qid}"
            "&props=labels|aliases|claims&languages=ko|en&format=json"  # claims -> P264 agency
        )

    def _label_url(self, qid: str) -> str:
        # Lean: just the ko/en label of the agency/label entity (no claims).
        return (
            f"{WIKIDATA_API}?action=wbgetentities&ids={qid}"
            "&props=labels&languages=ko|en&format=json"
        )

    def _labels_url(self, qids: list[str]) -> str:
        # Batch: ko/en labels for many ids in ONE call (members), | encoded by urlencode.
        query = urllib.parse.urlencode(
            {
                "action": "wbgetentities",
                "ids": "|".join(qids),
                "props": "labels",
                "languages": "ko|en",
                "format": "json",
            }
        )
        return f"{WIKIDATA_API}?{query}"

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
        return _http_get_json(url, _UA)

    async def resolve_qid(self, entity_id: str) -> str:
        """entity_id -> Q-id. Curated map first (precision), then memoized live search."""
        if entity_id in _QID:
            return _QID[entity_id]
        if entity_id in self._discovered:
            return self._discovered[entity_id]
        term = NAMES.get(entity_id) or self._aliases.get(entity_id) or entity_id.split(":", 1)[-1].strip()
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
        expected = (
            _CURATED.get(entity_id)
            or ({"en": NAMES[entity_id]} if entity_id in NAMES else None)
            or ({"en": self._aliases[entity_id]} if entity_id in self._aliases else None)
        )
        if expected:
            _verify_identity(payload, expected)  # reject contradictory data (invariant 2)

        # Resolve the 소속사/label anchor. P264 can list several labels (e.g. a foreign distribution
        # label alongside the primary 소속사); for a curated artist a hint picks the RIGHT one among
        # the live values (the value still comes from Wikidata - the hint only disambiguates).
        agency_qids = payload.pop("agency_qids", [])
        hint = ((_CURATED.get(entity_id) or {}).get("agency") or AGENCY_HINTS.get(entity_id) or "").lower()
        for q in agency_qids:
            try:
                label = parse_label(await asyncio.to_thread(self._http_get, self._label_url(q)))
            except Exception:
                continue  # agency is supplementary; never fail the artist fetch for it
            en, ko = label.get("en"), label.get("ko")
            if not (en or ko):
                continue
            matches = bool(hint) and (hint in (en or "").lower() or hint in (ko or "").lower())
            if "agency_en" not in payload or matches:  # first valid = default; a hint match wins
                payload["agency_en"], payload["agency_ko"] = en, ko
                payload["agency_source"] = f"Wikidata {q}"
            if not hint or matches:
                break  # no hint -> take the first valid label; with a hint -> stop at the match

        # Resolve members (P527 Q-ids) -> names in ONE batched call (best-effort; never fail for it).
        member_qids = payload.pop("member_qids", [])
        if member_qids:
            try:
                raw_m = await asyncio.to_thread(self._http_get, self._labels_url(member_qids[:25]))
                members = parse_member_names(raw_m, member_qids[:25])
                if members:
                    payload["members"] = members
            except Exception:
                pass

        # Resolve drama/film director(s) (P57) -> names (best-effort; reuses the member machinery).
        director_qids = payload.pop("director_qids", [])
        if director_qids:
            try:
                raw_dir = await asyncio.to_thread(self._http_get, self._labels_url(director_qids[:5]))
                directors = parse_member_names(raw_dir, director_qids[:5])
                if directors:
                    payload["directors"] = directors
            except Exception:
                pass

        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        return {"payload": payload, "citation": f"Wikidata {qid} {ts}"}


# --- Agency-hub sweep: discover an agency's other artists (labelmates) via SPARQL -------------
# 소속사 is a hub - given a label's Q-id, list the artists under it so the roster grows from the
# agency (the user's "정보가 계속 나온다"). Discovered names are then run through the normal
# Wikidata+Wikipedia cross-verification, so only verified labelmates are ingested (the moat holds).


def build_labelmates_query(label_qid: str, *, limit: int = 12) -> str:
    """Pure: SPARQL for artists (group/duo/human) directly on the record label (P264) = label_qid.

    NB: a 'family' variant (follow P749 to sibling labels) was tried and reverted - it over-broadened
    to obscure individual members (e.g. Japanese sub-unit members) and *lowered* result quality. Direct
    P264 yields the actual labelmates. (Determinism is deferred: ORDER BY ?item sorts by Q-id, not fame.)
    """
    return (
        "SELECT ?item ?en ?ko WHERE { "
        f"?item wdt:P264 wd:{label_qid} . "
        "{ ?item wdt:P31 wd:Q215380 } UNION { ?item wdt:P31 wd:Q5 } "
        "UNION { ?item wdt:P31 wd:Q4439542 } UNION { ?item wdt:P31 wd:Q864897 } "
        '?item rdfs:label ?en . FILTER(LANG(?en) = "en") '
        'OPTIONAL { ?item rdfs:label ?ko . FILTER(LANG(?ko) = "ko") } '
        f"}} LIMIT {limit}"
    )


def _slug(name: str) -> str:
    """A stable entity-id slug from an English name: 'Red Velvet' -> 'redvelvet'."""
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def parse_labelmates(raw: dict) -> list[dict]:
    """Pure: SPARQL bindings -> [{qid, en, ko, slug}], de-duped by slug (drops blanks)."""
    out: list[dict] = []
    seen: set[str] = set()
    for b in raw.get("results", {}).get("bindings", []):
        uri = (b.get("item") or {}).get("value", "")
        qid = uri.rsplit("/", 1)[-1] if uri else ""
        en = (b.get("en") or {}).get("value")
        if not qid or not en:
            continue
        slug = _slug(en)
        if not slug or slug in seen:
            continue
        seen.add(slug)
        out.append({"qid": qid, "en": en, "ko": (b.get("ko") or {}).get("value"), "slug": slug})
    return out


def fetch_labelmates(label_qid: str, *, limit: int = 12) -> list[dict]:
    """Live: query.wikidata.org SPARQL -> labelmate artists. Sync (call via asyncio.to_thread);
    needs open network (GitHub runner). Raises on transport error (caller degrades gracefully)."""
    url = f"{WIKIDATA_SPARQL}?" + urllib.parse.urlencode(
        {"query": build_labelmates_query(label_qid, limit=limit), "format": "json"}
    )
    req = urllib.request.Request(url, headers={**_UA, "Accept": "application/sparql-results+json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return parse_labelmates(json.load(r))
