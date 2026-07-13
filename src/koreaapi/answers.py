"""Answer Products — KoreaAPI's decision catalog (engine 3).

The data layer (engine 1) and the demand signal (engine 2) answer "what is true / what
is rising". Engine 3 turns that verified store into NAMED, INDIVIDUALLY CITABLE DECISIONS an
AI agent makes *before* it answers a user: confirm a Korean spelling, decide whether a claim
is safe to cite, resolve a fuzzy mention to a trusted ID, read the demand trend, pull a roster.

Each product is a thin pure layer over service.py and returns the SAME envelope:

    {product, name, emoji, sector, query, signal, action, score(0..1), rationale,
     answer, evidence:{sources, as_of, citation}}

So an agent (or a contract, or an answer engine) can branch on `signal`, gate on `score`,
cite from `evidence`, and surface `answer` — uniformly across every product. This mirrors the
sibling KWeather oracle's decision-products pattern (signal/action/score/rationale/metrics),
adapted from numeric weather to verifiable culture: `metrics` -> `answer` + `evidence`.

Offline-testable: the products need no keys, no network, no chain. The optional natural-language
router (ask / route) adds a best-effort LLM to PICK a product from free text, with a keyless keyword
fallback — routing only chooses; the verified product still decides. Discoverable at /v1/answer and
via the MCP tools list_answer_products + get_answer + ask.
"""

from __future__ import annotations

import json
import os
import re

from . import service
from .pipeline import store
from .roster import FOOD_SPICE, FOOD_VEG, GEO_NAMESPACES


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


# The GEO verticals a region trip-plan draws on — canonical list lives in roster.GEO_NAMESPACES.
_GEO_NS = GEO_NAMESPACES


def _evidence(d: dict) -> dict:
    """Lift provenance from a service result into the common evidence block."""
    ev: dict = {}
    if d.get("sources") is not None:
        ev["sources"] = d["sources"]
    if d.get("as_of"):
        ev["as_of"] = d["as_of"]
    if d.get("citation"):
        ev["citation"] = d["citation"]
    return ev


def _env(pid: str, query: str, *, signal: str, action: str, score: float,
         rationale: str, answer: dict, evidence: dict | None = None) -> dict:
    p = _BY_ID[pid]
    return {
        "product": p["id"], "name": p["name"], "emoji": p["emoji"], "sector": p["sector"],
        "query": query, "signal": signal, "action": action,
        "score": round(_clamp01(score), 2), "rationale": rationale,
        "answer": answer, "evidence": evidence or {},
    }


# ---- products (each: async run(query, db_path) -> envelope) ----

async def _run_canonical_name(query: str, db_path: str | None = None) -> dict:
    """Confirm the authoritative Korean ↔ English spelling. The 빈센조(not 빈첸초) decision, productized."""
    r = await service.resolve(query, db_path=db_path)
    if not r.get("found"):
        return _env("canonical-name", query, signal="NOT_FOUND",
                    action="No verified entity — do not assert a Korean spelling.", score=0.0,
                    rationale=f"'{query}' matches no verified KoreaAPI entity yet.", answer={})
    name = r["name"]
    n = r.get("agreeing_sources", 0)
    skill = r.get("skill_score", 0.0)
    ko, en = name.get("ko"), name.get("en_official")
    disp_ko, disp_en = ko or "—", en or "—"
    score = skill
    if r.get("matched_by") == "fuzzy":
        signal = "AMBIGUOUS"
        action = f"Fuzzy match only — confirm the entity before using 「{disp_ko}」."
        if r.get("candidates"):
            score = skill * (r["candidates"][0].get("match", 100) / 100.0)
    elif n >= 2:
        signal = "CONFIRMED"
        action = f"Use 「{disp_ko}」 / \"{disp_en}\" — {n} independent sources agree."
    else:
        signal = "UNVERIFIED"
        action = f"Single-source — verify 「{disp_ko}」 before asserting the spelling."
    answer = {"ko": ko, "en_official": en, "romanized": name.get("romanized"),
              "id": r.get("id"), "matched_by": r.get("matched_by")}
    if r.get("candidates"):
        answer["candidates"] = r["candidates"]
    return _env("canonical-name", query, signal=signal, action=action, score=score,
                rationale=f"{disp_en} ↔ {disp_ko}; {n} source(s) agreed on the bilingual name.",
                answer=answer, evidence=_evidence(r))


