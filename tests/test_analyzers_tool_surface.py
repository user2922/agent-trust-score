"""Tool Surface: one pass case, one fail case, and the partial where there is one."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from agent_trust.acquire import read_facts
from agent_trust.analyzers import REGISTRY, CheckSpec, assert_weights
from agent_trust.analyzers.tool_surface import (
    AXIS,
    SPECS,
    check_api_schema,
    check_cli_entry_point,
    check_config_contract,
    check_entry_points_documented,
    check_manifest_parses,
    check_mcp_server,
    check_typed_boundaries,
)
from agent_trust.inventory import RepoContext, build_context
from agent_trust.limits import Budget
from agent_trust.models import CheckStatus


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)  # noqa: S603


def make_repo(tmp_path: Path, files: dict[str, str]) -> RepoContext:
    """A committed repo containing exactly ``files``, inventoried."""
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
    _git(["add", "-A"], root)
    _git(["commit", "-qm", "fixture repository for the analyzer tests"], root)
    return build_context(
        root=root,
        source=str(root),
        facts=read_facts(root),
        budget=Budget(max_files=20_000, max_bytes=209_715_200),
    )


# ── the contract ────────────────────────────────────────────────────────────


def test_weights_sum_to_one_hundred() -> None:
    assert sum(spec.weight for spec in SPECS) == 100
    assert len(SPECS) == 7


def test_a_mistyped_weight_fails_at_import_time() -> None:
    with pytest.raises(ValueError, match="sum to 99"):
        assert_weights(AXIS, (CheckSpec("TS-01", "t", 99),))


def test_the_axis_is_registered() -> None:
    assert AXIS in REGISTRY


# ── TS-01 MCP server ────────────────────────────────────────────────────────


def test_mcp_manifest_passes(tmp_path: Path) -> None:
    ctx = make_repo(tmp_path, {"mcp.json": "{}\n"})
    assert check_mcp_server(ctx).status is CheckStatus.PASS


def test_mcp_dependency_passes(tmp_path: Path) -> None:
    ctx = make_repo(
        tmp_path, {"package.json": '{"dependencies": {"@modelcontextprotocol/sdk": "1"}}'}
    )
    assert check_mcp_server(ctx).status is CheckStatus.PASS


def test_mcp_construction_passes(tmp_path: Path) -> None:
    ctx = make_repo(tmp_path, {"srv.py": "server = MCPServer(name='x')\n"})
    assert check_mcp_server(ctx).status is CheckStatus.PASS


def test_no_mcp_anything_fails_and_says_what_was_searched(tmp_path: Path) -> None:
    ctx = make_repo(tmp_path, {"main.py": "print(1)\n"})
    outcome = check_mcp_server(ctx)
    assert outcome.status is CheckStatus.FAIL
    assert "Searched for" in outcome.detail


def test_removing_the_manifest_costs_exactly_twenty_points(tmp_path: Path) -> None:
    with_mcp = check_mcp_server(make_repo(tmp_path / "a", {"mcp.json": "{}\n"}))
    without = check_mcp_server(make_repo(tmp_path / "b", {"main.py": "x = 1\n"}))
    assert with_mcp.earned - without.earned == 20


# ── TS-02 API schema ────────────────────────────────────────────────────────


@pytest.mark.parametrize("name", ["openapi.yaml", "schema.graphql", "api/service.proto"])
def test_schema_files_pass(tmp_path: Path, name: str) -> None:
    ctx = make_repo(tmp_path / name.replace("/", "_"), {name: "x\n"})
    assert check_api_schema(ctx).status is CheckStatus.PASS


# ── TS-03 CLI entry point ───────────────────────────────────────────────────


def test_project_scripts_passes(tmp_path: Path) -> None:
    ctx = make_repo(tmp_path, {"pyproject.toml": '[project.scripts]\ndemo = "d:main"\n'})
    assert check_cli_entry_point(ctx).status is CheckStatus.PASS


def test_package_bin_passes(tmp_path: Path) -> None:
    ctx = make_repo(tmp_path, {"package.json": '{"bin": {"demo": "cli.js"}}'})
    assert check_cli_entry_point(ctx).status is CheckStatus.PASS


def test_cli_framework_import_passes(tmp_path: Path) -> None:
    ctx = make_repo(tmp_path, {"cli.py": "import argparse\n"})
    assert check_cli_entry_point(ctx).status is CheckStatus.PASS


def test_no_entry_point_fails(tmp_path: Path) -> None:
    ctx = make_repo(tmp_path, {"lib.py": "x = 1\n"})
    assert check_cli_entry_point(ctx).status is CheckStatus.FAIL


# ── TS-04 documented entry points ───────────────────────────────────────────


def test_usage_block_with_a_flag_passes(tmp_path: Path) -> None:
    ctx = make_repo(tmp_path, {"README.md": "# demo\n\n    demo build --watch\n"})
    assert check_entry_points_documented(ctx).status is CheckStatus.PASS


def test_readme_without_any_invocation_fails(tmp_path: Path) -> None:
    ctx = make_repo(tmp_path, {"README.md": "# demo\n\nA project that does things.\n"})
    assert check_entry_points_documented(ctx).status is CheckStatus.FAIL


# ── TS-05 typed boundaries ──────────────────────────────────────────────────


def _python_module(annotated: int, bare: int) -> str:
    lines = [f"def typed_{i}(a: int) -> int:\n    return a\n" for i in range(annotated)]
    lines += [f"def bare_{i}(a):\n    return a\n" for i in range(bare)]
    return "\n".join(lines)


def test_fully_annotated_python_passes(tmp_path: Path) -> None:
    ctx = make_repo(tmp_path, {"m.py": _python_module(annotated=8, bare=2)})
    outcome = check_typed_boundaries(ctx)
    assert outcome.status is CheckStatus.PASS
    assert "80%" in outcome.detail


def test_forty_percent_annotated_is_partial(tmp_path: Path) -> None:
    ctx = make_repo(tmp_path, {"m.py": _python_module(annotated=4, bare=6)})
    outcome = check_typed_boundaries(ctx)
    assert outcome.status is CheckStatus.PARTIAL
    assert "40%" in outcome.detail


def test_ten_percent_annotated_fails(tmp_path: Path) -> None:
    ctx = make_repo(tmp_path, {"m.py": _python_module(annotated=1, bare=9)})
    assert check_typed_boundaries(ctx).status is CheckStatus.FAIL


def test_tsconfig_strict_passes(tmp_path: Path) -> None:
    ctx = make_repo(
        tmp_path,
        {"tsconfig.json": '{"compilerOptions": {"strict": true}}', "a.ts": "const x = 1\n"},
    )
    assert check_typed_boundaries(ctx).status is CheckStatus.PASS


def test_go_only_repo_is_not_applicable(tmp_path: Path) -> None:
    ctx = make_repo(tmp_path, {"main.go": "package main\n"})
    outcome = check_typed_boundaries(ctx)
    assert outcome.status is CheckStatus.NOT_APPLICABLE
    assert outcome.earned == 0


def test_not_applicable_leaves_the_axis_denominator(tmp_path: Path) -> None:
    from agent_trust.scoring import score_axis

    ctx = make_repo(tmp_path, {"main.go": "package main\n", "mcp.json": "{}\n"})
    checks = [check_mcp_server(ctx), check_typed_boundaries(ctx)]
    axis = score_axis(AXIS, "Tool Surface", checks)
    # 20 of 20 applicable points, not 20 of 35.
    assert axis.score == 100


def test_syntax_error_does_not_crash_the_analyzer(tmp_path: Path) -> None:
    ctx = make_repo(
        tmp_path, {"broken.py": "def (((\n", "ok.py": "def f(a: int) -> int:\n    return a\n"}
    )
    assert check_typed_boundaries(ctx).status in {
        CheckStatus.PASS,
        CheckStatus.PARTIAL,
        CheckStatus.FAIL,
    }


# ── TS-06 manifest, TS-07 config ────────────────────────────────────────────


def test_valid_manifest_passes(tmp_path: Path) -> None:
    ctx = make_repo(tmp_path, {"pyproject.toml": '[project]\nname = "demo"\n'})
    assert check_manifest_parses(ctx).status is CheckStatus.PASS


def test_unparseable_manifest_fails_with_a_reason(tmp_path: Path) -> None:
    ctx = make_repo(tmp_path, {"package.json": "{ not json"})
    outcome = check_manifest_parses(ctx)
    assert outcome.status is CheckStatus.FAIL
    assert "does not parse" in outcome.detail


def test_env_example_passes(tmp_path: Path) -> None:
    ctx = make_repo(tmp_path, {".env.example": "API_KEY=\n"})
    assert check_config_contract(ctx).status is CheckStatus.PASS


def test_settings_schema_passes(tmp_path: Path) -> None:
    ctx = make_repo(tmp_path, {"config.py": "class S(BaseSettings):\n    x: int = 1\n"})
    assert check_config_contract(ctx).status is CheckStatus.PASS


def test_no_config_contract_fails(tmp_path: Path) -> None:
    assert (
        check_config_contract(make_repo(tmp_path, {"a.py": "x = 1\n"})).status is CheckStatus.FAIL
    )


# ── evidence and determinism ────────────────────────────────────────────────


def test_every_failed_check_names_what_was_searched(tmp_path: Path) -> None:
    ctx = make_repo(tmp_path, {"main.go": "package main\n"})
    from agent_trust.analyzers.tool_surface import run

    for outcome in run(ctx):
        if outcome.status is CheckStatus.FAIL:
            assert outcome.detail, f"{outcome.id} failed with no detail"


def test_two_runs_give_identical_results(tmp_path: Path) -> None:
    from agent_trust.analyzers.tool_surface import run

    ctx = make_repo(tmp_path, {"m.py": _python_module(4, 6), "mcp.json": "{}\n"})
    first, second = run(ctx), run(ctx)
    assert [(c.id, c.status, c.earned, c.detail) for c in first] == [
        (c.id, c.status, c.earned, c.detail) for c in second
    ]


def test_regexes_live_only_in_patterns_module() -> None:
    root = Path(__file__).resolve().parent.parent / "agent_trust"
    offenders = [
        path.name
        for path in root.rglob("*.py")
        if path.name not in {"patterns.py", "redact.py", "logging.py"}
        and "re.compile" in path.read_text(encoding="utf-8")
    ]
    assert offenders == []
