"""Context Quality -- does the repo explain itself to an agent?

This is the axis most tempting to hand to a model. It is not handed to a model.
Detection here is structural and deterministic: headings, command shapes, and
whether cited paths resolve. Prompt 14 may write prose *about* the result; it may
not decide the result.

Sections are matched on heading text **or** on the commands themselves, because a
doc that shows `uv sync` without a "Setup" heading has still told an agent what to
run, and scoring it as missing would be wrong.
"""

from __future__ import annotations

from collections.abc import Sequence

from agent_trust.analyzers import (
    CheckSpec,
    assert_weights,
    evidence_for_path,
    register,
    result,
    searched,
)
from agent_trust.analyzers import patterns as p
from agent_trust.inventory import RepoContext
from agent_trust.models import AxisKey, CheckResult, CheckStatus

AXIS = AxisKey.CONTEXT_QUALITY

CQ_01 = CheckSpec("CQ-01", "Agent instruction file exists", 20)
CQ_02 = CheckSpec("CQ-02", "README with substance", 10)
CQ_03 = CheckSpec("CQ-03", "Setup commands documented", 15)
CQ_04 = CheckSpec("CQ-04", "Architecture summary", 15)
CQ_05 = CheckSpec("CQ-05", "Run and test commands documented", 15)
CQ_06 = CheckSpec("CQ-06", "Conventions stated", 10)
CQ_07 = CheckSpec("CQ-07", "Do-not-touch list", 10)
CQ_08 = CheckSpec("CQ-08", "Docs resolve to reality", 5)

SPECS = (CQ_01, CQ_02, CQ_03, CQ_04, CQ_05, CQ_06, CQ_07, CQ_08)
assert_weights(AXIS, SPECS)

README_PASS_WORDS = 300
README_PARTIAL_WORDS = 100

PATHS_RESOLVE_PASS = 0.80
PATHS_RESOLVE_PARTIAL = 0.50
MAX_UNRESOLVED_EVIDENCE = 10


def agent_doc(ctx: RepoContext) -> str | None:
    """The agent instruction file this repo uses, in preference order.

    Returns one path even when several exist, so a repo carrying both CLAUDE.md
    and AGENTS.md is scored once rather than twice.
    """
    for candidate in p.AGENT_DOC_PATHS:
        for path in ctx.files:
            if path == candidate or path.rsplit("/", 1)[-1] == candidate:
                return path
    return None


def readme(ctx: RepoContext) -> str | None:
    for candidate in p.README_PATHS:
        for path in ctx.files:
            if path.lower() == candidate.lower():
                return path
    return None


def prose_words(text: str) -> int:
    """Word count with code fences and inline code removed.

    A README that is one long code block is not orientation, and counting the
    code would credit it as though it were.
    """
    stripped = p.INLINE_CODE.sub(" ", p.CODE_FENCE.sub(" ", text))
    return len([word for word in stripped.split() if any(ch.isalpha() for ch in word)])


def _documents(ctx: RepoContext) -> list[tuple[str, str]]:
    """(path, text) for the agent doc and the README, whichever exist."""
    pairs = []
    for path in (agent_doc(ctx), readme(ctx)):
        if path:
            pairs.append((path, ctx.read_text(path)))
    return pairs


def _first_match(
    ctx: RepoContext, *patterns: object, label: str, spec: CheckSpec
) -> CheckResult | None:
    """Pass on the first document matching any pattern, naming that document."""
    for path, text in _documents(ctx):
        for pattern in patterns:
            if pattern.search(text):  # type: ignore[attr-defined]
                return result(
                    spec,
                    CheckStatus.PASS,
                    f"{path} documents {label}.",
                    [evidence_for_path(path, spec.id.lower())],
                )
    return None


def check_agent_doc(ctx: RepoContext) -> CheckResult:
    """CQ-01: an agent instruction file exists and is not empty."""
    path = agent_doc(ctx)
    if path and prose_words(ctx.read_text(path)) > 0:
        return result(
            CQ_01, CheckStatus.PASS, f"Found {path}.", [evidence_for_path(path, "agent_doc")]
        )
    if path:
        return result(CQ_01, CheckStatus.FAIL, f"{path} exists but is empty.")
    return result(CQ_01, CheckStatus.FAIL, searched(*p.AGENT_DOC_PATHS))


def check_readme(ctx: RepoContext) -> CheckResult:
    """CQ-02: a README with real prose, code blocks excluded."""
    path = readme(ctx)
    if not path:
        return result(CQ_02, CheckStatus.FAIL, searched("README.md"))

    words = prose_words(ctx.read_text(path))
    detail = f"{path}: {words} words of prose, excluding code blocks."
    if words >= README_PASS_WORDS:
        return result(CQ_02, CheckStatus.PASS, detail)
    if words >= README_PARTIAL_WORDS:
        return result(CQ_02, CheckStatus.PARTIAL, detail)
    return result(CQ_02, CheckStatus.FAIL, detail)


