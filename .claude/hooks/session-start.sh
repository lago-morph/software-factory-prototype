#!/bin/bash
# SessionStart hook — ensure the Docker daemon is running.
#
# Why this exists: this repo is a Dockerized Gas City deployment; building and
# testing it needs Docker. In Claude Code on the web sandboxes, Docker IS fully
# available (the `docker` client, `dockerd`, and `docker compose`, as root) — the
# daemon is just not started at session boot. Agents have repeatedly mistaken
# "daemon not started" for "no Docker here" and shipped changes unverified. This
# hook starts the daemon automatically so that mistake can't recur.
#
# Idempotent and remote-only. NOTE: starting the daemon is only step 1 of a
# sandbox build/verify; the full recipe (CA injection for the build proxy, the
# real token, compose override) is in docs/HANDOFF.md §3.

# Deliberately no `set -e`: the poll loop below tolerates failing `docker info`
# calls while the daemon comes up.
set -uo pipefail

# Only in the remote (web) sandbox. On a laptop, Docker Desktop owns the daemon.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

# Already running? Nothing to do.
if docker info >/dev/null 2>&1; then
  echo "[session-start] docker daemon already running"
  exit 0
fi

echo "[session-start] starting docker daemon (sudo dockerd)"
sudo dockerd >/tmp/dockerd.log 2>&1 &

# Wait briefly for the socket to come up.
for _ in $(seq 1 20); do
  if docker info >/dev/null 2>&1; then
    echo "[session-start] docker daemon is up"
    exit 0
  fi
  sleep 1
done

echo "[session-start] WARNING: docker daemon did not come up in time; see /tmp/dockerd.log" >&2
# Do not fail the session start over this — surface the warning and continue.
exit 0
