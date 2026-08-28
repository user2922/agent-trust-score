"""Acquisition is a security boundary: these tests assert what it refuses."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import pytest

from agent_trust import acquire as acquire_module
from agent_trust.acquire import (
    _NULL_HOOKS,
    GitFacts,
    acquire,
    clone,
    is_url,
    read_facts,
    resolve_local,
    validate_url,
)
from agent_trust.errors import (
    AcquireError,
    HostNotAllowed,
    NotAGitRepo,
    TimeoutExceeded,
)
from agent_trust.limits import Budget, Deadline
from agent_trust.redact import MAX_SNIPPET, snippet


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)  # noqa: S603


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "sample"
    root.mkdir()
    _git(["init", "-q", "-b", "master"], root)
    _git(["config", "user.email", "t@example.com"], root)
    _git(["config", "user.name", "t"], root)
    (root / "README.md").write_text("hello\n", encoding="utf-8")
    _git(["add", "-A"], root)
    _git(["commit", "-qm", "initial commit with a real subject"], root)
    return root


# ── URL validation ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "url", ["https://github.com/a/b", "https://gitlab.com/a/b", "git@github.com:a/b.git"]
)
def test_allowlisted_hosts_pass(url: str) -> None:
    assert validate_url(url)


def test_unlisted_host_is_refused_then_permitted_by_flag() -> None:
    with pytest.raises(HostNotAllowed):
        validate_url("https://evil.example.com/a/b")
    assert validate_url("https://evil.example.com/a/b", allow_any_host=True) == "evil.example.com"


def test_file_scheme_is_refused_even_with_allow_any_host() -> None:
    with pytest.raises(HostNotAllowed):
        validate_url("file:///etc", allow_any_host=True)


@pytest.mark.parametrize("url", ["ftp://github.com/a/b", "javascript:alert(1)"])
def test_unsupported_schemes_are_refused(url: str) -> None:
    with pytest.raises(HostNotAllowed):
        validate_url(url)


def test_is_url_distinguishes_paths_from_remotes() -> None:
    assert is_url("https://github.com/a/b")
    assert is_url("git@github.com:a/b")
    assert not is_url("./local")
    assert not is_url("C:/Users/x/repo")


# ── local paths ─────────────────────────────────────────────────────────────


def test_missing_git_directory_is_refused(tmp_path: Path) -> None:
    (tmp_path / "plain").mkdir()
    with pytest.raises(NotAGitRepo):
        resolve_local(str(tmp_path / "plain"))


def test_nonexistent_path_is_refused(tmp_path: Path) -> None:
    with pytest.raises(NotAGitRepo):
        resolve_local(str(tmp_path / "nope"))


def test_local_repo_resolves(repo: Path) -> None:
    assert resolve_local(str(repo)) == repo.resolve()


def test_local_source_is_not_deleted(repo: Path) -> None:
    with acquire(str(repo)) as path:
        assert path.exists()
    assert repo.exists()


# ── git facts ───────────────────────────────────────────────────────────────


def test_reads_sha_branch_and_subjects(repo: Path) -> None:
    facts = read_facts(repo)
    assert facts.commit_sha and len(facts.commit_sha) == 40
    assert facts.default_branch == "master"
    assert facts.commit_subjects == ("initial commit with a real subject",)


def test_empty_repo_yields_no_sha_rather_than_raising(tmp_path: Path) -> None:
    root = tmp_path / "empty"
    root.mkdir()
    _git(["init", "-q"], root)
    facts = read_facts(root)
    assert facts == GitFacts(commit_sha=None, default_branch=None, commit_subjects=())


# ── no execution ────────────────────────────────────────────────────────────


def test_hooks_are_disabled_by_configuration() -> None:
    assert _NULL_HOOKS in {"/dev/null", "NUL"}


def test_temp_directory_is_removed_when_the_clone_fails(tmp_path: Path) -> None:
    before = set(Path(tempfile.gettempdir()).glob("agent-trust-*"))
    with (
        pytest.raises(AcquireError),
        acquire("https://github.com/this-org/does-not-exist-xyz", timeout=20),
    ):
        pass  # pragma: no cover - the clone must fail before the body runs
    after = set(Path(tempfile.gettempdir()).glob("agent-trust-*"))
    assert after == before, "a temp checkout survived a failed clone"


def test_clone_command_is_shallow_blobless_and_hookless(
    tmp_path: Path, repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[list[str]] = []
    real = acquire_module.run_git

    def spy(args: list[str], cwd: Path, timeout: int = 30) -> object:
        seen.append(args)
        return real(args, cwd, timeout)

    monkeypatch.setattr(acquire_module, "run_git", spy)
    dest = tmp_path / "dest"
    dest.mkdir()
    clone(repo.as_uri(), dest, timeout=30)

    flat = " ".join(seen[0])
    assert "--depth 1" in flat
    assert "--filter=blob:none" in flat
    assert f"core.hooksPath={_NULL_HOOKS}" in flat


def test_clone_of_a_repo_with_a_hook_does_not_run_it(tmp_path: Path, repo: Path) -> None:
    marker = tmp_path / "pwned"
    hooks = repo / ".git" / "hooks"
    hooks.mkdir(exist_ok=True)
    hook = hooks / "post-checkout"
    hook.write_text(f"#!/bin/sh\ntouch '{marker}'\n", encoding="utf-8")
    hook.chmod(0o755)

    dest = tmp_path / "dest"
    dest.mkdir()
    clone(repo.as_uri(), dest, timeout=30)
    assert not marker.exists(), "a repository hook executed during clone"


# ── budgets and deadlines ───────────────────────────────────────────────────


def test_budget_truncates_on_file_ceiling() -> None:
    budget = Budget(max_files=2, max_bytes=10_000)
    assert budget.accept(10) and budget.accept(10)
    assert not budget.accept(10)
    assert budget.truncated
    assert budget.skipped == {"budget_files": 1}


def test_budget_truncates_on_byte_ceiling() -> None:
    budget = Budget(max_files=100, max_bytes=50)
    assert budget.accept(40)
    assert not budget.accept(20)
    assert budget.truncated
    assert budget.skipped == {"budget_bytes": 1}


def test_expired_deadline_names_the_stage() -> None:
    deadline = Deadline(seconds=-1)
    with pytest.raises(TimeoutExceeded) as excinfo:
        deadline.check("inventory")
    assert "inventory" in str(excinfo.value)


def test_live_deadline_does_not_raise() -> None:
    Deadline(seconds=60).check("inventory")


# ── redaction of evidence ───────────────────────────────────────────────────


def test_snippet_redacts_the_match_and_bounds_length() -> None:
    line = 'AWS = "' + "A" * 400 + '"'
    out = snippet(line, 7, 407)
    assert len(out) <= MAX_SNIPPET
    assert "A" * 20 not in out


def test_snippet_strips_escapes_from_surrounding_text() -> None:
    line = "\x1b[31mkey = SECRETVALUE123456\x1b[0m"
    out = snippet(line, 12, len(line) - 4)
    assert "\x1b" not in out
