# Software Factory v4 prototype — design & decisions

This prototype stands up the **substrate layer** of the
[Software Factory v4 architecture](https://github.com/lago-morph/software-factory)
so it can be driven manually. The goal for this iteration, stated by the
operator, was: *"get Gas City installed, the Claude/tmux stuff set up, and
whatever else is required to run it manually in 100% human-guided usage, packaged
so it comes up with a `docker compose up` on a laptop."*

## Scope

In scope (this iteration):

- Gas City (`gc`) built and running in a container.
- The Claude/tmux agent machinery working (interactive `claude` per agent, no
  hung onboarding dialogs).
- A shared local bead store (Dolt SQL server) the whole compose project can use.
- Self-contained, one-command laptop bring-up (`docker compose up --build`).
- Subscription-based Claude auth (no API key).
- Manual, human-guided operation: the operator issues work as beads.

Explicitly deferred:

- The v4-specific agent pack (intent intake, spec linter, judge harness,
  CXDB/telemetry, self-healing loops — the C0x–C5x components). This prototype
  runs the **bundled gastown pack** so there is a working fleet day one.
- Broad autonomous operation / scheduled order fan-out beyond gastown's
  defaults. (One narrow slice is now **in scope and shipped**: autonomous
  *dispatch* of rig task beads — see the `route-rig-tasks` decision below.
  Higher-level autonomy — intent intake, self-healing, eval-gated promotion —
  remains deferred.)
- Multi-host / scale concerns.

## Key decisions

### Bead store: gc-managed local Dolt server, bridged to a host/port, no remote

The operator asked for *"a local server that anyone in the docker compose group
can access via a host/port, with a file it writes to that is not synced."*

Implementation: gc manages the Dolt SQL server itself inside the `city`
container (its proven "managed" path — it creates the databases, bead scopes, and
metadata). gc binds it to a deterministic loopback port; the entrypoint then
bridges it with `socat` to `0.0.0.0:3307`, reachable as **`city:3307`** across the
compose project and **`127.0.0.1:3307`** on the host. The database files live
in the **`sfv4-workspace`** named Docker volume (a named volume, not a host bind
mount — Dolt is unusably slow on Docker Desktop's Windows/macOS host mounts).
There is **no git remote and no
`dolt push`** — the store is local-only and never synced.

Why gc-managed + a bridge, not a dedicated Dolt service:

- The bundled **gastown pack makes ~368 `gc bd` calls**, and `gc bd` is gated to
  *bd-contract* providers. The gc-native `provider = "file"` store disables
  `gc bd`, so the proven gastown fleet would not run on it. Keeping
  `provider = "bd"` keeps the fleet working.
- A dedicated Dolt service would force gc's **external-endpoint** mode, which has
  a fiddly bootstrap (gc has no `init` flag for it; `use-external` needs scope
  metadata that only scope-init creates — a chicken-and-egg). The managed path
  avoids all of that. The socat bridge gives the same host/port access.
- Pinning `[dolt].port` (to force a nice 3307) breaks gc 1.1.1's managed Dolt
  lifecycle, so we omit `[dolt]` entirely and discover the real (deterministic,
  loopback) port at runtime from `.gc/runtime/packs/dolt/dolt-state.json`.

Difference from the older `gascity-prototype`: that one periodically `dolt
push`ed to a separate `gascity-proto-beadstore` GitHub repo for durability. Here
we drop the remote entirely; durability is "keep the `sfv4-workspace` volume."

### Auth: Claude subscription, not API key

The operator is on a Claude Max subscription, which is not an API key. The flow
is `claude setup-token` on the laptop → paste the OAuth token into `.env` as
`CLAUDE_CODE_OAUTH_TOKEN` → the container passes it to every spawned `claude`.
`ANTHROPIC_API_KEY` remains supported but optional/empty by default.

### Rigs: self-contained local repos by default

`RIG1_URL`/`RIG2_URL` empty (the default) makes the entrypoint `git init` two
empty local rigs, so a first run needs zero external repositories — only a Claude
subscription. Set the URLs to clone real projects instead.

### Autonomous dispatch: a controller `exec` order, not a mayor policy change

The goal for this iteration was that `gc bd create --rig rigN …` gets worked with
**no manual nudge and no manual sling**. Out of the box it does not: the **mayor**
(gastown's coordinator) wakes on a cadence + on nudges, *triages* the open beads,
and idles — so a bead created after its last wake sits `open` until the next wake,
and the mayor may decline it as not worth doing. (Both observed live: a bead went
unseen until nudged, and the mayor once judged a test bead spurious.)

The fix is [`pack/orders/route-rig-tasks.toml`](../pack/orders/route-rig-tasks.toml): a city-level
**`exec` order** on a 30s `cooldown`. The controller runs its script directly (no
agent, no LLM, no token spend) and, for each registered rig, slings the ready,
unrouted, top-level **task** beads to that rig's `gastown.polecat` on the
`sf-small-task` formula — the exact dispatch the docs describe, just automatic.

Why this shape, over the alternatives we weighed:

- **An `exec` order that slings directly (chosen)** side-steps the mayor's triage
  entirely — a created task bead is dispatched regardless of whether the mayor
  would have judged it worth doing — and costs nothing (controller-side script, no
  agent wake). It mirrors the already-verified manual `gc sling`, so the
  downstream pipeline (polecat → refinery → close) is unchanged.
- **Loosening the `[daemon]` wake budget** (`max_wakes_per_tick`) only changes how
  *fast* sessions materialize; it does not make the mayor route a bead it triaged
  away, so it does not by itself give hands-off dispatch. Left at the default.
- **A mayor prompt/policy change** to auto-sling every open bead is heavier,
  diverges from gastown's mayor design, and still routes through an LLM wake per
  cycle. Not needed once the order does the routing.

The routing filter is deliberately narrow so the order never re-pours formula
scaffolding: it selects only beads with `issue_type == "task"`, `status == "open"`,
and **no** `gc.routed_to` / `gc.step_ref` / `gc.root_bead_id`, and `gc.kind !=
"workflow"`. That excludes already-routed beads (including the mayor's own routes),
molecule step-beads and members, and molecule/workflow roots. Once a bead is slung
its `gc.routed_to` is set, so the next 30s tick skips it (idempotent). The mayor,
`gc session nudge`, and `gc sling` all still work as manual overrides.

### Image: build everything in the Dockerfile (laptop-portable)

`gc` is compiled from source (Go 1.26, CGO + ICU) in a `golang:1.26-bookworm`
builder stage, then copied into an `ubuntu:24.04` runtime that installs `dolt`,
`bd`, Node (via NodeSource), and the Claude Code CLI. Nothing is pre-staged, so
`docker compose up --build` works on a laptop with only Docker installed. (The
older prototype COPYed host-built binaries because its build ran in a
network-restricted sandbox; that constraint does not apply on a laptop.)

Target platform is **linux/amd64** only (the operator's laptop is Windows/x86-64;
arm64 was intentionally dropped to keep the build simple).

## Things this build had to figure out

Carried forward from the gascity-prototype and re-confirmed here:

1. **`gc bd` requires a bd-contract provider** — the gc-native `file` provider
   disables it, so the gastown pack needs `provider = "bd"`.
2. **gc-managed Dolt is loopback-only and on a hashed port** — gc binds the
   managed server to 127.0.0.1 on a deterministic port (hashed from the city
   path); the `[dolt].host` field is a *connect* host and rejects `0.0.0.0`.
   Setting `[dolt].port` to pin a nice port breaks the managed lifecycle in gc
   1.1.1. So we omit `[dolt]`, read the live port from
   `.gc/runtime/packs/dolt/dolt-state.json`, and `socat`-bridge it to
   `0.0.0.0:3307` for compose-group/host access.
3. **gc 1.1.1 config gotchas** — the workspace `provider` must be declared in a
   `[providers.claude] base = "builtin:claude"` catalog entry; workspace
   identity (`name`) belongs in `.gc/site.toml` (deprecated in `city.toml`).
4. **Interactive `claude` has three first-run dialogs** (theme, trust-folder,
   bypass-permissions) that hang an agent forever if not pre-acked. Global acks
   are baked into the image's `~/.claude.json`; per-path `projects` acks are
   written by the entrypoint (it knows the runtime city/rig paths).
5. **`claude --dangerously-skip-permissions` refuses to run as root** unless
   `IS_SANDBOX=1` is set; the container is itself isolated, so it's set.
6. **PID 1 must reap zombies** — `bd`/`dolt` spawn many short-lived children;
   compose `init: true` (tini) prevents a defunct-process pileup.
7. **Don't import `maintenance` directly** — gastown imports it transitively;
   a second import duplicates the `dog` agent and refuses startup.
8. **Rig prefix collisions** — `rig1`/`rig2` both auto-derive prefix `ri`; set
   explicit `prefix = "r1"/"r2"` in city.toml.
9. **gc needs CGO + ICU, matched builder/runtime** — it pulls in Dolt's
   `go-icu-regex`; the builder needs `libicu-dev` and the runtime needs the same
   ICU major (build on ubuntu:24.04 = ICU 74 = the runtime, or gc fails to load
   with a missing `libicu*.so.NN`).

## Verification status

Verified in a Docker-enabled sandbox (2026-06-06, `gc` built from gascity
`425ec63`, gc 1.1.1 / bd 1.0.4 / dolt 2.1.4 / node 22 / claude-code 2.1.x):

- The image builds end-to-end (gc compiled from source; dolt, bd, node,
  claude-code, socat installed); all tools run.
- The city boots from the real entrypoint: pack imports install, rigs are
  provisioned, gc starts the managed Dolt server, and bead scopes initialize
  (~8 s to first working `gc bd`).
- `gc bd create` / `gc bd list` work against the managed store; `gc status`
  shows the full 9-agent gastown fleet configured.
- The socat bridge republishes the bead store on `0.0.0.0:3307`; it is reachable
  from a **separate container** on the compose network at `city:3307` (verified
  by a cross-container TCP connect) and is published to `127.0.0.1:3307`.

**Live, real-token run (2026-06-07, gc 1.2.1) — native dispatch works end to
end.** Root cause of the earlier "nothing picks up the bead": `[[rigs]]` entries
had no pack import, so the gastown **rig roles never expanded**
(`[defaults.rig.imports]` is only a template consumed by `gc rig add`, which we
don't run — we declare rigs statically). Fix: give each `[[rigs]]` its own
`[rigs.imports.gastown]`. With that, `gc agent list` shows
`rigN/gastown.{witness,refinery,polecat}`, and the native pipeline runs: the
**mayor** routes a bead (`gc sling rigN/gastown.polecat`), the polecat pool
auto-scales 0→1, the polecat claims + commits on a worktree branch, and the
**refinery** merges it into the rig and closes the bead. Verified: a real
`Add … description … README` commit (`542f2ef`) merged into `rig1` main, bead
closed — no manual sling at the dispatch step.

**Autonomous dispatch verified live (2026-06-07, gc 1.2.1) — no nudge, no sling.**
With the `route-rig-tasks` order shipped (see the decision above), a plain
`gc bd create --rig rig1 --type=task "…"` reached `closed` fully unattended. The
shipped `docker compose` stack was exercised (the real compose file + entrypoint,
plus a sandbox-only CA override for the test network), with a real subscription
token. Observed timeline from creation (bead `r1-1lz`): auto-routed to
`rig1/gastown.polecat` at **t+69s** (the order's first applicable 30s tick) → the
polecat claimed it (`in_progress`) at **t+194s** → the polecat committed
`Add CONTRIBUTING.md …` on a worktree branch → the **refinery** merged it into
`rig1` main (commit `7a691f9`) and the bead went **`closed`** at **~t+10m**. A
real `CONTRIBUTING.md` landed on `rig1` main with no operator action at any step.
The tokenless controller-side routing was also confirmed independently (a created
bead's `gc.routed_to` is set within ~one 30s tick), and re-running the order
re-slings nothing (idempotent). The manual overrides still work: `gc session
nudge <mayor-id> "<message>"` returns 0 (`Nudged gastown.mayor`).

**Behavioral note (now an override, not the default path):** the mayor still
*triages* — it does not blindly sling every open bead, and on its own it may
decline one. That no longer blocks dispatch, because `route-rig-tasks` routes task
beads directly, side-stepping triage. `gc session nudge` / explicit `gc sling`
remain available to push a specific bead or to route work the order won't (it only
routes top-level `task` beads). Per-session `wake_budget` throttling still delays
agents *materializing* by up to a tick or two (it does not affect whether a bead
is routed), which is why a small task completes in a few minutes rather than
seconds; it is left at the gastown default.

## How this maps onto v4

- The bead store is v4 component **C19/C20** (work-graph + schema); here it is the
  Phase-0 "real store" using Dolt server mode rather than the file backend, to
  keep the gastown fleet operable.
- Gas City itself is **C01** (the substrate). The session/tmux machinery is
  **C04** (session provider) and **C28** (claude-code agent loop).
- The gastown pack is a stand-in for the future v4 pack (**C02** pack ABI). The
  v4-specific roles and the eval/telemetry/self-healing components (C10–C54) are
  the next build steps once manual operation is comfortable.
- The `route-rig-tasks` order is a first, deliberately minimal slice of the v4
  **autonomous dispatch** surface: a mechanical, no-LLM router that turns "create a
  bead" into worked-and-merged. The v4 design layers intent intake, eval gating,
  and self-healing on top of this seam — those remain deferred (see Scope).
