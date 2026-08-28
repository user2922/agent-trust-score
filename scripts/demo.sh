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
beat() { printf '\n\033[2m── %s\033[0m\n\n' "$1"; sleep "$PAUSE"; }

# ── setup, silent ───────────────────────────────────────────────────────────
rm -rf "$DEMO" && mkdir -p "$DEMO"
uv run python scripts/build_fixtures.py "$DEMO" >/dev/null 2>&1 || {
  echo "could not build fixtures — run: uv sync --extra dev" >&2
  exit 1
}

clear
printf '\033[1mAgent Trust Score\033[0m — how safely can an agent work in this repo?\n'
sleep "$PAUSE"

# ── 1. the repo an agent should not touch ───────────────────────────────────
beat "A repository an agent should not touch"
$RUN "$DEMO/ugly-repo" --no-llm --no-cache --quiet --format md --out "$DEMO/ugly-out"
$RUN "$DEMO/ugly-repo" --no-llm --out "$DEMO/ugly-out" 2>/dev/null | head -20

# ── 2. it found a live credential, and never printed it ─────────────────────
beat "It found a committed credential — and never printed it"
grep -m2 -A2 'BR-01' "$DEMO/ugly-out/report.md" | sed -n '1,6p'
printf '\n\033[2mThe full key appears in no artifact:\033[0m\n'
# Assembled from fragments, so this script carries no literal the detector matches.
PLANTED="AKIA""Q7RSTUVWX1234567"
for f in "$DEMO"/ugly-out/report.md; do
  if grep -q "$PLANTED" "$f"; then
    printf '  \033[31mLEAKED in %s\033[0m\n' "$f"
  else
    printf '  clean: %s\n' "$(basename "$f")"
  fi
done
grep -o 'AKIA[^`]*' "$DEMO/ugly-out/report.md" | head -1 | sed 's/^/  shown as: /'

# ── 3. what good looks like ─────────────────────────────────────────────────
beat "The same tool on a well-prepared repository"
$RUN "$DEMO/clean-repo" --no-llm --no-cache --out "$DEMO/clean-out" 2>/dev/null | head -12

# ── 4. it grades itself ─────────────────────────────────────────────────────
beat "And on itself — the findings are real, not hidden"
$RUN . --no-llm --no-cache --out "$DEMO/self-out" 2>/dev/null | head -16

# ── 5. the CI gate ──────────────────────────────────────────────────────────
beat "Usable as a CI gate"
printf '$ agent-trust . --min-grade A --quiet\n'
$RUN . --no-llm --quiet --min-grade A --out "$DEMO/self-out" >/dev/null 2>&1
printf 'exit %s  (0 = passed the floor)\n' "$?"
printf '$ agent-trust %s/ugly-repo --min-grade B --quiet\n' "$DEMO"
$RUN "$DEMO/ugly-repo" --no-llm --quiet --min-grade B --out "$DEMO/ugly-out" >/dev/null 2>&1
printf 'exit %s  (2 = below the floor, build fails)\n' "$?"

printf '\n\033[2mReports: %s/*/report.md · MCP server: agent-trust-mcp\033[0m\n\n' "$DEMO"
