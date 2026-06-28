# KoreaAPI — deploy the paid HTTP API (x402 + verified-data + resolve endpoints) as a REMOTE endpoint.
# Works on any Docker host (Railway / Render / Fly / Cloud Run). The container hydrates its DB from the
# published open data at boot (see deploy/start.sh), then serves the API. To also run a REMOTE MCP
# server, set MCP_TRANSPORT=http and run `python -m koreaapi.server` instead.
FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir uv
COPY pyproject.toml uv.lock ./
COPY src ./src
RUN uv sync --frozen --extra web
COPY deploy/start.sh ./deploy/start.sh
ENV PYTHONPATH=/app/src \
    KOREAAPI_DB=/app/koreaapi.db \
    KOREAAPI_DATA_URL=https://kwangdol-star.github.io/koreaapi/latest.json \
    PORT=8000
EXPOSE 8000
CMD ["sh", "deploy/start.sh"]
