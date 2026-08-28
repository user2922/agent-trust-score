# Agent Trust Score

Scores any git repository on how safely an autonomous coding agent can operate
inside it, and tells you what to fix first. It reads repositories; it never runs
their code.

```
uvx agent-trust-score https://github.com/your-org/your-repo
```

## Why

Teams are handing agents write access to codebases that were designed for
humans. Linters tell you whether the code is good. Nothing tells you whether an
agent can work in it safely — whether there are secrets in config, whether a
destructive migration has a dry-run flag, whether the test suite would catch the
agent's mistake, whether the README explains enough that the agent stops
guessing.

Here is `pallets/click` — a well-maintained, heavily used library:

```
Grade F  53/100

Axis             Score  Grade  Failed
Tool Surface        44    F         3
Blast Radius        71    C         2
Verifiability      100    A         0
Context Quality      5    F         7
Observability       47    F         4

Fix these first
  1. Run and test commands documented  10m, recovers 15 points
  2. Setup commands documented         15m, recovers 15 points
  3. Do-not-touch list                 10m, recovers 10 points
```

Perfect on Verifiability — the tests and CI are excellent. Near zero on Context
Quality, because there is no agent instruction file and the docs live somewhere
an agent will not look. That gap is the entire point: code quality and
agent-operability are different properties, and the second one is currently
unmeasured.

## Install and run

```
uvx agent-trust-score <repo>              # no install
pipx install agent-trust-score            # or install it
```

Grade a local checkout and write a markdown report:

```
agent-trust . --format md --out reports
```

Grade a remote repository, write all three formats, skip the model:

```
agent-trust https://github.com/pallets/click --no-llm --format md --format json --format html
```

Gate CI on a minimum grade:

```
agent-trust . --min-grade B --quiet     # exit 2 if the grade is worse than B
```

## Flags

| Flag | Default | Behaviour |
|---|---|---|
| `--axis KEY` (repeatable) | all five | Score only these axes |
| `--format md\|json\|html` (repeatable) | `md` | Which report files to write |
| `--out DIR` | `.` | Where to write them |
| `--no-llm` | off | Skip the explanation call entirely |
| `--min-grade LETTER` | none | Exit 2 if the grade is worse than this |
| `--allow-any-host` | off | Permit clone hosts off the allowlist |
| `--timeout SECONDS` | 60 | Whole-run budget |
| `--cache / --no-cache` | on | Reuse a cached report for the same commit |
| `--quiet` | off | Suppress the summary; still writes files |
| `--version` | — | Print the version |

Exit codes: `0` graded · `1` operational error · `2` graded but below
`--min-grade`. An unmeasurable repository exits 2 against any floor — a gate must
never read "could not measure" as "passed".

## From an agent, over MCP

```
agent-trust-mcp
```

Three tools: `audit_repo(source, axes, use_llm)`, `get_axis(source, axis)` and
`suggest_fixes(source, max_items)`. Errors cross the boundary as
`{"error": {"code", "message"}}`, never as a traceback.

## The five axes

**Tool surface** — can an agent call this code through typed, documented
interfaces, or must it screen-scrape and guess? MCP manifests, API schemas,
declared entry points, typed boundaries.

**Blast radius** — what happens if the agent acts? Committed secrets, tracked
`.env` files, destructive operations with no dry-run or confirmation, admin
credentials reachable from client code.

**Verifiability** — can the agent prove it did not break anything? A test suite
that exists, a runner it can invoke, and CI that actually runs the tests rather
than only linting.

**Context quality** — does the repo explain itself? An agent instruction file,
setup commands, an architecture summary, run and test commands, and whether the
paths the docs cite still exist.

**Observability** — can a human see what the agent did afterwards? Structured
logging, error reporting that is initialised rather than merely installed, an
audit trail, commit hygiene.

Each axis totals 100 points. The overall grade is the mean, except that any axis
below 40 caps it at 70, and a committed secret forces blast radius to at most 39.
A repository with a live credential in it is never agent-ready, whatever else it
does well.

Every check, with its weight and how to fix it: [`docs/CHECKS.md`](docs/CHECKS.md).

## What this does and does not tell you

**It reads. It never executes.** No dependency install, no build, no test run,
and clones disable git hooks. Auditing an untrusted repository is the normal
case, so that boundary is enforced rather than assumed.

**The scores are deterministic.** Every check is static analysis — file patterns,
manifest parsing, regexes, git metadata. The same commit produces the same
scores on any machine, whether or not a model is involved.

**The model only writes prose.** With an `ANTHROPIC_API_KEY` set, one Claude call
writes the explanations and fix steps. It cannot change a score, a status, a
severity, or the order of the fix list — the merge asserts that and refuses the
result otherwise. Without a key the tool runs identically and uses written-in
explanations. `--no-llm` is a complete product, not a degraded one.

**This is not a security audit and it certifies nothing.** A passing grade is
evidence about a repository's *structure*: that certain files exist, that certain
patterns are present or absent. It is not a guarantee that the code is safe, that
there are no secrets, or that an agent will behave. A static scan misses secrets
that do not look like secrets, guards it cannot recognise, and risks that live in
logic rather than in structure. Treat the grade as a starting point for a
conversation, not as an answer.

**Detection is best-effort and stated.** Every failing check reports what it
searched for, so you can see the method and disagree with it. BR-05 says outright
that it judges reachability by path convention rather than by import graph. When
the allowlist suppresses a possible secret, the count is reported rather than
hidden.

## Privacy

The tool sends nothing anywhere unless the model pass runs. When it does, it
sends the scored report, redacted evidence snippets and your README and agent
doc to the Anthropic API — nothing else, and no full secret value ever. No
telemetry, no analytics. Details in [`docs/PRIVACY.md`](docs/PRIVACY.md).

## Development

```
uv sync --extra dev
uv run python -m pytest
bash scripts/check_all.sh
```

`CLAUDE.md` carries the standing rules; `docs/FILE_LIST.md` maps every file to
the build phase that created it.

## Licence

MIT. See [`LICENSE`](LICENSE).
