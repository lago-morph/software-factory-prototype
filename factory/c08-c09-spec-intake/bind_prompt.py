#!/usr/bin/env python3
"""bind_prompt.py -- C09 spec->prompt render+bind (stdlib only).

Usage:
    python3 bind_prompt.py <spec.json> <template-name>

Reads the spec, VALIDATES it against the C08 format (validate_spec.validate),
binds its fields into the named prompt template, and prints the rendered prompt
to stdout. This is the spec -> prompt round-trip that satisfies Gate B1.

Faithful to C09 (architectures/v4/spec/C09-prompt-template-binding.md):
  - resolve(): <template-name> is resolved to a file under prompt-templates/
    (the canonical layout uses agents/<name>/prompt.template.md; this prototype
    keeps templates in a sibling prompt-templates/ dir for self-containment).
    A missing template is E-C09-01 (template-not-found).
  - render(): every {{ name }} placeholder in the template is substituted from
    the spec's fields (the binding mechanism). A placeholder with no matching
    spec field is E-C09-02 (unbound-variable) -- fail loud, never a silently
    empty prompt (C09 INV-1, §6 fail-loud postcondition).
  - INV-1 (render-faithfulness): the output is a pure function of
    (template body, spec fields) -- same inputs => byte-identical output.

The {{ name }} placeholder convention is the stdlib analogue of Go
text/template's {{.Name}} actions (C09 §3.2a names .TemplateName/.AgentRole/...).
Here the bound namespace is the spec's own fields.
"""
import json
import os
import re
import sys

import validate_spec

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(HERE, "prompt-templates")

PLACEHOLDER_RE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")


class BindingError(Exception):
    """A C09 render/bind failure, carrying a C09 error code."""


def resolve(template_name):
    """C09 resolve(): map a template name to its body.

    Accepts a bare name ('worker'), a filename ('worker.prompt.template.md'),
    or a canonical path ('agents/worker/prompt.template.md'). Returns the
    template body text. Raises E-C09-01 if no template file is found."""
    candidates = []
    base = os.path.basename(template_name)
    # canonical agents/<name>/prompt.template.md -> derive <name>
    m = re.match(r"^agents/([a-z0-9][a-z0-9_-]*)/prompt\.template\.md$", template_name)
    if m:
        candidates.append("%s.prompt.template.md" % m.group(1))
    candidates.append(base)
    candidates.append("%s.prompt.template.md" % base)

    seen = []
    for cand in candidates:
        path = os.path.join(TEMPLATE_DIR, cand)
        seen.append(path)
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as fh:
                return cand, fh.read()
    raise BindingError(
        "E-C09-01 template-not-found: no template '%s' under %s (tried: %s)"
        % (template_name, TEMPLATE_DIR, ", ".join(os.path.basename(p) for p in seen))
    )


def render(template_body, spec):
    """C09 render(): bind spec fields into {{ name }} placeholders.

    Every placeholder must resolve to a spec field; an unbound placeholder is
    E-C09-02 (fail loud, no partial output). Returns the rendered prompt."""
    referenced = {m.group(1) for m in PLACEHOLDER_RE.finditer(template_body)}
    missing = sorted(name for name in referenced if name not in spec)
    if missing:
        raise BindingError(
            "E-C09-02 unbound-variable: template references field(s) not "
            "supplied by the spec: %s" % ", ".join(missing)
        )

    def _sub(match):
        return str(spec[match.group(1)])

    return PLACEHOLDER_RE.sub(_sub, template_body)


def bind_and_render(spec, template_name):
    """C09 bind_and_render(): resolve + render in one call."""
    _resolved_name, body = resolve(template_name)
    return render(body, spec)


def main(argv):
    if len(argv) != 3:
        sys.stderr.write("usage: python3 bind_prompt.py <spec.json> <template-name>\n")
        return 2
    spec_path, template_name = argv[1], argv[2]

    try:
        with open(spec_path, "r", encoding="utf-8") as fh:
            spec = json.load(fh)
    except FileNotFoundError:
        sys.stderr.write("ERROR: spec file not found: %s\n" % spec_path)
        return 1
    except json.JSONDecodeError as exc:
        sys.stderr.write("ERROR: %s is not valid JSON: %s\n" % (spec_path, exc))
        return 1

    # The round-trip validates the spec before binding (C09 consumes a
    # conformant C08 artifact; a malformed spec must not render).
    try:
        validate_spec.validate(spec)
    except validate_spec.SpecError as exc:
        sys.stderr.write("ERROR: spec is invalid, refusing to render: %s\n" % exc)
        return 1

    try:
        prompt = bind_and_render(spec, template_name)
    except BindingError as exc:
        sys.stderr.write("ERROR: %s\n" % exc)
        return 1

    sys.stdout.write(prompt)
    if not prompt.endswith("\n"):
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
