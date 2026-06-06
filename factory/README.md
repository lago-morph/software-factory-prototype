# Factory backbone components

Backbone-25 components built **on top of** the Gas City substrate that the
repository root packages. The root (Dockerfile / compose / pack / entrypoint)
delivers **Gate B0** — the 11 adopt-and-configure Gas City components
(C01–C05, C17, C18, C19, C23, C41, C42) plus C28 (Claude Code worker). This
directory holds the **build-from-scratch** components that depend only on that
substrate.

See the upstream [backbone implementation plan](https://github.com/lago-morph/software-factory/blob/main/architectures/v4/backbone-implementation-plan.md)
for the gate model and per-component "done" definitions.

## Status

| Component | What | Gate | State |
|---|---|---|---|
| [C20 bead-type schema](c20-bead-schema/) | Legal bead types + validator on the adopted store | B1 | built + tested |
| [C08/C09 spec intake](c08-c09-spec-intake/) | Spec artifact format + prompt-template binding | B1 | built + tested |
| [C43 fence (boundary half)](c43-fence/) | Deterministic blast-radius typing over rig partitions | B1 | built + tested |
| [C29 model-floor policy](c29-model-floor/) | Cost/family routing policy on the model stylesheet | B1 | built + tested |

Later gates (not yet built): the evaluation tier C30–C33 (B2), the C34 holdout
half (B3), and the bootstrap loop C51–C53 (B3).

## Running the tests

Each component ships a stdlib-only test (no pip installs):

```bash
make -C factory test        # or: for d in factory/c*/; do (cd "$d" && ./test.sh); done
```

## Conventions

Every component directory is self-contained and uniform:

```
factory/<id>/
├── README.md        what it is, the spec it implements, the Gate B1 exit check it satisfies
├── <artifact(s)>    the schema / policy / templates (the deliverable)
├── <validator>      a pure-python3 (stdlib-only) validator/typing tool
└── test.sh          runs the validator over fixtures; exits non-zero on failure
```

These are **sweep-1** artifacts (faithful to the spec's interface + the Gate B1
exit criterion); deeper gc-pack wiring and CI are sweep-2.
