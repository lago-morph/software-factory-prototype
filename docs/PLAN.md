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

### Bead store: shared local Dolt server, no remote sync

The operator asked for *"a local server that anyone in the docker compose group
can access via a host/port, with a file it writes to that is not synced."*

Implementation: a dedicated **`beadstore`** compose service runs `dolt
sql-server` listening on TCP `beadstore:3307` (also published to
`127.0.0.1:3307` on the host). Its database files live in the **`beads-data`
named volume**. There is **no git remote and no `dolt push`** — the store is
local-only and never synced. The city is pointed at it as an *external* Dolt
endpoint (`gc beads city use-external --host beadstore --port 3307`).

Why a real server (not embedded Dolt or the gc-native file provider):

- The bundled **gastown pack makes ~368 `gc bd` calls**, and `gc bd` is gated to
  *bd-contract* providers. The gc-native `provider = "file"` store disables
  `gc bd`, so the proven gastown fleet would not run on it. Keeping
  `provider = "bd"` keeps the fleet working.
- A server (vs embedded single-writer Dolt) is what lets multiple agents — and
  any other compose service or `docker compose exec` client — share the store
  over a host/port, which is what the operator asked for.

Difference from the older `gascity-prototype`: that one ran embedded/managed Dolt
*and* periodically `dolt push`ed to a separate `gascity-proto-beadstore` GitHub
repo for durability. Here we drop the remote entirely; durability is "keep the
named volume."

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
2. **`gc` talks to an external Dolt server over TCP host/port** — its bd-env
   builder sets `BEADS_DOLT_SERVER_HOST/PORT/USER`, not a unix socket. So the
   "shared socket" is a TCP socket (`beadstore:3307`).
3. **Interactive `claude` has three first-run dialogs** (theme, trust-folder,
   bypass-permissions) that hang an agent forever if not pre-acked. Global acks
   are baked into the image's `~/.claude.json`; per-path `projects` acks are
   written by the entrypoint (it knows the runtime city/rig paths).
4. **`claude --dangerously-skip-permissions` refuses to run as root** unless
   `IS_SANDBOX=1` is set; the container is itself isolated, so it's set.
5. **PID 1 must reap zombies** — `bd`/`dolt` spawn many short-lived children;
   compose `init: true` (tini) prevents a defunct-process pileup.
6. **Don't import `maintenance` directly** — gastown imports it transitively;
   a second import duplicates the `dog` agent and refuses startup.
7. **Rig prefix collisions** — `rig1`/`rig2` both auto-derive prefix `ri`; set
   explicit `prefix = "r1"/"r2"` in city.toml.
8. **gc needs CGO + ICU** — it pulls in Dolt's `go-icu-regex`; the builder needs
   `libicu-dev`, the runtime needs `libicu74`, and builder/runtime glibc
   generations must be compatible (bookworm-built runs on noble).

## Verification status

See the PR description for the exact, dated verification results from the build
sandbox. In general: `gc` compiles from source; the image builds; the bead-store
server starts and the city connects to it. End-to-end agent task execution
depends on a live Claude subscription token and is exercised by the operator on
the laptop.

## How this maps onto v4

- The bead store is v4 component **C19/C20** (work-graph + schema); here it is the
  Phase-0 "real store" using Dolt server mode rather than the file backend, to
  keep the gastown fleet operable.
- Gas City itself is **C01** (the substrate). The session/tmux machinery is
  **C04** (session provider) and **C28** (claude-code agent loop).
- The gastown pack is a stand-in for the future v4 pack (**C02** pack ABI). The
  v4-specific roles and the eval/telemetry/self-healing components (C10–C54) are
  the next build steps once manual operation is comfortable.
