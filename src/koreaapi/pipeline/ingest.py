"""Ingestion flow: fetch -> extract -> verify -> bilingual-normalize -> append.

Component A from SCOPE.md S4. Runs unattended on a tiered schedule (scheduler.py).
On source failure: skip that source and lower confidence (graceful degradation) -
never break the loop. Overwrite = wrapper; append = asset.
"""

from __future__ import annotations

import asyncio
from collections import Counter
from datetime import datetime, timezone

from ..models import Name, Provenance, Record, TranslationProvenance
from ..romanize import romanize
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


def _verify_key(payload: dict) -> str:
    """The canonical fields sources must agree on to count as cross-verified: the bilingual
    NAME, case/space-normalized. Prose summaries are excluded, so two independent sources that
    agree on *who this is* (e.g. Wikidata + Wikipedia) raise the Skill Score above the
    single-source cap."""
    ko = (payload.get("name_ko") or "").casefold().replace(" ", "")
    en = (payload.get("name_en_official") or "").casefold().replace(" ", "")
    return f"{ko}|{en}"


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

    # cross-verify on the canonical FACTS (bilingual name), not the prose summary, so two
    # independent sources that agree on who this is count as agreement (raising Skill Score).
    keys = [_verify_key(p) for p in payloads]
    modal_key, n_agree = Counter(keys).most_common(1)[0]
    chosen = payloads[keys.index(modal_key)]

    if not chosen.get("name_romanized") and chosen.get("name_ko"):
        rom = await asyncio.to_thread(romanize, chosen["name_ko"])  # cheap LLM; best-effort
        if rom:
            chosen["name_romanized"] = rom

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


async def ingest_chart(chart: dict, *, db_path: str | None = None) -> Record | None:
    """Append a Circle Chart weekly snapshot (kind='chart') - settlement-grade outcome data.

    One official source, so the Skill Score is single-source-capped (honest: un-cross-verified).
    Empty entries (egress blocked / no key / page changed) -> nothing appended (never break).
    """
    entries = chart.get("entries") or []
    if not entries:
        return None
    now = datetime.now(timezone.utc)
    top = entries[0]
    score = compute_skill_score(
        age_seconds=0,
        ttl_seconds=CADENCE.get("charts", 43200),
        n_sources_agree=1,
        n_sources_total=1,
        used_fallback_only=False,
        translation_official=True,
    )
    record = Record(
        entity_id="chart:circle-digital",
        kind="chart",
        name=Name(ko="써클 디지털 차트", en_official="Circle Digital Chart"),
        snapshot_at=now,
        summary_en=f"Circle Digital Chart - {len(entries)} weekly #1s (current #1: {top['artist']} - {top.get('title', '')}).",
        summary_ko=f"써클 디지털 차트 - 주간 1위 {len(entries)}건 (현재 1위: {top['artist']}).",
        data={"entries": entries, "source_url": chart.get("source_url")},
        provenance=Provenance(
            sources=[chart.get("citation", "Circle Chart")],
            fetched_at=now,
            skill_score=score,
            confidence=to_confidence(score),
        ),
    )
    await store.append_record(record, db_path=db_path)
    return record


async def ingest_youtube(
    entity_id: str, payload: dict | None, *, db_path: str | None = None
) -> Record | None:
    """Append a YouTube official-channel snapshot (kind='release') - live-state event data.

    One official source (the artist's own channel), so the Skill Score is single-source-capped
    (honest: not cross-verified). Feeds the prediction-market vertical (release / milestone
    outcomes) + engine 2 (view velocity). No payload (no key / unresolved channel / blocked /
    failed the identity guard) -> nothing appended (graceful, never break).
    """
    if not payload or not payload.get("channel_id"):
        return None
    now = datetime.now(timezone.utc)
    name_en = payload.get("name_en") or payload.get("title") or entity_id.split(":", 1)[-1]
    subs, views = payload.get("subscribers"), payload.get("views")
    latest = payload.get("latest") or {}
    score = compute_skill_score(
        age_seconds=0,
        ttl_seconds=CADENCE.get("events", 86400),
        n_sources_agree=1,
        n_sources_total=1,  # single official source -> capped at 0.7 (honest)
        used_fallback_only=False,
        translation_official=True,
    )
    stat_parts = []
    if subs is not None:
        stat_parts.append(f"{subs:,} subscribers")
    if views is not None:
        stat_parts.append(f"{views:,} views")
    stat = ", ".join(stat_parts) if stat_parts else "channel stats"
    rel = ""
    if latest.get("title"):
        rel = f"; latest: '{latest['title']}' ({(latest.get('published_at') or '')[:10]})"
    record = Record(
        entity_id=entity_id,
        kind="release",
        name=Name(ko=name_en, en_official=name_en, en_source="official", en_confidence="high"),
        snapshot_at=now,
        summary_en=f"{name_en} - YouTube official channel: {stat}{rel}.",
        summary_ko=f"{name_en} - 유튜브 공식 채널: {stat}{rel}.",
        data={
            "channel_id": payload["channel_id"],
            "channel_title": payload.get("title"),
            "subscribers": subs,
            "views": views,
            "videos": payload.get("videos"),
            "latest": latest or None,
            "source_url": payload.get("source_url"),
        },
        provenance=Provenance(
            sources=[payload.get("citation", "YouTube Data API")],
            fetched_at=now,
            skill_score=score,
            confidence=to_confidence(score),
        ),
    )
    await store.append_record(record, db_path=db_path)
    return record
