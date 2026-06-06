#!/usr/bin/env python3
"""validate_spec.py -- C08 spec-artifact validator (stdlib only).

Usage:
    python3 validate_spec.py <spec.json>

Exit 0  -> the spec conforms to the C08 spec-artifact format.
Exit !=0 -> the spec is invalid; a clear message is printed to stderr.

Faithful to C08 (architectures/v4/spec/C08-spec-artifact.md):
  - Required logical fields (C08 §4.1): spec_id, spec_body, dod.
  - INV-4 / E-C08-02: a conformant spec MUST carry a free-form DoD.
  - INV-2 / E-C08-01: spec_body must be a renderable template -- here we
    check that every {{ ... }} placeholder is well-formed (balanced and
    non-empty), the stdlib analogue of "parses as a valid Go text/template".
  - spec_id is the pack-layout identity agents/<name> (C08 §4.1).

This is a stdlib-only re-implementation of the *format contract*; it is not
the Go text/template engine itself. It validates structure, required fields,
and placeholder well-formedness so a spec can round-trip spec -> prompt (C09).
"""
import json
import re
import sys

# ---- format contract derived from spec.schema.json (C08 §4.1) ----
REQUIRED_FIELDS = ("spec_id", "spec_body", "dod")
ALLOWED_FIELDS = {
    "spec_id", "title", "intent", "spec_body", "dod",
    "acceptance_criteria", "work_type", "actor", "pack_ref", "git_revision",
}
SPEC_ID_RE = re.compile(r"^agents/[a-z0-9][a-z0-9_-]*$")
WORK_TYPE_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
ACTOR_RE = re.compile(r"^[a-z]+:[A-Za-z0-9._-]+$")

# {{ placeholder }} -- the C09 binding mechanism (mirrors Go text/template {{.X}})
PLACEHOLDER_RE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")


class SpecError(Exception):
    """A spec-format violation, carrying a C08 error code where one applies."""


def _check_placeholders(body):
    """E-C08-01 analogue: every {{ and }} must be balanced and each
    placeholder must name a non-empty identifier. Returns the set of names."""
    if body.count("{{") != body.count("}}"):
        raise SpecError(
            "E-C08-01 malformed spec: unbalanced {{ }} in spec_body "
            "(template-parse-error; cannot be rendered by C09)"
        )
    # Find every {{...}} span and confirm it matches a well-formed placeholder.
    for m in re.finditer(r"\{\{(.*?)\}\}", body, flags=re.DOTALL):
        inner = m.group(1).strip()
        if not inner:
            raise SpecError(
                "E-C08-01 malformed spec: empty placeholder {{ }} in spec_body"
            )
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", inner):
            raise SpecError(
                "E-C08-01 malformed spec: placeholder {{ %s }} is not a bare "
                "identifier (this prototype binds {{ name }} placeholders)" % inner
            )
    return {m.group(1) for m in PLACEHOLDER_RE.finditer(body)}


def validate(spec):
    if not isinstance(spec, dict):
        raise SpecError("spec must be a JSON object at the top level")

    # Unknown fields are a format violation (schema additionalProperties:false).
    unknown = set(spec) - ALLOWED_FIELDS
    if unknown:
        raise SpecError("unknown field(s): %s" % ", ".join(sorted(unknown)))

    # Required fields (C08 §4.1).
    for field in REQUIRED_FIELDS:
        if field not in spec:
            code = "E-C08-02 missing DoD" if field == "dod" else "missing required field"
            raise SpecError("%s: '%s' is required by C08" % (code, field))
        if not isinstance(spec[field], str) or not spec[field].strip():
            raise SpecError("field '%s' must be a non-empty string" % field)

    # spec_id shape (pack-layout identity agents/<name>).
    if not SPEC_ID_RE.match(spec["spec_id"]):
        raise SpecError(
            "spec_id '%s' must be of the form 'agents/<name>' (C08 pack layout)"
            % spec["spec_id"]
        )

    # Optional typed fields.
    if "work_type" in spec and not WORK_TYPE_RE.match(str(spec["work_type"])):
        raise SpecError("work_type '%s' must be a lowercase role slug" % spec["work_type"])
    if "actor" in spec and not ACTOR_RE.match(str(spec["actor"])):
        raise SpecError(
            "actor '%s' must be in 'kind:id' wire form (D-29), e.g. 'human:alice'"
            % spec["actor"]
        )
    if "acceptance_criteria" in spec:
        ac = spec["acceptance_criteria"]
        if not isinstance(ac, list) or not all(
            isinstance(x, str) and x.strip() for x in ac
        ):
            raise SpecError("acceptance_criteria must be a list of non-empty strings")

    # INV-2 analogue: spec_body placeholders must be well-formed.
    _check_placeholders(spec["spec_body"])

    return True


def main(argv):
    if len(argv) != 2:
        sys.stderr.write("usage: python3 validate_spec.py <spec.json>\n")
        return 2
    path = argv[1]
    try:
        with open(path, "r", encoding="utf-8") as fh:
            spec = json.load(fh)
    except FileNotFoundError:
        sys.stderr.write("INVALID: file not found: %s\n" % path)
        return 1
    except json.JSONDecodeError as exc:
        sys.stderr.write("INVALID: %s is not valid JSON: %s\n" % (path, exc))
        return 1

    try:
        validate(spec)
    except SpecError as exc:
        sys.stderr.write("INVALID: %s\n" % exc)
        return 1

    sys.stdout.write("VALID: %s conforms to the C08 spec-artifact format\n" % path)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
