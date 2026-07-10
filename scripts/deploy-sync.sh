#!/usr/bin/env bash
# One-command deploy: sync this repo's koreaapi source into the koreaapi/ SUBTREE on the GitHub
# Pages deploy branch (claude/deploy-vercel-DwbJL) and push — which triggers the pages build that
# publishes aiagentlabs.co.kr. Idempotent (no-op when already in sync).
#
#   Usage:  GITHUB_TOKEN=<token-with-push> scripts/deploy-sync.sh
#
# Why this exists: development happens on the koreaapi-standalone branch, but the LIVE site is built
# from the koreaapi/ subtree on the deploy branch. This bridges the two in one step so a code change
# never silently sits undeployed (the multi-week freeze this fixes). The pages workflow's hub cp is a
# glob (site/*.html), so a new vertical needs NO workflow edit — just run this after your commit.
set -euo pipefail

DEPLOY_BRANCH="claude/deploy-vercel-DwbJL"
REPO_URL="https://github.com/wrxfoundation/weatherplan-ai.git"
TOKEN="${GITHUB_TOKEN:-${GH_TOKEN:-}}"
[ -n "$TOKEN" ] || { echo "error: set GITHUB_TOKEN (or GH_TOKEN) to a token with push access." >&2; exit 1; }

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AUTH="AUTHORIZATION: bearer ${TOKEN}"
WT="$(mktemp -d)"
cleanup() { git -C "$ROOT" worktree remove --force "$WT" >/dev/null 2>&1 || rm -rf "$WT"; }
trap cleanup EXIT

echo "fetching $DEPLOY_BRANCH ..."
git -C "$ROOT" -c http.https://github.com/.extraheader="$AUTH" fetch -q "$REPO_URL" "$DEPLOY_BRANCH"
git -C "$ROOT" worktree add -q --detach "$WT" FETCH_HEAD

echo "syncing src/ + tests/ into koreaapi/ ..."
rm -rf "$WT/koreaapi/src" "$WT/koreaapi/tests"
cp -a "$ROOT/src" "$WT/koreaapi/src"
cp -a "$ROOT/tests" "$WT/koreaapi/tests"
find "$WT/koreaapi/src" "$WT/koreaapi/tests" \( -name __pycache__ -o -name .pytest_cache \) -type d -prune -exec rm -rf {} + 2>/dev/null || true
find "$WT/koreaapi/src" "$WT/koreaapi/tests" \( -name '*.pyc' -o -name '*.db' \) -delete 2>/dev/null || true

git -C "$WT" add -A
if git -C "$WT" diff --cached --quiet; then
  echo "deploy branch already in sync — nothing to push."
  exit 0
fi
git -C "$WT" -c user.name="koreaapi deploy-sync" -c user.email="deploy-sync@local" \
  commit -q -m "chore(koreaapi): sync koreaapi/ subtree from source"
echo "pushing to $DEPLOY_BRANCH (triggers the pages build) ..."
git -C "$WT" -c http.https://github.com/.extraheader="$AUTH" push "$REPO_URL" HEAD:"refs/heads/$DEPLOY_BRANCH"
echo "done — watch the 'pages' workflow; the site publishes when it completes."
