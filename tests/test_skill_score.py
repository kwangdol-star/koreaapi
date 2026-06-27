"""Skill Score formula — the transparent trust measure. The load-bearing invariant: a record is
"cross-verified" (and may read "high") ONLY when >=2 sources actually AGREE. A single source, or
multiple sources that disagree, is uncorroborated and capped at 0.7 — so two contradicting sources
can never outrank one honest source (the fail-safe). Pure/offline.
"""

from __future__ import annotations

from koreaapi.skill_score import compute_skill_score, to_confidence


def _score(agree: int, total: int, *, age=0, ttl=86400, fallback=False, official=True) -> float:
    return compute_skill_score(age_seconds=age, ttl_seconds=ttl, n_sources_agree=agree,
                               n_sources_total=total, used_fallback_only=fallback,
                               translation_official=official)


def test_two_agreeing_sources_clear_the_cap():
    assert _score(2, 2) == 1.0
    assert to_confidence(_score(2, 2)) == "high"


def test_single_source_is_capped():
    assert _score(1, 1) == 0.7
    assert to_confidence(_score(1, 1)) == "medium"


def test_disagreement_never_outranks_a_clean_single_source():
    # THE regression: two sources that disagree (n_agree=1 of 2) must be capped at 0.7, NOT 0.85,
    # and must never read "high". Before the fix this scored 0.85/high — higher than a clean single.
    disagree = _score(1, 2)
    assert disagree <= 0.7
    assert to_confidence(disagree) != "high"
    assert disagree <= _score(1, 1)  # disagreement is never BETTER than one honest source


def test_partial_agreement_needs_at_least_two_to_corroborate():
    # 2-of-3 agree -> corroborated by a pair -> may stay high; 1-of-3 -> uncorroborated -> capped.
    assert _score(2, 3) > 0.7 and to_confidence(_score(2, 3)) == "high"
    assert _score(1, 3) <= 0.7


def test_freshness_and_translation_penalties():
    assert _score(2, 2, official=False) == 0.9            # non-official translation -0.1
    assert _score(2, 2, age=86400 * 2, ttl=86400) < 1.0   # stale -> freshness penalty
    assert _score(2, 2, fallback=True) <= 0.6             # fallback-only cap


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
