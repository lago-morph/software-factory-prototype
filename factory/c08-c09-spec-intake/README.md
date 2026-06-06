# C08 + C09 — Spec intake (spec artifact → prompt template binding)

This component group is the **spec-intake** backbone of the Software Factory v4
prototype: a version-controlled **spec artifact** that validates against a format,
then **binds to a named prompt template** to produce a concrete agent instruction.

It implements the two foundational Spec-Intake specs:

- **C08 — Spec artifact & format** (`spec-artifact`)
  Upstream spec: `/home/user/software-factory/architectures/v4/spec/C08-spec-artifact.md`
- **C09 — Prompt template & spec→execution binding** (`prompt-template-binding`)
  Upstream spec: `/home/user/software-factory/architectures/v4/spec/C09-prompt-template-binding.md`

## What C08 and C09 are

**C08** owns the *source-of-truth spec artifact and its format* — the
human-authored, version-controlled document that drives execution. Principle 1:
"Code is disposable; specs are the load-bearing artifact. When something breaks,
you fix the spec and rebuild, not the output." On the canonical track (C08 OQ-1
**Reading A / collapse**), the artifact *is* the prompt-template carrier: on disk
it lives at `agents/<name>/prompt.template.md` as a Go `text/template` over
Markdown, committed to git. C08 is the *artifact and its format* — it does not
render.

**C09** owns the *render + bind transform*: it turns the static C08 artifact into
a concrete agent instruction (the "becomes an instruction" half) and decides
*which spec drives which work* via the named association
`formula-node → template-name → agent-role` (the "binding" half). C09 *renders*
and *references* the C08 artifact; it owns no artifact of its own.

The seam: C08 guarantees the artifact exists, carries the required fields, and is
renderable; C09 reads it and produces the rendered instruction handed to the
agent loop (C28).

## The spec format (C08 §4.1)

The spec is expressed here as **JSON** (`spec.schema.json`) so it can be parsed
with the Python stdlib — a documented equivalent of v4's on-disk
`prompt.template.md`. The `spec_body` field carries the template-style body; the
other keys carry the *logical fields* C08 names so downstream components (C09
render+bind, C10 lint, C32/C33 DoD scoring, C39 fix routing) can operate on them.

| Field | Req? | C08 source | Meaning |
|---|---|---|---|
| `spec_id` | **R** | §4.1 | Stable identity, the pack-layout path segment `agents/<name>` that C09 `resolve()` keys on. |
| `spec_body` | **R** | §4.1 / INV-2 | The spec body; must be renderable (well-formed `{{ }}` placeholders — the stdlib analogue of "parses as a valid Go `text/template`"). |
| `dod` | **R** | §4.1 / **INV-4** | Free-form Definition-of-Done — what a successful run must satisfy. C33 passes it verbatim to C32's graded judge. Absence is **E-C08-02**. Free-form prose at Sweep-2 (per-criterion enumeration is FE-5 / deferred, D-15). |
| `title` | O | — | One-line human label. |
| `intent` | O | §2 | What the spec is for (the C11 crucible intake, surfaced into the artifact). |
| `acceptance_criteria` | O | AC-4 | The lintable surface C10 consumes. Free-form prose items — *not* machine-scored per-criterion DoD (FE-5 deferred). |
| `work_type` | O | §4.1 | Agent-role slug (e.g. `worker`, `judge`, `dog`); informs C09 role binding. |
| `actor` | O | §4.1 / D-29 | Author identity in `kind:id` wire form (e.g. `human:alice`). |
| `pack_ref` | O | §4.1 | Provenance — which pack repo the spec lives in (C51/C39 use it). |
| `git_revision` | O | §4.1 | Commit SHA. Per C08 this is *derived* from git history, not stored in the file; carried here only as an optional provenance echo. |

**Required fields enforced by `validate_spec.py`:** `spec_id`, `spec_body`, `dod`.
The validator also enforces `spec_id` shape (`agents/<name>`), `actor` wire form
(`kind:id`, D-29), `work_type` slug shape, and `spec_body` placeholder
well-formedness (the **INV-2 / E-C08-01** "renderable" analogue), and rejects
unknown fields.

## The binding mechanism (C09)

A prompt template is a named Markdown file under `prompt-templates/` (the
prototype keeps templates in a sibling directory for self-containment; the
canonical v4 path is `agents/<name>/prompt.template.md`). The template carries
`{{ field }}` placeholders — the stdlib analogue of Go `text/template`'s
`{{.Field}}` actions. Binding substitutes each placeholder with the value of the
**same-named field from the spec**.

