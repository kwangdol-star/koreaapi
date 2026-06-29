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

Offline-testable: no keys, no network, no chain. Discoverable at /v1/answer and via the
MCP tools list_answer_products + get_answer.
"""

from __future__ import annotations

from . import service


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


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


_PRODUCTS = [
    {"id": "canonical-name", "name": "Canonical Name Resolver", "emoji": "🪪",
     "sector": "Identity / AEO", "inputs": ["name or id"],
     "about": "Confirm the authoritative Korean ↔ English spelling of an entity before you assert it.",
     "run": _run_canonical_name},
    {"id": "fact-check", "name": "Citability / Fact Check", "emoji": "✅",
     "sector": "Trust / AEO", "inputs": ["name or id"],
     "about": "Decide whether a claim about an entity is safe to cite (cross-/triple-verified / certified).",
     "run": _run_fact_check},
    {"id": "identity-resolve", "name": "Entity ID Resolver", "emoji": "🧭",
     "sector": "Reconciliation", "inputs": ["name, external id, or id"],
     "about": "Map a fuzzy mention or external ID onto the canonical verified KoreaAPI entity.",
     "run": _run_identity_resolve},
    {"id": "trend-radar", "name": "Korea Demand Radar", "emoji": "📈",
     "sector": "Trends", "inputs": ["category or 'all'"],
     "about": "Read what is rising in Korea now from accumulated demand signal.",
     "run": _run_trend_radar},
    {"id": "agency-roster", "name": "Agency Roster", "emoji": "🏢",
     "sector": "Knowledge Graph", "inputs": ["agency name"],
     "about": "List the verified artists under a Korean agency/label (소속사).",
     "run": _run_agency_roster},
    {"id": "person-credits", "name": "Person Credits", "emoji": "🎬",
     "sector": "Knowledge Graph", "inputs": ["person name"],
     "about": "Aggregate a Korean-culture person's verified credits across works.",
     "run": _run_person_credits},
    {"id": "related-network", "name": "Related Network", "emoji": "🕸️",
     "sector": "Knowledge Graph", "inputs": ["name or id"],
     "about": "Find entities sharing the same agency/network hub edge.",
     "run": _run_related_network},
]
_BY_ID = {p["id"]: p for p in _PRODUCTS}


def list_products() -> dict:
    """The catalog — every Answer Product an agent can call, with its inputs + the shared envelope."""
    return {
        "count": len(_PRODUCTS),
        "products": [{"id": p["id"], "name": p["name"], "emoji": p["emoji"],
                      "sector": p["sector"], "inputs": p["inputs"], "about": p["about"]}
                     for p in _PRODUCTS],
        "envelope": ["product", "name", "signal", "action", "score", "rationale", "answer", "evidence"],
        "note": ("Each product turns the verified store into one decision. Call answer(product, query); "
                 "omit product to run all. Free; the underlying korea-rising signal is x402-metered."),
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
