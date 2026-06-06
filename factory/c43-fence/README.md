# C43 fence — deterministic blast-radius typing (boundary-typing half)

This component is the **boundary-typing / blast-radius half** of
**C43 — Isolation & lethal-trifecta boundary**.

- Spec: **C43 — Isolation & lethal-trifecta boundary** (canonical track)
- Upstream spec path: `architectures/v4/spec/C43-isolation-boundary.md`

## What this is (and what it is NOT)

C43's load-bearing keep is **deterministic boundary typing** — every external /
cross-partition interaction carries a boundary type assigned by a **deterministic
rule, never an LLM judgment** (the F51 "deterministic boundary typing is the
primary guard" invariant). This directory builds the half of that keep that
needs **only the C42 rig partitions** (pulled into Gate B1): given an action, it
**types the blast radius** over the Gas City rig/city partition model and
**refuses dangerous combinations** — a cross-partition write or a
production-typed action.

This is a **deterministic typing/policy artifact (sweep-1)**, not a runtime hook
into `gc`. It classifies a sample action handed to it as JSON; it does **not**
intercept tool calls, spawn sandboxes, or route to twins. Per **D-30** the
enforcement *mechanism* (native `gc` prevention vs. a blocking watcher) is
**DEFERRED** to the D-23 spike — the watcher is explicitly not designed here.
The runtime `gc`-pack wiring and twin routing are **sweep-2**.

Out of scope (the other halves of C43 and the dropped over-builds):

- The **C44 twin-isolation half** — the `twin` boundary type's realized route to
  a digital twin. Twins are Phase 3c and "unbuilt and last" (the **G31**
  residual): until they land, a `twin` type is a declared intent, not a realized
  control. This fence types blast radius over partitions; it does not stand up a
  twin.
- The **C34 holdout read-isolation enforcement + audit** — a *distinct* boundary
  (review-log **D-13**). C34 detects a scenario leak after the fact; C43 bounds
  what the broad-tool agent can touch.
- The **C42 partition declaration itself** — C42 *provides* the rig/city
  partitions; C43 *consumes* them as the baseline scope and types blast radius on
  top.
- No capability-grant engine (**C02-04** dropped), no spawn-time OS jail
  (**C04-05** — we trust the process boundaries Gas City gives), no OPA
  (**C42-06**), no `boundary_class` tag machinery (**C41-07**).

## The partition model

Bead-prefix scoping is the Gas City scoping **mechanism**, verified against the
Gas City prototype (`gascity-prototype@b14c278`, D-23):

| Scope | Prefix | Role |
|---|---|---|
| `gp` | `gp-` | city HQ / global partition |
| `r1` | `r1-` | rig 1 |
| `r2` | `r2-` | rig 2 |

An agent scoped to a rig sees/writes only its own prefix. A target's partition
is the prefix segment before the first `-` (or path `/`). An action is
**in-bounds** (same-partition) iff the target's resolved scope equals the actor's
rig scope; otherwise it is **cross-partition** — the reach this fence bounds.

> Note (D-23, OPEN OQ-C43-1): the prototype proved prefix is the scoping
> *mechanism*; it did **not** verify whether `gc` *prevents* out-of-prefix access
> at the tool-call level or merely scopes-by-convention. That prevent-vs-detect
> question is the D-23 spike target and is out of scope for this sweep-1 fence.

## Blast-radius classes & refusal rules

The boundary types are the closed C43 §4.1 set — `twin` (default for an external
surface; routes to a C44 twin at Phase 3c), `isolated` (the actor's own rig
worktree/partition, reachable by default), and `production` (real external
system, default-deny). The classifier types each action into one blast-radius
class. Refusal rules are applied in policy order (production first, so a
production cross-partition write reports as `production_action`):

| Class | Verdict | Reason code | Trigger |
|---|---|---|---|
| `in_bounds` | allow (exit 0) | — | same-partition action (or read) in `sandbox` env |
| `production_action` | refuse (exit 1) | `E-C43-PROD` | `env == production` |
| `cross_partition_write` | refuse (exit 1) | `E-C43-XP-WRITE` | `op == write` AND target scope != actor scope |

A read whose target scope is foreign is still **allowed** here — reads do not
extend blast radius, and the distinct holdout *read*-isolation boundary is
**C34**'s, not C43's (D-13). Malformed actions fail closed (`refuse`).

## D-20 default — production actions are blocked

Per **D-20** (ADOPTED 2026-05-31; the boundary-typing/blast-radius half is a
Phase-2 entry precondition), a **production-typed action is blocked**. Reaching
real production requires an explicit per-pack **production-scissors** declaration
(F44) — which is *not* granted in this boundary-typing-half fence — so every
`env == production` action refuses.

## Why this is pulled into Gate B1

The boundary-typing/blast-radius half **depends only on the C42 rig partitions**
(plus the P4 deterministic-typing primitive) — **not** on C44 twins. That is what
lets it be pulled forward into **Gate B1** ahead of the twin work (Batch 4 /
Phase 3c). It is the interim bound D-20 adopts for the Phase 0→3b exposure window
(rejecting detection-only Phase 0); the twin-isolation half stays at Phase 3c.

## Gate B1 exit criterion satisfied

> **"the fence types a sample action's blast radius."**

`python3 classify_action.py <action.json>` deterministically types a sample
action's blast radius and emits an `allow` / `refuse` verdict (exit 0 / non-zero)
with the reason. `bash test.sh` runs the classifier over the fixtures and asserts
each expected verdict.

## Files

```
c43-fence/
├── README.md                 this file
├── blast-radius-policy.json  declarative policy: partition/scope model + refused classes
├── classify_action.py        stdlib-only deterministic classifier (the typing tool)
├── fixtures/                 sample actions (allow / refuse cases)
└── test.sh                   runs the classifier over fixtures; non-zero on mismatch
```

## Running

```bash
bash test.sh                                          # all fixtures, asserts verdicts
python3 classify_action.py fixtures/cross-partition-write.json   # -> refuse, exit 1
```

stdlib only; offline; no pip.
