from __future__ import annotations


def distribute(desired_total: int, zones: list[str]) -> dict[str, int]:
    """
    Distribute desired_total across zones as evenly as possible.

    Zones are sorted alphabetically so the assignment is deterministic — the
    same desired_total always produces the same distribution regardless of
    current state. When total is not evenly divisible, earlier zones (a-z)
    carry the extra replica.

    Examples (3 zones):
      total=5  → zone-1:2, zone-2:2, zone-3:1
      total=10 → zone-1:4, zone-2:3, zone-3:3
      total=11 → zone-1:4, zone-2:4, zone-3:3
    """
    if not zones:
        return {}

    num_zones = len(zones)
    base = desired_total // num_zones
    extras = desired_total % num_zones
    sorted_zones = sorted(zones)

    return {
        zone: base + (1 if i < extras else 0)
        for i, zone in enumerate(sorted_zones)
    }
