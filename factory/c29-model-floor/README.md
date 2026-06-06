# C29 — Model floor & stylesheet routing (Software Factory v4, sweep-1)

This is the **C29** backbone component: a cost/family **routing policy** layered on the
worker "model stylesheet". Workers are Claude Code (C28); C29 does **not** run the agent
turn — it *decides which model* a request should run on, while never routing below a
declared capability **floor** and reporting the **cross-family** independence verdict.

- **Spec (read in full):** `C29-model-floor-stylesheet.md`
- **Upstream spec path (as text):**
  `/home/user/software-factory/architectures/v4/spec/C29-model-floor-stylesheet.md`
- **Inventory ID:** C29 — *model floor & stylesheet* (maps A11b / A106 / B84; F19 / F31).

## What C29 is

C29 fuses two v4 ideas under one ID:

1. **Model floor declaration (A106 / B84 / F19 / F31).** A declared *minimum acceptable
   model* per role/task-class. A request that asks for (or whose stylesheet picks) a model
   weaker than the floor is **upgraded to the floor** (the spec's E-C29-02 clamp-and-warn),
   or — if the policy is set to refuse — rejected as a hard rule violation.
2. **Stylesheet routing (A11b).** A CSS-like, cost-aware **model stylesheet** mapping
   `(role, task_class)` selectors to a *chosen* model + a *floor*, with each model tagged by
   `family` and `cost_tier`. Onto this hangs the **cross-family** rule.

## The stylesheet model (`model-stylesheet.json`)

- **`registry`** — `modeldb`-shaped `{id, family, cost_tier, rank}` per model. `rank` is the
  capability ordering the floor comparison uses (higher = more capable); `family` is what the
  cross-family rule compares. Current Claude model ids (authoritative):
  - `claude-opus-4-8` — family `anthropic`, tier `opus`, cost `premium`, rank 3
  - `claude-sonnet-4-6` — family `anthropic`, tier `sonnet`, cost `standard`, rank 2
  - `claude-haiku-4-5` — family `anthropic`, tier `haiku`, cost `economy`, rank 1
  - A non-Anthropic provider would be a **different family** — i.e. *cross-family*.
- **`rules`** — `role -> task_class -> {chosen, floor}`. Lookup precedence:
  exact `(role, task_class)` → role default (`*` task_class) → global `*`/`*`.
- **`policy`** — the `cross_family_required` flag (advisory default `false`) plus the
  Phase-0 `independence_level` (`L1`).

## The floor rule

`route.py` resolves a candidate model (`requested_model` pin if present, else the
stylesheet's `chosen`) and compares its `rank` to the matched rule's `floor` rank:

- **At or above floor** → resolves cleanly (exit 0).
- **Below floor** → by default **UPGRADED to the floor** (exit 0, `upgraded: true`,
  E-C29-02 clamp-and-warn). Flipping `BELOW_FLOOR_ACTION = "refuse"` makes a below-floor
  request a **hard rule violation** (exit 2). The floor is therefore never silently
  violated — a below-floor choice is either upgraded or refused, never honored.

## The cross-family rule

For a `judge` request, `route.py` compares the resolved model's `family` to the coder's
family (`coder_family`, defaulting to the floor family) and emits a verdict:

- **`cross_family_required: false` (advisory — Phase-0 default).** No route is ever refused
  on family grounds. When `family(judge) == family(coder)` the engine emits an **advisory
  note**: independence comes from rig/role/prompt isolation (L1), not family diversity.
- **`cross_family_required: true` (fail-closed — Gate-B4 trust lever).** A same-family judge
  becomes a hard violation (E-C29-04, exit 2). Flipping this flag to `true` is the
  **Gate-B4 trust lever** — it requires a non-Anthropic provider family for the judge
  (cross-provider holdout), which is upstream future work (FE-1 / G20).

### Why advisory-early

Per the spec's D-1 / FE-1 ruling, the literal `family(judge) != family(coder)` requirement
presumes a *second* model family, but the Max-tier coder floor is a single Claude adapter
with no separate provider available at Phase-0. So C29 keeps the `family` registry field and
the constraint emitter as the clean FE-1 seam, but ships the cross-family rule **advisory**
(`cross_family_required: false`) at Phase-0; the same-provider judge isolated by rig/role/
prompt (L1) is the sanctioned baseline. The flag is the switch FE-1 (Gate-B4) flips later.

## Usage

```
python3 route.py <request.json>
```

A request is `{role, task_class, requested_model?, coder_family?}`. Exit `0` on a resolvable
route (possibly upgraded and/or with an advisory note), `2` on a hard rule violation
(below-floor under refuse policy, or same-family judge under cross-family-required), `3` on
bad input / unresolvable request (no rule, unknown model id, bad json).

### Files

- `model-stylesheet.json` — registry + rules + policy (the stylesheet artifact).
- `route.py` — stdlib-only policy engine (floor + cross-family).
- `fixtures/clean.json` — resolves cleanly (coder/architect → opus, no upgrade).
- `fixtures/below-floor.json` — haiku pin below the sonnet floor → upgraded.
- `fixtures/cross-family.json` — judge same-family, advisory note (required=false).
- `test.sh` — runs the engine over the fixtures and asserts expected resolutions.

### Test

```
bash test.sh   # exit 0 = all assertions pass
```

## Gate B1 exit criterion satisfied

Gate B1 asks that the routing policy **apply cost/family rules** and that "a worker runs one
agent step under the policy". For **sweep-1** the demonstrable, paid-worker-free slice is the
**policy engine deciding a model for a request**: `route.py` matches a `(role, task_class)`
rule, applies the **floor** (upgrade/refuse below-floor), prefers the declared cost tier, and
reports the **cross-family** verdict (advisory when `cross_family_required: false`). This is
the cost/family policy *applied*. The literal "a worker runs a step under it" leg is exercised
when a real token is present (a live C28 worker dispatched with C29's resolved model) — that
is **sweep-2**; it cannot be run here because no paid worker is available.
