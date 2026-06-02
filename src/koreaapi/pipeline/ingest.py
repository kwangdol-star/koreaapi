"""Ingestion flow: fetch -> extract -> verify -> bilingual-normalize -> append.

Component A from SCOPE.md S4. Runs unattended on a tiered schedule (scheduler.py).
On source failure: skip that source and lower confidence (graceful degradation) -
never break the loop. Overwrite = wrapper; append = asset.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone

from ..models import Name, Provenance, Record, TranslationProvenance
from ..skill_score import compute_skill_score, to_confidence
from . import store
from .scheduler import CADENCE


def _build_name(payload: dict) -> Name:
    """Bilingual normalization: prefer the official English/stage name over translation."""
    return Name(
        ko=payload["name_ko"],
        en_official=payload.get("name_en_official"),
        romanized=payload.get("name_romanized"),
        en_source=payload.get("name_en_source", "llm"),
        en_confidence=payload.get("name_en_confidence", "medium"),
    )


async def ingest_one(
    kind: str,
    entity_id: str,
    sources: list,
    *,
    db_path: str | None = None,
) -> Record | None:
    """Run one ingestion unit for a single entity + kind, then append a snapshot.

    Steps: fetch each source -> cross-verify (agreement) -> bilingual-normalize
    (official EN first) -> compute Skill Score + Provenance -> append (never overwrite).
    """
    payloads: list[dict] = []
    citations: list[str] = []
    used_fallback: list[bool] = []
    for src in sources:
        try:
            res = await src.fetch(entity_id, kind)
        except Exception:
            continue  # graceful degradation: drop the failed source, keep going
        payloads.append(res["payload"])
        citations.append(res["citation"])
        used_fallback.append(bool(getattr(src, "is_fallback", False)))

    if not payloads:
        return None  # nothing usable this cycle

    # cross-verify: how many sources agree on the canonical payload?
    cores = [json.dumps(p, sort_keys=True, ensure_ascii=False) for p in payloads]
    modal_core, n_agree = Counter(cores).most_common(1)[0]
    chosen = payloads[cores.index(modal_core)]

    name = _build_name(chosen)
    translation_official = (
        chosen.get("name_en_source") == "official"
        and chosen.get("title_en_source", "official") == "official"
    )

    score = compute_skill_score(
        age_seconds=0,  # freshly fetched
        ttl_seconds=CADENCE.get(kind, 86400),
        n_sources_agree=n_agree,
        n_sources_total=len(payloads),
        used_fallback_only=all(used_fallback) if used_fallback else False,
        translation_official=translation_official,
    )

    now = datetime.now(timezone.utc)
    record = Record(
        entity_id=entity_id,
        kind=kind,
        name=name,
        snapshot_at=now,
        summary_en=chosen.get("summary_en", ""),
        summary_ko=chosen.get("summary_ko"),
        data=chosen,
        provenance=Provenance(
            sources=citations,
            fetched_at=now,
            skill_score=score,
            confidence=to_confidence(score),
            translation=TranslationProvenance(
                source="official" if translation_official else "llm",
                confidence="high" if translation_official else "medium",
            ),
            cache_age_seconds=0,
        ),
    )

    await store.append_record(record, db_path=db_path)
    return record
