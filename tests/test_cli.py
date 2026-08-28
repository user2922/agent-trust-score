"""Exit codes, error shape, and the walking skeleton running end to end."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from agent_trust import __version__, cache
from agent_trust.analyzers import registered_axes
from agent_trust.cli import EXIT_BELOW_GRADE, EXIT_ERROR, EXIT_OK, app
from agent_trust.config import get_settings
from agent_trust.models import AXIS_ORDER, load_report
from agent_trust.pipeline import audit

runner = CliRunner()


def registered_axes_values() -> list[str]:
    return [axis.value for axis in registered_axes()]


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)  # noqa: S603


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "sample"
    root.mkdir()
    _git(["init", "-q", "-b", "master"], root)
    _git(["config", "user.email", "t@example.com"], root)
    _git(["config", "user.name", "t"], root)
    (root / "README.md").write_text("# demo\n", encoding="utf-8")
    _git(["add", "-A"], root)
    _git(["commit", "-qm", "initial commit with a real subject line"], root)
    return root


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Never touch the developer's real cache directory during tests."""
    monkeypatch.setenv("AGENT_TRUST_CACHE_DIR", str(tmp_path / "cache"))
    get_settings.cache_clear()


# ── exit codes ──────────────────────────────────────────────────────────────


def test_version_matches_the_package() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == EXIT_OK
    assert result.stdout.strip() == __version__


def test_runs_end_to_end_and_scores_the_registered_axes(repo: Path, tmp_path: Path) -> None:
    result = runner.invoke(
        app, [str(repo), "--no-llm", "--out", str(tmp_path / "out"), "--format", "json"]
    )
    assert result.exit_code == EXIT_OK

    report = load_report((tmp_path / "out" / "report.json").read_text(encoding="utf-8"))
    assert len(report.axes) == 5

    scored = {axis.key.value for axis in report.axes if axis.score is not None}
    unscored = {axis.key.value for axis in report.axes if axis.score is None}
    # Grows as prompts 9-13 land; an axis with no analyzer stays N/A rather
    # than being scored zero.
    assert scored == set(registered_axes_values())
    assert scored | unscored == set(AXIS_ORDER)


def test_missing_repo_exits_one_with_no_traceback(tmp_path: Path) -> None:
    result = runner.invoke(app, [str(tmp_path / "nope"), "--no-llm"])
    assert result.exit_code == EXIT_ERROR
    assert "Traceback" not in result.output
    assert len(result.output.strip().splitlines()) <= 3


def test_unknown_axis_and_format_are_rejected(repo: Path) -> None:
    assert runner.invoke(app, [str(repo), "--axis", "nope"]).exit_code == EXIT_ERROR
    assert runner.invoke(app, [str(repo), "--format", "pdf"]).exit_code == EXIT_ERROR
    assert runner.invoke(app, [str(repo), "--min-grade", "Z"]).exit_code == EXIT_ERROR


def test_min_grade_gate(repo: Path, tmp_path: Path) -> None:
    out = ["--out", str(tmp_path / "out"), "--no-llm", "--quiet"]
    # The fixture repo is a bare README: it fails every Tool Surface check.
    assert runner.invoke(app, [str(repo), *out, "--min-grade", "A"]).exit_code == EXIT_BELOW_GRADE
    assert runner.invoke(app, [str(repo), *out, "--min-grade", "F"]).exit_code == EXIT_OK


def test_min_grade_is_not_satisfied_by_an_unmeasured_repo(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A gate must never read "could not measure" as "passed".
    monkeypatch.setattr("agent_trust.pipeline.REGISTRY", {})
    out = ["--out", str(tmp_path / "out"), "--no-llm", "--quiet", "--no-cache"]
    assert runner.invoke(app, [str(repo), *out, "--min-grade", "F"]).exit_code == EXIT_BELOW_GRADE


# ── output files ────────────────────────────────────────────────────────────


def test_writes_exactly_the_requested_formats(repo: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    result = runner.invoke(
        app, [str(repo), "--no-llm", "--out", str(out), "--format", "json", "--format", "md"]
    )
    assert result.exit_code == EXIT_OK
    assert sorted(p.name for p in out.iterdir()) == ["report.json", "report.md"]


def test_quiet_suppresses_the_summary_but_still_writes(repo: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    result = runner.invoke(app, [str(repo), "--no-llm", "--quiet", "--out", str(out)])
    assert result.exit_code == EXIT_OK
    assert (out / "report.md").is_file()
    assert "Agent Trust Score" not in result.stdout


def test_unmeasured_repo_does_not_claim_everything_passed(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("agent_trust.pipeline.REGISTRY", {})
    result = runner.invoke(
        app, [str(repo), "--no-llm", "--no-cache", "--out", str(tmp_path / "out")]
    )
    assert "Every check passed" not in result.stdout
    assert "nothing was verified" in result.stdout


# ── cache ───────────────────────────────────────────────────────────────────


def test_second_run_reuses_the_cache(repo: Path) -> None:
    first = audit(str(repo), use_llm=False)
    second = audit(str(repo), use_llm=False)
    assert first.generated_at == second.generated_at, "second run should be a cache hit"


def test_no_cache_forces_a_fresh_run(repo: Path) -> None:
    first = audit(str(repo), use_llm=False)
    fresh = audit(str(repo), use_llm=False, use_cache=False)
    assert fresh.generated_at != first.generated_at


def test_cache_write_is_atomic(repo: Path, tmp_path: Path) -> None:
    report = audit(str(repo), use_llm=False, use_cache=False)
    cache_dir = tmp_path / "atomic"
    path = cache.write(cache_dir, report)
    assert path is not None and path.is_file()
    assert list(cache_dir.glob("*.tmp")) == [], "a temp file survived the write"


def test_repo_without_commits_is_never_cached(tmp_path: Path) -> None:
    root = tmp_path / "empty"
    root.mkdir()
    _git(["init", "-q"], root)
    report = audit(str(root), use_llm=False, use_cache=False)
    assert report.repo.commit_sha is None
    assert cache.write(tmp_path / "cache", report) is None


def test_schema_mismatch_is_a_miss_not_a_crash(repo: Path, tmp_path: Path) -> None:
    report = audit(str(repo), use_llm=False, use_cache=False)
    cache_dir = tmp_path / "mismatch"
    path = cache.write(cache_dir, report)
    assert path is not None

    document = json.loads(path.read_text(encoding="utf-8"))
    document["schema_version"] = "0.9"
    path.write_text(json.dumps(document), encoding="utf-8")

    assert cache.read(cache_dir, report.repo.commit_sha) is None


def test_template_entry_is_a_miss_when_the_model_was_requested(repo: Path, tmp_path: Path) -> None:
    report = audit(str(repo), use_llm=False, use_cache=False)
    cache_dir = tmp_path / "want-llm"
    cache.write(cache_dir, report)
    sha = report.repo.commit_sha

    assert cache.read(cache_dir, sha, want_llm=False) is not None
    assert cache.read(cache_dir, sha, want_llm=True) is None
