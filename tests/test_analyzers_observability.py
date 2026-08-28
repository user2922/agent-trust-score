"""Observability: installed is not the same as wired up.

OB-05 is tested against real git history built by the fixture, not a mocked
list, because that is what the analyzer actually reads.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from agent_trust.acquire import read_facts
from agent_trust.analyzers.observability import (
    MIN_COMMITS_TO_JUDGE,
    SPECS,
    check_audit_trail,
    check_changelog,
    check_commit_hygiene,
    check_error_reporting,
    check_liveness,
    check_logging_over_printing,
    check_structured_logging,
    count_logging_calls,
)
from agent_trust.inventory import RepoContext, build_context
from agent_trust.limits import Budget
from agent_trust.models import CheckStatus


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)  # noqa: S603


def _init(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    if not (root / ".git").exists():
        _git(["init", "-q", "-b", "master"], root)
        _git(["config", "user.email", "t@example.com"], root)
        _git(["config", "user.name", "t"], root)


def _context(root: Path) -> RepoContext:
    return build_context(
        root=root,
        source=str(root),
        facts=read_facts(root),
        budget=Budget(max_files=20_000, max_bytes=209_715_200),
    )


def make_repo(tmp_path: Path, files: dict[str, str]) -> RepoContext:
    root = tmp_path / "repo"
    _init(root)
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    _git(["add", "-A", "-f"], root)
    _git(["commit", "-qm", "fixture repository for the observability tests"], root)
    return _context(root)


def make_history(tmp_path: Path, subjects: list[str]) -> RepoContext:
    """A repo whose commit history is exactly ``subjects``, oldest first."""
    root = tmp_path / "history"
    _init(root)
    for index, subject in enumerate(subjects):
        (root / f"file{index}.txt").write_text(f"{index}\n", encoding="utf-8")
        _git(["add", "-A"], root)
        _git(["commit", "-qm", subject], root)
    return _context(root)


# ── OB-01 · structured logging ──────────────────────────────────────────────


def test_logging_dependency_and_configuration_both_pass(tmp_path: Path) -> None:
    dep = make_repo(tmp_path / "d", {"pyproject.toml": '[project]\ndependencies = ["structlog"]\n'})
    conf = make_repo(tmp_path / "c", {"log.py": "import logging\n\nlogging.getLogger(__name__)\n"})
    assert check_structured_logging(dep).status is CheckStatus.PASS
    assert check_structured_logging(conf).status is CheckStatus.PASS


def test_no_logging_fails(tmp_path: Path) -> None:
    ctx = make_repo(tmp_path, {"app.py": "print('hello')\n"})
    assert check_structured_logging(ctx).status is CheckStatus.FAIL


# ── OB-02 · logging over printing ───────────────────────────────────────────


def test_console_log_heavy_repo_fails_and_reports_both_counts(tmp_path: Path) -> None:
    body = "\n".join(f"console.log('step {i}')" for i in range(40))
    body += "\nlogger.info('a')\nlogger.info('b')\n"
    ctx = make_repo(tmp_path, {"src/app.js": body})
    outcome = check_logging_over_printing(ctx)
    assert outcome.status is CheckStatus.FAIL
    assert "2 logger call(s) to 40 print call(s)" in outcome.detail


def test_prints_in_tests_and_scripts_are_not_counted(tmp_path: Path) -> None:
    ctx = make_repo(
        tmp_path,
        {
            "src/app.py": "logger.info('x')\n",
            "tests/test_app.py": "\n".join("print('t')" for _ in range(30)) + "\n",
            "scripts/seed.py": "\n".join("print('s')" for _ in range(30)) + "\n",
        },
    )
    loggers, prints = count_logging_calls(ctx)
    assert (loggers, prints) == (1, 0)
    assert check_logging_over_printing(ctx).status is CheckStatus.PASS


def test_silent_repo_is_not_applicable(tmp_path: Path) -> None:
    ctx = make_repo(tmp_path, {"src/app.py": "def add(a, b):\n    return a + b\n"})
    assert check_logging_over_printing(ctx).status is CheckStatus.NOT_APPLICABLE


# ── OB-03 · installed vs initialised ────────────────────────────────────────


def test_sentry_installed_but_never_initialised_is_partial(tmp_path: Path) -> None:
    ctx = make_repo(tmp_path, {"pyproject.toml": '[project]\ndependencies = ["sentry-sdk"]\n'})
    outcome = check_error_reporting(ctx)
    assert outcome.status is CheckStatus.PARTIAL
    assert "reports nothing" in outcome.detail


def test_adding_the_init_call_flips_it_to_pass(tmp_path: Path) -> None:
    ctx = make_repo(
        tmp_path,
        {
            "pyproject.toml": '[project]\ndependencies = ["sentry-sdk"]\n',
            "app.py": "import sentry_sdk\n\nsentry_sdk.init(dsn=DSN)\n",
        },
    )
    assert check_error_reporting(ctx).status is CheckStatus.PASS


def test_no_error_reporting_fails(tmp_path: Path) -> None:
    assert (
        check_error_reporting(make_repo(tmp_path, {"a.py": "x = 1\n"})).status is CheckStatus.FAIL
    )


# ── OB-04 · audit trail ─────────────────────────────────────────────────────


def test_named_audit_table_passes(tmp_path: Path) -> None:
    ctx = make_repo(tmp_path, {"schema.sql": "CREATE TABLE audit_log (id uuid);\n"})
    assert check_audit_trail(ctx).status is CheckStatus.PASS


def test_actor_action_timestamp_without_the_name_is_partial(tmp_path: Path) -> None:
    ctx = make_repo(
        tmp_path,
        {"model.py": "class Entry:\n    user_id: str\n    action: str\n    created_at: str\n"},
    )
    assert check_audit_trail(ctx).status is CheckStatus.PARTIAL


def test_no_audit_trail_fails(tmp_path: Path) -> None:
    assert check_audit_trail(make_repo(tmp_path, {"a.py": "x = 1\n"})).status is CheckStatus.FAIL


# ── OB-05 · commit hygiene, against real history ────────────────────────────


def test_all_wip_history_fails_and_shows_the_percentage(tmp_path: Path) -> None:
    ctx = make_history(tmp_path, ["wip"] * 12)
    outcome = check_commit_hygiene(ctx)
    assert outcome.status is CheckStatus.FAIL
    assert "0%" in outcome.detail


def test_informative_history_passes(tmp_path: Path) -> None:
    ctx = make_history(
        tmp_path, [f"add the {name} module and its tests" for name in "abcdefghijkl"]
    )
    outcome = check_commit_hygiene(ctx)
    assert outcome.status is CheckStatus.PASS
    assert "100%" in outcome.detail


def test_mixed_history_is_partial(tmp_path: Path) -> None:
    subjects = ["fix the parser for nested groups"] * 5 + ["wip"] * 7
    outcome = check_commit_hygiene(make_history(tmp_path, subjects))
    assert outcome.status is CheckStatus.PARTIAL


def test_short_history_is_not_applicable(tmp_path: Path) -> None:
    ctx = make_history(tmp_path, ["wip"] * (MIN_COMMITS_TO_JUDGE - 4))
    outcome = check_commit_hygiene(ctx)
    assert outcome.status is CheckStatus.NOT_APPLICABLE
    assert "too little history" in outcome.detail


def test_a_short_history_drops_fifteen_points_from_the_denominator(tmp_path: Path) -> None:
    from agent_trust.analyzers.observability import AXIS, run
    from agent_trust.scoring import score_axis

    ctx = make_history(tmp_path, ["wip"] * 3)
    checks = run(ctx)
    applicable = [c for c in checks if c.status is not CheckStatus.NOT_APPLICABLE]
    assert sum(c.weight for c in applicable) <= 100 - 15
    assert score_axis(AXIS, "Observability", checks).score is not None


# ── OB-06 / OB-07 ───────────────────────────────────────────────────────────


def test_changelog_detected_and_absent(tmp_path: Path) -> None:
    present = make_repo(tmp_path / "c", {"CHANGELOG.md": "# 1.0\n"})
    absent = make_repo(tmp_path / "a", {"a.py": "x = 1\n"})
    assert check_changelog(present).status is CheckStatus.PASS
    assert check_changelog(absent).status is CheckStatus.FAIL


def test_health_route_and_version_flag_both_pass(tmp_path: Path) -> None:
    route = make_repo(
        tmp_path / "r", {"api.py": '@app.get("/health")\ndef health():\n    return {}\n'}
    )
    version = make_repo(tmp_path / "v", {"cli.py": 'parser.add_argument("--version")\n'})
    assert check_liveness(route).status is CheckStatus.PASS
    assert check_liveness(version).status is CheckStatus.PASS


def test_no_liveness_surface_fails(tmp_path: Path) -> None:
    assert check_liveness(make_repo(tmp_path, {"a.py": "x = 1\n"})).status is CheckStatus.FAIL


# ── the axis, and the registry ──────────────────────────────────────────────


def test_weights_total_one_hundred_across_seven_checks() -> None:
    assert sum(spec.weight for spec in SPECS) == 100
    assert len(SPECS) == 7


def test_all_five_axes_are_registered() -> None:
    from agent_trust.analyzers import registered_axes
    from agent_trust.models import AXIS_ORDER

    assert [axis.value for axis in registered_axes()] == list(AXIS_ORDER)


def test_a_full_audit_scores_every_axis(tmp_path: Path) -> None:
    from agent_trust.pipeline import audit

    root = tmp_path / "repo"
    _init(root)
    (root / "app.py").write_text("x = 1\n", encoding="utf-8")
    _git(["add", "-A"], root)
    _git(["commit", "-qm", "add the application module"], root)

    report = audit(str(root), use_llm=False, use_cache=False)
    assert all(axis.score is not None for axis in report.axes)
    assert report.overall.score is not None
