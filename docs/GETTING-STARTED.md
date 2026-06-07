# Getting started — running the factory on your laptop

**What this is:** a plain-language walkthrough for standing up the Software
Factory prototype on a laptop, watching the fleet of Claude agents work inside
tmux, and driving a few simple runs by hand — including one small four-step
*formula*. **What this is not:** the design rationale (that's
[`PLAN.md`](PLAN.md)) or the component internals (that's [`../factory/`](../factory/)).

Everything here is hand-driven. You issue the work; you watch the agents; you
decide what happens next.

---

## The mental model (read this first)

The whole system is one **city**: a running deployment that owns a config, a set
of **agents**, a set of **rigs**, and a **bead store**.

```mermaid
flowchart LR
  you([You]) -->|gc bd create| store[(Bead store)]
  order[route-rig-tasks order] -->|auto-routes| polecat[Polecat worker]
  polecat -->|edits + commits branch| rig[Rig repo]
  refinery[Refinery] -->|merges branch| rig
```

The five words you need:

| Word | What it is |
|---|---|
| **City** | One running deployment — everything in `docker compose`. |
| **Rig** | A project directory the agents work on. This prototype ships two empty local ones (`rig1`, `rig2`). |
| **Bead** | A unit of work — like an issue, but the agents read and write them directly. Lives in the bead store. |
| **Agent** | A long-running `claude` session with a role and a scope. The city runs one per role, each in its own tmux pane. |
| **Formula** | A small recipe: a few steps wired into a graph that one agent walks top to bottom. |

**How work flows.** You create a bead — that's the only step you take. A built-in
controller order (`route-rig-tasks`) routes it to a rig's **polecat** worker
within about a minute; the polecat does the task and commits on a worktree branch,
and the **refinery** merges that branch into the rig and closes the bead. The city
works your task end-to-end, unattended.

> **Where does the routing come from?** The `route-rig-tasks` order is a plain
> controller `exec` that runs every 30s (no agent, no token spend); it slings
> ready, unrouted rig *task* beads straight to their polecat. It deliberately
> side-steps the **mayor's** triage (the coordinator that, in stock gastown,
> decides what's worth doing and otherwise waits for you) so a created task bead
> doesn't sit `open` waiting to be noticed. You can still drive the mayor by hand
> — **nudge** it (`gc session nudge <mayor-id> "<message>"` — the message arg is
> required) or route a specific bead yourself with `gc sling` — as a manual
> override (both shown in the tutorial below). A just-created bead may sit `open`
> in the rig for a few seconds before the order picks it up; `gc bd list --rig
> rig1` shows it.

---

## What you need

- **Docker** — Docker Desktop on Windows (uses the WSL2 backend) or macOS, or
  Docker Engine on Linux. That's the only thing the laptop needs; the image
  builds everything else itself.
- **A Claude Pro or Max subscription.** Not an API key — a subscription. The
  agents sign in with a token minted from your subscription.

---

## Step 1 — get the code and a subscription token

```bash
git clone https://github.com/lago-morph/software-factory-prototype.git
cd software-factory-prototype
cp .env.example .env
```

Now mint the token. On the machine where you already use Claude Code, run:

```bash
claude setup-token
```

It confirms your subscription in a browser and prints a long-lived token. Paste
it into `.env` as `CLAUDE_CODE_OAUTH_TOKEN=...`. Leave `ANTHROPIC_API_KEY` empty
— that line is only for the pay-as-you-go API case, which most subscription
users never touch.

> **Windows note.** Run `git`, `claude setup-token`, and the `docker compose`
> commands in a shell where the `claude` CLI is installed (PowerShell or a WSL
> shell). The factory itself runs in Linux containers under Docker Desktop.

---

## Step 2 — bring the city up

```bash
docker compose up -d --build
```

The first build compiles Gas City (`gc`) from source and installs the rest, so
the first `up` is slow. After that the image is cached and starts quickly. Watch
it boot:

```bash
docker compose logs -f city
```

When the controller settles, check the fleet:

```bash
docker compose exec city gc status
```

You should see the city's agents — `gastown.mayor` (the coordinator),
`gastown.deacon` and `gastown.boot` (housekeeping), `gastown.dog`, and the
per-rig gastown roles: `rig1/gastown.witness` (watches the rig),
`rig1/gastown.polecat` (the worker that does tasks), and `rig1/gastown.refinery`
(merges finished work) — likewise for `rig2`. The polecat is `min=0`, so it only
appears once there's work routed to it.

---

## Step 3 — watch the agents in tmux

This is the part people find surprising: **every agent is its own live `claude`
session**, and they all run as panes under a single tmux server inside the
container. The controller starts them, watches them, and restarts any that die.

```mermaid
flowchart TD
  ctrl[gc controller] --> tmux[tmux server -L software-factory-v4]
  tmux --> p1[pane: gastown.mayor — claude]
  tmux --> p2[pane: gastown.deacon — claude]
  tmux --> p3[pane: rig1/gastown.witness — claude]
  tmux --> p4[pane: rig1/gastown.polecat — claude]
```

**List the sessions** (one per agent — note the short `ID` column, e.g. `sfv-c2d`):

```bash
docker compose exec city gc session list
```

**Peek at what one agent is doing** without disturbing it — pass the session
**id** from the list:

```bash
docker compose exec city gc session peek <session-id>      # e.g. sfv-c2d (the mayor)
```

**Sit on an agent's shoulder live** and watch it think in real time:

```bash
docker compose exec -it city gc session attach <session-id>
```

To leave without killing the agent, **detach**: press `Ctrl-b` then `d`. (Don't
type `exit` — that would end the agent's session.)

> **Going through raw tmux instead?** The tmux socket is `software-factory-v4`,
> but tmux session names aren't the dotted names `gc session list` prints — gc
> maps `.`→`__` and `/`→`--`. So `gastown.mayor` is the tmux target
> `gastown__mayor`, and `rig1/control-dispatcher` is `rig1--control-dispatcher`:
> ```bash
> docker compose exec city tmux -L software-factory-v4 ls
> docker compose exec city tmux -L software-factory-v4 capture-pane -t gastown__mayor -p
> ```
> The `gc session peek`/`attach` commands above avoid this translation, so prefer them.

---

## Tutorial — three simple runs

These build on each other. Do them in order. And a standing expectation: **the
first time you try a new kind of task, something will be off.** That's normal —
the win is how cheaply you can look at a pane, adjust, and try again, not whether
it works on the first shot.

### Run 1 — create a bead and the city works it

Create a bead from the **city** dir with `--rig`. This is the *only* command you
run — there's no second step:

```bash
docker compose exec city bash -lc \
  'cd /workspace/city && gc bd create --rig rig1 --type=task "Add a CONTRIBUTING note to rig1"'
```

Now just watch. Within about a minute the `route-rig-tasks` order routes the bead
to the rig's polecat (it sets `gc.routed_to` and the polecat pool scales `0→1`);
the polecat walks **survey → implement → verify → report**, commits on a worktree
branch, and the refinery merges it into the rig and closes the bead. A small task
like this finishes in a few minutes, unattended. Watch it happen:

```bash
docker compose exec city gc session list                       # the rig1/gastown.polecat worker appears once routed
docker compose exec city gc session peek <polecat-session-id>  # peek to watch it think
docker compose exec city bash -lc 'cd /workspace/city && gc bd show <bead-id>'   # poll until it shows CLOSED
```

> **Watching progress.** A live event stream (`gc events --follow`) needs the
> supervisor API (`gc supervisor start`), which this standalone deployment doesn't
> run — so `gc session peek` plus polling `gc bd show <bead-id>` is how you watch.
> Use `gc bd show <bead-id>` (not `gc bd list`) to see the final state: plain
> `gc bd list` shows only the *city* scope, and even `gc bd list --rig rig1` hides
> `closed` beads by default, so a finished task looks like it "vanished" from the
> list when it has actually closed.

**Manual override (optional).** You don't need this for normal use — the order
above routes every task bead on its own. But if you want to push a bead the
instant you create it, or route work the order won't (it only routes top-level
`task` beads), drive the dispatch by hand. Nudge the mayor:

```bash
docker compose exec city gc session list                   # find the gastown.mayor id
# nudge requires a message arg (the text handed to the mayor session):
docker compose exec city gc session nudge <mayor-id> "Check open beads and dispatch actionable work."
```

…or sling a specific bead yourself (this both sets `gc.routed_to` and spawns the
worker; add `--dry-run` to preview without routing):

```bash
docker compose exec city bash -lc '
  cd /workspace/city &&
  BEAD=$(gc bd create --rig rig1 --type=task "Add a CONTRIBUTING note to rig1" --json | jq -r .id) &&
  gc sling rig1/gastown.polecat "$BEAD" --on sf-small-task'
```

### Run 2 — read the work graph

When the worker finishes, everything it did is in the bead store and the rig repo.

```bash
# the bead, now CLOSED, with the worker's report in its notes
docker compose exec city bash -lc 'cd /workspace/city && gc bd show <bead-id>'

# the four step-beads (survey/implement/verify/report) the formula created;
# --all includes the now-closed beads (the default list hides closed ones)
docker compose exec city bash -lc 'cd /workspace/city && gc bd list --rig rig1 --all'
```

And confirm the actual change landed as a commit in the rig repo:

```bash
docker compose exec city bash -lc 'cd /workspace/rigs/rig1 && git --no-pager log --oneline -3'
```

You should see the worker's commit (e.g. `Add CONTRIBUTING.md note to rig1`) on
top of the rig's initial commit, and a real `CONTRIBUTING.md` in the rig.

### Run 3 — understand and customize the formula

The thing that made Run 1 work is the **formula** — a small graph of steps one
agent walks in order. This prototype ships
[`sf-small-task`](../pack/formulas/sf-small-task.toml):

```mermaid
flowchart LR
  survey --> implement --> verify --> report
```

Each box is a step the worker does in turn: understand the task, make the change,
check its own diff, then commit and report back. Confirm the city sees it:

```bash
docker compose exec city gc formula list      # sf-small-task should appear
```

**Want to change the recipe?** Edit
[`pack/formulas/sf-small-task.toml`](../pack/formulas/sf-small-task.toml) — each
`[[steps]]` block is one node, and its `needs` list is the arrows into it. Add a
node, rebuild (`docker compose up -d --build`), and it shows up in
`gc formula list`. The formula file *is* the graph. Then dispatch another task
exactly as in Run 1 to watch your new recipe run.

---

## When things go wrong

| Symptom | Likely cause | What to do |
|---|---|---|
| Agents do nothing / error immediately | `CLAUDE_CODE_OAUTH_TOKEN` missing or stale in `.env` | Re-run `claude setup-token`, update `.env`, `docker compose restart city`. |
| Build is very slow the first time | `gc` is compiled from source | Expected once; the image is cached afterward. |
| An agent's pane looks stuck | The agent is waiting or wedged | Peek with `gc session peek <id>`; the controller restarts dead agents on its own. |
| You want a clean slate | Old bead/rig state in the volume | `docker compose down -v`, then `up` again. |
| Bead store is **extremely slow** / "tries native store over and over" | State on a Windows/macOS host bind mount (Dolt crawls on Docker Desktop's drvfs/9p) | Make sure the compose `volumes:` uses the named volume `sfv4-workspace`, not `./workspace`. This is the default; don't change it back. |

---

## Stopping and keeping costs sane

Every agent is a live `claude` session against your subscription, and a few run
continuously for housekeeping. When you're done working:

```bash
docker compose stop city      # pause everything; your state stays in the volume
docker compose start city      # resume later, right where you left off
```

| Command | Effect |
|---|---|
| `docker compose stop city` | Pause the fleet; keep all state. |
| `docker compose down` | Stop and remove the container; the `sfv4-workspace` volume (incl. the bead store) survives. |
| `docker compose down -v` | Full reset — wipes the bead store and rigs. |

The bead store lives in the `sfv4-workspace` named volume and is never pushed
anywhere, so stopping the city never loses your work; it just goes quiet.
