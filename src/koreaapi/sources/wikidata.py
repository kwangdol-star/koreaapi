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
    # Batch 3 collision-prone (real word / real name shares the English):
    "artist:boa": {"ko": "보아", "en": "BoA", "agency": "SM Entertainment"},
    "film:smugglers": {"ko": "밀수", "en": "Smugglers"},
    # webtoon whose English title is the common word "lookism" (the concept) — pin bilingually.
    "webtoon:lookism": {"ko": "외모지상주의", "en": "Lookism", "agency": "Naver"},
    # Korean blood sausage "sundae" collides with the English "sundae" (ice cream) — pin bilingually.
    "food:sundae": {"ko": "순대", "en": "Sundae"},
    # K-beauty brands whose English name is a common word/phrase — pin bilingually.
    "brand:innisfree": {"ko": "이니스프리", "en": "Innisfree"},
    "brand:naturerepublic": {"ko": "네이처리퍼블릭", "en": "Nature Republic"},
    "brand:thefaceshop": {"ko": "더페이스샵", "en": "The Face Shop"},
    # Korean novels whose English title is a common word/phrase — pin bilingually.
    "book:thevegetarian": {"ko": "채식주의자", "en": "The Vegetarian"},
    "book:humanacts": {"ko": "소년이 온다", "en": "Human Acts"},
    "book:almond": {"ko": "아몬드", "en": "Almond"},
    "book:pleaselookaftermom": {"ko": "엄마를 부탁해", "en": "Please Look After Mom"},
    # The flagship region — pin the country by VERIFIED Q-id (대한민국 = Q884) so the region vertical is
    # anchored; cities/provinces + hospitals are distinctive enough for live search + the identity guard.
    "region:southkorea": {"qid": "Q884", "ko": "대한민국", "en": "South Korea"},
    # Korean games whose English title is a common word (vs the Welsh myth "Mabinogi" / "lineage" the
    # concept / "aion") — pin bilingually so the strict KO guard rejects a same-EN-label impostor.
    "game:lineage": {"ko": "리니지", "en": "Lineage"},
    "game:aion": {"ko": "아이온", "en": "Aion"},
    # variety show whose English title is a common phrase ("Running Man" the concept/film) — pin.
    "show:runningman": {"ko": "런닝맨", "en": "Running Man"},
    # animation whose English title is a common word ("Larva" the insect) — pin bilingually.
    "animation:larva": {"ko": "라바", "en": "Larva"},
    # thin-vertical seeds whose English title is a common phrase — pin bilingually (strict KO guard).
    "webtoon:truebeauty": {"ko": "여신강림", "en": "True Beauty"},
    "webtoon:sweethome": {"ko": "스위트홈", "en": "Sweet Home"},
    "webtoon:windbreaker": {"ko": "윈드브레이커", "en": "Wind Breaker"},
    "book:pachinko": {"ko": "파친코", "en": "Pachinko"},
    "book:greeklessons": {"ko": "희랍어 시간", "en": "Greek Lessons"},
    "book:whitebook": {"ko": "흰", "en": "The White Book"},
    "book:loveinthebigcity": {"ko": "대도시의 사랑법", "en": "Love in the Big City"},
    "animation:seoulstation": {"ko": "서울역", "en": "Seoul Station"},
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


def _claim_string(item: dict, prop: str) -> str | None:
    """Pure: a string-valued claim (e.g. P297 ISO 3166-1 alpha-2, P474 country calling code)."""
    for claim in item.get("claims", {}).get(prop, []):
        ms = claim.get("mainsnak", {})
        if ms.get("snaktype") != "value":
            continue
        val = (ms.get("datavalue") or {}).get("value")
        if isinstance(val, str) and val.strip():
            return val.strip()
    return None


