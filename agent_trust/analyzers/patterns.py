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

# ── BR-04 · destructive operations ──────────────────────────────────────────
#
# Each entry is (family, pattern). The family is what the finding calls the
# operation, so a user can tell what was matched without reading this file.

DESTRUCTIVE_OPS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("SQL DROP", re.compile(r"(?i)\bDROP\s+(?:TABLE|DATABASE|SCHEMA|INDEX)\b")),
    ("SQL TRUNCATE", re.compile(r"(?i)\bTRUNCATE\s+(?:TABLE\s+)?\w")),
    # DELETE FROM with no WHERE on the same statement.
    ("unqualified DELETE", re.compile(r"(?i)\bDELETE\s+FROM\s+[\w.\"'`]+\s*(?:;|$)")),
    (
        "migration runner",
        re.compile(
            # Separator class rather than \s+: these runners are usually invoked as an
            # argv list -- ["prisma", "migrate", "deploy"] -- not as a shell string.
            r"(?i)(?:migrate[\"',\s]+deploy|db[\"',\s]+push|alembic[\"',\s]+upgrade"
            r"|prisma[\"',\s]+migrate[\"',\s]+(?:deploy|reset)|django-admin[\"',\s]+migrate"
            r"|rails[\"',\s]+db:migrate|flyway[\"',\s]+migrate)"
        ),
    ),
    (
        "recursive delete",
        re.compile(
            r"(?:\brm\s+-[a-zA-Z]*[rR][a-zA-Z]*f|\brm\s+-[a-zA-Z]*f[a-zA-Z]*[rR]"
            r"|\bshutil\.rmtree\s*\(|\bfs\.rm(?:Sync)?\s*\([^)]*recursive\s*:\s*true"
            r"|\brimraf\s*\()"
        ),
    ),
    (
        "bulk delete",
        re.compile(
            r"\b(?:deleteMany\s*\(|destroy_all\b|\.delete_many\s*\(|objects\.all\(\)\.delete\s*\(\)"
            r"|\.truncate\s*\(\))"
        ),
    ),
    (
        "payment capture",
        re.compile(
            r"\b(?:stripe|Stripe)\.(?:charges|paymentIntents|PaymentIntent|Charge)\."
            r"(?:create|capture)\s*\(|\.refunds\.create\s*\("
        ),
    ),
    (
        "outbound email",
        re.compile(
            r"\b(?:resend\.emails\.send|sendgrid\.send|ses\.send_email|ses\.sendEmail"
            r"|mailgun\.messages\(\)\.send|smtp\.send_message|transporter\.sendMail)\s*\("
        ),
    ),
)

# A guard makes the operation deliberate rather than incidental.
DESTRUCTIVE_GUARDS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("dry-run flag", re.compile(r"(?i)\bdry[_-]?run\b")),
    ("force flag", re.compile(r"(?i)--force\b|\bforce\s*[:=]\s*(?:True|true)|\bargs\.force\b")),
    (
        "confirmation prompt",
        re.compile(
            r"(?i)\b(?:input\s*\(|confirm\s*\(|prompt\s*\(|typer\.confirm|click\.confirm"
            r"|readline\.question|are you sure)"
        ),
    ),
    (
        "environment gate",
        re.compile(
            r"(?i)(?:os\.environ|process\.env|getenv|settings\.|config\.)\w*\s*(?:\[|\.|==|!=|in\b)"
            r"|\bif\s+(?:not\s+)?(?:is_production|IS_PROD|NODE_ENV|ENVIRONMENT)\b"
        ),
    ),
)

GUARD_WINDOW_LINES = 30

# ── BR-05 · admin credentials in reachable code ─────────────────────────────

ADMIN_CREDENTIAL = re.compile(
    r"(?i)\b(?:SUPABASE_SERVICE_ROLE_KEY|service_role|SERVICE_ACCOUNT_KEY|ADMIN_API_KEY"
    r"|ROOT_PASSWORD|MASTER_KEY|sk_live_|SUPERUSER_|AWS_SECRET_ACCESS_KEY)\b"
)
# Reachability judged by path convention, and the finding says so.
CLIENT_REACHABLE_DIRS = (
    "client/",
    "public/",
    "www/",
    "static/",
    "browser/",
    "components/",
    "pages/",
    "app/components/",
    "src/components/",
    "src/pages/",
    "frontend/",
    "web/",
)
CLIENT_REACHABLE_SUFFIXES = (".jsx", ".tsx", ".vue", ".svelte")
CLIENT_FILE_MARKER = re.compile(r"(?i)(?:^|/)(?:client|browser|frontend)[.\-_]")

# ── BR-06 · side effects behind a switch ────────────────────────────────────

SIDE_EFFECT_CALL = re.compile(
    r"\b(?:stripe|Stripe)\.\w+\.(?:create|capture|charge)\s*\("
    r"|\b(?:resend\.emails\.send|sendgrid\.send|ses\.send_email|transporter\.sendMail)\s*\("
    r"|\bwebhook\w*\.(?:post|send|trigger)\s*\("
)
TEST_MODE_SWITCH = re.compile(
    r"(?i)\bsk_test_|\btest_mode\b|\bTESTING\b|\bMOCK\b|\bstub\b|\bsandbox\b"
    r"|(?:os\.environ|process\.env|getenv)"
)

# ── BR-07 · ownership and protection ────────────────────────────────────────

CODEOWNERS_PATHS = ("CODEOWNERS", ".github/CODEOWNERS", "docs/CODEOWNERS", ".gitlab/CODEOWNERS")
PROTECTION_CONFIG_NAMES = (
    "branch-protection.yml",
    "branch-protection.yaml",
    "rulesets.yml",
    ".mergify.yml",
    "renovate.json",
    ".github/settings.yml",
)
