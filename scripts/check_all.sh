#!/usr/bin/env bash
# Run every gate in order.
#
# This is the single implementation; the Makefile delegates here so the two can
# never drift, and so the gates run on a machine without `make`.
#
# Exit codes: 0 all gates passed · 1 a gate failed · 2 a gate could not run.
#
# A gate that cannot run is NOT a pass. On this project's development machine
# (Windows ARM64 with Application Control enabled) the ruff and mypy binaries
# are blocked from executing; they run in CI on Linux. This script reports that
# as BLOCKED, keeps going so the runnable gates still give signal, and exits 2
# at the end so nobody reads the run as green.

set -uo pipefail
cd "$(dirname "$0")/.." || exit 2

blocked=0

run() {
  local name="$1"; shift
  printf '\n=== %s ===\n' "$name"
  local output status
  output=$("$@" 2>&1); status=$?
  printf '%s\n' "$output" | tail -20

  if printf '%s' "$output" | grep -q "Application Control policy has blocked"; then
    printf '::: %s BLOCKED by Application Control — not run, not passed\n' "$name" >&2
    blocked=$((blocked + 1))
    return
  fi
  if [ "$status" -eq 2 ]; then
    printf '!!! %s could not run (exit 2) — broken, not clean\n' "$name" >&2
    exit 2
  fi
  if [ "$status" -ne 0 ]; then
    printf '!!! %s FAILED (exit %s)\n' "$name" "$status" >&2
    exit 1
  fi
}

run "lint"      uv run ruff check .
run "typecheck" uv run mypy agent_trust
run "secrets"   bash scripts/check_secrets.sh
run "test"      uv run python -m pytest

if [ "$blocked" -gt 0 ]; then
  printf '\n%s gate(s) BLOCKED on this machine. Runnable gates passed.\n' "$blocked" >&2
  printf 'This run is NOT green — the blocked gates run in CI.\n' >&2
  exit 2
fi

printf '\nAll gates passed.\n'
