"""Effort and recoverable points per check -- data, never estimated at runtime.

Standing rule B: the model may write prose about a fix. It may not decide how
long the fix takes or how much it is worth, because those two numbers set the
order of the fix list, and the fix list is the product's actual advice.

``EFFORT_MINUTES`` is a considered guess at how long a competent engineer needs
to close each check on a mid-sized repository. It is deliberately coarse: the
ranking only needs the buckets to be right relative to each other.
"""

from __future__ import annotations

# Minutes to close each check. Keyed by check id; every one of the 37 appears.
EFFORT_MINUTES: dict[str, int] = {
    # Tool Surface -- mostly writing interface surface that does not exist yet.
    "TS-01": 120,
    "TS-02": 180,
    "TS-03": 45,
    "TS-04": 20,
    "TS-05": 240,
    "TS-06": 15,
    "TS-07": 20,
    # Blast Radius -- the cheapest wins in the product live here.
    "BR-01": 45,
    "BR-02": 15,
    "BR-03": 10,
    "BR-04": 90,
    "BR-05": 60,
    "BR-06": 60,
    "BR-07": 10,
    # Verifiability -- writing tests is the expensive end of the range.
    "VF-01": 480,
    "VF-02": 15,
    "VF-03": 480,
    "VF-04": 30,
    "VF-05": 15,
    "VF-06": 60,
    "VF-07": 20,
    "VF-08": 20,
    # Context Quality -- writing prose, and the best ratio in the product.
    "CQ-01": 45,
    "CQ-02": 30,
    "CQ-03": 15,
    "CQ-04": 30,
    "CQ-05": 10,
    "CQ-06": 20,
    "CQ-07": 10,
    "CQ-08": 20,
    # Observability
    "OB-01": 90,
    "OB-02": 60,
    "OB-03": 45,
    "OB-04": 120,
    "OB-05": 30,
    "OB-06": 20,
    "OB-07": 20,
}

# Fallback for a check id with no entry. Never silently used: assert_complete()
# is called at import by the scoring package so a missing id fails the build.
DEFAULT_EFFORT_MINUTES = 60


def effort_for(check_id: str) -> int:
    """Minutes to close ``check_id``."""
    return EFFORT_MINUTES.get(check_id, DEFAULT_EFFORT_MINUTES)


def assert_complete(check_ids: frozenset[str]) -> None:
    """Fail loudly when a check has no effort entry.

    Raises:
        ValueError: a check id is missing from EFFORT_MINUTES, which would let
            it silently take the default and mis-rank the fix list.
    """
    missing = sorted(check_ids - set(EFFORT_MINUTES))
    if missing:
        raise ValueError(f"EFFORT_MINUTES is missing entries for: {missing}")
