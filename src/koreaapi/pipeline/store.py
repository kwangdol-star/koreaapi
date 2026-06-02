"""Append-only store. The single most important rule of KoreaAPI:

    OVERWRITE = WRAPPER.  APPEND = ASSET.

Every snapshot is inserted with its `snapshot_at` timestamp and never updated in
place. The accumulated history is the moat and the raw material for the trend
product (get_korea_rising).

Phase 1 dev backend is SQLite (zero setup); production swaps to Postgres behind
the same insert-only contract. Set the DB path via the KOREAAPI_DB env var, or
pass db_path explicitly (used by tests).
"""

from __future__ import annotations

import asyncio
import os
import sqlite3
from datetime import datetime, timezone

from ..models import Record

_DDL = """
CREATE TABLE IF NOT EXISTS snapshots (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id   TEXT NOT NULL,
    kind        TEXT NOT NULL,
    snapshot_at TEXT NOT NULL,
    skill_score REAL NOT NULL,
    record_json TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_snapshots_entity
    ON snapshots (entity_id, kind, snapshot_at DESC);
"""


def _db_path(db_path: str | None) -> str:
    return db_path or os.environ.get("KOREAAPI_DB", "koreaapi.db")


def _connect(db_path: str | None) -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path(db_path))
    conn.executescript(_DDL)
    return conn


async def append_record(record: Record, *, db_path: str | None = None) -> int:
    """Insert a new immutable snapshot. INSERT-only; never update or delete prior rows.

    Returns the new row id.
    """

    def _do() -> int:
        conn = _connect(db_path)
        try:
            cur = conn.execute(
                "INSERT INTO snapshots "
                "(entity_id, kind, snapshot_at, skill_score, record_json, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    record.entity_id,
                    record.kind,
                    record.snapshot_at.isoformat(),
                    record.provenance.skill_score,
                    record.model_dump_json(),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            conn.commit()
            return int(cur.lastrowid)
        finally:
            conn.close()

    return await asyncio.to_thread(_do)


async def latest(entity_id: str, kind: str, *, db_path: str | None = None) -> Record | None:
    """Return the most recent snapshot for serving MCP tools."""

    def _do() -> str | None:
        conn = _connect(db_path)
        try:
            row = conn.execute(
                "SELECT record_json FROM snapshots WHERE entity_id = ? AND kind = ? "
                "ORDER BY snapshot_at DESC, id DESC LIMIT 1",
                (entity_id, kind),
            ).fetchone()
            return row[0] if row else None
        finally:
            conn.close()

    raw = await asyncio.to_thread(_do)
    return Record.model_validate_json(raw) if raw else None


async def count(entity_id: str, kind: str, *, db_path: str | None = None) -> int:
    """Count snapshots for an entity+kind. Used to prove append-only accumulation."""

    def _do() -> int:
        conn = _connect(db_path)
        try:
            return int(
                conn.execute(
                    "SELECT COUNT(*) FROM snapshots WHERE entity_id = ? AND kind = ?",
                    (entity_id, kind),
                ).fetchone()[0]
            )
        finally:
            conn.close()

    return await asyncio.to_thread(_do)
