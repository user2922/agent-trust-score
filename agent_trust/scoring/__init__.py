"""Scoring -- pure functions over CheckResults. No I/O, no clock, no network.

Two rules from SPEC.md are applied here, in this order:

1. **The secret rule.** Any high-severity BR-01 finding forces ``blast_radius``
   to at most 39. A committed secret is not a matter of degree.
2. **The cap rule.** Any scored axis below 40 sets the overall to
   ``min(mean, 70)``, so a repo with one catastrophic axis cannot average its
   way to an A.

The letter always comes from the capped score, never from the raw mean.
"""

from __future__ import annotations

from collections.abc import Sequence

from agent_trust.models import (
    AXES,
    AxisKey,
    AxisScore,
    CheckResult,
    CheckStatus,
    Finding,
    Fix,
    Overall,
    Severity,
)
from agent_trust.scoring.effort import assert_complete, effort_for
from agent_trust.scoring.findings import SECRET_CHECK_ID, findings_for, severity_for
from agent_trust.scoring.fixes import build_fixes
from agent_trust.scoring.grades import BANDS, letter_for

SECRET_CLAMP = 39
CAP_THRESHOLD = 40
CAP_CEILING = 70

_EARNED = {
    CheckStatus.PASS: 1.0,
    CheckStatus.PARTIAL: 0.5,
    CheckStatus.FAIL: 0.0,
    CheckStatus.NOT_APPLICABLE: 0.0,
}


def earned_for(status: CheckStatus, weight: int) -> float:
    """What a check with this status earns. The one place that arithmetic lives."""
    return _EARNED[status] * weight


def score_axis(key: AxisKey, name: str, checks: Sequence[CheckResult]) -> AxisScore:
    """Score one axis.

    ``not_applicable`` is removed from both the numerator and the denominator --
    never scored as a failure. An axis where every check is not applicable has a
    null score and is dropped from the overall mean.
    """
    applicable = [c for c in checks if c.status is not CheckStatus.NOT_APPLICABLE]
    total_weight = sum(c.weight for c in applicable)
    if not applicable or total_weight == 0:
        return AxisScore(
            key=key,
            name=name,
            score=None,
            letter=letter_for(None),
            weight=0.2,
            checks=tuple(checks),
        )

    earned = sum(c.earned for c in applicable)
    score = round(100 * earned / total_weight)
    return AxisScore(
        key=key, name=name, score=score, letter=letter_for(score), weight=0.2, checks=tuple(checks)
    )


def _clamp_for_secrets(axes: Sequence[AxisScore], findings: Sequence[Finding]) -> list[AxisScore]:
    """Force blast_radius to at most 39 when a secret is committed."""
    has_secret = any(
        f.check_id == SECRET_CHECK_ID and f.severity is Severity.HIGH for f in findings
    )
    if not has_secret:
        return list(axes)

    clamped: list[AxisScore] = []
    for axis in axes:
        if (
            axis.key is AxisKey.BLAST_RADIUS
            and axis.score is not None
            and axis.score > SECRET_CLAMP
        ):
            clamped.append(
                axis.model_copy(update={"score": SECRET_CLAMP, "letter": letter_for(SECRET_CLAMP)})
            )
        else:
            clamped.append(axis)
    return clamped


def score_overall(axes: Sequence[AxisScore]) -> Overall:
    """Mean of the scored axes, then the cap rule."""
    scored = [axis for axis in axes if axis.score is not None]
    if not scored:
        return Overall(score=None, letter=letter_for(None), mean=None)

    mean = round(sum(axis.score or 0 for axis in scored) / len(scored))

    worst = min(scored, key=lambda axis: axis.score or 0)
    if (worst.score or 0) < CAP_THRESHOLD:
        capped_score = min(mean, CAP_CEILING)
        return Overall(
            score=capped_score,
            letter=letter_for(capped_score),
            mean=mean,
            capped=capped_score != mean,
            cap_reason=(
                f"{worst.name} scored {worst.score}, below {CAP_THRESHOLD}; "
                f"overall is capped at {CAP_CEILING}."
            ),
        )
    return Overall(score=mean, letter=letter_for(mean), mean=mean)


def score(
    results: dict[AxisKey, Sequence[CheckResult]],
) -> tuple[tuple[AxisScore, ...], Overall, tuple[Finding, ...], tuple[Fix, ...]]:
    """Score every axis, apply both rules, and rank the fixes.

    Args:
        results: check results per axis. A missing axis scores as all-N/A rather
            than as a failure, which is what an ``--axis`` filter produces.

    Returns:
        Axes in ``AXES`` order, the overall grade, findings, and ranked fixes.
    """
    findings: list[Finding] = []
    axes: list[AxisScore] = []
    checks_by_id: dict[str, CheckResult] = {}

    for key_str, name, _weight in AXES:
        key = AxisKey(key_str)
        checks = tuple(results.get(key, ()))
        axes.append(score_axis(key, name, checks))
        findings.extend(findings_for(key, checks))
        for check in checks:
            checks_by_id[check.id] = check

    assert_complete(frozenset(checks_by_id))

    axes = _clamp_for_secrets(axes, findings)
    overall = score_overall(axes)
    fixes = build_fixes(findings, checks_by_id)
    return tuple(axes), overall, tuple(findings), tuple(fixes)


__all__ = [
    "BANDS",
    "CAP_CEILING",
    "CAP_THRESHOLD",
    "SECRET_CLAMP",
    "earned_for",
    "effort_for",
    "letter_for",
    "score",
    "score_axis",
    "score_overall",
    "severity_for",
]
