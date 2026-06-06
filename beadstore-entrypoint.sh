#!/usr/bin/env bash
# Bead-store service entrypoint.
#
# Runs a single local Dolt SQL server that the whole docker-compose project can
# share over TCP. It listens on ${BEADS_HOST}:${BEADS_PORT}, reachable on the
# compose network as `beadstore:${BEADS_PORT}` from the city service (or any
# other service / `docker compose exec` client).
#
# The database files live in ${BEADS_DATA_DIR} (a named volume). Nothing is ever
# pushed to a git remote — this is a purely local, non-synced store. Throw the
# data volume away to reset; keep it to persist the city's bead history.

set -euo pipefail

log() { printf '[beadstore] %s\n' "$*"; }

BEADS_DATA_DIR="${BEADS_DATA_DIR:-/beads-data}"
BEADS_PORT="${BEADS_PORT:-3307}"
BEADS_HOST="${BEADS_HOST:-0.0.0.0}"
BEADS_USER="${BEADS_USER:-root}"

mkdir -p "${BEADS_DATA_DIR}"
cd "${BEADS_DATA_DIR}"

log "starting dolt sql-server"
log "  data-dir : ${BEADS_DATA_DIR}"
log "  listen   : ${BEADS_HOST}:${BEADS_PORT} (TCP)"
log "  user     : ${BEADS_USER} (no password)"
log "  remote   : none (this store is local-only and never synced)"

# --data-dir lets bd CREATE DATABASE per scope under one server.
# Foreground (PID 1 under compose) so the service lifecycle == the server.
exec dolt sql-server \
  --host "${BEADS_HOST}" \
  --port "${BEADS_PORT}" \
  --user "${BEADS_USER}" \
  --data-dir "${BEADS_DATA_DIR}"
