"""An invalid Report must be unconstructable, not merely undocumented."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from agent_trust.models import (
    AXES,
    AXIS_ORDER,
    SCHEMA_VERSION,
    AxisKey,
    AxisScore,
    CheckResult,
    CheckStatus,
    Evidence,
    Finding,
    Fix,
    Letter,
    Overall,
    RepoInfo,
    Report,
    Severity,
    load_report,
)
from agent_trust.redact import MAX_SNIPPET


def axis(key: str, name: str, score: int | None = 100) -> AxisScore:
    return AxisScore(
        key=AxisKey(key),
        name=name,
        score=score,
        letter=Letter.A if score is not None else Letter.NA,
        weight=0.2,
    )


def minimal_report(**overrides: object) -> Report:
    base: dict[str, object] = {
        "generated_at": datetime(2026, 1, 1, tzinfo=UTC),
        "run_ms": 1234,
        "repo": RepoInfo(source="."),
        "overall": Overall(score=100, letter=Letter.A, mean=100),
        "axes": tuple(axis(key, name) for key, name, _ in AXES),
    }
    base.update(overrides)
    return Report(**base)  # type: ignore[arg-type]


# ── evidence redaction is enforced, not assumed ─────────────────────────────


def test_oversized_snippet_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Evidence(path="a.py", snippet="x" * (MAX_SNIPPET + 1))


def test_snippet_with_an_escape_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Evidence(path="a.py", snippet="\x1b[31mred")


def test_snippet_with_a_null_byte_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Evidence(path="a.py", snippet="a\x00b")


def test_line_zero_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Evidence(path="a.py", line=0)


# ── check arithmetic ────────────────────────────────────────────────────────


def test_pass_must_earn_full_weight() -> None:
    with pytest.raises(ValidationError):
        CheckResult(id="TS-01", title="t", status=CheckStatus.PASS, weight=20, earned=10)


def test_partial_must_earn_half_weight() -> None:
    CheckResult(id="TS-01", title="t", status=CheckStatus.PARTIAL, weight=20, earned=10)
    with pytest.raises(ValidationError):
        CheckResult(id="TS-01", title="t", status=CheckStatus.PARTIAL, weight=20, earned=20)


def test_fail_must_earn_nothing() -> None:
    with pytest.raises(ValidationError):
        CheckResult(id="TS-01", title="t", status=CheckStatus.FAIL, weight=20, earned=1)


def test_earned_cannot_exceed_weight() -> None:
    with pytest.raises(ValidationError):
        CheckResult(id="TS-01", title="t", status=CheckStatus.PASS, weight=20, earned=99)


# ── axis and overall consistency ────────────────────────────────────────────


def test_null_axis_score_requires_na_letter() -> None:
    with pytest.raises(ValidationError):
        AxisScore(key=AxisKey.TOOL_SURFACE, name="t", score=None, letter=Letter.A, weight=0.2)


def test_na_letter_requires_null_axis_score() -> None:
    with pytest.raises(ValidationError):
        AxisScore(key=AxisKey.TOOL_SURFACE, name="t", score=50, letter=Letter.NA, weight=0.2)


def test_capped_requires_a_reason() -> None:
    with pytest.raises(ValidationError):
        Overall(score=70, letter=Letter.C, mean=84, capped=True)
    Overall(score=70, letter=Letter.C, mean=84, capped=True, cap_reason="blast_radius")


# ── report-level invariants ─────────────────────────────────────────────────


def test_report_requires_five_axes() -> None:
    with pytest.raises(ValidationError):
        minimal_report(axes=tuple(axis(k, n) for k, n, _ in AXES[:4]))


def test_report_rejects_axes_out_of_order() -> None:
    reordered = tuple(axis(k, n) for k, n, _ in AXES)
    with pytest.raises(ValidationError):
        minimal_report(axes=(reordered[1], reordered[0], *reordered[2:]))


def test_fix_referencing_an_unknown_finding_is_rejected() -> None:
    fix = Fix(
        id="FIX-1",
        finding_ids=("nope",),
        axis=AxisKey.BLAST_RADIUS,
        title="t",
        risk_reduction=30,
        effort_minutes=15,
        ratio=120.0,
    )
    with pytest.raises(ValidationError):
        minimal_report(fixes=(fix,))


def test_fix_referencing_a_real_finding_is_accepted() -> None:
    finding = Finding(
        id="F-1",
        check_id="BR-01",
        axis=AxisKey.BLAST_RADIUS,
        severity=Severity.HIGH,
        title="committed secret",
    )
    fix = Fix(
        id="FIX-1",
        finding_ids=("F-1",),
        axis=AxisKey.BLAST_RADIUS,
        title="t",
        risk_reduction=30,
        effort_minutes=15,
        ratio=120.0,
    )
    assert minimal_report(findings=(finding,), fixes=(fix,)).fixes[0].id == "FIX-1"


def test_models_are_frozen() -> None:
    report = minimal_report()
    with pytest.raises(ValidationError):
        report.run_ms = 5  # type: ignore[misc]


def test_unknown_field_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Evidence(path="a.py", snipppet="typo")  # type: ignore[call-arg]


# ── serialization and determinism ───────────────────────────────────────────


def test_json_round_trip_is_byte_identical() -> None:
    report = minimal_report()
    assert report.to_json() == load_report(report.to_json()).to_json()


def test_stable_payload_excludes_volatile_fields() -> None:
    payload = minimal_report().stable_payload()
    assert "generated_at" not in payload
    assert "run_ms" not in payload
    assert "llm" not in payload
    assert payload["overall"]["score"] == 100


def test_runs_differing_only_in_timing_have_equal_stable_payloads() -> None:
    first = minimal_report(generated_at=datetime(2026, 1, 1, tzinfo=UTC), run_ms=10)
    second = minimal_report(generated_at=datetime(2026, 6, 9, tzinfo=UTC), run_ms=9999)
    assert first.stable_json() == second.stable_json()
    assert first.to_json() != second.to_json()


def test_mismatched_schema_version_is_refused_not_coerced() -> None:
    document = minimal_report().to_json().replace(f'"{SCHEMA_VERSION}"', '"0.9"')
    with pytest.raises(ValueError, match="refusing to coerce"):
        load_report(document)


def test_axis_order_constant_matches_axes() -> None:
    assert tuple(key for key, _, _ in AXES) == AXIS_ORDER
    assert len(AXES) == 5
    assert all(weight == 0.2 for _, _, weight in AXES)
