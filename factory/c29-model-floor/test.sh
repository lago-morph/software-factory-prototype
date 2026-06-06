#!/usr/bin/env bash
# C29 model-floor policy-engine test harness (sweep-1).
# Runs route.py over fixtures and asserts expected resolutions.
# python3 + bash only. Exits non-zero on any mismatch.
set -u

DIR="$(cd "$(dirname "$0")" && pwd)"
ROUTE="$DIR/route.py"
FIX="$DIR/fixtures"
FAILS=0

# run_case <fixture> <expected_exit>  -> echoes stdout, sets RC
run_case() {
  OUT="$(python3 "$ROUTE" "$FIX/$1" 2>/dev/null)"
  RC=$?
  if [ "$RC" -ne "$2" ]; then
    echo "FAIL [$1]: expected exit $2, got $RC"
    FAILS=$((FAILS + 1))
  fi
}

# assert that the JSON stdout (in $OUT) contains a substring
assert_contains() {
  if ! printf '%s' "$OUT" | grep -q -- "$1"; then
    echo "FAIL [$2]: stdout missing expected token: $1"
    echo "----- stdout was -----"
    printf '%s\n' "$OUT"
    echo "----------------------"
    FAILS=$((FAILS + 1))
  fi
}

echo "== C29 model-floor policy-engine tests =="

# 1) clean route: coder/architect -> opus, no upgrade, exit 0
run_case "clean.json" 0
assert_contains '"resolved_model": "claude-opus-4-8"' "clean.json"
assert_contains '"upgraded": false' "clean.json"

# 2) below-floor: haiku pin upgraded to sonnet floor, exit 0
run_case "below-floor.json" 0
assert_contains '"resolved_model": "claude-sonnet-4-6"' "below-floor.json"
assert_contains '"upgraded": true' "below-floor.json"
assert_contains 'BELOW FLOOR' "below-floor.json"

# 3) cross-family advisory: judge same-family, required=false, exit 0
run_case "cross-family.json" 0
assert_contains '"cross_family_required": false' "cross-family.json"
assert_contains '"same_family": true' "cross-family.json"
assert_contains 'ADVISORY' "cross-family.json"

if [ "$FAILS" -eq 0 ]; then
  echo "OK: all assertions passed"
  exit 0
else
  echo "FAILED: $FAILS assertion(s)"
  exit 1
fi
