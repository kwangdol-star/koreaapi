"""Embeddable "Verified by KoreaAPI" trust badge — the citation flywheel as a viral artifact. The SVG
is self-contained (no fonts/scripts/network) and coloured by the verification tier. Offline."""

from __future__ import annotations

from koreaapi.badge import badge_svg, tier_of


def test_tier_of_ladders_by_agreement_and_certification():
    assert tier_of(0, False) == "single-source"
    assert tier_of(1, False) == "single-source"
    assert tier_of(2, False) == "cross-verified"
    assert tier_of(3, False) == "triple-cross-verified"
    assert tier_of(3, True) == "officially-certified"   # certification tops the ladder
    assert tier_of(0, True) == "officially-certified"   # an institution's vouch beats source count


def test_badge_svg_is_self_contained_and_tier_coloured():
    svg = badge_svg("triple-cross-verified", 1.0)
    assert svg.startswith("<svg") and svg.rstrip().endswith("</svg>") and "KoreaAPI" in svg
    assert "#10B981" in svg and "✓✓✓" in svg and "1.00" in svg   # green + triple tick + skill
    assert "<script" not in svg                                   # no active content — safe to embed
    cert = badge_svg("officially-certified", 1.0)
    assert "#7C3AED" in cert and "certified" in cert              # violet + certified label
    u = badge_svg("unverified", None)
    assert "#EF4444" in u and "✗" in u and "·" not in u          # red + cross + no skill segment


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
