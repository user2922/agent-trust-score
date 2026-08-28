# Build status

Read this, `CLAUDE.md` and `SPEC.md` at the start of every session.

| Prompt | Phase | Status |
|---|---|---|
| 1 | Spec validation & project setup | **DONE** — Checkpoint 1 passed 8/8 |
| 2a | Project setup & toolchain | **DONE** - Checkpoint 2a passed 8/8 |
| 2b | Safety foundation | **DONE** - Checkpoint 2b passed 8/8 |
| 3 | Report schema | **DONE** - Checkpoint 3 passed 8/8 |
| 4 | Inventory & RepoContext | **DONE** - Checkpoint 4 passed 8/8 |
| 5 | Scoring engine | **DONE** - Checkpoint 5 passed 8/8 |
| 6 | Renderers | **DONE** - Checkpoint 6 passed 8/8 |
| 7 | CLI, MCP server, cache | **DONE** - Checkpoint 7 passed 10/10 |
| 8 | Analyzer framework + Tool Surface | **DONE** - Checkpoint 8 passed 8/8 |
| 9 | Blast Radius: secrets | **DONE** - Checkpoint 9 passed 8/8 |
| 10 | Blast Radius: destructive ops | next |
| 11 | Verifiability | — |
| 12 | Context Quality | — |
| 13 | Observability | — |
| 14 | LLM enrichment | — |
| 15 | Packaging, docs, polish | — |
| 16 | Testing, fixtures, CI | — |

## Decisions made in Prompt 1

- **37 checks, not 35.** The draft claimed 35 in five places; the tables always
  held 37 (TS 7, BR 7, VF 8, CQ 8, OB 7). Corrected everywhere. All five axes
  sum to 100, no duplicate ids, every id has a stated pass condition.
- **Determinism is asserted over `stable_payload()`**, not `report.json` bytes.
  `generated_at` and `run_ms` vary by design, so the original wording was
  unsatisfiable.
- **`--fix` is out of v1.** It was in the flag table but no prompt built it.
  Recorded under Stretch.
- **Cache key is commit SHA + schema version**, and a cached `--no-llm` report
  is a miss when enrichment is requested.
- **Empty repos, unclonable repos and oversized repos** now have defined
  behaviour — see the resolved-gaps table in `SPEC.md`.
- `spec.md` was renamed `SPEC_DRAFT.md`: on Windows it collided case-insensitively
  with the `SPEC.md` this prompt writes.

## Environment

Verified present: git 2.53.0 · Python 3.12.10 · uv 0.12.7 · node v25.8.1.
No `ANTHROPIC_API_KEY` configured — not needed until Prompt 14, and the tool
ships usable without one.

## Decisions made in Prompt 2a

- **Every remembered version pin was wrong.** Resolved and pinned what actually
  installs: typer 0.27.2 (was 0.15.1), rich 15.0.0 (13.9.4), pydantic 2.13.4
  (2.10.4), **mcp 2.1.1 (1.2.0 - a major version)**, jinja2 3.1.6, pytest 9.1.1
  (8.3.4), ruff 0.16.5 (0.9.x), mypy 2.3.1 (1.14.x). anthropic 1.2.0 was right.
  Prompt 7 must treat the MCP SDK as 2.x and check its API against the installed
  package rather than recalled 1.x shapes.
- **`cryptography` pinned to 46.0.3.** It arrives transitively via
  `mcp -> pyjwt[crypto]`. Version 47+ ships no `win_arm64` wheel, and this
  machine has no MSVC linker for the Rust source build. 46.0.3 is the newest
  release with an arm64 wheel.
- **`redact.py` and `errors.py` moved from Prompt 2b to 2a.** `logging.py` needs
  redaction and `config.py` needs an exception type; the alternative was a stub,
  which standing rule 9 forbids. Prompt 2b still adds `snippet()` and the
  acquisition errors. The ordering constraint (redaction before any content
  reader) is strengthened, not weakened.
- **`make` is not installed**, so the Makefile alone would have been an inert
  gate. `scripts/check_all.sh` is the single implementation; the Makefile
  delegates to it.
- **ruff and mypy cannot execute on this machine** - Windows Application Control
  blocks the ruff binary and mypy's compiled extension. Installing mypy from
  sdist did not help. `check_all.sh` reports them BLOCKED and exits 2, so a run
  is never mistaken for green. **They have no local signal until the repo reaches
  CI.**
