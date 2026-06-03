# Migrate `koreaapi/` to its own repository (history-preserving)

KoreaAPI currently lives in a subdirectory of `weatherplan-ai`. Splitting it into its own repo
(e.g. `kwangdol-star/koreaapi`) makes it cleanly publishable (PyPI, Smithery) and gives it its
own GitHub Pages URL. This preserves git history for the `koreaapi/` subtree.

## 1. Split the subtree (preserves history)

From a clone of `weatherplan-ai`, on the branch that has the latest KoreaAPI work
(`claude/eager-knuth-Vnzca`, or after it's merged):

```bash
git subtree split --prefix=koreaapi -b koreaapi-standalone
# -> creates a local branch `koreaapi-standalone` whose ROOT is the koreaapi/ contents, with history
```

Use [`scripts/split-koreaapi.sh`](../scripts/split-koreaapi.sh) to run this in one step.

## 2. Create the new repo + push

Create an empty `kwangdol-star/koreaapi` on GitHub (no README), then:

```bash
git push https://github.com/kwangdol-star/koreaapi.git koreaapi-standalone:main
```

## 3. Post-migration fixes (in the new repo)

Now that `koreaapi/` is the repo root, a few things that assumed the subdir must change:

- **Workflows** (`.github/workflows/*.yml`): remove `working-directory: koreaapi` and the
  `koreaapi/` path prefixes; change `cp ... ../_site/...` → `cp ... _site/...`; update the
  `push.branches` filter to `main`. (The build/pull/sweep/chart/youtube/digest steps are
  otherwise unchanged.)
- **Secrets** (repo → Settings → Secrets and variables → Actions): re-add `ANTHROPIC_API_KEY`
  and `YOUTUBE_API_KEY` (same values).
- **Pages**: Settings → Pages → Source: GitHub Actions. Deploying from `main` needs no
  `github-pages` environment branch restriction (that was only needed for the feature branch).
- **Public URL changes** to `https://kwangdol-star.github.io/koreaapi/`. Update it in:
  `README.md`, `llms.txt`, `docs/LAUNCH.md`, `docs/MCP_INSTALL.md`, the page meta/JSON-LD base
  in `admin.py`, and the digest URL in `admin.py` (`markdown_digest`).
- **User-Agent contact** in the source adapters (`sources/wikidata.py`, `wikipedia.py`,
  `youtube.py`, `circlechart.py`): the `_UA` string references
  `github.com/wrxfoundation/weatherplan-ai` — point it at the new repo (Wikimedia UA policy
  asks for a reachable contact).
- **Smithery**: `smithery.yaml` is now publishable from the standalone repo root — list it.

Quick find of everything to repoint:

```bash
grep -rn "wrxfoundation/weatherplan-ai\|wrxfoundation.github.io/weatherplan-ai" . \
  --include=*.py --include=*.md --include=*.txt --include=*.yml
```

## 4. Sanity check in the new repo

```bash
uv sync && uv run pytest -q && uv run ruff check src tests   # 57 passed, 3 skipped, clean
```

Then push a commit to trigger the `pages` workflow and confirm the new public URL builds.

> Tip: keep the `weatherplan-ai` copy until the new repo's Pages + secrets are confirmed green,
> then archive/remove the subdir there to avoid two sources of truth.
