"""Turn non-passing checks into findings, with severity fixed by rule.

Severity is derived, never judged: SPEC.md maps it from the check's weight and
status. The model may later replace ``explanation`` and nothing else, so the
template text here has to stand on its own -- every audit run without an API key
uses it.
"""

from __future__ import annotations

from collections.abc import Sequence

from agent_trust.models import (
    AxisKey,
    CheckResult,
    CheckStatus,
    ExplanationSource,
    Finding,
    Severity,
)

SECRET_CHECK_ID = "BR-01"  # noqa: S105 - a check id, not a credential

HIGH_WEIGHT_THRESHOLD = 20
MEDIUM_WEIGHT_THRESHOLD = 10

# Why each check matters, in one sentence, for the no-LLM path.
WHY: dict[str, str] = {
    "TS-01": "Without a declared MCP server an agent has no typed way to call this code, so it falls back to guessing at shell commands.",
    "TS-02": "With no machine-readable API schema an agent infers request shapes from source, and infers them wrong at the edges.",
    "TS-03": "No declared CLI entry point means an agent cannot discover how to invoke this project without reading the source.",
    "TS-04": "Entry points that are not documented get called with invented flags.",
    "TS-05": "Untyped public boundaries give an agent nothing to check its calls against before running them.",
    "TS-06": "A package manifest that does not parse hides the dependency and script information an agent needs to orient.",
    "TS-07": "With no documented config contract an agent cannot tell which environment variables are required.",
    "BR-01": "A committed secret is live credential material in every clone, and an agent with repository access can read and transmit it.",
    "BR-02": "A tracked .env file puts real environment values in history where they outlive any later deletion.",
    "BR-03": "Without .gitignore coverage the next careless `git add -A` commits credentials.",
    "BR-04": "An unguarded destructive operation is one confident agent action away from data loss, with no dry run to catch it first.",
    "BR-05": "An admin-scoped credential reachable from client code bypasses every access control behind it.",
    "BR-06": "Payment, email and webhook calls with no test-mode switch send real messages and move real money during development.",
    "BR-07": "With no ownership or protection config, nothing forces review of a change an agent proposes.",
    "VF-01": "With no test suite an agent cannot tell a working change from a broken one, and neither can you.",
    "VF-02": "An undeclared test runner means an agent has to guess the command, and a wrong guess reads as a passing run.",
    "VF-03": "Test coverage this thin leaves most of the codebase unverified after any agent edit.",
    "VF-04": "No CI configuration means nothing checks a change except the person who wrote it.",
    "VF-05": "A CI pipeline that never runs the tests is decoration: it goes green regardless of whether the code works.",
    "VF-06": "Without type checking, a whole class of agent mistake reaches runtime instead of the editor.",
    "VF-07": "No lint configuration means style and correctness drift accumulate unreviewed.",
    "VF-08": "With no commit-time gate, a broken change reaches the branch before anything objects.",
    "CQ-01": "With no agent instruction file, every session starts from zero and rediscovers the same conventions differently.",
    "CQ-02": "A README this thin gives an agent no orientation, so it infers the architecture from whichever file it opens first.",
    "CQ-03": "Undocumented setup commands mean an agent guesses at the install sequence and reports success it did not achieve.",
    "CQ-04": "With no architecture summary an agent has to reconstruct the design from source every time.",
    "CQ-05": "Undocumented run and test commands are the single most common cause of an agent declaring work done without verifying it.",
    "CQ-06": "Unstated conventions get violated, and the violations look like ordinary code in review.",
    "CQ-07": "With no do-not-touch list an agent edits generated files, and the edits vanish at the next build.",
    "CQ-08": "Documentation pointing at files that no longer exist is worse than none, because the agent trusts it.",
    "OB-01": "Without structured logging there is no record of what an agent-driven process actually did.",
    "OB-02": "Print statements scattered where logging belongs mean the useful output is unfiltered and unsearchable.",
    "OB-03": "With no error reporting, a failure an agent introduces surfaces as a user complaint rather than an alert.",
    "OB-04": "No audit trail means no way to reconstruct which actor changed what, after the fact.",
    "OB-05": "Commit subjects this thin make the history useless for working out when a behaviour changed.",
    "OB-06": "With no changelog there is no human-readable record of what shipped.",
    "OB-07": "No health or version surface means nothing can confirm which build is actually running.",
}

_FALLBACK_WHY = "This check did not pass, which limits how safely an agent can operate here."


def severity_for(check: CheckResult) -> Severity:
    """Map a check result to its severity, deterministically.

    A failed BR-01 is always high: a committed secret is not a matter of degree.
    """
    if check.id == SECRET_CHECK_ID and check.status is CheckStatus.FAIL:
        return Severity.HIGH
    if check.status is CheckStatus.FAIL:
        if check.weight >= HIGH_WEIGHT_THRESHOLD:
            return Severity.HIGH
        if check.weight >= MEDIUM_WEIGHT_THRESHOLD:
            return Severity.MEDIUM
    return Severity.LOW


def template_explanation(check: CheckResult) -> str:
    """The no-LLM explanation. Prompt 14 may replace this string and nothing else."""
    why = WHY.get(check.id, _FALLBACK_WHY)
    if check.status is CheckStatus.PARTIAL:
        return f"Partially satisfied. {why}"
    return why


def findings_for(axis: AxisKey, checks: Sequence[CheckResult]) -> list[Finding]:
    """One finding per non-passing, applicable check, in check-id order."""
    findings: list[Finding] = []
    for check in sorted(checks, key=lambda item: item.id):
        if check.status in (CheckStatus.PASS, CheckStatus.NOT_APPLICABLE):
            continue
        findings.append(
            Finding(
                id=f"F-{check.id}",
                check_id=check.id,
                axis=axis,
                severity=severity_for(check),
                title=check.title,
                evidence=check.evidence,
                explanation=template_explanation(check),
                explanation_source=ExplanationSource.TEMPLATE,
            )
        )
    return findings
