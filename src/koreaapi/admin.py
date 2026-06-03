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


async def sweep(*, db_path: str | None = None, max_new: int = 12, per_agency: int = 2) -> dict:
    """Agency-hub discovery: for each anchored 소속사 (Wikidata label), find FAMILY artists via
    SPARQL (same label or any sibling label under the same parent org) and ingest the NEW ones
    through the SAME Wikidata+Wikipedia cross-verification, so the verified roster grows from the
    agency hub ('정보가 계속 나온다') without lowering the bar. Balanced (a per-agency cap) so every
    family is represented, not just the best-covered one. Bounded per run; needs open network.
    """
    recs = await store.recent(2000, db_path=db_path)
    have = {r.entity_id for r in recs}
    agencies = _agency_qids_from_store(recs)
    todo: list[tuple[str, str]] = []
    seen: set[str] = set()
    n_candidates = 0
    for qid in agencies:
        try:
            mates = await asyncio.to_thread(fetch_labelmates, qid)
        except Exception:
            mates = []  # graceful: skip an agency whose SPARQL failed
        n_candidates += len(mates)
        taken = 0
        for m in mates:  # per-agency cap -> balanced representation across families
            eid = f"artist:{m['slug']}"
            if eid in have or m["slug"] in seen:
                continue
            seen.add(m["slug"])
            todo.append((eid, m["en"]))
            taken += 1
            if taken >= per_agency or len(todo) >= max_new:
                break
        if len(todo) >= max_new:
            break
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
    return json.dumps(doc, ensure_ascii=False, indent=2)


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
                f"chart: 0 entries - diagnosing: ANTHROPIC_API_KEY present={key}, fetched HTML "
                f"{html_len} bytes. HTML=0 -> fetch blocked; HTML>0 but 0 entries -> the page is "
                "JS-rendered (set CIRCLECHART_URL to a data/JSON endpoint); key=False -> add the secret."
            )
        else:
            asyncio.run(ingest_chart(chart, db_path=None))
            top = chart["entries"][0]
            print(f"chart: ingested top {n} -> #1 {top['artist']} - {top.get('title', '')}")
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
