#!/usr/bin/env bash
# The demo, paced for a screen recording.
#
#   bash scripts/demo.sh          # paced, pauses between beats
#   bash scripts/demo.sh --fast   # no pauses, for a rehearsal
#
# Everything runs locally against generated fixtures with --no-llm, so it needs
# no API key, no network, and costs nothing. Nothing here is pre-recorded: every
# number on screen is computed while you watch.

set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

PAUSE=2.5
[ "${1:-}" = "--fast" ] && PAUSE=0

# Prefer an installed console script; fall back to the project environment.
if command -v agent-trust >/dev/null 2>&1; then
  RUN="agent-trust"
else
  RUN="uv run agent-trust"
fi

DEMO=".demo"
DIM=$'\033[2m'; OFF=$'\033[0m'; BOLD=$'\033[1m'
GREEN=$'\033[32m'; RED=$'\033[31m'

beat() {
  printf '\n%s── %s%s\n\n' "$DIM" "$1" "$OFF"
  sleep "$PAUSE"
}

# ── setup, silent ───────────────────────────────────────────────────────────
rm -rf "$DEMO" && mkdir -p "$DEMO"
if ! uv run python scripts/build_fixtures.py "$DEMO" >/dev/null 2>&1; then
  echo "could not build fixtures — run: uv sync --extra dev" >&2
  exit 1
fi

clear
printf '%sAgent Trust Score%s — how safely can an agent work in this repository?\n' "$BOLD" "$OFF"
sleep "$PAUSE"

# ── 1 · the repository an agent should not touch ────────────────────────────
beat "A repository an agent should not touch"
$RUN "$DEMO/ugly-repo" --no-llm --no-cache \
  --format md --format json --format html --out "$DEMO/ugly-out" 2>/dev/null | head -20

# ── 2 · it found a credential, and never printed it ─────────────────────────
beat "It found a committed credential — and never printed it"
sed -n '/^\*\*`BR-01`/p; /^- `.*AKIA/p' "$DEMO/ugly-out/report.md" | head -4

PLANTED="AKIA""Q7RSTUVWX1234567"          # assembled: no literal in this file
ARTIFACTS=$(find "$DEMO/ugly-out" -type f | wc -l | tr -d ' ')
LEAKS=$(grep -rl "$PLANTED" "$DEMO/ugly-out" 2>/dev/null | wc -l | tr -d ' ')

printf '\n%sThe planted key is 20 characters. Grep all %s artifacts for it:%s\n' \
  "$DIM" "$ARTIFACTS" "$OFF"
if [ "$LEAKS" = "0" ]; then
  printf '  %s0 leaks%s — markdown, JSON and HTML. Redaction happens at capture,\n' "$GREEN" "$OFF"
  printf '  not at render, so no code path downstream can leak it.\n'
else
  printf '  %s%s LEAK(S)%s\n' "$RED" "$LEAKS" "$OFF"
fi

# ── 3 · what good looks like ────────────────────────────────────────────────
beat "The same tool on a well-prepared repository"
$RUN "$DEMO/clean-repo" --no-llm --no-cache --out "$DEMO/clean-out" 2>/dev/null | head -16

# ── 4 · it grades itself ────────────────────────────────────────────────────
beat "And on itself — the remaining findings are real, not hidden"
$RUN . --no-llm --no-cache --out "$DEMO/self-out" 2>/dev/null | head -16

# ── 5 · the CI gate ─────────────────────────────────────────────────────────
beat "Usable as a CI gate"
printf '$ agent-trust . --min-grade A --quiet\n'
$RUN . --no-llm --quiet --min-grade A --out "$DEMO/self-out" >/dev/null 2>&1
printf 'exit %s   (0 — passed the floor)\n\n' "$?"
printf '$ agent-trust %s/ugly-repo --min-grade B --quiet\n' "$DEMO"
$RUN "$DEMO/ugly-repo" --no-llm --quiet --min-grade B --out "$DEMO/ugly-out" >/dev/null 2>&1
printf 'exit %s   (2 — below the floor, the build fails)\n' "$?"

printf '\n%sReports in %s/*/report.html · MCP server: agent-trust-mcp%s\n\n' \
  "$DIM" "$DEMO" "$OFF"
