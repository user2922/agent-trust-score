"""The MCP boundary: structured errors, no tracebacks, nothing on stdout."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from agent_trust import mcp_server
from agent_trust.config import get_settings
from agent_trust.models import AXIS_ORDER

# The tools are registered with the server, so reach the plain functions through
# the module rather than through the decorator's return value.
audit_repo = mcp_server.audit_repo
get_axis = mcp_server.get_axis
suggest_fixes = mcp_server.suggest_fixes


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
    monkeypatch.setenv("AGENT_TRUST_CACHE_DIR", str(tmp_path / "cache"))
    get_settings.cache_clear()


def is_error(payload: dict[str, Any]) -> bool:
    return "error" in payload


# ── the happy path ──────────────────────────────────────────────────────────


def test_audit_repo_returns_a_full_report(repo: Path) -> None:
    payload = audit_repo(str(repo), use_llm=False)
    assert not is_error(payload)
    assert payload["schema_version"] == "1.0"
    assert len(payload["axes"]) == 5
    assert [axis["key"] for axis in payload["axes"]] == list(AXIS_ORDER)


def test_get_axis_returns_one_axis(repo: Path) -> None:
    payload = get_axis(str(repo), "blast_radius")
    assert not is_error(payload)
    assert payload["key"] == "blast_radius"
    assert "checks" in payload


def test_suggest_fixes_returns_a_list(repo: Path) -> None:
    payload = suggest_fixes(str(repo))
    assert not is_error(payload)
    assert isinstance(payload["fixes"], list)


def test_suggest_fixes_honours_max_items(repo: Path) -> None:
    assert len(suggest_fixes(str(repo), max_items=1)["fixes"]) <= 1


# ── the boundary converts every failure to data ─────────────────────────────


def test_missing_repo_returns_a_structured_error(tmp_path: Path) -> None:
    payload = audit_repo(str(tmp_path / "nope"), use_llm=False)
    assert is_error(payload)
    assert set(payload["error"]) == {"code", "message"}
    assert payload["error"]["code"] == "not_a_git_repo"
    assert "Traceback" not in payload["error"]["message"]


def test_unlisted_host_returns_a_structured_error() -> None:
    payload = audit_repo("https://evil.example.com/a/b", use_llm=False)
    assert is_error(payload)
    assert payload["error"]["code"] == "host_not_allowed"


def test_unknown_axis_is_rejected_by_name(repo: Path) -> None:
    payload = get_axis(str(repo), "not_an_axis")
    assert is_error(payload)
    assert "not_an_axis" in payload["error"]["message"]


def test_unknown_axes_list_is_rejected(repo: Path) -> None:
    payload = audit_repo(str(repo), axes=["blast_radius", "nope"], use_llm=False)
    assert is_error(payload)


def test_bad_max_items_is_rejected(repo: Path) -> None:
    assert is_error(suggest_fixes(str(repo), max_items=0))


def test_unexpected_exception_becomes_internal_error(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("a secret path /home/someone/private appears here")

    monkeypatch.setattr(mcp_server, "_run_audit", boom)
    payload = audit_repo(str(repo), use_llm=False)
    assert payload["error"]["code"] == "internal_error"
    # The raw exception text must not cross the boundary.
    assert "private" not in payload["error"]["message"]
    assert "Traceback" not in payload["error"]["message"]


# ── the server itself ───────────────────────────────────────────────────────


def test_server_registers_the_three_tools() -> None:
    names = {tool.name for tool in mcp_server.server._tool_manager.list_tools()}
    assert {"audit_repo", "get_axis", "suggest_fixes"} <= names


def test_tools_carry_descriptions_an_agent_can_act_on() -> None:
    for tool in mcp_server.server._tool_manager.list_tools():
        assert tool.description, f"{tool.name} has no description"
        assert len(tool.description) > 40


def test_importing_the_server_writes_nothing_to_stdout() -> None:
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", "import agent_trust.mcp_server"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout == "", f"stdout polluted: {result.stdout!r}"
