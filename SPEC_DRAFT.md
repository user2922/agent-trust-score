# Agent Trust Score — App Specification

> Spec draft v1.0 (2026-08-28). Input to `/gauntlet:build`, which produces
> BUILD.md, CLAUDE.md and the canonical SPEC.md. Working title: **Agent Trust
> Score**; alt name **Blast Radius** (kept as the name of axis 2 either way).

## Overview

| Field | Value |
|---|---|
| Name | Agent Trust Score |
| CLI binary | `agent-trust` |
| Package name | `agent-trust-score` |
| Python module | `agent_trust` |
| Description | Scores any git repository on how safely an autonomous coding agent can operate inside it, and emits a graded report with prioritized fixes |
| Target user | Engineering lead or solo founder about to point Claude Code / Codex / Antigravity / an ADK agent at a repo. Secondary: hackathon judges evaluating whether a submission is real |
| Platform | Local CLI + MCP stdio server + static HTML report |
| Build context | Hackathon build — no auth, no database, no billing, no hosted backend |
| Distribution | `uvx agent-trust-score <repo>` / `pipx install agent-trust-score` |

**Problem.** Teams are handing agents write access to codebases designed for
humans. Nothing tells them whether that is safe. A repo with secrets in config,
no tests, undocumented side effects and no callable interfaces will produce
confident, destructive agent behavior. Linters check code quality; nothing
checks agent-operability.

**One-liner.** A CLI and MCP server that grades a repo on agent-operability and
tells you what to fix first.

## Tech Stack

| Layer | Technology | Version (pinned) |
|---|---|---|
| Language | Python | 3.12 |
| Package/dep manager | uv | 0.12.7 (installed) |
| CLI framework | Typer | 0.15.1 |
| Terminal output | Rich | 13.9.4 |
| Schema/validation | Pydantic | 2.10.4 |
| MCP server | `mcp` (official Python SDK) | 1.2.0 |
| LLM | Anthropic SDK (`anthropic`) | 1.x |
| Model | `claude-opus-5` | — |
| Templating (md + html) | Jinja2 | 3.1.5 |
| Git access | `git` subprocess (no GitPython) | system |
| Tests | pytest + pytest-cov | 8.3.4 |
| Lint | ruff | 0.9.x |
| Types | mypy (strict) | 1.14.x |
| CI | GitHub Actions | — |

No web framework. No database. No auth. No payments. State is the filesystem
cache only.

## Non-Goals

- Never executes the repo's code — no `npm install`, no `pip install`, no test
  runs, no build steps, no git hooks (clone with `core.hooksPath=/dev/null`).
- Not a general code-quality scorer. Not a SAST tool. Not a linter.
- No language-specific deep analysis beyond **JavaScript/TypeScript and Python**
  for this build. Other languages are inventoried and scored on the
  language-agnostic checks only, with `not_applicable` on the rest.
- No hosted service, no accounts, no telemetry.
- No auto-applied fixes. `--fix` writes suggested patches to disk; it never
  commits, never pushes, and never edits the audited repo in place.

## Scoring Model

Five axes, equal weight (20% each) unless overridden by `--axis`.

| Key | Name | Question it answers |
|---|---|---|
| `tool_surface` | Tool Surface | Can an agent call this code through typed, documented interfaces? |
| `blast_radius` | Blast Radius | What can go wrong if the agent acts? |
| `verifiability` | Verifiability | Can the agent prove it didn't break anything? |
| `context_quality` | Context Quality | Does the repo explain itself to an agent? |
| `observability` | Observability | Can a human see what the agent did afterward? |

### Check result model

Every check returns exactly one of `pass` / `partial` / `fail` / `not_applicable`.

- `pass` earns the full weight, `partial` earns `weight * 0.5`, `fail` earns 0.
- `not_applicable` is removed from both numerator and denominator.
- Axis score = `round(100 * sum(earned) / sum(weight of applicable checks))`.
- If every check on an axis is `not_applicable`, the axis score is `null`, its
  letter is `N/A`, and it is dropped from the overall mean.

### Grade bands (single source of truth)

| Letter | Score |
|---|---|
| A | 90–100 |
| B | 80–89 |
| C | 70–79 |
| D | 60–69 |
| F | 0–59 |

### Overall score

