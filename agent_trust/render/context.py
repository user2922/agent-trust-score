"""The shared, deterministic view model both file renderers use.

Rendering does no arithmetic. Every number here is copied from the Report; a
renderer that recomputed a score could disagree with the JSON, and the JSON is
what a CI gate reads.
"""

from __future__ import annotations

from typing import Any

from agent_trust.models import CheckStatus, Report

NO_FINDINGS = "No findings on this axis."
NO_FIXES = "Nothing to fix. Every check passed."
# An unmeasured repo is not a clean one. Saying "every check passed" when no
# check ran is the most dangerous sentence this product could print.
NO_FIXES_UNMEASURED = "No checks ran, so nothing was verified and nothing is ranked."

_STATUS_MARK = {
    CheckStatus.PASS: "pass",
    CheckStatus.PARTIAL: "partial",
    CheckStatus.FAIL: "FAIL",
    CheckStatus.NOT_APPLICABLE: "n/a",
}


def format_effort(minutes: int) -> str:
    """Human-readable effort. Deterministic: no locale, no rounding drift."""
    if minutes < 60:
        return f"{minutes}m"
    hours, remainder = divmod(minutes, 60)
    return f"{hours}h" if remainder == 0 else f"{hours}h{remainder:02d}m"


def build(report: Report) -> dict[str, Any]:
    """Flatten a Report into the structure the templates walk."""
    findings_by_axis: dict[str, list[Any]] = {axis.key.value: [] for axis in report.axes}
    for finding in report.findings:
        findings_by_axis[finding.axis.value].append(finding)

    axes = []
    for axis in report.axes:
        findings = findings_by_axis[axis.key.value]
        axes.append(
            {
                "key": axis.key.value,
                "name": axis.name,
                "score": axis.score,
                "score_text": "N/A" if axis.score is None else str(axis.score),
                "letter": axis.letter.value,
                "failed": sum(1 for c in axis.checks if c.status is CheckStatus.FAIL),
                "checks": [
                    {
                        "id": c.id,
                        "title": c.title,
                        "status": c.status.value,
                        "mark": _STATUS_MARK[c.status],
                        "weight": c.weight,
                        "detail": c.detail,
                    }
                    for c in axis.checks
                ],
                "findings": [
                    {
                        "id": f.id,
                        "check_id": f.check_id,
                        "severity": f.severity.value,
                        "title": f.title,
                        "explanation": f.explanation,
                        "evidence": [
                            {
                                "path": e.path,
                                "line": e.line,
                                "location": f"{e.path}:{e.line}" if e.line else e.path,
                                "snippet": e.snippet,
                            }
                            for e in f.evidence
                        ],
                    }
                    for f in findings
                ],
            }
        )

    fixes = [
        {
            "id": fix.id,
            "title": fix.title,
            "axis": fix.axis.value,
            "steps": list(fix.steps),
            "points": fix.risk_reduction,
            "effort": format_effort(fix.effort_minutes),
            "ratio": f"{fix.ratio:.1f}",
        }
        for fix in report.fixes
    ]

    # An unmeasured repo is not a clean one; the empty state must say which.
    measured = any(axis.score is not None for axis in report.axes)

    return {
        "schema_version": report.schema_version,
        "repo": {
            "source": report.repo.source,
            "commit": (report.repo.commit_sha or "")[:12] or "(no commits)",
            "branch": report.repo.default_branch or "(detached)",
            "analyzed": report.repo.analyzed_file_count,
            "total": report.repo.file_count,
            "truncated": report.repo.truncated,
            "languages": sorted(report.repo.languages.items(), key=lambda kv: (-kv[1], kv[0])),
        },
        "overall": {
            "score": report.overall.score,
            "score_text": "N/A" if report.overall.score is None else str(report.overall.score),
            "letter": report.overall.letter.value,
            "capped": report.overall.capped,
            "cap_reason": report.overall.cap_reason,
        },
        "axes": axes,
        "fixes": fixes,
        "llm": {
            "used": report.llm.used,
            "model": report.llm.model,
            "cost": f"{report.llm.cost_usd:.4f}",
            "fallback_reason": report.llm.fallback_reason,
        },
        "generated_at": report.generated_at.strftime("%Y-%m-%d %H:%M UTC"),
        "no_findings": NO_FINDINGS,
        "no_fixes": NO_FIXES if measured else NO_FIXES_UNMEASURED,
    }
