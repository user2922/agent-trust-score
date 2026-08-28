"""Tool Surface -- can an agent call this code through typed, documented interfaces?

The question behind the axis: does an agent reach this project through a schema
and an entry point, or by screen-scraping source and guessing at shell commands?

Detection is structural and deterministic. Nothing here consults a model.
"""

from __future__ import annotations

import ast
from collections.abc import Sequence

from agent_trust.analyzers import (
    CheckSpec,
    assert_weights,
    evidence_for_path,
    register,
    result,
    searched,
)
from agent_trust.analyzers import patterns as p
from agent_trust.inventory import RepoContext
from agent_trust.models import AxisKey, CheckResult, CheckStatus

AXIS = AxisKey.TOOL_SURFACE

TS_01 = CheckSpec("TS-01", "MCP server declared", 20)
TS_02 = CheckSpec("TS-02", "Machine-readable API schema", 20)
TS_03 = CheckSpec("TS-03", "CLI entry point declared", 15)
TS_04 = CheckSpec("TS-04", "Entry points documented", 10)
TS_05 = CheckSpec("TS-05", "Typed public boundaries", 15)
TS_06 = CheckSpec("TS-06", "Parseable package manifest", 10)
TS_07 = CheckSpec("TS-07", "Documented config contract", 10)

SPECS = (TS_01, TS_02, TS_03, TS_04, TS_05, TS_06, TS_07)
assert_weights(AXIS, SPECS)

# TS-05 thresholds, from SPEC.md.
TYPED_PASS_RATIO = 0.60
TYPED_PARTIAL_RATIO = 0.30
# Sample cap: sorted, so the sample is the same on every run.
TYPED_SAMPLE_FILES = 60

DOC_PATHS = ("readme.md", "readme.rst", "readme.txt", "usage.md", "cli.md")


def _dependencies(ctx: RepoContext) -> set[str]:
    """Every declared dependency name, from either manifest."""
    names: set[str] = set()
    if ctx.package_json:
        for field in ("dependencies", "devDependencies", "peerDependencies"):
            section = ctx.package_json.get(field)
            if isinstance(section, dict):
                names.update(str(k) for k in section)
    if ctx.pyproject:
        project = ctx.pyproject.get("project")
        if isinstance(project, dict):
            for entry in project.get("dependencies") or []:
                # "typer==0.27.2" -> "typer"
                names.add(
                    str(entry).split("[")[0].split("=")[0].split(">")[0].split("<")[0].strip()
                )
    return names


def check_mcp_server(ctx: RepoContext) -> CheckResult:
    """TS-01: a manifest, a dependency, or a server construction call."""
    manifests = ctx.paths_named(*p.MCP_MANIFEST_NAMES)
    if manifests:
        return result(
            TS_01,
            CheckStatus.PASS,
            f"Found {manifests[0]}.",
            [evidence_for_path(manifests[0], "mcp_manifest")],
        )

    declared = _dependencies(ctx) & set(p.MCP_DEPENDENCIES)
    if declared:
        return result(TS_01, CheckStatus.PASS, f"Declares the {sorted(declared)[0]} SDK.")

    for path in ctx.paths_with_suffix(".py", ".ts", ".js", ".tsx"):
        for number, line in enumerate(ctx.read_lines(path), start=1):
            match = p.MCP_CONSTRUCTION.search(line)
            if match:
                return result(
                    TS_01,
                    CheckStatus.PASS,
                    f"Constructs an MCP server in {path}.",
                    [evidence_for_path(f"{path}:{number}", "mcp_construction")],
                )

    return result(
        TS_01,
        CheckStatus.FAIL,
        searched("mcp.json", "an mcp SDK dependency", "a FastMCP/MCPServer construction"),
    )


def check_api_schema(ctx: RepoContext) -> CheckResult:
    """TS-02: OpenAPI, Swagger, GraphQL or protobuf."""
    found = ctx.paths_named(*p.API_SCHEMA_NAMES) or ctx.paths_with_suffix(*p.API_SCHEMA_SUFFIXES)
    if found:
        return result(
            TS_02,
            CheckStatus.PASS,
            f"Found {found[0]}.",
            [evidence_for_path(found[0], "api_schema")],
        )
    return result(TS_02, CheckStatus.FAIL, searched("openapi/swagger", "*.graphql", "*.proto"))


def check_cli_entry_point(ctx: RepoContext) -> CheckResult:
    """TS-03: a declared console script, or a CLI framework in use."""
    if ctx.pyproject:
        scripts = ctx.pyproject.get("project", {}).get("scripts")
        if isinstance(scripts, dict) and scripts:
            return result(
                TS_03,
                CheckStatus.PASS,
                f"pyproject declares {sorted(scripts)[0]}.",
                [evidence_for_path("pyproject.toml", "project_scripts")],
            )
    if ctx.package_json and ctx.package_json.get("bin"):
        return result(
            TS_03,
            CheckStatus.PASS,
            "package.json declares a bin entry.",
            [evidence_for_path("package.json", "package_bin")],
        )

    for path in ctx.paths_with_suffix(".py", ".ts", ".js"):
        if p.CLI_FRAMEWORK_IMPORT.search(ctx.read_text(path)):
            return result(
                TS_03,
                CheckStatus.PASS,
                f"Uses a CLI framework in {path}.",
                [evidence_for_path(path, "cli_framework")],
            )

    return result(
        TS_03,
        CheckStatus.FAIL,
        searched("[project.scripts]", "package.json bin", "a CLI framework"),
    )