def _claim_qty(item: dict, prop: str) -> str | None:
    """Pure: a quantity claim's amount as a clean number string (e.g. P1113 episodes, P2047 runtime)
    — sign + trailing '.0' stripped; the unit is dropped (the display label carries it)."""
    for claim in item.get("claims", {}).get(prop, []):
        ms = claim.get("mainsnak", {})
        if ms.get("snaktype") != "value":
            continue
        amt = ((ms.get("datavalue") or {}).get("value") or {}).get("amount")
        if not amt:
            continue
        a = amt.lstrip("+")
        try:
            f = float(a)
            return str(int(f)) if f.is_integer() else str(f)
        except ValueError:
            return a
    return None


def _claim_coord(item: dict, prop: str) -> tuple[float, float] | None:
    """Pure: a globe-coordinate claim (P625) -> (lat, lon), rounded. Enables a map link + Schema.org
    GeoCoordinates for physical places. None when absent/malformed (supplementary)."""
    for claim in item.get("claims", {}).get(prop, []):
        ms = claim.get("mainsnak", {})
        if ms.get("snaktype") != "value":
            continue
        v = (ms.get("datavalue") or {}).get("value") or {}
        lat, lon = v.get("latitude"), v.get("longitude")
        if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
            return (round(float(lat), 5), round(float(lon), 5))
    return None


# Per-namespace Wikidata property map — the SAME engine, switched by entity namespace. `agency` is
# the org edge (소속사 / network / publisher), `date` the debut/air/publication date (`date2` a
# fallback), `members` the people edge (group members / cast / authors), `directors` drama·film only,
# `disband` the end date (artists only). Adding a vertical = one row here + a roster/_TITLES entry.
_NS_PROPS = {
    "artist":  {"agency": "P264", "date": "P571", "members": "P527", "directors": None, "disband": "P576"},
    "drama":   {"agency": "P449", "date": "P577", "members": "P161", "directors": "P57"},
    "film":    {"agency": "P449", "date": "P577", "members": "P161", "directors": "P57"},
    # webtoon/manhwa: publisher/platform P123 (Naver·Kakao), publication date P577 (else inception
    # P571), author(s) P50 as the people edge (the "creator"), no director.
    "webtoon": {"agency": "P123", "date": "P577", "date2": "P571", "members": "P50", "directors": None},
    # place/attraction: located-in P131 (the region) as the org edge, inception/opening P571 (else
    # P729 service-entry handled as date2), no people edge.
    "place": {"agency": "P131", "date": "P571", "date2": "P729", "members": None, "directors": None},
    # food/dish: cross-verified by NAME only (a dish has no stable agency/date/people edge) — the
    # verified bilingual name + Wikidata sameAs IS the citable asset.
    "food": {"agency": None, "date": None, "members": None, "directors": None},
    # company: industry (P452) as the category edge, inception/founded (P571), no people edge.
    "company": {"agency": "P452", "date": "P571", "members": None, "directors": None},
    # brand (K-beauty / consumer): owned-by P127 (the parent) as the org edge, inception P571.
    "brand": {"agency": "P127", "date": "P571", "members": None, "directors": None},
    # book / literature: publisher P123, publication date P577 (else P571), author(s) P50.
    "book": {"agency": "P123", "date": "P577", "date2": "P571", "members": "P50", "directors": None},
    # history (dynasty/period/event): start time P580 (else inception P571), no org/people edge.
    "history": {"agency": None, "date": "P580", "date2": "P571", "members": None, "directors": None},
    # heritage (cultural property / traditional art / gugak): inception P571 (optional), name-anchored.
    "heritage": {"agency": None, "date": "P571", "members": None, "directors": None},
    # folklore (legend / myth / shamanism / ghost): cross-verified by NAME only.
    "folklore": {"agency": None, "date": None, "members": None, "directors": None},
    # medical: hospital / institution — located-in P131 (region) + inception P571.
    "medical": {"agency": "P131", "date": "P571", "members": None, "directors": None},
    # region: country / administrative division — name-anchored (capital/population not modelled here).
    "region": {"agency": None, "date": None, "members": None, "directors": None},
    # game (Korean-developed video game): developer P178 as the studio edge, publication date P577.
    "game": {"agency": "P178", "date": "P577", "members": None, "directors": None},
    # show (방송 / 예능 — variety & entertainment TV): original network P449, start date P580 (else
    # air date P577), cast/host P161 as the people edge (feeds the person graph: an MC across shows).
    "show": {"agency": "P449", "date": "P580", "date2": "P577", "members": "P161", "directors": None},
    # animation (애니메이션): production company P272 as the studio edge, publication date P577 (else
    # inception P571), no people edge.
    "animation": {"agency": "P272", "date": "P577", "date2": "P571", "members": None, "directors": None},
    # university (교육): located-in P131 (region) as the place edge + inception P571 (founded).
    "university": {"agency": "P131", "date": "P571", "members": None, "directors": None},
    # classic (고전 · 사료 — historical text / record / treatise): author P50 as the people edge,
    # publication/compilation date P577 (else inception P571). No modern publisher edge.
    "classic": {"agency": None, "date": "P577", "date2": "P571", "members": "P50", "directors": None},
}

