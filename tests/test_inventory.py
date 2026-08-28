"""The inventory decides what every analyzer can see, so its skips are the test."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from agent_trust.acquire import read_facts
from agent_trust.inventory import MAX_FILE_BYTES, RepoContext, build_context
from agent_trust.limits import Budget


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)  # noqa: S603


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "sample"
    root.mkdir()
    _git(["init", "-q", "-b", "master"], root)
    _git(["config", "user.email", "t@example.com"], root)
    _git(["config", "user.name", "t"], root)
    return root


def commit(root: Path, message: str = "add files for the inventory tests") -> None:
    _git(["add", "-A"], root)
    _git(["commit", "-qm", message], root)


def write(root: Path, relative: str, content: str = "x = 1\n") -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def context_for(
    root: Path, *, max_files: int = 20_000, max_bytes: int = 209_715_200
) -> RepoContext:
    return build_context(
        root=root,
        source=str(root),
        facts=read_facts(root),
        budget=Budget(max_files=max_files, max_bytes=max_bytes),
    )


# ── what is out of scope ────────────────────────────────────────────────────


def test_vendored_directories_are_excluded(repo: Path) -> None:
    write(repo, "src/app.py")
    for index in range(20):
        write(repo, f"node_modules/pkg/file{index}.js")
    commit(repo)

    ctx = context_for(repo)
    assert "src/app.py" in ctx.files
    assert not any(path.startswith("node_modules/") for path in ctx.files)
    assert ctx.skipped["vendored"] == 20


def test_oversized_file_is_skipped(repo: Path) -> None:
    write(repo, "small.py")
    write(repo, "huge.py", "#" + "a" * (MAX_FILE_BYTES + 10))
    commit(repo)

    ctx = context_for(repo)
    assert "huge.py" not in ctx.files
    assert ctx.skipped["too_large"] == 1


def test_binary_file_is_skipped(repo: Path) -> None:
    write(repo, "app.py")
    (repo / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")
    commit(repo)

    ctx = context_for(repo)
    assert "logo.png" not in ctx.files
    assert ctx.skipped["binary"] == 1


def test_lockfiles_and_minified_files_are_skipped(repo: Path) -> None:
    write(repo, "app.py")
    write(repo, "package-lock.json", "{}\n")
    write(repo, "bundle.min.js", "var a=1\n")
    commit(repo)

    ctx = context_for(repo)
    assert ctx.files == ("app.py",)
    assert ctx.skipped["lockfile"] == 1
    assert ctx.skipped["minified"] == 1


def test_untracked_file_is_invisible(repo: Path) -> None:
    write(repo, "tracked.py")
    commit(repo)
    write(repo, "untracked.py")

    ctx = context_for(repo)
    assert ctx.files == ("tracked.py",)


# ── budgets ─────────────────────────────────────────────────────────────────


def test_file_budget_sets_truncated(repo: Path) -> None:
    for index in range(50):
        write(repo, f"mod{index:02d}.py")
    commit(repo)

    ctx = context_for(repo, max_files=5)
    assert ctx.truncated
    assert ctx.analyzed_file_count == 5
    assert ctx.file_count == 50
    assert ctx.skipped["budget_files"] == 45


def test_byte_budget_sets_truncated(repo: Path) -> None:
    for index in range(5):
        write(repo, f"mod{index}.py", "x" * 500)
    commit(repo)

    ctx = context_for(repo, max_bytes=900)
    assert ctx.truncated
    assert ctx.analyzed_file_count == 1


def test_untruncated_repo_reports_no_truncation(repo: Path) -> None:
    write(repo, "app.py")
    commit(repo)
    assert context_for(repo).truncated is False


# ── determinism ─────────────────────────────────────────────────────────────


def test_two_runs_return_equal_file_lists(repo: Path) -> None:
    for name in ("z.py", "a.py", "m/b.py"):
        write(repo, name)
    commit(repo)

    first, second = context_for(repo), context_for(repo)
    assert first.files == second.files
    assert first.files == tuple(sorted(first.files))
    assert list(first.languages) == sorted(first.languages)


# ── reading ─────────────────────────────────────────────────────────────────


def test_read_is_memoized(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write(repo, "app.py", "line one\nline two\n")
    commit(repo)
    ctx = context_for(repo)

    reads = {"count": 0}
    original = Path.read_text

    def counting(self: Path, *args: object, **kwargs: object) -> str:
        if self.name == "app.py":
            reads["count"] += 1
        return original(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "read_text", counting)
    assert ctx.read_lines("app.py") == ("line one", "line two")
    ctx.read_lines("app.py")
    ctx.read_lines("app.py")
    assert reads["count"] == 1


def test_line_numbers_are_one_based(repo: Path) -> None:
    write(repo, "app.py", "first\nsecond\nthird\n")
    commit(repo)
    ctx = context_for(repo)
    assert ctx.read_lines("app.py")[2 - 1] == "second"


def test_unreadable_path_returns_empty_rather_than_raising(repo: Path) -> None:
    write(repo, "app.py")
    commit(repo)
    assert context_for(repo).read_lines("does/not/exist.py") == ()


# ── languages and manifests ─────────────────────────────────────────────────


def test_language_detection_and_predicates(repo: Path) -> None:
    write(repo, "a.py")
    write(repo, "b.ts", "const a = 1\n")
    commit(repo)

    ctx = context_for(repo)
    assert ctx.languages["Python"] == 1
    assert ctx.languages["TypeScript"] == 1
    assert ctx.has_python and ctx.has_javascript


def test_go_only_repo_is_neither_python_nor_javascript(repo: Path) -> None:
    write(repo, "main.go", "package main\n")
    commit(repo)

    ctx = context_for(repo)
    assert not ctx.has_python
    assert not ctx.has_javascript


def test_malformed_manifest_returns_none_without_raising(repo: Path) -> None:
    write(repo, "package.json", "{ this is not json")
    write(repo, "pyproject.toml", "[project\nbroken")
    commit(repo)

    ctx = context_for(repo)
    assert ctx.package_json is None
    assert ctx.pyproject is None


def test_valid_manifests_are_parsed(repo: Path) -> None:
    write(repo, "package.json", '{"name": "demo", "bin": {"demo": "cli.js"}}')
    write(repo, "pyproject.toml", '[project]\nname = "demo"\n')
    commit(repo)

    ctx = context_for(repo)
    assert ctx.package_json is not None and ctx.package_json["name"] == "demo"
    assert ctx.pyproject is not None and ctx.pyproject["project"]["name"] == "demo"


def test_empty_repo_yields_an_empty_inventory(repo: Path) -> None:
    ctx = context_for(repo)
    assert ctx.files == ()
    assert ctx.commit_sha is None
    assert ctx.truncated is False


# ── helpers analyzers rely on ───────────────────────────────────────────────


def test_path_lookup_helpers(repo: Path) -> None:
    write(repo, "src/app.py")
    write(repo, "README.md", "# hi\n")
    commit(repo)

    ctx = context_for(repo)
    assert ctx.paths_with_suffix(".py") == ("src/app.py",)
    assert ctx.paths_named("readme.md") == ("README.md",)
    assert ctx.exists("src/app.py")
    assert not ctx.exists("nope.py")