1. `mean = round(sum(axis scores) / count(scored axes))`
2. **Cap rule:** if any scored axis is below **40**, `overall = min(mean, 70)`
   and `capped = true` with `cap_reason` naming the axis. A repo with committed
   secrets is never "agent-ready".
3. **Secret rule:** any `high`-severity finding on check `BR-01` forces
   `blast_radius <= 39`, which in turn triggers the cap rule above.
4. Letter is derived from the final capped score using the bands above.

### Axis 1 — Tool Surface (checks total 100)

| ID | Check | Weight | Passes when |
|---|---|---|---|
| TS-01 | MCP server declared | 20 | `.mcp.json` / `mcp.json` present, or a dep on `mcp` / `@modelcontextprotocol/sdk`, or a `FastMCP(` / `Server(` construction |
| TS-02 | Machine-readable API schema | 20 | `openapi.{json,yaml,yml}`, `swagger.*`, `*.graphql`, `schema.graphql`, or `*.proto` present |
| TS-03 | CLI entry point declared | 15 | `[project.scripts]` in pyproject, `"bin"` in package.json, or an argparse / typer / click / commander / yargs import |
| TS-04 | Entry points documented | 10 | README or docs contain a usage block showing an invocation with flags or `--help` |
| TS-05 | Typed public boundaries | 15 | TS: `tsconfig.json` with `"strict": true`. PY: >=60% of public defs in sampled source files carry annotations (partial at >=30%) |
| TS-06 | Parseable package manifest | 10 | `package.json` or `pyproject.toml` present and parses |
| TS-07 | Documented config contract | 10 | `.env.example`, `.env.sample`, or a config schema / settings model |

### Axis 2 — Blast Radius (checks total 100)

| ID | Check | Weight | Passes when |
|---|---|---|---|
| BR-01 | No committed secrets | 30 | Zero non-allowlisted secret matches in tracked files. **Fail forces axis <= 39** |
| BR-02 | `.env` not tracked | 12 | No `.env`, `.env.local`, `.env.production` in `git ls-files` |
| BR-03 | `.gitignore` covers sensitive paths | 8 | `.gitignore` exists and matches `.env`, key/credential and build-artifact patterns (partial if it exists but misses some) |
| BR-04 | Destructive ops guarded | 20 | Every detected destructive operation has a guard within 30 lines: `--dry-run`, `dry_run`, a confirmation prompt, an `os.environ` / `process.env` gate, or a required `--force`. Partial if some are guarded |
| BR-05 | No admin credential in reachable code | 15 | No `service_role`, `SUPABASE_SERVICE_ROLE_KEY`, `sk_live_`, or root/admin token referenced from client- or browser-reachable paths |
| BR-06 | Side effects behind a test/env switch | 10 | Payment, email and outbound-webhook calls sit behind an env flag, a test-mode key, or an injected client |
| BR-07 | Ownership/protection config | 5 | `CODEOWNERS` present, or a branch-protection / ruleset config file |

**Destructive operation patterns (BR-04):** SQL `DROP` / `TRUNCATE` /
`DELETE FROM` without a `WHERE`; migration runners (`migrate deploy`, `db push`,
`alembic upgrade`); `rm -rf`; `shutil.rmtree`; `fs.rm(` with `recursive`; bulk
`.delete()` / `.deleteMany(` / `destroy_all`; `stripe.*.create` / `capture`;
`resend.emails.send` / `sendgrid` / `ses.send`; and `requests.post` / `fetch(`
to a non-localhost literal host inside a script entry point.

**Secret detection (BR-01).** Provider regexes for AWS access key ids, GitHub
tokens (`gh[pousr]_` + 36 chars), Stripe live keys (`sk_live_` + 20 chars),
Slack tokens (`xox[baprs]-`), Google API keys (`AIza` + 35 chars),
OpenAI/Anthropic keys (`sk-` / `sk-ant-` + 32 chars), PEM private-key headers,
and three-segment JWTs beginning `eyJ`. Plus one generic rule: an assignment to
a name matching secret / token / password / api_key / access_key / private_key
whose value is a literal of 20+ characters with Shannon entropy >= 4.0.

**Allowlist (must not fire — this is the zero-false-positives requirement):**
paths matching `*.example`, `*.sample`, `*.template`, `.env.example`,
`**/tests/**`, `**/test/**`, `**/fixtures/**`, `**/__mocks__/**`, `**/docs/**`,
lockfiles, `**/*.snap`; values containing `EXAMPLE`, `PLACEHOLDER`, `CHANGEME`,
`YOUR_`, `<`, `xxxx`, `0000`, `sk_test_`, `pk_test_`, `dummy`, `foobar`; and any
value that is itself an env-var reference (`${...}`, `process.env.`,
`os.environ`).