`bind_prompt.py` implements the C09 transform in three faithful steps:

1. **`resolve(template-name)`** — maps a template name (bare `worker`, a filename,
   or canonical `agents/worker/prompt.template.md`) to its body. A missing
   template is **E-C09-01** (template-not-found).
2. **`render(body, spec)`** — substitutes every `{{ name }}` placeholder from the
   spec's fields. A placeholder with no matching spec field is **E-C09-02**
   (unbound-variable) — fail loud, never a silently-empty prompt (C09 INV-1, §6).
3. **`bind_and_render`** — resolve + render in one call (C09 §3.1b entry point).

Before binding, `bind_prompt.py` **validates** the spec against the C08 format
(`validate_spec.validate`) — C09 consumes a *conformant* C08 artifact, so a
malformed spec must not render. Rendering is a pure function of (template body,
spec fields): same inputs ⇒ byte-identical output (C09 **INV-1**,
render-faithfulness).

## Files

| File | Role |
|---|---|
| `spec.schema.json` | The C08 spec-artifact format (JSON Schema draft-07). |
| `validate_spec.py` | Stdlib-only validator: `python3 validate_spec.py <spec.json>` → exit 0 valid / non-zero invalid. |
| `prompt-templates/worker.prompt.template.md` | A named prompt template with `{{ field }}` placeholder bindings. |
| `bind_prompt.py` | Stdlib-only round-trip: `python3 bind_prompt.py <spec.json> <template-name>` → validates, binds, prints the rendered prompt. |
| `fixtures/valid-spec.json` | A VALID toy spec ("reverse a string"). |
| `fixtures/invalid-spec.json` | An INVALID spec — missing the required `dod` (E-C08-02). |
| `test.sh` | Validates the toy spec, renders it, asserts the prompt contains bound values, asserts the invalid spec is rejected. |

## Usage

```sh
# Validate a spec against the C08 format
python3 validate_spec.py fixtures/valid-spec.json

# Round-trip: spec -> prompt (validates, then binds into the named template)
python3 bind_prompt.py fixtures/valid-spec.json worker

# Run the full test harness
bash test.sh
```

## Gate B1 exit criterion satisfied

> **"A toy spec round-trips spec → prompt."**

`test.sh` validates `fixtures/valid-spec.json` against the C08 format, renders it
through the `worker` prompt template via the C09 binding, and asserts the rendered
prompt actually contains values pulled from the spec (`spec_id`, `title`, `actor`,
and the head of `dod`). It also asserts the invalid spec (missing DoD) is rejected
by both the validator and `bind_prompt.py`, and that an unknown template name fails
loud (E-C09-01). The harness exits non-zero on any failure — a green run is the
Gate B1 round-trip.

## [FAITHFUL-FILL] notes

- **JSON over `prompt.template.md`.** v4's on-disk artifact is a Go
  `text/template` Markdown file; this prototype expresses the same logical fields
  (C08 §4.1) as stdlib-parseable JSON, with `spec_body` carrying the body. This is
  a representation choice for offline / stdlib-only fidelity, not a format change —
  the required fields, the renderability invariant, and the binding mechanism are
  preserved.
- **`{{ name }}` placeholders.** The binding uses bare-identifier `{{ name }}`
  placeholders bound from the spec's own fields, the stdlib analogue of Go
  `text/template`'s `{{.Name}}` actions (C09 §3.2a). The bound namespace here is
  the spec's fields rather than C09's dispatch-context variables
  (`.BeadId`/`.CreatedBy`/…), which belong to the Phase-0 dispatch runtime not
  modeled in this sweep-1 prototype.
- **INV-2 as placeholder well-formedness.** "Parses as a valid Go `text/template`"
  is approximated by checking `{{`/`}}` balance and bare-identifier placeholders
  (E-C08-01 analogue), since the Go template engine is not available stdlib-side.
- **Templates in `prompt-templates/`.** The canonical v4 path is
  `agents/<name>/prompt.template.md`; the prototype keeps templates in a sibling
  directory for self-containment, and `resolve()` accepts the canonical path form
  and maps it onto the local file.
- **Validation before binding.** C09 does not itself re-define the C08 format;
  `bind_prompt.py` calls the C08 validator before rendering to enforce the
  "C09 consumes a conformant C08 artifact" seam.
