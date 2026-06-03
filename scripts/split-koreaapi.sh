#!/usr/bin/env bash
# Split koreaapi/ into a standalone branch with full git history, ready to push to its own repo.
#
# Run from the weatherplan-ai repo ROOT, on the branch with the latest KoreaAPI work:
#     bash koreaapi/scripts/split-koreaapi.sh
# Then create an empty repo and:
#     git push https://github.com/kwangdol-star/koreaapi.git koreaapi-standalone:main
#
# See koreaapi/docs/MIGRATION.md for the full post-migration checklist (paths, secrets, Pages,
# URLs, User-Agent, Smithery).
set -euo pipefail

PREFIX="koreaapi"
BRANCH="koreaapi-standalone"

git rev-parse --is-inside-work-tree >/dev/null 2>&1 || { echo "error: not inside a git repo." >&2; exit 1; }
if [ ! -d "$PREFIX" ]; then
  echo "error: run this from the weatherplan-ai repo root (no ./$PREFIX directory here)." >&2
  exit 1
fi

echo "Splitting '$PREFIX/' into branch '$BRANCH' (preserving history)..."
git branch -D "$BRANCH" 2>/dev/null || true
git subtree split --prefix="$PREFIX" -b "$BRANCH"

cat <<EOF

✓ Done. Branch '$BRANCH' now has koreaapi/ at its root, with full history.

Next:
  1) Create an empty repo on GitHub (e.g. kwangdol-star/koreaapi, no README).
  2) git push https://github.com/kwangdol-star/koreaapi.git $BRANCH:main
  3) Follow koreaapi/docs/MIGRATION.md section 3 (workflow paths, secrets, Pages, URLs,
     User-Agent, Smithery), then 'uv run pytest -q' in the new repo to confirm green.
EOF
