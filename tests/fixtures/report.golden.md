# Agent Trust Score — https://github.com/example/demo

**Grade C** — 70/100

> **Capped.** Blast Radius scored 7, below 40; overall is capped at 70.

| Axis | Score | Grade | Failed checks |
|---|---:|:---:|---:|
| Tool Surface | 86 | B | 0 |
| Blast Radius | 7 | F | 3 |
| Verifiability | 100 | A | 0 |
| Context Quality | 92 | A | 0 |
| Observability | N/A | N/A | 0 |

Commit `a1b2c3d4e5f6` on `master` · 118 of 412 tracked files analyzed · **truncated: this audit did not see the whole repository**
Languages: Python (84), TypeScript (30), Markdown (4)
---

## Fix these first

Ordered by points recovered per hour of effort.

| # | Fix | Axis | Points | Effort | Points/hour |
|---:|---|---|---:|---:|---:|
| 1 | .env not tracked | blast_radius | 12 | 15m | 48.0 |
| 2 | No committed secrets | blast_radius | 30 | 45m | 40.0 |
| 3 | Ownership config | blast_radius | 5 | 10m | 30.0 |
| 4 | gitignore covers sensitive paths | blast_radius | 4 | 10m | 24.0 |
| 5 | Docs resolve to reality | context_quality | 3 | 20m | 9.0 |
| 6 | Typed public boundaries | tool_surface | 8 | 4h | 2.0 |

**1. .env not tracked** — 15m, recovers 12 points

- Untrack the .env file with `git rm --cached`.
- Add it to .gitignore and rotate anything it contained.

**2. No committed secrets** — 45m, recovers 30 points

- Rotate the exposed credential now -- it is in every clone and in history.
- Remove it from the working tree and move the value to an environment variable.
- Purge it from history, or treat the repository as compromised.

**3. Ownership config** — 10m, recovers 5 points

- Add a CODEOWNERS file so changes need a named reviewer.

**4. gitignore covers sensitive paths** — 10m, recovers 4 points

- Add .env, key and credential patterns, and build output to .gitignore.

**5. Docs resolve to reality** — 20m, recovers 3 points

- Update the paths cited in the agent doc so they resolve.

**6. Typed public boundaries** — 4h, recovers 8 points

- Enable strict type checking and annotate the public functions first.

---

## Tool Surface — 86 (B)

| Check | Status | Weight | Detail |
|---|:---:|---:|---|
| `TS-01` MCP server declared | pass | 20 |  |
| `TS-02` Machine-readable API schema | pass | 20 |  |
| `TS-05` Typed public boundaries | partial | 15 | 42% annotated |
| `TS-06` Parseable package manifest | n/a | 10 | no manifest |

**`TS-05` · low — Typed public boundaries**

Partially satisfied. Untyped public boundaries give an agent nothing to check its calls against before running them.

## Blast Radius — 7 (F)

| Check | Status | Weight | Detail |
|---|:---:|---:|---|
| `BR-01` No committed secrets | FAIL | 30 | 1 match, 3 placeholders suppressed |
| `BR-02` .env not tracked | FAIL | 12 |  |
| `BR-03` gitignore covers sensitive paths | partial | 8 |  |
| `BR-07` Ownership config | FAIL | 5 |  |

**`BR-01` · high — No committed secrets**

A committed secret is live credential material in every clone, and an agent with repository access can read and transmit it.

- `config/settings.py:12` — `AWS_KEY = "AKIA…LE"`
**`BR-02` · medium — .env not tracked**

A tracked .env file puts real environment values in history where they outlive any later deletion.

**`BR-03` · low — gitignore covers sensitive paths**

Partially satisfied. Without .gitignore coverage the next careless `git add -A` commits credentials.

**`BR-07` · low — Ownership config**

With no ownership or protection config, nothing forces review of a change an agent proposes.

## Verifiability — 100 (A)

| Check | Status | Weight | Detail |
|---|:---:|---:|---|
| `VF-01` Test suite exists | pass | 20 |  |
| `VF-05` CI actually runs tests | pass | 15 |  |

No findings on this axis.

## Context Quality — 92 (A)

| Check | Status | Weight | Detail |
|---|:---:|---:|---|
| `CQ-02` README with substance | pass | 10 | README begins: <script>alert('xss')</script> |
| `CQ-05` Run and test commands | pass | 15 |  |
| `CQ-08` Docs resolve to reality | partial | 5 | 3 of 5 paths resolve |

**`CQ-08` · low — Docs resolve to reality**

Partially satisfied. Documentation pointing at files that no longer exist is worse than none, because the agent trusts it.

## Observability — N/A (N/A)

| Check | Status | Weight | Detail |
|---|:---:|---:|---|
| `OB-01` Structured logging | n/a | 25 | no source files |

No findings on this axis.

---

Generated 2026-01-15 09:30 UTC · schema 1.0 · template explanations (no ANTHROPIC_API_KEY configured)
This report grades repository structure. It is not a security audit, and a
passing grade certifies nothing.
