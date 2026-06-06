#!/usr/bin/env python3
"""C20 bead validator (sweep-1, stdlib-only).

Validates a single bead instance (JSON) against the C20 bead-type schema
registry (``bead-types.schema.json``). Implements the write-time validation
surface from C20-bead-schema.md section 5 + the error taxonomy in section 6.1:

  E6  wrong/colliding bundle_id (the XC-4 hazard)         -> reject
  E1  unknown / missing ``type``                          -> reject
  E2  missing required envelope field (e.g. created_by)    -> reject
  E3  missing required type-specific field                 -> reject
  E4  wrong field logical type                             -> reject
  E5  resume-incompleteness on a mid-flight build          -> reject

It is deliberately pragmatic (sweep-1 acceptance): it enforces the bundle_id
rule, the closed type list, required envelope + per-type fields, basic logical
types, and the section-3 resume-completeness invariant. It does NOT enforce the
chain-acyclicity / <=1-resolution structural rules (E9) or registry<->store
conformance (E7) -- those need multi-bead / store context and are out of scope
for a single-instance validator.

CLI:
    python3 validate_bead.py <bead.json> [--schema <schema.json>]

Exit code 0 = valid; non-zero = invalid (with a clear message on stderr).
"""

import argparse
import json
import os
import sys

DEFAULT_SCHEMA = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "bead-types.schema.json")
EXPECTED_BUNDLE_ID = "softwarefactory.v4.beads"


class BeadInvalid(Exception):
    """Raised with a clear, error-code-tagged message for an invalid bead."""


# --- logical-type checks -------------------------------------------------

def _is_bead_id(v):
    return isinstance(v, str) and len(v) > 0


def _is_actor(v):
    # D-29 wire form is colon-delimited "kind:id"; sweep-1 just requires a
    # non-empty string (provenance verification is C41's optional pack, G36).
    return isinstance(v, str) and len(v) > 0


_TYPE_CHECKS = {
    "bead_id": _is_bead_id,
    "actor": _is_actor,
    "string": lambda v: isinstance(v, str),
    "int": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "bool": lambda v: isinstance(v, bool),
    "timestamp": lambda v: isinstance(v, str),
    "path": lambda v: isinstance(v, str) and len(v) > 0,
    "handle": lambda v: isinstance(v, str) and len(v) > 0,
    "enum": lambda v: isinstance(v, str),
    "list<bead_id>": lambda v: isinstance(v, list) and all(_is_bead_id(x) for x in v),
    "list<string>": lambda v: isinstance(v, list) and all(isinstance(x, str) for x in v),
    "JSON": lambda v: isinstance(v, (dict, list)),
    # union types referenced in the schema
    "bead_id|string": lambda v: isinstance(v, str),
    "string|list<string>": lambda v: isinstance(v, str) or (
        isinstance(v, list) and all(isinstance(x, str) for x in v)),
}


def _check_logical_type(field_name, value, logical_type, spec):
    checker = _TYPE_CHECKS.get(logical_type)
    if checker is None:
        # Unknown logical type in the schema: be permissive (sweep-1) but only
        # for declared schema types -- this should not happen with the shipped
        # schema.
        return
    if logical_type == "enum":
        members = spec.get("enum")
        if members is not None and value not in members:
            raise BeadInvalid(
                "E4: field '%s' value %r is not in enum %r" % (
                    field_name, value, members))
        if not isinstance(value, str):
            raise BeadInvalid(
                "E4: field '%s' must be a string enum value, got %s" % (
                    field_name, type(value).__name__))
        return
    if not checker(value):
        raise BeadInvalid(
            "E4: field '%s' has wrong type; expected %s, got %r" % (
                field_name, logical_type, value))


def _check_fieldset(bead, fields, where):
    """Enforce required + logical-type for one field map. Returns nothing."""
    for name, spec in fields.items():
        present = name in bead
        if spec.get("required") and not present:
            code = "E2" if where == "envelope" else "E3"
            raise BeadInvalid(
                "%s: missing required %s field '%s'" % (code, where, name))
        if present:
            _check_logical_type(name, bead[name], spec["type"], spec)


# --- main validation -----------------------------------------------------

def validate(bead, schema):
    # E6: bundle_id collision / wrong namespace.
    bundle_id = schema.get("bundle_id")
    if bundle_id != EXPECTED_BUNDLE_ID:
        raise BeadInvalid(
            "E6: schema bundle_id %r is not the D-2 namespace %r (XC-4 collision)"
            % (bundle_id, EXPECTED_BUNDLE_ID))

    # A bead MAY carry its own bundle_id; if it does it must match exactly.
    bead_bundle = bead.get("bundle_id")
    if bead_bundle is not None and bead_bundle != EXPECTED_BUNDLE_ID:
        raise BeadInvalid(
            "E6: bead bundle_id %r is not %r (XC-4 collision)"
            % (bead_bundle, EXPECTED_BUNDLE_ID))

    # E1: type present + in the closed registry.
    btype = bead.get("type")
    if btype is None:
        raise BeadInvalid("E1: bead has no 'type' field (untyped bead)")
    if btype not in schema.get("types", {}):
        raise BeadInvalid(
            "E1: unknown bead type %r; not in the closed registry %r"
            % (btype, sorted(schema.get("types", {}).keys())))

    # E2: common envelope required fields + types.
    _check_fieldset(bead, schema["envelope"]["fields"], "envelope")

    # E3/E4: per-type required fields + types.
    type_def = schema["types"][btype]
    _check_fieldset(bead, type_def.get("fields", {}), "type-specific")

    # E5: resume-completeness for mid-flight builds.
    #   - legacy factory_build_in_progress always needs the resume fields
    #     (enforced as required in the schema, handled above).
    #   - a factory_build with status=in_progress needs a workflow_handle
    #     (D-40 resume-completeness invariant, section 4.5.3).
    if btype == "factory_build" and bead.get("status") == "in_progress":
        if not bead.get("workflow_handle"):
            raise BeadInvalid(
                "E5: factory_build with status=in_progress must carry a "
                "workflow_handle for gc converge resume (section 4.5.3)")

    return True


def load_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Validate a bead instance against the C20 schema registry.")
    parser.add_argument("bead", help="path to the bead instance JSON file")
    parser.add_argument("--schema", default=DEFAULT_SCHEMA,
                        help="path to bead-types.schema.json "
                             "(default: alongside this script)")
    args = parser.parse_args(argv)

    try:
        schema = load_json(args.schema)
    except (OSError, ValueError) as exc:
        print("error: cannot load schema %s: %s" % (args.schema, exc),
              file=sys.stderr)
        return 2

    try:
        bead = load_json(args.bead)
    except (OSError, ValueError) as exc:
        print("error: cannot load bead %s: %s" % (args.bead, exc),
              file=sys.stderr)
        return 2

    try:
        validate(bead, schema)
    except BeadInvalid as exc:
        print("INVALID %s: %s" % (args.bead, exc), file=sys.stderr)
        return 1

    print("VALID %s (type=%s)" % (args.bead, bead.get("type")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
