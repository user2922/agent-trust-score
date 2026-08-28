"""Build the clean and ugly fixture repositories, with real git history.

The fixtures are defined here rather than committed as trees for two reasons: a
nested `.git` cannot be committed inside this repository, and the ugly fixture
must contain a marker-free key-shaped string, which is safer to keep in one
auditable file than scattered across a directory.

Nothing here is a live credential. The planted values are syntactically valid
and have never existed. Each is assembled from fragments so that no line of this
file matches a detector pattern -- the tool grades its own repository as a gate,
and a fixture definition must not make it fail.

Usage:
    uv run python scripts/build_fixtures.py <destination>
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# ── the clean repository ────────────────────────────────────────────────────

CLEAN_README = """# Ledger

A small double-entry ledger service. It records transactions, keeps accounts in
balance, and exposes both an HTTP API and a command line.

## Setup

```
uv sync --extra dev
```

You need Python 3.12 and a Postgres instance. Copy `.env.example` to `.env.local`
and fill in the connection string before the first run. No other configuration is
required to work on the project locally, and every value has a documented default
so a new contributor can be productive without asking anyone for credentials.

## Run and test

```
uv run ledger serve --port 8000
uv run ledger import --file statements.csv --dry-run
uv run python -m pytest
```

The `--dry-run` flag prints the plan without writing anything, and every command
that mutates data requires it to be absent explicitly.

## Architecture

```
src/
  app.py        the HTTP surface and the CLI entry point
  ledger.py     double-entry posting rules, pure functions
  audit.py      the append-only audit trail
tests/
  test_app.py   covers the posting rules and the API
```

The posting rules are pure and heavily tested; everything with a side effect
lives behind an explicit flag. The audit trail records the actor, the action and
a timestamp for every state change, so any operation can be reconstructed later.

## Conventions

Type annotations on every public function. Structured logging, never `print`.
Sorted output everywhere so diffs stay small.

## Do not touch

Do not edit `src/generated_types.py` by hand; it is generated from the schema.
"""

CLEAN_AGENT_DOC = """# CLAUDE.md

## Setup

```
uv sync --extra dev
```

## Run and test

```
uv run ledger serve --port 8000
uv run python -m pytest
```

## Architecture

```
src/
  app.py
  ledger.py
  audit.py
```

`src/app.py` owns the HTTP surface. `src/ledger.py` holds the posting rules and
must stay free of I/O. `src/audit.py` is the only writer of the audit trail.

## Conventions

Annotate every public function. Use the structured logger, never `print`.

## Do not touch

Do not edit `src/generated_types.py`; it is generated. Do not hand-edit
`uv.lock`.
"""

CLEAN_APP = '''"""The HTTP surface and the CLI."""

from __future__ import annotations

import argparse
import logging
import os

import sentry_sdk
import structlog

logger = structlog.get_logger(__name__)
logging.getLogger("ledger").setLevel(logging.INFO)

sentry_sdk.init(dsn=os.environ.get("SENTRY_DSN", ""))


def health() -> dict[str, str]:
    """Liveness probe for the load balancer."""
    logger.info("health checked")
    return {"status": "ok"}


def post_transaction(account: str, amount: int) -> dict[str, object]:
    """Record one transaction against an account."""
    logger.info("posting", account=account, amount=amount)
    return {"account": account, "amount": amount}


def send_receipt(address: str) -> bool:
    """Email a receipt, but only when a real key is configured."""
    if not os.environ.get("RESEND_API_KEY"):
        logger.info("receipt suppressed, no key configured")
        return False
    return True


def purge(directory: str, dry_run: bool = True) -> None:
    """Remove a directory tree. Refuses to act without an explicit dry_run=False."""
    if dry_run:
        logger.info("would purge", directory=directory)
        return
    import shutil

    shutil.rmtree(directory)


def main() -> int:
    """Entry point for the ledger command."""
    parser = argparse.ArgumentParser(prog="ledger")
    parser.add_argument("--version", action="store_true")
    parser.parse_args()
    return 0
'''

CLEAN_AUDIT = '''"""The append-only audit trail."""

from __future__ import annotations

import structlog

logger = structlog.get_logger(__name__)


def record(actor: str, action: str, timestamp: str) -> dict[str, str]:
    """Append one entry to audit_log. Nothing here ever updates or deletes."""
    entry = {"actor": actor, "action": action, "timestamp": timestamp}
    logger.info("audit_log entry", **entry)
    return entry
'''

CLEAN_TESTS = '''"""Tests for the posting rules and the API surface."""

from __future__ import annotations

from src.app import health, post_transaction
from src.audit import record


def test_health_reports_ok() -> None:
    assert health()["status"] == "ok"


def test_posting_returns_the_transaction() -> None:
    assert post_transaction("cash", 100)["amount"] == 100


def test_audit_entry_carries_actor_action_and_time() -> None:
    entry = record("alice", "post_transaction", "2026-01-01T00:00:00Z")
    assert set(entry) == {"actor", "action", "timestamp"}
'''

CLEAN_CI = """name: CI
on:
  push:
    branches: [master]
  pull_request:
    branches: [master]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: uv sync --extra dev
      - run: uv run python -m pytest
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: uv run ruff check .
"""

CLEAN_PYPROJECT = """[project]
name = "ledger"
version = "1.0.0"
requires-python = ">=3.12"
dependencies = ["fastapi", "structlog", "sentry-sdk", "pytest"]

