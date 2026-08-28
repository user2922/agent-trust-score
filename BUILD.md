# Agent Trust Score — Build Document

Sequential build prompts. Paste one per session, run its checkpoint, commit, then
advance. Derived from `SPEC_DRAFT.md` in this folder.

**This is not a SaaS.** No accounts, no database, no payments. The core sequence
is adapted per the "Build Phase Mapping" section of `SPEC_DRAFT.md`, and every
substitution is stated below rather than silently dropped.

---

## App Specification

**Agent Trust Score** — a CLI and MCP server that scores any git repository on
how safely an autonomous coding agent can operate inside it, and emits a graded
report with prioritized fixes.

**Target user:** an engineering lead or solo founder about to point Claude Code,
Codex, Antigravity or an ADK agent at a repo. Secondary: hackathon judges
checking whether a submission is real.

**What a user can do:** grade a repo by URL or local path · read a graded report
(terminal, markdown, JSON, HTML) · get a fix list ordered by risk reduction per
hour · call the same audit from any agent host over MCP · gate CI on a minimum
grade.

**Tech stack (pinned):** Python 3.12 · uv 0.12.7 · Typer 0.15.1 · Rich 13.9.4 ·
Pydantic 2.10.4 · `mcp` 1.2.0 · `anthropic` 1.x · Jinja2 3.1.5 · pytest 8.3.4 ·
ruff 0.9.x · mypy 1.14.x (strict) · GitHub Actions. Git is invoked as a
subprocess; no GitPython.

**Package:** `agent-trust-score` · **module:** `agent_trust` · **console
scripts:** `agent-trust`, `agent-trust-mcp`.

**Scoring:** five axes at equal weight — `tool_surface`, `blast_radius`,
`verifiability`, `context_quality`, `observability` — 37 checks total
(TS-01..07, BR-01..07, VF-01..08, CQ-01..08, OB-01..07). Grade bands, the
below-40 cap rule and the committed-secret rule are defined once in `SPEC_DRAFT.md`
and restated nowhere else.

**AI:** yes, one call per audit — `claude-opus-5`, used for explanation prose
only. It can never change a score. Every path must work with `--no-llm`.

**Env vars —** OPTIONAL only, there are no required ones: `ANTHROPIC_API_KEY`
(absent ⇒ the tool runs as if `--no-llm` and says so), `AGENT_TRUST_CACHE_DIR`,
`AGENT_TRUST_MAX_FILES`, `AGENT_TRUST_MAX_BYTES`, `AGENT_TRUST_CLONE_TIMEOUT`,
`AGENT_TRUST_LLM_TIMEOUT`, `AGENT_TRUST_LLM_MODEL`.

## Standing rules

The 16 Phase-Zero non-negotiables are written for a web SaaS. Prompt 1 copies the
adapted set below into `CLAUDE.md`, including the N/A lines — a rule marked N/A
with a reason is a decision; a rule silently missing is a gap.

**Applies as written:** Rule 1 (no secrets in code) · Rule 2 (validate env at
startup, one `config.py`, never read `os.environ` elsewhere) · Rule 5 (generic
errors out, detail to the log) · Rule 9 (no placeholder code, no TODO, no stub
functions) · Rule 14 (model id from `AGENT_TRUST_LLM_MODEL`, never hardcoded;
deprecation error on a model-not-found 404) · Rule 15 (record input tokens,
output tokens and USD cost on every audit) · Rule 16 (same code runs any
environment purely on env values).

**Applies, restated for this app:** Rule 4 — the Anthropic call is the paid API.
It needs a wall-clock timeout, a per-run token ceiling, and content-addressed
caching by commit SHA so the same commit is never billed twice.

**N/A, with the reason:** Rule 3 (RLS) — no database. Rule 6, 7, 10, 12 (auth,
CSRF, server-side auth routes) — no HTTP server and no accounts; input validation
survives as Pydantic on every MCP tool argument and every CLI flag. Rule 8
(webhook idempotency) — no webhooks. Rule 11 (double-submit) — no forms. Rule 13
(legal for monetization) — not monetized; a LICENSE and a privacy note still ship
in Prompt 15.

**Four project-specific non-negotiables, equal in force to the sixteen:**

**D — Determinism.** Analyzers and scoring are pure functions of the repo
contents. The same commit SHA yields byte-identical scores, findings and
ordering, with and without the LLM. Nothing in the scoring path reads the clock,
the network, a random seed, or a dict iteration order it did not sort.

**X — No execution.** The tool never runs the audited repo's code. No dependency
install, no build, no test run, no git hooks. Clone with
`-c core.hooksPath=/dev/null`. Reading and parsing only.

**R — Redaction.** A matched secret value is truncated to its first 4 and last 2
characters at the moment of capture, inside `redact.py`, before it enters any
object. Nothing downstream may see the full value — not the report, the cache,
the LLM prompt, stdout, the HTML page, or a log line.

**B — The LLM writes prose, never numbers.** Enrichment output is merged by id
into `explanation` and `fix_steps` fields only. A failed, refused, malformed or
absent LLM response degrades to templates and changes no score, status, severity
or ordering.

---

## Prompt 1 — Spec validation & project setup

```
Read SPEC_DRAFT.md in full before doing anything. Write no application code in this
prompt.

1. Confirm the spec is complete enough to ship a tool that audits untrusted
   third-party repositories. Flag every gap across safety, determinism,
   correctness, licensing and privacy as a markdown table with columns: Gap, Why
   it matters, Suggested resolution. Answer these four explicitly, because they
   are the ones that turn into crashes on demo day: what happens on a repo that
   cannot be cloned; what happens on a repo of 200,000 files; what happens when
   a repo has no commits; and what a report must never contain.

2. Produce a FILE LIST for the whole build, grouped by the prompt that creates
   each file, matching the File Layout section of SPEC_DRAFT.md. It must include
   agent_trust/redact.py, acquire.py, inventory.py, models.py, config.py, the
   five analyzer modules, analyzers/patterns.py, the scoring package, enrich.py,
   cli.py, mcp_server.py, both renderers with their Jinja templates, and the two
   test fixtures tests/fixtures/clean-repo and tests/fixtures/ugly-repo.
   redact.py must appear at an earlier prompt than any module that reads file
   contents.

3. Reconcile the check ids. SPEC_DRAFT.md defines 37: TS-01..07, BR-01..07, VF-01..08,
   CQ-01..08, OB-01..07. Verify that each axis table sums to exactly 100, that
   no id appears twice, and that every id has a stated pass condition. Report
   the five totals and the count.

4. Write CLAUDE.md as a committed file. It contains: the adapted standing rules
   from BUILD.md including the N/A lines with their reasons; the four
   project-specific non-negotiables D, X, R and B verbatim; the pinned stack
   table; the 37 check ids as the single source of truth; and the module
   ownership rule — patterns.py owns every regex, redact.py is the only module
   that touches a secret value, config.py is the only module that reads
   os.environ.

5. Write SPEC.md as a committed file: SPEC_DRAFT.md expanded with the Report schema
   field list, the AXES constant in fixed order with names and weights, and the
   grade bands stated exactly once, with a note that scoring/grades.py is the
   only place they may be encoded.

6. State once, in SPEC.md: Python 3.12, package agent-trust-score, module
   agent_trust, console scripts agent-trust and agent-trust-mcp, model id
   claude-opus-5 read from AGENT_TRUST_LLM_MODEL. Later prompts reference these
   rather than restating them.

End with: "Spec validated. N gaps flagged. CLAUDE.md and SPEC.md written."
```