async def _run_fact_check(query: str, db_path: str | None = None) -> dict:
    """Decide whether a claim about an entity is safe to cite (cross-/triple-verified / certified)."""
    r = await service.resolve(query, db_path=db_path)
    if not r.get("found"):
        return _env("fact-check", query, signal="NOT_FOUND",
                    action="No verified record — do not present as fact.", score=0.0,
                    rationale=f"'{query}' has no verified KoreaAPI record.", answer={})
    v = await service.verified(r["id"], db_path=db_path)
    if not v.get("found"):
        return _env("fact-check", query, signal="NOT_FOUND",
                    action="No verified record — do not present as fact.", score=0.0,
                    rationale=f"'{query}' has no verified KoreaAPI record.", answer={})
    n = v.get("agreeing_sources", 0)
    skill = v.get("skill_score", 0.0)
    if v.get("officially_certified"):
        signal, action = "CERTIFIED", f"Citable — officially certified by {v.get('certified_by')}."
    elif n >= 3:
        signal, action = "TRIPLE_VERIFIED", "Safe to cite — ≥3 independent sources agree."
    elif n >= 2:
        signal, action = "CROSS_VERIFIED", "Citable with attribution — ≥2 independent sources agree."
    else:
        signal, action = "UNVERIFIED", "Do not cite as fact — single / uncorroborated source (Skill Score capped 0.7)."
    answer = {k: v.get(k) for k in ("name", "skill_score", "confidence", "agreeing_sources",
                                    "cross_verified", "triple_verified", "officially_certified", "certified_by")}
    answer["id"] = v["entity_id"]
    return _env("fact-check", query, signal=signal, action=action, score=skill,
                rationale=v.get("note", ""), answer=answer, evidence=_evidence(v))


async def _run_identity_resolve(query: str, db_path: str | None = None) -> dict:
    """Map a fuzzy mention or external ID onto the canonical verified entity (the ID spine)."""
    r = await service.resolve(query, db_path=db_path)
    if not r.get("found"):
        return _env("identity-resolve", query, signal="NOT_FOUND",
                    action="No trusted entity — do not fabricate an ID.", score=0.0,
                    rationale=f"'{query}' resolves to no verified entity.", answer={})
    exact = r.get("matched_by") in ("entity_id", "wikidata", "name")
    skill = r.get("skill_score", 0.0)
    if exact:
        signal, action, score = "RESOLVED", f"Map your mention to {r['id']}.", skill
    else:
        signal = "AMBIGUOUS"
        action = f"Best guess {r['id']} — confirm among candidates."
        score = skill * (r["candidates"][0].get("match", 100) / 100.0) if r.get("candidates") else skill
    answer = {"id": r["id"], "kind": r.get("kind"), "name": r.get("name"),
              "ids": r.get("ids", {}), "matched_by": r.get("matched_by"),
              "content_hash": r.get("content_hash")}
    if r.get("candidates"):
        answer["candidates"] = r["candidates"]
    return _env("identity-resolve", query, signal=signal, action=action, score=score,
                rationale=f"matched by {r.get('matched_by')}.", answer=answer, evidence=_evidence(r))


async def _run_trend_radar(query: str, db_path: str | None = None) -> dict:
    """Read what is rising in Korea now from accumulated demand signal. `query` = category or 'all'."""
    cat = (query or "all").strip() or "all"
    res = await service.korea_rising(cat, 5, db_path=db_path)
    items = res.get("items", [])
    top = items[0] if items else None
    top_demand = top.get("demand_signal", 0) if top else 0
    if top and top_demand > 0:
        nm = top["name"].get("en_official") or top["name"].get("ko")
        signal, action = "HOT", f"Surface {nm} — highest observed demand in '{cat}'."
    elif items:
        signal, action = "QUIET", f"Verified items in '{cat}' but no demand signal yet (cold-start)."
    else:
        signal, action = "QUIET", f"No verified items / demand in '{cat}' yet."
    answer = {"category": cat, "top": [
        {"name": it["name"], "demand_signal": it.get("demand_signal", 0),
         "skill_score": it["provenance"]["skill_score"]}
        for it in items]}
    return _env("trend-radar", cat, signal=signal, action=action,
                score=_clamp01(top_demand / 10.0),
                rationale=f"top demand {top_demand} in '{cat}'.",
                answer=answer, evidence={"as_of": top["snapshot_at"]} if top else {})


