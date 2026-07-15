# OPERATIONS — how KoreaAPI runs itself

The operator's map: what runs when, what each safety system does, and what to check when something
looks wrong. (What we believe: `PRINCIPLES.md` · what we ship: `SCOPE.md` / `ROADMAP.md` · how it
looks: `DESIGN_HERITAGE.md`.)

## The two pipelines

**collect** (`.github/workflows/collect.yml`, every 6h: 00:17/06:17/12:17/18:17 UTC) — the data engine.
Accumulates the verified DB across runs via the Actions cache (out of git; immune to force-push).

| step | what it does |
|---|---|
| `pull` | re-verifies the curated roster (~650 seeds) through the full cross-verification source list |
| `refresh 400` | re-verifies the **stalest discovered entities** (see Freshness model below) |
| `sweep` | agency-hub SPARQL discovery — new labelmates, same verification bar |
| `discover` | bulk per-vertical discovery (the "10x") — new entities only, identity-guarded |
| `audit fix` / `prune` | store-wide P31 type re-check + removal of mis-discovered items (hard delete; refresh cannot resurrect them) |
| `chart` / `youtube` | once daily at the 00 UTC tick (quota + LLM cost) |
| `export` / `digest` / `stats` | data/latest.json + snapshots.jsonl + korea-rising.md + counters |

**pages** (`.github/workflows/pages.yml`, on push to main + daily 01:37 UTC + after each collect) — the
site build. Restores the collect DB (read-only), regenerates every surface, then:

- assembles `_site/` (globbed copies: `cp site/*.html`, `cp llms*.txt`, explicit `search-index.json`)
- **`verifysite _site 100` — the pre-deploy gate.** Index size, sitemap ≥100 URLs on our host, search
  index ≥100 entries, `artist/` + `ko/artist/` page counts, key files present. A generator regression
  or a lost DB cache fails the build here and GitHub Pages keeps serving the previous good deployment
  — freeze beats broken (the 5-week-freeze lesson, inverted).

## Freshness model (why nothing should stay stale)

- `facts` TTL = 7 days (`pipeline/scheduler.CADENCE`); the Fresh badge / `status.json:fresh` read it.
- `pull` keeps the roster fresh, but discovery only ADDs — so `refresh` re-verifies discovered
  entities: eligible at **half-TTL** (refresh-before-stale), **oldest first**, budget **stride-sampled**
  across the pool so a permanently-failing entity (deleted/renamed upstream) costs one slot per run
  instead of starving the tail. 400/run × 4 runs/day ⇒ the ~5k store cycles in ~3 days < TTL.
- Refresh re-ingests through the same cross-verification path the entity was discovered with (stored
  name as the search alias + the memoized Wikidata Q-id from provenance). The identity guard still
  applies: upstream drift ⇒ a MISS, never a wrong record.
- **No downgrades:** a cross-verified record refreshes only if ≥2 sources answer that cycle
  (`ingest_one(min_sources=2)`), and verified P625 coordinates carry forward when the coord-bearing
  source fails a cycle — an outage never demotes a tier or drops an entity off the map features.
- Watch it drain: `status.json` → `stale` (past TTL), `refresh_pool` (past half-TTL = what refresh
  targets next), `oldest_snapshot_days`. Expect `stale → ~0` within ~3 days of collect running.

## AI usage (all grounded, all best-effort, all key-gated on ANTHROPIC_API_KEY)

| where | model | gate |
|---|---|---|
| `romanize.py` — name romanization | Haiku | retries each build until it succeeds |
| `enrich.py` — attrs + aliases from the cited Wikipedia lead | Haiku | every value must appear **literally** in the abstract; run-once per entity (marker only stored on a REAL run, so transient failures self-heal) |
| `sources/circlechart.py` — weekly #1 extraction | Haiku | `_grounded` drops anything not literally on the page |
| `answers.route()` — free-text → Answer Product | Haiku | pure keyword fallback (works keyless); routing only CHOOSES, the verified product decides |

Hallucination cannot enter a record: extraction is labor, grounding is the gate.

## Dormant rails (INERT until the env key exists — activation is adding a repo secret)

