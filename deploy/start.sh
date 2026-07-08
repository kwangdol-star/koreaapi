#!/bin/sh
# Boot the KoreaAPI HTTP API on a host. The container has no committed DB, so hydrate it from the
# PUBLISHED open data (latest.json on Pages) — Pages is the data source, this is the live API face.
# Best-effort: if the data isn't reachable yet, serve an empty store (found:false) rather than crash.
mkdir -p data
if uv run python -c "import urllib.request,os;urllib.request.urlretrieve(os.environ.get('KOREAAPI_DATA_URL','https://aiagentlabs.co.kr/latest.json'),'data/latest.json')"; then
  uv run python -m koreaapi.admin load || echo "load failed — serving empty store"
else
  echo "hydrate skipped (data not reachable) — serving empty store until it is"
fi
exec uv run --extra web uvicorn koreaapi.api:app --host 0.0.0.0 --port "${PORT:-8000}"
