"""Embeddable "Verified by KoreaAPI" trust badge (SVG) — the citation flywheel as a viral artifact.

Any site or rights-holder can <img> a badge that shows the entity's verification TIER + Skill Score.
Every embed is a backlink + a "via KoreaAPI" mark, so the more badges spread, the more KoreaAPI becomes
the Schelling-point citation standard — and it gives a certified rights-holder a visible "blue check".
Pure SVG-string builder (shields.io-style), offline — no fonts, no network, self-contained.
"""

from __future__ import annotations

# Trust tier -> right-side colour. Certified is the top tier (an institution vouched).
_TIER_COLOR = {
    "officially-certified": "#7C3AED",   # violet
    "triple-cross-verified": "#10B981",  # green
    "cross-verified": "#2563EB",         # blue
    "single-source": "#9CA3AF",          # grey (honest: uncorroborated)
    "unverified": "#EF4444",             # red
}
_TIER_LABEL = {
    "officially-certified": "certified",
    "triple-cross-verified": "triple-verified",
    "cross-verified": "cross-verified",
    "single-source": "single-source",
    "unverified": "not found",
}


def tier_of(agreeing_sources: int, certified: bool) -> str:
    """The verification tier from how many INDEPENDENT sources agreed (+ institutional certification)."""
    if certified:
        return "officially-certified"
    if agreeing_sources >= 3:
        return "triple-cross-verified"
    if agreeing_sources >= 2:
        return "cross-verified"
    return "single-source"


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _w(text: str) -> int:
    """Crude monospace-ish width estimate (px) at font-size 11, with padding."""
    return int(6.4 * len(text)) + 12


def badge_svg(tier: str, skill: float | None, *, left: str = "KoreaAPI") -> str:
    """A self-contained SVG badge: left '<left>', right '<tick> <tier> · <skill>', coloured by tier.
    `tier` is one of tier_of()'s values (or 'unverified'); `skill` is the 0–1 Skill Score (or None)."""
    tick = "✓✓✓" if tier == "triple-cross-verified" else "✗" if tier == "unverified" else "✓"
    label = _TIER_LABEL.get(tier, tier)
    right = f"{tick} {label}" + (f" · {skill:.2f}" if skill is not None else "")
    color = _TIER_COLOR.get(tier, "#9CA3AF")
    lw, rw = _w(left), _w(right)
    total = lw + rw
    le, re = _esc(left), _esc(right)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{total}" height="20" role="img" '
        f'aria-label="{le}: {re}">'
        f'<linearGradient id="s" x2="0" y2="100%"><stop offset="0" stop-color="#fff" stop-opacity=".1"/>'
        f'<stop offset="1" stop-opacity=".1"/></linearGradient>'
        f'<rect rx="3" width="{total}" height="20" fill="#24292e"/>'
        f'<rect rx="3" x="{lw}" width="{rw}" height="20" fill="{color}"/>'
        f'<rect x="{lw}" width="4" height="20" fill="{color}"/>'
        f'<rect rx="3" width="{total}" height="20" fill="url(#s)"/>'
        f'<g fill="#fff" text-anchor="middle" font-family="Verdana,DejaVu Sans,Geneva,sans-serif" font-size="11">'
        f'<text x="{lw / 2:.0f}" y="14">{le}</text>'
        f'<text x="{lw + rw / 2:.0f}" y="14">{re}</text>'
        f'</g></svg>'
    )
