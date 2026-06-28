"""Human data console for KoreaAPI (read-only ops view over the append-only store).

The product is agent-facing (MCP), but a verifiable-data business needs a human
cockpit: browse what was collected, watch data quality (Skill Score / freshness /
source agreement), and spot-correct. This is Face 2 over the SAME source of truth
agents read - never a second data path.

CLI:
  python -m koreaapi.admin seed     # populate koreaapi.db with sample snapshots (offline)
  python -m koreaapi.admin pull     # LIVE: pull real Wikidata snapshots (needs network egress)
  python -m koreaapi.admin chart    # LIVE: Circle Chart weekly + LLM-extract (needs egress + key)
  python -m koreaapi.admin youtube  # LIVE: official-channel release snapshots (needs YOUTUBE_API_KEY)
  python -m koreaapi.admin sweep    # LIVE: discover labelmates from each anchored agency (SPARQL)
  python -m koreaapi.admin discover # LIVE: bulk-discover each vertical's Korean entities (SPARQL) -> 10x
  python -m koreaapi.admin load     # re-seed the DB from data/latest.json (so discovery accumulates)
  python -m koreaapi.admin export   # write data/ asset (snapshots.jsonl history + latest.json)
  python -m koreaapi.admin signals  # top behavioral signals (engine 2: what agents query)
  python -m koreaapi.admin stats    # print a data-quality summary
  python -m koreaapi.admin dump     # print recent snapshots
  python -m koreaapi.admin report   # write report.html (open it in a browser)
  python -m koreaapi.admin digest   # write data/korea-rising.md (shareable verified digest)
  python -m koreaapi.admin llms     # regenerate llms.txt (agent index) from the live store
  python -m koreaapi.admin entitypages  # write per-entity + per-person citable pages (site/)
  python -m koreaapi.admin sitemap  # write sitemap.xml (every entity + person page)
  python -m koreaapi.admin monitor  # write monitor.html (human data-quality cockpit)

For zero-code interactive browse / query / JSON API:  datasette koreaapi.db
"""

from __future__ import annotations

import asyncio
import html
import json
import os
import re
import sys
from datetime import datetime, timezone

from .models import Record
from .pipeline import store
from .pipeline.ingest import ingest_chart, ingest_one, ingest_youtube
from .pipeline.scheduler import CADENCE
from .roster import ARTISTS, NAMES
from .sources.circlechart import CircleChartSource
from .sources.mock import MockSource
from .sources.musicbrainz import MusicBrainzSource
from .sources.wikidata import _DISCOVER, WikidataSource, fetch_discover, fetch_labelmates
from .sources.wikipedia import WikipediaSource
from .sources.youtube import YouTubeSource

# Offline sample data for `seed` (replace with real source adapters later).
# The third entry has a single source -> demonstrates the single-source Skill cap.
_SAMPLES = [
    ("comeback", "artist:bts", {
        "name_ko": "방탄소년단", "name_en_official": "BTS", "name_romanized": "Bangtan Sonyeondan",
        "name_en_source": "official", "date": "2026-06-13", "agency_en": "Big Hit Music",
        "summary_en": "BTS comeback scheduled 2026-06-13.",
        "summary_ko": "방탄소년단 컴백 2026-06-13.",
    }, 2),
    ("chart", "artist:newjeans", {
        "name_ko": "뉴진스", "name_en_official": "NewJeans", "name_romanized": "Nyujinseu",
        "name_en_source": "official", "rank": 1, "agency_en": "ADOR",
        "summary_en": "NewJeans #1 on the weekly chart.",
        "summary_ko": "뉴진스 주간 차트 1위.",
    }, 2),
    ("comeback", "artist:aespa", {
        "name_ko": "에스파", "name_en_official": "aespa", "name_romanized": "Eseupa",
        "name_en_source": "official", "date": "2026-07-01", "agency_en": "SM Entertainment",
        "summary_en": "aespa comeback scheduled 2026-07-01.",
        "summary_ko": "에스파 컴백 2026-07-01.",
    }, 1),
]


async def seed(db_path: str | None = None) -> None:
    for kind, entity_id, payload, n_sources in _SAMPLES:
        names = ["Circle Chart", "Wikidata"][:n_sources]
        sources = [MockSource(name, payload) for name in names]
        await ingest_one(kind, entity_id, sources, db_path=db_path)


async def pull(entity_ids: list[str] | None = None, *, db_path: str | None = None) -> dict:
    """Live-pull curated artists from Wikidata + Wikipedia and append REAL verified snapshots.

    The turnkey live ingestion (component A, live): for each entity it fetches the bilingual
    name from two INDEPENDENT sources (Wikidata + Wikipedia), CROSS-VERIFIES them, identity-
    checks, computes Skill Score + provenance, and appends a snapshot. When both agree on the
    name the score clears the single-source cap. Needs network egress; where it's blocked (e.g.
    the sandbox allowlist) failed sources are dropped by graceful degradation - a snapshot is
    still appended if at least one source succeeds, and nothing if none do (never poison).
    """
    ids = entity_ids or list(NAMES)  # artists + dramas + films
    # Three sources. MusicBrainz is a TRULY independent 3rd source (separate DB; Wikidata+Wikipedia
    # are correlated) — it self-filters to artists (raises -> gracefully dropped for other verticals),
    # so it only adds a cross-check where it's competent. (Roadmap: TMDB for video, Open Library for
    # book/classic, Nominatim for place — add the same way; each self-scopes.)
    sources = [WikidataSource(), WikipediaSource(), MusicBrainzSource()]
    ingested: list[str] = []
    failed: list[str] = []
    for i, entity_id in enumerate(ids):
        if i:
            await asyncio.sleep(0.2)  # pace the ~100-entity batch so Wikimedia doesn't throttle the
            #                           tail (dramas/films sort last); _http_get also retries on 429
        rec = await ingest_one("facts", entity_id, sources, db_path=db_path)
        (ingested if rec is not None else failed).append(entity_id)
    return {"requested": ids, "ingested": ingested, "failed": failed}


async def youtube(entity_ids: list[str] | None = None, *, db_path: str | None = None) -> dict:
    """Live-pull each artist's OFFICIAL YouTube channel (stats + latest release) -> kind='release'.

    Live-state event data for the prediction-market vertical + engine 2 (view velocity). NOT a
    name cross-verifier (channels are EN/brand-titled - that would lower scores; the Spotify
    lesson) - it appends its own single-source-capped snapshot. The identity guard drops any
    channel whose title doesn't match the artist's known aliases, so a fan/impostor channel is
    skipped, never poisoned. Needs YOUTUBE_API_KEY + egress; keyless/blocked/unresolved -> skip.
    """
    ids = entity_ids or list(ARTISTS)
    src = YouTubeSource()
    ingested: list[str] = []
    skipped: list[str] = []
    for entity_id in ids:
        try:
            payload = await src.fetch(entity_id)
        except Exception:
            payload = None
        rec = await ingest_youtube(entity_id, payload, db_path=db_path) if payload else None
        (ingested if rec is not None else skipped).append(entity_id)
    return {"ingested": ingested, "skipped": skipped}


def _agency_qids_from_store(recs: list) -> dict[str, str]:
    """agency Q-id -> agency name, mined from already-ingested artists' `agency_source`."""
    out: dict[str, str] = {}
    for r in recs:
        src = (r.data or {}).get("agency_source") or ""
        m = re.search(r"\bQ\d+\b", src)
        if m:
            out.setdefault(m.group(0), r.data.get("agency_en") or r.data.get("agency_ko") or m.group(0))
    return out


async def sweep(*, db_path: str | None = None, max_new: int = 10) -> dict:
    """Agency-hub discovery: for each anchored 소속사 (Wikidata label), find direct labelmate artists
    via SPARQL and ingest the NEW ones through the SAME Wikidata+Wikipedia cross-verification, so the
    verified roster grows from the agency hub ('정보가 계속 나온다') without lowering the bar - only
    cross-verified labelmates are kept. Bounded per run; needs open network (SPARQL on a runner).
    """
    recs = await store.recent(2000, db_path=db_path)
    have = {r.entity_id for r in recs}
    have_qids = {
        m2.group(0) for r in recs for s in r.provenance.sources if (m2 := re.search(r"\bQ\d+\b", s))
    }
    agencies = _agency_qids_from_store(recs)
    candidates: list[dict] = []
    for qid in agencies:
        try:
            candidates.extend(await asyncio.to_thread(fetch_labelmates, qid))
        except Exception:
            continue  # graceful: skip an agency whose SPARQL failed
    todo: list[tuple[str, str]] = []
    seen: set[str] = set()
    for m in candidates:
        eid = f"artist:{m['slug']}"
        # Dedup by Q-id (reliable) as well as slug-id/run-local: a discovered act already in the
        # store under a different entity_id (its Wikidata label slugifies differently than the
        # hand-authored id) must not be re-ingested as a DUPLICATE entity that splits its history.
        if eid in have or m["qid"] in have_qids or m["slug"] in seen or m["qid"] in seen:
            continue
        seen.add(m["slug"])
        seen.add(m["qid"])
        todo.append((eid, m["en"]))
    todo = todo[:max_new]
    n_candidates = len(candidates)
    aliases = dict(todo)
    sources = [WikidataSource(aliases=aliases), WikipediaSource(aliases=aliases),
               MusicBrainzSource(aliases=aliases)]
    ingested: list[str] = []
    for eid, _name in todo:
        rec = await ingest_one("facts", eid, sources, db_path=db_path)
        if rec is not None:
            ingested.append(eid)
    return {"agencies": list(agencies.values()), "candidates": n_candidates, "ingested": ingested}


async def discover(verticals: list[str] | None = None, *, db_path: str | None = None,
                   max_new: int = 25, limit: int = 400) -> dict:
    """Universe discovery (the path to 10x): SPARQL-list each vertical's Korean entities and ingest
    the NEW ones through the SAME Wikidata+Wikipedia cross-verification — only verified ones are kept,
    so breadth grows without lowering the bar. The discovered Q-id is fetched DIRECTLY (no same-name
    search drift). Bounded per run + per vertical (rate-limit/runtime safe) so the daily collector
    accrues steadily; dedups against the store by entity_id AND Q-id. Needs open network (SPARQL)."""
    verticals = verticals or list(_DISCOVER)
    recs = await store.recent(20000, db_path=db_path)
    have = {r.entity_id for r in recs}
    have_qids = {
        m.group(0) for r in recs for s in r.provenance.sources if (m := re.search(r"\bQ\d+\b", s))
    }
    out: dict[str, dict] = {}
    for v in verticals:
        try:
            cands = await asyncio.to_thread(fetch_discover, v, limit=limit)
        except Exception:
            out[v] = {"candidates": 0, "ingested": []}  # graceful: skip a vertical whose SPARQL failed
            continue
        todo: list[tuple[str, str, str]] = []
        seen: set[str] = set()
        for c in cands:
            eid = f"{v}:{c['slug']}"
            if eid in have or c["qid"] in have_qids or c["slug"] in seen or c["qid"] in seen:
                continue
            seen.add(c["slug"])
            seen.add(c["qid"])
            todo.append((eid, c["en"], c["qid"]))
        todo = todo[:max_new]
        aliases = {eid: en for eid, en, _q in todo}
        qids = {eid: q for eid, _en, q in todo}
        sources = [WikidataSource(aliases=aliases, qids=qids), WikipediaSource(aliases=aliases),
                   MusicBrainzSource(aliases=aliases)]
        ingested: list[str] = []
        for eid, _en, _q in todo:
            rec = await ingest_one("facts", eid, sources, db_path=db_path)
            if rec is not None:
                ingested.append(eid)
            have.add(eid)
        out[v] = {"candidates": len(cands), "ingested": ingested}
    return out


async def load_latest(in_path: str = "data/latest.json", *, db_path: str | None = None) -> int:
    """Re-seed the DB from the committed data asset (data/latest.json) so a fresh-per-run collector
    ACCUMULATES: discover()/sweep() dedup against everything found in prior runs, instead of
    rediscovering the same head every day. Best-effort — a missing or garbled file just returns 0."""
    if not os.path.exists(in_path):
        return 0
    try:
        with open(in_path, encoding="utf-8") as f:
            rows = json.load(f)
    except Exception:
        return 0
    n = 0
    for d in rows:
        try:
            await store.append_record(Record.model_validate(d), db_path=db_path)
            n += 1
        except Exception:
            continue
    return n


async def export(db_path: str | None = None, *, out_dir: str = "data") -> dict:
    """Write the data asset as committable text - the cold-start 'database' before Postgres.

    - data/snapshots.jsonl : full time-series, one record per line, APPENDED (history grows)
    - data/latest.json     : current state, latest snapshot per entity+kind (overwritten)

    Both are diffable, versionable, and crawlable (GEO). The scheduled collector
    (.github/workflows/collect.yml) runs pull + export each tick so the asset accumulates in
    git - run on GitHub's runners (open network), where the live pull works even though the
    dev sandbox blocks Wikidata egress. Run export right after a pull (it appends history).
    """
    recs = await store.recent(100000, db_path=db_path)
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "snapshots.jsonl"), "a", encoding="utf-8") as f:
        for r in reversed(recs):  # append oldest-first so the file reads as a timeline
            f.write(r.model_dump_json() + "\n")
    latest: dict[str, dict] = {}
    for r in recs:  # recs are newest-first -> first seen per entity+kind is the latest
        key = f"{r.entity_id}:{r.kind}"
        if key not in latest:
            latest[key] = json.loads(r.model_dump_json())
    with open(os.path.join(out_dir, "latest.json"), "w", encoding="utf-8") as f:
        json.dump(list(latest.values()), f, ensure_ascii=False, indent=2)
    return {"appended": len(recs), "entities": len(latest)}


def _fresh(latest_at: str, kind: str) -> bool:
    try:
        dt = datetime.fromisoformat(latest_at)
    except (ValueError, TypeError):
        return False
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)  # tolerate a naive stored timestamp (assume UTC) - never crash stats
    age = (datetime.now(timezone.utc) - dt).total_seconds()
    return age <= CADENCE.get(kind, 86400)


async def stats(db_path: str | None = None) -> dict:
    recs = await store.recent(1000, db_path=db_path)
    ents = await store.entities(db_path=db_path)
    if not recs:
        return {"entities": 0, "snapshots": 0}
    avg = sum(r.provenance.skill_score for r in recs) / len(recs)
    low = sum(1 for r in recs if r.provenance.confidence == "low")
    fresh = sum(1 for e in ents if _fresh(e["latest_at"], e["kind"]))
    return {
        "entities": len(ents),
        "snapshots": sum(e["snapshots"] for e in ents),
        "avg_skill_score": round(avg, 3),
        "low_confidence": low,
        "fresh_entities": f"{fresh}/{len(ents)}",
    }


def _wikidata_url(sources: list[str]) -> str | None:
    """Pull a Wikidata entity URL out of a provenance citation like 'Wikidata Q13580495 ...'."""
    for s in sources:
        if "wikidata" in s.lower():
            m = re.search(r"\bQ\d+\b", s)
            if m:
                return f"https://www.wikidata.org/entity/{m.group(0)}"
    return None