async def _run_agency_roster(query: str, db_path: str | None = None) -> dict:
    """List the verified artists under a Korean agency/label (소속사)."""
    res = await service.agency(query, db_path=db_path)
    members = res.get("members", [])
    count = res.get("count", 0)
    if count:
        signal, action = "FOUND", f"{count} verified artist(s) under '{query}'."
    else:
        signal, action = "EMPTY", f"No verified artists under '{query}' yet."
    answer = {"agency": query, "count": count,
              "members": [{"name": m["name"], "kind": m["kind"]} for m in members]}
    return _env("agency-roster", query, signal=signal, action=action,
                score=_clamp01(count / 12.0), rationale=f"{count} member(s) matched.", answer=answer)


async def _run_person_credits(query: str, db_path: str | None = None) -> dict:
    """Aggregate a Korean-culture person's verified credits across works."""
    res = await service.person(query, db_path=db_path)
    if not res.get("found"):
        return _env("person-credits", query, signal="NOT_FOUND",
                    action="No verified credit for this person yet.", score=0.0,
                    rationale=res.get("note", ""), answer={})
    count = res.get("count", 0)
    return _env("person-credits", query, signal="FOUND",
                action=f"{res.get('name')}: {count} verified credit(s).",
                score=_clamp01(count / 8.0),
                rationale=f"{count} credit(s) across verified works.",
                answer={"name": res.get("name"), "count": count, "credits": res.get("credits", [])},
                evidence={"citation": res.get("citation")} if res.get("citation") else {})


async def _run_related_network(query: str, db_path: str | None = None) -> dict:
    """Find entities sharing the same agency/network hub edge."""
    r = await service.resolve(query, db_path=db_path)
    if not r.get("found"):
        return _env("related-network", query, signal="NOT_FOUND",
                    action="No verified entity to expand.", score=0.0,
                    rationale=f"'{query}' resolves to no entity.", answer={})
    rel = await service.related(r["id"], db_path=db_path)
    items = rel.get("related", [])
    count = rel.get("count", 0)
    if count:
        signal = "FOUND"
        action = f"{count} entit(ies) share the same {rel.get('related_by')} ({rel.get('key')})."
    else:
        signal, action = "NONE", "No shared agency/network edge found."
    answer = {"id": r["id"], "related_by": rel.get("related_by"), "key": rel.get("key"),
              "count": count, "related": [{"name": it["name"], "kind": it["kind"]} for it in items]}
    return _env("related-network", query, signal=signal, action=action,
                score=_clamp01(count / 12.0),
                rationale=f"{count} related via {rel.get('related_by')}.", answer=answer)


