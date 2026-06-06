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
- Autonomous operation / scheduled order fan-out beyond gastown's defaults.
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
under the mounted **`./workspace`** directory. There is **no git remote and no
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
we drop the remote entirely; durability is "keep `./workspace`."

### Auth: Claude subscription, not API key

The operator is on a Claude Max subscription, which is not an API key. The flow
is `claude setup-token` on the laptop → paste the OAuth token into `.env` as
`CLAUDE_CODE_OAUTH_TOKEN` → the container passes it to every spawned `claude`.
`ANTHROPIC_API_KEY` remains supported but optional/empty by default.

### Rigs: self-contained local repos by default

`RIG1_URL`/`RIG2_URL` empty (the default) makes the entrypoint `git init` two
empty local rigs, so a first run needs zero external repositories — only a Claude
subscription. Set the URLs to clone real projects instead.

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

Not exercised here (by design — it spends the operator's subscription): agents
were left without a token, so they stay in `stopped`/`reserved` state. Live
end-to-end task execution (mayor dispatches a worker that does a rig task) is the
operator's first run on the laptop with a real `CLAUDE_CODE_OAUTH_TOKEN`.

## How this maps onto v4

- The bead store is v4 component **C19/C20** (work-graph + schema); here it is the
  Phase-0 "real store" using Dolt server mode rather than the file backend, to
  keep the gastown fleet operable.
- Gas City itself is **C01** (the substrate). The session/tmux machinery is
  **C04** (session provider) and **C28** (claude-code agent loop).
- The gastown pack is a stand-in for the future v4 pack (**C02** pack ABI). The
  v4-specific roles and the eval/telemetry/self-healing components (C10–C54) are
  the next build steps once manual operation is comfortable.