# Per-vertical EXTRA structured attributes — depth BEYOND name/date/agency/people, so a verified page
# actually says something (genre, language, runtime, ingredients, heritage designation, platform …).
# Each = (display, property, kind); kind: "label" (entity Q-ids -> resolved names), "str", "time",
# "qty" (numeric amount). STABLE facts only (volatile stats stay off-model). Best-effort + supplementary
# (a missing one never fails the record, never enters cross-verification, never moves the Skill Score).
_EXTRAS = {
    "artist":    [("Genre", "P136", "label")],
    "drama":     [("Genre", "P136", "label"), ("Episodes", "P1113", "qty"),
                  ("Original language", "P364", "label")],
    "film":      [("Genre", "P136", "label"), ("Runtime (min)", "P2047", "qty"),
                  ("Original language", "P364", "label")],
    "webtoon":   [("Genre", "P136", "label")],
    "place":     [("Heritage status", "P1435", "label")],
    "food":      [("Country of origin", "P495", "label"), ("Made from", "P186", "label")],
    "company":   [("Headquarters", "P159", "label")],
    "brand":     [("Country of origin", "P495", "label")],
    "book":      [("Genre", "P136", "label"), ("Original language", "P407", "label")],
    "history":   [("End", "P582", "time")],
    "heritage":  [("Heritage designation", "P1435", "label")],
    "game":      [("Genre", "P136", "label"), ("Platform", "P400", "label")],
    "show":      [("Genre", "P136", "label")],
    "animation": [("Genre", "P136", "label")],
    "classic":   [("Heritage designation", "P1435", "label")],  # National Treasure / UNESCO Memory of the World
}


