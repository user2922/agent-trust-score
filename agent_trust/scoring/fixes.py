"""Build and rank the fix list.

The ranking is the product's advice, so it is a total order with no ties left to
chance: ratio, then severity, then axis order, then check id. Two runs over the
same commit produce the same list in the same order (rule D).
"""

from __future__ import annotations

from collections.abc import Sequence

from agent_trust.models import AXIS_ORDER, CheckResult, CheckStatus, Finding, Fix, Severity
from agent_trust.scoring.effort import effort_for

_SEVERITY_RANK = {Severity.HIGH: 0, Severity.MEDIUM: 1, Severity.LOW: 2}

# How to close each check, in imperative steps. The model may rewrite these
# (rule B); it may not add or remove a fix.
STEPS: dict[str, tuple[str, ...]] = {
    "TS-01": ("Add an MCP server exposing your main operations as typed tools.",),
    "TS-02": ("Publish an OpenAPI or GraphQL schema for the public surface.",),
    "TS-03": ("Declare a console entry point in the package manifest.",),
    "TS-04": ("Add a usage block to the README showing a real invocation with flags.",),
    "TS-05": ("Enable strict type checking and annotate the public functions first.",),
    "TS-06": ("Fix the package manifest so it parses.",),
    "TS-07": ("Add a .env.example listing every variable with a placeholder value.",),
    "BR-01": (
        "Rotate the exposed credential now -- it is in every clone and in history.",
        "Remove it from the working tree and move the value to an environment variable.",
        "Purge it from history, or treat the repository as compromised.",
    ),
    "BR-02": (
        "Untrack the .env file with `git rm --cached`.",
        "Add it to .gitignore and rotate anything it contained.",
    ),
    "BR-03": ("Add .env, key and credential patterns, and build output to .gitignore.",),
    "BR-04": (
        "Add a --dry-run flag that prints the plan without executing it.",
        "Require an explicit confirmation or environment gate for the real run.",
    ),
    "BR-05": ("Move the admin credential server-side and give client code a scoped one.",),
    "BR-06": ("Put payment, email and webhook calls behind a test-mode switch.",),
    "BR-07": ("Add a CODEOWNERS file so changes need a named reviewer.",),
    "VF-01": ("Add a test suite, starting with the paths an agent is most likely to edit.",),
    "VF-02": ("Declare the test runner in the package manifest.",),
    "VF-03": ("Raise test coverage of the modules that change most often.",),
    "VF-04": ("Add a CI workflow that runs on push and pull request.",),
    "VF-05": ("Add a step to the CI workflow that actually runs the test suite.",),
    "VF-06": ("Turn on strict type checking and fix what it reports.",),
    "VF-07": ("Add a lint configuration and wire it into CI.",),
    "VF-08": ("Add a pre-commit hook running lint and type checks.",),
    "CQ-01": ("Add a CLAUDE.md or AGENTS.md describing setup, architecture and conventions.",),
    "CQ-02": ("Expand the README past a stub: what it is, how to run it, how it fits together.",),
    "CQ-03": ("Document the exact setup commands, copy-pasteable.",),
    "CQ-04": ("Add an architecture section: the directory map and what each part owns.",),
    "CQ-05": ("Document the commands to run the app and to run the tests.",),
    "CQ-06": ("Write down the conventions a new contributor would otherwise violate.",),
    "CQ-07": ("List the generated and vendored paths that must not be edited by hand.",),
    "CQ-08": ("Update the paths cited in the agent doc so they resolve.",),
    "OB-01": ("Adopt a structured logger and route existing output through it.",),
    "OB-02": ("Replace print and console.log calls in application code with logger calls.",),
    "OB-03": ("Wire an error reporter and initialize it at startup.",),
    "OB-04": ("Record actor, action and timestamp for every state-changing operation.",),
    "OB-05": ("Write commit subjects that say what changed and why.",),
    "OB-06": ("Add a CHANGELOG recording what shipped in each release.",),
    "OB-07": ("Expose a health endpoint, or a --version flag on the CLI.",),
}

_FALLBACK_STEP = "Address the finding described above."


def _recoverable_points(check: CheckResult) -> int:
    """Axis points this fix would recover.

    A failed check recovers its full weight; a partial recovers the half it did
    not earn. Points are axis-local, which is what a user reads on the axis row.
    """
    if check.status is CheckStatus.PARTIAL:
        return check.weight - int(check.earned)
    return check.weight


def build_fixes(findings: Sequence[Finding], checks_by_id: dict[str, CheckResult]) -> list[Fix]:
    """One fix per finding, ranked by risk reduction per hour of effort."""
    fixes: list[Fix] = []
    for finding in findings:
        check = checks_by_id.get(finding.check_id)
        if check is None:  # pragma: no cover - findings are built from checks
            continue
        points = _recoverable_points(check)
        minutes = effort_for(finding.check_id)
        fixes.append(
            Fix(
                id=f"FIX-{finding.check_id}",
                finding_ids=(finding.id,),
                axis=finding.axis,
                title=check.title,
                steps=STEPS.get(finding.check_id, (_FALLBACK_STEP,)),
                risk_reduction=points,
                effort_minutes=minutes,
                ratio=round(points / (minutes / 60), 4),
            )
        )

    severity_by_finding = {finding.id: finding.severity for finding in findings}

    def sort_key(fix: Fix) -> tuple[float, int, int, str]:
        severity = severity_by_finding.get(fix.finding_ids[0], Severity.LOW)
        return (
            -fix.ratio,
            _SEVERITY_RANK[severity],
            AXIS_ORDER.index(fix.axis.value),
            fix.id,
        )

    return sorted(fixes, key=sort_key)