**Redaction is mandatory.** Evidence snippets show at most the first 4 and last
2 characters of a matched secret (`AKIA…7Q`). The full value never enters the
report, the cache, the LLM prompt, stdout, or the HTML page.

### Axis 3 — Verifiability (checks total 100)

| ID | Check | Weight | Passes when |
|---|---|---|---|
| VF-01 | Test suite exists | 20 | >=1 file matching `test_*.py`, `*_test.py`, `*.test.{ts,tsx,js}`, `*.spec.*`, or a `tests/` dir containing source files |
| VF-02 | Test runner declared | 15 | pytest / vitest / jest / mocha in deps, or a `test` script in package.json |
| VF-03 | Test density | 15 | test files / source files >= 0.20 (partial >= 0.10) |
| VF-04 | CI config present | 15 | `.github/workflows/*.yml`, `.gitlab-ci.yml`, `.circleci/config.yml`, or `azure-pipelines.yml` |
| VF-05 | CI actually runs tests | 15 | A CI job invokes the declared test runner (not just lint or build) |
| VF-06 | Type checking configured | 10 | `tsconfig.json` with `"strict": true`, or `[tool.mypy]` / `mypy.ini` / `pyrightconfig.json` |
| VF-07 | Lint configured | 5 | eslint / biome / ruff config present |
| VF-08 | Commit-time gate | 5 | `.pre-commit-config.yaml`, husky hooks, or lint-staged config |

### Axis 4 — Context Quality (checks total 100)

Agent doc = the first present of `CLAUDE.md`, `AGENTS.md`, `.cursorrules`,
`.github/copilot-instructions.md`. Sections are detected by heading text and
keyword patterns; the LLM never sets these scores.

| ID | Check | Weight | Passes when |
|---|---|---|---|
| CQ-01 | Agent instruction file exists | 20 | Agent doc present and non-empty |
| CQ-02 | README exists with substance | 10 | `README.md` present and >= 300 words (partial >= 100) |
| CQ-03 | Setup commands | 15 | A copy-pasteable install/setup command block in the agent doc or README |
| CQ-04 | Architecture summary | 15 | A directory map, component list, or data-flow section |
| CQ-05 | Run/test commands | 15 | Documented commands to run the app and to run the tests |
| CQ-06 | Conventions stated | 10 | A conventions / style / patterns section |
| CQ-07 | Do-not-touch list | 10 | An explicit "do not edit / generated / vendored" list |
| CQ-08 | Docs resolve to reality | 5 | >= 80% of file paths cited in the agent doc still exist (partial >= 50%) |

### Axis 5 — Observability (checks total 100)

| ID | Check | Weight | Passes when |
|---|---|---|---|
| OB-01 | Structured logging | 25 | structlog, `logging.config`, pino, winston, bunyan, or an OTel logs exporter |
| OB-02 | Logging over printing | 10 | logger calls >= print / console.log calls, outside tests and scripts |
| OB-03 | Error reporting wired | 20 | Sentry, Rollbar, Bugsnag, Honeybadger, or OpenTelemetry traces initialized |
| OB-04 | Audit trail pattern | 15 | An `audit_log` / `activity_log` / `events` table, an append-only writer, or an actor+action+timestamp record |
| OB-05 | Commit hygiene | 15 | >= 60% of the last 50 commit subjects are >= 15 chars and not a bare `wip` / `fix` / `update` / `asdf` (partial >= 40%) |
| OB-06 | Changelog | 5 | `CHANGELOG.md` or a releases directory |
| OB-07 | Liveness surface | 10 | A health/status endpoint, or the CLI exposes `--version` |

37 checks total — enough that the ugly fixture yields at least one true positive
per axis.

## Report Schema (Pydantic, `agent_trust/models.py`)

`SCHEMA_VERSION = "1.0"`. All models are `frozen=True`, `extra="forbid"`.

