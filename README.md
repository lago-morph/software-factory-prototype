# Software Factory v4 — prototype

A Dockerized [Gas City](https://github.com/gastownhall/gascity) deployment you
can stand up on a laptop with one `docker compose up`. It runs a small fleet of
cooperating Claude coding agents that coordinate through a shared bead store and
work on local project directories ("rigs").

This prototype is the **substrate layer** of the
[Software Factory v4 architecture](https://github.com/lago-morph/software-factory):
it gets Gas City installed, the Claude/tmux agent machinery running, and a shared
bead store stood up, so you can drive the factory **manually, by hand**. It is
deliberately scoped for 100% human-guided operation — you issue the work, you
watch the agents, you decide what happens next. Full autonomy and the
v4-specific agent pack are later steps.

The hard parts (building `gc`, installing `dolt`/`bd`/`claude`, the tmux
plumbing, the onboarding dialogs) are baked into the image. You bring a Claude
subscription and an interest in watching agents argue with each other.

## What you need

- **Docker** (Docker Desktop on Windows/macOS, or Docker Engine on Linux).
  Target platform is `linux/amd64`.
- **A Claude Pro or Max subscription.** You do **not** need an Anthropic API
  key — the agents authenticate with a subscription token (see below).

## Quick start

```bash
git clone https://github.com/lago-morph/software-factory-prototype.git
cd software-factory-prototype

# 1. Create your env file
cp .env.example .env

# 2. Generate a subscription auth token (this uses your Claude login, not an
#    API key) and paste it into .env as CLAUDE_CODE_OAUTH_TOKEN:
claude setup-token

# 3. Build and start the stack
docker compose up -d --build

# 4. Watch the city boot
docker compose logs -f city
```

> **Windows note.** Run the commands above in a shell where the `claude` CLI is
> installed (PowerShell, or a WSL shell). `claude setup-token` opens a browser to
> confirm your subscription and prints a token; copy it into `.env`. Everything
> else runs inside Linux containers via Docker Desktop's WSL2 backend.

Once it's up:

```bash
docker compose exec city gc status          # see the agent fleet
docker compose exec city gc session list    # tmux sessions, one per agent
```

> **New here?** [`docs/GETTING-STARTED.md`](docs/GETTING-STARTED.md) is the
> plain-language walkthrough: the mental model, watching the agents live in
> tmux, and a three-run tutorial (including running the example formula).

To peek at what an agent is doing (each agent is a `claude` process in its own
tmux pane), use the session id from `gc session list`:

```bash
docker compose exec city gc session peek <session-id>     # e.g. sfv-c2d (the mayor)
```

## Authentication — subscription, not API key

A Claude Max/Pro subscription is **not** an API key. The flow is:

1. On your laptop (where you're already logged into Claude Code), run
   `claude setup-token`. It produces a long-lived OAuth token tied to your
   subscription.
2. Put that token in `.env` as `CLAUDE_CODE_OAUTH_TOKEN=...`.
3. The container passes it to every `claude` agent it spawns.

If you ever do have a pay-as-you-go API key instead, you can leave the OAuth
token empty and set `ANTHROPIC_API_KEY=` in `.env` — but the subscription path
is the default and what most people on Max will use.

## Giving the city work (manual operation)

The city is **human-guided: you dispatch the work**. The mayor and the rest of
the fleet do housekeeping; they do **not** auto-pick-up tasks you create in a
rig. The reliable, verified way to get a task done is to create a bead and then
**sling** it at the rig's worker with a formula attached — that both routes the
bead and spawns the worker:

```bash
docker compose exec city bash -lc '
  cd /workspace/city &&
  BEAD=$(gc bd create --rig rig1 --type=task "Add a CONTRIBUTING note" --json | jq -r .id) &&
  gc sling rig1/claude "$BEAD" --on sf-small-task'
```

The `rig1/claude` worker then walks the `sf-small-task` formula
(survey → implement → verify → report), commits, and closes the bead.

> **A bead you create but don't sling just sits `open` in the rig scope — it is
> not lost and nothing works it.** Plain `gc bd list` shows the *city* scope, so
> a rig bead won't appear there (this is why it can look like it "disappeared").
> List rig beads explicitly:

```bash
docker compose exec city bash -lc 'cd /workspace/city && gc bd list --rig rig1'
```

## The bead store

The bead store is the city's source of truth — every task, message, gate, and
result lives there. In this prototype it is a **local Dolt SQL server** that gc
manages for itself inside the `city` service, exposed as a host/port to the whole
compose project:

- gc runs the Dolt server on a loopback port inside the container and owns its
  whole lifecycle (creating databases, scopes, and metadata). The entrypoint
  then bridges it (with `socat`) to **`0.0.0.0:3307`**, so it is reachable as
  **`city:3307`** by anything else in the compose project and as
  **`127.0.0.1:3307`** on your host (point a MySQL/Dolt client there to poke
  around).
- Its database files live in a **named Docker volume** (`sfv4-workspace`). This
  data is **purely local and is never pushed to any git remote** — there is no
  durability sync, by design. Keep the volume to keep your history; wipe it with
  `docker compose down -v` to start fresh. (It's a named volume rather than a
  host folder on purpose — Dolt is extremely slow on Docker Desktop's
  Windows/macOS host mounts; the named volume lives in Docker's Linux VM.)

This differs from the earlier `gascity-prototype`, which periodically `dolt
push`ed its bead store to a separate GitHub repo. Here the store is local with no
remote.

> Why gc-managed + a bridge rather than a standalone Dolt service? gc's managed
> Dolt path "just works" — it creates the databases, bead scopes, and metadata
> itself. Pointing the city at a *separate* Dolt server means gc's "external
> endpoint" mode, which has a fiddly bootstrap. The bridge gives you the same
> host/port access without that complexity.

## Rigs

"Rigs" are the project directories the agents work on. By default this prototype
provisions **two empty local rigs** (`rig1`, `rig2`) — no external repositories
required, so a first run is fully self-contained. Put real projects in them, or
point `RIG1_URL` / `RIG2_URL` in `.env` at any git URL to clone real repos
instead.

## Day-to-day

```bash
docker compose up -d --build      # build + start
docker compose logs -f city       # follow the controller
docker compose exec city gc status
docker compose restart city       # restart the controller, keep state
docker compose down               # stop (keeps the volume, so state survives)
docker compose down -v            # stop and WIPE all state + bead store
```

### Keeping costs in check

Every agent is a live `claude` session against your subscription. A handful run
continuously (the mayor and its housekeeping). If you want the city idle between
your tasks, `docker compose stop city` when you're done and `start` it again when
you want to work; the bead store keeps your state.

## Architecture

```
   ┌──────────────────────────────────────────────────────────────────────┐
   │  docker compose project: software-factory-prototype                    │
   │                                                                        │
   │   ┌──────────────────────────────────────────────────────────────┐    │
   │   │  city  (one container)                                        │    │
   │   │  ─────                                                        │    │
   │   │  gc start (controller)                                        │    │
   │   │   ├ mayor / deacon / boot   (claude in tmux)                  │    │
   │   │   ├ rig1 / rig2 observers & dispatchers                       │    │
   │   │   └ worker / dog pools (0..N)                                 │    │
   │   │                                                               │    │
   │   │  gc-managed dolt sql-server (loopback)                        │    │
   │   │         ▲                                                     │    │
   │   │         │ socat bridge                                        │    │
   │   │   0.0.0.0:3307  ──►  reachable as city:3307 (compose net)     │    │
   │   │                      and 127.0.0.1:3307 (host)                │    │
   │   │                                                               │    │
   │   │  /workspace (named volume): city/ · rigs/rig1 · rigs/rig2 ·   │    │
   │   │                           bead-store data (local, NOT synced) │    │
   │   └──────────────────────────────────────────────────────────────┘    │
   └──────────────────────────────────────────────────────────────────────┘
                              │ outbound HTTPS
                              ▼
                    api.anthropic.com  (your Claude subscription)
```

- **One image, one service.** gc runs the controller, the managed Dolt bead
  store, and the agent fleet in the single `city` container; a socat bridge
  republishes the bead store on a host/port.
- **Agents talk through beads, not directly.** The controller reconciles the
  desired agent set, spawns each as a `claude` process in a tmux pane, and routes
  work via beads in the shared store.

See [`docs/PLAN.md`](docs/PLAN.md) for design decisions, what's verified, and how
this maps onto the v4 architecture.

## Backbone components (beyond the substrate)

The repository root packages the **Gas City substrate** — which is Gate B0 of the
v4 [backbone plan](https://github.com/lago-morph/software-factory/blob/main/architectures/v4/backbone-implementation-plan.md)
(the 11 adopt-and-configure Gas City components + C28 Claude Code worker). The
[`factory/`](factory/) directory adds the **Gate B1 build-from-scratch
components** that depend only on that substrate, each self-contained and tested
(stdlib-only, no pip):

| Component | What | Exit check |
|---|---|---|
| [C20 bead-type schema](factory/c20-bead-schema/) | Legal bead types + validator | accepts a valid bead, rejects an ill-typed one |
| [C08/C09 spec intake](factory/c08-c09-spec-intake/) | Spec artifact + prompt-template binding | a toy spec round-trips spec → prompt |
| [C43 fence (boundary half)](factory/c43-fence/) | Deterministic blast-radius typing | types a sample action's blast radius |
| [C29 model-floor policy](factory/c29-model-floor/) | Cost/family routing on the model stylesheet | applies the floor + cross-family rules |

```bash
make -C factory test     # run every component's self-test
```

Later gates (not yet built): the evaluation tier C30–C33 (B2), the C34 holdout
half (B3), and the bootstrap loop C51–C53 (B3).

## Repository layout

```
software-factory-prototype/
├── Dockerfile                  Builds gc from source; installs dolt + bd + node + claude + socat
├── docker-compose.yml          The single `city` service (publishes bead store on 3307)
├── entrypoint.sh               Render config, provision rigs, bridge the bead store, gc start
├── city.toml.example           Templated city config (envsubst'd at startup)
├── pack/pack.toml              Imports the bundled gastown role pack
├── factory/                    Gate B1 backbone components (C20, C08/C09, C43, C29) + tests
├── .env.example                Subscription-auth + rig config template
└── docs/PLAN.md                Design, decisions, verification status, v4 mapping
```

## Building the image

`docker compose up --build` builds everything itself — `gc` is compiled from
source (Go 1.26 + ICU), and `dolt`, `bd`, Node, and the Claude Code CLI are
installed in the image. No pre-staged binaries are needed. Useful build args
(override with `--build-arg`): `GASCITY_REF`, `BD_VERSION`, `NODE_MAJOR`,
`CLAUDE_CODE_VERSION`.
