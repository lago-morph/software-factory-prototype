#!/usr/bin/env bash
# Software Factory v4 — city entrypoint (PID 1 of the `city` service).
#
# Flow:
#   1. Stamp claude per-path trust/onboarding acks (so tmux claude agents don't
#      hang on first-run dialogs).
#   2. Render city.toml from the template; place pack.toml + pack subdirs.
#   3. Write .gc/site.toml with the on-disk rig path bindings.
#   4. Provision rigs: clone if a URL is given, else git-init an empty local rig.
#   5. Install pack imports (gastown + bd).
#   6. exec gc start --foreground (brings up the gc-managed Dolt bead-store
#      server AND the agent fleet).

set -euo pipefail

log() { printf '[entrypoint] %s\n' "$*"; }

WORKSPACE="${WORKSPACE:-/workspace}"
CITY_DIR="${WORKSPACE}/city"
RIGS_DIR="${WORKSPACE}/rigs"

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

# ---------- 3b. make the city scope a git repo ----------
# bd resolves a scope's context via its git repository root. The city dir lives
# in a volume and is not otherwise a git repo, so `bd context` fails there with
# "not a git repository" — which makes gc's bd_context_agreement preflight fail
# and log `native_store_unavailable ... scope=/workspace/city` (the bead store is
# fine; only scope resolution trips). git-init the city dir so bd can resolve it.
# .beads/ and .gc/ (the live store + runtime) are ignored, not committed.
if [ ! -d "${CITY_DIR}/.git" ]; then
  log "initializing city scope as a git repo (for bd context resolution)"
  git -C "$CITY_DIR" init -q
  printf '.beads/\n.gc/\n' > "${CITY_DIR}/.gitignore"
  git -C "$CITY_DIR" -c user.email=city@local -c user.name="Software Factory" add -A 2>/dev/null || true
  git -C "$CITY_DIR" -c user.email=city@local -c user.name="Software Factory" \
    commit -q -m "Initialize city scope" 2>/dev/null || true
fi

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

# ---------- 5. install pack imports (gastown + bd) ----------
if [ ! -f "${CITY_DIR}/packs.lock" ]; then
  log "installing pack imports"
  gc import install 2>&1 | sed 's/^/[gc import] /' || { log "gc import install failed"; exit 1; }
fi

# ---------- 6. publish the bead store on a stable host/port ----------
# gc manages the Dolt SQL server on a deterministic, loopback-only port. Bridge
# it to 0.0.0.0:${BEADS_PUBLISH_PORT} so the whole compose project (and the
# published host port) can reach the bead store by host/port. Runs in the
# background; it waits for gc to bring the server up, then starts socat. After
# `exec gc start` replaces this shell, tini (init: true) reaps the bridge.
BEADS_PUBLISH_PORT="${BEADS_PUBLISH_PORT:-3307}"
DOLT_STATE="${CITY_DIR}/.gc/runtime/packs/dolt/dolt-state.json"
(
  for _ in $(seq 1 120); do
    if [ -f "$DOLT_STATE" ]; then
      port="$(jq -r '.port // empty' "$DOLT_STATE" 2>/dev/null || true)"
      running="$(jq -r '.running // false' "$DOLT_STATE" 2>/dev/null || true)"
      if [ -n "$port" ] && [ "$running" = "true" ]; then
        log "bridging bead store 0.0.0.0:${BEADS_PUBLISH_PORT} -> 127.0.0.1:${port}"
        exec socat "TCP-LISTEN:${BEADS_PUBLISH_PORT},bind=0.0.0.0,fork,reuseaddr" \
                   "TCP:127.0.0.1:${port}"
      fi
    fi
    sleep 2
  done
  log "WARNING: managed Dolt port never appeared; bead store not published"
) &

# ---------- 7. start the controller ----------
# gc start brings up the gc-managed Dolt SQL server, initializes the city/rig
# bead scopes against it, and reconciles the agent fleet.
log "starting controller (foreground)"
exec gc start --foreground
