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
  python -m koreaapi.admin export   # write data/ asset (snapshots.jsonl history + latest.json)
  python -m koreaapi.admin signals  # top behavioral signals (engine 2: what agents query)
  python -m koreaapi.admin stats    # print a data-quality summary
  python -m koreaapi.admin dump     # print recent snapshots
  python -m koreaapi.admin report   # write report.html (open it in a browser)
  python -m koreaapi.admin digest   # write data/korea-rising.md (shareable verified digest)
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

from .pipeline import store
from .pipeline.ingest import ingest_chart, ingest_one, ingest_youtube
from .pipeline.scheduler import CADENCE
from .roster import ARTISTS
from .sources.circlechart import CircleChartSource
from .sources.mock import MockSource
from .sources.wikidata import WikidataSource, fetch_labelmates
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
    ids = entity_ids or list(ARTISTS)
    sources = [WikidataSource(), WikipediaSource()]  # two independent sources -> cross-verify
    ingested: list[str] = []
    failed: list[str] = []
    for entity_id in ids:
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
    sources = [WikidataSource(aliases=aliases), WikipediaSource(aliases=aliases)]
    ingested: list[str] = []
    for eid, _name in todo:
        rec = await ingest_one("facts", eid, sources, db_path=db_path)
        if rec is not None:
            ingested.append(eid)
    return {"agencies": list(agencies.values()), "candidates": n_candidates, "ingested": ingested}


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
    except ValueError:
        return False
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


def _jsonld(records: list, generated_iso: str) -> str:
    """Schema.org JSON-LD for the verified entities (AEO/GEO: crawlable, citable structure).

    Answer engines (Perplexity / ChatGPT / Google AI Overviews) parse JSON-LD; emitting each
    artist as a MusicGroup with `sameAs` the Wikidata entity makes our verified, dated record
    citable on the open web - the GEO substrate on top of the same append-only store.
    """
    groups = []
    seen: set[str] = set()
    for r in records:
        if r.entity_id in seen:
            continue
        seen.add(r.entity_id)
        node = {
            "@type": "MusicGroup",
            "name": r.name.en_official or r.name.ko,
            "alternateName": [x for x in (r.name.ko, r.name.romanized) if x],
            "description": r.summary_en,
            "dateModified": r.snapshot_at.isoformat(),
        }
        wd = _wikidata_url(r.provenance.sources)
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
        groups.append(node)
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
        ],
    }
    # Escape <, >, & so a field value containing "</script>" (LLM/scraped prose) cannot break out
    # of the inline <script type="application/ld+json"> block and inject HTML into the public page.
    return (
        json.dumps(doc, ensure_ascii=False, indent=2)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )


