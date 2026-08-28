"""Every regex in the build lives here.

One home means one place to audit when a detector is too loose or too strict,
and it keeps `re.compile` out of the analyzers -- a test asserts that. Each
pattern names the check id that uses it, so a pattern with no owner is visible.
"""

from __future__ import annotations

import re

# ── TS-01 · MCP server declared ─────────────────────────────────────────────

MCP_MANIFEST_NAMES = ("mcp.json", ".mcp.json", "mcp.config.json")
MCP_DEPENDENCIES = ("mcp", "@modelcontextprotocol/sdk", "modelcontextprotocol")
# Both SDK generations: FastMCP was renamed MCPServer in mcp 2.x.
MCP_CONSTRUCTION = re.compile(r"\b(FastMCP|MCPServer|McpServer|Server)\s*\(")

# ── TS-02 · machine-readable API schema ─────────────────────────────────────

API_SCHEMA_NAMES = (
    "openapi.json",
    "openapi.yaml",
    "openapi.yml",
    "swagger.json",
    "swagger.yaml",
    "swagger.yml",
    "schema.graphql",
    "api.graphql",
)
API_SCHEMA_SUFFIXES = (".graphql", ".gql", ".proto")

# TS-02 only applies to a repo that actually serves an API. Asking a CLI or a
# library for an OpenAPI document is bad advice, not a finding, so absence of
# every signal below makes the check not_applicable rather than a failure.
WEB_FRAMEWORK_DEPENDENCIES = frozenset(
    {
        "fastapi",
        "flask",
        "django",
        "starlette",
        "sanic",
        "falcon",
        "bottle",
        "tornado",
        "aiohttp",
        "quart",
        "connexion",
        "strawberry-graphql",
        "graphene",
        "ariadne",
        "grpcio",
        "uvicorn",
        "gunicorn",
        "hypercorn",
        "express",
        "koa",
        "fastify",
        "@hapi/hapi",
        "@nestjs/core",
        "next",
        "apollo-server",
        "@apollo/server",
        "graphql-yoga",
        "restify",
        "h3",
    }
)
WEB_SERVER_SOURCE = re.compile(
    r"(?:FastAPI\s*\(|Flask\s*\(|express\s*\(|createServer\s*\("
    r"|@app\.(?:get|post|put|patch|delete|route)"
    r"|(?:app|router)\.(?:get|post|put|patch|delete)\s*\(\s*['\"]/"
    r"|app\.listen\s*\(|urlpatterns\s*=|ApolloServer\s*\()"
)

# ── TS-03 · CLI entry point ─────────────────────────────────────────────────

CLI_FRAMEWORK_IMPORT = re.compile(
    r"^\s*(?:import\s+(?:argparse|typer|click)\b"
    r"|from\s+(?:argparse|typer|click)\s+import\b"
    r"|(?:const|let|var|import)\s+.*\brequire\(['\"](?:commander|yargs)['\"]\)"
    r"|import\s+.*\bfrom\s+['\"](?:commander|yargs)['\"])",
    re.MULTILINE,
)

# ── TS-04 · entry points documented ─────────────────────────────────────────

# A usage block: a command invocation carrying at least one flag, or --help.
USAGE_INVOCATION = re.compile(
    r"(?:^|\n)\s*(?:\$\s*)?[\w./-]+(?:\s+[\w./=-]+)*\s+--[a-z][\w-]+", re.MULTILINE
)
USAGE_HELP = re.compile(r"--help\b")

# ── TS-05 · typed public boundaries ─────────────────────────────────────────

TSCONFIG_STRICT = re.compile(r'"strict"\s*:\s*true')

# ── TS-07 · documented config contract ──────────────────────────────────────

ENV_EXAMPLE_NAMES = (".env.example", ".env.sample", ".env.template", "env.example")
# A settings/config object rather than scattered environment reads.
CONFIG_SCHEMA = re.compile(
    r"\b(?:BaseSettings|SettingsConfigDict|createEnv|envSchema|z\.object\s*\(\s*\{[^}]*process\.env)",
)

# ── BR-01 · committed secrets ───────────────────────────────────────────────
#
# Provider patterns first: a well-formed AWS key is a hit regardless of entropy.
# The generic rule below is the only one that consults entropy, because it is
# the only one that cannot tell a credential from a sentence by shape alone.

SECRET_PROVIDERS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("aws_access_key_id", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("github_token", re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}")),
    ("stripe_live_key", re.compile(r"sk_live_[A-Za-z0-9]{20,}")),
    ("slack_token", re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}")),
    ("google_api_key", re.compile(r"AIza[0-9A-Za-z_\-]{35}")),
    ("anthropic_key", re.compile(r"sk-ant-[A-Za-z0-9_\-]{32,}")),
    ("openai_key", re.compile(r"sk-[A-Za-z0-9]{32,}")),
    ("private_key_block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("json_web_token", re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{5,}")),
)

# name = "value" where the name looks like a credential and the value is long.
SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(?P<name>[A-Za-z0-9_.\-]*"
    r"(?:secret|token|password|passwd|api_?key|access_?key|private_?key|credential)"
    r"[A-Za-z0-9_.\-]*)\s*[:=]\s*"
    r"[\"'`](?P<value>[^\"'`\n]{20,})[\"'`]"
)

# Paths whose contents are examples by construction.
SECRET_ALLOWLIST_PATHS = (
    ".example",
    ".sample",
    ".template",
    ".dist",
    "/tests/",
    "/test/",
    "/fixtures/",
    "/__mocks__/",
    "/docs/",
    "/examples/",
    ".snap",
)
SECRET_ALLOWLIST_PATH_PREFIXES = ("tests/", "test/", "fixtures/", "docs/", "examples/")

# Values that announce themselves as placeholders.
SECRET_ALLOWLIST_VALUES = re.compile(
    r"(?i)(example|placeholder|changeme|change_me|your[_-]?|dummy|foobar|xxxx|0000|"
    r"sk_test_|pk_test_|not[_-]?a[_-]?real|redacted|sample|<|\{\{|\$\{|process\.env|os\.environ|"
    r"getenv|todo|insert|replace[_-]?me|\.\.\.)"
)

# ── BR-02 / BR-03 · env files and gitignore ─────────────────────────────────

TRACKED_ENV_NAMES = (".env", ".env.local", ".env.production", ".env.prod", ".env.development")

GITIGNORE_ENV = re.compile(r"^\s*\.?\*?\.?env", re.MULTILINE | re.IGNORECASE)
GITIGNORE_KEYS = re.compile(
    r"(?i)^\s*\*?\.?(pem|key|p12|pfx|keystore|credentials?)\b", re.MULTILINE
)
GITIGNORE_BUILD = re.compile(
    r"(?i)^\s*/?(dist|build|node_modules|target|\.venv|venv|__pycache__|coverage)\b", re.MULTILINE
)