[project.scripts]
ledger = "src.app:main"

[tool.mypy]
strict = true

[tool.ruff]
line-length = 100
"""

CLEAN_FILES: dict[str, str] = {
    "README.md": CLEAN_README,
    "CLAUDE.md": CLEAN_AGENT_DOC,
    "CHANGELOG.md": "# Changelog\n\n## 1.0.0\n\nFirst release.\n",
    "pyproject.toml": CLEAN_PYPROJECT,
    "mcp.json": '{"name": "ledger", "tools": []}\n',
    "openapi.yaml": "openapi: 3.1.0\ninfo:\n  title: Ledger\n  version: 1.0.0\npaths: {}\n",
    ".env.example": (
        "# No required values; every one has a default.\n"
        "DATABASE_URL=\nSENTRY_DSN=\nRESEND_API_KEY=\n"
    ),
    ".gitignore": (
        ".env\n.env.*\n!.env.example\n*.pem\n*.key\ncredentials\ndist/\nbuild/\n__pycache__/\n"
    ),
    "CODEOWNERS": "* @ledger-team\n",
    ".pre-commit-config.yaml": "repos:\n  - repo: local\n    hooks: []\n",
    "src/app.py": CLEAN_APP,
    "src/audit.py": CLEAN_AUDIT,
    "src/ledger.py": '"""Posting rules."""\n\nfrom __future__ import annotations\n\n\ndef balance(entries: list[int]) -> int:\n    """Sum of every entry; zero for an empty ledger."""\n    return sum(entries)\n',
    "tests/test_app.py": CLEAN_TESTS,
    ".github/workflows/ci.yml": CLEAN_CI,
}

CLEAN_COMMITS = [
    "add the posting rules and their tests",
    "expose a health endpoint for the load balancer",
    "record actor, action and timestamp in the audit trail",
    "document setup, architecture and the run commands",
    "add the MCP manifest so agents can call the ledger",
    "publish the OpenAPI schema for the HTTP surface",
    "wire structured logging through every module",
    "initialise error reporting at startup",
    "require an explicit flag before any destructive purge",
    "add CI running the test suite on every push",
    "add CODEOWNERS so changes need a named reviewer",
    "ignore env files and credential material",
]

# ── the ugly repository ─────────────────────────────────────────────────────

# Syntactically valid, never issued, marker-free on purpose: the detector must
# catch it, and a placeholder marker would make the fixture prove nothing.
FAKE_AWS_KEY = "AKIA" + "Q7RSTUVWX1234567"
# Same reasoning: assembled, so this file carries no matching literal.
FAKE_DB_PASSWORD = "j8Kq2Zm" + "V4nRw7Yt" + "B9xLpQ3sF"

UGLY_SETTINGS = f'''import os

AWS_ACCESS_KEY_ID = "{FAKE_AWS_KEY}"
DB_PASSWORD = "{FAKE_DB_PASSWORD}"


def reset_everything(target):
    import shutil
    shutil.rmtree(target)
    db.execute("DROP TABLE users")
    db.execute("DELETE FROM sessions;")


def charge(amount):
    stripe.charges.create(amount=amount)
'''

UGLY_FILES: dict[str, str] = {
    "README.md": "# app\n\nTODO.\n",
    "settings.py": UGLY_SETTINGS,
    ".env": f"AWS_ACCESS_KEY_ID={FAKE_AWS_KEY}\nDB_PASSWORD=hunter2\n",
    "package.json": "{ this is not valid json",
    "src/components/Panel.tsx": (
        "export function Panel() {\n"
        "  const key = process.env.SUPABASE_SERVICE_ROLE_KEY\n"
        "  console.log('rendering', key)\n"
        "  return null\n"
        "}\n"
    ),
    "src/main.py": (
        "def run(a, b):\n"
        "    console = None\n"
        "    print('starting')\n"
        "    print('working')\n"
        "    print('done')\n"
        "    return a + b\n"
    ),
    "src/util.py": "def helper(x):\n    print(x)\n    return x\n",
}

UGLY_COMMITS = ["wip"] * 14


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)  # noqa: S603


def _write(root: Path, files: dict[str, str]) -> None:
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="")


def build(root: Path, files: dict[str, str], subjects: list[str]) -> Path:
    """Materialise a fixture repository with real git history at ``root``."""
    root.mkdir(parents=True, exist_ok=True)
    _git(["init", "-q", "-b", "master"], root)
    _git(["config", "user.email", "fixture@example.com"], root)
    _git(["config", "user.name", "fixture"], root)

    _write(root, files)

    # One commit per subject so OB-05 has real history to read. The files all
    # land in the first commit; later commits touch a marker file.
    for index, subject in enumerate(subjects):
        if index:
            (root / ".history").write_text(f"{index}\n", encoding="utf-8")
        _git(["add", "-A", "-f"], root)
        _git(["commit", "-qm", subject, "--allow-empty"], root)
    return root


def build_clean(destination: Path) -> Path:
    return build(destination / "clean-repo", CLEAN_FILES, CLEAN_COMMITS)


def build_ugly(destination: Path) -> Path:
    return build(destination / "ugly-repo", UGLY_FILES, UGLY_COMMITS)


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    destination = Path(sys.argv[1]).resolve()
    print(f"clean: {build_clean(destination)}")
    print(f"ugly:  {build_ugly(destination)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
