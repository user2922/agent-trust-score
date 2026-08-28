"""Blast Radius -- what can go wrong if the agent acts?

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


@dataclass(frozen=True)
class OpHit:
    """One destructive operation and the guard found near it, if any."""

    path: str
    line: int
    family: str
    guard: str | None


def _guard_near(ctx: RepoContext, path: str, line_number: int) -> str | None:
    """The guard protecting an operation, or None.

    The window is GUARD_WINDOW_LINES either side of the operation. A guard
    further away is almost certainly protecting something else, and counting it
    would let one dry-run flag at the top of a 500-line file excuse every
    destructive call below it.
    """
    lines = ctx.read_lines(path)
    start = max(0, line_number - 1 - p.GUARD_WINDOW_LINES)
    end = min(len(lines), line_number + p.GUARD_WINDOW_LINES)
    window = "\n".join(lines[start:end])
    for name, pattern in p.DESTRUCTIVE_GUARDS:
        if pattern.search(window):
            return name
    return None


def scan_destructive_ops(ctx: RepoContext) -> list[OpHit]:
    """Every destructive operation found, each with its guard or None."""
    hits: list[OpHit] = []
    for path in ctx.files:
        if _path_is_allowlisted(path):
            continue
        for number, line in enumerate(ctx.read_lines(path), start=1):
            for family, pattern in p.DESTRUCTIVE_OPS:
                if pattern.search(line):
                    hits.append(
                        OpHit(
                            path=path,
                            line=number,
                            family=family,
                            guard=_guard_near(ctx, path, number),
                        )
                    )
                    break
    return hits


def _line_evidence(ctx: RepoContext, path: str, line_number: int, matcher: str) -> Evidence:
    """Evidence quoting a whole line, trimmed and stripped by the redactor."""
    lines = ctx.read_lines(path)
    line = lines[line_number - 1] if 0 < line_number <= len(lines) else ""
    return Evidence(path=path, line=line_number, snippet=snippet(line, 0, 0), matcher=matcher)


def check_destructive_ops_guarded(ctx: RepoContext) -> CheckResult:
    """BR-04: every destructive operation sits behind a guard."""
    hits = scan_destructive_ops(ctx)
    if not hits:
        return result(BR_04, CheckStatus.PASS, "No destructive operations detected.")

    unguarded = [hit for hit in hits if hit.guard is None]
    if not unguarded:
        guards = sorted({hit.guard for hit in hits if hit.guard})
        return result(
            BR_04,
            CheckStatus.PASS,
            f"All {len(hits)} destructive operation(s) guarded by: {', '.join(guards)}.",
        )

    evidence = [
        _line_evidence(ctx, hit.path, hit.line, hit.family)
        for hit in unguarded[:MAX_SECRET_EVIDENCE]
    ]
    families = ", ".join(sorted({hit.family for hit in unguarded}))
    detail = (
        f"{len(unguarded)} of {len(hits)} destructive operation(s) unguarded ({families}). "
        f"Looked for a dry-run flag, a confirmation, an environment gate or a force flag "
        f"within {p.GUARD_WINDOW_LINES} lines."
    )
    status = CheckStatus.PARTIAL if len(unguarded) < len(hits) else CheckStatus.FAIL
    return result(BR_04, status, detail, evidence)


def _is_client_reachable(path: str) -> bool:
    """Reachability by path convention. Every finding states the method used."""
    lowered = path.lower()
    if lowered.endswith(p.CLIENT_REACHABLE_SUFFIXES):
        return True
    if p.CLIENT_FILE_MARKER.search(lowered):
        return True
    return any(f"/{directory}" in f"/{lowered}" for directory in p.CLIENT_REACHABLE_DIRS)


def check_admin_credential_reach(ctx: RepoContext) -> CheckResult:
    """BR-05: no admin-scoped credential named in client-reachable code."""
    method = "Reachability was judged by path convention, not by import graph."
    hits: list[Evidence] = []
    for path in ctx.files:
        if not _is_client_reachable(path) or _path_is_allowlisted(path):
            continue
        for number, line in enumerate(ctx.read_lines(path), start=1):
            match = p.ADMIN_CREDENTIAL.search(line)
            if match:
                hits.append(
                    Evidence(
                        path=path,
                        line=number,
                        snippet=snippet(line, match.start(), match.end()),
                        matcher="admin_credential",
                    )
                )

    if not hits:
        return result(
            BR_05, CheckStatus.PASS, f"No admin credential in client-reachable paths. {method}"
        )
    return result(
        BR_05,
        CheckStatus.FAIL,
        f"{len(hits)} admin credential reference(s) in client-reachable paths. {method}",
        hits[:MAX_SECRET_EVIDENCE],
    )


def check_side_effect_switch(ctx: RepoContext) -> CheckResult:
    """BR-06: payment, email and webhook calls sit behind a test or env switch."""
    total = 0
    unswitched: list[Evidence] = []
    for path in ctx.files:
        if _path_is_allowlisted(path):
            continue
        lines = ctx.read_lines(path)
        has_switch = bool(p.TEST_MODE_SWITCH.search("\n".join(lines)))
        for number, line in enumerate(lines, start=1):
            if not p.SIDE_EFFECT_CALL.search(line):
                continue
            total += 1
            if not has_switch:
                unswitched.append(_line_evidence(ctx, path, number, "unswitched_side_effect"))

    if total == 0:
        return result(BR_06, CheckStatus.PASS, "No payment, email or webhook calls detected.")
    if not unswitched:
        return result(
            BR_06, CheckStatus.PASS, f"All {total} side-effecting call(s) sit behind a switch."
        )
    status = CheckStatus.PARTIAL if len(unswitched) < total else CheckStatus.FAIL
    return result(
        BR_06,
        status,
        f"{len(unswitched)} of {total} side-effecting call(s) have no test-mode or "
        "environment switch in the same file.",
        unswitched[:MAX_SECRET_EVIDENCE],
    )


def check_ownership_config(ctx: RepoContext) -> CheckResult:
    """BR-07: CODEOWNERS, or a branch-protection config."""
    owners = [path for path in ctx.files if path in p.CODEOWNERS_PATHS]
    if owners:
        return result(
            BR_07,
            CheckStatus.PASS,
            f"Found {owners[0]}.",
            [evidence_for_path(owners[0], "codeowners")],
        )
    protection = ctx.paths_named(*p.PROTECTION_CONFIG_NAMES)
    if protection:
        return result(
            BR_07,
            CheckStatus.PASS,
            f"Found {protection[0]}.",
            [evidence_for_path(protection[0], "protection_config")],
        )
    return result(BR_07, CheckStatus.FAIL, searched("CODEOWNERS", "a branch-protection config"))


CHECKS = (
    check_committed_secrets,
    check_env_not_tracked,
    check_gitignore_coverage,
    check_destructive_ops_guarded,
    check_admin_credential_reach,
    check_side_effect_switch,
    check_ownership_config,
)


def run(ctx: RepoContext) -> Sequence[CheckResult]:
    """Run every Blast Radius check, in spec order."""
    return [check(ctx) for check in CHECKS]


register(AXIS, run)
