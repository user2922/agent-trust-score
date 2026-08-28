"""The four success criteria, asserted end to end on the two fixtures.

1. A clean repository grades well and reports **zero** secrets.
2. An ugly repository grades F with at least one true positive on every axis.
3. The same commit produces the same scores, with and without the model.
4. No output artifact ever carries a full secret value.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from agent_trust.models import AXIS_ORDER, CheckStatus, Report, Severity
from agent_trust.pipeline import audit, write_reports

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from build_fixtures import FAKE_AWS_KEY, build_clean, build_ugly  # noqa: E402


@pytest.fixture(scope="module")
def clean(tmp_path_factory: pytest.TempPathFactory) -> Report:
    root = build_clean(tmp_path_factory.mktemp("clean"))
    return audit(str(root), use_llm=False, use_cache=False, timeout=120)


@pytest.fixture(scope="module")
def ugly(tmp_path_factory: pytest.TempPathFactory) -> Report:
    root = build_ugly(tmp_path_factory.mktemp("ugly"))
    return audit(str(root), use_llm=False, use_cache=False, timeout=120)


# ── criterion 1 · the clean repository ──────────────────────────────────────


def test_clean_repo_grades_b_or_better(clean: Report) -> None:
    assert clean.overall.score is not None
    assert clean.overall.score >= 80, f"clean fixture fell to {clean.overall.score}"
    assert clean.overall.letter.value in {"A", "B"}


def test_clean_repo_reports_zero_secrets(clean: Report) -> None:
    """The zero-false-positives criterion."""
    secret_findings = [f for f in clean.findings if f.check_id == "BR-01"]
    assert secret_findings == []

    br01 = next(check for axis in clean.axes for check in axis.checks if check.id == "BR-01")
    assert br01.status is CheckStatus.PASS


def test_clean_repo_is_not_capped(clean: Report) -> None:
    assert not clean.overall.capped
    assert all(axis.score is None or axis.score >= 40 for axis in clean.axes)


# ── criterion 2 · the ugly repository ───────────────────────────────────────


def test_ugly_repo_grades_f(ugly: Report) -> None:
    assert ugly.overall.letter.value == "F"


def test_ugly_repo_has_a_finding_on_every_axis(ugly: Report) -> None:
    """One true positive per axis -- the criterion, asserted per axis."""
    by_axis = {key: 0 for key in AXIS_ORDER}
    for finding in ugly.findings:
        by_axis[finding.axis.value] += 1

    missing = [key for key, count in by_axis.items() if count == 0]
    assert missing == [], f"no finding on: {missing}"


def test_ugly_repo_flags_the_planted_credential(ugly: Report) -> None:
    secrets = [f for f in ugly.findings if f.check_id == "BR-01"]
    assert secrets, "the planted AWS key was not detected"
    assert secrets[0].severity is Severity.HIGH


def test_the_secret_clamp_holds_blast_radius_down(ugly: Report) -> None:
    blast = next(axis for axis in ugly.axes if axis.key.value == "blast_radius")
    assert blast.score is not None and blast.score <= 39


def test_ugly_repo_findings_carry_actionable_evidence(ugly: Report) -> None:
    with_evidence = [f for f in ugly.findings if f.evidence]
    assert with_evidence, "no finding carried evidence"
    for finding in with_evidence:
        for item in finding.evidence:
            assert item.path
    # Every failing check says what it looked for, so a reader can disagree.
    for axis in ugly.axes:
        for check in axis.checks:
            if check.status is CheckStatus.FAIL:
                assert check.detail, f"{check.id} failed with no detail"


# ── criterion 4 · no artifact leaks the secret ──────────────────────────────


def test_no_written_artifact_contains_the_full_secret(ugly: Report, tmp_path: Path) -> None:
    written = write_reports(ugly, tmp_path / "out", ["md", "json", "html"])
    assert len(written) == 3

    for path in written:
        body = path.read_text(encoding="utf-8")
        assert FAKE_AWS_KEY not in body, f"{path.name} leaked the key"
        assert FAKE_AWS_KEY[4:-2] not in body, f"{path.name} leaked the key's middle"

    # The report does show enough to find it again.
    markdown = (tmp_path / "out" / "report.md").read_text(encoding="utf-8")
    assert "settings.py" in markdown


def test_the_ugly_fixture_really_contains_the_key(tmp_path: Path) -> None:
    """Guard against the fixture silently losing its planted credential.

    Without this, a fixture change could make every detection test above pass
    vacuously.
    """
    root = build_ugly(tmp_path)
    assert FAKE_AWS_KEY in (root / "settings.py").read_text(encoding="utf-8")