```
Report
  schema_version: str
  generated_at: datetime (UTC)
  run_ms: int
  repo: RepoInfo
  overall: Overall
  axes: list[AxisScore]        # always 5, in fixed order
  findings: list[Finding]
  fixes: list[Fix]
  llm: LlmUsage

RepoInfo    source (url|path), resolved_path, commit_sha, default_branch,
            file_count, analyzed_file_count, bytes_scanned,
            languages: dict[str, int], truncated: bool
Overall     score: int | None, letter: str, mean: int | None, capped: bool,
            cap_reason: str | None      # None score requires letter "N/A"
AxisScore   key, name, score: int | None, letter, weight: float,
            checks: list[CheckResult]
CheckResult id, title, status, weight: int, earned: float, detail: str,
            evidence: list[Evidence]
Evidence    path: str, line: int | None, snippet: str (redacted, <=200 chars),
            matcher: str
Finding     id, check_id, axis, severity (high|medium|low), title,
            evidence: list[Evidence], explanation: str,
            explanation_source (llm|template)
Fix         id, finding_ids: list[str], axis, title, steps: list[str],
            risk_reduction: int (points), effort_minutes: int,
            ratio: float, patch: str | None
LlmUsage    used: bool, model: str | None, input_tokens: int,
            output_tokens: int, cost_usd: float, fallback_reason: str | None
```

**Severity mapping (deterministic):** `high` = a failed check worth >= 20 points,
or any BR-01 hit; `medium` = a failed check worth 10–19; `low` = everything
else, including `partial` results.

**Fix ordering:** `ratio = risk_reduction / (effort_minutes / 60)`, descending;
ties broken by severity, then by axis order as listed above, then by check id.
`effort_minutes` comes from a fixed per-check table in
`agent_trust/scoring/effort.py` — never estimated by the LLM.

## Architecture

```
acquire  ->  inventory  ->  analyzers  ->  score  ->  enrich (LLM)  ->  render
```

1. **acquire** — a local path is used in place; a URL is cloned with
   `git clone --depth 1 --filter=blob:none -c core.hooksPath=/dev/null` into a
   temp dir that is removed on exit. Clone timeout 30s. Only `https://` and
   `git@` hosts on an allowlist of github.com, gitlab.com, bitbucket.org and
   codeberg.org; anything else requires `--allow-any-host`.
2. **inventory** — `git ls-files` for tracked paths; skip `node_modules/`,
   `.venv/`, `venv/`, `dist/`, `build/`, `vendor/`, `.git/`, `target/`,
   minified `*.min.*`, lockfiles, and any file over 1 MB or detected as binary.
   Hard caps: 20,000 files and 200 MB scanned. Exceeding either sets
   `repo.truncated = true`, which is stated in the report.
3. **analyzers** — one module per axis under `agent_trust/analyzers/`, each
   exporting `run(ctx: RepoContext) -> list[CheckResult]`. Pure functions over
   the file inventory: path globs, manifest parsing, regex with line numbers,
   `git log` metadata. **No LLM, no network, no code execution.**
4. **score** — `agent_trust/scoring/` applies weights, the cap rule and the
   secret rule. Deterministic: the same commit SHA always yields the same
   numbers.
5. **enrich** — a single Claude call that writes prose only.
6. **render** — Jinja2 templates to `report.md`, `report.html`, `report.json`.

**Determinism rule (standing, applies to every prompt in the build):** analyzers
and scoring must produce a complete, correct report with `--no-llm` and with no
`ANTHROPIC_API_KEY` set. The LLM adds explanations and fix text only; it can
never change a score, a status, a severity, or an ordering.

## LLM Pass

- One call per audit. Model `claude-opus-5`, `thinking: {"type": "adaptive"}`,
  `output_config: {"effort": "medium", "format": {...}}` with a structured-output
  schema, parsed via `client.messages.parse()` into the `Enrichment` model.
- **Input:** the frozen scored report JSON, up to 40 redacted evidence snippets
  (<= 200 chars each), and the agent doc plus README truncated to 6,000 tokens
  total. Prompt cap: 30,000 input tokens. The rubric and system prompt form a
  stable cached prefix (`cache_control: {"type": "ephemeral"}`).
- **Output:** `Enrichment { summary: str, explanations: dict[finding_id, str],
  fix_steps: dict[fix_id, list[str]] }`. Unknown ids are dropped; missing ids
  fall back to templates.
- **Judgment calls the LLM is allowed to make:** the wording of README /
  agent-doc quality commentary, and whether a flagged destructive operation
  looks genuinely guarded — recorded as `explanation` text and an advisory note,
  **not** as a score change.
