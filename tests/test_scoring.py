"""Scoring decides every number in the product, so the arithmetic is the test."""

from __future__ import annotations

import random

import pytest

from agent_trust.models import AxisKey, AxisScore, CheckResult, CheckStatus, Letter, Severity
from agent_trust.scoring import (
    CAP_CEILING,
    CAP_THRESHOLD,
    SECRET_CLAMP,
    score,
    score_axis,
    score_overall,
)
from agent_trust.scoring.effort import EFFORT_MINUTES, assert_complete
from agent_trust.scoring.findings import WHY, severity_for
from agent_trust.scoring.grades import letter_for

ALL_CHECK_IDS = frozenset(EFFORT_MINUTES)


def check(
    check_id: str,
    status: CheckStatus,
    weight: int,
    title: str = "a check",
) -> CheckResult:
    earned = {
        CheckStatus.PASS: float(weight),
        CheckStatus.PARTIAL: weight / 2,
        CheckStatus.FAIL: 0.0,
        CheckStatus.NOT_APPLICABLE: 0.0,
    }[status]
    return CheckResult(id=check_id, title=title, status=status, weight=weight, earned=earned)


def axis_at(key: str, score_value: int | None) -> AxisScore:
    return AxisScore(
        key=AxisKey(key),
        name=key.replace("_", " ").title(),
        score=score_value,
        letter=letter_for(score_value),
        weight=0.2,
    )


# ── grade bands ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (100, Letter.A),
        (90, Letter.A),
        (89, Letter.B),
        (80, Letter.B),
        (79, Letter.C),
        (70, Letter.C),
        (69, Letter.D),
        (60, Letter.D),
        (59, Letter.F),
        (0, Letter.F),
        (None, Letter.NA),
    ],
)
def test_band_boundaries(value: int | None, expected: Letter) -> None:
    assert letter_for(value) == expected


def test_bands_live_only_in_grades_module() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent / "agent_trust"
    offenders = []
    for path in root.rglob("*.py"):
        if path.name == "grades.py":
            continue
        text = path.read_text(encoding="utf-8")
        if "Letter.A" in text and "90" in text:
            offenders.append(path.name)
    assert offenders == []


# ── axis arithmetic ─────────────────────────────────────────────────────────


def test_not_applicable_leaves_the_denominator() -> None:
    checks = [
        check("TS-01", CheckStatus.PASS, 20),
        check("TS-02", CheckStatus.PASS, 20),
        check("TS-03", CheckStatus.NOT_APPLICABLE, 15),
        check("TS-04", CheckStatus.NOT_APPLICABLE, 10),
    ]
    axis = score_axis(AxisKey.TOOL_SURFACE, "Tool Surface", checks)
    assert axis.score == 100, "not_applicable must not be scored as a failure"


def test_all_not_applicable_axis_is_null_and_na() -> None:
    checks = [check("TS-01", CheckStatus.NOT_APPLICABLE, 20)]
    axis = score_axis(AxisKey.TOOL_SURFACE, "Tool Surface", checks)
    assert axis.score is None
    assert axis.letter is Letter.NA


def test_partial_earns_half() -> None:
    checks = [
        check("TS-01", CheckStatus.PARTIAL, 20),
        check("TS-02", CheckStatus.FAIL, 20),
    ]
    assert score_axis(AxisKey.TOOL_SURFACE, "Tool Surface", checks).score == 25


def test_all_fail_scores_zero() -> None:
    checks = [check("TS-01", CheckStatus.FAIL, 20), check("TS-02", CheckStatus.FAIL, 20)]
    assert score_axis(AxisKey.TOOL_SURFACE, "Tool Surface", checks).score == 0


# ── the cap rule ────────────────────────────────────────────────────────────


def test_cap_fires_on_an_axis_below_forty() -> None:
    axes = [
        axis_at("tool_surface", 95),
        axis_at("blast_radius", 38),
        axis_at("verifiability", 95),
        axis_at("context_quality", 95),
        axis_at("observability", 95),
    ]
    overall = score_overall(axes)
    assert overall.mean == 84
    assert overall.score == CAP_CEILING
    assert overall.letter is Letter.C
    assert overall.capped
    assert overall.cap_reason and "Blast Radius" in overall.cap_reason


def test_cap_does_not_fire_at_exactly_forty() -> None:
    axes = [
        axis_at("tool_surface", 95),
        axis_at("blast_radius", CAP_THRESHOLD),
        axis_at("verifiability", 95),
        axis_at("context_quality", 95),
        axis_at("observability", 95),
    ]
    overall = score_overall(axes)
    assert overall.score == 84
    assert overall.letter is Letter.B
    assert not overall.capped


def test_cap_never_raises_a_low_mean() -> None:
    axes = [axis_at(key, 30) for key in ("tool_surface", "blast_radius", "verifiability")]
    axes += [axis_at("context_quality", 30), axis_at("observability", 30)]
    overall = score_overall(axes)
    assert overall.score == 30, "min(mean, 70) must not lift a score"
    assert overall.capped is False


