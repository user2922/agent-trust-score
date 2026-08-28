"""A hand-built Report covering every status, severity and edge the renderers face.

Built through the real scoring engine rather than by hand-assembling a Report, so
the fixture cannot drift away from what the product actually produces.
"""

from __future__ import annotations

from datetime import UTC, datetime

from agent_trust.models import (
    AxisKey,
    CheckResult,
    CheckStatus,
    Evidence,
    LlmUsage,
    RepoInfo,
    Report,
)
from agent_trust.scoring import score

# Deliberately hostile content: a repository can put anything in a README, and
# the HTML renderer must show this as text rather than execute it.
HOSTILE = "<script>alert('xss')</script>"


def _check(
    check_id: str,
    title: str,
    status: CheckStatus,
    weight: int,
    detail: str = "",
    evidence: tuple[Evidence, ...] = (),
) -> CheckResult:
    earned = {
        CheckStatus.PASS: float(weight),
        CheckStatus.PARTIAL: weight / 2,
        CheckStatus.FAIL: 0.0,
        CheckStatus.NOT_APPLICABLE: 0.0,
    }[status]
    return CheckResult(
        id=check_id,
        title=title,
        status=status,
        weight=weight,
        earned=earned,
        detail=detail,
        evidence=evidence,
    )


def golden_report() -> Report:
    """A report with a capped grade, a truncated repo, and every status present."""
    results = {
        AxisKey.TOOL_SURFACE: [
            _check("TS-01", "MCP server declared", CheckStatus.PASS, 20),
            _check("TS-02", "Machine-readable API schema", CheckStatus.PASS, 20),
            _check("TS-05", "Typed public boundaries", CheckStatus.PARTIAL, 15, "42% annotated"),
            _check(
                "TS-06", "Parseable package manifest", CheckStatus.NOT_APPLICABLE, 10, "no manifest"
            ),
        ],
        AxisKey.BLAST_RADIUS: [
            _check(
                "BR-01",
                "No committed secrets",
                CheckStatus.FAIL,
                30,
                "1 match, 3 placeholders suppressed",
                (
                    Evidence(
                        path="config/settings.py",
                        line=12,
                        snippet='AWS_KEY = "AKIA…LE"',
                        matcher="aws_access_key_id",
                    ),
                ),
            ),
            _check("BR-02", ".env not tracked", CheckStatus.FAIL, 12),
            _check("BR-03", "gitignore covers sensitive paths", CheckStatus.PARTIAL, 8),
            _check("BR-07", "Ownership config", CheckStatus.FAIL, 5),
        ],
        AxisKey.VERIFIABILITY: [
            _check("VF-01", "Test suite exists", CheckStatus.PASS, 20),
            _check("VF-05", "CI actually runs tests", CheckStatus.PASS, 15),
        ],
        AxisKey.CONTEXT_QUALITY: [
            _check(
                "CQ-02",
                "README with substance",
                CheckStatus.PASS,
                10,
                f"README begins: {HOSTILE}",
                (Evidence(path="README.md", line=1, snippet=HOSTILE, matcher="readme_words"),),
            ),
            _check("CQ-05", "Run and test commands", CheckStatus.PASS, 15),
            _check(
                "CQ-08", "Docs resolve to reality", CheckStatus.PARTIAL, 5, "3 of 5 paths resolve"
            ),
        ],
        # Every check not applicable: this axis must render as N/A, not zero.
        AxisKey.OBSERVABILITY: [
            _check(
                "OB-01", "Structured logging", CheckStatus.NOT_APPLICABLE, 25, "no source files"
            ),
        ],
    }

    axes, overall, findings, fixes = score(results)
    return Report(
        generated_at=datetime(2026, 1, 15, 9, 30, tzinfo=UTC),
        run_ms=8421,
        repo=RepoInfo(
            source="https://github.com/example/demo",
            commit_sha="a1b2c3d4e5f60718293a4b5c6d7e8f9012345678",
            default_branch="master",
            file_count=412,
            analyzed_file_count=118,
            bytes_scanned=1_204_992,
            languages={"Python": 84, "TypeScript": 30, "Markdown": 4},
            truncated=True,
            skipped={"vendored": 280, "binary": 14},
        ),
        overall=overall,
        axes=axes,
        findings=findings,
        fixes=fixes,
        llm=LlmUsage(used=False, fallback_reason="no ANTHROPIC_API_KEY configured"),
    )