- **Cost:** ~30k input + ~4k output at $5 / $25 per MTok ~= **$0.25 per audit**
  uncached, ~$0.10 with a cache hit on the prefix. `--no-llm` costs $0.
- **Failure handling:** timeout (20s), refusal, validation error, missing key or
  non-200 → templated explanations, `llm.used = false`, `llm.fallback_reason`
  set, exit code unchanged.

## CLI Surface

```
agent-trust <repo-url-or-path> [OPTIONS]
```

| Flag | Default | Behavior |
|---|---|---|
| `--axis KEY` (repeatable) | all five | Score only these axes; overall is the mean of those scored |
| `--format md\|json\|html` (repeatable) | `md` | Which report files to write |
| `--out DIR` | `.` | Output dir; writes `report.md` / `report.json` / `report.html` |
| `--fix` | off | Also write `fixes/` patch suggestions (draft files, never applied) |
| `--no-llm` | off | Skip the enrichment call entirely |
| `--min-grade LETTER` | none | Exit 2 if the overall letter is worse than this (CI gate) |
| `--allow-any-host` | off | Permit clone hosts outside the allowlist |
| `--timeout SECONDS` | 60 | Whole-run wall-clock budget |
| `--cache / --no-cache` | on | Reuse a cached report for the same commit SHA |
| `--quiet` | off | Suppress the terminal summary; still writes files |
| `--version` | — | Print version and exit |

Terminal output: a Rich table — overall grade, five axis rows with score and
letter, the top three fixes by ratio, and the report file paths.

**Exit codes:** `0` graded successfully · `1` operational error (clone failed,
not a git repo, timeout, unreadable path) · `2` graded but below `--min-grade`.

## MCP Server

`agent-trust-mcp` — stdio transport, registered in `[project.scripts]`.

| Tool | Signature | Returns |
|---|---|---|
| `audit_repo` | `(url: str, axes: list[str] \| None = None, use_llm: bool = True)` | Full `Report` JSON |
| `get_axis` | `(url: str, axis: str)` | One `AxisScore` JSON |
| `suggest_fixes` | `(url: str, max_items: int = 10)` | `list[Fix]` ordered by ratio |

Every tool has a typed schema derived from the Pydantic models, a docstring an
agent can act on, and a hard 90s cap. Errors return a structured
`{"error": {"code": ..., "message": ...}}` payload, never a raw traceback.
Cache: `~/.cache/agent-trust/<commit_sha>.json`, 24h TTL, so `get_axis` and
`suggest_fixes` after an `audit_repo` are instant.

## Environment Variables

```
# OPTIONAL — absent means the tool runs in --no-llm mode with a printed notice
ANTHROPIC_API_KEY

# OPTIONAL — tuning; all have defaults in agent_trust/config.py
AGENT_TRUST_CACHE_DIR=~/.cache/agent-trust
AGENT_TRUST_MAX_FILES=20000
AGENT_TRUST_MAX_BYTES=209715200
AGENT_TRUST_CLONE_TIMEOUT=30
AGENT_TRUST_LLM_TIMEOUT=20
AGENT_TRUST_LLM_MODEL=claude-opus-5
```

No secrets are ever written to the cache, the report, or the HTML page.

## File Layout

```
agent_trust/
  __init__.py            __version__ — single source of the version string
  cli.py                 Typer app
  mcp_server.py          stdio MCP server
  pipeline.py            the one audit() both surfaces call
  cache.py               content-addressed by commit SHA, atomic writes
  config.py              env parsing + defaults — the only reader of os.environ
  logging.py             JSON lines to stderr, redacted
  models.py              all Pydantic models + SCHEMA_VERSION + AXES
  errors.py              the exception hierarchy, each with a safe message
  redact.py              the only place a secret value is touched
  acquire.py             clone/resolve, temp-dir lifecycle, host allowlist
  limits.py              deadline + file/byte budgets
  inventory.py           git ls-files, skip rules, language detection, caps
  analyzers/
    __init__.py          registry + CheckSpec tables, AXES in fixed order
    tool_surface.py  blast_radius.py  verifiability.py
    context_quality.py  observability.py
    patterns.py          every regex, one place
    entropy.py           Shannon entropy for the generic secret rule only
  scoring/
    __init__.py  grades.py  findings.py  effort.py  fixes.py
  enrich.py              the single Claude call + Enrichment model + fallbacks
  render/
    markdown.py  html.py  terminal.py
    templates/report.md.j2  report.html.j2
docs/
  CHECKS.md              generated from the CheckSpec tables, never hand-typed
  PRIVACY.md             no telemetry; Anthropic is the only third party
tests/
  fixtures/clean-repo/   committed fixture — expected grade A or B
  fixtures/ugly-repo/    committed fixture — expected grade F, >=1 finding per axis
  test_analyzers_*.py  test_scoring.py  test_redact.py  test_cli.py  test_mcp.py
```