async def _run_trip_plan(query: str, db_path: str | None = None) -> dict:
    """Compose a verified visit plan for a region/city: every GEO entity verified THERE — places, parks,
    temples, museums, theaters, theme parks, ski resorts, islands, hot springs, beaches, venues (matched
    on the located-in region edge + name/summary) — grouped by type, plus festivals THERE and signature
    national Korean dishes. Every item is a verified, citable entity."""
    q = (query or "").strip().casefold()
    geo: dict[str, list] = {}   # namespace -> [(eid, rec)]
    festivals: list = []
    foods: list = []
    for e in await store.entities(db_path=db_path):
        ns = e["entity_id"].split(":", 1)[0]
        if e["kind"] != "facts" or (ns not in _GEO_NS and ns not in ("festival", "food")):
            continue
        rec = await store.latest(e["entity_id"], "facts", db_path=db_path)
        if rec is None:
            continue
        if ns == "food":  # national picks — not region-filtered
            foods.append((e["entity_id"], rec))
            continue
        hay = " ".join(filter(None, [
            rec.data.get("agency_en"), rec.data.get("agency_ko"),
            rec.name.en_official, rec.name.ko, rec.summary_en])).casefold()
        if not (q and q in hay):
            continue
        if ns == "festival":
            festivals.append((e["entity_id"], rec))
        else:
            geo.setdefault(ns, []).append((e["entity_id"], rec))

    def by_skill(t) -> float:
        return -t[1].provenance.skill_score

    festivals.sort(key=by_skill)
    foods.sort(key=by_skill)
    all_geo = sorted((x for v in geo.values() for x in v), key=by_skill)

    def _li(items: list, n: int) -> list[dict]:
        return [{"id": eid, "name": {"ko": r.name.ko, "en_official": r.name.en_official},
                 "skill_score": r.provenance.skill_score} for eid, r in items[:n]]

    by_type = {ns: _li(sorted(v, key=by_skill), 6) for ns, v in sorted(geo.items())}
    n_geo, n_fe = len(all_geo), len(festivals)
    if n_geo >= 3:
        signal, action = "PLAN_READY", f"Build the itinerary — {n_geo} verified spot(s) in '{query}'."
    elif n_geo or n_fe:
        signal, action = "PARTIAL", f"Thin coverage for '{query}' — pad with national picks."
    else:
        signal, action = "THIN", f"No verified spots/festivals matched '{query}' yet."
    kinds = ", ".join(f"{len(v)} {ns}" for ns, v in sorted(geo.items())) or "none"
    return _env("trip-plan", query, signal=signal, action=action,
                score=_clamp01((n_geo + n_fe) / 8.0),
                rationale=(f"{n_geo} spot(s) across {len(geo)} type(s) ({kinds}) + {n_fe} festival(s) "
                           "matched; foods are national picks."),
                answer={"region": query, "places": _li(all_geo, 8), "by_type": by_type,
                        "festivals": _li(festivals, 4), "foods": _li(foods, 5)})


async def _run_food_guide(query: str, db_path: str | None = None) -> dict:
    """Foreigner meal filter: verified Korean dishes matching a dietary need or spice tolerance —
    'vegetarian', 'vegan', 'not spicy', 'no seafood'. The dish NAME is cross-verified; the spice +
    dietary tag is a labeled KoreaAPI EDITORIAL classification (clearly NOT cross-verified)."""
    q = (query or "").strip().casefold()
    want_vegan = any(w in q for w in ("vegan", "비건"))
    want_veg = want_vegan or any(w in q for w in ("vegetarian", "veggie", "채식", "no meat",
                                                  "meat-free", "meatless"))
    want_mild = any(w in q for w in ("not spicy", "non-spicy", "mild", "안 매", "안매", "순한", "덜 매"))
    no_seafood = any(w in q for w in ("no seafood", "seafood-free", "no fish", "해산물"))

    def ok(spice: str | None, veg: str | None) -> bool:
        vg, sp = (veg or "").casefold(), (spice or "").casefold()
        if want_vegan and "vegan" not in vg:
            return False
        if want_veg and not ("vegan" in vg or "vegetarian" in vg):
            return False
        if want_mild and sp not in ("none", "mild"):
            return False
        if no_seafood and "seafood" in vg:
            return False
        return True

    matches: list = []
    for e in await store.entities(db_path=db_path):
        eid = e["entity_id"]
        if e["kind"] != "facts" or not eid.startswith("food:") or not ok(FOOD_SPICE.get(eid), FOOD_VEG.get(eid)):
            continue
        rec = await store.latest(eid, "facts", db_path=db_path)
        if rec is not None:
            matches.append((eid, rec, FOOD_SPICE.get(eid), FOOD_VEG.get(eid)))
    matches.sort(key=lambda t: -t[1].provenance.skill_score)

    filters: list[str] = []
    if want_vegan:
        filters.append("vegan")
    elif want_veg:
        filters.append("vegetarian")
    if want_mild:
        filters.append("not-spicy")
    if no_seafood:
        filters.append("no-seafood")
    n = len(matches)
    if not filters:
        signal = "BROWSE"
        action = "No dietary/spice filter recognized — returning verified dishes with their tags."
    elif n:
        signal, action = "MATCHES", f"{n} verified dish(es) fit: {', '.join(filters)}."
    else:
        signal, action = "NONE", f"No verified dish fits: {', '.join(filters)}."
    dishes = [{"id": eid, "name": {"ko": r.name.ko, "en_official": r.name.en_official},
               "spice": sp, "dietary": vg, "skill_score": r.provenance.skill_score}
              for eid, r, sp, vg in matches[:12]]
    return _env("food-guide", query, signal=signal, action=action, score=_clamp01(n / 10.0),
                rationale=(f"{n} dish(es) match [{', '.join(filters) or 'no filter'}]; the dish name is "
                           "cross-verified, but the spice + dietary tag is a labeled KoreaAPI EDITORIAL "
                           "classification (not cross-verified)."),
                answer={"filters": filters, "dishes": dishes,
                        "editorial_note": "spice + dietary tags are KoreaAPI editorial, not cross-verified"})


