#!/usr/bin/env bash
# Software Factory v4 — city entrypoint (PID 1 of the `city` service).
#
# Flow:
#   1. Stamp claude per-path trust/onboarding acks (so tmux claude agents don't
#      hang on first-run dialogs).
#   2. Render city.toml from the template; place pack.toml + pack subdirs.
#   3. Write .gc/site.toml with the on-disk rig path bindings.
#   4. Provision rigs: clone if a URL is given, else git-init an empty local rig.
#   5. Wait for the shared bead-store (Dolt) server, then point the city at it.
#   6. Install pack imports (gastown + bd).
#   7. exec gc start --foreground (brings up the agent fleet).

set -euo pipefail

log() { printf '[entrypoint] %s\n' "$*"; }

WORKSPACE="${WORKSPACE:-/workspace}"
CITY_DIR="${WORKSPACE}/city"
RIGS_DIR="${WORKSPACE}/rigs"

# Bead store (the `beadstore` service). Host/port the compose group connects to.
BEADS_HOST="${BEADS_HOST:-beadstore}"
BEADS_PORT="${BEADS_PORT:-3307}"
BEADS_USER="${BEADS_USER:-root}"

# Rig sources. Empty URL => create an empty local git repo (self-contained,
# zero external dependencies). Set RIGn_URL in .env to clone a real repo.
RIG1_NAME="${RIG1_NAME:-rig1}"
RIG2_NAME="${RIG2_NAME:-rig2}"
RIG1_URL="${RIG1_URL:-}"
RIG2_URL="${RIG2_URL:-}"
RIG1_BRANCH="${RIG1_BRANCH:-main}"
RIG2_BRANCH="${RIG2_BRANCH:-main}"

mkdir -p "$CITY_DIR" "$RIGS_DIR"

# ---------- 1. claude trust + onboarding acks (per-path) ----------
log "stamping claude per-path trust acks"
cat > /root/.claude.json <<JEOF
{
  "firstStartTime": "2026-01-01T00:00:00.000Z",
  "hasCompletedOnboarding": true,
  "hasSeenWelcome": true,
  "theme": "dark",
  "bypassPermissionsModeAccepted": true,
  "projects": {
    "${CITY_DIR}": {"hasTrustDialogAccepted": true, "bypassPermissionsModeAccepted": true},
    "${RIGS_DIR}/${RIG1_NAME}": {"hasTrustDialogAccepted": true, "bypassPermissionsModeAccepted": true},
    "${RIGS_DIR}/${RIG2_NAME}": {"hasTrustDialogAccepted": true, "bypassPermissionsModeAccepted": true}
  }
}
JEOF

# ---------- 2. render city.toml + pack ----------
log "rendering city.toml from template"
envsubst < /pack/city.toml.example > "${CITY_DIR}/city.toml"
cp /pack/pack.toml "${CITY_DIR}/pack.toml"
for sub in prompts formulas agents; do
  if [ -d "/pack/${sub}" ] && [ ! -e "${CITY_DIR}/${sub}" ]; then
    ln -s "/pack/${sub}" "${CITY_DIR}/${sub}"
  fi
done

# ---------- 3. site.toml (machine-local rig path bindings) ----------
mkdir -p "${CITY_DIR}/.gc"
cat > "${CITY_DIR}/.gc/site.toml" <<EOF
workspace_name = "software-factory-v4"

[[rig]]
name = "${RIG1_NAME}"
path = "${RIGS_DIR}/${RIG1_NAME}"

[[rig]]
name = "${RIG2_NAME}"
path = "${RIGS_DIR}/${RIG2_NAME}"
EOF

# ---------- 4. provision rigs ----------
provision_rig() {
  local name=$1 url=$2 branch=$3
  local dest="${RIGS_DIR}/${name}"
  if [ -d "${dest}/.git" ]; then
    log "rig ${name}: already present"
    [ -n "$url" ] && git -C "$dest" fetch --quiet origin "$branch" 2>/dev/null || true
    return
  fi
  if [ -n "$url" ]; then
    log "rig ${name}: cloning ${url} (branch ${branch})"
    git clone --quiet --branch "$branch" "$url" "$dest"
  else
    log "rig ${name}: initializing empty local repo"
    mkdir -p "$dest"
    git -C "$dest" init --quiet -b "$branch"
    cat > "${dest}/README.md" <<RIGEOF
# ${name}

Empty local rig provisioned by the Software Factory v4 prototype. Put a project
here (or point RIG*_URL at a real repo in .env) and give the city work with:

    docker compose exec city bash -lc 'cd /workspace/rigs/${name} && gc bd create --type=task "your task"'
RIGEOF
    git -C "$dest" add -A
    git -C "$dest" -c user.email=city@example.com -c user.name="Software Factory" \
      commit --quiet -m "Initialize empty rig ${name}"
  fi
}
provision_rig "$RIG1_NAME" "$RIG1_URL" "$RIG1_BRANCH"
provision_rig "$RIG2_NAME" "$RIG2_URL" "$RIG2_BRANCH"

cd "$CITY_DIR"

# ---------- 5. point the city at the shared bead-store server ----------
log "waiting for bead-store server at ${BEADS_HOST}:${BEADS_PORT}"
for i in $(seq 1 60); do
  if (exec 3<>"/dev/tcp/${BEADS_HOST}/${BEADS_PORT}") 2>/dev/null; then
    exec 3>&- 3<&- 2>/dev/null || true
    log "bead-store server is up"
    break
  fi
  [ "$i" = 60 ] && { log "ERROR: bead-store never became reachable"; exit 1; }
  sleep 2
done

# Record the external endpoint. --adopt-unverified avoids the chicken-and-egg of
# verifying a database that gc itself will create on first init.
log "configuring external bead-store endpoint"
gc beads city use-external \
  --host "${BEADS_HOST}" --port "${BEADS_PORT}" --user "${BEADS_USER}" \
  --adopt-unverified 2>&1 | sed 's/^/[gc use-external] /' || \
  log "use-external returned non-zero (continuing; gc start will (re)initialize)"

# ---------- 6. install pack imports (gastown + bd) ----------
if [ ! -f "${CITY_DIR}/packs.lock" ]; then
  log "installing pack imports"
  gc import install 2>&1 | sed 's/^/[gc import] /' || { log "gc import install failed"; exit 1; }
fi

# ---------- 7. start the controller ----------
log "starting controller (foreground)"
exec gc start --foreground
