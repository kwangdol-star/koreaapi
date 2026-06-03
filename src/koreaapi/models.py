"""Core data contracts for KoreaAPI.

Every stored record and every MCP response is bilingual and carries Provenance.
See SCOPE.md S5 (bilingual model) and S1/S4 (verification moat).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

TranslationSource = Literal["official", "llm", "human"]
Confidence = Literal["high", "medium", "low"]


def _to_utc(v: datetime) -> datetime:
    """Normalize a datetime to timezone-aware UTC. A naive value is assumed UTC.

    Keeps every stored timestamp aware + UTC so (a) sorting records never mixes naive/aware
    (which raises), and (b) ISO strings sort lexically == chronologically in SQLite ORDER BY.
    """
    return v.replace(tzinfo=timezone.utc) if v.tzinfo is None else v.astimezone(timezone.utc)


class Name(BaseModel):
    """A bilingual name. Prefer the official English/stage name over translation.

    e.g. 방탄소년단 -> ko='방탄소년단', en_official='BTS', romanized='Bangtan Sonyeondan'
    """

    ko: str
    en_official: Optional[str] = None
    romanized: Optional[str] = None
    en_source: TranslationSource = "llm"
    en_confidence: Confidence = "medium"


class TranslationProvenance(BaseModel):
    source: TranslationSource = "llm"
    confidence: Confidence = "medium"


class Provenance(BaseModel):
    """The competitive moat. Never omit this.

    Lets an agent decide whether to trust and cite a record.
    """

    sources: list[str]  # e.g. ["Circle Chart 2026-06-01 KST", "agency notice"]
    fetched_at: datetime
    skill_score: float = Field(ge=0.0, le=1.0)
    confidence: Confidence
    translation: TranslationProvenance = Field(default_factory=TranslationProvenance)
    cache_age_seconds: int = 0

    _utc_fetched = field_validator("fetched_at")(_to_utc)


class Record(BaseModel):
    """Base append-only record. Stored snapshots are never overwritten.

    `snapshot_at` makes the time-series reconstructable -> the moat.
    """

    entity_id: str  # stable key, e.g. "artist:bts"
    kind: str  # "comeback" | "chart" | "concert" | "price" | ...
    name: Name
    snapshot_at: datetime
    summary_en: str  # LLM-friendly, English-first
    summary_ko: Optional[str] = None
    data: dict  # kind-specific payload (bilingual fields inside)
    provenance: Provenance

    _utc_snapshot = field_validator("snapshot_at")(_to_utc)
