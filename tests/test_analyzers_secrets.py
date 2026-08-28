"""BR-01 is the highest-stakes detector in the product.

A false negative loses the claim; a false positive on a clean repo loses the
demo. Both are defects, so both directions are tested exhaustively here.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from agent_trust.acquire import read_facts
from agent_trust.analyzers.blast_radius import (
    AXIS,
    SPECS,
    check_committed_secrets,
    check_destructive_ops_guarded,
    check_env_not_tracked,
    check_gitignore_coverage,
    scan_secrets,
)
from agent_trust.inventory import RepoContext, build_context
from agent_trust.limits import Budget
from agent_trust.models import CheckStatus

# Real-shaped values, none of them live credentials. Each carries no placeholder
# marker, so the allowlist must not rescue them.
POSITIVES: list[tuple[str, str]] = [
    ("aws_access_key_id", "AKIAQ7RSTUVWX1234567"),
    ("github_token", "ghp_9aBcD3fGhI2jKlM4nOpQ5rStU6vWxY7zA1bC"),
    ("github_token", "gho_1QWERTYUIOP2asdfghjkl3ZXCVBNM4qwerty5"),
    ("stripe_live_key", "sk_live_51QwErTyUiOpAsDfGhJkLzXcVb"),
    ("slack_token", "xoxb-472913857206-KdLmNpQrStUvWxYz"),
    ("google_api_key", "AIzaSyD9fK2mQ7pR4tV6wX8yZ1aB3cD5eF7gH9j"),
    ("anthropic_key", "sk-ant-api03-QwErTyUiOpAsDfGhJkLzXcVbNmQwErTyUi"),
    ("openai_key", "sk-QwErTyUiOpAsDfGhJkLzXcVbNmQwErTyUiOp"),
    ("private_key_block", "-----BEGIN RSA PRIVATE KEY-----"),
    ("private_key_block", "-----BEGIN OPENSSH PRIVATE KEY-----"),
    (
        "json_web_token",
        "eyJhbGciOiJIUzI1NiIs.eyJzdWIiOiIxMjM0NTY3.SflKxwRJSMeKKF2QT4fwpM",
    ),
    ("high_entropy_assignment", 'DB_PASSWORD = "j8Kq2ZmV4nRw7YtB9xLpQ3sF"'),
]

# Forms that appear constantly in healthy repositories. Any hit here is a defect.
NEGATIVES: list[str] = [
    'AWS_KEY = "AKIAIOSFODNN7EXAMPLE"',
    'API_KEY = "your-api-key-here"',
    'SECRET = "CHANGEME"',
    'TOKEN = "placeholder"',
    'password = "dummy"',
    'STRIPE_KEY = "sk_test_51QwErTyUiOpAsDfGhJkLzXcVb"',
    'api_key = os.environ["API_KEY"]',
    "api_key = process.env.API_KEY",
    'API_KEY = "${API_KEY}"',
    'token = "<your token>"',
    'SECRET_KEY = "insert-secret-here"',
    'password = "not_a_real_password_value"',
    'API_KEY = ""',
    "API_KEY=",
    "# Set SECRET_TOKEN to the value from the dashboard before running this",
    'PASSWORD_MIN_LENGTH = "twelve characters minimum for all accounts"',
    'secret = "aaaaaaaaaaaaaaaaaaaaaaaaaaaa"',
    'token = "the quick brown fox jumps over the lazy dog"',
    'API_KEY_NAME = "production-key-rotation-schedule-quarterly"',
    'credential_help = "Ask an administrator to provision one for you today"',
    'SECRET = "0000000000000000000000000"',
    'key = "xxxxxxxxxxxxxxxxxxxxxxxxxx"',
]


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
    _git(["commit", "-qm", "fixture repository for the secret tests"], root)
    return build_context(
        root=root,
        source=str(root),
        facts=read_facts(root),
        budget=Budget(max_files=20_000, max_bytes=209_715_200),
    )


# ── true positives ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("matcher", "value"), POSITIVES, ids=[f"{m}-{i}" for i, (m, _) in enumerate(POSITIVES)]
)
def test_every_provider_pattern_is_caught(tmp_path: Path, matcher: str, value: str) -> None:
    line = value if "=" in value else f'KEY = "{value}"'
    ctx = make_repo(tmp_path, {"src/config.py": f"{line}\n"})
    hits, _suppressed = scan_secrets(ctx)
    assert hits, f"{matcher} was not detected"
    assert hits[0].matcher == matcher


def test_a_committed_key_fails_the_check_at_high_severity(tmp_path: Path) -> None:
    ctx = make_repo(tmp_path, {"src/settings.py": 'AWS = "AKIAQ7RSTUVWX1234567"\n'})
    outcome = check_committed_secrets(ctx)
    assert outcome.status is CheckStatus.FAIL
    assert outcome.evidence
    assert "Rotate" in outcome.detail


def test_a_key_in_src_is_caught_while_the_same_value_in_tests_is_not(tmp_path: Path) -> None:
    value = 'KEY = "AKIAQ7RSTUVWX1234567"\n'
    ctx = make_repo(tmp_path, {"src/app.py": value, "tests/fixtures/sample.py": value})
    hits, suppressed = scan_secrets(ctx)
    assert [hit.path for hit in hits] == ["src/app.py"]
    assert suppressed >= 1


# ── zero false positives ────────────────────────────────────────────────────


@pytest.mark.parametrize("line", NEGATIVES)
def test_placeholder_forms_are_never_flagged(tmp_path: Path, line: str) -> None:
    ctx = make_repo(tmp_path, {"src/config.py": f"{line}\n"})
    hits, _ = scan_secrets(ctx)
    assert hits == [], f"false positive on: {line}"


def test_a_clean_repo_reports_zero_secrets(tmp_path: Path) -> None:
    ctx = make_repo(
        tmp_path,
        {
            ".env.example": "API_KEY=\nDATABASE_URL=\n",
            "README.md": "# demo\n\nSet API_KEY before running.\n",
            "src/app.py": "import os\n\nkey = os.environ['API_KEY']\n",
        },
    )
    assert check_committed_secrets(ctx).status is CheckStatus.PASS


def test_suppression_count_is_always_reported(tmp_path: Path) -> None:
    ctx = make_repo(tmp_path, {".env.example": 'KEY = "AKIAIOSFODNN7EXAMPLE"\n'})
    outcome = check_committed_secrets(ctx)
    assert outcome.status is CheckStatus.PASS
    assert "suppressed" in outcome.detail


def test_entropy_alone_would_flag_a_pangram(tmp_path: Path) -> None:
    # Regression guard. This value scores above the entropy threshold, so only
    # the no-whitespace rule keeps it out of the report.
    from agent_trust.analyzers.entropy import ENTROPY_THRESHOLD, looks_random, shannon

    pangram = "the quick brown fox jumps over the lazy dog"
    assert shannon(pangram) >= ENTROPY_THRESHOLD
    assert not looks_random(pangram)


# ── redaction ───────────────────────────────────────────────────────────────


def test_no_output_carries_the_full_secret(tmp_path: Path) -> None:
    secret = "AKIAQ7RSTUVWX1234567"
    ctx = make_repo(tmp_path, {"src/settings.py": f'AWS = "{secret}"\n'})
    outcome = check_committed_secrets(ctx)

    serialized = outcome.model_dump_json()
    assert secret not in serialized
    assert secret[4:-2] not in serialized
    for item in outcome.evidence:
        assert secret not in item.snippet


# ── BR-02 and BR-03 ─────────────────────────────────────────────────────────


def test_tracked_env_fails_then_passes_once_untracked(tmp_path: Path) -> None:
    tracked = make_repo(tmp_path / "a", {".env": "SECRET=abc\n"})
    assert check_env_not_tracked(tracked).status is CheckStatus.FAIL

    clean = make_repo(tmp_path / "b", {".env.example": "SECRET=\n"})
    assert check_env_not_tracked(clean).status is CheckStatus.PASS


def test_gitignore_missing_key_patterns_is_partial_not_fail(tmp_path: Path) -> None:
    ctx = make_repo(tmp_path, {".gitignore": ".env\ndist/\n"})
    outcome = check_gitignore_coverage(ctx)
    assert outcome.status is CheckStatus.PARTIAL
    assert "key and credential" in outcome.detail


def test_complete_gitignore_passes(tmp_path: Path) -> None:
    ctx = make_repo(tmp_path, {".gitignore": ".env\n*.pem\n*.key\ndist/\nnode_modules/\n"})
    assert check_gitignore_coverage(ctx).status is CheckStatus.PASS


def test_absent_gitignore_fails(tmp_path: Path) -> None:
    ctx = make_repo(tmp_path, {"a.py": "x = 1\n"})
    assert check_gitignore_coverage(ctx).status is CheckStatus.FAIL


# ── the unimplemented checks must not read as passes ────────────────────────


def test_prompt_ten_checks_raise_rather_than_passing(tmp_path: Path) -> None:
    ctx = make_repo(tmp_path, {"a.py": "x = 1\n"})
    with pytest.raises(NotImplementedError):
        check_destructive_ops_guarded(ctx)


def test_axis_weights_still_total_one_hundred() -> None:
    assert sum(spec.weight for spec in SPECS) == 100
    assert len(SPECS) == 7
    assert AXIS.value == "blast_radius"
