"""Verifiability: gates that exist AND are wired up.

The centrepiece is VF-04 vs VF-05. A CI file that lints but never tests passes
one and fails the other, and that gap is the finding.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from agent_trust.acquire import read_facts
from agent_trust.analyzers.verifiability import (
    SPECS,
    check_ci_present,
    check_ci_runs_tests,
    check_commit_gate,
    check_lint,
    check_test_density,
    check_test_runner,
    check_test_suite,
    check_type_checking,
)
from agent_trust.inventory import RepoContext, build_context
from agent_trust.limits import Budget
from agent_trust.models import CheckStatus

LINT_ONLY_CI = """
name: CI
on:
  push:
    branches: [master]
jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: npm run lint
"""

CI_WITH_TESTS = (
    LINT_ONLY_CI
    + """
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pytest
"""
)

WRONG_BRANCH_CI = CI_WITH_TESTS.replace("branches: [master]", "branches: [main]")


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)  # noqa: S603


def make_repo(tmp_path: Path, files: dict[str, str]) -> RepoContext:
    root = tmp_path / "repo"
    root.mkdir(parents=True, exist_ok=True)
    if not (root / ".git").exists():
        _git(["init", "-q", "-b", "master"], root)
        _git(["config", "user.email", "t@example.com"], root)
        _git(["config", "user.name", "t"], root)
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    _git(["add", "-A", "-f"], root)
    _git(["commit", "-qm", "fixture repository for the verifiability tests"], root)
    return build_context(
        root=root,
        source=str(root),
        facts=read_facts(root),
        budget=Budget(max_files=20_000, max_bytes=209_715_200),
    )


PYPROJECT_WITH_PYTEST = '[project]\nname = "demo"\ndependencies = ["pytest"]\n'


# ── VF-01..VF-03 ────────────────────────────────────────────────────────────


def test_test_suite_detected_and_absent(tmp_path: Path) -> None:
    with_tests = make_repo(tmp_path / "a", {"tests/test_app.py": "def test_x():\n    pass\n"})
    without = make_repo(tmp_path / "b", {"app.py": "x = 1\n"})
    assert check_test_suite(with_tests).status is CheckStatus.PASS
    assert check_test_suite(without).status is CheckStatus.FAIL


def test_runner_read_from_the_manifest(tmp_path: Path) -> None:
    ctx = make_repo(tmp_path, {"pyproject.toml": PYPROJECT_WITH_PYTEST})
    outcome = check_test_runner(ctx)
    assert outcome.status is CheckStatus.PASS
    assert "pytest" in outcome.detail


def test_no_declared_runner_fails(tmp_path: Path) -> None:
    ctx = make_repo(tmp_path, {"app.py": "x = 1\n"})
    assert check_test_runner(ctx).status is CheckStatus.FAIL


def test_density_partial_reports_both_counts(tmp_path: Path) -> None:
    files = {f"src/mod{i}.py": "x = 1\n" for i in range(30)}
    files.update({f"tests/test_{i}.py": "def test_x():\n    pass\n" for i in range(3)})
    outcome = check_test_density(make_repo(tmp_path, files))
    assert outcome.status is CheckStatus.PARTIAL
    assert "3 test file(s) to 30 source file(s)" in outcome.detail


def test_density_pass_and_fail_boundaries(tmp_path: Path) -> None:
    dense = {f"src/mod{i}.py": "x = 1\n" for i in range(10)}
    dense.update({f"tests/test_{i}.py": "def test_x():\n    pass\n" for i in range(3)})
    assert check_test_density(make_repo(tmp_path / "d", dense)).status is CheckStatus.PASS

    thin = {f"src/mod{i}.py": "x = 1\n" for i in range(40)}
    thin["tests/test_one.py"] = "def test_x():\n    pass\n"
    assert check_test_density(make_repo(tmp_path / "t", thin)).status is CheckStatus.FAIL


def test_density_is_not_applicable_without_source(tmp_path: Path) -> None:
    ctx = make_repo(tmp_path, {"README.md": "# demo\n"})
    assert check_test_density(ctx).status is CheckStatus.NOT_APPLICABLE


# ── VF-04 vs VF-05 · the gap that matters ───────────────────────────────────


def test_lint_only_ci_passes_vf04_and_fails_vf05(tmp_path: Path) -> None:
    ctx = make_repo(
        tmp_path,
        {".github/workflows/ci.yml": LINT_ONLY_CI, "pyproject.toml": PYPROJECT_WITH_PYTEST},
    )
    assert check_ci_present(ctx).status is CheckStatus.PASS

    outcome = check_ci_runs_tests(ctx)
    assert outcome.status is CheckStatus.FAIL
    assert "never tests" in outcome.detail


def test_adding_a_test_step_flips_vf05(tmp_path: Path) -> None:
    ctx = make_repo(
        tmp_path,
        {".github/workflows/ci.yml": CI_WITH_TESTS, "pyproject.toml": PYPROJECT_WITH_PYTEST},
    )
    outcome = check_ci_runs_tests(ctx)
    assert outcome.status is CheckStatus.PASS
    assert "runs pytest" in outcome.detail


def test_wrong_trigger_branch_is_surfaced_as_a_note(tmp_path: Path) -> None:
    # Not scored -- reported. A workflow watching the wrong branch has never run,
    # and an empty run history reads exactly like a passing one.
    ctx = make_repo(
        tmp_path,
        {".github/workflows/ci.yml": WRONG_BRANCH_CI, "pyproject.toml": PYPROJECT_WITH_PYTEST},
    )
    outcome = check_ci_runs_tests(ctx)
    assert outcome.status is CheckStatus.PASS
    assert "may never have run" in outcome.detail
    assert "main" in outcome.detail and "master" in outcome.detail


def test_matching_trigger_branch_adds_no_note(tmp_path: Path) -> None:
    ctx = make_repo(
        tmp_path,
        {".github/workflows/ci.yml": CI_WITH_TESTS, "pyproject.toml": PYPROJECT_WITH_PYTEST},
    )
    assert "may never have run" not in check_ci_runs_tests(ctx).detail


def test_malformed_ci_fails_with_the_parse_error_and_does_not_raise(tmp_path: Path) -> None:
    ctx = make_repo(tmp_path, {".github/workflows/ci.yml": "jobs:\n  - [unclosed\n"})
    outcome = check_ci_runs_tests(ctx)
    assert outcome.status is CheckStatus.FAIL
    assert "does not parse" in outcome.detail


def test_no_ci_fails_both(tmp_path: Path) -> None:
    ctx = make_repo(tmp_path, {"app.py": "x = 1\n"})
    assert check_ci_present(ctx).status is CheckStatus.FAIL
    assert check_ci_runs_tests(ctx).status is CheckStatus.FAIL


def test_gitlab_ci_is_recognised(tmp_path: Path) -> None:
    ctx = make_repo(
        tmp_path,
        {
            ".gitlab-ci.yml": "test:\n  script:\n    - pytest\n",
            "pyproject.toml": PYPROJECT_WITH_PYTEST,
        },
    )
    assert check_ci_present(ctx).status is CheckStatus.PASS
    assert check_ci_runs_tests(ctx).status is CheckStatus.PASS


# ── VF-06..VF-08 · read from structure, not from a repr ─────────────────────


def test_mypy_in_pyproject_is_found(tmp_path: Path) -> None:
    # Regression guard: an earlier version regexed the literal header
    # "[tool.mypy]" against the PARSED dict, so a strictly-typed repo read as
    # untyped. Detection must walk the structure.
    ctx = make_repo(
        tmp_path, {"pyproject.toml": '[project]\nname = "d"\n\n[tool.mypy]\nstrict = true\n'}
    )
    outcome = check_type_checking(ctx)
    assert outcome.status is CheckStatus.PASS
    assert "mypy" in outcome.detail


def test_tsconfig_without_strict_fails_then_passes(tmp_path: Path) -> None:
    loose = make_repo(tmp_path / "l", {"tsconfig.json": "{}", "a.ts": "const x = 1\n"})
    assert check_type_checking(loose).status is CheckStatus.FAIL

    strict = make_repo(
        tmp_path / "s",
        {"tsconfig.json": '{"compilerOptions":{"strict":true}}', "a.ts": "const x=1\n"},
    )
    assert check_type_checking(strict).status is CheckStatus.PASS


def test_ruff_in_pyproject_is_found(tmp_path: Path) -> None:
    ctx = make_repo(
        tmp_path, {"pyproject.toml": '[project]\nname = "d"\n\n[tool.ruff]\nline-length = 100\n'}
    )
    assert check_lint(ctx).status is CheckStatus.PASS


def test_eslint_dependency_is_found(tmp_path: Path) -> None:
    ctx = make_repo(tmp_path, {"package.json": '{"devDependencies": {"eslint": "9"}}'})
    assert check_lint(ctx).status is CheckStatus.PASS


def test_no_lint_config_fails(tmp_path: Path) -> None:
    assert check_lint(make_repo(tmp_path, {"a.py": "x = 1\n"})).status is CheckStatus.FAIL


def test_commit_gate_detected_three_ways(tmp_path: Path) -> None:
    precommit = make_repo(tmp_path / "p", {".pre-commit-config.yaml": "repos: []\n"})
    husky = make_repo(tmp_path / "h", {".husky/pre-commit": "npm test\n"})
    staged = make_repo(tmp_path / "s", {"package.json": '{"lint-staged": {"*.js": "eslint"}}'})
    for ctx in (precommit, husky, staged):
        assert check_commit_gate(ctx).status is CheckStatus.PASS


def test_no_commit_gate_fails(tmp_path: Path) -> None:
    assert check_commit_gate(make_repo(tmp_path, {"a.py": "x = 1\n"})).status is CheckStatus.FAIL


# ── the axis ────────────────────────────────────────────────────────────────


def test_weights_total_one_hundred_across_eight_checks() -> None:
    assert sum(spec.weight for spec in SPECS) == 100
    assert len(SPECS) == 8


def test_repo_with_no_tests_scores_at_most_thirty_five(tmp_path: Path) -> None:
    from agent_trust.analyzers.verifiability import AXIS, run
    from agent_trust.scoring import score_axis

    ctx = make_repo(
        tmp_path,
        {
            "app.py": "x = 1\n",
            ".github/workflows/ci.yml": LINT_ONLY_CI,
            "pyproject.toml": (
                '[project]\nname = "d"\n\n[tool.mypy]\nstrict = true\n\n[tool.ruff]\n'
            ),
            ".pre-commit-config.yaml": "repos: []\n",
        },
    )
    axis = score_axis(AXIS, "Verifiability", run(ctx))
    assert axis.score is not None and axis.score <= 35