_PRODUCTS = [
    {"id": "canonical-name", "name": "Canonical Name Resolver", "name_ko": "공식 표기 확정", "emoji": "🪪",
     "sector": "Identity / AEO", "inputs": ["name or id"],
     "about": "Confirm the authoritative Korean ↔ English spelling of an entity before you assert it.",
     "about_ko": "단정하기 전에 공식 한글 ↔ 영문 표기를 확정합니다.",
     "run": _run_canonical_name},
    {"id": "fact-check", "name": "Citability / Fact Check", "name_ko": "인용 가능성 판정", "emoji": "✅",
     "sector": "Trust / AEO", "inputs": ["name or id"],
     "about": "Decide whether a claim about an entity is safe to cite (cross-/triple-verified / certified).",
     "about_ko": "이 주장을 인용해도 되는지(교차/3중 검증·공증) 판정합니다.",
     "run": _run_fact_check},
    {"id": "identity-resolve", "name": "Entity ID Resolver", "name_ko": "식별자 매핑", "emoji": "🧭",
     "sector": "Reconciliation", "inputs": ["name, external id, or id"],
     "about": "Map a fuzzy mention or external ID onto the canonical verified KoreaAPI entity.",
     "about_ko": "모호한 멘션·외부 ID를 신뢰 엔티티에 매핑합니다.",
     "run": _run_identity_resolve},
    {"id": "trend-radar", "name": "Korea Demand Radar", "name_ko": "수요 레이더", "emoji": "📈",
     "sector": "Trends", "inputs": ["category or 'all'"],
     "about": "Read what is rising in Korea now from accumulated demand signal.",
     "about_ko": "축적된 수요 신호로 지금 뜨는 것을 읽습니다.",
     "run": _run_trend_radar},
    {"id": "agency-roster", "name": "Agency Roster", "name_ko": "소속사 명단", "emoji": "🏢",
     "sector": "Knowledge Graph", "inputs": ["agency name"],
     "about": "List the verified artists under a Korean agency/label (소속사).",
     "about_ko": "소속사/레이블 아래 검증된 아티스트를 나열합니다.",
     "run": _run_agency_roster},
    {"id": "person-credits", "name": "Person Credits", "name_ko": "인물 크레딧", "emoji": "🎬",
     "sector": "Knowledge Graph", "inputs": ["person name"],
     "about": "Aggregate a Korean-culture person's verified credits across works.",
     "about_ko": "작품들에 걸친 인물의 검증된 크레딧을 집계합니다.",
     "run": _run_person_credits},
    {"id": "related-network", "name": "Related Network", "name_ko": "연관 네트워크", "emoji": "🕸️",
     "sector": "Knowledge Graph", "inputs": ["name or id"],
     "about": "Find entities sharing the same agency/network hub edge.",
     "about_ko": "같은 소속사/채널 허브를 공유하는 엔티티를 찾습니다.",
     "run": _run_related_network},
    {"id": "trip-plan", "name": "Trip Plan (Region)", "name_ko": "여행 플랜", "emoji": "🧳",
     "sector": "Travel", "inputs": ["region or city name, e.g. 'Busan'"],
     "about": "Every verified spot in a region — places, parks, temples, museums, beaches, ski resorts… "
              "grouped by type — plus festivals + signature dishes; itinerary raw material.",
     "about_ko": "지역의 검증된 모든 명소(장소·공원·절·박물관·해변 등)를 유형별로 + 축제 + 대표 음식 — 여행 일정 재료.",
     "run": _run_trip_plan},
    {"id": "food-guide", "name": "Food Guide (Dietary)", "name_ko": "음식 가이드", "emoji": "🍚",
     "sector": "Travel", "inputs": ["a dietary/spice filter, e.g. 'vegetarian', 'not spicy', 'no seafood'"],
     "about": "Verified Korean dishes filtered by dietary need or spice tolerance (vegan / vegetarian / "
              "not-spicy / no-seafood). The dish name is cross-verified; the spice + dietary tag is "
              "labeled KoreaAPI editorial (not cross-verified).",
     "about_ko": "채식·비건·안 매운·해산물 없는 검증된 한식 필터 — 음식명은 교차검증, 맵기·식이 태그는 KoreaAPI 편집(비교차검증).",
     "run": _run_food_guide},
]
_BY_ID = {p["id"]: p for p in _PRODUCTS}


