# The checks

Generated from the `CheckSpec` tables by `scripts/generate_checks_doc.py`.
Do not edit by hand — run the script.

Every axis totals 100 points, asserted at import time. The overall grade is the
mean of the scored axes, except that any axis below 40 caps the overall at 70,
and a committed secret forces `blast_radius` to at most 39.

A check that cannot apply to a repository returns `not_applicable` and leaves
the axis denominator, so it is never scored as a failure.


## Tool Surface

| ID | Check | Weight | Effort | Why it matters |
|---|---|---:|---:|---|
| `TS-01` | MCP server declared | 20 | 2h | Without a declared MCP server an agent has no typed way to call this code, so it falls back to guessing at shell commands. |
| `TS-02` | Machine-readable API schema | 20 | 3h | With no machine-readable API schema an agent infers request shapes from source, and infers them wrong at the edges. |
| `TS-03` | CLI entry point declared | 15 | 45m | No declared CLI entry point means an agent cannot discover how to invoke this project without reading the source. |
| `TS-04` | Entry points documented | 10 | 20m | Entry points that are not documented get called with invented flags. |
| `TS-05` | Typed public boundaries | 15 | 4h | Untyped public boundaries give an agent nothing to check its calls against before running them. |
| `TS-06` | Parseable package manifest | 10 | 15m | A package manifest that does not parse hides the dependency and script information an agent needs to orient. |
| `TS-07` | Documented config contract | 10 | 20m | With no documented config contract an agent cannot tell which environment variables are required. |

Axis total: 100.

<details><summary>How to fix each one</summary>

- **TS-01**
  - Add an MCP server exposing your main operations as typed tools.
- **TS-02**
  - Publish an OpenAPI or GraphQL schema for the public surface.
- **TS-03**
  - Declare a console entry point in the package manifest.
- **TS-04**
  - Add a usage block to the README showing a real invocation with flags.
- **TS-05**
  - Enable strict type checking and annotate the public functions first.
- **TS-06**
  - Fix the package manifest so it parses.
- **TS-07**
  - Add a .env.example listing every variable with a placeholder value.

</details>

## Blast Radius

| ID | Check | Weight | Effort | Why it matters |
|---|---|---:|---:|---|
| `BR-01` | No committed secrets | 30 | 45m | A committed secret is live credential material in every clone, and an agent with repository access can read and transmit it. |
| `BR-02` | .env not tracked | 12 | 15m | A tracked .env file puts real environment values in history where they outlive any later deletion. |
| `BR-03` | .gitignore covers sensitive paths | 8 | 10m | Without .gitignore coverage the next careless `git add -A` commits credentials. |
| `BR-04` | Destructive operations guarded | 20 | 1h | An unguarded destructive operation is one confident agent action away from data loss, with no dry run to catch it first. |
| `BR-05` | No admin credential in reachable code | 15 | 1h | An admin-scoped credential reachable from client code bypasses every access control behind it. |
| `BR-06` | Side effects behind a test or env switch | 10 | 1h | Payment, email and webhook calls with no test-mode switch send real messages and move real money during development. |
| `BR-07` | Ownership or protection config | 5 | 10m | With no ownership or protection config, nothing forces review of a change an agent proposes. |

Axis total: 100.

<details><summary>How to fix each one</summary>

- **BR-01**
  - Rotate the exposed credential now -- it is in every clone and in history.
  - Remove it from the working tree and move the value to an environment variable.
  - Purge it from history, or treat the repository as compromised.
- **BR-02**
  - Untrack the .env file with `git rm --cached`.
  - Add it to .gitignore and rotate anything it contained.
- **BR-03**
  - Add .env, key and credential patterns, and build output to .gitignore.
- **BR-04**
  - Add a --dry-run flag that prints the plan without executing it.
  - Require an explicit confirmation or environment gate for the real run.
- **BR-05**
  - Move the admin credential server-side and give client code a scoped one.
- **BR-06**
  - Put payment, email and webhook calls behind a test-mode switch.
- **BR-07**
  - Add a CODEOWNERS file so changes need a named reviewer.

</details>

## Verifiability

| ID | Check | Weight | Effort | Why it matters |
|---|---|---:|---:|---|
| `VF-01` | Test suite exists | 20 | 8h | With no test suite an agent cannot tell a working change from a broken one, and neither can you. |
| `VF-02` | Test runner declared | 15 | 15m | An undeclared test runner means an agent has to guess the command, and a wrong guess reads as a passing run. |
| `VF-03` | Test density | 15 | 8h | Test coverage this thin leaves most of the codebase unverified after any agent edit. |
| `VF-04` | CI config present | 15 | 30m | No CI configuration means nothing checks a change except the person who wrote it. |
| `VF-05` | CI actually runs tests | 15 | 15m | A CI pipeline that never runs the tests is decoration: it goes green regardless of whether the code works. |
| `VF-06` | Type checking configured | 10 | 1h | Without type checking, a whole class of agent mistake reaches runtime instead of the editor. |
| `VF-07` | Lint configured | 5 | 20m | No lint configuration means style and correctness drift accumulate unreviewed. |
| `VF-08` | Commit-time gate | 5 | 20m | With no commit-time gate, a broken change reaches the branch before anything objects. |

