# CLAUDE.md — Agent Trust Score

Read this, `SPEC.md`, and `BUILD_STATUS.md` before touching any file. These rules
apply to every file, every function and every prompt in this build.

`SPEC.md` is canonical. `SPEC_DRAFT.md` is provenance only — when they disagree,
`SPEC.md` wins.

---

## Project identifiers — never restate, always reference

| Thing | Value |
|---|---|
| Python | 3.12 |
| Package | `agent-trust-score` |
| Module | `agent_trust` |
| Console scripts | `agent-trust`, `agent-trust-mcp` |
| Model id | `claude-opus-5`, read from `AGENT_TRUST_LLM_MODEL` |
| Schema version | `1.0` |

## Pinned stack

**`pyproject.toml` is authoritative.** These are what Prompt 2a resolved against
the index; every version written from memory beforehand was wrong except
`anthropic`:

Python 3.12 · uv 0.12.7 · Typer 0.27.2 · Rich 15.0.0 · Pydantic 2.13.4 ·
`mcp` **2.1.1 (2.x — `FastMCP` is `MCPServer` from `mcp.server.mcpserver`)** ·
`anthropic` 1.2.0 · Jinja2 3.1.6 · pytest 9.1.1 + pytest-cov · ruff 0.16.5 ·
mypy 2.3.1 (strict) · cryptography 46.0.3 (newest with a win_arm64 wheel) ·
GitHub Actions. Git is invoked as a subprocess; no GitPython. No web framework,
no database, no auth, no payments.

`black` is installed as an emergency formatter only. `ruff format` is the single
formatting authority; the two disagree on implicit string concatenation, so
never run both as gates.

---

## The four project non-negotiables

**D — Determinism.** Analyzers and scoring are pure functions of the repo
contents. The same commit SHA yields byte-identical scores, findings and
ordering, with and without the LLM. Nothing in the scoring path reads the clock,
the network, a random seed, or a dict iteration order it did not sort.

Determinism is asserted over `Report.stable_payload()` — the report minus
`generated_at`, `run_ms` and `LlmUsage`. Those three vary by design; everything
else must not.

**X — No execution.** The tool never runs the audited repo's code. No dependency
install, no build, no test run, no git hooks. Clone with
`-c core.hooksPath=/dev/null`. Reading and parsing only.

**R — Redaction.** A matched secret is truncated to its first 4 and last 2
characters at the moment of capture, inside `redact.py`, before it enters any
object. Nothing downstream may see the full value — not the report, the cache,
the LLM prompt, stdout, the HTML page, or a log line.

**B — The LLM writes prose, never numbers.** Enrichment merges by id into
`explanation` and `fix_steps` only. A failed, refused, malformed or absent
response degrades to templates and changes no score, status, severity or
ordering. The merge asserts this; it is enforcement, not a comment.

## Module ownership — one home per concern

| Concern | Sole owner | Consequence |
|---|---|---|
| Every regex over repo content | `analyzers/patterns.py` | `re.compile` appears nowhere else |
| Every secret value | `redact.py` | No other module sees an unredacted match |
| Every `os.environ` read | `config.py` | Nothing else reads the environment |
| Grade band boundaries | `scoring/grades.py` | No band number lives anywhere else |
| Axis order and weights | `AXES` in `models.py` | Every list, table and section follows it |
| Effort and points per check | `scoring/effort.py` | Data, never estimated at runtime |
| Report shapes | `models.py` | No prompt redefines a field |

## The 37 checks — the single source of truth

Weights sum to 100 per axis; each analyzer asserts its own sum at import time.

**Tool Surface (7):** TS-01 MCP server declared 20 · TS-02 machine-readable API schema 20 (N/A when the repo serves no API) · TS-03 CLI entry point declared 15 · TS-04 entry points documented 10
· TS-05 typed public boundaries 15 · TS-06 parseable package manifest 10 ·
TS-07 documented config contract 10

**Blast Radius (7):** BR-01 no committed secrets 30 · BR-02 `.env` not tracked
12 · BR-03 `.gitignore` covers sensitive paths 8 · BR-04 destructive ops guarded
20 · BR-05 no admin credential in reachable code 15 · BR-06 side effects behind
a test/env switch 10 · BR-07 ownership/protection config 5

**Verifiability (8):** VF-01 test suite exists 20 · VF-02 test runner declared
15 · VF-03 test density 15 · VF-04 CI config present 15 · VF-05 CI actually runs
tests 15 · VF-06 type checking configured 10 · VF-07 lint configured 5 · VF-08
commit-time gate 5

**Context Quality (8):** CQ-01 agent instruction file exists 20 · CQ-02 README
with substance 10 · CQ-03 setup commands 15 · CQ-04 architecture summary 15 ·
CQ-05 run/test commands 15 · CQ-06 conventions stated 10 · CQ-07 do-not-touch
list 10 · CQ-08 docs resolve to reality 5

