"""Verifiability -- can the agent prove it did not break anything?

The checks look for gates that exist **and are wired up**, never for gates that
merely exist. VF-04 and VF-05 are deliberately separate: a CI file that lints and
builds but never runs the tests passes one and fails the other, and that two-line
gap is a real finding worth reporting on its own.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import yaml

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

AXIS = AxisKey.VERIFIABILITY

VF_01 = CheckSpec("VF-01", "Test suite exists", 20)
VF_02 = CheckSpec("VF-02", "Test runner declared", 15)
VF_03 = CheckSpec("VF-03", "Test density", 15)
VF_04 = CheckSpec("VF-04", "CI config present", 15)
VF_05 = CheckSpec("VF-05", "CI actually runs tests", 15)
VF_06 = CheckSpec("VF-06", "Type checking configured", 10)
VF_07 = CheckSpec("VF-07", "Lint configured", 5)
VF_08 = CheckSpec("VF-08", "Commit-time gate", 5)

SPECS = (VF_01, VF_02, VF_03, VF_04, VF_05, VF_06, VF_07, VF_08)
assert_weights(AXIS, SPECS)

DENSITY_PASS = 0.20
DENSITY_PARTIAL = 0.10


def test_files(ctx: RepoContext) -> list[str]:
    """Every file that looks like a test, by name or by directory."""
    found = []
    for path in ctx.files:
        in_test_dir = any(path.startswith(d) or f"/{d}" in f"/{path}" for d in p.TEST_DIRS)
        named_as_test = any(pattern.search(path) for pattern in p.TEST_FILE_PATTERNS)
        if named_as_test or (in_test_dir and path.endswith(p.SOURCE_SUFFIXES)):
            found.append(path)
    return found


def source_files(ctx: RepoContext) -> list[str]:
    """Source files that are not tests -- the denominator for density."""
    tests = set(test_files(ctx))
    return [path for path in ctx.files if path.endswith(p.SOURCE_SUFFIXES) and path not in tests]


def declared_runner(ctx: RepoContext) -> str | None:
    """The test runner this repo declares, or None.

    Read from the manifests rather than from source: a runner that appears only
    in an import is not a runner the project knows how to invoke.
    """
    haystacks: list[str] = []
    if ctx.package_json:
        scripts = ctx.package_json.get("scripts")
        if isinstance(scripts, dict):
            haystacks.extend(str(value) for value in scripts.values())
        for field in ("dependencies", "devDependencies"):
            section = ctx.package_json.get(field)
            if isinstance(section, dict):
                haystacks.extend(str(name) for name in section)
    if ctx.pyproject:
        haystacks.append(str(ctx.pyproject))
    for path in ctx.paths_named("tox.ini", "noxfile.py", "Makefile", "justfile"):
        haystacks.append(ctx.read_text(path))

    combined = "\n".join(haystacks)
    for name, pattern in p.TEST_RUNNERS.items():
        if pattern.search(combined):
            return name
    return None


def check_test_suite(ctx: RepoContext) -> CheckResult:
    """VF-01: at least one test file."""
    found = test_files(ctx)
    if found:
        return result(
            VF_01,
            CheckStatus.PASS,
            f"{len(found)} test file(s).",
            [evidence_for_path(found[0], "test_file")],
        )
    return result(VF_01, CheckStatus.FAIL, searched("test_*.py", "*.test.ts", "a tests/ directory"))


def check_test_runner(ctx: RepoContext) -> CheckResult:
    """VF-02: the manifest names a runner an agent can invoke."""
    runner = declared_runner(ctx)
    if runner:
        return result(VF_02, CheckStatus.PASS, f"Declares {runner}.")
    return result(VF_02, CheckStatus.FAIL, searched("a test runner in the package manifest"))


def check_test_density(ctx: RepoContext) -> CheckResult:
    """VF-03: enough tests relative to source, with both counts reported."""
    tests, sources = len(test_files(ctx)), len(source_files(ctx))
    if sources == 0:
        return result(VF_03, CheckStatus.NOT_APPLICABLE, "No source files to measure against.")

    ratio = tests / sources
    detail = f"{tests} test file(s) to {sources} source file(s) ({ratio:.2f})."
    if ratio >= DENSITY_PASS:
        return result(VF_03, CheckStatus.PASS, detail)
    if ratio >= DENSITY_PARTIAL:
        return result(VF_03, CheckStatus.PARTIAL, detail)
    return result(VF_03, CheckStatus.FAIL, detail)


def ci_files(ctx: RepoContext) -> list[str]:
    """Every CI configuration file, at any of the standard locations."""
    return [
        path
        for path in ctx.files
        if any(
            path.startswith(glob) if glob.endswith("/") else path == glob
            for glob in p.CI_CONFIG_GLOBS
        )
    ]


def check_ci_present(ctx: RepoContext) -> CheckResult:
    """VF-04: a CI configuration exists."""
    found = ci_files(ctx)
    if found:
        return result(
            VF_04,
            CheckStatus.PASS,
            f"Found {found[0]}.",
            [evidence_for_path(found[0], "ci_config")],
        )
    return result(VF_04, CheckStatus.FAIL, searched(".github/workflows", ".gitlab-ci.yml"))


def _run_commands(document: Any) -> list[str]:
    """Every ``run:`` / ``script:`` string anywhere in a parsed CI document."""
    commands: list[str] = []
    if isinstance(document, dict):
        for key, value in document.items():
            if key in ("run", "script", "commands") and isinstance(value, str):
                commands.append(value)
            elif key in ("script", "commands") and isinstance(value, list):
                commands.extend(str(item) for item in value)
            else:
                commands.extend(_run_commands(value))
    elif isinstance(document, list):
        for item in document:
            commands.extend(_run_commands(item))
    return commands


def _trigger_branches(document: Any) -> list[str]:
    """Branch names a workflow triggers on, if it names any."""
    if not isinstance(document, dict):
        return []
    # PyYAML parses the bare key `on:` as the boolean True.
    triggers = document.get("on", document.get(True))
    branches: list[str] = []
    if isinstance(triggers, dict):
        for event in triggers.values():
            if isinstance(event, dict) and isinstance(event.get("branches"), list):
                branches.extend(str(name) for name in event["branches"])
    return branches


def check_ci_runs_tests(ctx: RepoContext) -> CheckResult:
    """VF-05: a CI job actually invokes the test runner.

    Separate from VF-04 on purpose. A pipeline that lints and builds but never
    tests goes green regardless of whether the code works, which is worse than
    no pipeline because it looks like coverage.
    """
    configs = ci_files(ctx)
    if not configs:
        return result(VF_05, CheckStatus.FAIL, "No CI configuration to inspect.")

    runner = declared_runner(ctx)
    runner_patterns = (
        {runner: p.TEST_RUNNERS[runner]} if runner and runner in p.TEST_RUNNERS else p.TEST_RUNNERS
    )

    branch_note = ""
    for path in configs:
        try:
            document = yaml.safe_load(ctx.read_text(path))
        except yaml.YAMLError as exc:
            first_line = str(exc).splitlines()[0][:120]
            return result(VF_05, CheckStatus.FAIL, f"{path} does not parse: {first_line}")

        branches = _trigger_branches(document)
        if branches and ctx.default_branch and ctx.default_branch not in branches:
            # Not scored -- surfaced. A workflow watching the wrong branch has
            # never run, and an empty run history reads exactly like a pass.
            branch_note = (
                f" Note: {path} triggers on {', '.join(branches)} but the default branch is "
                f"{ctx.default_branch}; it may never have run."
            )

        for command in _run_commands(document):
            for name, pattern in runner_patterns.items():
                if pattern.search(command):
                    return result(
                        VF_05,
                        CheckStatus.PASS,
                        f"{path} runs {name}.{branch_note}",
                        [evidence_for_path(path, "ci_test_step")],
                    )

    return result(
        VF_05,
        CheckStatus.FAIL,
        f"CI exists but no job invokes a test runner. A pipeline that never tests goes "
        f"green regardless of whether the code works.{branch_note}",
        [evidence_for_path(configs[0], "ci_without_tests")],
    )


def _pyproject_tools(ctx: RepoContext) -> set[str]:
    """The `[tool.*]` sections a pyproject declares.

    Read from the parsed structure. An earlier version regexed for the literal
    header `[tool.mypy]` against the *parsed dict*, where that text can never
    appear -- so this tool reported its own strictly-typed repo as untyped.
    """
    if not ctx.pyproject:
        return set()
    tools = ctx.pyproject.get("tool")
    return {str(name) for name in tools} if isinstance(tools, dict) else set()


def _package_json_keys(ctx: RepoContext) -> tuple[set[str], set[str]]:
    """(script names, dependency names) from package.json."""
    if not ctx.package_json:
        return set(), set()
    scripts = ctx.package_json.get("scripts")
    script_names = {str(name) for name in scripts} if isinstance(scripts, dict) else set()
    deps: set[str] = set()
    for field in ("dependencies", "devDependencies"):
        section = ctx.package_json.get(field)
        if isinstance(section, dict):
            deps.update(str(name) for name in section)
    return script_names, deps


def check_type_checking(ctx: RepoContext) -> CheckResult:
    """VF-06: strict TypeScript, or a Python type-checker configuration."""
    if ctx.has_javascript:
        for path in ctx.paths_named("tsconfig.json"):
            if p.TSCONFIG_STRICT.search(ctx.read_text(path)):
                return result(VF_06, CheckStatus.PASS, f"{path} sets strict.")

    for path in ctx.paths_named(*p.TYPECHECK_CONFIG_NAMES):
        if path.rsplit("/", 1)[-1] != "tsconfig.json":
            return result(VF_06, CheckStatus.PASS, f"Found {path}.")

    configured = _pyproject_tools(ctx) & {"mypy", "pyright", "ty", "pyrefly"}
    if configured:
        return result(VF_06, CheckStatus.PASS, f"pyproject configures {sorted(configured)[0]}.")

    scripts, deps = _package_json_keys(ctx)
    if "typecheck" in scripts or {"typescript", "tsc"} & deps:
        return result(VF_06, CheckStatus.PASS, "package.json declares type checking.")

    return result(VF_06, CheckStatus.FAIL, searched("mypy or pyright config", "tsconfig strict"))


def check_lint(ctx: RepoContext) -> CheckResult:
    """VF-07: a lint configuration exists."""
    found = ctx.paths_named(*p.LINT_CONFIG_NAMES)
    if found:
        return result(VF_07, CheckStatus.PASS, f"Found {found[0]}.")

    configured = _pyproject_tools(ctx) & {"ruff", "flake8", "pylint", "black"}
    if configured:
        return result(VF_07, CheckStatus.PASS, f"pyproject configures {sorted(configured)[0]}.")

    scripts, deps = _package_json_keys(ctx)
    if "lint" in scripts or {"eslint", "@biomejs/biome", "oxlint"} & deps:
        return result(VF_07, CheckStatus.PASS, "package.json declares linting.")

    return result(VF_07, CheckStatus.FAIL, searched("eslint, biome or ruff configuration"))


def check_commit_gate(ctx: RepoContext) -> CheckResult:
    """VF-08: something runs before a commit lands."""
    found = ctx.paths_named(*p.COMMIT_GATE_NAMES)
    if found:
        return result(VF_08, CheckStatus.PASS, f"Found {found[0]}.")
    if any(path.startswith(p.COMMIT_GATE_DIRS) for path in ctx.files):
        return result(VF_08, CheckStatus.PASS, "Found husky hooks.")

    if "pre-commit" in _pyproject_tools(ctx):
        return result(VF_08, CheckStatus.PASS, "pyproject configures pre-commit.")

    scripts, deps = _package_json_keys(ctx)
    # lint-staged and husky are configured at the TOP level of package.json,
    # not under scripts or dependencies.
    top_level = {str(key) for key in ctx.package_json} if ctx.package_json else set()
    if {"lint-staged", "husky"} & (scripts | deps | top_level):
        return result(VF_08, CheckStatus.PASS, "package.json declares a commit gate.")

    return result(VF_08, CheckStatus.FAIL, searched("pre-commit, husky or lint-staged"))


CHECKS = (
    check_test_suite,
    check_test_runner,
    check_test_density,
    check_ci_present,
    check_ci_runs_tests,
    check_type_checking,
    check_lint,
    check_commit_gate,
)


def run(ctx: RepoContext) -> Sequence[CheckResult]:
    """Run every Verifiability check, in spec order."""
    return [check(ctx) for check in CHECKS]


register(AXIS, run)
