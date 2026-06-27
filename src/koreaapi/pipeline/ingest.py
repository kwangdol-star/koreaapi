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
            payload, citation = res["payload"], res["citation"]  # inside try: a malformed source
        except Exception:                                        # dict (missing keys) is a failed
            continue  # graceful degradation: drop a failed/malformed source, never break the loop
        payloads.append(payload)
        citations.append(citation)
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

    # Agent-facing summary: the source's "X - facts (Wikidata labels)." is dev-ish + low-context.
    # For a verified profile build a natural bilingual sentence (name + agency); other kinds keep
    # the source's specific summary (e.g. "BTS comeback scheduled 2026-06-13").
    summary_en = chosen.get("summary_en", "")
    summary_ko = chosen.get("summary_ko")
    if kind == "facts" and entity_id.startswith(("drama:", "film:")):
        disp = name.en_official or name.ko
        ko_part = f" ({name.ko})" if name.ko and name.ko != disp else ""
        year = chosen.get("debut")
        cast = chosen.get("members") or []
        is_film = entity_id.startswith("film:")
        net = chosen.get("agency_en") or chosen.get("agency_ko")  # original network/platform (P449)
        directors = chosen.get("directors") or []
        noun_en, date_en = ("film", "Released") if is_film else ("drama (TV series)", "Aired")
        noun_ko, date_ko = ("K-영화", "개봉") if is_film else ("K-드라마", "방영")
        summary_en = (f"{disp}{ko_part} — verified Korean {noun_en}."
                      + (f" {date_en} {year}." if year else "")
                      + (f" On {net}." if net else "")
                      + (f" Directed by {', '.join(directors)}." if directors else "")
                      + (f" {len(cast)} verified cast." if cast else ""))
        summary_ko = (f"{name.ko} — 검증된 {noun_ko}."
                      + (f" {date_ko} {year}." if year else "")
                      + (f" 채널/플랫폼: {net}." if net else "")
                      + (f" 감독: {', '.join(directors)}." if directors else "")
                      + (f" 출연 {len(cast)}명 검증." if cast else ""))
    elif kind == "facts" and entity_id.startswith("webtoon:"):
        disp = name.en_official or name.ko
        ko_part = f" ({name.ko})" if name.ko and name.ko != disp else ""
        year = chosen.get("debut")
        platform = chosen.get("agency_en") or chosen.get("agency_ko")  # publisher/platform (P123)
        creators = chosen.get("members") or []  # author(s) (P50)
        summary_en = (f"{disp}{ko_part} — verified Korean webtoon."
                      + (f" Published {year}." if year else "")
                      + (f" On {platform}." if platform else "")
                      + (f" By {', '.join(creators)}." if creators else ""))
        summary_ko = (f"{name.ko} — 검증된 웹툰."
                      + (f" 연재 시작 {year}." if year else "")
                      + (f" 플랫폼: {platform}." if platform else "")
                      + (f" 작가: {', '.join(creators)}." if creators else ""))
    elif kind == "facts" and entity_id.startswith("place:"):
        disp = name.en_official or name.ko
        ko_part = f" ({name.ko})" if name.ko and name.ko != disp else ""
        region = chosen.get("agency_en") or chosen.get("agency_ko")  # located-in (P131)
        year = chosen.get("debut")
        summary_en = (f"{disp}{ko_part} — verified Korean place / attraction."
                      + (f" In {region}." if region else "")
                      + (f" Est. {year}." if year else ""))
        summary_ko = (f"{name.ko} — 검증된 한국 명소."
                      + (f" 위치: {region}." if region else "")
                      + (f" 조성 {year}." if year else ""))
    elif kind == "facts" and entity_id.startswith("food:"):
        disp = name.en_official or name.ko
        ko_part = f" ({name.ko})" if name.ko and name.ko != disp else ""
        summary_en = f"{disp}{ko_part} — verified Korean dish / food."
        summary_ko = f"{name.ko} — 검증된 한국 음식."
    elif kind == "facts" and entity_id.startswith("company:"):
        disp = name.en_official or name.ko
        ko_part = f" ({name.ko})" if name.ko and name.ko != disp else ""
        industry = chosen.get("agency_en") or chosen.get("agency_ko")  # industry (P452)
        year = chosen.get("debut")
        summary_en = (f"{disp}{ko_part} — verified Korean company."
                      + (f" Founded {year}." if year else "")
                      + (f" Industry: {industry}." if industry else ""))
        summary_ko = (f"{name.ko} — 검증된 한국 기업."
                      + (f" 설립 {year}." if year else "")
                      + (f" 산업: {industry}." if industry else ""))
    elif kind == "facts" and entity_id.startswith("brand:"):
        disp = name.en_official or name.ko
        ko_part = f" ({name.ko})" if name.ko and name.ko != disp else ""
        owner = chosen.get("agency_en") or chosen.get("agency_ko")  # owned-by (P127)
        year = chosen.get("debut")
        summary_en = (f"{disp}{ko_part} — verified Korean brand."
                      + (f" Est. {year}." if year else "")
                      + (f" Owned by {owner}." if owner else ""))
        summary_ko = (f"{name.ko} — 검증된 한국 브랜드."
                      + (f" 설립 {year}." if year else "")
                      + (f" 소유: {owner}." if owner else ""))
    elif kind == "facts" and entity_id.startswith("book:"):
        disp = name.en_official or name.ko
        ko_part = f" ({name.ko})" if name.ko and name.ko != disp else ""
        year = chosen.get("debut")
        authors = chosen.get("members") or []  # author(s) P50
        publisher = chosen.get("agency_en") or chosen.get("agency_ko")
        summary_en = (f"{disp}{ko_part} — verified Korean book."
                      + (f" Published {year}." if year else "")
                      + (f" By {', '.join(authors)}." if authors else "")
                      + (f" Publisher {publisher}." if publisher else ""))
        summary_ko = (f"{name.ko} — 검증된 한국 도서."
                      + (f" 출간 {year}." if year else "")
                      + (f" 저자: {', '.join(authors)}." if authors else "")
                      + (f" 출판사: {publisher}." if publisher else ""))
    elif kind == "facts" and entity_id.startswith("history:"):
        disp = name.en_official or name.ko
        ko_part = f" ({name.ko})" if name.ko and name.ko != disp else ""
        year = chosen.get("debut")
        summary_en = (f"{disp}{ko_part} — verified Korean history (dynasty / period / event)."
                      + (f" From {year}." if year else ""))
        summary_ko = (f"{name.ko} — 검증된 한국사 (왕조 / 시대 / 사건)."
                      + (f" 시작 {year}." if year else ""))
    elif kind == "facts":
        disp = name.en_official or name.ko
        ko_part = f" ({name.ko})" if name.ko and name.ko != disp else ""
        agency = chosen.get("agency_en") or chosen.get("agency_ko")
        debut = chosen.get("debut")
        members = chosen.get("members") or []
        noun = "artist" if entity_id.startswith("artist:") else "entity"
        summary_en = (
            f"{disp}{ko_part} — verified Korean {noun}."
            + (f" Debut {debut}." if debut else "")
            + (f" Agency: {agency}." if agency else "")
            + (f" {len(members)} members." if members else "")
        )
        summary_ko = (
            f"{name.ko} — 검증된 K-{'아티스트' if noun == 'artist' else '엔티티'}."
            + (f" 데뷔 {debut}." if debut else "")
            + (f" 소속사: {agency}." if agency else "")
            + (f" 멤버 {len(members)}명." if members else "")
        )
    # Drop the now-redundant prose from the stored payload (it duplicates summary_* + names above).
    data = {k: v for k, v in chosen.items() if k not in ("summary_en", "summary_ko")}

    record = Record(
        entity_id=entity_id,
        kind=kind,
        name=name,
        snapshot_at=now,
        summary_en=summary_en,
        summary_ko=summary_ko,
        data=data,
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
        summary_en=f"Circle Digital Chart - {len(entries)} weekly #1s (current #1: {top.get('artist', '')} - {top.get('title', '')}).",
        summary_ko=f"써클 디지털 차트 - 주간 1위 {len(entries)}건 (현재 1위: {top.get('artist', '')}).",
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
    # Borrow the cross-verified Korean name + romanization from the artist's facts record (pulled
    # earlier this cycle) so a release record doesn't carry English in its Korean field.
    facts = await store.latest(entity_id, "facts", db_path=db_path)
    name_ko = (facts.name.ko if facts and facts.name.ko else None) or name_en
    name_rom = facts.name.romanized if facts else None
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
    en_parts, ko_parts = [], []
    if subs is not None:
        en_parts.append(f"{subs:,} subscribers")
        ko_parts.append(f"구독자 {subs:,}명")
    if views is not None:
        en_parts.append(f"{views:,} views")
        ko_parts.append(f"조회수 {views:,}회")
    stat_en = ", ".join(en_parts) if en_parts else "channel stats"
    stat_ko = ", ".join(ko_parts) if ko_parts else "채널 통계"
    date = (latest.get("published_at") or "")[:10]
    rel_en = f"; latest: '{latest['title']}' ({date})" if latest.get("title") else ""
    rel_ko = f"; 최신: '{latest['title']}' ({date})" if latest.get("title") else ""
    record = Record(
        entity_id=entity_id,
        kind="release",
        name=Name(ko=name_ko, en_official=name_en, romanized=name_rom, en_source="official", en_confidence="high"),
        snapshot_at=now,
        summary_en=f"{name_en} — YouTube official channel: {stat_en}{rel_en}.",
        summary_ko=f"{name_ko} — 유튜브 공식 채널: {stat_ko}{rel_ko}.",
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
