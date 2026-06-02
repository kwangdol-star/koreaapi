"""Ingestion flow: fetch -> extract -> verify -> bilingual-normalize -> append.

Component A from SCOPE.md S4. Runs unattended on a tiered schedule (scheduler.py).
On source failure: lower confidence and still record (graceful degradation) - never
break the loop. Overwrite = wrapper; append = asset.
"""

from __future__ import annotations

from ..models import Record


async def ingest_one(kind: str, entity_id: str, sources: list) -> Record | None:
    """Run one ingestion unit for a single entity + kind.

    Steps:
      1. fetch raw from each source (concurrently)
      2. LLM-extract structured fields
      3. cross-verify across sources; measure agreement
      4. bilingual-normalize: official EN name first, then romanize
      5. compute Skill Score + Provenance (skill_score.compute_skill_score)
      6. append (never overwrite) via store.append_record
    """
    raise NotImplementedError(
        "Phase 1: wire fetch/extract/verify/translate, then call store.append_record()."
    )
