"""Bulk discovery for the GEO verticals — the travel-content growth engine. Previously all 11 geo
verticals were seed-only (artists grew to 675 via discovery while hot springs sat at 2). Canonical
classes only, scoped to country=South Korea; every candidate still passes the bilingual name guard,
cross-verification, and the type audit — and place↔geo adjacency covers attraction dual-typing."""

from __future__ import annotations

from koreaapi.sources.wikidata import _DISCOVER, _alien_class, build_discover_search

_GEO_DISCOVER = {
    "beach": "Q40080", "island": "Q23442", "hotspring": "Q177380", "skiresort": "Q130003",
    "themepark": "Q194195", "venue": "Q483110", "airport": "Q1248784",
}


def test_geo_verticals_join_bulk_discovery():
    for ns, cls in _GEO_DISCOVER.items():
        assert ns in _DISCOVER                                   # enrolled (discover() walks list(_DISCOVER))
        q = build_discover_search(ns)
        assert f"P31={cls}" in q and "P17=Q884" in q             # its class, scoped to South Korea


def test_new_geo_classes_respect_the_adjacency_lattice():
    # A place: item positively typed as a beach (Q40080) must NOT be alien (place↔beach adjacency —
    # place:haeundae IS a beach); a beach: item tagged attraction (Q570116, place's class) likewise.
    assert _alien_class("place", {"Q40080"}) is None
    assert _alien_class("beach", {"Q570116"}) is None
    # ... but a non-adjacent vertical positively typed as a beach IS alien (the Sweet-Home lesson).
    assert _alien_class("artist", {"Q40080"}) == "Q40080"


def test_seed_only_verticals_stay_seed_only():
    # Deliberate exclusions hold: museum/temple keep flowing through place's classes, park is complete
    # (all 22 national parks seeded), theater is roster/KOPIS-covered, and the heterogeneous ones stay out.
    for ns in ("museum", "temple", "park", "theater", "history", "heritage", "folklore", "region", "show"):
        assert ns not in _DISCOVER


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