def parse_entity(raw: dict, entity_id: str, kind: str) -> dict:
    """Pure: turn a Wikidata `wbgetentities` response into our payload shape (agency/publisher,
    debut/air/publication date, active status, people Q-ids), namespace-switched via _NS_PROPS."""
    ents = raw.get("entities", {})
    if not ents:
        raise ValueError("no entity in Wikidata response")
    item = next(iter(ents.values()))
    labels = item.get("labels", {})
    ko = labels.get("ko", {}).get("value")
    en = labels.get("en", {}).get("value")
    if not ko and not en:
        raise ValueError("no ko/en label in Wikidata response")
    ns = entity_id.split(":", 1)[0]
    p = _NS_PROPS.get(ns, _NS_PROPS["artist"])
    debut = _claim_time(item, p["date"]) or (_claim_time(item, p["date2"]) if p.get("date2") else None)
    payload = {
        "name_ko": ko or en,
        "name_en_official": en,
        "name_romanized": None,  # Wikidata rarely carries clean romanization; filled elsewhere
        "name_en_source": "official" if en else "llm",
        "name_en_confidence": "high" if en else "low",
        "agency_qids": _claim_qids(item, p["agency"]) if p["agency"] else [],
        "debut": debut,
        "active": "disbanded" if (p.get("disband") and _claim_time(item, p["disband"])) else "active",
        "member_qids": _claim_qids(item, p["members"]) if p["members"] else [],
        "director_qids": _claim_qids(item, p["directors"]) if p["directors"] else [],
        "summary_en": f"{en or ko} - {kind} (Wikidata labels).",
        "summary_ko": f"{ko or en} - {kind} (위키데이터 라벨).",
    }
    if ns == "region":
        # Country/admin infobox: STABLE facts only (capital/language/currency entity Q-ids -> resolved
        # to labels in fetch(); ISO code + calling code are direct strings). Volatile stats (population,
        # GDP, head of state) are deliberately EXCLUDED — those are an off-model curated digest, not the
        # cross-verify entity model.
        payload["capital_qids"] = _claim_qids(item, "P36")
        payload["lang_qids"] = _claim_qids(item, "P37")
        payload["currency_qids"] = _claim_qids(item, "P38")
        payload["iso_code"] = _claim_string(item, "P297")      # ISO 3166-1 alpha-2
        payload["calling_code"] = _claim_string(item, "P474")  # country calling code
    # Per-vertical extra attrs: resolve "str"/"time"/"qty" now; defer "label" (entity Q-ids) to fetch()
    # where they're batch-resolved to names. attrs = the resolved {display: value} we render + cite.
    extra_attrs: dict = {}
    extra_label_qids: dict = {}
    for display, prop, ekind in _EXTRAS.get(ns, []):
        if ekind == "label":
            qs = _claim_qids(item, prop)[:3]
            if qs:
                extra_label_qids[display] = qs
        else:
            v = (_claim_string(item, prop) if ekind == "str"
                 else _claim_time(item, prop) if ekind == "time"
                 else _claim_qty(item, prop) if ekind == "qty" else None)
            if v:
                extra_attrs[display] = v
    if extra_attrs:
        payload["attrs"] = extra_attrs
    if extra_label_qids:
        payload["extra_label_qids"] = extra_label_qids
    if ns in ("place", "medical", "university"):  # physical locations -> coordinates (map + geo JSON-LD)
        coord = _claim_coord(item, "P625")
        if coord:
            payload["geo"] = {"lat": coord[0], "lon": coord[1]}
    return payload


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

    def __init__(self, aliases: dict[str, str] | None = None,
                 qids: dict[str, str] | None = None) -> None:
        # entity_id -> Q-id discovered via live search (memoized to spare the API).
        self._discovered: dict[str, str] = {}
        # entity_id -> search name for ids outside the curated roster (e.g. swept labelmates),
        # so discovered artists resolve + identity-guard against their known name too.
        self._aliases: dict[str, str] = aliases or {}
        # entity_id -> Q-id known up front (e.g. SPARQL-discovered): fetch that exact item, skipping
        # the search step entirely — avoids same-name search drift and saves a call. Identity is still
        # guarded against the alias name, so a wrong qid would be caught and dropped.
        self._qids: dict[str, str] = qids or {}

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
        """entity_id -> Q-id. Curated pin, then a caller-supplied (SPARQL-discovered) qid, then
        memoized live search."""
        if entity_id in _QID:
            return _QID[entity_id]
        if entity_id in self._qids:  # discovered up front -> fetch that exact item (no search)
            return self._qids[entity_id]
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

        # Region infobox: resolve capital / official language / currency Q-ids -> labels (the first,
        # preferred-ranked value each). Best-effort + supplementary (a region without these is still a
        # valid record). The .pop is a no-op for every other namespace (the keys exist only for region).
        for key, qkey in (("capital", "capital_qids"), ("language", "lang_qids"),
                          ("currency", "currency_qids")):
            for q in payload.pop(qkey, []):
                try:
                    label = parse_label(await asyncio.to_thread(self._http_get, self._label_url(q)))
                except Exception:
                    break  # the fact is supplementary; never fail the region fetch for it
                en_l, ko_l = label.get("en"), label.get("ko")
                if en_l or ko_l:
                    payload[f"{key}_en"], payload[f"{key}_ko"] = en_l, ko_l
                break  # take the first (preferred) value only

        # Per-vertical extra attrs (genre / language / platform / …): resolve the label-typed Q-ids ->
        # names in ONE batched call, merged into payload["attrs"]. Best-effort + supplementary.
        extra_label_qids = payload.pop("extra_label_qids", {})
        if extra_label_qids:
            all_q = [q for qs in extra_label_qids.values() for q in qs][:40]
            try:
                raw_l = await asyncio.to_thread(self._http_get, self._labels_url(all_q))
            except Exception:
                raw_l = {}
            attrs = payload.get("attrs") or {}
            for display, qs in extra_label_qids.items():
                names = parse_member_names(raw_l, qs)  # reuses the one batched response
                if names:
                    attrs[display] = ", ".join(names)
            if attrs:
                payload["attrs"] = attrs

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


