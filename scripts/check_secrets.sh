#!/usr/bin/env bash
# Scan this repository's own tracked files for key-shaped strings.
#
# Exit codes -- never collapse these into two:
#   0  scanned, clean
#   1  scanned, hit(s) found
#   2  could not scan -- broken, NOT clean
#
# A scanner that cannot tell "clean" from "did not run" reports a pass on an
# empty checkout for the life of the repo. Prove this one can fail: plant a
# key-shaped string, watch it go red, remove it.

set -uo pipefail

cd "$(dirname "$0")/.." || { echo "check-secrets: cannot reach repo root" >&2; exit 2; }

if ! command -v git >/dev/null 2>&1; then
  echo "check-secrets: git not found -- cannot enumerate tracked files" >&2
  exit 2
fi

# Tracked AND untracked-but-not-ignored files: a secret must be caught before it
# is committed, not after. Ignored files are out of scope by definition.
#
# Documentation legitimately contains the *patterns* this tool matches on, so it
# is excluded from the scan for literals; source code is not.
#
# tests/test_analyzers_secrets.py is the ONE source file excluded, and only
# because it is the detector's fixture corpus: it must hold real-shaped values
# carrying no placeholder marker, or the tests could not prove BR-01 catches
# them. Every value in it is synthetic. Keep this exclusion to that one path.
mapfile -t FILES < <(git ls-files --cached --others --exclude-standard -- \
  ':!:SPEC.md' ':!:SPEC_DRAFT.md' ':!:BUILD.md' ':!:CLAUDE.md' ':!:docs/*' \
  ':!:uv.lock' ':!:*.snap' ':!:tests/test_analyzers_secrets.py')

# A near-empty scan is indistinguishable from a broken one. This project has
# dozens of scannable files; anything under 5 means the enumeration is wrong.
MIN_FILES=5
if [ "${#FILES[@]}" -lt "$MIN_FILES" ]; then
  echo "check-secrets: only ${#FILES[@]} file(s) enumerated (expected >= ${MIN_FILES})" >&2
  echo "check-secrets: enumeration looks broken -- refusing to report a pass" >&2
  exit 2
fi

PATTERNS=(
  'AKIA[0-9A-Z]{16}'
  'gh[pousr]_[A-Za-z0-9]{36,}'
  'sk_live_[A-Za-z0-9]{20,}'
  'xox[baprs]-[A-Za-z0-9-]{10,}'
  'AIza[0-9A-Za-z_-]{35}'
  'sk-ant-[A-Za-z0-9_-]{32,}'
  '-----BEGIN [A-Z ]*PRIVATE KEY-----'
)

# Value markers that make a match a documented placeholder rather than a secret.
# Same rule SPEC.md specifies for the product itself: allowlist by VALUE, not by
# excluding whole directories. Excluding tests/ would let a real key hide there.
ALLOWLIST='EXAMPLE|PLACEHOLDER|CHANGEME|YOUR_|NOT_A_REAL|xxxx|0000|sk_test_|pk_test_|dummy'

hits=0
suppressed=0
for pattern in "${PATTERNS[@]}"; do
  if out=$(grep -nHE "$pattern" "${FILES[@]}" 2>/dev/null); then
    while IFS= read -r line; do
      if printf '%s' "$line" | grep -qE "$ALLOWLIST"; then
        suppressed=$((suppressed + 1))
        continue
      fi
      # Print location only. Never echo the matched value.
      echo "check-secrets: HIT ${line%%:*}:$(echo "$line" | cut -d: -f2) matches /${pattern}/" >&2
      hits=$((hits + 1))
    done <<< "$out"
  fi
done

if [ "$hits" -gt 0 ]; then
  echo "check-secrets: ${hits} hit(s) across ${#FILES[@]} file(s)" >&2
  exit 1
fi

# Always report the suppression count. A scan where the allowlist swallowed
# everything must not look identical to a scan that found nothing.
echo "check-secrets: clean -- ${#FILES[@]} file(s) scanned, ${suppressed} placeholder match(es) suppressed"
exit 0