def _entity_node(r) -> dict:
    """One verified entity as a Schema.org node, shared by the index + entity pages: a `drama:` ->
    TVSeries, otherwise an artist -> MusicGroup (carrying the verified 소속사 edge)."""
    name = r.name.en_official or r.name.ko
    alt = [x for x in (r.name.ko, r.name.romanized) if x]
    wd = _wikidata_url(r.provenance.sources)
    # Schema.org description: prefer the rich Wikipedia-sourced abstract (real substance an answer
    # engine can lift) over our terse facts line; fall back to the facts line when there's no abstract.
    desc = r.data.get("abstract_en") or r.summary_en
    if r.entity_id.startswith("webtoon:"):
        node = {"@type": "ComicSeries", "name": name, "alternateName": alt,
                "description": desc, "dateModified": r.snapshot_at.isoformat()}
        if wd:
            node["sameAs"] = wd
        if r.data.get("debut"):  # publication date -> citable "when did X start?"
            node["datePublished"] = r.data["debut"]
        creators = r.data.get("members") or []
        if creators:  # author(s) P50 -> citable "who created/wrote X?" (schema.org author)
            node["author"] = [{"@type": "Person", "name": m} for m in creators]
        pub = r.data.get("agency_en") or r.data.get("agency_ko")
        if pub:  # publisher / platform P123 (Naver·Kakao)
            node["publisher"] = {"@type": "Organization", "name": pub}
        return node
    if r.entity_id.startswith("place:"):
        node = {"@type": "TouristAttraction", "name": name, "alternateName": alt,
                "description": desc, "dateModified": r.snapshot_at.isoformat()}
        if wd:
            node["sameAs"] = wd
        region = r.data.get("agency_en") or r.data.get("agency_ko")  # located-in (P131)
        if region:  # citable "where is X?"
            node["containedInPlace"] = {"@type": "Place", "name": region}
        geo = r.data.get("geo")
        if geo:  # P625 -> map + schema.org GeoCoordinates
            node["geo"] = {"@type": "GeoCoordinates", "latitude": geo["lat"], "longitude": geo["lon"]}
        return node
    if r.entity_id.startswith("food:"):
        # a Korean dish: verified bilingual name + Wikidata sameAs is the asset (no agency/people edge)
        node = {"@type": "Thing", "name": name, "alternateName": alt,
                "description": desc, "dateModified": r.snapshot_at.isoformat()}
        if wd:
            node["sameAs"] = wd
        return node
    if r.entity_id.startswith("company:"):
        node = {"@type": "Organization", "name": name, "alternateName": alt,
                "description": desc, "dateModified": r.snapshot_at.isoformat()}
        if wd:
            node["sameAs"] = wd
        if r.data.get("debut"):  # founded -> citable "when was X founded?"
            node["foundingDate"] = r.data["debut"]
        return node
    if r.entity_id.startswith("brand:"):
        node = {"@type": "Brand", "name": name, "alternateName": alt,
                "description": desc, "dateModified": r.snapshot_at.isoformat()}
        if wd:
            node["sameAs"] = wd
        owner = r.data.get("agency_en") or r.data.get("agency_ko")  # owned-by P127 (parent group)
        if owner:
            node["manufacturer"] = {"@type": "Organization", "name": owner}
        return node
    if r.entity_id.startswith(("book:", "classic:")):
        node = {"@type": "Book", "name": name, "alternateName": alt,
                "description": desc, "dateModified": r.snapshot_at.isoformat()}
        if wd:
            node["sameAs"] = wd
        if r.data.get("debut"):
            node["datePublished"] = r.data["debut"]
        authors = r.data.get("members") or []
        if authors:  # author(s) P50 -> citable "who wrote X?"
            node["author"] = [{"@type": "Person", "name": m} for m in authors]
        pub = r.data.get("agency_en") or r.data.get("agency_ko")
        if pub:
            node["publisher"] = {"@type": "Organization", "name": pub}
        return node
    if r.entity_id.startswith("history:"):
        # a dynasty/period/event: verified bilingual name + sameAs + start date (no schema.org period
        # type fits cleanly, so Thing — still carries name/description/sameAs for AEO citation)
        node = {"@type": "Thing", "name": name, "alternateName": alt,
                "description": desc, "dateModified": r.snapshot_at.isoformat()}
        if wd:
            node["sameAs"] = wd
        return node
    if r.entity_id.startswith("heritage:"):
        node = {"@type": "CreativeWork", "name": name, "alternateName": alt,
                "description": desc, "dateModified": r.snapshot_at.isoformat()}
        if wd:
            node["sameAs"] = wd
        return node
    if r.entity_id.startswith("folklore:"):
        node = {"@type": "Thing", "name": name, "alternateName": alt,
                "description": desc, "dateModified": r.snapshot_at.isoformat()}
        if wd:
            node["sameAs"] = wd
        return node
    if r.entity_id.startswith("medical:"):
        node = {"@type": "Hospital", "name": name, "alternateName": alt,
                "description": desc, "dateModified": r.snapshot_at.isoformat()}
        if wd:
            node["sameAs"] = wd
        region = r.data.get("agency_en") or r.data.get("agency_ko")  # located-in (P131)
        if region:  # citable "where is X?"
            node["address"] = {"@type": "PostalAddress", "addressLocality": region,
                               "addressCountry": "KR"}
        if r.data.get("debut"):  # founded -> citable "when was X founded?"
            node["foundingDate"] = r.data["debut"]
        geo = r.data.get("geo")
        if geo:  # P625 -> map + schema.org GeoCoordinates
            node["geo"] = {"@type": "GeoCoordinates", "latitude": geo["lat"], "longitude": geo["lon"]}
        return node
    if r.entity_id.startswith("region:"):
        # The country -> schema.org Country; its administrative divisions -> AdministrativeArea. Verified
        # bilingual name + sameAs + the STABLE infobox facts (capital/language/currency/ISO/calling code)
        # as additionalProperty — citable, machine-readable. (Volatile stats stay off-model.)
        is_country = r.entity_id == "region:southkorea"
        node = {"@type": "Country" if is_country else "AdministrativeArea", "name": name,
                "alternateName": alt, "description": desc,
                "dateModified": r.snapshot_at.isoformat()}
        if wd:
            node["sameAs"] = wd
        facts = [
            ("Capital", r.data.get("capital_en") or r.data.get("capital_ko")),
            ("Official language", r.data.get("language_en") or r.data.get("language_ko")),
            ("Currency", r.data.get("currency_en") or r.data.get("currency_ko")),
            ("ISO 3166-1", r.data.get("iso_code")),
            ("Country calling code", r.data.get("calling_code")),
        ]
        props = [{"@type": "PropertyValue", "name": n, "value": v} for n, v in facts if v]
        if props:
            node["additionalProperty"] = props
        return node
    if r.entity_id.startswith("game:"):
        node = {"@type": "VideoGame", "name": name, "alternateName": alt,
                "description": desc, "dateModified": r.snapshot_at.isoformat()}
        if wd:
            node["sameAs"] = wd
        if r.data.get("debut"):  # release date -> citable "when did X come out?"
            node["datePublished"] = r.data["debut"]
        dev = r.data.get("agency_en") or r.data.get("agency_ko")  # developer P178 (the studio)
        if dev:  # citable "who made X?"
            node["creator"] = {"@type": "Organization", "name": dev}
        return node
    if r.entity_id.startswith("show:"):
        node = {"@type": "TVSeries", "name": name, "alternateName": alt,
                "description": desc, "dateModified": r.snapshot_at.isoformat()}
        if wd:
            node["sameAs"] = wd
        if r.data.get("debut"):  # first-aired -> citable "when did X start?"
            node["datePublished"] = r.data["debut"]
        cast = r.data.get("members") or []
        if cast:  # verified host/cast -> citable "who's in X?"
            node["actor"] = [{"@type": "Person", "name": m} for m in cast]
        return node
    if r.entity_id.startswith("animation:"):
        node = {"@type": "TVSeries", "name": name, "alternateName": alt,
                "description": desc, "dateModified": r.snapshot_at.isoformat()}
        if wd:
            node["sameAs"] = wd
        if r.data.get("debut"):  # release date -> citable "when did X come out?"
            node["datePublished"] = r.data["debut"]
        studio = r.data.get("agency_en") or r.data.get("agency_ko")  # production company P272
        if studio:
            node["productionCompany"] = {"@type": "Organization", "name": studio}
        return node
    if r.entity_id.startswith("university:"):
        node = {"@type": "CollegeOrUniversity", "name": name, "alternateName": alt,
                "description": desc, "dateModified": r.snapshot_at.isoformat()}
        if wd:
            node["sameAs"] = wd
        region = r.data.get("agency_en") or r.data.get("agency_ko")  # located-in (P131)
        if region:  # citable "where is X?"
            node["address"] = {"@type": "PostalAddress", "addressLocality": region,
                               "addressCountry": "KR"}
        if r.data.get("debut"):  # founded -> citable "when was X founded?"
            node["foundingDate"] = r.data["debut"]
        geo = r.data.get("geo")
        if geo:  # P625 -> map + schema.org GeoCoordinates
            node["geo"] = {"@type": "GeoCoordinates", "latitude": geo["lat"], "longitude": geo["lon"]}
        return node
    if r.entity_id.startswith(("drama:", "film:")):
        node = {"@type": "Movie" if r.entity_id.startswith("film:") else "TVSeries",
                "name": name, "alternateName": alt,
                "description": desc, "dateModified": r.snapshot_at.isoformat()}
        if wd:
            node["sameAs"] = wd
        if r.data.get("debut"):  # air/release date -> citable "when did X come out?"
            node["datePublished"] = r.data["debut"]
        cast = r.data.get("members") or []
        if cast:  # verified cast -> citable "who's in X?" (schema.org TVSeries/Movie.actor)
            node["actor"] = [{"@type": "Person", "name": m} for m in cast]
        directors = r.data.get("directors") or []
        if directors:  # verified director(s) -> citable "who directed X?"
            node["director"] = [{"@type": "Person", "name": m} for m in directors]
        return node
    node = {
        "@type": "MusicGroup",
        "name": name,
        "alternateName": alt,
        "description": desc,
        "dateModified": r.snapshot_at.isoformat(),
    }
    if wd:
        node["sameAs"] = wd
    agency = r.data.get("agency_en") or r.data.get("agency_ko")
    if agency:  # the verified artist -> 소속사 edge, citable by answer engines (the agency hub)
        node["recordLabel"] = {"@type": "Organization", "name": agency}
    if r.data.get("debut"):  # verified debut/formation -> citable "when did X debut?"
        node["foundingDate"] = r.data["debut"]
    members = r.data.get("members") or []
    if members:  # verified members -> citable "who is in X?" (schema.org MusicGroup.member)
        node["member"] = [{"@type": "Person", "name": m} for m in members]
    return node


def _escape_jsonld(doc: dict) -> str:
    # Escape <, >, & so a field value containing "</script>" (LLM/scraped prose) cannot break out
    # of the inline <script type="application/ld+json"> block and inject HTML into the public page.
    return (
        json.dumps(doc, ensure_ascii=False, indent=2)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )


def _jsonld(records: list, generated_iso: str, person_nodes: list | None = None) -> str:
    """Schema.org JSON-LD for the verified entities + people (AEO/GEO: crawlable, citable structure).

    Answer engines (Perplexity / ChatGPT / Google AI Overviews) parse JSON-LD; emitting each
    artist as a MusicGroup with `sameAs` the Wikidata entity (and each person as a Person with
    knownFor) makes our verified, dated records citable on the open web - the GEO substrate on top
    of the same append-only store.
    """
    groups = []
    seen: set[str] = set()
    for r in records:
        if r.entity_id in seen:
            continue
        seen.add(r.entity_id)
        groups.append(_entity_node(r))
    doc = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "Dataset",
                "name": "KoreaAPI — verified K-culture data",
                "description": (
                    "Bilingual, provenance-bearing Korean culture & commerce data for AI "
                    "agents; every record carries a source and a Skill Score."
                ),
                "dateModified": generated_iso,
                "creator": {"@type": "Organization", "name": "KoreaAPI"},
            },
            *groups,
            *(person_nodes or []),
        ],
    }
    return _escape_jsonld(doc)


def _report_row(entity_id: str, rec) -> str:
    """One verified entity as a homepage table row (links to its citable per-entity page)."""
    sc = rec.provenance.skill_score
    color = "#10B981" if sc >= 0.8 else ("#F59E0B" if sc >= 0.5 else "#EF4444")
    is_fresh = _fresh(rec.snapshot_at.isoformat(), rec.kind)
    agency_en = rec.data.get("agency_en") or rec.data.get("agency_ko") or ""
    agency_ko = rec.data.get("agency_ko") or ""
    cell = html.escape(agency_en)
    if agency_ko and agency_ko != agency_en:
        cell += f"<br><span class=ko>{html.escape(agency_ko)}</span>"
    slug = _slug(entity_id)
    return (
        "<tr>"
        f"<td><b><a href=\"artist/{slug}.html\">{html.escape(rec.name.en_official or rec.name.ko)}</a></b>"
        f"<br><span class=ko>{html.escape(rec.name.ko)}</span>"
        f"<br><span class=rom>{html.escape(rec.name.romanized or '')}</span></td>"
        f"<td>{cell}</td>"
        f"<td><span class=badge style=\"background:{color}\">{sc:.2f} {html.escape(rec.provenance.confidence)}</span></td>"
        f"<td class={'fresh' if is_fresh else 'stale'}>{'fresh' if is_fresh else 'STALE'}</td>"
        f"<td class=src>{html.escape('; '.join(rec.provenance.sources))}</td>"
        f"<td>{html.escape(rec.summary_en)}</td>"
        "</tr>"
    )


def _report_section(title: str, col2: str, items: list[tuple[str, object]]) -> str:
    """A per-vertical table section (empty -> omitted, e.g. when a deploy's pull found none)."""
    if not items:
        return ""
    rows = "".join(_report_row(eid, rec) for eid, rec in items)
    return (f"<h2 class=sec>{title}</h2><div class=tablewrap><table>"
            f"<tr><th>Name (EN / KO / rom)</th><th>{col2}</th><th>Skill Score</th>"
            f"<th>Fresh</th><th>Sources (provenance)</th><th>Summary (EN)</th></tr>"
            f"{rows}</table></div>")


