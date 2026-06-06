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

To peek at what an agent is doing (each agent is a `claude` process in its own
tmux pane):

```bash
docker compose exec city tmux -L software-factory-v4 capture-pane -t <session> -p
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

The city is human-guided: it won't invent work for itself beyond routine
housekeeping. You hand it tasks as **beads** in a rig's scope:

```bash
docker compose exec city bash -lc \
  'cd /workspace/rigs/rig1 && gc bd create --type=task "rewrite the README"'
```

The coordinator agent (gastown's *mayor*) notices the open bead, dispatches a
worker, the worker does the task and commits, an optional reviewer checks it, and
housekeeping closes it out. Inspect the bead graph any time:

```bash
docker compose exec city bash -lc 'cd /workspace/rigs/rig1 && gc bd list'
```

## The bead store

The bead store is the city's source of truth — every task, message, gate, and
result lives there. In this prototype it is a **single local Dolt SQL server**
running as its own compose service (`beadstore`):

- It listens on **`beadstore:3307`** (host/port) on the compose network, so the
  city — and anything else in the compose project, including `docker compose
  exec` clients — can connect to it.
- Its database files live in the **`beads-data` named volume**. This data is
  **purely local and is never pushed to any git remote** — there is no
  durability sync, by design. Keep the volume to keep your history; delete it
  (`docker compose down -v`) to start fresh.
- The port is also published to `127.0.0.1:3307` on your host, so you can point a
  local MySQL/Dolt client at it if you want to poke around.

This differs from the earlier `gascity-prototype`, which kept its bead store in
embedded Dolt and periodically `dolt push`ed it to a separate GitHub repo. Here
the store is a shared server with no remote.

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
docker compose down               # stop (keeps the beads-data volume)
docker compose down -v            # stop and WIPE the bead store
```

### Keeping costs in check

Every agent is a live `claude` session against your subscription. A handful run
continuously (the mayor and its housekeeping). If you want the city idle between
your tasks, `docker compose stop city` when you're done and `start` it again when
you want to work; the bead store keeps your state.

## Architecture

```
        ┌─────────────────────────────────────────────────────────────┐
        │  docker compose project: software-factory-prototype          │
        │                                                              │
        │   ┌──────────────────────────┐     ┌───────────────────────┐ │
        │   │  city                    │     │  beadstore            │ │
        │   │  ──────                  │     │  ─────────            │ │
        │   │  gc start (controller)   │ TCP │  dolt sql-server      │ │
        │   │   ├ mayor   (claude)     │────▶│  beadstore:3307       │ │
        │   │   ├ deacon  (claude)     │     │                       │ │
        │   │   ├ boot    (claude)     │     │  data: beads-data vol │ │
        │   │   ├ rig observers/...    │     │  (local, NOT synced)  │ │
        │   │   └ worker pool (0..N)   │     └───────────────────────┘ │
        │   │  /workspace (bind mount) │                               │
        │   │   ├ city/  rigs/rig1/    │                               │
        │   └──────────────────────────┘                               │
        └──────────────────────────────────────────────────────────────┘
                              │ outbound HTTPS
                              ▼
                    api.anthropic.com  (your Claude subscription)
```

- **One image, two services.** Both `city` and `beadstore` run the same image;
  `beadstore` overrides the entrypoint to run `dolt sql-server`.
- **Agents talk through beads, not directly.** The controller reconciles the
  desired agent set, spawns each as a `claude` process in a tmux pane, and routes
  work via beads in the shared store.

See [`docs/PLAN.md`](docs/PLAN.md) for design decisions, what's verified, and how
this maps onto the v4 architecture.

## Repository layout

```
software-factory-prototype/
├── Dockerfile                  Builds gc from source; installs dolt + bd + node + claude
├── docker-compose.yml          The beadstore + city services
├── entrypoint.sh               city service: render config, provision rigs, gc start
├── beadstore-entrypoint.sh     beadstore service: run dolt sql-server (TCP, no remote)
├── city.toml.example           Templated city config (envsubst'd at startup)
├── pack/pack.toml              Imports the bundled gastown role pack
├── .env.example                Subscription-auth + rig config template
└── docs/PLAN.md                Design, decisions, verification status, v4 mapping
```

## Building the image

`docker compose up --build` builds everything itself — `gc` is compiled from
source (Go 1.26 + ICU), and `dolt`, `bd`, Node, and the Claude Code CLI are
installed in the image. No pre-staged binaries are needed. Useful build args
(override with `--build-arg`): `GASCITY_REF`, `BD_VERSION`, `NODE_MAJOR`,
`CLAUDE_CODE_VERSION`.
