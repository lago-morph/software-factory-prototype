# CLAUDE.md

Per-repo conventions loader. The actual conventions live in [`AGENTS.md`](./AGENTS.md)
so other coding agents (Codex, etc.) that follow the AGENTS.md convention see
them too.

**Session-startup convention.** Read [`AGENTS.md`](./AGENTS.md) first. The single
most load-bearing fact for this Dockerized repo: **the sandbox HAS Docker** — the
daemon is just not started at boot. Start it with
`sudo dockerd >/tmp/dockerd.log 2>&1 &` (a SessionStart hook does this
automatically for web sessions) rather than assuming Docker is unavailable. The
full sandbox build/verify recipe is in [`docs/HANDOFF.md`](./docs/HANDOFF.md) §3.