- **Secret scanner canary-verified in both directions**: clean at baseline, exit
  1 on a planted key-shaped value with no placeholder marker, clean again once
  removed. It scans tracked *and* untracked-not-ignored files, allowlists by
  value marker rather than by excluding `tests/`, always reports its suppression
  count, and exits 2 when it enumerates fewer than 5 files.
- **One real bug caught by the tests**: the control-character regex listed the
  bare ESC character before the ANSI-sequence alternative, so it stripped the ESC and left
  `[31m` as visible text. Ordering fixed.
- Three Checkpoint 2a items were unverifiable as written (they invoked
  `agent-trust`, whose `cli.py` is Prompt 7's file). Rewritten to assert the same
  behaviour at the layer that exists; the CLI form moved to Checkpoint 7.

## CI moved earlier (was Prompt 16)

Pushed to `github.com/user2922/agent-trust-score` (private) after Prompt 2a.
Reason: ruff and mypy cannot execute on the development machine, so they had no
signal at all; on Linux CI they do. Five named jobs — lint, typecheck, secrets,
test, build — triggering on `master`, which is this repo's actual default branch.

**Verified it has actually run**, not merely that the file exists: `gh run list`
shows runs, and the first one was red. It found three defects invisible locally
(E501, an unused `type: ignore`, and a `ruff format` divergence). Green as of
run 33179088546.

From here every prompt pushes, and CI is the lint/typecheck gate. Prompt 16 now
extends this workflow with the e2e/determinism jobs rather than creating it.

## Gate tooling — resolved after Prompt 2b

The Application Control block on `ruff` and `mypy` cleared once the packages were
reinstalled (`mypy` now reports `compiled: no` — the pure-Python build). Both run
locally again, so `scripts/check_all.sh` gives full local signal and the BLOCKED
path in it is now a safety net rather than the normal case. Do not delete that
path: it is what stops a blocked tool from ever reading as a pass.

`black` stays in the dev extras as the local formatter. It is pure Python, so it
survives an Application Control block that would stop `ruff format`, and its
output is what `ruff format --check` accepts. CI verifies with ruff either way.

## Decisions made in Prompt 7

- **mcp 2.x confirmed incompatible with recalled 1.x code.** `FastMCP` is gone;
  it is `MCPServer` from `mcp.server.mcpserver`. The SDK raises a
  `ModuleNotFoundError` naming the migration guide, which is how this was
  caught. Tool metadata also uses `input_schema`, not `inputSchema`.
- **`peek_commit_sha` uses `git ls-remote`**, so a cache hit costs no clone at
  all rather than paying for one to discover the clone was unnecessary.
- **Cache key is SHA + schema version**, and a template-only entry is a miss when
  enrichment is requested. Writes are atomic (temp file + rename).
- **`--min-grade` exits 2 on an unmeasured repo.** A CI gate must never read
  "could not measure" as "passed".
- **The empty state distinguishes unmeasured from clean.** "Nothing to fix.
  Every check passed" would be the most dangerous sentence this product could
  print while the analyzer registry is still empty.
- The analyzer registry moved to Prompt 7 (from 8) because the pipeline has to
  iterate something. Prompt 8 fills it; the empty registry yields five N/A axes.

## Spot check - detector accuracy (after Prompt 9)

- **Zero false secrets on three real public repos**: psf/requests (124 files),
  pallets/click (163), tiangolo/typer (769). One of the four hackathon success
  criteria, verified early rather than assumed.
- **Every provider pattern catches its planted key** - 12 parametrized positives.
- **Redaction verified across every artifact**: a repo with a planted AWS key and
  GitHub token produced report.md, report.json and report.html with **zero**
  full-value occurrences. The report shows `AKIA...67`.
- **Entropy alone is not a secret detector.** "the quick brown fox jumps over the
  lazy dog" is a pangram, so it scores ABOVE the entropy threshold. Credential
  material contains no whitespace; that structural rule runs first and does most
  of the work. Regression guard in tests/test_analyzers_secrets.py.
- `tests/test_analyzers_secrets.py` is the one source file excluded from the
  repo's own scanner - it is the fixture corpus and must hold real-shaped values
  with no placeholder marker. Every value in it is synthetic.
- The tool flagged its own `.gitignore` for missing credential patterns (BR-03
  partial). Fixed by taking the advice; blast_radius is now 100.