**Observability (7):** OB-01 structured logging 25 · OB-02 logging over printing
10 · OB-03 error reporting wired 20 · OB-04 audit trail pattern 15 · OB-05
commit hygiene 15 · OB-06 changelog 5 · OB-07 liveness surface 10

---

## Standing rules, adapted

The 16 Phase-Zero non-negotiables are written for a web SaaS. A rule marked N/A
with a reason is a decision; a rule silently missing is a gap.

**Applies as written.** Rule 1 — no secrets in code, `.env.example` holds
placeholder names only. Rule 2 — validate env at startup in `config.py`; a
malformed value fails fast naming the variable; nothing else reads `os.environ`.
Rule 5 — generic message to the caller, detail to the log, never a traceback.
Rule 9 — no placeholder code, no `TODO`, no stub functions, no mock data in a
real path. Rule 14 — model id from the env var, never a literal; a
model-not-found 404 raises a deprecation error naming the configured id. Rule 15
— record input tokens, output tokens and USD cost on every audit. Rule 16 — the
same code runs any environment purely on its env values.

**Applies, restated.** Rule 4 — the Anthropic call is the paid API. It needs a
wall-clock timeout, a per-run token ceiling, and content-addressed caching keyed
on commit SHA + schema version, so the same commit is never billed twice.

**N/A, with the reason.** Rule 3 (RLS) — no database. Rules 6, 7, 10, 12 (auth,
CSRF, server-side auth routes) — no HTTP server and no accounts; input validation
survives as Pydantic on every CLI flag and MCP argument. Rule 8 (webhook
idempotency) — no webhooks. Rule 11 (double-submit) — no forms. Rule 13 (legal
for monetization) — not monetized; a LICENSE and `docs/PRIVACY.md` still ship in
Prompt 15.

## Never claim more than the tool does

This product grades structure. It is not a security audit, it certifies nothing,
and it guarantees nothing. No README line, report string, or terminal message
may say otherwise. A passing grade is evidence about a repo's shape, and saying
more than that is the one failure mode that would make the whole thing worthless.

## What a report must never contain

An unredacted secret · an absolute path outside the audited repo · a traceback ·
any repo content beyond a 200-character redacted snippet.

## Working agreement

- One build prompt per session. Run its checkpoint before advancing. Commit
  after each phase so a bad one is cheap to undo.
- Ask for the simpler way before accepting an approach, and take it unless it
  breaks a non-negotiable.
- Read the actual output before hypothesizing about a failure. A regex over the
  source is a proxy signal, not ground truth.
- Prove a gate can fail before trusting it. A detector nobody has watched go red
  is decoration.

---

## Setup

```
uv sync --extra dev
```

Python 3.12 and git must already be on PATH. No API key is needed: without
`ANTHROPIC_API_KEY` the tool runs in template mode and says so.

## Run and test

```
uv run agent-trust . --no-llm        # grade this repo
uv run agent-trust <url> --format html --out reports
uv run agent-trust-mcp               # serve over MCP stdio

uv run python -m pytest              # the test suite
bash scripts/check_all.sh            # every gate, in order
```

`scripts/check_all.sh` is the single gate implementation; the Makefile delegates
to it. A tool it cannot execute is reported BLOCKED and exits 2 — never a pass.

## Architecture

```
agent_trust/
  cli.py            Typer app          -- thin adapter over pipeline.audit
  mcp_server.py     MCP stdio server   -- the other thin adapter (mcp 2.x)
  pipeline.py       acquire -> inventory -> analyzers -> score -> enrich -> render
  cache.py          content-addressed by commit SHA + schema version
  config.py         the only reader of os.environ
  models.py         every shape; AXES is the ordering authority
  redact.py         the only module that touches a secret value
  acquire.py        clone/resolve; never executes repository code
  inventory.py      git ls-files, skip rules, budgets -> RepoContext
  analyzers/        one module per axis; patterns.py owns every regex
  scoring/          grades.py owns the bands; effort.py is data, not estimates
  render/           terminal, markdown, html -- none of them computes a number
docs/               FILE_LIST.md, and the generated CHECKS.md
tests/              one test module per analyzer, plus fixtures/
```

## Do not touch

- `tests/fixtures/report.golden.md`, `report.golden.html`, `golden_report.json` —
  regenerate them from `tests/golden.py` rather than hand-editing; a manual edit
  makes the render tests assert whatever was typed.
- `uv.lock` — regenerate with `uv lock`, never edit by hand.
- `docs/CHECKS.md` — generated from the CheckSpec tables (Prompt 15).
- `tests/test_analyzers_secrets.py` fixture values — they must stay real-shaped
  and marker-free or the detector tests stop proving anything. This is the one
  file excluded from the repo's own secret scan.
