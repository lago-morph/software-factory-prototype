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

> **Status: chunk-1 built and verified in-sandbox.** `beadview.py` here is the
> v0.1 produced by the prototype's **own build loop** (the dogfood below) and
> verified end-to-end: the image builds, `sftui --dump` lists beads across all
> scopes in the running container, and the chunk-1 bead built the file
> autonomously (created → routed → polecat commit → refinery merge, ~15 min).
> Later rungs extend it.

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

> **Verified in-sandbox.** The image wiring (python3, `sftui` shim, the `tui/`
> bake) and the chunk-1 dogfood build were exercised end-to-end in the Claude
> Code sandbox — the image builds, `sftui --dump` works in the running container,
> and the chunk-1 bead built `beadview.py` autonomously. Docker is available in
> the sandbox: start the daemon with `sudo dockerd >/tmp/dockerd.log 2>&1 &` (a
> SessionStart hook does this automatically); the full build + live-test recipe
> (CA injection for the build proxy, the real token, compose override) is in
> [`../docs/HANDOFF.md`](../docs/HANDOFF.md) §3. (The opt-in build-rig push-back
> path above is the one part not yet exercised — chunk-1 was built into the
> default local rig.)
