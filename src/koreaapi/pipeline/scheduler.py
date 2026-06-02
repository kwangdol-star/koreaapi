"""Tiered collection cadence (SCOPE.md S4). Not everything daily - tier by velocity.

Overwrite = wrapper; append timestamped snapshots = asset.
"""

from __future__ import annotations

# Default cadence in seconds. Behavioral signal is captured continuously at query
# time (not scheduled here).
CADENCE = {
    "charts": 12 * 3600,  # 1-2x/day  - high velocity
    "events": 24 * 3600,  # daily sweep - catch announcements & changes
    "facts": 7 * 86400,  # weekly / on-change - slow, stable
    "prices": 24 * 3600,  # daily or on-query + cache
}