Axis total: 100.

<details><summary>How to fix each one</summary>

- **VF-01**
  - Add a test suite, starting with the paths an agent is most likely to edit.
- **VF-02**
  - Declare the test runner in the package manifest.
- **VF-03**
  - Raise test coverage of the modules that change most often.
- **VF-04**
  - Add a CI workflow that runs on push and pull request.
- **VF-05**
  - Add a step to the CI workflow that actually runs the test suite.
- **VF-06**
  - Turn on strict type checking and fix what it reports.
- **VF-07**
  - Add a lint configuration and wire it into CI.
- **VF-08**
  - Add a pre-commit hook running lint and type checks.

</details>

## Context Quality

| ID | Check | Weight | Effort | Why it matters |
|---|---|---:|---:|---|
| `CQ-01` | Agent instruction file exists | 20 | 45m | With no agent instruction file, every session starts from zero and rediscovers the same conventions differently. |
| `CQ-02` | README with substance | 10 | 30m | A README this thin gives an agent no orientation, so it infers the architecture from whichever file it opens first. |
| `CQ-03` | Setup commands documented | 15 | 15m | Undocumented setup commands mean an agent guesses at the install sequence and reports success it did not achieve. |
| `CQ-04` | Architecture summary | 15 | 30m | With no architecture summary an agent has to reconstruct the design from source every time. |
| `CQ-05` | Run and test commands documented | 15 | 10m | Undocumented run and test commands are the single most common cause of an agent declaring work done without verifying it. |
| `CQ-06` | Conventions stated | 10 | 20m | Unstated conventions get violated, and the violations look like ordinary code in review. |
| `CQ-07` | Do-not-touch list | 10 | 10m | With no do-not-touch list an agent edits generated files, and the edits vanish at the next build. |
| `CQ-08` | Docs resolve to reality | 5 | 20m | Documentation pointing at files that no longer exist is worse than none, because the agent trusts it. |

Axis total: 100.

<details><summary>How to fix each one</summary>

- **CQ-01**
  - Add a CLAUDE.md or AGENTS.md describing setup, architecture and conventions.
- **CQ-02**
  - Expand the README past a stub: what it is, how to run it, how it fits together.
- **CQ-03**
  - Document the exact setup commands, copy-pasteable.
- **CQ-04**
  - Add an architecture section: the directory map and what each part owns.
- **CQ-05**
  - Document the commands to run the app and to run the tests.
- **CQ-06**
  - Write down the conventions a new contributor would otherwise violate.
- **CQ-07**
  - List the generated and vendored paths that must not be edited by hand.
- **CQ-08**
  - Update the paths cited in the agent doc so they resolve.

</details>

## Observability

| ID | Check | Weight | Effort | Why it matters |
|---|---|---:|---:|---|
| `OB-01` | Structured logging | 25 | 1h | Without structured logging there is no record of what an agent-driven process actually did. |
| `OB-02` | Logging rather than printing | 10 | 1h | Print statements scattered where logging belongs mean the useful output is unfiltered and unsearchable. |
| `OB-03` | Error reporting wired | 20 | 45m | With no error reporting, a failure an agent introduces surfaces as a user complaint rather than an alert. |
| `OB-04` | Audit trail pattern | 15 | 2h | No audit trail means no way to reconstruct which actor changed what, after the fact. |
| `OB-05` | Commit hygiene | 15 | 30m | Commit subjects this thin make the history useless for working out when a behaviour changed. |
| `OB-06` | Changelog | 5 | 20m | With no changelog there is no human-readable record of what shipped. |
| `OB-07` | Liveness surface | 10 | 20m | No health or version surface means nothing can confirm which build is actually running. |

Axis total: 100.

<details><summary>How to fix each one</summary>

- **OB-01**
  - Adopt a structured logger and route existing output through it.
- **OB-02**
  - Replace print and console.log calls in application code with logger calls.
- **OB-03**
  - Wire an error reporter and initialize it at startup.
- **OB-04**
  - Record actor, action and timestamp for every state-changing operation.
- **OB-05**
  - Write commit subjects that say what changed and why.
- **OB-06**
  - Add a CHANGELOG recording what shipped in each release.
- **OB-07**
  - Expose a health endpoint, or a --version flag on the CLI.

</details>

---

37 checks across 5 axes.