`TMDB_API_KEY` · `TOURAPI_KEY` (KTO) · `KOSIS_API_KEY` · `KOPIS_API_KEY` (theaters) ·
`KHERITAGE_API_KEY` (+ `KHERITAGE_URL` override; verify the field shape on first activation) ·
`YOUTUBE_API_KEY` · x402/Stripe payment rails. A missing key is a graceful skip, never an error.

## Surfaces inventory (everything the build ships)

- **Per-entity**: `/artist/<slug>.html` + `/ko/artist/…` (FAQ leads with a grounded "What is X?",
  nearby ≤30 km from verified P625, region-guide backlink, label-hub link, source-reconciliation note,
  Also-known-as, badge SVG, JSON-LD: typed node + sameAs + alternateName + dateModified + isPartOf +
  license + identifier + FAQPage + Breadcrumb).
- **Hubs**: 40 vertical hubs (+/ko/), `/people.html`, `/label/<slug>.html` (+/ko/), region guides
  `/guide-<region>.html` (+/ko/, walkable clusters + TouristTrip), food guides `/food-<diet>.html`
  (+/ko/), `/guides.html` index (+/ko/), `/whats-new.html` (+/ko/), `/search.html` (+/ko/, ?q= deep
  links) over `search-index.json` (entities + people + labels), custom `/404.html`.
- **Machine**: `/latest.json` · `/changes.json` · `/reconcile.json` · `/status.json` · `/integrity.json`
  (+ append-only log; OpenTimestamps when enabled) · `/certified.json` · `/openapi.json` ·
  `/agents.json` · `/feed.xml` · `/feed.json` · `/llms.txt` · `/llms-full.txt` · per-vertical
  `/llms-<vertical>.txt` chunks · `/sitemap.xml` · `/robots.txt`.
- **API/MCP**: 16 MCP tools (incl. `ask` free-text router, `get_answer` over 11 Answer Products —
  canonical-name · fact-check · identity-resolve · trend-radar · agency-roster · person-credits ·
  related-network(+nearby) · trip-plan(map-ready + walkable clusters) · food-guide · compare ·
  evidence-pack) + the same over HTTP `/v1/*` (`/v1/answer?product=auto` = ask).

## Verification layers (what protects a deploy)

1. `test.yml` — full offline suite (~350) + ruff on every push.
2. `tests/test_frontend_integrity.py` — builds the real site, validates every JSON-LD block, link,
   badge SVG, placeholder/None leak.
3. Adversarial-data QA (session scratch scripts) — naive datetimes, junk aliases, string coords,
   quote-heavy names must build clean.
4. `verifysite` — the pre-deploy gate on the assembled `_site` (above).

## Deploying (the standalone → live flow)

Work lands on `wrxfoundation/weatherplan-ai:koreaapi-standalone` (public mirror). The live repo is
`kwangdol-star/koreaapi` (`main` → pages workflow → aiagentlabs.co.kr). To ship:

```
cd <local koreaapi checkout>
git fetch https://github.com/wrxfoundation/weatherplan-ai.git koreaapi-standalone
git reset --hard FETCH_HEAD
git log --oneline origin/main..HEAD   # review the delta before pushing
git push origin main
```

Never force-push `main` (history is the time-moat). If push is rejected as non-fast-forward, STOP and
compare — someone/something moved `main`.

## When something looks wrong

- **"Everything is stale"** → is `collect` green and running every 6h? Then watch `status.json:stale`
  drain (~3 days). If a specific entity never refreshes, it may be an upstream-deleted zombie — it
  costs one stride slot and is otherwise harmless; `prune` it if it's genuinely dead.
- **Site didn't update** → Actions → `pages`: red at `verifysite` means the gate saved you — read its
  ✗ lines. Red earlier = a build error; the previous site is still being served either way.
- **A wrong name/fact on a page** → check the entity page's Source-reconciliation note + provenance;
  fix = correct the roster/alias, never hand-edit output (everything regenerates).
- **Suspected cache poisoning of enrichment** → `data.enrichment` on the record shows exactly what the
  one-time extraction grounded; delete the entity's records and let refresh re-derive if needed.
