#!/usr/bin/env bash
# C43 fence — test harness (boundary-typing half).
#
# Runs classify_action.py over every fixture and asserts the expected verdict
# (allow => exit 0, refuse => exit 1) and the expected blast_radius_class.
# Exits non-zero on any mismatch. python3 + bash only; offline; no pip.
set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
CLASSIFY="$HERE/classify_action.py"
FIX="$HERE/fixtures"

fails=0

# assert <fixture> <expected_verdict> <expected_class>
assert() {
  fixture="$1"; want_verdict="$2"; want_class="$3"
  out="$(python3 "$CLASSIFY" "$FIX/$fixture" 2>&1)"
  rc=$?

  if [ "$want_verdict" = "allow" ]; then want_rc=0; else want_rc=1; fi

  got_verdict="$(printf '%s' "$out" | python3 -c 'import sys,json; print(json.load(sys.stdin)["verdict"])' 2>/dev/null)"
  got_class="$(printf '%s' "$out" | python3 -c 'import sys,json; print(json.load(sys.stdin)["blast_radius_class"])' 2>/dev/null)"

  if [ "$rc" -ne "$want_rc" ] || [ "$got_verdict" != "$want_verdict" ] || [ "$got_class" != "$want_class" ]; then
    echo "FAIL $fixture"
    echo "  want: verdict=$want_verdict class=$want_class exit=$want_rc"
    echo "  got : verdict=$got_verdict class=$got_class exit=$rc"
    echo "  output: $out"
    fails=$((fails + 1))
  else
    echo "ok   $fixture -> $got_verdict ($got_class) exit=$rc"
  fi
}

echo "== C43 fence: blast-radius typing over rig partitions =="
assert "in-bounds-sandbox-read.json"  "allow"  "in_bounds"
assert "in-bounds-sandbox-write.json" "allow"  "in_bounds"
assert "cross-partition-write.json"   "refuse" "cross_partition_write"
assert "production-action.json"       "refuse" "production_action"

echo
if [ "$fails" -eq 0 ]; then
  echo "PASS: all fixtures classified as expected"
  exit 0
else
  echo "FAIL: $fails fixture(s) mismatched"
  exit 1
fi