### Checkpoint 1

- [ ] `grep -o 'TS-0\|BR-0\|VF-0\|CQ-0\|OB-0' CLAUDE.md | wc -l` returns 37
- [ ] Each of the five axis weight tables in SPEC.md sums to 100, shown per axis
- [ ] The FILE LIST places `redact.py` at an earlier prompt than any analyzer
- [ ] SPEC.md states the grade bands exactly once, and names `scoring/grades.py`
      as the only place they may be encoded
- [ ] CLAUDE.md contains rules D, X, R and B verbatim
- [ ] CLAUDE.md states which of the 16 standing rules are N/A and why
- [ ] `claude-opus-5` appears in SPEC.md and CLAUDE.md and nowhere disagrees
- [ ] No `.py` file exists in the repo after this prompt

---

## Prompt 2a — Project setup

```
Set up the Python project and its toolchain. No analyzers, no CLI behaviour yet.

1. pyproject.toml — build backend hatchling; requires-python ">=3.12,<3.13";
   dependencies pinned exactly as SPEC.md lists them (typer 0.15.1, rich 13.9.4,
   pydantic 2.10.4, mcp 1.2.0, anthropic>=1.0,<2.0, jinja2 3.1.5); dev extras
   pytest 8.3.4, pytest-cov, ruff, mypy. [project.scripts] declares exactly two
   entry points: agent-trust = "agent_trust.cli:app" and agent-trust-mcp =
   "agent_trust.mcp_server:main". Configure ruff (line length 100, isort, pyupgrade),
   mypy strict with disallow_untyped_defs and warn_unreachable, and pytest with
   --cov=agent_trust --cov-fail-under=80.

2. agent_trust/__init__.py — __version__ as the single source of the version
   string. Nothing else duplicates it; pyproject reads it dynamically.

3. agent_trust/py.typed — empty marker so consumers get the types.

4. agent_trust/config.py — a frozen Pydantic Settings model holding every
   AGENT_TRUST_* variable from SPEC.md with its default, plus anthropic_api_key
   as an optional field. This is the ONLY module in the project permitted to
   read os.environ. A malformed integer value fails at startup with a message
   naming the variable, not a traceback. A missing ANTHROPIC_API_KEY is not an
   error: it sets llm_available to False.

5. agent_trust/logging.py — a stdlib logging configuration emitting one JSON
   object per line to stderr, never stdout, because stdout carries report data
   and the MCP stdio protocol. It routes every message through the redaction
   helper that Prompt 2b will own, so no log line can carry a raw secret.

6. .env.example — every variable bucketed OPTIONAL with a placeholder value and
   a one-line comment. There are no REQUIRED variables; say so at the top.

7. scripts/check_secrets.sh — scans this repository's own tracked files for
   key-shaped strings and exits non-zero on a hit. It must distinguish "clean"
   from "did not run": if git ls-files returns nothing, exit 2, never 0.

8. .gitignore, LICENSE placeholder, and a Makefile with targets lint, typecheck,
   secrets, test and check-all that runs the four in that order and stops at the
   first failure.

Do not write any module that reads a repository under audit yet.
```

### Checkpoint 2a

- [ ] `uv build` produces a wheel whose version equals `agent_trust.__version__`
      (the `agent-trust --version` form moves to Checkpoint 7, which owns `cli.py`)
- [ ] `AGENT_TRUST_MAX_FILES=abc` makes `get_settings()` raise `ConfigError`
      naming the variable, with no traceback in the message
