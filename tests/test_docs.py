"""The documentation must not be able to drift from the code."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from agent_trust.analyzers import (
    blast_radius,
    context_quality,
    observability,
    tool_surface,
    verifiability,
)

ROOT = Path(__file__).resolve().parent.parent
FORBIDDEN_CLAIMS = (
    "hipaa compliant",
    "soc 2",
    "pci compliant",
    "certified secure",
    "guarantees security",
    "guaranteed secure",
    "is secure",
    "makes your repo safe",
)


def test_checks_doc_regenerates_identically() -> None:
    """docs/CHECKS.md is generated; a hand edit must fail the build."""
    result = subprocess.run(  # noqa: S603
        [sys.executable, "scripts/generate_checks_doc.py", "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_checks_doc_lists_every_check() -> None:
    document = (ROOT / "docs" / "CHECKS.md").read_text(encoding="utf-8")
    modules = (tool_surface, blast_radius, verifiability, context_quality, observability)
    ids = [spec.id for module in modules for spec in module.SPECS]

    assert len(ids) == 37
    for check_id in ids:
        assert f"`{check_id}`" in document, f"{check_id} missing from docs/CHECKS.md"


def test_every_axis_totals_one_hundred_in_the_doc() -> None:
    document = (ROOT / "docs" / "CHECKS.md").read_text(encoding="utf-8")
    assert document.count("Axis total: 100.") == 5


# ── the product must not overclaim ──────────────────────────────────────────


@pytest.mark.parametrize("name", ["README.md", "docs/PRIVACY.md", "docs/CHECKS.md", "CLAUDE.md"])
def test_documents_make_no_certification_claim(name: str) -> None:
    asserted = _asserted_claims((ROOT / name).read_text(encoding="utf-8"))
    assert asserted == [], f"{name} claims: {asserted}"


def test_readme_states_the_limits_plainly() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "not a security audit" in readme.lower()
    assert "certifies nothing" in readme.lower()
    assert "never executes" in readme.lower()


def test_readme_documents_install_run_and_flags() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for expected in ("uvx agent-trust-score", "--no-llm", "--min-grade", "agent-trust-mcp"):
        assert expected in readme, f"README does not document {expected}"


def test_privacy_names_the_only_third_party() -> None:
    privacy = (ROOT / "docs" / "PRIVACY.md").read_text(encoding="utf-8")
    assert "Anthropic" in privacy
    assert "no telemetry" in privacy.lower() or "There is no telemetry" in privacy


NEGATIONS = ("never", "not ", "no ", "cannot", "false", "must not", "avoid", "refus")


def _asserted_claims(text: str) -> list[str]:
    """Claim phrases that are asserted rather than forbidden.

    A line reading "Never claim the repository is secure" contains the phrase
    "is secure" but is the opposite of a claim, so the negation guard is what
    makes this check usable on a codebase whose job is to police that wording.
    """
    found = []
    for line in text.lower().splitlines():
        for claim in FORBIDDEN_CLAIMS:
            if claim in line and not any(negation in line for negation in NEGATIONS):
                found.append(line.strip())
    return found


def test_no_source_file_claims_the_tool_secures_anything() -> None:
    for path in (ROOT / "agent_trust").rglob("*.py"):
        asserted = _asserted_claims(path.read_text(encoding="utf-8"))
        assert asserted == [], f"{path.name} claims: {asserted}"


def test_the_negation_guard_still_catches_a_real_claim() -> None:
    # Canary: the guard must not be so permissive that it passes everything.
    assert _asserted_claims("This tool guarantees security for your repo.") != []
    assert _asserted_claims("Never claim the repository is secure.") == []


# ── this repo scores well on its own tool ───────────────────────────────────


def test_this_repo_grades_b_or_better_on_itself() -> None:
    """Dogfooding, as a gate.

    A tool that grades agent-operability and scores badly on its own repository
    is not credible. This fails the build rather than being noticed on a demo.
    """
    from agent_trust.pipeline import audit

    report = audit(str(ROOT), use_llm=False, use_cache=False, timeout=120)
    assert report.overall.score is not None
    assert report.overall.score >= 80, f"self-grade fell to {report.overall.score}"
    assert not report.overall.capped


def test_this_repo_contains_no_credential_shaped_literal() -> None:
    """The fixture definitions must not trip the detector on their own source.

    CI caught this once: the ugly fixture's password was a marker-free literal
    and the docstring spelled the fake AWS key out, so the tool flagged its own
    repository. Both are now assembled from fragments.
    """
    from agent_trust.pipeline import audit

    report = audit(str(ROOT), use_llm=False, use_cache=False, timeout=120)
    secrets = [f for f in report.findings if f.check_id == "BR-01"]
    assert secrets == [], (
        f"BR-01 fires on this repo: {[e.path for f in secrets for e in f.evidence]}"
    )
