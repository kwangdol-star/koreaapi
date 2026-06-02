"""Skill Score: a transparent 0.0-1.0 quality measure attached to every record.

This is a differentiator - keep it transparent and documented (SCOPE.md S1).

Heuristic (Phase 1), starting from 1.0:
  - freshness penalty: data older than its tier TTL loses up to 0.4
  - agreement penalty: when >=2 sources are available, disagreement subtracts up to 0.3
  - fallback penalty: relying on a single fallback source caps the score at ~0.6
  - translation penalty: a non-official English translation subtracts 0.1
Clamp to [0, 1].
"""

from __future__ import annotations

from typing import Literal

Confidence = Literal["high", "medium", "low"]


def compute_skill_score(
    *,
    age_seconds: int,
    ttl_seconds: int,
    n_sources_agree: int,
    n_sources_total: int,
    used_fallback_only: bool,
    translation_official: bool,
) -> float:
    """Return a 0.0-1.0 Skill Score. See module docstring for the formula."""
    score = 1.0

    # freshness
    if age_seconds > ttl_seconds:
        over = min((age_seconds - ttl_seconds) / max(ttl_seconds, 1), 1.0)
        score -= 0.4 * over

    # source agreement
    if n_sources_total >= 2:
        agree_ratio = n_sources_agree / n_sources_total
        score -= 0.3 * (1.0 - agree_ratio)

    # fallback only
    if used_fallback_only:
        score = min(score, 0.6)

    # translation quality
    if not translation_official:
        score -= 0.1

    return max(0.0, min(1.0, round(score, 3)))


def to_confidence(score: float) -> Confidence:
    if score >= 0.8:
        return "high"
    if score >= 0.5:
        return "medium"
    return "low"