# --- Universe discovery: bulk-find a vertical's Korean entities from Wikidata (the path to 10x) ----
# Per vertical: the instance-of class(es) + a country/cuisine filter. Discovered candidates are run
# through the SAME cross-verification pipeline (only verified ones are kept), so breadth grows without
# lowering the bar — and the discovered Q-id is fetched directly (no same-name search drift).
_DISCOVER = {
    "artist":  (["Q215380", "Q864897", "Q4439542"], "P495", "Q884"),   # group/boy band/girl group, origin SK
    "drama":   (["Q5398426"], "P495", "Q884"),                          # television series, origin SK
    "film":    (["Q11424"], "P495", "Q884"),                            # film, origin SK
    "webtoon": (["Q1062335"], "P495", "Q884"),                          # webtoon, origin SK
    "place":   (["Q570116"], "P17", "Q884"),                            # tourist attraction, country SK
    "food":    (["Q746549"], "P2012", "Q234138"),                       # dish, cuisine = Korean cuisine
    "company": (["Q4830453", "Q891723"], "P17", "Q884"),               # business/public company, country SK
    "brand":   (["Q431289"], "P17", "Q884"),                            # brand, country SK
    "book":    (["Q7725634", "Q47461344"], "P407", "Q9176"),           # literary/written work, language Korean
    "medical": (["Q16917"], "P17", "Q884"),                            # hospital, country SK
    "game":    (["Q7889"], "P495", "Q884"),                            # video game, origin SK
    "animation": (["Q581714", "Q202866"], "P495", "Q884"),             # animated series/film, origin SK
    "university": (["Q3918"], "P17", "Q884"),                          # university, country SK
    # (history/heritage/folklore/region/show are seed-only: too heterogeneous / class-overlapping to
    #  discover cleanly — e.g. a variety "television program" class overlaps the drama vertical)
}


def build_discover_query(vertical: str, *, limit: int = 400, offset: int = 0) -> str:
    """Pure: SPARQL listing a vertical's Korean entities (instance-of class(es) + country/cuisine
    filter), with ko/en labels. ORDER BY ?item for stable pagination; the caller dedups vs the store."""
    classes, prop, val = _DISCOVER[vertical]
    union = " UNION ".join(f"{{ ?item wdt:P31 wd:{c} }}" for c in classes)
    return (
        "SELECT ?item ?en ?ko WHERE { "
        f"{union} . ?item wdt:{prop} wd:{val} . "
        '?item rdfs:label ?en . FILTER(LANG(?en) = "en") '
        'OPTIONAL { ?item rdfs:label ?ko . FILTER(LANG(?ko) = "ko") } '
        f"}} ORDER BY ?item LIMIT {limit} OFFSET {offset}"
    )


def fetch_discover(vertical: str, *, limit: int = 400, offset: int = 0) -> list[dict]:
    """Live: SPARQL -> [{qid, en, ko, slug}] for a vertical's Korean entities. Sync (asyncio.to_thread);
    needs open network. Raises on transport error (caller degrades gracefully)."""
    url = f"{WIKIDATA_SPARQL}?" + urllib.parse.urlencode(
        {"query": build_discover_query(vertical, limit=limit, offset=offset), "format": "json"}
    )
    req = urllib.request.Request(url, headers={**_UA, "Accept": "application/sparql-results+json"})
    with urllib.request.urlopen(req, timeout=45) as r:
        return parse_labelmates(json.load(r))
