"""Grade bands -- encoded here and nowhere else in the build.

SPEC.md states the bands once and names this module as their only home. If a
band boundary appears in a renderer, a template or a test fixture, that is a
defect: two places that restate a policy eventually disagree.
"""

from __future__ import annotations

from agent_trust.models import Letter

# (minimum score, letter), highest first.
BANDS: tuple[tuple[int, Letter], ...] = (
    (90, Letter.A),
    (80, Letter.B),
    (70, Letter.C),
    (60, Letter.D),
    (0, Letter.F),
)


def letter_for(score: int | None) -> Letter:
    """Map a 0-100 score to its letter. ``None`` means nothing was scored."""
    if score is None:
        return Letter.NA
    for minimum, letter in BANDS:
        if score >= minimum:
            return letter
    return Letter.F  # pragma: no cover - BANDS ends at 0, so unreachable