async def report_html(db_path: str | None = None, out_path: str = "report.html") -> str:
    ents = await store.entities(db_path=db_path)
    s = await stats(db_path=db_path)
    rows = []
    recs = []
    for e in ents:
        rec = await store.latest(e["entity_id"], e["kind"], db_path=db_path)
        if rec is None:
            continue
        recs.append(rec)
        sc = rec.provenance.skill_score
        color = "#10B981" if sc >= 0.8 else ("#F59E0B" if sc >= 0.5 else "#EF4444")
        is_fresh = _fresh(e["latest_at"], e["kind"])
        agency_en = rec.data.get("agency_en") or rec.data.get("agency_ko") or ""
        agency_ko = rec.data.get("agency_ko") or ""
        agency_cell = html.escape(agency_en)
        if agency_ko and agency_ko != agency_en:
            agency_cell += f"<br><span class=ko>{html.escape(agency_ko)}</span>"
        rows.append(
            "<tr>"
            f"<td><b>{html.escape(rec.name.en_official or '')}</b>"
            f"<br><span class=ko>{html.escape(rec.name.ko)}</span>"
            f"<br><span class=rom>{html.escape(rec.name.romanized or '')}</span></td>"
            f"<td>{html.escape(e['kind'])}</td>"
            f"<td>{agency_cell}</td>"
            f"<td><span class=badge style=\"background:{color}\">"
            f"{sc:.2f} {html.escape(rec.provenance.confidence)}</span></td>"
            f"<td>{html.escape(rec.provenance.translation.source)}</td>"
            f"<td class={'fresh' if is_fresh else 'stale'}>{'fresh' if is_fresh else 'STALE'}</td>"
            f"<td>{e['snapshots']}</td>"
            f"<td>{html.escape('; '.join(rec.provenance.sources))}</td>"
            f"<td>{html.escape(rec.summary_en)}</td>"
            "</tr>"
        )
    now = datetime.now(timezone.utc)
    generated = now.strftime("%Y-%m-%d %H:%M UTC")
    jsonld = _jsonld(recs, now.isoformat())
    doc = f"""<!doctype html><html><head><meta charset="utf-8">
<title>KoreaAPI — verifiable Korean-culture data for AI agents</title>
<meta name="description" content="KoreaAPI - verifiable, bilingual Korean culture data for AI agents. Every record carries its source and a Skill Score.">
<meta name="robots" content="index,follow">
<script type="application/ld+json">
{jsonld}
</script>
<style>
 body{{font-family:system-ui,-apple-system,sans-serif;background:#0A0E1A;color:#F5F7FA;margin:0;padding:24px}}
 h1{{margin:0 0 4px}} .sub{{color:#A0AEC0;margin-bottom:20px}}
 .cards{{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:20px}}
 .card{{background:#131829;border:1px solid #2A3349;border-radius:10px;padding:12px 16px;min-width:120px}}
 .card .v{{font-size:24px;font-weight:700}} .card .k{{color:#A0AEC0;font-size:12px}}
 table{{width:100%;border-collapse:collapse;background:#131829;border:1px solid #2A3349;border-radius:10px;overflow:hidden}}
 th,td{{padding:10px 12px;text-align:left;border-bottom:1px solid #1F2638;font-size:13px;vertical-align:top}}
 th{{color:#A0AEC0;font-weight:600;background:#1A2036}}
 .ko{{color:#A0AEC0}} .rom{{color:#6B7585;font-size:11px}}
 .badge{{color:#0A0E1A;font-weight:700;padding:2px 8px;border-radius:6px;font-size:12px}}
 .fresh{{color:#10B981}} .stale{{color:#EF4444;font-weight:700}}
 footer{{color:#6B7585;margin-top:16px;font-size:12px}}
 code{{background:#1A2036;padding:1px 6px;border-radius:4px}}
 a{{color:#7DA2FF;text-decoration:none}} a:hover{{text-decoration:underline}}
 .intro{{background:#131829;border:1px solid #2A3349;border-radius:10px;padding:14px 18px;margin-bottom:20px;max-width:1100px;line-height:1.55}}
 .intro p{{margin:6px 0;font-size:13px;color:#C9D2E3}} .intro b{{color:#F5F7FA}}
</style></head><body>
<h1>KoreaAPI</h1>
<div class="sub">The verifiable data layer for Korean culture &mdash; callable by any AI agent (MCP), citable by any answer engine.</div>
<div class="intro">
 <p>Every row below is <b>verified</b>: cross-checked across independent sources (Wikidata + Wikipedia), identity- and hallucination-guarded, and stamped with a transparent <b>Skill Score</b> + <b>provenance</b>. Korean is canonical; English + romanization for distribution. Each artist is anchored to its <b>소속사 (agency)</b>, and the roster grows by discovering cross-verified labelmates.</p>
 <p><b>Agents</b> call 5 MCP tools &mdash; <code>get_artist_status</code>, <code>get_agency</code>, <code>get_kculture_calendar</code>, <code>get_korea_rising</code>, <code>get_buy_options</code>. <b>Answer engines</b>: this page ships Schema.org JSON-LD + <a href="./llms.txt">/llms.txt</a>. <b>Cite a row as:</b> &ldquo;Name &mdash; kind, as of date &middot; source &middot; Skill Score &middot; via KoreaAPI&rdquo;.</p>
 <p><a href="https://github.com/wrxfoundation/weatherplan-ai">Source &amp; docs on GitHub</a> &middot; <a href="./llms.txt">llms.txt</a></p>
</div>
<div class="cards">
 <div class="card"><div class="v">{s.get('entities', 0)}</div><div class="k">entities</div></div>
 <div class="card"><div class="v">{s.get('snapshots', 0)}</div><div class="k">snapshots (append-only)</div></div>
 <div class="card"><div class="v">{s.get('avg_skill_score', '-')}</div><div class="k">avg Skill Score</div></div>
 <div class="card"><div class="v">{s.get('fresh_entities', '-')}</div><div class="k">fresh</div></div>
 <div class="card"><div class="v">{s.get('low_confidence', 0)}</div><div class="k">low confidence</div></div>
</div>
<table>
<tr><th>Name (EN / KO / rom)</th><th>Kind</th><th>Agency (소속사)</th><th>Skill Score</th><th>Translation</th><th>Freshness</th><th>Snapshots</th><th>Sources (provenance)</th><th>Summary (EN)</th></tr>
{''.join(rows)}
</table>
<footer>Generated {generated} &middot; KoreaAPI Phase 1 (cold-start) &middot; verifiable Korean-culture data for AI agents &middot; <a href="./llms.txt">/llms.txt</a> &middot; <a href="https://github.com/wrxfoundation/weatherplan-ai">GitHub</a></footer>
</body></html>"""
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(doc)
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
        "<https://wrxfoundation.github.io/weatherplan-ai/> · via KoreaAPI (MCP).",
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
        "MCP tools: get_artist_status, get_agency, get_kculture_calendar, get_korea_rising, get_buy_options.",
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
        f"<tr><td>cross-verified (≥2 sources)</td><td>{xver}</td><td>{bar(xver, total, '#7DA2FF')}</td></tr>"
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
        f"<tr><td>{d}</td><td>{c}</td><td>{bar(c, dmax, '#7DA2FF')}</td></tr>"
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
    empty = '<td colspan=2 style="color:#6B7585">none yet — fills once the MCP server is live + agents call it</td>'
    usage = "".join(f"<tr><td>{html.escape(s['key'])}</td><td>{s['count']}</td></tr>" for s in sig_q) or f"<tr>{empty}</tr>"
    buys = "".join(f"<tr><td>{html.escape(s['key'])}</td><td>{s['count']}</td></tr>" for s in sig_b) or f"<tr>{empty}</tr>"
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    doc = f"""<!doctype html><html><head><meta charset="utf-8">
<title>KoreaAPI · Monitor</title><meta name="robots" content="noindex">
<style>
 body{{font-family:system-ui,-apple-system,sans-serif;background:#0A0E1A;color:#F5F7FA;margin:0;padding:24px}}
 h1{{margin:0 0 2px}} h2{{font-size:14px;color:#A0AEC0;margin:22px 0 8px}} .sub{{color:#A0AEC0;margin-bottom:18px;font-size:13px}}
 .cards{{display:flex;gap:12px;flex-wrap:wrap}} .card{{background:#131829;border:1px solid #2A3349;border-radius:10px;padding:12px 16px;min-width:120px}}
 .card .v{{font-size:24px;font-weight:700}} .card .k{{color:#A0AEC0;font-size:12px}}
 .grid{{display:flex;gap:18px;flex-wrap:wrap;align-items:flex-start}} .panel{{flex:1;min-width:300px}}
 table{{width:100%;border-collapse:collapse;background:#131829;border:1px solid #2A3349;border-radius:10px;overflow:hidden}}
 th,td{{padding:7px 12px;text-align:left;border-bottom:1px solid #1F2638;font-size:13px}} th{{color:#A0AEC0;background:#1A2036}}
 .bw{{background:#1F2638;border-radius:4px;height:10px;width:120px;overflow:hidden}} .b{{height:10px}}
 .pill{{color:#0A0E1A;font-weight:700;padding:1px 7px;border-radius:5px;font-size:12px}}
 .warn{{color:#F59E0B;font-weight:600}} .ok{{color:#10B981}} footer{{color:#6B7585;margin-top:18px;font-size:12px}}
</style></head><body>
<h1>KoreaAPI &middot; Monitor</h1>
<div class="sub">Data-quality cockpit over the append-only verified store. (Public view: <a href="./index.html" style="color:#7DA2FF">index.html</a>.)</div>
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
    elif cmd == "digest":
        print("wrote", asyncio.run(markdown_digest()))
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