def list_products() -> dict:
    """The catalog — every Answer Product an agent can call, with its inputs + the shared envelope."""
    return {
        "count": len(_PRODUCTS),
        "products": [{"id": p["id"], "name": p["name"], "name_ko": p["name_ko"], "emoji": p["emoji"],
                      "sector": p["sector"], "inputs": p["inputs"], "about": p["about"],
                      "about_ko": p["about_ko"]}
                     for p in _PRODUCTS],
        "envelope": ["product", "name", "signal", "action", "score", "rationale", "answer", "evidence"],
        "note": ("Each product turns the verified store into one decision. Call answer(product, query); "
                 "omit product to run all; or ask(question) to auto-route free text to the right product. "
                 "Free; the underlying korea-rising signal is x402-metered."),
        "note_ko": "각 제품은 검증 저장소를 하나의 결정으로 바꿉니다. answer(product, query) 호출; "
                   "product 생략 시 전체 실행; 또는 ask(question)으로 자유 문장을 알맞은 제품에 자동 라우팅. "
                   "무료 (korea-rising 신호만 x402 과금).",
    }


async def answer(product: str, query: str, *, db_path: str | None = None) -> dict:
    """Run ONE Answer Product on a query -> the decision envelope (or an error dict)."""
    p = _BY_ID.get(str(product))
    if not p:
        return {"error": f"unknown product '{product}'", "available": [x["id"] for x in _PRODUCTS]}
    if not (query or "").strip() and product != "trend-radar":
        return {"error": "query required", "product": product}
    return await p["run"](query, db_path=db_path)


async def answer_all(query: str, *, db_path: str | None = None) -> dict:
    """Run EVERY product on one query — "tell me everything KoreaAPI decides about this string"."""
    q = (query or "").strip()
    if not q:
        return {"error": "query required"}
    results: list[dict] = []
    for p in _PRODUCTS:
        try:
            results.append(await p["run"](q, db_path=db_path))
        except Exception as e:  # one product failing must never break the batch
            results.append({"product": p["id"], "signal": "ERROR", "error": str(e)})
    return {"query": q, "count": len(results), "answers": results}


# ---- natural-language router: free text -> (product, arg) ------------------------------------------
# "Cheap AI as collection labor" applied to the REQUEST side: an agent that doesn't yet know WHICH
# product it needs sends a free-text question; a cheap LLM (Haiku) picks one product + extracts its
# argument. Best-effort — no ANTHROPIC_API_KEY / any failure falls back to a pure keyword router, so
# ask() ALWAYS routes (offline, keyless too). The router only CHOOSES a product; the product itself
# is the same verified, offline decision layer — routing never fabricates an answer.

_ROUTE_MODEL = "claude-haiku-4-5-20251001"  # cheap; routing is a tiny classification task