def check_entry_points_documented(ctx: RepoContext) -> CheckResult:
    """TS-04: a usage block showing a real invocation with flags."""
    docs = [
        path for path in ctx.files if path.lower() in DOC_PATHS or path.lower().startswith("docs/")
    ]
    for path in docs:
        text = ctx.read_text(path)
        if p.USAGE_HELP.search(text) or p.USAGE_INVOCATION.search(text):
            return result(
                TS_04,
                CheckStatus.PASS,
                f"{path} shows an invocation with flags.",
                [evidence_for_path(path, "usage_block")],
            )
    return result(TS_04, CheckStatus.FAIL, searched("a documented invocation carrying a flag"))


def _annotation_ratio(ctx: RepoContext) -> tuple[int, int]:
    """(annotated, total) public defs across a deterministic sample."""
    annotated = total = 0
    for path in ctx.paths_with_suffix(".py")[:TYPED_SAMPLE_FILES]:
        try:
            tree = ast.parse(ctx.read_text(path))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            if node.name.startswith("_"):
                continue
            total += 1
            args = [*node.args.args, *node.args.kwonlyargs, *node.args.posonlyargs]
            arguments = [a for a in args if a.arg not in ("self", "cls")]
            if node.returns is not None and all(a.annotation is not None for a in arguments):
                annotated += 1
    return annotated, total


def check_typed_boundaries(ctx: RepoContext) -> CheckResult:
    """TS-05: TypeScript strict mode, or annotated Python public functions."""
    if ctx.has_javascript:
        for path in ctx.paths_named("tsconfig.json"):
            if p.TSCONFIG_STRICT.search(ctx.read_text(path)):
                return result(
                    TS_05,
                    CheckStatus.PASS,
                    f"{path} sets strict.",
                    [evidence_for_path(path, "tsconfig_strict")],
                )

    if ctx.has_python:
        annotated, total = _annotation_ratio(ctx)
        if total:
            ratio = annotated / total
            detail = f"{annotated} of {total} public functions annotated ({ratio:.0%})."
            if ratio >= TYPED_PASS_RATIO:
                return result(TS_05, CheckStatus.PASS, detail)
            if ratio >= TYPED_PARTIAL_RATIO:
                return result(TS_05, CheckStatus.PARTIAL, detail)
            return result(TS_05, CheckStatus.FAIL, detail)

    if ctx.has_javascript:
        return result(TS_05, CheckStatus.FAIL, searched("tsconfig.json with strict: true"))

    return result(
        TS_05,
        CheckStatus.NOT_APPLICABLE,
        "Needs Python or TypeScript; this build analyzes no other language deeply.",
    )


def check_manifest_parses(ctx: RepoContext) -> CheckResult:
    """TS-06: a package manifest that is present and parses."""
    declared = ctx.paths_named("pyproject.toml", "package.json")
    if not declared:
        return result(TS_06, CheckStatus.FAIL, searched("pyproject.toml", "package.json"))
    if ctx.pyproject is not None or ctx.package_json is not None:
        return result(
            TS_06,
            CheckStatus.PASS,
            f"Parsed {declared[0]}.",
            [evidence_for_path(declared[0], "manifest")],
        )
    return result(
        TS_06,
        CheckStatus.FAIL,
        f"{declared[0]} is present but does not parse.",
        [evidence_for_path(declared[0], "manifest_unparseable")],
    )


def check_config_contract(ctx: RepoContext) -> CheckResult:
    """TS-07: an env example file, or a settings schema."""
    examples = ctx.paths_named(*p.ENV_EXAMPLE_NAMES)
    if examples:
        return result(
            TS_07,
            CheckStatus.PASS,
            f"Found {examples[0]}.",
            [evidence_for_path(examples[0], "env_example")],
        )

    for path in ctx.paths_with_suffix(".py", ".ts", ".js"):
        if p.CONFIG_SCHEMA.search(ctx.read_text(path)):
            return result(
                TS_07,
                CheckStatus.PASS,
                f"Declares a settings schema in {path}.",
                [evidence_for_path(path, "config_schema")],
            )

    return result(TS_07, CheckStatus.FAIL, searched(".env.example", "a settings schema"))


CHECKS = (
    check_mcp_server,
    check_api_schema,
    check_cli_entry_point,
    check_entry_points_documented,
    check_typed_boundaries,
    check_manifest_parses,
    check_config_contract,
)


def run(ctx: RepoContext) -> Sequence[CheckResult]:
    """Run every Tool Surface check, in spec order."""
    return [check(ctx) for check in CHECKS]


register(AXIS, run)
