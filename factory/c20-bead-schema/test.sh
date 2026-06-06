#!/usr/bin/env bash
# C20 bead-type schema — test harness.
#
# Runs validate_bead.py over every fixture and asserts the expected verdict
# (valid => exit 0, invalid => exit non-zero), keyed off the fixture filename
# prefix: "valid-*" must pass, "invalid-*" must fail. Prints a summary and
# exits non-zero on any mismatch. python3 + bash only; offline; no pip.
#
# Gate B1 exit criterion: "the schema accepts a valid bead and rejects an
# ill-typed one." This harness is the executable form of that check.
set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
VALIDATE="$HERE/validate_bead.py"
FIX="$HERE/fixtures"

fails=0
n_valid=0
n_invalid=0

echo "== C20 bead-type schema: validate every fixture =="

for fixture in "$FIX"/*.json; do
  base="$(basename "$fixture")"
  case "$base" in
    valid-*)   want="valid";   want_rc=0 ;;
    invalid-*) want="invalid"; want_rc=1 ;;
    *)
      echo "FAIL $base : fixture name must start with 'valid-' or 'invalid-'"
      fails=$((fails + 1))
      continue
      ;;
  esac

  out="$(python3 "$VALIDATE" "$fixture" 2>&1)"
  rc=$?

  if [ "$rc" -eq "$want_rc" ]; then
    [ "$want" = "valid" ] && n_valid=$((n_valid + 1)) || n_invalid=$((n_invalid + 1))
    echo "ok   $base -> want=$want exit=$rc"
  else
    echo "FAIL $base"
    echo "  want: $want (exit=$want_rc)"
    echo "  got : exit=$rc"
    echo "  output: $out"
    fails=$((fails + 1))
  fi
done

echo
if [ "$fails" -eq 0 ]; then
  echo "PASS: ${n_valid} valid accepted, ${n_invalid} invalid rejected, 0 mismatches"
  exit 0
else
  echo "FAIL: $fails fixture(s) mismatched"
  exit 1
fi
