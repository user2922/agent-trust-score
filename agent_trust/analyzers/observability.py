"""Observability -- can a human reconstruct what the agent did afterwards?

The distinction that matters here is installed versus wired up. An error
reporter listed in the dependencies but never initialised reports nothing, so it
scores `partial`, not `pass`. That is the common case in real repositories.
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

AXIS = AxisKey.OBSERVABILITY

OB_01 = CheckSpec("OB-01", "Structured logging", 25)
OB_02 = CheckSpec("OB-02", "Logging rather than printing", 10)
OB_03 = CheckSpec("OB-03", "Error reporting wired", 20)
OB_04 = CheckSpec("OB-04", "Audit trail pattern", 15)
OB_05 = CheckSpec("OB-05", "Commit hygiene", 15)
OB_06 = CheckSpec("OB-06", "Changelog", 5)
OB_07 = CheckSpec("OB-07", "Liveness surface", 10)

SPECS = (OB_01, OB_02, OB_03, OB_04, OB_05, OB_06, OB_07)
assert_weights(AXIS, SPECS)

# OB-05: below this many commits there is not enough history to judge, and a
# false fail here reads as noise rather than as advice.
MIN_COMMITS_TO_JUDGE = 10
HYGIENE_PASS = 0.60
HYGIENE_PARTIAL = 0.40
MIN_SUBJECT_LENGTH = 15

# Excluded from every content check on this axis, not just OB-02.
#
# A print in a test is not a logging-strategy failure -- and, the direction that
# actually bit: a fixture, a tutorial or a generator string is not the repo's own
# error reporting. Reading them as such gave this tool three false passes on its
# own repository, and would credit any project that ships example code in docs/.
NON_APPLICATION_DIRS = ("tests/", "test/", "scripts/", "examples/", "docs/", "bin/")
SOURCE_SUFFIXES = (".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rb", ".java", ".rs", ".sql")


def _dependencies(ctx: RepoContext) -> set[str]:
    names: set[str] = set()
    if ctx.package_json:
        for field in ("dependencies", "devDependencies"):
            section = ctx.package_json.get(field)
            if isinstance(section, dict):
                names.update(str(key) for key in section)
    if ctx.pyproject:
        project = ctx.pyproject.get("project")
        if isinstance(project, dict):
            for entry in project.get("dependencies") or []:
                names.add(
                    str(entry).split("[")[0].split("=")[0].split(">")[0].split("<")[0].strip()
                )
    return names


def application_files(ctx: RepoContext, suffixes: tuple[str, ...] | None = None) -> list[str]:
    """Source files that are application code -- not tests, scripts or docs."""
    wanted = suffixes or (".py", ".ts", ".tsx", ".js", ".jsx")
    return [
        path
        for path in ctx.files
        if path.endswith(wanted)
        and not path.startswith(NON_APPLICATION_DIRS)
        and not any(f"/{d}" in f"/{path}" for d in NON_APPLICATION_DIRS)
    ]


def check_structured_logging(ctx: RepoContext) -> CheckResult:
    """OB-01: a logging library or configuration, not ad-hoc output."""
    declared = _dependencies(ctx) & p.STRUCTURED_LOGGING_DEPENDENCIES
    if declared:
        return result(OB_01, CheckStatus.PASS, f"Declares {sorted(declared)[0]}.")

    for path in application_files(ctx, (".py", ".ts", ".js")):
        if p.STRUCTURED_LOGGING.search(ctx.read_text(path)):
            return result(
                OB_01,
                CheckStatus.PASS,
                f"Configures logging in {path}.",
                [evidence_for_path(path, "structured_logging")],
            )
    return result(OB_01, CheckStatus.FAIL, searched("structlog, pino, winston", "a logging config"))


def count_logging_calls(ctx: RepoContext) -> tuple[int, int]:
    """(logger calls, print calls) across application code only."""
    loggers = prints = 0
    for path in application_files(ctx):
        text = ctx.read_text(path)
        loggers += len(p.LOGGER_CALL.findall(text))
        prints += len(p.PRINT_CALL.findall(text))
    return loggers, prints


def check_logging_over_printing(ctx: RepoContext) -> CheckResult:
    """OB-02: logging calls at least match print calls in application code."""
    loggers, prints = count_logging_calls(ctx)
    detail = f"{loggers} logger call(s) to {prints} print call(s) in application code."

    if loggers == 0 and prints == 0:
        return result(
            OB_02, CheckStatus.NOT_APPLICABLE, "No logging or printing in application code."
        )
    if loggers >= prints:
        return result(OB_02, CheckStatus.PASS, detail)
    return result(OB_02, CheckStatus.FAIL, detail)


def check_error_reporting(ctx: RepoContext) -> CheckResult:
    """OB-03: a monitor that is initialised, not merely installed.

    An installed-but-never-initialised reporter is the common real-world case and
    it reports nothing, so it scores partial.
    """
    for path in application_files(ctx):
        if p.ERROR_REPORTING_INIT.search(ctx.read_text(path)):
            return result(
                OB_03,
                CheckStatus.PASS,
                f"Initialised in {path}.",
                [evidence_for_path(path, "error_reporting_init")],
            )

    declared = _dependencies(ctx) & p.ERROR_REPORTING_DEPENDENCIES
    if declared:
        return result(
            OB_03,
            CheckStatus.PARTIAL,
            f"{sorted(declared)[0]} is a dependency but no initialisation call was found. "
            "An uninitialised reporter reports nothing.",
        )
    return result(OB_03, CheckStatus.FAIL, searched("Sentry, Rollbar, Bugsnag or OpenTelemetry"))


def check_audit_trail(ctx: RepoContext) -> CheckResult:
    """OB-04: a record of who did what, when."""
    for path in application_files(ctx, SOURCE_SUFFIXES):
        text = ctx.read_text(path)
        if p.AUDIT_TRAIL.search(text):
            return result(
                OB_04,
                CheckStatus.PASS,
                f"Audit trail in {path}.",
                [evidence_for_path(path, "audit_trail")],
            )
    for path in application_files(ctx, SOURCE_SUFFIXES):
        if p.AUDIT_TRIPLE.search(ctx.read_text(path)):
            return result(
                OB_04,
                CheckStatus.PARTIAL,
                f"{path} records an actor, an action and a timestamp together, but nothing is "
                "named as an audit trail.",
            )
    return result(
        OB_04, CheckStatus.FAIL, searched("an audit_log table", "an actor+action+time record")
    )


def check_commit_hygiene(ctx: RepoContext) -> CheckResult:
    """OB-05: commit subjects that say what changed.

    Fewer than ten commits is not_applicable rather than a failure: there is not
    enough history to judge, and a false fail here reads as noise.
    """
    subjects = ctx.commit_subjects
    if len(subjects) < MIN_COMMITS_TO_JUDGE:
        return result(
            OB_05,
            CheckStatus.NOT_APPLICABLE,
            f"Only {len(subjects)} commit(s); too little history to judge.",
        )

    informative = [
        subject
        for subject in subjects
        if len(subject) >= MIN_SUBJECT_LENGTH and not p.EMPTY_COMMIT_SUBJECT.match(subject)
    ]
    ratio = len(informative) / len(subjects)
    detail = (
        f"{len(informative)} of {len(subjects)} recent commit subjects "
        f"are informative ({ratio:.0%})."
    )

    if ratio >= HYGIENE_PASS:
        return result(OB_05, CheckStatus.PASS, detail)
    if ratio >= HYGIENE_PARTIAL:
        return result(OB_05, CheckStatus.PARTIAL, detail)
    return result(OB_05, CheckStatus.FAIL, detail)


def check_changelog(ctx: RepoContext) -> CheckResult:
    """OB-06: a human-readable record of what shipped."""
    found = ctx.paths_named(*p.CHANGELOG_NAMES)
    if found:
        return result(OB_06, CheckStatus.PASS, f"Found {found[0]}.")
    if any(path.startswith(p.RELEASE_DIRS) for path in ctx.files):
        return result(OB_06, CheckStatus.PASS, "Found a release-notes directory.")
    return result(OB_06, CheckStatus.FAIL, searched("CHANGELOG.md", "a releases directory"))


def check_liveness(ctx: RepoContext) -> CheckResult:
    """OB-07: a health endpoint, or a version flag on the CLI."""
    for path in application_files(ctx, (".py", ".ts", ".tsx", ".js", ".go", ".rb")):
        if p.HEALTH_ENDPOINT.search(ctx.read_text(path)):
            return result(
                OB_07,
                CheckStatus.PASS,
                f"Health surface in {path}.",
                [evidence_for_path(path, "health_endpoint")],
            )
    version_sources = application_files(ctx, (".py", ".ts", ".js")) + list(
        ctx.paths_named("pyproject.toml")
    )
    for path in version_sources:
        if p.VERSION_FLAG.search(ctx.read_text(path)):
            return result(OB_07, CheckStatus.PASS, f"Version surface in {path}.")
    return result(OB_07, CheckStatus.FAIL, searched("a /health route", "a --version flag"))


CHECKS = (
    check_structured_logging,
    check_logging_over_printing,
    check_error_reporting,
    check_audit_trail,
    check_commit_hygiene,
    check_changelog,
    check_liveness,
)


def run(ctx: RepoContext) -> Sequence[CheckResult]:
    """Run every Observability check, in spec order."""
    return [check(ctx) for check in CHECKS]


register(AXIS, run)