- [ ] Unsetting `ANTHROPIC_API_KEY` still boots, and `config.llm_available` is False
- [ ] `grep -rn "os.environ\|getenv" agent_trust/ --include=*.py | grep -v config.py`
      returns nothing (without `--include` it matches `config.py`'s own bytecode)
- [ ] `scripts/check_secrets.sh` exits 1 on a planted key-shaped value with no
      placeholder marker, and 0 once removed — verified in both directions
- [ ] The scanner exits 2, not 0, when it enumerates fewer than 5 files
- [ ] `scripts/check_all.sh` runs lint, typecheck, secrets, test in that order,
      and reports a tool it cannot execute as BLOCKED with a non-zero exit
- [ ] A log record containing `\x1b[31m` serializes with no escape byte, and log
      output goes to stderr while stdout stays clean

> **Spot check — environment & secrets.** Before Prompt 2b:
> - [ ] No secret value is readable from any committed file, including `.env.example`
> - [ ] The secret scanner was canary-verified: a key-shaped string was planted, the scan went red, the string was removed
> - [ ] The scanner exits 2 rather than 0 when it has nothing to scan
> - [ ] Logging writes to stderr only — stdout is reserved for report output and MCP framing
---

## Prompt 2b — Safety foundation

```
Build the safety layer every later prompt depends on. This is the security
foundation phase: the tool reads untrusted third-party repositories, so these
modules decide what the rest of the build is allowed to do.

1. agent_trust/redact.py — the only module in the project that touches a raw
   secret value. A redact function truncates any string to its first 4 and last
   2 characters joined by an ellipsis, returning a marker for strings under 8
   characters so a short secret is never shown whole. A snippet function takes a
   line and a match span, redacts the matched span, trims the surrounding line
   to 200 characters, and strips control characters and ANSI escapes so a
   crafted repository cannot inject terminal escapes into our output. Every
   Evidence object in the build is constructed through this module.

2. agent_trust/errors.py — a small exception hierarchy: AcquireError,
   TimeoutExceeded, RepoTooLarge, NotAGitRepo, HostNotAllowed, EnrichmentError.
   Each carries a machine code and a message safe to show a user. Nothing in
   this hierarchy embeds a filesystem path outside the audited repo.

3. agent_trust/acquire.py — resolve a source to a local checkout.
   A local path is used in place after resolving symlinks and confirming the
   resolved path contains a .git directory. A URL is validated against the host
   allowlist in SPEC.md (github.com, gitlab.com, bitbucket.org, codeberg.org)
   unless allow_any_host is passed, then cloned shallow and blobless into a temp
   directory created with mkdtemp, with core.hooksPath set to /dev/null so no
   repository hook can execute. Reject any URL whose scheme is not https or ssh,
   and reject file:// entirely. The clone runs with a timeout from config and
   with an environment that disables credential prompts. Expose it as a context
   manager that removes the temp directory on every exit path including
   exceptions and timeouts.

4. In the same module, a git helper that runs read-only git subcommands with a
   fixed argument list, never a shell string, and never on user-controlled
   arguments that could be read as flags. It returns the commit SHA, the default
   branch and the last 50 commit subjects.

5. agent_trust/limits.py — a wall-clock deadline object created once per run
   from the timeout, checked between pipeline stages, plus the file-count and
   byte-count budgets from config. Exceeding a budget is not an error: it sets a
   truncated flag that the report carries.

State in a module docstring on acquire.py that this tool never executes
repository code, and list what that forbids: no dependency install, no build,
no test run, no hooks, no import of anything under the audited path.
```

### Checkpoint 2b

- [ ] Auditing a path with no `.git` directory raises `NotAGitRepo` and exits 1 with a one-line message
- [ ] A URL on an unlisted host is rejected with `HostNotAllowed`; the same URL with `--allow-any-host` proceeds
- [ ] A `file:///etc` source is rejected regardless of `--allow-any-host`
- [ ] The clone command line contains `--depth 1`, `--filter=blob:none` and `core.hooksPath=/dev/null`
- [ ] A repo containing a hook that writes `/tmp/pwned` leaves no such file after an audit
- [ ] The temp directory is removed after a run that raises mid-clone
- [ ] `redact("sk-ant-api03-ABCDEFGHIJKLMNOP")` returns a string containing neither `api03` nor any middle character
- [ ] A file whose content contains ANSI escape codes produces a snippet with none

---

## Prompt 3 — Report schema

```
Define the Report schema. This is the shared foundation of the build and the one
prompt that owns it: every later prompt imports these models and none of them
redefines a field. Replaces the database-schema phase — there is no database.

1. agent_trust/models.py — all models, Pydantic v2, every one declared with
   model_config = ConfigDict(frozen=True, extra="forbid"). Build exactly the
   models listed in the Report Schema section of SPEC.md with the field names
   and types given there: Report, RepoInfo, Overall, AxisScore, CheckResult,
   Evidence, Finding, Fix, LlmUsage. Add SCHEMA_VERSION = "1.0" as a module
   constant, carried on every Report.

2. Enumerations as string enums so the JSON is readable and stable:
   CheckStatus (pass, partial, fail, not_applicable), Severity (high, medium,
   low), Letter (A, B, C, D, F, N/A), AxisKey (the five keys in fixed order).
   The fixed order is a module-level tuple AXES holding key, display name and
   weight 0.2 for each — this tuple is the ordering authority for every axis
   list, table row and report section in the build.

3. Validators that make an invalid Report unconstructable: earned may not exceed
   weight; a CheckResult with status pass must have earned equal to weight; an
   axis score is either an integer 0..100 or None, and None requires letter
   N/A; Overall.score and Overall.mean follow the same nullable rule, so a run
   with no scored axis is representable without inventing a zero; a Report must
   carry exactly five AxisScore entries in AXES order; a Fix
   must reference at least one finding id that exists in the same report.

4. Evidence takes its snippet only from the redaction helper. Enforce it: the
   snippet field validator rejects a string longer than 200 characters or
   containing a control character, so a caller that bypasses redact.py fails
   loudly rather than shipping a secret.

5. A serialization helper that dumps a Report to JSON with sorted keys and a
   fixed datetime format, plus stable_payload() returning the report minus
   generated_at, run_ms and LlmUsage — the object determinism is asserted over, and a loader that round-trips it back. Reject a document whose
   schema_version does not match SCHEMA_VERSION rather than coercing it.

6. tests/test_models.py — construct a minimal valid Report, assert the round
   trip is byte-identical, and assert each validator above rejects its invalid
   case.

No scoring logic, no grade letters computed here. This prompt defines shapes.
```

### Checkpoint 3

- [ ] A `CheckResult` with `status="pass"` and `earned` less than `weight` raises a ValidationError
- [ ] A Report with four axes raises; with five in the wrong order raises
- [ ] An `Evidence` snippet of 201 characters raises
- [ ] An `Evidence` snippet containing `\x1b[31m` raises
- [ ] Dumping the same Report twice returns byte-identical JSON
- [ ] Loading a document with `schema_version: "0.9"` raises rather than coercing
- [ ] A `Fix` naming a finding id absent from the report raises
- [ ] `AXES` has five entries and every weight is 0.2

> **Spot check — schema stability.** Before Prompt 4:
> - [ ] `SCHEMA_VERSION` is referenced, not retyped, wherever a version is written
> - [ ] The connection-pooling spot check from the standard sequence is recorded as skipped, with the reason: no database, no pooled connections
> - [ ] Every model is frozen and forbids extra fields — a typo'd field name fails at construction, not at render time
> - [ ] JSON key order is fixed by the dump helper, not by dict insertion order

---

## Prompt 4 — Inventory and repo context

```
Build the file inventory that every analyzer reads. Replaces the types-and-
validation phase: this is the shared data structure later prompts import.

1. agent_trust/inventory.py — a RepoContext dataclass, frozen, holding the
   resolved root path, the commit SHA, the default branch, the last 50 commit
   subjects, the list of tracked files, the language histogram, and the
   truncated flag. Analyzers receive this object and nothing else, so an
   analyzer physically cannot reach the network or the environment.

2. File discovery from `git ls-files -z` only, never a filesystem walk, so
   untracked build output and anything ignored is out of scope by construction.
   Skip the directories and patterns named in SPEC.md: node_modules, .venv,
   venv, dist, build, vendor, target, .git, any *.min.* file, lockfiles, and any
   file over 1 MB or detected as binary by a null byte in its first 8000 bytes.

3. Budget enforcement using the limits module: stop adding files at
   max_files or max_bytes, set truncated True, and record how many files were
   skipped for each reason. A truncated inventory is a legitimate result that
   the report states plainly; it is never a silent partial answer.

4. A read helper that returns a file's text decoded as UTF-8 with errors
   replaced, memoized per run so ten analyzers reading README.md read the disk
   once. It returns lines with 1-based numbers, because every Evidence object
   carries a line number a human will use to find the code.

5. Language detection by extension into the histogram, with two booleans the
   analyzers branch on: has_python and has_javascript. A check that cannot apply
   to any detected language returns not_applicable, which SPEC.md removes from
   both sides of the axis fraction — it must never be scored as a failure.

6. A manifest parser returning parsed pyproject.toml and package.json when
   present, and None when absent or malformed. A malformed manifest is a finding
   later, not a crash now.

7. tests/test_inventory.py — build a temporary git repo in a fixture, assert the
   skip rules, assert the budget sets truncated, assert the memoized read is
   called once per file.

Sort every list this module produces. Unsorted output is the most common source
of run-to-run drift, and determinism is non-negotiable rule D.
```

### Checkpoint 4

- [ ] A repo with `node_modules/` containing 500 files reports an analyzed count that excludes all 500
- [ ] A 2 MB source file is skipped and counted in the skip reasons
- [ ] A PNG committed to the repo is skipped as binary
- [ ] Setting `AGENT_TRUST_MAX_FILES=5` on a 50-file repo sets `truncated` True and reports 5 analyzed
- [ ] Two runs over the same commit return file lists that compare equal
- [ ] Reading the same file from two analyzers hits the disk once
- [ ] A repo with a malformed `package.json` returns None from the parser and does not raise
- [ ] An untracked file present on disk does not appear in the inventory
---

## Prompt 5 — Scoring engine

> **Reordered, deliberately.** The spec's phase map put scoring in the feature
> block. It moves here because the CLI at Prompt 7 cannot produce a Report
> without it, and a walking skeleton that runs end-to-end before any analyzer
> exists is worth more than the original ordering. Nothing else moves.

```
Build the scoring engine. Pure functions over CheckResult lists — no I/O, no
clock, no network. This module decides every number in the product.

1. agent_trust/scoring/grades.py — the grade bands from SPEC.md encoded exactly
   once, here: A 90-100, B 80-89, C 70-79, D 60-69, F 0-59. A letter_for
   function maps a score to a Letter, and None maps to N/A. No other module in
   the build may contain a band boundary; later prompts import this.

2. agent_trust/scoring/__init__.py — score_axis takes an axis key and its
   CheckResults and returns an AxisScore. pass earns the full weight, partial
   earns half the weight, fail earns zero, and not_applicable is removed from
   both the numerator and the denominator. The score is round(100 * earned /
   applicable_weight). When every check on an axis is not_applicable the score
   is None and the letter is N/A, and that axis is dropped from the overall
   mean rather than counted as a zero.

3. score_report applies the two rules from SPEC.md in this order: the secret
   rule first, where any high-severity BR-01 finding forces the blast_radius
   score to at most 39; then the cap rule, where any scored axis below 40 sets
   overall to min(mean, 70) with capped True and cap_reason naming that axis.
   With no scored axes at all, overall score and mean are None and the letter is
   N/A. Compute the letter from the capped score, never from the raw mean.

4. agent_trust/scoring/findings.py — derive a Finding from every non-pass
   CheckResult using the deterministic severity map in SPEC.md: high for a
   failed check worth 20 or more points or any BR-01 hit, medium for a failed
   check worth 10 to 19, low for everything else including every partial. The
   explanation starts as template text keyed by check id; Prompt 14 may replace
   the string and nothing else.

5. agent_trust/scoring/effort.py — a literal dict mapping each of the 37 check
   ids to an effort in minutes, and a table mapping each id to the points it
   would recover. Both are data, not estimates made at runtime, and neither is
   ever produced by the model.

6. agent_trust/scoring/fixes.py — build Fix objects, one per failed check, with
   ratio = risk_reduction / (effort_minutes / 60). Sort descending by ratio,
   breaking ties by severity, then AXES order, then check id, so the ordering is
   total and reproducible.

7. tests/test_scoring.py — table-driven cases covering an all-pass repo, an
   all-fail repo, a single not_applicable axis, the 39-point secret clamp, the
   cap firing on a 38-point axis with a 95 mean, and the cap not firing at 40.
```

### Checkpoint 5

- [ ] An axis of two passes and two `not_applicable` scores 100, not 50
- [ ] An axis where every check is `not_applicable` returns score None and letter N/A
- [ ] A report with a high-severity BR-01 finding shows `blast_radius` at 39 or below
- [ ] Four axes at 95 and one at 38 yields overall 70, letter C, `capped` True, `cap_reason` naming the axis
- [ ] The same five axes with the low one at 40 yields overall 84, `capped` False
- [ ] `grep -rn "90\|80\|70\|60" agent_trust/ --include=*.py` shows band numbers only in `grades.py`
- [ ] Two Fixes with equal ratio always sort in the same order across 100 shuffled inputs
- [ ] Every `partial` result produces a `low` severity finding, never `medium`

---

## Prompt 6 — Renderers

```
Build the three renderers. Replaces the design-system phase: these are this
product's entire user interface. Each takes a Report and returns text; none of
them computes a number, recomputes a letter, or reorders a list.

1. agent_trust/render/terminal.py — a Rich rendering to stderr-safe stdout: a
   header line with the repo, the commit SHA short form and the overall grade;
   a five-row table of axis, score, letter and failed-check count in AXES order;
   the top three fixes with their effort and the points they recover; then the
   paths of the files written. When overall is capped, print the cap reason
   directly under the grade, because a C that is really a capped A is the single
   most important thing on the screen. Colour by letter, and degrade to plain
   text when the stream is not a TTY or NO_COLOR is set.

2. agent_trust/render/templates/report.md.j2 — the markdown report: summary,
   the grade table, then one section per axis in AXES order listing every check
   with its status, weight and detail, then the findings with file and line
   references written as path:line so they are clickable, then the ranked fix
   list as a table. Every evidence snippet is already redacted; the template
   never reaches into a raw value.

3. agent_trust/render/markdown.py — renders that template, with a deterministic
   context builder so the same Report always yields the same bytes.

4. agent_trust/render/templates/report.html.j2 and render/html.py — a single
   self-contained HTML file with inline CSS, no external requests, no scripts.
   It must autoescape: repository content appears in this page, so a repo
   containing a script tag in its README must render as text. Same content and
   same order as the markdown.

5. A golden-file test: tests/fixtures/golden_report.json holds a hand-built
   Report covering every status and severity. tests/test_render.py asserts the
   markdown and HTML outputs match committed golden files byte for byte, so a
   template edit that changes output is a visible diff rather than a surprise.

6. An empty-state rule, the one most often forgotten: a repo with zero findings
   must render a real "no findings on this axis" line in all three renderers,
   never an empty table or a blank section.
```

### Checkpoint 6

- [ ] A Report with `capped` True prints the cap reason on the line below the grade
- [ ] A README containing `<script>alert(1)</script>` renders as visible text in the HTML, not as a tag
- [ ] The HTML file contains no `http://` or `https://` resource reference
- [ ] Piping the terminal output to a file produces no ANSI escape codes
- [ ] Rendering the golden report twice produces byte-identical markdown
- [ ] An axis with zero findings shows an explicit no-findings line in all three renderers
- [ ] Axis order in all three outputs matches `AXES`
- [ ] Every finding line shows `path:line`

---

## Prompt 7 — CLI, MCP server and cache

```
Wire the two delivery surfaces onto one pipeline. Replaces the layout-and-
navigation phase. After this prompt the tool runs end to end with zero analyzers
registered, and reports five N/A axes honestly rather than inventing a score.

1. agent_trust/pipeline.py — a single audit function taking a source, an axis
   filter, a use_llm flag and a deadline, running acquire, inventory, the
   analyzer registry, scoring, and enrichment in that order, and returning a
   Report. Both surfaces call this and neither has logic of its own. The
   registry starts empty; Prompt 8 defines how analyzers register into it.

2. agent_trust/cache.py — content-addressed by commit SHA under the configured
   cache dir, one JSON file per SHA, 24 hour TTL, written atomically by writing
   a temp file and renaming so an interrupted run never leaves a half report. A
   cached Report whose schema_version differs is discarded, not migrated. The
   cache stores reports only — never repository content, never a snippet that
   was not already redacted.

3. agent_trust/cli.py — the Typer app implementing every flag in SPEC.md with
   the exact names and defaults given there, including repeatable --axis and
   --format, --no-llm, --min-grade, --allow-any-host, --timeout, --cache and
   --quiet. Exit 0 on a successful grade, 1 on an operational error, 2 when the
   grade is worse than --min-grade. An operational error prints one line and no
   traceback; the traceback goes to the log.

4. agent_trust/mcp_server.py — a stdio MCP server exposing audit_repo,
   get_axis and suggest_fixes with the signatures in SPEC.md, argument schemas
   derived from the Pydantic models, and a docstring on each that tells a
   calling agent what it returns and what it costs. Every tool is wrapped so an
   exception becomes a structured error object with a code and a safe message,
   never a traceback. A hard 90 second cap per call. Nothing is ever written to
   stdout except MCP frames.

5. get_axis and suggest_fixes read the cache when a report for that SHA exists
   and run the pipeline when it does not, so a follow-up call after audit_repo
   is instant and free.

6. tests/test_cli.py and tests/test_mcp.py — invoke both surfaces against a
   fixture repo and assert the exit codes, the error shapes and the cache reuse.
```

### Checkpoint 7

- [ ] `agent-trust . --no-llm` exits 0 and prints five axes, each showing N/A
- [ ] `agent-trust /not/a/repo` exits 1, prints one line, and shows no traceback
- [ ] `agent-trust . --min-grade A` exits 2 while `--min-grade F` exits 0
- [ ] A second run on the same commit reads the cache; `--no-cache` re-runs the pipeline
- [ ] Killing a run mid-write leaves no partial file in the cache directory
- [ ] An MCP tool call that raises returns `{"error": {"code": ..., "message": ...}}` with no traceback
- [ ] The MCP server writes nothing to stdout but protocol frames
- [ ] `agent-trust . --format json --format md` writes exactly `report.json` and `report.md`
- [ ] `agent-trust --version` prints the same string as `agent_trust.__version__`
      (deferred here from Checkpoint 2a, which predates `cli.py`)

> **Spot check — untrusted input and sandboxing.** Before Prompt 8:
> - [ ] A repo containing a symlink to `/etc/passwd` is not read through; the link is skipped and recorded
> - [ ] A path argument containing `../` cannot cause a read outside the resolved repo root
> - [ ] Every clone runs with `core.hooksPath=/dev/null`, verified by planting a `post-checkout` hook and confirming it did not run
> - [ ] Error messages returned to the caller contain no absolute path outside the audited repo, and no traceback
> - [ ] The temp checkout directory is gone after a run that timed out
---

## Prompt 8 — Analyzer framework and Tool Surface

```
Build the analyzer contract and the first axis. Every later analyzer follows the
shape established here, so get the contract right before adding checks.

1. agent_trust/analyzers/__init__.py — a registry mapping each AxisKey to a run
   function with the signature run(ctx: RepoContext) -> list[CheckResult]. An
   analyzer receives the RepoContext and nothing else: no config, no network, no
   environment, no clock. Registration is explicit at import time, and the
   pipeline iterates the registry in AXES order.

2. A CheckSpec dataclass carrying the check id, title, weight and the axis it
   belongs to, plus a module-level table of all seven Tool Surface specs with
   the exact ids and weights from SPEC.md: TS-01 20, TS-02 20, TS-03 15, TS-04
   10, TS-05 15, TS-06 10, TS-07 10. Assert at import that the weights sum to
   100, so a mistyped weight fails at startup rather than skewing a grade
   silently.

3. agent_trust/analyzers/patterns.py — the single home for every regex in the
   build. Each pattern is a named compiled constant with a comment giving the
   check id that uses it. No other module may compile a regex over repository
   content. Start it with the Tool Surface patterns.

4. agent_trust/analyzers/tool_surface.py — implement the seven checks exactly as
   SPEC.md specifies them. TS-01 looks for an MCP manifest file, an mcp or
   modelcontextprotocol dependency, or a server construction call. TS-02 looks
   for an OpenAPI, Swagger, GraphQL or proto schema file. TS-03 reads the parsed
   manifests for a scripts or bin entry, or finds a CLI framework in use. TS-04
   requires a usage block in the README showing an invocation with flags. TS-05
   is language-branched: TypeScript strict mode, or the annotated-def ratio in
   sampled Python files, partial at 30 percent and pass at 60. TS-06 checks a
   manifest parses. TS-07 checks for a documented config contract.

5. Every check returns evidence with a path and, where a match came from file
   content, a line number and a redacted snippet. A check that cannot apply to
   the detected languages returns not_applicable with a detail line saying which
   language it needs. A check that fails returns evidence of what was searched
   for, because a finding with no evidence is unactionable.

6. tests/test_analyzers_tool_surface.py — one test per check, each asserting the
   pass case, the fail case and where applicable the partial case, using small
   temporary repos rather than the shared fixtures.
```

### Checkpoint 8

- [ ] Importing the analyzers package with a weight table summing to 99 raises at import time
- [ ] A repo with `.mcp.json` passes TS-01; removing the file drops the axis by exactly 20 points
- [ ] A Python repo with 40 percent annotated public defs returns `partial` on TS-05
- [ ] A repo of only Go files returns `not_applicable` on TS-05 and the axis denominator excludes its weight
- [ ] Every failed check carries at least one evidence entry naming what was searched
- [ ] `grep -rn "re.compile" agent_trust/ --include=*.py` shows hits only in `patterns.py`
- [ ] `agent-trust . --axis tool_surface --no-llm` prints one scored axis and four N/A
- [ ] Running the axis twice on the same commit returns identical evidence line numbers

---

## Prompt 9 — Blast Radius, part one: secrets

```
Implement the three secret-facing checks of the blast_radius axis: BR-01 weight
30, BR-02 weight 12, BR-03 weight 8. This is the highest-stakes prompt in the
build. A false negative loses the product's whole claim; a false positive on a
clean repo loses the demo. Treat both as defects.

1. Add to analyzers/patterns.py the provider patterns named in SPEC.md: AWS
   access key ids, GitHub tokens, Stripe live keys, Slack tokens, Google API
   keys, OpenAI and Anthropic keys, PEM private key headers, and three-segment
   JWTs. Each is a named constant carrying the provider name used in the finding
   title. Add the generic rule separately: an assignment whose name matches
   secret, token, password, api_key, access_key or private_key and whose value
   is a literal of 20 or more characters.

2. agent_trust/analyzers/entropy.py — Shannon entropy over a string, and a
   threshold constant of 4.0 used only by the generic rule. Provider matches do
   not consult entropy; a well-formed AWS key is a hit regardless of its
   entropy.

3. The allowlist, implemented as a first-class part of the check rather than a
   filter bolted on: the path patterns and the value markers listed in SPEC.md,
   plus any value that is itself an environment reference. Every suppression is
   counted, and the count appears in the check detail, so a repo where the
   allowlist swallowed 40 matches says so instead of reporting a clean bill.

4. agent_trust/analyzers/blast_radius.py — BR-01 fails on any non-allowlisted
   match, with one Finding per match at high severity and evidence built through
   redact.py. BR-02 fails when git ls-files lists a .env, .env.local or
   .env.production. BR-03 checks .gitignore exists and covers env files, key and
   credential patterns and build artifacts, partial when it exists but misses
   some. Register the axis with all seven specs, leaving the four Prompt 10
   checks raising NotImplementedError until then — do not register a check that
   silently returns pass.

5. tests/test_analyzers_secrets.py — a table of at least twelve positive strings
   covering every provider pattern and at least twenty negative strings drawn
   from real placeholder and test-fixture forms. Assert no finding ever contains
   a full matched value, by asserting the planted secret string is absent from
   the serialized report.
```

### Checkpoint 9

- [ ] Each of the provider patterns matches its planted key and produces exactly one high-severity finding
- [ ] `.env.example` containing `STRIPE_SECRET_KEY=sk_test_placeholder` produces zero findings
- [ ] A committed `AKIA` key drives `blast_radius` to 39 or below and caps the overall grade at C
- [ ] The serialized report does not contain the planted secret's middle characters
- [ ] A repo with 40 allowlisted matches states that suppression count in the check detail
- [ ] Tracking `.env` fails BR-02; the same repo with it ignored and untracked passes
- [ ] A `.gitignore` missing key patterns returns `partial` on BR-03, not `fail`
- [ ] The four unimplemented blast_radius checks raise rather than returning `pass`

> **Spot check — detector accuracy.** Before Prompt 10, and again before the demo:
> - [ ] Run the axis against three real public repos known to be clean; zero secrets flagged in all three
> - [ ] Plant one key of each provider type in a scratch repo; every one is caught
> - [ ] Grep the written `report.md`, `report.json`, `report.html` and the cache file for the planted value; zero hits in all four
> - [ ] The allowlist suppression count is reported, never silent
> - [ ] A key inside a `tests/fixtures/` path is suppressed, and a key in `src/` at the same value is not

---

## Prompt 10 — Blast Radius, part two: destructive operations

```
Complete the blast_radius axis with BR-04 weight 20, BR-05 weight 15, BR-06
weight 10 and BR-07 weight 5. These are the judgment-adjacent checks, so the
rule from CLAUDE.md matters here: detection is static and deterministic, and the
model may later explain a finding but never create, remove or re-grade one.

1. Add the destructive-operation patterns from SPEC.md to patterns.py, each
   named for what it does: SQL DROP, TRUNCATE and unqualified DELETE FROM;
   migration runners; recursive filesystem removal in both languages; bulk ORM
   deletes; payment creation and capture; transactional email sends; and an
   outbound request to a non-localhost literal host from a script entry point.

2. BR-04 — for every match, search a 30-line window around it for a guard: a
   dry-run flag or parameter, an interactive confirmation, an environment gate,
   or a required force flag. Pass when every match is guarded, partial when some
   are, fail when none are. The evidence names the operation and the guard that
   was or was not found, because "destructive op unguarded" without the line is
   an accusation rather than a finding.

3. BR-05 — locate admin-scoped credential names, then decide reachability by
   path convention rather than by import graph: anything under a client, public,
   www, static, browser, components or pages directory, plus any file whose name
   marks it as client-side. Fail on a hit, and say in the detail that
   reachability was judged by path, so a user can see the method and disagree.

4. BR-06 — payment, email and outbound-webhook calls must sit behind an
   environment flag, a test-mode key literal, or an injected client parameter.
   Partial when some are.

5. BR-07 — a CODEOWNERS file at any of its three standard locations, or a
   branch-protection or ruleset config.

6. Remove the NotImplementedError registrations from Prompt 9 and assert at
   import that the seven blast_radius weights sum to 100.

7. tests/test_analyzers_blast_radius.py — for BR-04, one case per guard type
   proving a guarded operation passes, plus an unguarded case per operation
   family. Include a case where a guard exists 31 lines away and must not count.
```

### Checkpoint 10

- [ ] `rm -rf` behind an `if args.dry_run` check returns `pass`; the same line with the guard deleted returns `fail`
- [ ] A guard 31 lines from the operation does not count, and 30 lines does
- [ ] A repo with three destructive ops, two guarded, returns `partial` on BR-04
- [ ] A `SUPABASE_SERVICE_ROLE_KEY` reference under `components/` fails BR-05 and states that reachability was judged by path
- [ ] The same reference under `scripts/` does not fail BR-05
- [ ] `stripe.charges.create` with no env gate fails BR-06; wrapping it in an env check passes
- [ ] The seven blast_radius weights sum to 100, asserted at import
- [ ] A clean repo scores 100 on blast_radius with no findings
---

## Prompt 11 — Verifiability

```
Implement the eight verifiability checks with the ids and weights from SPEC.md:
VF-01 20, VF-02 15, VF-03 15, VF-04 15, VF-05 15, VF-06 10, VF-07 5, VF-08 5.
This axis answers whether an agent can prove it did not break anything, so the
checks look for gates that exist AND are wired up, never for gates that merely
exist. A CI file that runs only a linter is the exact failure this axis is for.

1. agent_trust/analyzers/verifiability.py, registered in AXES order with the
   weight-sum assertion at import.

2. VF-01 counts test files by the five naming patterns in SPEC.md plus a tests
   directory containing source files. VF-02 reads the parsed manifests for a
   test runner dependency or a test script. VF-03 computes the test-to-source
   file ratio, pass at 0.20 and partial at 0.10, and reports both counts in the
   detail so the number is auditable.

3. VF-04 finds a CI config at any of the four locations named in SPEC.md. VF-05
   is the important one: parse the CI file as YAML and look for a step whose run
   command actually invokes the test runner discovered by VF-02. A workflow that
   lints and builds but never tests fails VF-05 while passing VF-04, and that
   two-line gap is a real finding worth reporting on its own.

4. VF-05 also reports, without scoring it, whether the workflow's trigger branch
   matches the repository's default branch. A workflow watching main in a repo
   whose branch is master has never run once, and an empty run history reads
   exactly like a passing one. Surface it as a note on the finding.

5. VF-06 checks TypeScript strict mode or a mypy or pyright configuration. VF-07
   checks for an eslint, biome or ruff configuration. VF-08 checks for a
   pre-commit config, husky hooks or lint-staged.

6. Every check that reads a config file must handle a malformed one: a YAML file
   that will not parse is a fail with the parse error in the detail, never an
   exception that kills the run.

7. tests/test_analyzers_verifiability.py — include a workflow that runs only
   lint, a workflow that runs tests, a workflow watching the wrong branch, and a
   malformed YAML file.
```

### Checkpoint 11

- [ ] A repo with a CI workflow that runs only `npm run lint` passes VF-04 and fails VF-05
- [ ] Adding a test step to that workflow flips VF-05 to `pass`
- [ ] A workflow triggering on `main` in a repo whose default branch is `master` produces a note on the VF-05 finding
- [ ] A repo with 3 test files and 30 source files returns `partial` on VF-03 and shows both counts
- [ ] A malformed `ci.yml` returns `fail` with the parse error in the detail and does not raise
- [ ] `tsconfig.json` without `"strict": true` fails VF-06; adding it passes
- [ ] The eight verifiability weights sum to 100, asserted at import
- [ ] A repo with no tests scores at most 35 on this axis

---

## Prompt 12 — Context Quality

```
Implement the eight context_quality checks with the ids and weights from
SPEC.md: CQ-01 20, CQ-02 10, CQ-03 15, CQ-04 15, CQ-05 15, CQ-06 10, CQ-07 10,
CQ-08 5. This axis scores whether the repo explains itself to an agent, and it
is the axis most tempting to hand to the model. Do not. Detection is structural
and deterministic here; Prompt 14 may write prose about the result and nothing
more.

1. agent_trust/analyzers/context_quality.py. Resolve the agent doc as the first
   present of CLAUDE.md, AGENTS.md, .cursorrules and
   .github/copilot-instructions.md, and record which one was used in every
   evidence entry, since a repo with two of them should not be scored twice.

2. CQ-01 is the agent doc's presence and non-emptiness. CQ-02 is a README with
   at least 300 words, partial at 100, counting words after stripping code
   fences so a README that is one long code block is not credited as prose.

3. CQ-03 through CQ-07 detect sections structurally across the agent doc and the
   README combined: a setup or install command block, an architecture summary as
   a directory tree or a component list, documented run and test commands, a
   conventions or style section, and an explicit do-not-touch or generated-files
   list. Match on heading text and on the command patterns themselves, so a doc
   that shows the commands without a matching heading still passes.

4. CQ-08 extracts every path-like token from the agent doc, resolves each
   against the repo, and passes at 80 percent resolving, partial at 50. This is
   the staleness check: a doc that points an agent at files that no longer exist
   is worse than no doc, because the agent trusts it. Report the unresolved
   paths as evidence, capped at ten.

5. Every check states in its detail which document satisfied it, so a fix list
   can tell a user to edit CLAUDE.md rather than the README.

6. tests/test_analyzers_context_quality.py — cases for no doc, a doc with every
   section, a doc with headings but no commands, a doc with commands but no
   headings, and a doc citing three paths of which one is missing.
```

### Checkpoint 12

- [ ] A repo with no agent doc and no README scores 0 on this axis with eight findings
- [ ] A README that is one 500-word code block returns `fail` on CQ-02
- [ ] A doc listing setup commands without a "Setup" heading still passes CQ-03
- [ ] A doc citing five paths of which one is missing returns `partial` on CQ-08 and names the missing path
- [ ] A repo with both `CLAUDE.md` and `AGENTS.md` is scored against one of them, named in the evidence
- [ ] Every check detail names the file that satisfied or failed it
- [ ] The eight context_quality weights sum to 100, asserted at import
- [ ] This repository's own `CLAUDE.md` scores 80 or better on this axis

---

## Prompt 13 — Observability

```
Implement the seven observability checks with the ids and weights from SPEC.md:
OB-01 25, OB-02 10, OB-03 20, OB-04 15, OB-05 15, OB-06 5, OB-07 10. This axis
answers whether a human can reconstruct what the agent did after the fact.

1. agent_trust/analyzers/observability.py, registered with the weight-sum
   assertion at import.

2. OB-01 detects a structured logging library or configuration by dependency and
   by import: structlog, a logging configuration call, pino, winston, bunyan, or
   an OpenTelemetry logs exporter. OB-02 compares logger call sites to print and
   console.log call sites across source files, excluding tests and scripts
   directories, and passes when logger calls are at least equal. Report both
   counts in the detail.

3. OB-03 detects error reporting initialization: Sentry, Rollbar, Bugsnag,
   Honeybadger or OpenTelemetry tracing. Presence of the dependency alone is
   partial; an initialization call is a pass, because an installed-but-never-
   initialized monitor is the common case and it reports nothing.

4. OB-04 looks for an audit-trail pattern: a table or model named audit_log,
   activity_log or events, an append-only writer, or a record carrying an actor,
   an action and a timestamp together.

5. OB-05 reads the last 50 commit subjects from the RepoContext and passes when
   at least 60 percent are 15 characters or longer and are not a bare wip, fix,
   update or asdf, partial at 40 percent. A repo with fewer than 10 commits
   returns not_applicable rather than a fail, since there is not enough history
   to judge and a false fail here reads as noise.

6. OB-06 checks for a CHANGELOG or a releases directory. OB-07 checks for a
   health or status endpoint route, or a CLI exposing a version flag.

7. tests/test_analyzers_observability.py — build fixture repos with controlled
   commit histories using git commands, so OB-05 is tested against real history
   rather than a mocked list.
```

### Checkpoint 13

- [ ] A repo with `sentry` in dependencies but no `init` call returns `partial` on OB-03
- [ ] Adding the init call flips OB-03 to `pass`
- [ ] A repo whose last 50 commits are all `wip` fails OB-05 and shows the percentage
- [ ] A repo with 6 commits returns `not_applicable` on OB-05, and the axis denominator drops 15
- [ ] A repo using `console.log` 40 times and a logger twice fails OB-02 and reports both counts
- [ ] The seven observability weights sum to 100, asserted at import
- [ ] All five axes are now registered; `agent-trust . --no-llm` prints five scored axes and no N/A
- [ ] Running the full audit twice on the same commit produces byte-identical `stable_payload()`
---

## Prompt 14 — LLM enrichment

```
Add the single Claude call. Rule B from CLAUDE.md governs this entire prompt:
the model writes prose, never numbers. Build it so that deleting the API key
changes the wording of the report and nothing else.

1. agent_trust/enrich.py — an Enrichment Pydantic model with three fields: a
   summary string, an explanations mapping of finding id to string, and a
   fix_steps mapping of fix id to a list of strings. This model is the response
   schema; nothing else may come back from the model.

2. One call per audit through the Anthropic SDK. The model id comes from
   config, defaulting to claude-opus-5, never a literal in this module. Pass
   thinking as adaptive and set effort to medium inside output_config, and use
   the SDK's parse helper with the Enrichment schema as the structured output
   format so an unparseable response raises rather than arriving as prose. Set
   an explicit client timeout from AGENT_TRUST_LLM_TIMEOUT, default 20 seconds,
   and max_tokens 8000.

3. The prompt has two parts and the split is what makes it cheap: a stable
   prefix holding the system prompt and the scoring rubric, marked with an
   ephemeral cache_control breakpoint, then the volatile part holding this
   repo's scored report JSON and up to 40 redacted evidence snippets plus the
   agent doc and README truncated to 6000 tokens. Nothing before the breakpoint
   varies between runs — no timestamp, no repo name, no commit SHA — or the
   cache never hits.

4. Merge by id only. Explanations for unknown finding ids are dropped; missing
   ids keep their template text and their explanation_source stays "template".
   Assert after merging that the score, letter, capped flag, severity and fix
   order are identical to the pre-enrichment report, and raise if they are not.
   That assertion is the enforcement of rule B, not a comment about it.

5. Failure is a normal path, not an exception: a missing key, a timeout, a
   connection error, a validation failure, or a response whose stop_reason is
   refusal all degrade to template text with llm.used False and a
   fallback_reason recorded in the report. A model-not-found 404 raises a
   distinct deprecation error naming the configured model id, because a silently
   swapped model id is how this breaks six months from now.

6. Record input tokens, output tokens and computed USD cost on LlmUsage using
   the rate constants in config, and print the cost on the terminal summary.

7. tests/test_enrich.py — with a stubbed client, assert the merge changes only
   prose, assert every failure mode degrades, and assert the cached prefix is
   byte-identical across two different repositories.
```

### Checkpoint 14

- [ ] With `ANTHROPIC_API_KEY` unset, the audit completes, `llm.used` is False, and a fallback reason is printed
- [ ] With and without the LLM, every score, letter, severity and fix position is identical
- [ ] A stubbed response containing an unknown finding id is dropped, not merged
- [ ] A stubbed response that fails schema validation degrades to templates and exits 0
- [ ] A stubbed 404 raises an error naming the configured model id
- [ ] The cached prefix bytes are identical across two different repositories
- [ ] `report.json` shows non-zero input tokens, output tokens and a cost when the LLM ran
- [ ] `grep -rn "claude-opus-5" agent_trust/ --include=*.py` shows the id only in `config.py`

> **Spot check — model integration.** Before Prompt 15:
> - [ ] The prompt sent to the API contains no unredacted secret — assert against a fixture repo with a planted key
> - [ ] The stable prefix carries the cache breakpoint and nothing volatile precedes it
> - [ ] Cost is recorded per run and the cache prevents a second charge for the same commit SHA
> - [ ] The refusal path and the timeout path were both exercised, not just reasoned about
> - [ ] Determinism holds: the same commit graded twice with the LLM on produces the same numbers

---

## Prompt 15 — Packaging, docs and polish

```
Make the tool installable and explainable. Reduced legal tail: this product is
not monetized and stores no user data, so there is no privacy policy, no cookie
consent and no data-export endpoint. What replaces them is stated below.

1. LICENSE — MIT, with the copyright line filled in. A repo-auditing tool with
   no license is a tool nobody can adopt.

2. README.md — what it does in two sentences, an install line using uvx, three
   worked examples with their real terminal output pasted from an actual run,
   the flag table copied from SPEC.md, the five axes with one sentence each, and
   an explicit accuracy section: what the tool detects statically, what the
   model adds, and the fact that a passing grade is evidence about structure and
   never a security audit. Overclaiming here is the failure mode that matters —
   never describe the tool as certifying, guaranteeing, or securing anything.

3. docs/PRIVACY.md — short and specific: the tool sends nothing anywhere unless
   the LLM pass runs; when it does, it sends the scored report, redacted
   snippets and the two doc files to the Anthropic API and nothing else; no
   telemetry, no analytics, no phone-home; the cache is local and holds reports
   only. Name the one third party by name.

4. docs/CHECKS.md — the full 37-check reference generated from the CheckSpec
   tables rather than typed by hand, so it cannot drift from the code. A test
   asserts the file matches what the tables produce.

5. CLAUDE.md for this repository, if Prompt 1's version has drifted: dogfood it.
   This tool grades agent-operability, and a low context_quality score on its own
   repository is the most embarrassing possible demo.

6. Polish pass: a first-run message when no API key is configured explaining
   that reports will use template text and how to change that; a progress
   indicator during clone and analysis that writes to stderr; a clear message
   when a repo is truncated by the file budget; a non-zero-exit path that never
   prints a traceback; and `--quiet` honored by every renderer.

7. Publishing readiness: verify the built wheel installs into a clean virtual
   environment and both console scripts resolve.
```

### Checkpoint 15

- [ ] `uvx --from ./dist/*.whl agent-trust --version` works in a clean environment
- [ ] Both console scripts resolve after a wheel install
- [ ] `docs/CHECKS.md` regenerates identically, asserted by a test
- [ ] The README contains no claim that the tool certifies, guarantees or secures anything
- [ ] Running with no API key prints the template-mode notice once, to stderr
- [ ] `--quiet` suppresses the summary while still writing the report files
- [ ] `agent-trust .` on this repository scores B or better on `context_quality`
- [ ] `docs/PRIVACY.md` names Anthropic as the only third party and states there is no telemetry

---

## Prompt 16 — Testing, fixtures and CI

```
Close the build with the test suite and a CI pipeline that actually runs. CI is
a specified deliverable here, not a bullet: write the workflow file with named
jobs and the branch it triggers on, then prove it ran.

1. tests/fixtures/clean-repo — a committed fixture repository that scores A or
   B: an MCP manifest, an OpenAPI schema, a typed CLI, a test suite with CI that
   runs it, a CLAUDE.md with all five sections, structured logging and a Sentry
   init, a CODEOWNERS file, and a .env.example with placeholders only. It must
   produce zero secret findings — that is one of the four hackathon success
   criteria.

2. tests/fixtures/ugly-repo — a committed fixture that scores F and yields at
   least one true-positive finding on every axis: a planted fake AWS key that
   matches the pattern but is not a live credential, a tracked .env, an
   unguarded migration runner, no tests, no CI, no agent doc, a README of two
   lines, console.log everywhere, and 50 commits reading "wip". Both fixtures
   need real git history, so build them with a script that initializes and
   commits rather than committing a .git directory.

3. tests/test_determinism.py — audit both fixtures twice with the LLM stubbed
   off and assert byte-identical stable_payload(), then assert that enabling a
   stubbed LLM changes only prose fields. Never compare report.json bytes:
   generated_at and run_ms vary by design and are excluded from the payload.

4. tests/test_acceptance.py — assert clean-repo grades B or better with zero
   secret findings, and ugly-repo grades F with at least one finding on each of
   the five axis keys.

5. A canary test that proves the secret scanner can fail: write a key-shaped
   string into a temp fixture, assert the analyzer reports it, then assert the
   same repo without it reports nothing. A detector nobody has watched fail is
   decoration.

6. .github/workflows/ci.yml — on push and pull_request to the default branch.
   Jobs, each named and each with its run commands: lint running ruff, typecheck
   running mypy strict, secrets running scripts/check_secrets.sh, test running
   pytest with the coverage floor, and build running the wheel build. Set up
   Python 3.12 and uv explicitly. Confirm the trigger branch name matches this
   repository's actual default branch before committing the file.

7. After pushing, check that the workflow has a run history. An empty history
   reads exactly like a passing one.
```

### Checkpoint 16

- [ ] `agent-trust tests/fixtures/clean-repo --no-llm` grades B or better with zero secret findings
- [ ] `agent-trust tests/fixtures/ugly-repo --no-llm` grades F with at least one finding on each of the five axes
- [ ] The ugly repo's report shows `capped` True with `cap_reason` naming `blast_radius`
- [ ] Both fixtures audited twice produce byte-identical `stable_payload()`
- [ ] The canary test fails when the planted key is present and passes when removed
- [ ] `gh run list` shows at least one completed run, and every job is green
- [ ] The workflow's trigger branch matches the repository's default branch
- [ ] A full audit of a 5,000-file public repo finishes in under 60 seconds

---

## Service keys, by the prompt that first needs them

| Service | First needed | Placeholder OK? |
|---|---|---|
| `git` on PATH | 2b | N/A — a system binary, not a key |
| Anthropic API key | 14 | Yes — every prompt before 14 runs with `--no-llm`, and the tool ships usable without one |
| GitHub account (public clone) | 9 | N/A — public repos need no credential; do not add token auth |
| GitHub Actions | 16 | N/A — provided by the repository |
| PyPI token | 15 | Only if publishing; the build is complete without it |

There are no required secrets to start this build. That is deliberate: prompts 1
through 13 are fully executable and testable with no external account at all.

## Next

When Checkpoint 16 passes, the build is done. Hand off to the **harden** skill
for the A–G cascade — it is a separate discipline with its own gates, and much
of it will map differently for a CLI than for a web app. Do not inline it here
and do not compress it into a single "run the hardening" step.

Two carry-over notes for that handoff, both learned the expensive way on earlier
projects: check that CI has actually run rather than trusting a green-looking
empty history, and expect fixing one dead gate to reveal the next one behind it.