async def report_html(db_path: str | None = None, out_path: str = "report.html") -> str:
    by_entity = await _load_by_entity(db_path=db_path)
    s = await stats(db_path=db_path)
    # Group the verified entities by vertical (facts/primary record), so the homepage reads as a
    # browsable catalogue (artists / dramas / films) instead of one undifferentiated table.
    groups: dict[str, list[tuple[str, object]]] = {ns: [] for ns in _VERTICALS}
    recs: list = []
    for entity_id, by_kind in by_entity.items():
        primary = by_kind.get("facts") or max(by_kind.values(), key=lambda r: r.provenance.skill_score)
        ns = _entity_kind(entity_id)
        if ns in groups:
            groups[ns].append((entity_id, primary))
            recs.append(primary)
    for g in groups.values():
        g.sort(key=lambda it: (it[1].name.en_official or it[1].name.ko).lower())

    # The person graph (hubs) — chips + Person JSON-LD nodes.
    people = _collect_credits(by_entity)
    linked = _linked_person_slugs(people, {_slug(e) for e in by_entity})
    ppl: list[tuple[str, str]] = []
    done: set[str] = set()
    for name, p in sorted(people.items(), key=lambda kv: -len(kv[1]["credits"])):
        if p["slug"] in linked and p["slug"] not in done:
            done.add(p["slug"])
            ppl.append((name, p["slug"]))
    person_nodes = [_person_node(name, people[name]["credits"]) for name, _s in ppl]
    people_block = ""
    if ppl:
        chips = "".join(f'<a class="pchip" href="person/{s}.html">{html.escape(n)}</a>' for n, s in ppl)
        people_block = f"<h2 class=sec>{_ICON['people']} Verified people ({len(ppl)})</h2><div class=pchips>{chips}</div>"

    # Labels & networks (the agency-hub axis) — chips to each /label/ hub.
    labels = _collect_labels(by_entity)
    lslugs = _label_slugs(labels)
    label_items = sorted(((L["name"], L["slug"], len(L["items"])) for L in labels.values()
                          if L["slug"] in lslugs), key=lambda x: -x[2])
    labels_block = ""
    if label_items:
        lchips = "".join(f'<a class="pchip" href="label/{s}.html">{html.escape(n)} ({c})</a>'
                         for n, s, c in label_items)
        labels_block = (f"<h2 class=sec>{_ICON['label']} Labels &amp; networks ({len(label_items)})</h2>"
                        f"<div class=pchips>{lchips}</div>")

    n_total = sum(len(g) for g in groups.values())  # all verified entities across verticals
    # one catalogue section per vertical (data-driven from _VERTICALS — adding a vertical needs no
    # edit here); the per-vertical count rides in each section header.
    sections = "".join(
        _report_section(f"{emoji} {label} ({len(groups[ns])})", col2, groups[ns])
        for ns, (label, _fname, emoji, col2) in _VERTICALS.items()
    ) + people_block + labels_block

    def _card(v: object, k: str) -> str:
        return f'<div class="card"><div class="v">{v}</div><div class="k">{k}</div></div>'

    cards_html = (
        _card(n_total, "verified entities")
        + "".join(_card(len(groups[ns]), label) for ns, (label, *_r) in _VERTICALS.items())
        + _card(len(ppl), "verified people")
        + _card(s.get("avg_skill_score", "-"), "avg Skill Score")
        + _card(s.get("fresh_entities", "-"), "fresh")
    )
    now = datetime.now(timezone.utc)
    generated = now.strftime("%Y-%m-%d %H:%M UTC")
    jsonld = _jsonld(recs, now.isoformat(), person_nodes)
    doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
{_FONT_LINKS}
<title>KoreaAPI — verifiable Korean-culture data for AI agents</title>
<meta name="description" content="KoreaAPI - verifiable, bilingual Korean culture data for AI agents. Every record carries its source and a Skill Score.">
<meta name="robots" content="index,follow">
<meta name="google-site-verification" content="rlCsGCeBa_AkOV4prHXu-OBEHu1HYcOwmJcpGPyWXFk">
<link rel="canonical" href="{_SITE_BASE}/">
<meta property="og:type" content="website">
<meta property="og:site_name" content="KoreaAPI">
<meta property="og:title" content="KoreaAPI — verifiable Korean-culture data for AI agents">
<meta property="og:description" content="Verifiable, bilingual Korean culture data (K-pop · K-drama · K-film) for AI agents &amp; answer engines. Every record carries its source + a Skill Score.">
<meta property="og:url" content="{_SITE_BASE}/">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="KoreaAPI — verifiable Korean-culture data for AI agents">
<meta name="twitter:description" content="K-pop · K-drama · K-film, cross-verified with provenance + Skill Score. Citable by any answer engine.">
<script type="application/ld+json">
{jsonld}
</script>
<style>{_AURORA}
 :root{{--bg:#0D0B06;--panel:#17120A;--panel2:#1E1710;--line:#3A2F1A;--ink:#F7F2E8;--mut:#C2B7A3;--dim:#8C8068;--accent:#E9C46A;--accent2:#D9A441;--ok:#10B981;--bad:#EF4444;
  --glass:linear-gradient(135deg,rgba(255,255,255,.08),rgba(255,255,255,.02));--gbord:rgba(255,255,255,.14);
  --blur:saturate(170%) blur(18px);
  --gshadow:0 14px 44px rgba(0,0,0,.55),0 2px 8px rgba(0,0,0,.35),inset 0 1.5px 0 rgba(255,255,255,.28),inset 0 0 0 1px rgba(255,255,255,.04),inset 0 -16px 30px rgba(6,10,22,.6)}}
 *{{box-sizing:border-box}}
 body{{font-family:'Montserrat','Apple SD Gothic Neo','Noto Sans KR','Malgun Gothic',system-ui,-apple-system,sans-serif;color:var(--ink);margin:0;padding:34px 20px 52px;line-height:1.5;
  background:
   radial-gradient(900px 520px at 10% -12%,rgba(233,196,106,.20),transparent 60%),
   radial-gradient(840px 480px at 102% -2%,rgba(217,164,65,.18),transparent 55%),
   radial-gradient(760px 620px at 50% 118%,rgba(233,196,106,.12),transparent 60%),
   radial-gradient(1100px 520px at 50% -160px,#241A06 0%,var(--bg) 58%);
  background-attachment:fixed}}
 .wrap{{max-width:1180px;margin:0 auto}}
 .brand{{display:flex;align-items:center;gap:11px}}
 .brand h1{{margin:0;font-size:30px;font-weight:800;letter-spacing:-.02em}}
 .dot{{width:11px;height:11px;border-radius:50%;background:linear-gradient(135deg,var(--accent),var(--accent2));box-shadow:0 0 14px rgba(233,196,106,.6)}}
 .tag{{color:var(--mut);margin:11px 0 18px;font-size:15px;max-width:780px}}
 .pills{{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:16px}}
 .pill{{background:var(--glass);backdrop-filter:var(--blur);-webkit-backdrop-filter:var(--blur);border:1px solid var(--gbord);border-radius:999px;padding:7px 14px;font-size:13px;font-weight:600;color:var(--ink);box-shadow:0 6px 18px rgba(0,0,0,.4),inset 0 1px 0 rgba(255,255,255,.28)}}
 .pill:hover{{border-color:var(--accent);color:var(--accent);text-decoration:none;transform:translateY(-1px)}}
 .chips{{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:22px}}
 .chip{{font-size:12px;color:var(--mut);background:var(--glass);backdrop-filter:var(--blur);-webkit-backdrop-filter:var(--blur);border:1px solid var(--gbord);border-radius:10px;padding:7px 12px;box-shadow:0 6px 18px rgba(0,0,0,.4),inset 0 1px 0 rgba(255,255,255,.22)}}
 .chip b{{color:var(--ink)}}
 .note{{color:var(--mut);font-size:13px;line-height:1.65;background:var(--glass);backdrop-filter:var(--blur);-webkit-backdrop-filter:var(--blur);border:1px solid var(--gbord);border-left:3px solid var(--accent);border-radius:14px;padding:15px 18px;margin-bottom:24px;max-width:1000px;box-shadow:var(--gshadow)}}
 .note b{{color:var(--ink)}}
 code{{background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.10);padding:1px 6px;border-radius:5px;font-size:12px}}
 .cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(148px,1fr));gap:14px;margin-bottom:24px}}
 .card{{background:var(--glass);backdrop-filter:var(--blur);-webkit-backdrop-filter:var(--blur);border:1px solid var(--gbord);border-radius:18px;padding:18px 20px;box-shadow:var(--gshadow)}}
 .card .v{{font-size:28px;font-weight:800;letter-spacing:-.02em}}
 .card .k{{color:var(--mut);font-size:12px;margin-top:3px}}
 .tablewrap{{overflow:hidden;overflow-x:auto;border:1px solid var(--gbord);border-radius:18px;background:var(--glass);backdrop-filter:var(--blur);-webkit-backdrop-filter:var(--blur);box-shadow:var(--gshadow)}}
 table{{width:100%;border-collapse:collapse;min-width:900px;background:transparent}}
 th,td{{padding:13px 14px;text-align:left;font-size:13px;vertical-align:top;border-bottom:1px solid rgba(255,255,255,.08)}}
 th{{color:var(--mut);font-weight:600;background:rgba(255,255,255,.06);font-size:11px;text-transform:uppercase;letter-spacing:.04em}}
 tbody tr:last-child td{{border-bottom:none}}
 tbody tr:hover{{background:rgba(255,255,255,.06)}}
 td b a{{color:var(--ink);font-weight:700}} td b a:hover{{color:var(--accent)}}
 .ko{{color:var(--mut)}} .rom{{color:var(--dim);font-size:11px}}
 .badge{{color:#06140E;font-weight:800;padding:3px 9px;border-radius:6px;font-size:12px;white-space:nowrap}}
 .fresh{{color:var(--ok);font-weight:700}} .stale{{color:var(--bad);font-weight:800}}
 .src{{color:var(--mut);font-size:12px;max-width:230px}}
 a{{color:var(--accent);text-decoration:none}} a:hover{{text-decoration:underline}}
 h2.sec{{font-size:18px;font-weight:800;letter-spacing:-.01em;margin:30px 0 12px}}
 .pchips{{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:8px}}
 .pchip{{background:var(--glass);backdrop-filter:var(--blur);-webkit-backdrop-filter:var(--blur);border:1px solid var(--gbord);border-radius:10px;padding:7px 12px;font-size:13px;font-weight:600;color:var(--ink);box-shadow:0 6px 16px rgba(0,0,0,.38),inset 0 1px 0 rgba(255,255,255,.22)}}
 .pchip:hover{{border-color:var(--accent);color:var(--accent);text-decoration:none;transform:translateY(-1px)}}
 footer{{color:var(--dim);margin-top:24px;font-size:12px;line-height:1.7}}
</style></head><body><div class="wrap">
<div class="brand"><span class="dot"></span><h1>KoreaAPI</h1></div>
<div class="tag">The verifiable data layer for Korean culture — callable by any AI agent (MCP), citable by any answer engine.</div>
<div class="pills">
 <a class="pill" href="./artists.html">{_ICON['artist']} Artists</a>
 <a class="pill" href="./dramas.html">{_ICON['drama']} K-dramas</a>
 <a class="pill" href="./films.html">{_ICON['film']} K-films</a>
 <a class="pill" href="./webtoons.html">{_ICON['webtoon']} Webtoons</a>
 <a class="pill" href="./places.html">{_ICON['place']} Places</a>
 <a class="pill" href="./food.html">{_ICON['food']} Food</a>
 <a class="pill" href="./companies.html">{_ICON['company']} Companies</a>
 <a class="pill" href="./brands.html">{_ICON['brand']} Brands</a>
 <a class="pill" href="./books.html">{_ICON['book']} Books</a>
 <a class="pill" href="./history.html">{_ICON['history']} History</a>
 <a class="pill" href="./heritage.html">{_ICON['heritage']} Heritage</a>
 <a class="pill" href="./folklore.html">{_ICON['folklore']} Folklore</a>
 <a class="pill" href="./medical.html">{_ICON['medical']} Medical</a>
 <a class="pill" href="./regions.html">{_ICON['region']} Regions</a>
 <a class="pill" href="./games.html">{_ICON['game']} Games</a>
 <a class="pill" href="./shows.html">{_ICON['show']} Variety</a>
 <a class="pill" href="./animation.html">{_ICON['animation']} Animation</a>
 <a class="pill" href="./universities.html">{_ICON['university']} Universities</a>
 <a class="pill" href="./classics.html">{_ICON['classic']} Classics</a>
 <a class="pill" href="./people.html">{_ICON['people']} People</a>
 <a class="pill" href="./latest.json">/latest.json · open data</a>
 <a class="pill" href="./llms.txt">/llms.txt · agent index</a>
 <a class="pill" href="./korea-rising.md">/korea-rising.md · digest</a>
 <a class="pill" href="https://github.com/kwangdol-star/koreaapi">GitHub</a>
</div>
<div class="chips">
 <span class="chip"><b>Cross-verified</b> · Wikidata + Wikipedia agree</span>
 <span class="chip"><b>Provenance</b> + <b>Skill Score</b> on every record</span>
 <span class="chip"><b>Hallucination-guarded</b></span>
 <span class="chip"><b>Bilingual</b> · KO / EN / romanized</span>
</div>
<div class="note">Every row is <b>verified</b> — cross-checked across independent sources (Wikidata + Wikipedia), identity- and hallucination-guarded, stamped with a transparent <b>Skill Score</b> + <b>provenance</b>, and anchored to its <b>소속사 (agency)</b>. <b>Agents</b> call 7 MCP tools (<code>get_artist_status</code>, <code>get_agency</code>, <code>get_kculture_calendar</code>, <code>get_korea_rising</code>, <code>get_person</code>, <code>get_related</code>, <code>get_buy_options</code>); <b>answer engines</b> get Schema.org JSON-LD + <a href="./llms.txt">/llms.txt</a>. <b>Cite a row as:</b> &ldquo;Name — kind, as of date · source · Skill Score · via KoreaAPI&rdquo;.</div>
<div class="cards">{cards_html}</div>
{sections}
<footer>Generated {generated} · KoreaAPI Phase 1 (cold-start) · verifiable Korean-culture data for AI agents · <a href="./latest.json">/latest.json</a> · <a href="./llms.txt">/llms.txt</a> · <a href="https://github.com/kwangdol-star/koreaapi">GitHub</a></footer>
</div></body></html>"""
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(doc)
    return out_path


_SITE_BASE = "https://kwangdol-star.github.io/koreaapi"

# Brand typography: Montserrat for Latin/headings (loaded from Google Fonts), with system Korean
# fonts as the fallback for Hangul (Montserrat has no Korean glyphs) — consistent brand, no heavy
# Korean webfont. `_FONT_LINKS` goes in every page <head>; `_FONT_STACK` in every body font-family.
_FONT_LINKS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600;700;800&display=swap" rel="stylesheet">'
)
_FONT_STACK = "'Montserrat','Apple SD Gothic Neo','Noto Sans KR','Malgun Gothic',system-ui,-apple-system,sans-serif"

# Background animation removed (was too heavy) — kept the static gold + glass look. `_AURORA` is
# still injected into every <style> block; empty string = no animated layer. To bring motion back,
# put a `@keyframes ... body::before{...}` string here.
_AURORA = ""

# Clean line (stroke) SVG icons — replace the emoji glyphs in section/hub/pill labels. Gold stroke,
# currentColor-free so they read consistently on any surface. Sized in em; vertical-aligned inline.
def _icon(paths: str) -> str:
    return ('<svg viewBox="0 0 24 24" width="1.05em" height="1.05em" fill="none" stroke="#E9C46A" '
            'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" '
            'style="vertical-align:-0.16em;margin-right:.1em">' + paths + "</svg>")


_ICON = {
    # microphone (artists)
    "artist": _icon('<rect x="9" y="2" width="6" height="11" rx="3"/><path d="M5 10a7 7 0 0 0 14 0"/>'
                    '<line x1="12" y1="17" x2="12" y2="21"/><line x1="8" y1="21" x2="16" y2="21"/>'),
    # tv / screen (dramas)
    "drama": _icon('<rect x="2" y="4" width="20" height="14" rx="2"/>'
                   '<polyline points="8 21 12 18 16 21"/>'),
    # film strip (films)
    "film": _icon('<rect x="3" y="4" width="18" height="16" rx="2"/><line x1="7" y1="4" x2="7" y2="20"/>'
                  '<line x1="17" y1="4" x2="17" y2="20"/><line x1="3" y1="9" x2="7" y2="9"/>'
                  '<line x1="3" y1="14" x2="7" y2="14"/><line x1="17" y1="9" x2="21" y2="9"/>'
                  '<line x1="17" y1="14" x2="21" y2="14"/>'),
    # person (people)
    "people": _icon('<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>'),
    # tag (labels / agencies / networks)
    "label": _icon('<path d="M20.6 13.4 13.4 20.6a2 2 0 0 1-2.8 0l-7-7A2 2 0 0 1 3 12.2V5a2 2 0 0 1 '
                   '2-2h7.2a2 2 0 0 1 1.4.6l7 7a2 2 0 0 1 0 2.8z"/><circle cx="7.6" cy="7.6" r="1.3"/>'),
    # open book (webtoons)
    "webtoon": _icon('<path d="M3 5a2 2 0 0 1 2-2h6v16H5a2 2 0 0 0-2 2z"/>'
                     '<path d="M21 5a2 2 0 0 0-2-2h-6v16h6a2 2 0 0 1 2 2z"/>'),
    # map pin (places / travel)
    "place": _icon('<path d="M12 21s-7-6.3-7-11a7 7 0 0 1 14 0c0 4.7-7 11-7 11z"/>'
                   '<circle cx="12" cy="10" r="2.5"/>'),
    # steaming bowl (Korean food)
    "food": _icon('<path d="M3 11h18a9 9 0 0 1-9 9 9 9 0 0 1-9-9z"/>'
                  '<path d="M8 4c0 1-1 1-1 2s1 1 1 2M12 3c0 1-1 1-1 2s1 1 1 2M16 4c0 1-1 1-1 2s1 1 1 2"/>'),
    # building (companies)
    "company": _icon('<rect x="3" y="3" width="12" height="18" rx="1"/>'
                     '<path d="M15 9h5a1 1 0 0 1 1 1v11h-6"/><line x1="7" y1="7" x2="11" y2="7"/>'
                     '<line x1="7" y1="11" x2="11" y2="11"/><line x1="7" y1="15" x2="11" y2="15"/>'),
    # sparkle (brands / K-beauty)
    "brand": _icon('<path d="M12 3l1.9 4.8L18.7 9.7l-4.8 1.9L12 16.4l-1.9-4.8L5.3 9.7l4.8-1.9z"/>'
                   '<path d="M19 14l.7 1.8 1.8.7-1.8.7-.7 1.8-.7-1.8-1.8-.7 1.8-.7z"/>'),
    # closed book (literature)
    "book": _icon('<path d="M5 4a2 2 0 0 1 2-2h12v18H7a2 2 0 0 0-2 2z"/><path d="M5 20a2 2 0 0 1 2-2h12"/>'),
    # column / pillar (history)
    "history": _icon('<path d="M3 21h18"/><path d="M5 21V9l7-5 7 5v12"/>'
                     '<line x1="9" y1="21" x2="9" y2="13"/><line x1="15" y1="21" x2="15" y2="13"/>'),
    # gem / treasure (heritage & traditional arts)
    "heritage": _icon('<path d="M6 3h12l3 6-9 12L3 9z"/><path d="M3 9h18"/>'
                      '<path d="M9 3 6 9l6 12 6-12-3-6"/>'),
    # ghost (folklore / myth / the supernatural)
    "folklore": _icon('<path d="M5 21V10a7 7 0 0 1 14 0v11l-2.5-1.6L14 21l-2-1.6L10 21l-2.5-1.6z"/>'
                      '<circle cx="9.5" cy="10" r="1"/><circle cx="14.5" cy="10" r="1"/>'),
    # medical cross (hospitals / medical centers)
    "medical": _icon('<rect x="3" y="3" width="18" height="18" rx="3"/>'
                     '<line x1="12" y1="8" x2="12" y2="16"/><line x1="8" y1="12" x2="16" y2="12"/>'),
    # globe (Korea & regions)
    "region": _icon('<circle cx="12" cy="12" r="9"/><line x1="3" y1="12" x2="21" y2="12"/>'
                    '<path d="M12 3a15 15 0 0 1 0 18a15 15 0 0 1 0-18z"/>'),
    # gamepad (Korean games)
    "game": _icon('<rect x="2" y="7" width="20" height="10" rx="5"/><line x1="6" y1="12" x2="8" y2="12"/>'
                  '<line x1="7" y1="11" x2="7" y2="13"/><circle cx="16" cy="11.5" r="1"/>'
                  '<circle cx="18.5" cy="13.5" r="1"/>'),
    # tv + play (variety / broadcast)
    "show": _icon('<rect x="2" y="5" width="20" height="14" rx="2"/><polygon points="10 9 16 12 10 15"/>'),
    # overlapping frame + play (animation)
    "animation": _icon('<rect x="3" y="7" width="13" height="12" rx="1.5"/><path d="M8 7V4h13v12h-3"/>'
                       '<polygon points="8 11 12.5 13.5 8 16"/>'),
    # mortarboard (universities / education)
    "university": _icon('<path d="M12 4 2 9l10 5 10-5-10-5z"/>'
                        '<path d="M6 11v5c0 1.2 2.7 2.5 6 2.5s6-1.3 6-2.5v-5"/><line x1="22" y1="9.5" x2="22" y2="14"/>'),
    # document / record (classics & historical texts)
    "classic": _icon('<path d="M6 3h9l4 4v12a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z"/>'
                     '<polyline points="15 3 15 7 19 7"/><line x1="8" y1="12" x2="15" y2="12"/>'
                     '<line x1="8" y1="16" x2="13" y2="16"/>'),
}

_ENTITY_STYLE = _FONT_LINKS + "<style>" + _AURORA + """
 :root{--glass:linear-gradient(135deg,rgba(255,255,255,.08),rgba(255,255,255,.02));--gbord:rgba(255,255,255,.14);--blur:saturate(170%) blur(18px);--gshadow:0 14px 44px rgba(0,0,0,.55),0 2px 8px rgba(0,0,0,.35),inset 0 1.5px 0 rgba(255,255,255,.26),inset 0 0 0 1px rgba(255,255,255,.04),inset 0 -16px 30px rgba(6,10,22,.6)}
 body{font-family:'Montserrat','Apple SD Gothic Neo','Noto Sans KR','Malgun Gothic',system-ui,-apple-system,sans-serif;color:#F7F2E8;margin:0 auto;padding:34px 22px 48px;line-height:1.55;max-width:860px;
  background:
   radial-gradient(760px 440px at 0% -8%,rgba(233,196,106,.20),transparent 60%),
   radial-gradient(720px 420px at 100% 0%,rgba(217,164,65,.18),transparent 55%),
   radial-gradient(900px 520px at 50% 120%,rgba(233,196,106,.10),transparent 60%),
   radial-gradient(1000px 480px at 50% -160px,#241A06 0%,#0D0B06 60%);background-attachment:fixed}
 a{color:#E9C46A;text-decoration:none} a:hover{text-decoration:underline}
 h1{margin:0;font-size:27px;font-weight:800;letter-spacing:-.02em} h2{margin:24px 0 9px;font-size:14px;color:#C2B7A3;text-transform:uppercase;letter-spacing:.04em}
 .ko{color:#C2B7A3;font-weight:400} .rom{color:#8C8068;font-size:12px}
 .sub{color:#C2B7A3;margin:6px 0 8px;font-size:13px}
 ul{padding-left:18px} li{margin:5px 0}
 .people{list-style:none;padding:0;display:flex;flex-wrap:wrap;gap:8px}
 .people li{margin:0;background:var(--glass);backdrop-filter:var(--blur);-webkit-backdrop-filter:var(--blur);border:1px solid var(--gbord);border-radius:10px;padding:6px 11px;font-size:13px;box-shadow:0 6px 16px rgba(0,0,0,.38),inset 0 1px 0 rgba(255,255,255,.20)}
 .people li a{color:#E9C46A}
 .qa{background:var(--glass);backdrop-filter:var(--blur);-webkit-backdrop-filter:var(--blur);border:1px solid var(--gbord);border-radius:14px;padding:12px 16px;margin:9px 0;box-shadow:var(--gshadow)}
 .qa .q{font-weight:700} .qa .a{color:#E0D7C6;margin-top:3px;font-size:14px}
 .cite{background:linear-gradient(135deg,rgba(233,196,106,.16),rgba(255,255,255,.02));backdrop-filter:var(--blur);-webkit-backdrop-filter:var(--blur);border:1px solid rgba(233,196,106,.35);border-radius:14px;padding:12px 16px;margin:18px 0;font-size:13px;box-shadow:var(--gshadow)}
 .back{font-size:13px;margin:0 0 12px} footer{color:#8C8068;margin-top:20px;font-size:12px}
</style>"""


def _slug(entity_id: str) -> str:
    """`artist:bts` -> `bts` (stable, semantic per-entity URL slug)."""
    raw = entity_id.split(":", 1)[-1].lower()
    return "".join(c if (c.isalnum() or c in "-_") else "-" for c in raw).strip("-") or "entity"


def _person_slug(name: str) -> str:
    """A person name -> a stable URL slug: 'Bong Joon-ho' -> 'bong-joon-ho'. Comparable to _slug
    so a person who is ALSO a tracked entity (a soloist) resolves to the same slug."""
    return "".join(c if (c.isalnum() or c in "-_") else "-" for c in name.lower()).strip("-") or "person"


# --- Person / credit knowledge graph -----------------------------------------------------------
# The verified store already carries each work's people (members P527 / cast P161 / director P57),
# resolved to names. Pivoting those edges by PERSON turns a flat list into a navigable graph: a
# director becomes a hub linking the films they made (Bong Joon-ho -> Parasite, Memories of Murder,
# ...), which is exactly the internal-link + entity structure answer engines reward. Pure aggregation
# over ALREADY-verified records — no new fetch, no new trust surface (provenance = the works' own).

_ROLE_TYPE = {"film": "Movie", "drama": "TVSeries", "artist": "MusicGroup", "webtoon": "ComicSeries"}


def _entity_kind(entity_id: str) -> str:
    return entity_id.split(":", 1)[0]  # "artist" | "drama" | "film"


def _collect_credits(by_entity: dict) -> dict:
    """Pure: pivot verified works by person -> {name: {slug, credits:[{entity_id, work_name,
    work_slug, role, kind, sources, asof}]}}. role: 'member' (artist) / 'cast' (drama·film) /
    'director'. Names come straight from the works' verified data (no new claims)."""
    people: dict[str, dict] = {}

    def add(name: str, rec, role: str) -> None:
        name = (name or "").strip()
        if not name:
            return
        p = people.setdefault(name, {"slug": _person_slug(name), "credits": []})
        p["credits"].append({
            "entity_id": rec.entity_id,
            "work_name": rec.name.en_official or rec.name.ko,
            "work_slug": _slug(rec.entity_id),
            "role": role,
            "kind": _entity_kind(rec.entity_id),
            "sources": list(rec.provenance.sources),
            "asof": rec.snapshot_at.strftime("%Y-%m-%d"),
        })

    for entity_id, by_kind in by_entity.items():
        rec = by_kind.get("facts")
        if rec is None:
            continue
        member_role = ("creator" if entity_id.startswith("webtoon:")
                       else "author" if entity_id.startswith(("book:", "classic:"))
                       else "cast" if entity_id.startswith(("drama:", "film:", "show:")) else "member")
        for nm in (rec.data.get("members") or []):
            add(nm, rec, member_role)
        for nm in (rec.data.get("directors") or []):
            add(nm, rec, "director")
    return people


def _qualifies_for_person_page(credits: list[dict]) -> bool:
    """Who earns a standalone citable page: a director (a prominent cross-work hub even with one
    film) OR anyone credited in ≥2 verified works (the graph's connective tissue). A one-work cast
    member stays a plain name on the work page — avoids a long tail of thin, duplicative pages."""
    return any(c["role"] == "director" for c in credits) or len(credits) >= 2


def _linked_person_slugs(people: dict, entity_slugs: set) -> set:
    """Slugs that get a person page: qualifying, ASCII-sluggable (clean URL / valid sitemap), and
    NOT already a tracked entity (a soloist links to their own entity page instead)."""
    return {
        p["slug"]
        for p in people.values()
        if _qualifies_for_person_page(p["credits"])
        and p["slug"].isascii()
        and p["slug"] not in entity_slugs
    }


def _credit_link(name: str, entity_slugs: set, linked: set) -> str:
    """Render a person's name as a link to their entity page (if they're tracked), else their person
    page (if it exists), else plain escaped text. Emitted only from pages one level under site/
    (site/artist/, site/person/), so the `../artist/` and `../person/` relative paths resolve."""
    s = _person_slug(name)
    label = html.escape(name)
    if s in entity_slugs:
        return f'<a href="../artist/{s}.html">{label}</a>'
    if s in linked:
        return f'<a href="../person/{s}.html">{label}</a>'
    return label


def _collaborators(name: str, credits: list[dict], work_people: dict, linked_names: set) -> list[tuple]:
    """The person↔person graph edge: other LINKED people who share a verified work with `name`.
    Pure. Returns [(collab_name, slug, [shared work_names])] sorted by #shared works desc, then name."""
    shared: dict[str, set] = {}
    for c in credits:
        for other in work_people.get(c["work_slug"], ()):
            if other == name or other not in linked_names:
                continue
            shared.setdefault(other, set()).add(c["work_name"])
    return [(o, _person_slug(o), sorted(w))
            for o, w in sorted(shared.items(), key=lambda kv: (-len(kv[1]), kv[0]))]


def _person_node(name: str, credits: list[dict], collaborators: list | None = None) -> dict:
    """Schema.org Person with `knownFor` the verified works (each linked) + `colleague` the verified
    collaborators — a citable node tying a person to their cross-verified works AND co-workers."""
    known = [
        {"@type": _ROLE_TYPE.get(c["kind"], "CreativeWork"), "name": c["work_name"],
         "url": f"{_SITE_BASE}/artist/{c['work_slug']}.html"}
        for c in credits
    ]
    node = {"@type": "Person", "name": name, "knownFor": known}
    if collaborators:
        node["colleague"] = [{"@type": "Person", "name": o, "url": f"{_SITE_BASE}/person/{s}.html"}
                             for o, s, _w in collaborators]
    return node


def _person_qa(name: str, credits: list[dict], collaborators: list | None = None) -> list[tuple[str, str]]:
    """Answer-shaped Q&A for a person, grouped by role — emitted visibly AND as FAQPage JSON-LD."""
    src = "; ".join(sorted({s for c in credits for s in c["sources"]}))
    qas: list[tuple[str, str]] = []

    def names(role: str) -> list[str]:
        return [c["work_name"] for c in credits if c["role"] == role]

    directed, acted, member = names("director"), names("cast"), names("member")
    created, authored = names("creator"), names("author")
    if directed:
        qas.append((f"What did {name} direct?",
                    f"{name} directed {', '.join(directed)} (verified via {src})."))
    if acted:
        qas.append((f"What is {name} known for acting in?",
                    f"{name} appears in {', '.join(acted)} (verified via {src})."))
    if created:
        qas.append((f"What did {name} create?",
                    f"{name} created {', '.join(created)} (verified via {src})."))
    if authored:
        qas.append((f"What did {name} write?",
                    f"{name} wrote {', '.join(authored)} (verified via {src})."))
    if member:
        qas.append((f"What group is {name} in?",
                    f"{name} is a member of {', '.join(member)} (verified via {src})."))
    if collaborators:
        parts = [f"{o} (on {', '.join(w)})" for o, _s, w in collaborators[:8]]
        qas.append((f"Who has {name} worked with?",
                    f"{name} shares verified works with {', '.join(parts)} (via {src})."))
    return qas


def _related(entity_id: str, primary, by_entity: dict, *, limit: int = 8) -> list[tuple[str, str]]:
    """Verified hub edges to OTHER entities: artists sharing a 소속사, or videos sharing a network/
    platform (the same P264/P449 value). Returns [(name, slug)] — the internal-link graph crawlers
    and answer engines follow from one verified node to its neighbours."""
    key = (primary.data.get("agency_en") or primary.data.get("agency_ko") or "").strip().lower()
    if not key:
        return []
    is_artist = entity_id.startswith("artist:")
    out: list[tuple[str, str]] = []
    for oid, by_kind in by_entity.items():
        if oid == entity_id or oid.startswith("artist:") != is_artist:
            continue  # keep "related" within the same family (artist↔artist, video↔video)
        r = by_kind.get("facts")
        if r is None:
            continue
        okey = (r.data.get("agency_en") or r.data.get("agency_ko") or "").strip().lower()
        if okey and okey == key:
            out.append((r.name.en_official or r.name.ko, _slug(oid)))
    return sorted(out)[:limit]


def _entity_qa(name: str, primary, by_kind: dict) -> list[tuple[str, str]]:
    """Answer-shaped (question, plain-text answer) pairs from verified data — the FAQ an agent asks.

    Rendered visibly AND emitted as FAQPage JSON-LD so an answer engine can extract a cited answer.
    """
    qas: list[tuple[str, str]] = []
    d = primary.data if primary else {}
    asof = primary.snapshot_at.strftime("%Y-%m-%d") if primary else ""
    src = "; ".join(primary.provenance.sources) if primary else ""
    eid0 = primary.entity_id if primary else ""
    _whatis = {  # name-anchored verticals (no people/agency edge) lead with a "what is it" answer
        "food": "a verified Korean dish/food",
        "history": "a verified part of Korean history (dynasty / period / event)",
        "heritage": "a verified Korean cultural heritage / traditional art",
        "folklore": "a verified Korean folktale / myth",
        "region": "a verified South Korean region (the country or a first-level administrative division)",
    }
    if _entity_kind(eid0) in _whatis:
        ko = (primary.name.ko if primary else "") or ""
        ko_part = f" ({ko})" if ko and ko != name else ""
        qas.append((f"What is {name}?",
                    f"{name}{ko_part} is {_whatis[_entity_kind(eid0)]} (cross-checked via {src}, as of {asof})."))
    if _entity_kind(eid0) == "region":  # stable infobox facts -> citable Q&A (capital / language / …)
        cap = d.get("capital_en") or d.get("capital_ko")
        if cap:
            qas.append((f"What is the capital of {name}?",
                        f"The capital of {name} is {cap} (verified via {src}, as of {asof})."))
        lang = d.get("language_en") or d.get("language_ko")
        if lang:
            qas.append((f"What is the official language of {name}?",
                        f"The official language of {name} is {lang} (verified via {src}, as of {asof})."))
        cur = d.get("currency_en") or d.get("currency_ko")
        if cur:
            qas.append((f"What currency does {name} use?",
                        f"{name} uses the {cur} (verified via {src}, as of {asof})."))
        codes = ([f"ISO 3166-1 code {d['iso_code']}"] if d.get("iso_code") else []) + \
                ([f"calling code {d['calling_code']}"] if d.get("calling_code") else [])
        if codes:
            qas.append((f"What is the country code of {name}?",
                        f"{name}: {', '.join(codes)} (verified via {src}, as of {asof})."))
    if d.get("debut"):
        eid = primary.entity_id if primary else ""
        if eid.startswith("film:"):
            qas.append((f"When was {name} released?",
                        f"{name} was released in {d['debut']} (verified via {src}, as of {asof})."))
        elif eid.startswith("place:"):
            qas.append((f"When was {name} built or established?",
                        f"{name} dates to {d['debut']} (verified via {src}, as of {asof})."))
        elif eid.startswith("company:"):
            qas.append((f"When was {name} founded?",
                        f"{name} was founded in {d['debut']} (verified via {src}, as of {asof})."))
        elif eid.startswith("medical:"):
            qas.append((f"When was {name} founded?",
                        f"{name} was founded in {d['debut']} (verified via {src}, as of {asof})."))
        elif eid.startswith("brand:"):
            qas.append((f"When was {name} established?",
                        f"{name} was established in {d['debut']} (verified via {src}, as of {asof})."))
        elif eid.startswith(("book:", "classic:")):
            qas.append((f"When was {name} published?",
                        f"{name} was published in {d['debut']} (verified via {src}, as of {asof})."))
        elif eid.startswith("game:"):
            qas.append((f"When was {name} released?",
                        f"{name} was released in {d['debut']} (verified via {src}, as of {asof})."))
        elif eid.startswith("animation:"):
            qas.append((f"When was {name} first released?",
                        f"{name} was first released in {d['debut']} (verified via {src}, as of {asof})."))
        elif eid.startswith("university:"):
            qas.append((f"When was {name} founded?",
                        f"{name} was founded in {d['debut']} (verified via {src}, as of {asof})."))
        elif eid.startswith("history:"):
            qas.append((f"When did {name} begin?",
                        f"{name} began in {d['debut']} (verified via {src}, as of {asof})."))
        elif eid.startswith(("drama:", "show:")):
            qas.append((f"When did {name} first air?",
                        f"{name} first aired in {d['debut']} (verified via {src}, as of {asof})."))
        elif eid.startswith("webtoon:"):
            qas.append((f"When was {name} first published?",
                        f"{name} was first published in {d['debut']} (verified via {src}, as of {asof})."))
        else:
            qas.append((f"When did {name} debut?",
                        f"{name} debuted/formed on {d['debut']} (verified via {src}, as of {asof})."))
    members = d.get("members") or []
    if members:
        eid = primary.entity_id if primary else ""
        if eid.startswith(("drama:", "film:", "show:")):
            qas.append((f"Who stars in {name}?",
                        f"Cast includes {', '.join(members)} (verified via {src}, as of {asof})."))
        elif eid.startswith("webtoon:"):
            qas.append((f"Who created {name}?",
                        f"{name} was created by {', '.join(members)} (verified via {src}, as of {asof})."))
        elif eid.startswith(("book:", "classic:")):
            qas.append((f"Who wrote {name}?",
                        f"{name} was written by {', '.join(members)} (verified via {src}, as of {asof})."))
        else:
            qas.append((f"Who are the members of {name}?",
                        f"{', '.join(members)} — {len(members)} members (verified via {src}, as of {asof})."))
    directors = d.get("directors") or []
    if directors:  # drama/film only (artists/webtoons carry none)
        qas.append((f"Who directed {name}?",
                    f"{name} was directed by {', '.join(directors)} (verified via {src}, as of {asof})."))
    agency = d.get("agency_en") or d.get("agency_ko")
    if agency:
        eid = primary.entity_id if primary else ""
        if eid.startswith(("drama:", "film:", "show:")):
            qas.append((f"What network or platform is {name} on?",
                        f"{name} — original network/platform: {agency} (verified via {src}, as of {asof})."))
        elif eid.startswith("webtoon:"):
            qas.append((f"What platform is {name} on?",
                        f"{name} — publisher/platform: {agency} (verified via {src}, as of {asof})."))
        elif eid.startswith(("place:", "medical:", "university:")):
            qas.append((f"Where is {name}?",
                        f"{name} is located in {agency} (verified via {src}, as of {asof})."))
        elif eid.startswith("company:"):
            qas.append((f"What industry is {name} in?",
                        f"{name} operates in {agency} (verified via {src}, as of {asof})."))
        elif eid.startswith("brand:"):
            qas.append((f"Who owns {name}?",
                        f"{name} is owned by {agency} (verified via {src}, as of {asof})."))
        elif eid.startswith("book:"):
            qas.append((f"Who published {name}?",
                        f"{name} was published by {agency} (verified via {src}, as of {asof})."))
        elif eid.startswith("game:"):
            qas.append((f"Who developed {name}?",
                        f"{name} was developed by {agency} (verified via {src}, as of {asof})."))
        elif eid.startswith("animation:"):
            qas.append((f"Who produced {name}?",
                        f"{name} was produced by {agency} (verified via {src}, as of {asof})."))
        else:
            ag = agency + (f" ({d['agency_ko']})" if d.get("agency_ko") and d["agency_ko"] != agency else "")
            qas.append((f"What agency (소속사) is {name} under?",
                        f"{name} is under {ag} (verified via {src}, as of {asof})."))
    geo = d.get("geo") or {}
    if geo.get("lat") is not None:  # verified coordinates (P625)
        qas.append((f"What are the coordinates of {name}?",
                    f"{name} is located at {geo['lat']}, {geo['lon']} (verified via {src}, as of {asof})."))
    if d.get("spice_level"):  # editorial spice rating (clearly attributed)
        qas.append((f"Is {name} spicy?",
                    f"{name} is rated '{d['spice_level']}' on KoreaAPI's spice scale "
                    f"(editorial rating; the dish name is cross-verified via {src})."))
    if d.get("diet"):  # editorial dietary note (clearly attributed)
        qas.append((f"Is {name} vegetarian?",
                    f"{name} — dietary note: {d['diet']} (KoreaAPI editorial; the dish name is "
                    f"cross-verified via {src})."))
    for k, v in (d.get("attrs") or {}).items():  # per-vertical structured attrs -> citable Q&A
        qas.append((f"What is {name}'s {k.lower()}?",
                    f"{name} — {k}: {v} (verified via {src}, as of {asof})."))
    for kind, rec in by_kind.items():  # fresh current-state Q — the answer an LLM's training set can't have
        if kind == "facts":
            continue
        q = (f"What is {name}'s latest release / current status?" if kind == "release"
             else f"What is {name}'s current {kind}?")
        qas.append((q, f"{rec.summary_en} (as of {rec.snapshot_at.strftime('%Y-%m-%d')}, "
                       f"via {'; '.join(rec.provenance.sources)})."))
    return qas


def _faqpage_node(qas: list[tuple[str, str]]) -> dict:
    return {
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
            for q, a in qas
        ],
    }


def _breadcrumb(name: str, url: str, *, middle: tuple[str, str] | None = None) -> dict:
    """BreadcrumbList (Home [> vertical] > current) — answer engines surface breadcrumbs in results."""
    items = [{"@type": "ListItem", "position": 1, "name": "KoreaAPI", "item": f"{_SITE_BASE}/"}]
    if middle:
        items.append({"@type": "ListItem", "position": 2, "name": middle[0], "item": middle[1]})
    items.append({"@type": "ListItem", "position": len(items) + 1, "name": name, "item": url})
    return {"@type": "BreadcrumbList", "itemListElement": items}


def _social_meta(title: str, desc: str, url: str, og_type: str = "website") -> str:
    """Open Graph + Twitter card tags (richer link previews when a page is shared / cited). `title`
    and `desc` must already be HTML-attribute-escaped by the caller (html.escape, quote=True)."""
    return (
        f'<meta property="og:type" content="{og_type}">'
        f'<meta property="og:site_name" content="KoreaAPI">'
        f'<meta property="og:title" content="{title}">'
        f'<meta property="og:description" content="{desc}">'
        f'<meta property="og:url" content="{url}">'
        f'<meta name="twitter:card" content="summary">'
        f'<meta name="twitter:title" content="{title}">'
        f'<meta name="twitter:description" content="{desc}">'
    )


def _write_entity_html(out_dir: str, slug: str, url: str, primary, by_kind: dict,
                       qas: list[tuple[str, str]], jsonld: str, *,
                       entity_slugs: set | None = None, linked: set | None = None,
                       related: list[tuple[str, str]] | None = None,
                       label_url: str | None = None) -> None:
    entity_slugs, linked, related = entity_slugs or set(), linked or set(), related or []
    asof = primary.snapshot_at.strftime("%Y-%m-%d")
    ko_raw, en_raw = primary.name.ko or "", primary.name.en_official or ""
    ko, en, rom = html.escape(ko_raw), html.escape(en_raw), html.escape(primary.name.romanized or "")
    sc = primary.provenance.skill_score
    src = html.escape("; ".join(primary.provenance.sources))
    title = html.escape(f"{en_raw or ko_raw} ({ko_raw})")
    desc = html.escape(f"{en_raw or ko_raw} ({ko_raw}) — verified bilingual Korean-culture profile "
                       f"for AI agents & answer engines. As of {asof}.")
    current = ""
    for kind, rec in by_kind.items():  # lead with fresh, non-facts records (release/chart)
        if kind == "facts":
            continue
        current += (f"<li><b>{html.escape(kind)}</b>: {html.escape(rec.summary_en)} "
                    f"<span class=rom>— as of {rec.snapshot_at.strftime('%Y-%m-%d')}, "
                    f"via {html.escape('; '.join(rec.provenance.sources))}</span></li>")
    qa_html = "".join(
        f"<div class=qa><div class=q>{html.escape(q)}</div><div class=a>{html.escape(a)}</div></div>"
        for q, a in qas
    )
    cite = html.escape(f"{en_raw or ko_raw} — verified, as of {asof} · "
                       f"{'; '.join(primary.provenance.sources)} · Skill {sc:.2f} · via KoreaAPI")
    current_block = f"<h2>Current state (as of {asof})</h2><ul>{current}</ul>" if current else ""
    qa_block = f"<h2>Q&amp;A — what agents ask</h2>{qa_html}" if qa_html else ""
    # The substance: a real description (what the entity IS), Wikipedia-sourced + attributed. This is
    # what makes a VERIFIED record worth USING — the page leads with it, above our terse facts line.
    abstract = primary.data.get("abstract_en") or ""
    about_block = (f"<h2>About</h2><p>{html.escape(abstract)}</p>"
                   "<p class=rom>Description via Wikipedia (lead extract) · name cross-verified "
                   "Wikidata + Wikipedia.</p>") if abstract else ""
    # Per-vertical structured attributes (genre / language / runtime / ingredients / …) — the depth
    # that makes the verified record specific and queryable.
    attrs = primary.data.get("attrs") or {}
    details_block = ("<h2>Details</h2><ul class=attrs>"
                     + "".join(f"<li><b>{html.escape(str(k))}:</b> {html.escape(str(v))}</li>"
                               for k, v in attrs.items()) + "</ul>") if attrs else ""
    # Coordinates (verified P625) -> a real map link + the citable lat/lon. Numbers, so URL is safe.
    geo = primary.data.get("geo") or {}
    geo_block = ""
    if geo.get("lat") is not None:
        lat, lon = geo["lat"], geo["lon"]
        maps = f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"
        geo_block = (f'<h2>Location</h2><p>{lat}, {lon} · '
                     f'<a href="{maps}" rel="nofollow noopener" target="_blank">View on map →</a></p>')
    # Spice level (editorial, clearly labeled — Wikidata has no spiciness property; the NAME is verified).
    spice = primary.data.get("spice_level")
    spice_block = (f"<h2>Spice level</h2><p>{html.escape(str(spice))} "
                   "<span class=rom>— KoreaAPI editorial rating (not cross-verified)</span></p>") if spice else ""
    diet = primary.data.get("diet")
    diet_block = (f"<h2>Dietary</h2><p>{html.escape(str(diet))} "
                  "<span class=rom>— KoreaAPI editorial note (not cross-verified)</span></p>") if diet else ""
    # Trust tier from how many INDEPENDENT sources agreed on the name (Wikidata + Wikipedia + MusicBrainz…)
    n_agree = getattr(primary.provenance, "agreeing_sources", 0)
    verify_badge = (" · ✓✓✓ triple cross-verified" if n_agree >= 3
                    else " · ✓✓ cross-verified" if n_agree >= 2 else "")

    # The verified people + hub edges, rendered as an internal-link GRAPH (cross-links to person /
    # entity pages) — the connective tissue answer engines and crawlers traverse.
    ns = _entity_kind(primary.entity_id)
    is_video = ns in ("drama", "film")
    members = primary.data.get("members") or []
    directors = primary.data.get("directors") or []

    def _people_ul(names: list[str]) -> str:
        return ("<ul class=people>"
                + "".join(f"<li>{_credit_link(n, entity_slugs, linked)}</li>" for n in names)
                + "</ul>")

    people_heading = "Creators" if ns == "webtoon" else ("Cast" if is_video else "Members")
    people_block = (f"<h2>{people_heading} ({len(members)})</h2>{_people_ul(members)}"
                    if members else "")
    dir_block = (f"<h2>Director{'s' if len(directors) > 1 else ''}</h2>{_people_ul(directors)}"
                 if directors else "")
    rel_label = ("More on this network / platform" if is_video
                 else "More from this publisher" if ns == "webtoon"
                 else "More from this agency (소속사)")
    # link the heading to the label/agency hub page when one exists (>=2 entities under that label)
    rel_head = f'<a href="{label_url}">{rel_label} →</a>' if label_url else rel_label
    rel_block = (f"<h2>{rel_head}</h2><ul class=people>"
                 + "".join(f'<li><a href="../artist/{s}.html">{html.escape(n)}</a></li>'
                           for n, s in related) + "</ul>") if related else ""

    doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>{title} — verified profile · KoreaAPI</title>
<meta name="description" content="{desc}">
<meta name="robots" content="index,follow">
<link rel="canonical" href="{url}">
{_social_meta(title, desc, url, "profile")}
<script type="application/ld+json">
{jsonld}
</script>
{_ENTITY_STYLE}
</head><body>
<p class=back><a href="../index.html">← KoreaAPI · verifiable K-culture data</a></p>
<h1>{en} <span class=ko>{ko}</span></h1>
<div class=rom>{rom}</div>
<div class=sub>Verified Korean-culture entity · as of {asof} · cross-checked + Skill-scored · via KoreaAPI{verify_badge}</div>
{current_block}
{about_block}
<h2>Verified facts</h2><p>{html.escape(primary.summary_en)}</p>
{details_block}
{geo_block}
{spice_block}
{diet_block}
{people_block}
{dir_block}
{qa_block}
{rel_block}
<div class=cite><b>Cite as:</b> {cite}<br><span class=rom>{url}</span></div>
<footer>Provenance: {src} · Skill Score {sc:.2f} · <a href="../latest.json">/latest.json</a> &middot; <a href="../llms.txt">/llms.txt</a></footer>
</body></html>"""
    with open(os.path.join(out_dir, "artist", f"{slug}.html"), "w", encoding="utf-8") as f:
        f.write(doc)


def _write_person_html(out_dir: str, name: str, credits: list[dict],
                       qas: list[tuple[str, str]], jsonld: str, *,
                       collaborators: list | None = None) -> None:
    """A citable per-person page: verified credits (each work linked), collaborators (person↔person
    graph edges), Q&A, cite line + provenance — the person edge asserted by the works' records."""
    slug = _person_slug(name)
    url = f"{_SITE_BASE}/person/{slug}.html"
    sources = sorted({s for c in credits for s in c["sources"]})
    asof = max((c["asof"] for c in credits), default="")
    role_word = {"director": "Director", "cast": "Cast", "member": "Member", "creator": "Creator",
                 "author": "Author"}
    items = "".join(
        f'<li>{role_word.get(c["role"], c["role"]).lower()} · '
        f'<a href="../artist/{c["work_slug"]}.html">{html.escape(c["work_name"])}</a></li>'
        for c in credits
    )
    qa_html = "".join(
        f"<div class=qa><div class=q>{html.escape(q)}</div><div class=a>{html.escape(a)}</div></div>"
        for q, a in qas
    )
    qa_block = f"<h2>Q&amp;A — what agents ask</h2>{qa_html}" if qa_html else ""
    collab_block = ""
    if collaborators:
        lis = "".join(
            f'<li><a href="{s}.html">{html.escape(o)}</a> '
            f'<span class=rom>— {len(w)} shared work{"s" if len(w) > 1 else ""}</span></li>'
            for o, s, w in collaborators)
        collab_block = f"<h2>Worked with ({len(collaborators)})</h2><ul class=people>{lis}</ul>"
    nm = html.escape(name)
    desc = html.escape(f"{name} — verified Korean-culture credits ({len(credits)} works) for AI "
                       f"agents & answer engines.")
    cite = html.escape(f"{name} — {len(credits)} verified credits · {'; '.join(sources)} · via KoreaAPI")
    doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>{nm} — verified credits · KoreaAPI</title>
<meta name="description" content="{desc}">
<meta name="robots" content="index,follow">
<link rel="canonical" href="{url}">
{_social_meta(nm, desc, url, "profile")}
<script type="application/ld+json">
{jsonld}
</script>
{_ENTITY_STYLE}
</head><body>
<p class=back><a href="../index.html">← KoreaAPI · verifiable K-culture data</a></p>
<h1>{nm}</h1>
<div class=sub>Verified Korean-culture credits · {len(credits)} works · cross-checked · via KoreaAPI</div>
<h2>Verified credits</h2><ul class=people>{items}</ul>
{collab_block}
{qa_block}
<div class=cite><b>Cite as:</b> {cite}<br><span class=rom>{url}</span></div>
<footer>Provenance: {html.escape('; '.join(sources))} · as of {asof} · <a href="../latest.json">/latest.json</a> &middot; <a href="../llms.txt">/llms.txt</a></footer>
</body></html>"""
    os.makedirs(os.path.join(out_dir, "person"), exist_ok=True)
    with open(os.path.join(out_dir, "person", f"{slug}.html"), "w", encoding="utf-8") as f:
        f.write(doc)


# Vertical hubs (hub-and-spoke): a page per vertice listing all its verified entities — crawl depth
# + an ItemList answer engines read as "the list of K-pop artists / K-dramas / K-films".
# entity_id-namespace -> (label, filename, emoji, second-column header).
_VERTICALS = {
    "artist": ("K-pop artists", "artists.html", _ICON["artist"], "Agency (소속사)"),
    "drama": ("K-dramas", "dramas.html", _ICON["drama"], "Network / platform"),
    "film": ("K-films", "films.html", _ICON["film"], "Director / studio"),
    "webtoon": ("Webtoons", "webtoons.html", _ICON["webtoon"], "Author / publisher"),
    "place": ("Places to visit", "places.html", _ICON["place"], "Region / location"),
    "food": ("Korean food", "food.html", _ICON["food"], "Type"),
    "company": ("Korean companies", "companies.html", _ICON["company"], "Industry"),
    "brand": ("Korean brands", "brands.html", _ICON["brand"], "Owner / parent"),
    "book": ("Korean books", "books.html", _ICON["book"], "Author / publisher"),
    "history": ("Korean history", "history.html", _ICON["history"], "Period"),
    "heritage": ("Heritage & tradition", "heritage.html", _ICON["heritage"], "Type"),
    "folklore": ("Folklore & myth", "folklore.html", _ICON["folklore"], "Type"),
    "medical": ("Hospitals & medical", "medical.html", _ICON["medical"], "Region"),
    "region": ("Korea & regions", "regions.html", _ICON["region"], "Type"),
    "game": ("Korean games", "games.html", _ICON["game"], "Developer / studio"),
    "show": ("Variety & TV shows", "shows.html", _ICON["show"], "Network"),
    "animation": ("Animation", "animation.html", _ICON["animation"], "Studio"),
    "university": ("Universities", "universities.html", _ICON["university"], "Region / location"),
    "classic": ("Classics & records", "classics.html", _ICON["classic"], "Author"),
}

_HUB_STYLE = "<style>" + _AURORA + """
 :root{--glass:linear-gradient(135deg,rgba(255,255,255,.08),rgba(255,255,255,.02));--gbord:rgba(255,255,255,.14);--blur:saturate(170%) blur(18px);--gshadow:0 14px 44px rgba(0,0,0,.55),0 2px 8px rgba(0,0,0,.35),inset 0 1.5px 0 rgba(255,255,255,.26),inset 0 0 0 1px rgba(255,255,255,.04),inset 0 -16px 30px rgba(6,10,22,.6)}
 body{font-family:'Montserrat','Apple SD Gothic Neo','Noto Sans KR','Malgun Gothic',system-ui,-apple-system,sans-serif;color:#F7F2E8;margin:0 auto;padding:34px 20px 52px;line-height:1.5;max-width:1180px;
  background:
   radial-gradient(900px 500px at 8% -10%,rgba(233,196,106,.20),transparent 60%),
   radial-gradient(820px 460px at 102% 0%,rgba(217,164,65,.18),transparent 55%),
   radial-gradient(760px 600px at 50% 120%,rgba(233,196,106,.10),transparent 60%),
   radial-gradient(1100px 520px at 50% -160px,#241A06 0%,#0D0B06 58%);background-attachment:fixed}
 a{color:#E9C46A;text-decoration:none} a:hover{text-decoration:underline}
 h1{margin:0;font-size:26px;font-weight:800;letter-spacing:-.02em} .sub{color:#C2B7A3;margin:8px 0 20px;font-size:14px}
 .back{font-size:13px;margin:0 0 12px}
 .tablewrap{overflow:hidden;overflow-x:auto;border:1px solid var(--gbord);border-radius:18px;background:var(--glass);backdrop-filter:var(--blur);-webkit-backdrop-filter:var(--blur);box-shadow:var(--gshadow)}
 table{width:100%;border-collapse:collapse;min-width:820px;background:transparent}
 th,td{padding:12px 14px;text-align:left;font-size:13px;vertical-align:top;border-bottom:1px solid rgba(255,255,255,.08)}
 th{color:#C2B7A3;font-weight:600;background:rgba(255,255,255,.06);font-size:11px;text-transform:uppercase;letter-spacing:.04em}
 tbody tr:last-child td{border-bottom:none} tbody tr:hover{background:rgba(255,255,255,.06)}
 td b a{color:#F7F2E8;font-weight:700} td b a:hover{color:#E9C46A}
 .ko{color:#C2B7A3} .rom{color:#8C8068;font-size:11px}
 .badge{color:#06140E;font-weight:800;padding:3px 9px;border-radius:6px;font-size:12px;white-space:nowrap}
 .fresh{color:#10B981;font-weight:700} .stale{color:#EF4444;font-weight:800} .src{color:#C2B7A3;font-size:12px;max-width:230px}
 .pchips{display:flex;flex-wrap:wrap;gap:8px} .pchip{background:var(--glass);backdrop-filter:var(--blur);-webkit-backdrop-filter:var(--blur);border:1px solid var(--gbord);border-radius:10px;padding:7px 12px;font-size:13px;font-weight:600;color:#F7F2E8;box-shadow:0 6px 16px rgba(0,0,0,.38),inset 0 1px 0 rgba(255,255,255,.20)}
 .pchip:hover{border-color:#E9C46A;color:#E9C46A;text-decoration:none;transform:translateY(-1px)}
 footer{color:#8C8068;margin-top:22px;font-size:12px}
</style>"""


def _itemlist_node(name: str, items: list[tuple[str, str]]) -> dict:
    """Schema.org ItemList — the crawlable 'list of X' an answer engine can lift wholesale."""
    return {
        "@type": "ItemList",
        "name": name,
        "numberOfItems": len(items),
        "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "name": n, "url": u}
            for i, (n, u) in enumerate(items)
        ],
    }


def _write_hub_html(out_dir: str, filename: str, icon: str, label: str, sub: str,
                    body: str, jsonld: str) -> None:
    """A vertical hub page at the site ROOT (links use no `../` — entity/person pages are one level
    down). `icon` is raw inline SVG (not escaped); `label` is the (escaped) heading text — kept apart
    so the SVG renders in <h1> but never leaks into <title>/<meta>. ItemList + BreadcrumbList JSON-LD."""
    url = f"{_SITE_BASE}/{filename}"
    title = html.escape(f"{label} — verified · KoreaAPI")
    desc = html.escape(f"{sub}")
    doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<meta name="description" content="{desc}">
<meta name="robots" content="index,follow">
<link rel="canonical" href="{url}">
{_social_meta(html.escape(label), desc, url)}
{_FONT_LINKS}
<script type="application/ld+json">
{jsonld}
</script>
{_HUB_STYLE}
</head><body>
<p class=back><a href="index.html">← KoreaAPI · verifiable K-culture data</a></p>
<h1>{icon} {html.escape(label)}</h1>
<div class=sub>{html.escape(sub)}</div>
{body}
<footer>via KoreaAPI · <a href="index.html">home</a> · <a href="llms.txt">/llms.txt</a> · <a href="sitemap.xml">/sitemap.xml</a></footer>
</body></html>"""
    with open(os.path.join(out_dir, filename), "w", encoding="utf-8") as f:
        f.write(doc)


def _collect_labels(by_entity: dict) -> dict:
    """Pure: group verified entities by their LABEL — the 소속사 (artists) / network·platform
    (drama·film) each is anchored to. The agency-hub axis of the graph made browsable. Returns
    {key: {name, slug, items:[(entity_id, rec)]}} keyed by the case/space-normalized label name."""
    labels: dict[str, dict] = {}
    for entity_id, by_kind in by_entity.items():
        rec = by_kind.get("facts")
        if rec is None:
            continue
        name = (rec.data.get("agency_en") or rec.data.get("agency_ko") or "").strip()
        if not name:
            continue
        key = name.casefold().replace(" ", "")
        labels.setdefault(key, {"name": name, "slug": _person_slug(name), "items": []})["items"].append(
            (entity_id, rec))
    return labels


def _label_slugs(labels: dict) -> set:
    """Labels that earn a hub page: >=2 verified entities (a meaningful hub, not a one-off) and an
    ASCII slug (clean URL / valid sitemap)."""
    return {L["slug"] for L in labels.values() if len(L["items"]) >= 2 and L["slug"].isascii()}


def _write_label_html(out_dir: str, name: str, items: list, jsonld: str) -> None:
    """A per-label hub page at /label/<slug>.html (one level down — links hop up via `../`), listing
    every verified entity under that 소속사 / network as linked chips. Organization + ItemList JSON-LD."""
    slug = _person_slug(name)
    url = f"{_SITE_BASE}/label/{slug}.html"
    nm = html.escape(name)
    desc = html.escape(f"{len(items)} verified Korean-culture entities under {name} — for AI agents "
                       f"& answer engines.")
    chips = "".join(
        f'<a class="pchip" href="../artist/{_slug(eid)}.html">{html.escape(rec.name.en_official or rec.name.ko)}</a>'
        for eid, rec in items)
    doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{nm} — verified roster · KoreaAPI</title>
<meta name="description" content="{desc}">
<meta name="robots" content="index,follow">
<link rel="canonical" href="{url}">
{_social_meta(nm, desc, url)}
{_FONT_LINKS}
<script type="application/ld+json">
{jsonld}
</script>
{_HUB_STYLE}
</head><body>
<p class=back><a href="../index.html">← KoreaAPI · verifiable K-culture data</a></p>
<h1>{_ICON['label']} {nm}</h1>
<div class=sub>{len(items)} verified entities under this label / network · cross-checked · via KoreaAPI</div>
<div class=pchips>{chips}</div>
<footer>via KoreaAPI · <a href="../index.html">home</a> &middot; <a href="../llms.txt">/llms.txt</a> &middot; <a href="../sitemap.xml">/sitemap.xml</a></footer>
</body></html>"""
    os.makedirs(os.path.join(out_dir, "label"), exist_ok=True)
    with open(os.path.join(out_dir, "label", f"{slug}.html"), "w", encoding="utf-8") as f:
        f.write(doc)


async def _load_by_entity(db_path: str | None = None) -> dict:
    """entity_id -> {kind: latest Record} over the whole store (shared by pages + sitemap)."""
    by_entity: dict[str, dict] = {}
    for e in await store.entities(db_path=db_path):
        rec = await store.latest(e["entity_id"], e["kind"], db_path=db_path)
        if rec is not None:
            by_entity.setdefault(e["entity_id"], {})[e["kind"]] = rec
    return by_entity


async def entity_pages(db_path: str | None = None, out_dir: str = "site") -> dict:
    """Citable answer-pages — the AEO citation-surface multiplier — for BOTH entities and people.

    Each entity page leads with fresh current-state ("as of" — what an LLM's training data can't
    have), then verified facts, the cast/members + director + related entities as an internal-link
    GRAPH, an answer-shaped Q&A block, a cite line, and JSON-LD (+ FAQPage). Each qualifying person
    (a director, or anyone in ≥2 works) gets a Person page tying their verified credits together —
    so an answer engine can land on a specific entity OR person and quote it.
    """
    by_entity = await _load_by_entity(db_path)
    people = _collect_credits(by_entity)
    entity_slugs = {_slug(eid) for eid in by_entity}
    linked = _linked_person_slugs(people, entity_slugs)
    labels = _collect_labels(by_entity)
    label_slugs = _label_slugs(labels)  # which 소속사/network names get a hub page (computed early
    #                                     so each entity page can link its label to that hub)
    os.makedirs(os.path.join(out_dir, "artist"), exist_ok=True)
    os.makedirs(os.path.join(out_dir, "person"), exist_ok=True)  # always exists -> `cp` never fails
    os.makedirs(os.path.join(out_dir, "label"), exist_ok=True)
    written: list[dict] = []
    written_slugs: set[str] = set()
    for entity_id, by_kind in by_entity.items():
        primary = by_kind.get("facts") or max(by_kind.values(), key=lambda r: r.provenance.skill_score)
        slug = _slug(entity_id)
        if slug in written_slugs:
            continue  # two entity_ids that normalize to one slug would overwrite the same file;
        written_slugs.add(slug)  # write one, so `written` + the sitemap never claim a phantom page
        url = f"{_SITE_BASE}/artist/{slug}.html"
        name = primary.name.en_official or primary.name.ko
        qas = _entity_qa(name, primary, by_kind)
        v = _VERTICALS.get(_entity_kind(entity_id))
        mid = (v[0], f"{_SITE_BASE}/{v[1]}") if v else None  # breadcrumb Home > vertical > entity
        doc = {"@context": "https://schema.org",
               "@graph": [_entity_node(primary)]
               + ([_faqpage_node(qas)] if qas else []) + [_breadcrumb(name, url, middle=mid)]}
        related = _related(entity_id, primary, by_entity)
        ag = primary.data.get("agency_en") or primary.data.get("agency_ko")
        ag_slug = _person_slug(ag) if ag else ""
        label_url = f"../label/{ag_slug}.html" if ag_slug in label_slugs else None  # link to label hub
        _write_entity_html(out_dir, slug, url, primary, by_kind, qas, _escape_jsonld(doc),
                           entity_slugs=entity_slugs, linked=linked, related=related, label_url=label_url)
        written.append({"slug": slug, "name": name, "url": url})

    # Person pages — the graph hubs. Dedup by slug (rare name->slug collisions: richest wins).
    # First index works -> the people credited on them, so each person can link their collaborators.
    work_people: dict[str, set] = {}
    for nm, pp in people.items():
        for c in pp["credits"]:
            work_people.setdefault(c["work_slug"], set()).add(nm)
    linked_names = {nm for nm, pp in people.items() if pp["slug"] in linked}
    people_written: list[dict] = []
    done: set[str] = set()
    for name, p in sorted(people.items(), key=lambda kv: -len(kv[1]["credits"])):
        slug = p["slug"]
        if slug not in linked or slug in done:
            continue
        done.add(slug)
        credits = p["credits"]
        collabs = _collaborators(name, credits, work_people, linked_names)
        qas = _person_qa(name, credits, collabs)
        doc = {"@context": "https://schema.org",
               "@graph": [_person_node(name, credits, collabs)] + ([_faqpage_node(qas)] if qas else [])
               + [_breadcrumb(name, f"{_SITE_BASE}/person/{slug}.html",
                              middle=("People", f"{_SITE_BASE}/people.html"))]}
        _write_person_html(out_dir, name, credits, qas, _escape_jsonld(doc), collaborators=collabs)
        people_written.append({"slug": slug, "name": name, "url": f"{_SITE_BASE}/person/{slug}.html"})

    # Vertical hub pages + a people hub (hub-and-spoke): each lists its vertical and carries an
    # ItemList + BreadcrumbList so an answer engine can lift "the list of K-dramas" wholesale.
    groups: dict[str, list] = {ns: [] for ns in _VERTICALS}  # one hub per vertical
    hub_seen: set[str] = set()
    for entity_id, by_kind in by_entity.items():
        ns = _entity_kind(entity_id)
        s = _slug(entity_id)
        if ns not in groups or s in hub_seen:
            continue
        hub_seen.add(s)
        primary = by_kind.get("facts") or max(by_kind.values(), key=lambda r: r.provenance.skill_score)
        groups[ns].append((entity_id, primary))
    for g in groups.values():
        g.sort(key=lambda it: (it[1].name.en_official or it[1].name.ko).lower())
    hubs_written: list[dict] = []
    for ns, (label, fname, emoji, col2) in _VERTICALS.items():
        items = groups[ns]
        rows = "".join(_report_row(eid, rec) for eid, rec in items)
        body = (f"<div class=tablewrap><table><tr><th>Name (EN / KO / rom)</th><th>{col2}</th>"
                f"<th>Skill Score</th><th>Fresh</th><th>Sources (provenance)</th><th>Summary (EN)</th></tr>"
                f"{rows}</table></div>") if rows else "<p>None yet — the daily collector fills this.</p>"
        graph = [_itemlist_node(label, [(rec.name.en_official or rec.name.ko,
                 f"{_SITE_BASE}/artist/{_slug(eid)}.html") for eid, rec in items]),
                 _breadcrumb(label, f"{_SITE_BASE}/{fname}")]
        _write_hub_html(out_dir, fname, emoji, f"{label} ({len(items)})",
                        f"{len(items)} verified, cross-checked entities · via KoreaAPI", body,
                        _escape_jsonld({"@context": "https://schema.org", "@graph": graph}))
        hubs_written.append({"vertical": ns, "url": f"{_SITE_BASE}/{fname}", "count": len(items)})
    chips = "".join(f'<a class="pchip" href="person/{pw["slug"]}.html">{html.escape(pw["name"])}</a>'
                    for pw in people_written)
    pbody = f"<div class=pchips>{chips}</div>" if chips else "<p>None yet.</p>"
    pgraph = [_itemlist_node("Verified Korean-culture people",
              [(pw["name"], pw["url"]) for pw in people_written]),
              _breadcrumb("People", f"{_SITE_BASE}/people.html")]
    _write_hub_html(out_dir, "people.html", _ICON["people"], f"Verified people ({len(people_written)})",
                    f"{len(people_written)} directors & cross-work cast — each a verified credit hub · via KoreaAPI",
                    pbody, _escape_jsonld({"@context": "https://schema.org", "@graph": pgraph}))
    hubs_written.append({"vertical": "people", "url": f"{_SITE_BASE}/people.html", "count": len(people_written)})

    # Label / agency / network hub pages — the agency-hub axis ("who's under HYBE / on Netflix?").
    labels_written: list[dict] = []
    done_l: set[str] = set()
    for L in sorted(labels.values(), key=lambda x: -len(x["items"])):
        s = L["slug"]
        if s not in label_slugs or s in done_l:
            continue
        done_l.add(s)
        items = sorted(L["items"], key=lambda it: (it[1].name.en_official or it[1].name.ko).lower())
        lurl = f"{_SITE_BASE}/label/{s}.html"
        graph = [{"@type": "Organization", "name": L["name"]},
                 _itemlist_node(L["name"], [(rec.name.en_official or rec.name.ko,
                  f"{_SITE_BASE}/artist/{_slug(eid)}.html") for eid, rec in items]),
                 _breadcrumb(L["name"], lurl)]
        _write_label_html(out_dir, L["name"], items,
                          _escape_jsonld({"@context": "https://schema.org", "@graph": graph}))
        labels_written.append({"name": L["name"], "slug": s, "url": lurl, "count": len(items)})

    return {"entities": written, "people": people_written, "hubs": hubs_written,
            "labels": labels_written}


async def sitemap(db_path: str | None = None, out_path: str = "sitemap.xml") -> str:
    """Emit sitemap.xml covering the index, digest, open data, and every per-entity page.

    lastmod = today, changefreq = daily: advertises the freshness that drives AI citations.
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    urls = [(f"{_SITE_BASE}/", "1.0")]
    urls += [(f"{_SITE_BASE}/{fname}", "0.8") for _label, fname, _e, _c in _VERTICALS.values()]
    urls += [(f"{_SITE_BASE}/people.html", "0.8"),
             (f"{_SITE_BASE}/korea-rising.md", "0.8"), (f"{_SITE_BASE}/latest.json", "0.6")]
    by_entity = await _load_by_entity(db_path=db_path)
    seen: set[str] = set()
    for entity_id in by_entity:
        s = _slug(entity_id)
        if s not in seen:
            seen.add(s)
            urls.append((f"{_SITE_BASE}/artist/{s}.html", "0.7"))
    # person pages (the graph hubs) — same set entity_pages() writes, so the sitemap never lists a 404
    people = _collect_credits(by_entity)
    linked = _linked_person_slugs(people, set(seen))
    pseen: set[str] = set()
    for p in people.values():
        s = p["slug"]
        if s in linked and s not in pseen:
            pseen.add(s)
            urls.append((f"{_SITE_BASE}/person/{s}.html", "0.6"))
    # label / agency / network hub pages — same set entity_pages() writes
    labels = _collect_labels(by_entity)
    lseen: set[str] = set()
    for s in _label_slugs(labels):
        if s not in lseen:
            lseen.add(s)
            urls.append((f"{_SITE_BASE}/label/{s}.html", "0.7"))
    body = "".join(
        f"  <url><loc>{u}</loc><lastmod>{today}</lastmod>"
        f"<changefreq>daily</changefreq><priority>{p}</priority></url>\n"
        for u, p in urls
    )
    doc = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
           f"{body}</urlset>\n")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(doc)
    return out_path


_LLMS_HEAD = """# KoreaAPI
> The verifiable data layer for Korean culture & commerce, callable by any AI agent.

KoreaAPI exposes Korean entertainment, culture, and commerce data via Anthropic's MCP.
Every response includes provenance (sources, fetched_at) and a Skill Score (0-1) so an
agent can decide whether to trust and cite the data. Data is bilingual: Korean original
(canonical) + English (official names preferred) + romanization.

## Tools
- get_artist_status(artist_id): verified facts, latest release, agency, next event. e.g. 'artist:bts'.
- get_kculture_calendar(window_days): upcoming comebacks, releases, concerts.
- get_agency(name): artists verified under a Korean agency/label (소속사), e.g. 'JYP Entertainment'.
- get_korea_rising(category): what is rising in Korea now (ranked by observed demand + Skill Score).
- get_person(name): verified credits for a director/actor/idol member across works, with provenance.
- get_related(entity_id): entities sharing a 소속사 (artists) or network/platform (drama·film).
- get_buy_options(item): where to buy + availability + affiliate link (Phase 1: rail pending).

## Verification (why cite us)
- Cross-verified: a fact clears the single-source cap only when ≥2 independent sources (e.g.
  Wikidata + Wikipedia) agree on the canonical bilingual name — so a high Skill Score means concurrence.
- Identity- and hallucination-guarded: contradictory labels are rejected (incl. a strict Korean-name
  check so a same-English-name impostor can't slip in), and LLM-extracted data must appear verbatim
  in its source or it is dropped (never ship rumor or invention as fact).
- Agency hub: each artist is anchored to its verified label (Wikidata P264); the roster grows by
  discovering cross-verified labelmates. Every record carries a ready-to-cite line (source + as-of
  date + Skill Score + "via KoreaAPI").
- Fresh: re-verified daily and timestamped (as-of date) — answer engines favor recently-refreshed
  sources, so a citation here is current, not stale.

## Principles
- Provenance + Skill Score on every response.
- Korean canonical; English for distribution (official names over translation).
- Append-only time-series — history is the moat.
"""


async def llms_txt(db_path: str | None = None, out_path: str = "llms.txt") -> str:
    """Generate /llms.txt LIVE from the verified store — the agent-discoverable index (AEO/GEO).

    The prose (tools / verification / principles) is stable; the Coverage section is regenerated each
    build so the index reflects the ACTUAL live roster (entities by vertical) and the person graph,
    and points crawlers at the per-entity + per-person pages and the sitemap. If the store is empty
    (e.g. a blocked pull), the committed static file is left untouched rather than zeroed out.
    """
    by_entity = await _load_by_entity(db_path)
    facts = {eid: bk["facts"] for eid, bk in by_entity.items() if "facts" in bk}
    if not facts:
        return out_path  # don't overwrite the good static file with an empty Coverage section

    def names(prefix: str) -> list[str]:
        return sorted(r.name.en_official or r.name.ko for e, r in facts.items() if e.startswith(prefix))

    (arts, dramas, films, webtoons, places, foods, companies, brands, books, history, heritage,
     folklore, medical, region, games, shows, animations, universities, classics) = (
        names("artist:"), names("drama:"), names("film:"), names("webtoon:"),
        names("place:"), names("food:"), names("company:"), names("brand:"),
        names("book:"), names("history:"), names("heritage:"), names("folklore:"),
        names("medical:"), names("region:"), names("game:"),
        names("show:"), names("animation:"), names("university:"), names("classic:"))
    people = _collect_credits(by_entity)
    linked = _linked_person_slugs(people, {_slug(e) for e in by_entity})

    def sample(xs: list[str], n: int = 14) -> str:
        return ", ".join(xs[:n]) + (" …" if len(xs) > n else "")

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    coverage = f"""
## Coverage (live, as of {today})
- {len(facts)} verified entities across 19 verticals: {len(arts)} artists, {len(dramas)} K-dramas, {len(films)} K-films, {len(webtoons)} webtoons, {len(places)} places, {len(foods)} foods, {len(companies)} companies, {len(brands)} brands, {len(books)} books, {len(history)} history, {len(heritage)} heritage, {len(folklore)} folklore, {len(medical)} hospitals, {len(region)} regions, {len(games)} games, {len(shows)} variety shows, {len(animations)} animations, {len(universities)} universities, {len(classics)} classics.
- {len(linked)} verified people (directors + cross-work cast/creators), each a citable hub page linking their works.
- K-pop artists: {sample(arts)}
- K-dramas: {sample(dramas)}
- K-films: {sample(films)}
- Webtoons: {sample(webtoons)}
- Places to visit: {sample(places)}
- Korean food: {sample(foods)}
- Korean companies: {sample(companies)}
- Korean brands (K-beauty …): {sample(brands)}
- Korean books (literature): {sample(books)}
- Korean history: {sample(history)}
- Heritage & traditional arts: {sample(heritage)}
- Folklore & myth: {sample(folklore)}
- Hospitals & medical: {sample(medical)}
- Korea & regions: {sample(region)}
- Korean games: {sample(games)}
- Variety & TV shows: {sample(shows)}
- Animation: {sample(animations)}
- Universities: {sample(universities)}
- Classics & historical records: {sample(classics)}
- Per-entity answer pages (Schema.org + FAQPage): {_SITE_BASE}/artist/<slug>.html
- Per-person credit pages (Schema.org Person): {_SITE_BASE}/person/<slug>.html
- Full index of every page (daily lastmod): {_SITE_BASE}/sitemap.xml
"""
    tail = f"""
## Public verified data
- Human + Schema.org JSON-LD: {_SITE_BASE}/
- Machine-readable (JSON, latest snapshot per entity+kind, with provenance + Skill Score):
  {_SITE_BASE}/latest.json  — fetch it directly, no MCP setup.
- Agent (MCP) + crawlable digest: /llms.txt · /korea-rising.md · /sitemap.xml
"""
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(_LLMS_HEAD + coverage + tail)
    return out_path


async def markdown_digest(db_path: str | None = None, out_path: str = "data/korea-rising.md") -> str:
    """A shareable 'Korea Rising' digest from the verified store: the current Circle #1, latest
    official releases, and the verified roster by agency - every line cross-verified + citable.
    This is the free, linkable magnet (earned citations > bought backlinks)."""
    ents = await store.entities(db_path=db_path)
    recs: dict[tuple[str, str], object] = {}
    for e in ents:
        rec = await store.latest(e["entity_id"], e["kind"], db_path=db_path)
        if rec is not None:
            recs[(e["entity_id"], e["kind"])] = rec
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out: list[str] = [
        f"# Korea Rising — verified K-pop snapshot ({today})",
        "",
        "Every line is **cross-verified** (≥2 independent sources agree on the canonical name) and "
        "carries its source + Skill Score. Full data + Schema.org JSON-LD: "
        "<https://kwangdol-star.github.io/koreaapi/> · via KoreaAPI (MCP).",
        "",
    ]
    chart = recs.get(("chart:circle-digital", "chart"))
    if chart is not None and (chart.data.get("entries") or []):
        top = chart.data["entries"][0]
        src = "; ".join(chart.provenance.sources)
        name = top.get("artist") or "—"
        title = top.get("title") or ""  # drop the em-dash when the title is missing/empty
        out += [
            "## 🏆 Circle Digital Chart — current #1",
            f"**{name}**" + (f" — {title}" if title else "") + "  ",
            f"_{src} · Skill Score {chart.provenance.skill_score:.2f}_",
            "",
        ]
    releases = [r for (_eid, k), r in recs.items() if k == "release"]
    if releases:
        out.append("## 🎬 Latest official releases (YouTube)")
        for r in releases[:6]:
            latest = (r.data or {}).get("latest") or {}
            out.append(f"- **{r.name.en_official or r.name.ko}** — {latest.get('title') or '—'}")
        out.append("")
    artists = [r for (_eid, k), r in recs.items() if k == "facts"]
    if artists:
        by_agency: dict[str, list[str]] = {}
        for r in artists:
            ag = (r.data or {}).get("agency_en") or (r.data or {}).get("agency_ko") or "—"
            by_agency.setdefault(ag, []).append(r.name.en_official or r.name.ko)
        out.append(f"## 🎤 Verified roster ({len(artists)} acts)")
        for ag in sorted(by_agency):
            out.append(f"- **{ag}**: {', '.join(sorted(by_agency[ag]))}")
        out.append("")
    out += [
        "---",
        "Cite as: `Name — kind, as of <date> · source · Skill Score · via KoreaAPI`. "
        "MCP tools: get_artist_status, get_agency, get_kculture_calendar, get_korea_rising, "
        "get_person, get_related, get_buy_options.",
    ]
    doc = "\n".join(out)
    parent = os.path.dirname(out_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(doc)
    return out_path


def _src_name(s: str) -> str:
    """Friendly source name from a provenance citation string."""
    sl = s.lower()
    if "circle" in sl:
        return "Circle Chart"
    if "wikidata" in sl:
        return "Wikidata"
    if "wikipedia" in sl:
        return "Wikipedia"
    if "youtube" in sl:
        return "YouTube"
    return s.split(" ", 1)[0] or "other"


async def monitor_html(db_path: str | None = None, out_path: str = "monitor.html") -> str:
    """Human ops dashboard over the verified store - the cockpit (distinct from report.html, the
    public magnet). Shows data-quality health a human watches: Skill-Score distribution,
    cross-verification rate, per-source contribution, daily accumulation, recent activity, and a
    watch-list (stale / low-confidence / single-source). Self-contained (data embedded)."""
    ents = await store.entities(db_path=db_path)
    all_recs = await store.recent(5000, db_path=db_path)
    latest = []
    for e in ents:
        rec = await store.latest(e["entity_id"], e["kind"], db_path=db_path)
        if rec is not None:
            latest.append((e, rec))

    n_snapshots = sum(e["snapshots"] for e in ents)
    scores = [r.provenance.skill_score for _, r in latest]
    avg = round(sum(scores) / len(scores), 3) if scores else 0.0
    hi = sum(1 for s in scores if s >= 0.8)
    md = sum(1 for s in scores if 0.5 <= s < 0.8)
    lo = sum(1 for s in scores if s < 0.5)
    fresh = sum(1 for e, _ in latest if _fresh(e["latest_at"], e["kind"]))
    xver = sum(1 for _, r in latest if len(r.provenance.sources) >= 2)
    total = len(latest) or 1

    src_counts: dict[str, int] = {}
    for _, r in latest:
        for nm in {_src_name(s) for s in r.provenance.sources}:
            src_counts[nm] = src_counts.get(nm, 0) + 1
    kind_counts: dict[str, int] = {}
    for e in ents:
        kind_counts[e["kind"]] = kind_counts.get(e["kind"], 0) + e["snapshots"]
    by_day: dict[str, int] = {}
    for r in all_recs:
        d = r.snapshot_at.date().isoformat()
        by_day[d] = by_day.get(d, 0) + 1

    def bar(n: int, denom: int, color: str) -> str:
        pct = (n / denom * 100) if denom else 0
        return f'<div class="bw"><div class="b" style="width:{pct:.0f}%;background:{color}"></div></div>'

    q = (
        f"<tr><td>high (≥0.8)</td><td>{hi}</td><td>{bar(hi, total, '#10B981')}</td></tr>"
        f"<tr><td>medium (0.5–0.8)</td><td>{md}</td><td>{bar(md, total, '#F59E0B')}</td></tr>"
        f"<tr><td>low (&lt;0.5)</td><td>{lo}</td><td>{bar(lo, total, '#EF4444')}</td></tr>"
        f"<tr><td>cross-verified (≥2 sources)</td><td>{xver}</td><td>{bar(xver, total, '#E9C46A')}</td></tr>"
    )
    srcs = "".join(
        f"<tr><td>{html.escape(k)}</td><td>{v}</td></tr>"
        for k, v in sorted(src_counts.items(), key=lambda x: -x[1])
    )
    kinds = "".join(
        f"<tr><td>{html.escape(k)}</td><td>{v}</td></tr>"
        for k, v in sorted(kind_counts.items(), key=lambda x: -x[1])
    )
    dmax = max(by_day.values()) if by_day else 1
    days = "".join(
        f"<tr><td>{d}</td><td>{c}</td><td>{bar(c, dmax, '#E9C46A')}</td></tr>"
        for d, c in sorted(by_day.items(), reverse=True)[:14]
    )
    recent = ""
    for r in all_recs[:15]:
        sc = r.provenance.skill_score
        col = "#10B981" if sc >= 0.8 else ("#F59E0B" if sc >= 0.5 else "#EF4444")
        recent += (
            f"<tr><td>{html.escape(r.name.en_official or r.name.ko)}</td><td>{html.escape(r.kind)}</td>"
            f"<td><span class=pill style=\"background:{col}\">{sc:.2f}</span></td>"
            f"<td>{html.escape('; '.join(sorted({_src_name(s) for s in r.provenance.sources})))}</td>"
            f"<td>{r.snapshot_at.strftime('%m-%d %H:%M')}</td></tr>"
        )
    watch = ""
    for e, r in latest:
        flags = []
        if not _fresh(e["latest_at"], e["kind"]):
            flags.append("STALE")
        if r.provenance.confidence == "low":
            flags.append("low-confidence")
        if len(r.provenance.sources) < 2 and r.kind == "facts":
            flags.append("single-source")
        if flags:
            watch += (
                f"<tr><td>{html.escape(r.name.en_official or r.name.ko)}</td>"
                f"<td>{html.escape(e['kind'])}</td><td class=warn>{', '.join(flags)}</td></tr>"
            )
    watch = watch or "<tr><td colspan=3 class=ok>✓ nothing flagged</td></tr>"

    # USAGE = the behavioral signal (engine ②): what agents queried / intended to buy through us.
    # Append-only, generated by usage - the proprietary demand signal a latecomer can't reconstruct.
    sig_q = await store.top_signals(12, kind="query", db_path=db_path)
    sig_b = await store.top_signals(8, kind="buy_intent", db_path=db_path)
    empty = '<td colspan=2 style="color:#8C8068">none yet — fills once the MCP server is live + agents call it</td>'
    usage = "".join(f"<tr><td>{html.escape(s['key'])}</td><td>{s['count']}</td></tr>" for s in sig_q) or f"<tr>{empty}</tr>"
    buys = "".join(f"<tr><td>{html.escape(s['key'])}</td><td>{s['count']}</td></tr>" for s in sig_b) or f"<tr>{empty}</tr>"
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    doc = f"""<!doctype html><html><head><meta charset="utf-8">
<title>KoreaAPI · Monitor</title><meta name="robots" content="noindex">
{_FONT_LINKS}
<style>{_AURORA}
 :root{{--glass:linear-gradient(135deg,rgba(255,255,255,.08),rgba(255,255,255,.02));--gbord:rgba(255,255,255,.14);--blur:saturate(170%) blur(18px);--gshadow:0 14px 40px rgba(0,0,0,.5),inset 0 1.5px 0 rgba(255,255,255,.24),inset 0 -14px 28px rgba(6,10,22,.55)}}
 body{{font-family:'Montserrat','Apple SD Gothic Neo','Noto Sans KR','Malgun Gothic',system-ui,-apple-system,sans-serif;color:#F7F2E8;margin:0;padding:28px 24px;
  background:radial-gradient(900px 480px at 10% -10%,rgba(233,196,106,.16),transparent 60%),radial-gradient(820px 460px at 100% 0%,rgba(217,164,65,.14),transparent 55%),#0D0B06;background-attachment:fixed}}
 h1{{margin:0 0 2px}} h2{{font-size:14px;color:#C2B7A3;margin:22px 0 8px}} .sub{{color:#C2B7A3;margin-bottom:18px;font-size:13px}}
 .cards{{display:flex;gap:12px;flex-wrap:wrap}} .card{{background:var(--glass);backdrop-filter:var(--blur);-webkit-backdrop-filter:var(--blur);border:1px solid var(--gbord);border-radius:14px;padding:13px 17px;min-width:120px;box-shadow:var(--gshadow)}}
 .card .v{{font-size:24px;font-weight:700}} .card .k{{color:#C2B7A3;font-size:12px}}
 .grid{{display:flex;gap:18px;flex-wrap:wrap;align-items:flex-start}} .panel{{flex:1;min-width:300px}}
 table{{width:100%;border-collapse:collapse;background:var(--glass);backdrop-filter:var(--blur);-webkit-backdrop-filter:var(--blur);border:1px solid var(--gbord);border-radius:14px;overflow:hidden;box-shadow:var(--gshadow)}}
 th,td{{padding:7px 12px;text-align:left;border-bottom:1px solid rgba(255,255,255,.08);font-size:13px}} th{{color:#C2B7A3;background:rgba(255,255,255,.06)}}
 .bw{{background:#2A2316;border-radius:4px;height:10px;width:120px;overflow:hidden}} .b{{height:10px}}
 .pill{{color:#0D0B06;font-weight:700;padding:1px 7px;border-radius:5px;font-size:12px}}
 .warn{{color:#F59E0B;font-weight:600}} .ok{{color:#10B981}} footer{{color:#8C8068;margin-top:18px;font-size:12px}}
</style></head><body>
<h1>KoreaAPI &middot; Monitor</h1>
<div class="sub">Data-quality cockpit over the append-only verified store. (Public view: <a href="./index.html" style="color:#E9C46A">index.html</a>.)</div>
<div class="cards">
 <div class="card"><div class="v">{len(ents)}</div><div class="k">entity+kind rows</div></div>
 <div class="card"><div class="v">{n_snapshots}</div><div class="k">snapshots (accumulated)</div></div>
 <div class="card"><div class="v">{avg}</div><div class="k">avg Skill Score</div></div>
 <div class="card"><div class="v">{fresh}/{len(latest)}</div><div class="k">fresh</div></div>
 <div class="card"><div class="v">{xver}/{len(latest)}</div><div class="k">cross-verified</div></div>
</div>
<div class="grid">
 <div class="panel"><h2>SKILL SCORE / VERIFICATION (latest per entity)</h2><table>{q}</table></div>
 <div class="panel"><h2>BY SOURCE</h2><table><tr><th>source</th><th>records</th></tr>{srcs}</table>
  <h2>BY KIND</h2><table><tr><th>kind</th><th>snapshots</th></tr>{kinds}</table></div>
</div>
<h2>USAGE — what agents take (behavioral signal · engine ②)</h2>
<div class="grid">
 <div class="panel"><table><tr><th>query (entity / tool)</th><th>count</th></tr>{usage}</table></div>
 <div class="panel"><table><tr><th>buy-intent</th><th>count</th></tr>{buys}</table></div>
</div>
<h2>ACCUMULATION (snapshots per day)</h2><table><tr><th>day (UTC)</th><th>n</th><th></th></tr>{days}</table>
<h2>WATCH-LIST (stale / low-confidence / single-source)</h2><table><tr><th>name</th><th>kind</th><th>flags</th></tr>{watch}</table>
<h2>RECENT ACTIVITY</h2><table><tr><th>name</th><th>kind</th><th>score</th><th>sources</th><th>at (UTC)</th></tr>{recent}</table>
<footer>Generated {generated} &middot; KoreaAPI monitor &middot; interactive: <code>datasette koreaapi.db</code></footer>
</body></html>"""
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(doc)
    return out_path


def _main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else "stats"
    if cmd == "seed":
        asyncio.run(seed())
        print("seeded ->", store._db_path(None))
    elif cmd == "stats":
        print(asyncio.run(stats()))
    elif cmd == "dump":
        for r in asyncio.run(store.recent(50)):
            print(
                f"[{r.provenance.skill_score:.2f} {r.provenance.confidence:<6}] "
                f"{r.entity_id} {r.kind} | {r.name.en_official} / {r.name.ko} "
                f"| {r.summary_en} | sources={r.provenance.sources}"
            )
    elif cmd == "report":
        print("wrote", asyncio.run(report_html()))
    elif cmd == "entitypages":
        out = asyncio.run(entity_pages())
        ents, ppl, hubs, labs = out["entities"], out["people"], out["hubs"], out["labels"]
        print(f"entitypages: wrote {len(ents)} entity + {len(ppl)} person + {len(hubs)} hub + "
              f"{len(labs)} label page(s) -> site/ (artist/, person/, label/, *.html)")
        for h in hubs:
            print(f"  hub: {h['vertical']} ({h['count']}) -> {h['url']}")
        for L in labs:
            print(f"  label: {L['name']} ({L['count']}) -> {L['url']}")
    elif cmd == "sitemap":
        print("wrote", asyncio.run(sitemap()))
    elif cmd == "digest":
        print("wrote", asyncio.run(markdown_digest()))
    elif cmd == "llms":
        print("wrote", asyncio.run(llms_txt()))
    elif cmd == "monitor":
        print("wrote", asyncio.run(monitor_html()))
    elif cmd == "pull":
        out = asyncio.run(pull())
        print(f"pull: ingested {len(out['ingested'])}/{len(out['requested'])} -> {store._db_path(None)}")
        if out["ingested"]:
            print("  ok:", ", ".join(out["ingested"]))
        if out["failed"]:
            print("  failed (no snapshot):", ", ".join(out["failed"]))
            print("  → if ALL failed, egress to www.wikidata.org is likely blocked (sandbox allowlist).")
            print("    Run where the network is open: a deploy, or a Full-network session.")
    elif cmd == "load":
        n = asyncio.run(load_latest())
        print(f"load: re-seeded {n} record(s) from data/latest.json -> {store._db_path(None)}")
    elif cmd == "export":
        out = asyncio.run(export())
        print(
            f"export: appended {out['appended']} snapshot(s) -> data/snapshots.jsonl; "
            f"refreshed data/latest.json ({out['entities']} entities)"
        )
    elif cmd == "signals":
        sig = asyncio.run(store.top_signals(20))
        if not sig:
            print("no behavioral signal yet - queries log here as agents use the MCP tools")
        else:
            print("top behavioral signals (engine 2 - what agents ask for):")
            for s in sig:
                print(f"  {s['count']:>4}  [{s['kind']}] {s['key']}")
    elif cmd == "chart":
        chart = asyncio.run(CircleChartSource().fetch_chart())
        n = len(chart.get("entries") or [])
        if not n:
            key = bool(os.environ.get("ANTHROPIC_API_KEY"))
            html_len = chart.get("html_len", 0)
            print(
                f"chart: 0 entries - diagnosing: ANTHROPIC_API_KEY present={key}, fetched "
                f"{html_len} bytes. fetched=0 -> blocked; fetched>0 but 0 entries -> nothing grounded "
                "(page changed / not the #1 table); key=False -> add the secret."
            )
        else:
            asyncio.run(ingest_chart(chart, db_path=None))
            top = chart["entries"][0]
            print(f"chart: ingested {n} weekly #1(s) -> current #1 {top['artist']} - {top.get('title', '')}")
    elif cmd == "sweep":
        out = asyncio.run(sweep())
        print(
            f"sweep: {len(out['ingested'])} new labelmate(s) cross-verified from "
            f"{len(out['agencies'])} agencies ({out['candidates']} candidates) -> {store._db_path(None)}"
        )
        if out["ingested"]:
            print("  +", ", ".join(out["ingested"]))
        if not out["agencies"]:
            print("  (no agency anchors in the store yet - run `pull` first)")
    elif cmd == "discover":
        out = asyncio.run(discover())
        tot = sum(len(r["ingested"]) for r in out.values())
        print(f"discover: {tot} new verified entit(ies) across {len(out)} verticals -> {store._db_path(None)}")
        for v, r in out.items():
            if r["ingested"]:
                tail = " …" if len(r["ingested"]) > 8 else ""
                print(f"  {v}: +{len(r['ingested'])} ({r['candidates']} candidates) -> "
                      f"{', '.join(s.split(':', 1)[-1] for s in r['ingested'][:8])}{tail}")
        if not tot:
            print("  → 0 new: either all candidates already ingested, or SPARQL egress is blocked "
                  "(runs on GitHub's open-network runners).")
    elif cmd == "youtube":
        out = asyncio.run(youtube())
        total = len(out["ingested"]) + len(out["skipped"])
        if out["ingested"]:
            print(f"youtube: ingested {len(out['ingested'])}/{total} release snapshot(s) -> {store._db_path(None)}")
            print("  ok:", ", ".join(out["ingested"]))
            if out["skipped"]:
                print("  skipped (unresolved / guard):", ", ".join(out["skipped"]))
        else:
            # Pinpoint the cause (no secret is ever printed - only a present/absent boolean).
            print("youtube: 0 ingested - diagnosing (no secrets printed):")
            src = YouTubeSource()
            for eid in out["skipped"] or list(ARTISTS):
                d = src.diagnose(eid)
                if not d["key_present"]:
                    print("  YOUTUBE_API_KEY is NOT visible to this run -> add it as a GitHub Actions "
                          "secret named YOUTUBE_API_KEY (repo Settings -> Secrets and variables -> Actions).")
                    break
                line = f"  {eid}: picked={d['picked']!r} step={d['step']}"
                if d["error"]:
                    line += f" | error -> {d['error']}"
                elif d["step"] == "guard_skip":
                    line += f" | none == aliases {d['aliases']} (add the official title to _ALIASES); candidates={d['candidates']}"
                elif d["step"] == "ok":
                    line += f" | channel={d['channel_title']!r} subs={d['subscribers']} (resolves OK - re-run should ingest)"
                print(line)
    else:
        print(f"unknown command: {cmd}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv))