def check_setup_commands(ctx: RepoContext) -> CheckResult:
    """CQ-03: a setup heading, or the install commands themselves."""
    found = _first_match(ctx, p.SETUP_HEADING, p.SETUP_COMMAND, label="setup commands", spec=CQ_03)
    return found or result(
        CQ_03, CheckStatus.FAIL, searched("a setup heading", "an install command")
    )


def check_architecture(ctx: RepoContext) -> CheckResult:
    """CQ-04: an architecture section, or a directory map."""
    found = _first_match(
        ctx, p.ARCHITECTURE_HEADING, p.DIRECTORY_TREE, label="the architecture", spec=CQ_04
    )
    return found or result(
        CQ_04, CheckStatus.FAIL, searched("an architecture heading", "a directory map")
    )


def check_run_and_test(ctx: RepoContext) -> CheckResult:
    """CQ-05: both a run command and a test command, or a section documenting them.

    The most common cause of an agent declaring work done without verifying it is
    not knowing how to run the tests, so a test command specifically is required.
    """
    for path, text in _documents(ctx):
        has_test = bool(p.TEST_COMMAND.search(text))
        has_run = bool(p.RUN_COMMAND.search(text))
        if has_test and has_run:
            return result(
                CQ_05,
                CheckStatus.PASS,
                f"{path} documents both run and test commands.",
                [evidence_for_path(path, "run_test_commands")],
            )
        if has_test or has_run:
            missing = "a run command" if has_test else "a test command"
            return result(CQ_05, CheckStatus.PARTIAL, f"{path} is missing {missing}.")
    return result(CQ_05, CheckStatus.FAIL, searched("a documented run command", "a test command"))


def check_conventions(ctx: RepoContext) -> CheckResult:
    """CQ-06: a conventions or style section."""
    found = _first_match(ctx, p.CONVENTIONS_HEADING, label="conventions", spec=CQ_06)
    return found or result(CQ_06, CheckStatus.FAIL, searched("a conventions or style section"))


def check_do_not_touch(ctx: RepoContext) -> CheckResult:
    """CQ-07: an explicit do-not-edit or generated-files list."""
    found = _first_match(ctx, p.DO_NOT_TOUCH, label="what not to edit", spec=CQ_07)
    return found or result(
        CQ_07, CheckStatus.FAIL, searched("a do-not-edit or generated-files list")
    )


def check_paths_resolve(ctx: RepoContext) -> CheckResult:
    """CQ-08: the paths the agent doc cites still exist.

    Documentation pointing at files that no longer exist is worse than none,
    because the agent trusts it.
    """
    path = agent_doc(ctx)
    if not path:
        return result(CQ_08, CheckStatus.NOT_APPLICABLE, "No agent doc to check paths against.")

    known = set(ctx.files)
    directories = {
        f"{part}/" for file in ctx.files for part in (file.rsplit("/", 1)[0],) if "/" in file
    }
    cited = sorted(set(p.CITED_PATH.findall(ctx.read_text(path))))
    if not cited:
        return result(CQ_08, CheckStatus.NOT_APPLICABLE, f"{path} cites no paths.")

    def resolves(token: str) -> bool:
        """True when a cited token points at something that exists.

        A doc legitimately cites `analyzers/patterns.py` for a file that lives at
        `agent_trust/analyzers/patterns.py`, so a suffix match counts. Requiring
        an exact repo-relative path would report accurate documentation as stale.
        """
        if token in known:
            return True
        trimmed = token.rstrip("/")
        if f"{trimmed}/" in directories or any(d.startswith(f"{trimmed}/") for d in directories):
            return True
        return any(
            existing.startswith(token) or existing.endswith(f"/{trimmed}") for existing in known
        )

    unresolved = [token for token in cited if not resolves(token)]
    resolved = len(cited) - len(unresolved)
    ratio = resolved / len(cited)
    detail = f"{resolved} of {len(cited)} cited paths resolve ({ratio:.0%})."
    if unresolved:
        detail += " Missing: " + ", ".join(unresolved[:MAX_UNRESOLVED_EVIDENCE]) + "."

    if ratio >= PATHS_RESOLVE_PASS:
        return result(CQ_08, CheckStatus.PASS, detail)
    if ratio >= PATHS_RESOLVE_PARTIAL:
        return result(CQ_08, CheckStatus.PARTIAL, detail)
    return result(CQ_08, CheckStatus.FAIL, detail)


CHECKS = (
    check_agent_doc,
    check_readme,
    check_setup_commands,
    check_architecture,
    check_run_and_test,
    check_conventions,
    check_do_not_touch,
    check_paths_resolve,
)


def run(ctx: RepoContext) -> Sequence[CheckResult]:
    """Run every Context Quality check, in spec order."""
    return [check(ctx) for check in CHECKS]


register(AXIS, run)
