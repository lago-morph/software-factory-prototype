# C20 — Bead-type schema registry

C20 is the **canonical schema registry for every bead type** in Software
Factory v4. A *bead* is one node in the durable, typed work-graph (the bead
store, owned by C19). C20 does **not** own persistence — it owns the
**vocabulary of node types** that flow through the store: what each `type` tag
means, what fields each type carries, and how typed beads chain to each other.

This component exists to close gap **G17**: v4 instructs agents to query bead
types that were never defined (e.g. `gc bd find --type factory_build_in_progress`
in the cold-start procedure, and `override` / `fix_task` / `factory_build` in the
README), but no schema was given anywhere. C20 is where those definitions live.

> **Spec:** *C20 — Bead schema registry* (canonical track), upstream at
> `architectures/v4/spec/C20-bead-schema.md` in the `lago-morph/software-factory`
> design repo. (A relative link from this prototype repo will not resolve, so the
> spec is cited by name + path as text.) This directory implements the **sweep-1**
> altitude of that spec: the bundle namespace rule, the closed type list, the
> common envelope, and per-type required fields.

## The bundle

All bead types live under one bundle, namespace **`softwarefactory.v4.beads`**
(binding decision **D-2**). Registering the bundle under any other string is the
**XC-4 collision** and is rejected (error **E6**). The full bundle document —
the artifact C20 hands to C22's `register_bundle` mechanism (D-3) — is
[`bead-types.schema.json`](bead-types.schema.json).

## Legal bead types

Every bead carries the **common envelope** (spec §4.5.0): `id`, `type`,
`created_by`, `status` (`open` | `in_progress` | `closed`), optional `depends_on`
edges, and an optional schema `version` pin.

| `type` | Source | Required type-specific fields |
|---|---|---|
| `override` | README P8 (operator-override record) | `overridden`, `why` |
| `fix_task` | README P11 / Phase 3b (diagnosis-generated repair unit) | `diagnosis_ref`, `anomaly_ref`, `spec_ref`, `attempt_no` (+ XC-3 bound slots `max_attempts`, `escalated`) |
| `factory_build` | AI-CONTEXT §16 / D-40 (factory self-build record) | `transfused_from`, `spec_ref`, `scenario_ref`, `status`, `exemplar_set` |
| `factory_build_in_progress` | AI-CONTEXT §16 (PRE-D-40 legacy-compat alias) | `transfused_from`, `spec_ref`, `scenario_ref`, `workflow_handle` |
| `anomaly` | README P11 closure chain (provisional, OQ-C20-2) | `signal_ref` |
| `diagnosis` | README P11 closure chain (provisional, OQ-C20-2) | `anomaly_ref` |
| `resolution` | README P11 closure chain (provisional, OQ-C20-2) | `closes`, `verdict` (XC-3 closure slots) |
| `score_record` | spec §3.1 (registered per D-3; schema **owned by C32**, D-39) | — (envelope only here) |
| `satisfaction_metric` | spec §3.1 (registered per D-3; schema **owned by C33**, D-39) | — (envelope only here) |

The self-heal closure chain is `anomaly → diagnosis → fix_task → resolution`
(README P11). The XC-3 slots (`attempt_no` / `max_attempts` / `escalated` on
`fix_task`; `closes` / `verdict` on `resolution`) make the loop *boundable* —
C20 owns the slots, **C39 owns the policy** (the actual `N`-attempts bound).

## How to validate a bead

```bash
python3 validate_bead.py <bead.json>
# exit 0 + "VALID ..."   when the bead conforms
# exit 1 + "INVALID ..." (error code on stderr) when it does not
```

The validator (`validate_bead.py`, pure stdlib) resolves the bead's `type`
within the bundle and enforces the spec §6.1 error taxonomy at the
single-instance altitude:

- **E6** — bundle_id is not exactly `softwarefactory.v4.beads` (XC-4 collision).
- **E1** — `type` is missing or not in the closed registry.
- **E2** — a required envelope field (e.g. `created_by`) is missing.
- **E3** — a required type-specific field (e.g. `fix_task` without `spec_ref`) is missing.
- **E4** — a field has the wrong logical type (e.g. an out-of-enum `status`).
- **E5** — resume-incompleteness: a `factory_build` with `status=in_progress` (or a legacy `factory_build_in_progress`) missing its `workflow_handle`/resume fields.

Out of scope for a single-instance validator (need multi-bead / store context):
chain acyclicity and the ≤1-`resolution` rule (**E9**), and registry↔store
version conformance (**E7**).

## Tests

```bash
./test.sh
```

`test.sh` runs the validator over every file in [`fixtures/`](fixtures), keying
off the filename prefix: `valid-*` fixtures must pass, `invalid-*` fixtures must
fail. It prints a summary and exits non-zero on any mismatch. The fixtures
include at least one valid bead for several representative types and invalid
beads demonstrating E6 (wrong bundle), E1 (unknown type), E2 (missing
`created_by`), E3 (missing type-specific field), and E5 (resume-incompleteness).

## Gate B1 exit criterion

This component satisfies the Gate B1 exit check:

> **the schema accepts a valid bead and rejects an ill-typed one.**

`test.sh` is the executable form of that criterion — green means the closed
registry both accepts every well-formed representative bead and rejects the
ill-typed / mis-namespaced ones.
