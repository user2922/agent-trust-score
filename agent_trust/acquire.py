"""Obtain a repository to audit -- without ever executing its code.

Standing rule X (CLAUDE.md). This tool audits untrusted third-party
repositories, so the acquisition step is a security boundary. What is forbidden,
explicitly:

* no dependency install (``npm install``, ``pip install``, ...)
* no build step, no test run, no script execution of any kind
* no git hooks -- every clone sets ``core.hooksPath`` to the null device, so a
  repository's ``post-checkout`` hook cannot run
* no import of anything under the audited path

Reading and parsing only. Every git invocation here is read-only, takes a fixed
argument list rather than a shell string, and is separated from user-supplied
values by ``--`` so a branch or path named ``--upload-pack=...`` cannot be read
as a flag.
"""

from __future__ import annotations

import os
import shutil
import subprocess  # noqa: S404 - read-only git, fixed argv, never shell=True
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from agent_trust.config import subprocess_env
from agent_trust.errors import AcquireError, HostNotAllowed, NotAGitRepo
from agent_trust.logging import get_logger

logger = get_logger("acquire")

ALLOWED_HOSTS = frozenset({"github.com", "gitlab.com", "bitbucket.org", "codeberg.org"})

# Hooks are disabled by pointing git at a directory that cannot contain any.
_NULL_HOOKS = "/dev/null" if os.name != "nt" else "NUL"

_COMMIT_SUBJECT_LIMIT = 50


@dataclass(frozen=True)
class GitFacts:
    """Read-only metadata about a checkout."""

    commit_sha: str | None
    default_branch: str | None
    commit_subjects: tuple[str, ...]


def _run_git(args: list[str], cwd: Path, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    """Run one read-only git subcommand with a fixed argument list."""
    # Never prompt for credentials: a private URL must fail fast, not hang.
    # The environment is built in config.py, the only permitted reader of
    # os.environ (standing rule 2).
    env = subprocess_env()
    return subprocess.run(  # noqa: S603 - fixed argv, shell=False
        ["git", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def is_url(source: str) -> bool:
    """True when ``source`` looks like a remote to clone rather than a path."""
    return source.startswith(("http://", "https://", "git@", "ssh://"))


def validate_url(url: str, allow_any_host: bool = False) -> str:
    """Return the host of ``url``, rejecting anything not safe to clone.

    Raises:
        HostNotAllowed: the scheme is unsupported, or the host is off the
            allowlist and ``allow_any_host`` was not set.
    """
    if url.startswith("file://"):
        # Always refused: a file:// clone turns a URL argument into arbitrary
        # local filesystem access, and --allow-any-host must not unlock that.
        raise HostNotAllowed("file:// sources are not supported.")

    if url.startswith("git@"):
        host = url.split("@", 1)[1].split(":", 1)[0]
    else:
        parsed = urlparse(url)
        if parsed.scheme not in {"https", "ssh"}:
            raise HostNotAllowed(f"Unsupported scheme '{parsed.scheme}'. Use https or ssh.")
        host = parsed.hostname or ""

    if not host:
        raise HostNotAllowed("Could not determine a host from the URL.")
    if not allow_any_host and host.lower() not in ALLOWED_HOSTS:
        allowed = ", ".join(sorted(ALLOWED_HOSTS))
        raise HostNotAllowed(
            f"Host '{host}' is not on the allowlist ({allowed}). "
            f"Pass --allow-any-host to override."
        )
    return host


def resolve_local(path_str: str) -> Path:
    """Resolve a local path and confirm it is a git repository.

    Symlinks are resolved first so a link pointing outside the intended tree is
    visible as its real location rather than followed blindly.

    Raises:
        NotAGitRepo: the path does not exist or has no .git entry.
    """
    path = Path(path_str).expanduser().resolve()
    if not path.is_dir():
        raise NotAGitRepo(f"'{path_str}' is not a directory.")
    if not (path / ".git").exists():
        raise NotAGitRepo(f"'{path_str}' has no .git -- not a git repository.")
    return path


def clone(url: str, into: Path, timeout: int) -> Path:
    """Shallow, blobless, hook-free clone of ``url`` into ``into``.

    Raises:
        AcquireError: the clone failed or timed out.
    """
    target = into / "repo"
    args = [
        "-c",
        f"core.hooksPath={_NULL_HOOKS}",
        "clone",
        "--depth",
        "1",
        "--filter=blob:none",
        "--no-tags",
        "--quiet",
        "--",
        url,
        str(target),
    ]
    try:
        result = _run_git(args, cwd=into, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise AcquireError(f"Clone timed out after {timeout}s.") from exc
    if result.returncode != 0:
        # git's stderr can echo the URL; keep the message short and generic.
        raise AcquireError("Clone failed. Check the URL and that the repo is public.")
    return target


def read_facts(repo: Path) -> GitFacts:
    """Read commit SHA, default branch and recent subjects from a checkout.

    An empty repository has no HEAD. That is a legitimate state, not an error:
    every field comes back None or empty and the caller degrades accordingly
    (the cache is bypassed and OB-05 returns not_applicable).
    """
    head = _run_git(["rev-parse", "HEAD"], cwd=repo)
    commit_sha = head.stdout.strip() if head.returncode == 0 else None

    branch = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=repo)
    default_branch = branch.stdout.strip() if branch.returncode == 0 else None
    if default_branch == "HEAD":  # detached
        default_branch = None

    subjects: tuple[str, ...] = ()
    if commit_sha:
        log = _run_git(["log", f"-{_COMMIT_SUBJECT_LIMIT}", "--format=%s", "--no-merges"], cwd=repo)
        if log.returncode == 0:
            subjects = tuple(line for line in log.stdout.splitlines() if line.strip())

    return GitFacts(commit_sha=commit_sha, default_branch=default_branch, commit_subjects=subjects)


@contextmanager
def acquire(source: str, *, allow_any_host: bool = False, timeout: int = 30) -> Iterator[Path]:
    """Yield a local checkout of ``source``, cleaning up on every exit path.

    A local path is used in place and never deleted. A URL is cloned into a
    temporary directory which is removed on success, on exception, and on
    timeout alike.
    """
    if not is_url(source):
        yield resolve_local(source)
        return

    validate_url(source, allow_any_host=allow_any_host)
    tmp = Path(tempfile.mkdtemp(prefix="agent-trust-"))
    logger.info("cloning", extra={"host": validate_url(source, allow_any_host=True)})
    try:
        yield clone(source, tmp, timeout=timeout)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
