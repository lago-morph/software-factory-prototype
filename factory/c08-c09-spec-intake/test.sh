#!/usr/bin/env bash
# C08+C09 spec-intake — test harness.
#
# Gate B1 exit criterion: "a toy spec round-trips spec -> prompt."
# This harness:
#   1. validates the VALID toy spec   (expect exit 0)
#   2. rejects the INVALID spec        (expect non-zero; missing DoD / E-C08-02)
#   3. renders the toy spec through the worker template and asserts the
#      rendered prompt actually contains values bound FROM the spec
#      (the spec->prompt round-trip)
#   4. asserts bind_prompt refuses to render the INVALID spec
# Exits non-zero on any failure. python3 + bash only; offline; no pip.
set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
VALIDATE="$HERE/validate_spec.py"
BIND="$HERE/bind_prompt.py"
FIX="$HERE/fixtures"
VALID="$FIX/valid-spec.json"
INVALID="$FIX/invalid-spec.json"
TEMPLATE="worker"

fails=0
note() { echo "ok   $1"; }
fail() { echo "FAIL $1"; fails=$((fails + 1)); }

echo "== C08+C09 spec-intake: spec -> prompt round-trip =="

# --- 1. validate the VALID toy spec (expect exit 0) ---
if python3 "$VALIDATE" "$VALID" >/dev/null 2>&1; then
  note "valid toy spec validates (exit 0)"
else
  fail "valid toy spec should validate but did not"
fi

# --- 2. reject the INVALID spec (expect non-zero) ---
if python3 "$VALIDATE" "$INVALID" >/dev/null 2>&1; then
  fail "invalid spec should be rejected but validator returned exit 0"
else
  note "invalid spec rejected by validator (non-zero exit)"
fi

# --- 3. render the toy spec through the worker template (round-trip) ---
PROMPT="$(python3 "$BIND" "$VALID" "$TEMPLATE" 2>/dev/null)"
rc=$?
if [ "$rc" -ne 0 ]; then
  fail "bind_prompt should render the valid spec but exited $rc"
else
  note "valid toy spec rendered through template '$TEMPLATE' (exit 0)"
fi

# --- 3a. assert the rendered prompt contains values BOUND FROM the spec ---
# Pull a couple of distinctive values straight out of the spec JSON, then grep
# for them in the rendered prompt. If the binding worked, they must be present.
assert_contains() {
  needle="$1"; label="$2"
  if printf '%s' "$PROMPT" | grep -qF -- "$needle"; then
    note "rendered prompt contains bound $label"
  else
    fail "rendered prompt is missing bound $label: '$needle'"
  fi
}

SPEC_ID="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["spec_id"])' "$VALID")"
TITLE="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["title"])' "$VALID")"
ACTOR="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["actor"])' "$VALID")"
DOD_HEAD="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["dod"][:24])' "$VALID")"

assert_contains "$SPEC_ID"  "spec_id"
assert_contains "$TITLE"    "title"
assert_contains "$ACTOR"    "actor"
assert_contains "$DOD_HEAD" "dod"

# --- 4. bind_prompt must REFUSE to render the invalid spec ---
if python3 "$BIND" "$INVALID" "$TEMPLATE" >/dev/null 2>&1; then
  fail "bind_prompt should refuse the invalid spec but exited 0"
else
  note "bind_prompt refused the invalid spec (non-zero exit)"
fi

# --- 5. unknown template name must be E-C09-01 (template-not-found) ---
if python3 "$BIND" "$VALID" "no-such-template" >/dev/null 2>&1; then
  fail "bind_prompt should fail on unknown template but exited 0"
else
  note "bind_prompt failed loud on unknown template (E-C09-01)"
fi

echo
if [ "$fails" -eq 0 ]; then
  echo "PASS: toy spec round-trips spec -> prompt; invalid spec rejected (Gate B1 satisfied)"
  exit 0
else
  echo "FAIL: $fails assertion(s) failed"
  exit 1
fi
