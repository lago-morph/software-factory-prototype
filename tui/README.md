# Gascity progress tracker (TUI) — operator instrument

A read-only terminal UI for watching this prototype work: the flow of beads
through agent sessions, the contents and status of individual beads, the commit
diffs a bead's execution produced, and the formulas the factory runs.

It is an **operator instrument** built *alongside* the v4 backbone (not one of
the backbone's 25 components). The durable plan — the three phases, the chunk
ladder, the card-driven enhancement model, and why it's an instrument rather
than a component — lives in the `software-factory` repo at
[`architectures/v4/tui-operator-instrument-plan.md`](https://github.com/lago-morph/software-factory/blob/main/architectures/v4/tui-operator-instrument-plan.md),
and it tracks
[idea-pipeline issue #21](https://github.com/lago-morph/idea-pipeline/issues/21).

## Running it

The TUI is baked into the city image and runs inside the container:

```bash
docker compose exec city sftui
```

(`sftui` is a shim for `python3 /opt/tui/beadview.py`.) It is **stdlib Python +
curses** — no pip, no network.

> **Status: v0.1 placeholder.** `beadview.py` currently just explains itself.
> The first real version is produced by the prototype's own build loop (see
> below), reviewed, merged, and baked in on the next image build.

## How it gets built (dogfood)

The viewer is built *by the prototype* in small chunks. Each chunk is a single
`gc bd create` task prompt; the fleet builds it; we keep complexity low so the
early factory can actually finish it. The chunk ladder:

| Rung | Capability | gc surface it reads |
|---|---|---|
| 1 | Browse **beads** (city + each rig); Enter=details, Esc=back | `gc bd list` / `gc bd list --rig <name>` / `gc bd show <id>` |
| 2 | Browse **sessions**; Enter shows a `tail -30` peek | `gc session list` / `gc session peek <id>` |
| 3+ | Commit **diffs**; configurable **polling** + force-refresh; interrupt-driven if feasible; **formula** browsing | rig git worktrees; event bus (C23) if watchable |

Two invariants on every rung: **keyboard help is always visible**, and the
viewer is **read-only**.

### Build-rig setup (optional, opt-in)

To have the prototype build/extend the TUI and push the result back for review,
point a rig at *this* repo and give the container a push token (both in `.env`,
which is gitignored):

```bash
RIG1_URL=https://github.com/lago-morph/software-factory-prototype.git
RIG_PUSH_TOKEN=...   # GitHub token with push scope
```

Then drive the chunk-1 bead from the city dir:

```bash
docker compose exec city bash -lc 'cd /workspace/city && gc bd create --rig rig1 --type=task "<chunk-1 prompt>"'
```

The build is bounded to the `tui/` directory and its PR is **operator-reviewed
before merge + image rebuild** — a human gate before the container modifies the
files that build it (the same review ethos as the backbone's C52/C53 gate).
Leave `RIG1_URL` / `RIG_PUSH_TOKEN` empty for the normal self-contained demo.

> **Not yet verified in a Docker environment.** The image wiring (python3,
> `sftui` shim, the `tui/` bake) and the build-rig credential plumbing were
> authored from source and have not been exercised with `docker compose up` +
> a real subscription token. Verify on a Docker host before relying on them.
