"""Content-addressed report cache.

Keyed on commit SHA plus schema version: the same commit graded by the same
build is the same answer, and re-running it should not cost another API call.

Three rules that keep it honest:

* A repository with no commits has no SHA, so it is never cached. There is
  nothing to key on, and an empty repo is cheap to re-audit anyway.
* A cached report whose ``schema_version`` differs is discarded, not migrated.
* A cached report with ``llm.used`` false is a **miss** when enrichment is
  requested -- otherwise a ``--no-llm`` run would silently poison later runs.

Writes are atomic: a temp file plus a rename, so an interrupted run never leaves
a half-written report behind for the next one to read.
"""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path

from agent_trust.logging import get_logger
from agent_trust.models import SCHEMA_VERSION, Report, load_report

logger = get_logger("cache")

TTL_SECONDS = 24 * 60 * 60


def cache_path(cache_dir: Path, commit_sha: str) -> Path:
    """Where the report for ``commit_sha`` lives."""
    return cache_dir / f"{commit_sha}-{SCHEMA_VERSION}.json"


def read(cache_dir: Path, commit_sha: str | None, *, want_llm: bool = False) -> Report | None:
    """Return a cached report, or None on any kind of miss."""
    if not commit_sha:
        return None
    path = cache_path(cache_dir, commit_sha)
    if not path.is_file():
        return None
    if time.time() - path.stat().st_mtime > TTL_SECONDS:
        return None

    try:
        report = load_report(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        # A corrupt or version-mismatched entry is a miss, never a crash.
        logger.info("cache entry unusable", extra={"reason": type(exc).__name__})
        return None

    if want_llm and not report.llm.used:
        # The caller asked for model-written prose; this entry has templates.
        return None
    return report


def write(cache_dir: Path, report: Report) -> Path | None:
    """Store ``report``, atomically. Returns the path, or None if not cacheable."""
    commit_sha = report.repo.commit_sha
    if not commit_sha:
        return None

    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_path(cache_dir, commit_sha)
    handle, temp_name = tempfile.mkstemp(dir=cache_dir, suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="") as stream:
            stream.write(report.to_json() + "\n")
        os.replace(temp_name, path)
    except OSError:
        Path(temp_name).unlink(missing_ok=True)
        raise
    return path