# (substrings -> product id); first match wins. Pure, offline, keyless — the fallback when the LLM is
# unavailable, and independently unit-tested. Ordered most-specific first.
_KEYWORD_ROUTES: list[tuple[tuple[str, ...], str]] = [
    (("vegan", "vegetarian", "veggie", "not spicy", "non-spicy", "no seafood", "no meat", "meat-free",
      "채식", "비건", "안 매", "안매", "매운", "해산물", "먹을"), "food-guide"),
    (("trip", "itinerary", "visit", "travel", "things to do", "여행", "가볼", "관광", "일정", "코스"), "trip-plan"),
    (("rising", "trending", "trend", "what's hot", "popular now", "뜨는", "인기", "요즘", "핫한"), "trend-radar"),
    (("credit", "filmography", "starred", "acted in", "directed", "출연", "필모", "크레딧", "작품"), "person-credits"),
    (("agency", "label", "roster", "artists under", "소속사", "레이블", "명단", "소속"), "agency-roster"),
    (("related", "network", "same agency", "also on", "labelmate", "연관", "네트워크", "같은"), "related-network"),
    (("spelling", "spell", "romaniz", "how do you write", "korean name", "표기", "한글로", "로마자"), "canonical-name"),
    (("cite", "citable", "is it true", "fact-check", "verify", "사실", "인용", "검증", "맞아"), "fact-check"),
]


def _fallback_route(q: str) -> dict:
    """Pure keyword router (no key, no network). Default: identity-resolve (map the mention to an id)."""
    ql = q.casefold()
    for subs, pid in _KEYWORD_ROUTES:
        if any(s in ql for s in subs):
            return {"product": pid, "query": q}
    return {"product": "identity-resolve", "query": q}


def _route_system() -> str:
    """Router system prompt, built from the live product catalog (never drifts from _PRODUCTS)."""
    catalog = "\n".join(f"- {p['id']}: {p['about']}" for p in _PRODUCTS)
    return (
        "You route a user's free-text request about Korean culture to exactly ONE KoreaAPI Answer "
        "Product and extract the argument to pass it.\nProducts:\n" + catalog + "\n\n"
        'Return ONLY a JSON object: {"product": "<one id from the list>", "query": "<argument>"}. '
        "The query is the entity, region, category, person, agency, or dietary/spice filter the chosen "
        "product needs — extract the shortest sufficient argument, not the whole sentence. If nothing "
        'clearly fits, use "identity-resolve". No prose, no markdown, no code fences.'
    )


def route(question: str) -> dict:
    """Route a free-text question to ONE Answer Product + its argument. Best-effort LLM (Haiku) with a
    pure keyword fallback (no key / any failure). Returns {product, query, via: 'llm'|'keyword'|'empty'}."""
    q = (question or "").strip()
    if not q:
        return {"product": None, "query": "", "via": "empty"}
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            import anthropic

            msg = anthropic.Anthropic().messages.create(
                model=_ROUTE_MODEL, max_tokens=120, system=_route_system(),
                messages=[{"role": "user", "content": q}],
            )
            text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
            m = re.search(r"\{.*\}", text, re.DOTALL)
            if m:
                obj = json.loads(m.group(0))
                pid = obj.get("product")
                if pid in _BY_ID:
                    return {"product": pid, "query": (obj.get("query") or "").strip() or q, "via": "llm"}
        except Exception:
            pass  # fall through to the deterministic keyword router
    return {**_fallback_route(q), "via": "keyword"}


async def ask(question: str, *, db_path: str | None = None) -> dict:
    """Natural-language entry point: route a free-text question to the right Answer Product, run it, and
    return the decision envelope annotated with how it routed (`routed`). The one call an agent makes
    when it doesn't yet know WHICH product it needs — routing chooses; the verified product decides."""
    q = (question or "").strip()
    if not q:
        return {"error": "question required"}
    r = route(q)
    pid = r.get("product")
    if not pid:
        return {"error": "question required"}
    env = await answer(pid, r["query"], db_path=db_path)
    if isinstance(env, dict):
        env["routed"] = {"from": q, "to_product": pid, "query": r["query"], "via": r.get("via")}
    return env
