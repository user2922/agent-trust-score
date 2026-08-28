"""The file inventory every analyzer reads.

Replaces the types-and-validation phase: ``RepoContext`` is the structure later
prompts import. An analyzer receives this object and nothing else -- no config,
no network, no environment, no clock -- so an analyzer physically cannot reach
outside the repository it was handed.

Discovery is ``git ls-files`` only, never a filesystem walk. Untracked build
output and anything ignored is therefore out of scope by construction rather
than by a skip rule that might miss something.

Every list this module produces is sorted. Unsorted output is the most common
source of run-to-run drift, and determinism is non-negotiable rule D.
"""

from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent_trust.acquire import GitFacts, run_git
from agent_trust.limits import Budget
from agent_trust.logging import get_logger

logger = get_logger("inventory")

# Directories whose contents are somebody else's code or build output.
SKIP_DIRS = frozenset(
    {
        ".git",
        "node_modules",
        ".venv",
        "venv",
        "dist",
        "build",
        "vendor",
        "target",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "site-packages",
    }
)

LOCKFILES = frozenset(
    {
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "uv.lock",
        "poetry.lock",
        "Pipfile.lock",
        "Cargo.lock",
        "composer.lock",
        "Gemfile.lock",
        "go.sum",
    }
)

MAX_FILE_BYTES = 1_048_576  # 1 MB
BINARY_SNIFF_BYTES = 8000

LANGUAGE_BY_SUFFIX: dict[str, str] = {
    ".py": "Python",
    ".pyi": "Python",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".go": "Go",
    ".rs": "Rust",
    ".rb": "Ruby",
    ".java": "Java",
    ".kt": "Kotlin",
    ".cs": "C#",
    ".php": "PHP",
    ".swift": "Swift",
    ".c": "C",
    ".h": "C",
    ".cpp": "C++",
    ".sh": "Shell",
    ".sql": "SQL",
    ".md": "Markdown",
    ".yml": "YAML",
    ".yaml": "YAML",
    ".json": "JSON",
    ".toml": "TOML",
}

_PYTHON = "Python"
_JS_LIKE = frozenset({"JavaScript", "TypeScript"})


@dataclass(frozen=True)
class RepoContext:
    """Everything an analyzer is allowed to see."""

    root: Path
    source: str
    commit_sha: str | None
    default_branch: str | None
    commit_subjects: tuple[str, ...]
    files: tuple[str, ...]
    file_sizes: dict[str, int]
    languages: dict[str, int]
    bytes_scanned: int
    file_count: int
    truncated: bool
    skipped: dict[str, int]
    pyproject: dict[str, Any] | None = None
    package_json: dict[str, Any] | None = None
    _lines: dict[str, tuple[str, ...]] = field(default_factory=dict, compare=False, repr=False)

    # ── language predicates ────────────────────────────────────────────────

    @property
    def has_python(self) -> bool:
        return self.languages.get(_PYTHON, 0) > 0

    @property
    def has_javascript(self) -> bool:
        return any(self.languages.get(name, 0) > 0 for name in _JS_LIKE)

    @property
    def analyzed_file_count(self) -> int:
        return len(self.files)

    # ── reading ────────────────────────────────────────────────────────────

    def exists(self, relative: str) -> bool:
        """True when a repo-relative path was inventoried."""
        return relative in self.file_sizes

    def read_lines(self, relative: str) -> tuple[str, ...]:
        """Return a file's lines, decoded leniently and memoized for the run.

        Ten analyzers reading README.md read the disk once. Line numbers used in
        evidence are 1-based, so ``read_lines(p)[n - 1]`` is line ``n``.
        """
        cached = self._lines.get(relative)
        if cached is not None:
            return cached
        try:
            text = (self.root / relative).read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        lines = tuple(text.splitlines())
        self._lines[relative] = lines
        return lines

    def read_text(self, relative: str) -> str:
        return "\n".join(self.read_lines(relative))

    def paths_with_suffix(self, *suffixes: str) -> tuple[str, ...]:
        lowered = tuple(s.lower() for s in suffixes)
        return tuple(p for p in self.files if p.lower().endswith(lowered))

    def paths_named(self, *names: str) -> tuple[str, ...]:
        wanted = {n.lower() for n in names}
        return tuple(p for p in self.files if p.rsplit("/", 1)[-1].lower() in wanted)


def _is_binary(path: Path) -> bool:
    """A null byte in the first 8000 bytes means we should not read it as text."""
    try:
        with path.open("rb") as handle:
            return b"\x00" in handle.read(BINARY_SNIFF_BYTES)
    except OSError:
        return True


def _skip_reason(relative: str, size: int) -> str | None:
    """Why this file is out of scope, or None if it should be analyzed."""
    parts = relative.split("/")
    if any(part in SKIP_DIRS for part in parts[:-1]):
        return "vendored"
    name = parts[-1]
    if name in LOCKFILES:
        return "lockfile"
    if ".min." in name:
        return "minified"
    if size > MAX_FILE_BYTES:
        return "too_large"
    return None


def _tracked_files(root: Path) -> list[str]:
    """Repo-relative paths of tracked files, sorted. Empty for an empty repo."""
    result = run_git(["ls-files", "-z"], cwd=root)
    if result.returncode != 0:
        return []
    return sorted(entry for entry in result.stdout.split("\0") if entry)


def _parse_json(path: Path) -> dict[str, Any] | None:
    """Parsed JSON, or None. A malformed manifest is a finding later, not a crash."""
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _parse_toml(path: Path) -> dict[str, Any] | None:
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError):
        return None


def build_context(root: Path, source: str, facts: GitFacts, budget: Budget) -> RepoContext:
    """Inventory ``root`` into the object analyzers consume.

    Exceeding a budget is not an error: it sets ``truncated`` and records the
    reason, so a partial audit is reported as partial rather than presented as
    a complete one.
    """
    tracked = _tracked_files(root)
    files: list[str] = []
    sizes: dict[str, int] = {}
    languages: dict[str, int] = {}

    for relative in tracked:
        absolute = root / relative
        try:
            size = absolute.stat().st_size
        except OSError:
            budget.skip("unreadable")
            continue

        reason = _skip_reason(relative, size)
        if reason:
            budget.skip(reason)
            continue
        if _is_binary(absolute):
            budget.skip("binary")
            continue
        if not budget.accept(size):
            continue

        files.append(relative)
        sizes[relative] = size
        language = LANGUAGE_BY_SUFFIX.get(Path(relative).suffix.lower())
        if language:
            languages[language] = languages.get(language, 0) + 1

    if budget.truncated:
        logger.info(
            "inventory truncated",
            extra={"analyzed": len(files), "tracked": len(tracked)},
        )

    return RepoContext(
        root=root,
        source=source,
        commit_sha=facts.commit_sha,
        default_branch=facts.default_branch,
        commit_subjects=facts.commit_subjects,
        files=tuple(sorted(files)),
        file_sizes=sizes,
        languages=dict(sorted(languages.items())),
        bytes_scanned=budget.bytes_used,
        file_count=len(tracked),
        truncated=budget.truncated,
        skipped=dict(sorted(budget.skipped.items())),
        pyproject=_parse_toml(root / "pyproject.toml")
        if (root / "pyproject.toml").is_file()
        else None,
        package_json=_parse_json(root / "package.json")
        if (root / "package.json").is_file()
        else None,
    )


__all__ = [
    "LANGUAGE_BY_SUFFIX",
    "LOCKFILES",
    "MAX_FILE_BYTES",
    "SKIP_DIRS",
    "RepoContext",
    "build_context",
]
