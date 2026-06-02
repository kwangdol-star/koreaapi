"""Append-only store. The single most important rule of KoreaAPI:

    OVERWRITE = WRAPPER.  APPEND = ASSET.

Every snapshot is inserted with its `snapshot_at` timestamp and never updated in
place. The accumulated history is the moat and the raw material for the trend
product (get_korea_rising). Phase 1 may back this with Postgres; the contract is
append-only regardless of backend.
"""

from __future__ import annotations

from ..models import Record


async def append_record(record: Record) -> None:
    """Insert a new immutable snapshot. Must never update or delete prior rows."""
    raise NotImplementedError("Phase 1: implement append-only insert (Postgres).")


async def latest(entity_id: str, kind: str) -> Record | None:
    """Return the most recent snapshot for serving MCP tools."""
    raise NotImplementedError("Phase 1: implement read of newest snapshot.")
