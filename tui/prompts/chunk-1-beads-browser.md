# Chunk-1 build prompt — beads browser

This is the exact prompt that built the first version of the progress-tracker TUI
(`tui/beadview.py`). It is fed to the factory as a task bead; the prototype's
fleet builds it (polecat → refinery → merge). The agent authors these prompts;
each rung of the [chunk ladder](../README.md) is one such prompt.

> **Why this file exists.** The bead created from this prompt lives only in the
> prototype's local Dolt store (ephemeral, never synced). This file is the
> durable source of truth for the prompt so it can be re-run, reviewed, or
> adapted for later rungs.

## How it was run

From the city dir, with `python3` available in the image (it is):

```bash
docker compose exec city bash -lc \
  'cd /workspace/city && gc bd create --rig rig1 --type=task "<the prompt body below>"'
```

It ran end-to-end autonomously (created → auto-routed → polecat commit → refinery
merge, ~15 min) and produced a working `beadview.py`.

## Prompt body (verbatim)

```text
Build a tiny read-only terminal viewer for beads, version 0.1, deliberately minimal. This is a toy to shake down the prototype, so keep it small.

Deliverable: a single Python 3 file at tui/beadview.py in this rig, using ONLY the Python standard library (the curses and subprocess modules). Do NOT pip install anything and do NOT use the network. First run python3 --version to confirm Python 3 is available here; if it is not, stop and report that instead of installing anything.

What it does:
1. At startup, collect beads from three scopes by shelling out to the gc CLI: the city scope (gc bd list) and each rig (gc bd list --rig rig1 and gc bd list --rig rig2). Before writing the parser, actually run these commands and read their real output so you parse the real format; if gc offers a JSON or machine-readable flag, prefer it.
2. Show one combined scrollable list. Each row shows: scope (city / rig1 / rig2), bead id, type, status, and a short title or summary.
3. Up and Down arrow keys move a highlighted selection through the list.
4. Enter opens a detail view of the selected bead by running gc bd show <id> (with the matching --rig for rig beads) and shows its full output, scrollable with the arrow keys.
5. Escape returns from the detail view to the list.
6. The letter q quits.
7. A footer line is ALWAYS visible showing the key bindings, for example: up/down navigate, Enter details, Esc back, q quit.

Constraints and acceptance:
- One file, stdlib only, no pip, no network, runs inside this container where gc is on PATH.
- Also support a non-interactive self-check: python3 tui/beadview.py --dump prints the collected bead list to stdout as plain text (no curses) and exits 0. Use this to verify it can reach gc and parse beads without needing a terminal.
- Keep it readable and small. This is v0.1. Do NOT add polling, refresh, sessions, diffs, or formulas, those are later steps. Just load once, navigate, details, back, quit.
- Commit tui/beadview.py with a one-line note in the commit message on how to run it.
```

## Later rungs (not yet built)

| Rung | Capability |
|---|---|
| 2 | Browse sessions; Enter shows a `tail -30` peek (`gc session list` / `gc session peek <id>`) |
| 3+ | Commit diffs; configurable polling + force-refresh; interrupt-driven if feasible; formula browsing |

Each new rung is a card on Board 1 (Card 8 lineage) and starts with a scope/UI
discussion before its prompt is authored here.
