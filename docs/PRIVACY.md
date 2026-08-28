# Privacy

Short version: the tool sends nothing anywhere unless you give it an API key and
let the model pass run. There is no telemetry.

## What leaves your machine

**Nothing, by default.** With no `ANTHROPIC_API_KEY` set, or with `--no-llm`,
`agent-trust` performs a `git clone` (for a remote repository) and nothing else.
No analytics, no crash reporting, no usage counters, no phone-home.

**With the model pass enabled**, exactly one request goes to the Anthropic API
per audit. It contains:

- the scored report — grades, check statuses, findings and fixes;
- up to 40 evidence snippets, each at most 200 characters, **already redacted**;
- your agent instruction file and README, truncated to roughly 6,000 tokens.

It does not contain your source code beyond those snippets, your git history,
your environment, or any full secret value.

Anthropic is the only third party. Their handling of API requests is governed by
their own terms, which you should read if the repository you are auditing is
sensitive. If it is, use `--no-llm`: the scores are identical either way.

## Secrets found during a scan

When a secret is detected it is truncated at the moment of capture, inside
`redact.py`, to its first four and last two characters — `AKIA…7Q`. The full
value never enters the report, the JSON, the HTML, the cache, the terminal, a log
line, or the model prompt. Values shorter than eight characters are masked
entirely.

This is enforced rather than intended: the `Evidence` model rejects any snippet
over 200 characters or containing a control character, so a code path that
skipped redaction fails at construction instead of shipping a credential.

## What is stored locally

Reports are cached under `~/.cache/agent-trust` (override with
`AGENT_TRUST_CACHE_DIR`), one JSON file per commit SHA, for 24 hours. The cache
holds reports only — never repository contents, and never a snippet that was not
already redacted. Delete the directory at any time; the next run rebuilds it.

Remote repositories are cloned into a temporary directory that is removed on
every exit path, including failures and timeouts.

## What the tool never does

- It never executes code from the repository under audit: no dependency install,
  no build, no test run, and every clone disables git hooks.
- It never writes to the repository under audit.
- It never transmits a full secret value, to Anthropic or anywhere else.

## Reporting a problem

If you find a way to make this tool leak a credential into any output, please
open an issue. That is the defect class this project cares about most.
