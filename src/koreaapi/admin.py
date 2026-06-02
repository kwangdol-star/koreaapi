"""Human data console for KoreaAPI (read-only ops view over the append-only store).

The product is agent-facing (MCP), but a verifiable-data business needs a human
cockpit: browse what was collected, watch data quality (Skill Score / freshness /
source agreement), and spot-correct. This is Face 2 over the SAME source of truth
agents read - never a second data path.

CLI:
  python -m koreaapi.admin seed     # populate koreaapi.db with sample snapshots (offline)
  python -m koreaapi.admin pull     # LIVE: pull real Wikidata snapshots (needs network egress)
  python -m koreaapi.admin stats    # print a data-quality summary
  python -m koreaapi.admin dump     # print recent snapshots
  python -m koreaapi.admin report   # write report.html (open it in a browser)

For zero-code interactive browse / query / JSON API:  datasette koreaapi.db
"""

from __future__ import annotations

import asyncio
import html
import sys
from datetime import datetime, timezone

from .pipeline import store
from .pipeline.ingest import ingest_one
from .pipeline.scheduler import CADENCE
from .sources.mock import MockSource
from .sources.wikidata import WikidataSource, _CURATED

# Offline sample data for `seed` (replace with real source adapters later).
# The third entry has a single source -> demonstrates the single-source Skill cap.
_SAMPLES = [
    ("comeback", "artist:bts", {
        "name_ko": "방탄소년단", "name_en_official": "BTS", "name_romanized": "Bangtan Sonyeondan",
        "name_en_source": "official", "date": "2026-06-13",
        "summary_en": "BTS comeback scheduled 2026-06-13.",
        "summary_ko": "방탄소년단 컴백 2026-06-13.",
    }, 2),
    ("chart", "artist:newjeans", {
        "name_ko": "뉴진스", "name_en_official": "NewJeans", "name_romanized": "Nyujinseu",
        "name_en_source": "official", "rank": 1,
        "summary_en": "NewJeans #1 on the weekly chart.",
        "summary_ko": "뉴진스 주간 차트 1위.",
    }, 2),
    ("comeback", "artist:aespa", {
        "name_ko": "에스파", "name_en_official": "aespa", "name_romanized": "Eseupa",
        "name_en_source": "official", "date": "2026-07-01",
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
    """Live-pull curated artists from Wikidata and append REAL verified snapshots.

    The turnkey live ingestion (component A, live): for each entity it fetches the
    bilingual labels from Wikidata, identity-verifies them, computes Skill Score +
    provenance, and appends a snapshot. Needs network egress to www.wikidata.org; where
    egress is blocked (e.g. the sandbox allowlist) each fetch is dropped by graceful
    degradation and the entity is reported as failed - nothing is appended (never poison).
    """
    ids = entity_ids or list(_CURATED)
    src = WikidataSource()  # one instance memoizes any live Q-id lookups
    ingested: list[str] = []
    failed: list[str] = []
    for entity_id in ids:
        rec = await ingest_one("facts", entity_id, [src], db_path=db_path)
        (ingested if rec is not None else failed).append(entity_id)
    return {"requested": ids, "ingested": ingested, "failed": failed}


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


async def report_html(db_path: str | None = None, out_path: str = "report.html") -> str:
    ents = await store.entities(db_path=db_path)
    s = await stats(db_path=db_path)
    rows = []
    for e in ents:
        rec = await store.latest(e["entity_id"], e["kind"], db_path=db_path)
        if rec is None:
            continue
        sc = rec.provenance.skill_score
        color = "#10B981" if sc >= 0.8 else ("#F59E0B" if sc >= 0.5 else "#EF4444")
        is_fresh = _fresh(e["latest_at"], e["kind"])
        rows.append(
            "<tr>"
            f"<td><b>{html.escape(rec.name.en_official or '')}</b>"
            f"<br><span class=ko>{html.escape(rec.name.ko)}</span>"
            f"<br><span class=rom>{html.escape(rec.name.romanized or '')}</span></td>"
            f"<td>{html.escape(e['kind'])}</td>"
            f"<td><span class=badge style=\"background:{color}\">"
            f"{sc:.2f} {html.escape(rec.provenance.confidence)}</span></td>"
            f"<td>{html.escape(rec.provenance.translation.source)}</td>"
            f"<td class={'fresh' if is_fresh else 'stale'}>{'fresh' if is_fresh else 'STALE'}</td>"
            f"<td>{e['snapshots']}</td>"
            f"<td>{html.escape('; '.join(rec.provenance.sources))}</td>"
            f"<td>{html.escape(rec.summary_en)}</td>"
            "</tr>"
        )
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    doc = f"""<!doctype html><html><head><meta charset="utf-8">
<title>KoreaAPI - Data Console</title>
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
</style></head><body>
<h1>KoreaAPI &middot; Data Console</h1>
<div class="sub">Read-only human view over the append-only store. Agents read the same store via MCP.</div>
<div class="cards">
 <div class="card"><div class="v">{s.get('entities', 0)}</div><div class="k">entities</div></div>
 <div class="card"><div class="v">{s.get('snapshots', 0)}</div><div class="k">snapshots (append-only)</div></div>
 <div class="card"><div class="v">{s.get('avg_skill_score', '-')}</div><div class="k">avg Skill Score</div></div>
 <div class="card"><div class="v">{s.get('fresh_entities', '-')}</div><div class="k">fresh</div></div>
 <div class="card"><div class="v">{s.get('low_confidence', 0)}</div><div class="k">low confidence</div></div>
</div>
<table>
<tr><th>Name (EN / KO / rom)</th><th>Kind</th><th>Skill Score</th><th>Translation</th><th>Freshness</th><th>Snapshots</th><th>Sources (provenance)</th><th>Summary (EN)</th></tr>
{''.join(rows)}
</table>
<footer>Generated {generated} &middot; KoreaAPI Phase 1 &middot; interactive query: <code>datasette koreaapi.db</code></footer>
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
    else:
        print(f"unknown command: {cmd}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv))