def test_no_scored_axes_yields_null_overall() -> None:
    overall = score_overall(
        [axis_at(key, None) for key, _, _ in (("tool_surface", 0, 0), ("blast_radius", 0, 0))]
    )
    assert overall.score is None
    assert overall.letter is Letter.NA


# ── the secret rule ─────────────────────────────────────────────────────────


def test_committed_secret_clamps_blast_radius_and_caps_overall() -> None:
    results = {
        AxisKey.TOOL_SURFACE: [check("TS-01", CheckStatus.PASS, 20)],
        AxisKey.BLAST_RADIUS: [
            check("BR-01", CheckStatus.FAIL, 30, "No committed secrets"),
            check("BR-02", CheckStatus.PASS, 12),
            check("BR-03", CheckStatus.PASS, 8),
            check("BR-04", CheckStatus.PASS, 20),
            check("BR-05", CheckStatus.PASS, 15),
            check("BR-06", CheckStatus.PASS, 10),
            check("BR-07", CheckStatus.PASS, 5),
        ],
        AxisKey.VERIFIABILITY: [check("VF-01", CheckStatus.PASS, 20)],
        AxisKey.CONTEXT_QUALITY: [check("CQ-01", CheckStatus.PASS, 20)],
        AxisKey.OBSERVABILITY: [check("OB-01", CheckStatus.PASS, 25)],
    }
    axes, overall, findings, _fixes = score(results)

    blast = next(a for a in axes if a.key is AxisKey.BLAST_RADIUS)
    assert blast.score is not None and blast.score <= SECRET_CLAMP
    assert overall.capped
    assert overall.letter is Letter.C
    assert any(f.check_id == "BR-01" and f.severity is Severity.HIGH for f in findings)


def test_clean_repo_scores_a_hundred_with_no_findings() -> None:
    results = {
        AxisKey.TOOL_SURFACE: [check("TS-01", CheckStatus.PASS, 20)],
        AxisKey.BLAST_RADIUS: [check("BR-01", CheckStatus.PASS, 30)],
        AxisKey.VERIFIABILITY: [check("VF-01", CheckStatus.PASS, 20)],
        AxisKey.CONTEXT_QUALITY: [check("CQ-01", CheckStatus.PASS, 20)],
        AxisKey.OBSERVABILITY: [check("OB-01", CheckStatus.PASS, 25)],
    }
    axes, overall, findings, fixes = score(results)
    assert overall.score == 100
    assert overall.letter is Letter.A
    assert findings == () and fixes == ()
    assert len(axes) == 5


# ── severity ────────────────────────────────────────────────────────────────


def test_severity_map() -> None:
    assert severity_for(check("BR-01", CheckStatus.FAIL, 30)) is Severity.HIGH
    assert severity_for(check("VF-01", CheckStatus.FAIL, 20)) is Severity.HIGH
    assert severity_for(check("BR-02", CheckStatus.FAIL, 12)) is Severity.MEDIUM
    assert severity_for(check("BR-07", CheckStatus.FAIL, 5)) is Severity.LOW


def test_every_partial_is_low_never_medium() -> None:
    for weight in (5, 10, 15, 20, 30):
        assert severity_for(check("BR-04", CheckStatus.PARTIAL, weight)) is Severity.LOW


# ── fix ranking ─────────────────────────────────────────────────────────────


def test_fixes_rank_by_risk_reduction_per_hour() -> None:
    results = {
        AxisKey.BLAST_RADIUS: [
            check("BR-03", CheckStatus.FAIL, 8, "gitignore"),  # 8 pts / 10 min = 48/h
            check("BR-04", CheckStatus.FAIL, 20, "guards"),  # 20 pts / 90 min = 13.3/h
        ],
    }
    _axes, _overall, _findings, fixes = score(results)
    assert [f.id for f in fixes] == ["FIX-BR-03", "FIX-BR-04"]
    assert fixes[0].ratio > fixes[1].ratio


def test_ranking_is_stable_across_shuffled_input() -> None:
    checks = [
        check("CQ-05", CheckStatus.FAIL, 15),
        check("CQ-07", CheckStatus.FAIL, 10),
        check("CQ-03", CheckStatus.FAIL, 15),
    ]
    orders = set()
    for _ in range(50):
        random.shuffle(checks)
        _a, _o, _f, fixes = score({AxisKey.CONTEXT_QUALITY: list(checks)})
        orders.add(tuple(f.id for f in fixes))
    assert len(orders) == 1, f"ranking is not stable: {orders}"


def test_partial_recovers_only_the_unearned_half() -> None:
    results = {AxisKey.BLAST_RADIUS: [check("BR-04", CheckStatus.PARTIAL, 20)]}
    _a, _o, _f, fixes = score(results)
    assert fixes[0].risk_reduction == 10


# ── data completeness ───────────────────────────────────────────────────────


def test_every_check_has_effort_a_reason_and_steps() -> None:
    from agent_trust.scoring.fixes import STEPS

    assert len(ALL_CHECK_IDS) == 37
    assert set(WHY) == ALL_CHECK_IDS
    assert set(STEPS) == ALL_CHECK_IDS


def test_missing_effort_entry_fails_loudly() -> None:
    with pytest.raises(ValueError, match="missing entries"):
        assert_complete(frozenset({"XX-99"}))
