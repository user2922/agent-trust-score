"""Blast Radius -- what can go wrong if the agent acts?

Prompt 9 implements the three secret-facing checks: BR-01, BR-02, BR-03. The
four destructive-operation checks arrive in Prompt 10 and raise
``NotImplementedError`` until then, because a check that silently returns
``pass`` would inflate every grade on this axis without anyone noticing.

BR-01 is the highest-stakes detector in the product. A false negative loses the
whole claim; a false positive on a clean repo loses the demo. Both are defects,
and the allowlist is a first-class part of the check rather than a filter bolted
on afterwards -- every suppression is counted, and the count is reported.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from agent_trust.analyzers import (
    CheckSpec,
    assert_weights,
    evidence_for_path,
    register,
    result,
    searched,
)
from agent_trust.analyzers import patterns as p
from agent_trust.analyzers.entropy import looks_random
from agent_trust.inventory import RepoContext
from agent_trust.models import AxisKey, CheckResult, CheckStatus, Evidence
from agent_trust.redact import snippet

AXIS = AxisKey.BLAST_RADIUS

BR_01 = CheckSpec("BR-01", "No committed secrets", 30)
BR_02 = CheckSpec("BR-02", ".env not tracked", 12)
BR_03 = CheckSpec("BR-03", ".gitignore covers sensitive paths", 8)
BR_04 = CheckSpec("BR-04", "Destructive operations guarded", 20)
BR_05 = CheckSpec("BR-05", "No admin credential in reachable code", 15)
BR_06 = CheckSpec("BR-06", "Side effects behind a test or env switch", 10)
BR_07 = CheckSpec("BR-07", "Ownership or protection config", 5)

SPECS = (BR_01, BR_02, BR_03, BR_04, BR_05, BR_06, BR_07)
assert_weights(AXIS, SPECS)

# Evidence is capped: a repo leaking 300 keys does not need 300 rows to make the
# point, and the report stays readable.
MAX_SECRET_EVIDENCE = 10


@dataclass(frozen=True)
class SecretHit:
    """One non-allowlisted match, already redacted."""

    path: str
    line: int
    matcher: str
    evidence: Evidence


def _path_is_allowlisted(path: str) -> bool:
    """True for paths whose contents are examples by construction."""
    lowered = path.lower()
    if lowered.startswith(p.SECRET_ALLOWLIST_PATH_PREFIXES):
        return True
    return any(marker in f"/{lowered}" for marker in p.SECRET_ALLOWLIST_PATHS)


def _value_is_allowlisted(value: str) -> bool:
    """True when the value announces itself as a placeholder or an env reference."""
    return bool(p.SECRET_ALLOWLIST_VALUES.search(value))


def scan_secrets(ctx: RepoContext) -> tuple[list[SecretHit], int]:
    """Every non-allowlisted secret match, and how many were suppressed.

    The suppression count is returned rather than discarded: a repo where the
    allowlist swallowed forty matches must not read identically to one that had
    none.
    """
    hits: list[SecretHit] = []
    suppressed = 0

    for path in ctx.files:
        path_allowlisted = _path_is_allowlisted(path)
        for number, line in enumerate(ctx.read_lines(path), start=1):
            for matcher, pattern in p.SECRET_PROVIDERS:
                match = pattern.search(line)
                if not match:
                    continue
                if path_allowlisted or _value_is_allowlisted(match.group(0)):
                    suppressed += 1
                    continue
                hits.append(
                    SecretHit(
                        path=path,
                        line=number,
                        matcher=matcher,
                        evidence=Evidence(
                            path=path,
                            line=number,
                            snippet=snippet(line, match.start(), match.end()),
                            matcher=matcher,
                        ),
                    )
                )

            generic = p.SECRET_ASSIGNMENT.search(line)
            if generic:
                value = generic.group("value")
                if path_allowlisted or _value_is_allowlisted(value) or not looks_random(value):
                    suppressed += 1
                else:
                    start, end = generic.span("value")
                    hits.append(
                        SecretHit(
                            path=path,
                            line=number,
                            matcher="high_entropy_assignment",
                            evidence=Evidence(
                                path=path,
                                line=number,
                                snippet=snippet(line, start, end),
                                matcher="high_entropy_assignment",
                            ),
                        )
                    )

    return hits, suppressed


def check_committed_secrets(ctx: RepoContext) -> CheckResult:
    """BR-01: no live-looking credential in a tracked file."""
    hits, suppressed = scan_secrets(ctx)
    suppression_note = f"{suppressed} placeholder match(es) suppressed."

    if not hits:
        return result(
            BR_01,
            CheckStatus.PASS,
            f"No committed secrets across {ctx.analyzed_file_count} files. {suppression_note}",
        )

    kinds = sorted({hit.matcher for hit in hits})
    return result(
        BR_01,
        CheckStatus.FAIL,
        f"{len(hits)} match(es): {', '.join(kinds)}. {suppression_note} "
        "Rotate before anything else -- the value is in every clone and in history.",
        [hit.evidence for hit in hits[:MAX_SECRET_EVIDENCE]],
    )


def check_env_not_tracked(ctx: RepoContext) -> CheckResult:
    """BR-02: no .env file under version control."""
    tracked = [path for path in ctx.files if path.rsplit("/", 1)[-1] in p.TRACKED_ENV_NAMES]
    if not tracked:
        return result(BR_02, CheckStatus.PASS, "No .env file is tracked.")
    return result(
        BR_02,
        CheckStatus.FAIL,
        f"Tracked: {', '.join(tracked)}. History outlives any later deletion, so rotate too.",
        [evidence_for_path(path, "tracked_env") for path in tracked[:MAX_SECRET_EVIDENCE]],
    )


def check_gitignore_coverage(ctx: RepoContext) -> CheckResult:
    """BR-03: .gitignore covers env files, credentials and build output."""
    paths = ctx.paths_named(".gitignore")
    if not paths:
        return result(BR_03, CheckStatus.FAIL, searched(".gitignore"))

    text = ctx.read_text(paths[0])
    covered = {
        "env files": bool(p.GITIGNORE_ENV.search(text)),
        "key and credential files": bool(p.GITIGNORE_KEYS.search(text)),
        "build output": bool(p.GITIGNORE_BUILD.search(text)),
    }
    missing = sorted(name for name, present in covered.items() if not present)

    if not missing:
        return result(
            BR_03, CheckStatus.PASS, f"{paths[0]} covers env, credentials and build output."
        )
    if len(missing) == len(covered):
        return result(BR_03, CheckStatus.FAIL, f"{paths[0]} covers none of: {', '.join(missing)}.")
    return result(BR_03, CheckStatus.PARTIAL, f"{paths[0]} does not cover: {', '.join(missing)}.")


def _not_implemented(spec: CheckSpec) -> CheckResult:
    """Prompt 10 owns these.

    Raising is deliberate. A check that returned ``pass`` while unimplemented
    would hand every repo 50 free points on this axis, and nothing would look
    wrong in the report.
    """
    raise NotImplementedError(f"{spec.id} is implemented in Prompt 10")


def check_destructive_ops_guarded(ctx: RepoContext) -> CheckResult:
    return _not_implemented(BR_04)


def check_admin_credential_reach(ctx: RepoContext) -> CheckResult:
    return _not_implemented(BR_05)


def check_side_effect_switch(ctx: RepoContext) -> CheckResult:
    return _not_implemented(BR_06)


def check_ownership_config(ctx: RepoContext) -> CheckResult:
    return _not_implemented(BR_07)


IMPLEMENTED = (
    check_committed_secrets,
    check_env_not_tracked,
    check_gitignore_coverage,
)


def run(ctx: RepoContext) -> Sequence[CheckResult]:
    """Run the implemented Blast Radius checks, in spec order."""
    return [check(ctx) for check in IMPLEMENTED]


register(AXIS, run)