## Performance Budget

| Stage | Budget |
|---|---|
| clone (shallow, blobless) | <= 15s |
| inventory + analyzers | <= 20s |
| LLM enrichment | <= 20s |
| render | <= 1s |
| **total, mid-sized repo (<= 5,000 files)** | **< 60s p50** |
| `--no-llm` path | < 15s |

## Demo Plan

1. Two pre-cached reports ready on screen — one clean repo (A/B) and one ugly
   repo (F, capped, with the committed-secret finding visible and redacted).
2. A live run on a judge-supplied repo, invoked from Claude Code through the MCP
   server via `audit_repo`, then `suggest_fixes` for the top three.
3. The HTML report open beside the terminal.

## Success Criteria (hackathon definition of done)

- [ ] Runs end-to-end on three real public repos without a crash.
- [ ] MCP server responds to `audit_repo`, `get_axis` and `suggest_fixes` from
      Claude Code.
- [ ] On `tests/fixtures/ugly-repo/`, at least one true-positive finding on each
      of the five axes.
- [ ] On `tests/fixtures/clean-repo/`, **zero** secrets flagged.
- [ ] Same commit SHA → byte-identical scores across runs, with and without the
      LLM.
- [ ] `--no-llm` produces a complete report with no API key present.
- [ ] Under 60s on a mid-sized repo.
- [ ] No unredacted secret value appears in any output artifact.

## Stretch (only if time remains)

- `--fix` emits a draft `CLAUDE.md` and a `.gitignore` patch as unified diffs.
- A GitHub Action wrapper that comments the grade on PRs and fails on
  `--min-grade`.

## Build Phase Mapping

This is a CLI/MCP tool, not a SaaS. The build sequence's fixed core phases map
as follows; the build doc should replace rather than skip.

As built in `BUILD.md` (17 prompts). Scoring moved ahead of the renderers so the
CLI has something to render; that reorder is annotated in the build doc itself.

| Core phase | Becomes | Prompt |
|---|---|---|
| 1 Spec validation & setup | **Keep** — produces CLAUDE.md + SPEC.md | 1 |
| 2a Project setup | **Keep** — uv, pyproject, ruff, mypy strict, pytest, secret scanner | 2a |
| 2b Security utilities & foundation | **Replace** — redaction, host allowlist, temp-dir and symlink safety, no-execution rule, resource caps | 2b |
| 3 Database schema | **Replace** — `models.py`, the Pydantic Report schema and `AXES` | 3 |
| 4 Types & validation | **Replace** — `inventory.py` and `RepoContext`, the structure every analyzer reads | 4 |
| 5 Design system & UI | **Replace** — the scoring engine (moved up; the CLI cannot render without it) | 5 |
| 6 Authentication | **N/A** — no accounts. Input validation survives as Pydantic on every CLI flag and MCP argument | — |
| 6 (slot) | Renderers — Rich terminal, Jinja markdown and self-contained HTML | 6 |
| 7 Layout & navigation | **Replace** — `pipeline.py`, the CLI, the MCP server and the cache; walking skeleton runs here | 7 |
| 8–13 Features | The five axes — blast radius split across two prompts, as the heaviest | 8–13 |
| 14 (added) | The single LLM enrichment call and its fallbacks | 14 |
| Stripe | **N/A** — not monetized | — |
| Legal / GDPR | **Reduced** — LICENSE plus `docs/PRIVACY.md`: no telemetry, and repo content reaches the Anthropic API only when the LLM pass runs | 15 |
| Polish | Keep — folded into packaging and docs | 15 |
| Testing & CI/CD | Keep — both fixtures, a determinism test, a redaction test, a canary proving the secret scanner can fail, and a CI pipeline verified to have actually run | 16 |
