# Software Factory v4 prototype image.
#
# A single image used by BOTH docker-compose services:
#   - `beadstore` : runs `dolt sql-server` (the shared local bead-store server)
#   - `city`      : runs the Gas City controller (`gc start`) + the agent fleet
#
# It bundles everything needed to run a Gas City manually on a laptop:
#   gc (built from source) + bd + dolt + node + claude-code + tmux + git.
#
# Target platform is linux/amd64 (Windows/Docker-Desktop and Linux laptops).
# Everything is fetched/built at image-build time, so a laptop only needs
# Docker — no pre-staged binaries (unlike the older gascity-prototype, which
# COPYed host-built binaries because the build ran inside a network-restricted
# sandbox).

# ---------------------------------------------------------------------------
# Stage 1 — build `gc` from source.
#
# gc pulls in Dolt's go-icu-regex, a CGO dependency that links ICU. The binary
# references ICU shared libraries by SONAME (e.g. libicui18n.so.NN), so the
# builder's ICU major version MUST match the runtime's. We therefore build on
# the SAME ubuntu:24.04 base as the runtime (ICU 74, glibc 2.39) — building on a
# different base (e.g. Debian bookworm = ICU 72) produces a gc that fails to
# load on noble with "library not found".
# ---------------------------------------------------------------------------
FROM ubuntu:24.04 AS gcbuild

ARG GO_VERSION=1.26.4
RUN apt-get update -qq \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends \
      ca-certificates curl git make gcc g++ pkg-config libicu-dev xz-utils \
 && rm -rf /var/lib/apt/lists/* \
 && curl -fsSL "https://go.dev/dl/go${GO_VERSION}.linux-amd64.tar.gz" | tar -xz -C /usr/local
ENV PATH="/usr/local/go/bin:${PATH}"

# Pin the Gas City source. Override with --build-arg GASCITY_REF=<sha|branch>.
ARG GASCITY_REPO=https://github.com/gastownhall/gascity.git
ARG GASCITY_REF=main

WORKDIR /src
RUN git clone --filter=blob:none "${GASCITY_REPO}" . \
 && git checkout "${GASCITY_REF}" \
 && git rev-parse HEAD > /GASCITY_COMMIT

# `make build` compiles ./cmd/gc -> bin/gc with the project's CGO/ICU flags.
RUN make build \
 && install -Dm0755 bin/gc /out/gc \
 && /out/gc version

# ---------------------------------------------------------------------------
# Stage 2 — runtime image.
# ---------------------------------------------------------------------------
FROM ubuntu:24.04

ARG TARGETARCH=amd64
# bd (Beads CLI) release. Proven-compatible with gc as of the gascity prototype.
ARG BD_VERSION=1.0.4
ARG BD_REPO=gastownhall/beads
# Node major version (installed via NodeSource so it stays a current 22.x LTS).
ARG NODE_MAJOR=22
# claude-code version; empty = latest.
ARG CLAUDE_CODE_VERSION=

# --- OS runtime dependencies ------------------------------------------------
# libicu74 satisfies gc's runtime ICU linkage on ubuntu 24.04 (noble).
RUN apt-get update -qq \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends \
      tmux git jq lsof procps util-linux \
      ca-certificates openssh-client curl xz-utils \
      gettext-base libicu74 \
 && rm -rf /var/lib/apt/lists/*

# --- dolt -------------------------------------------------------------------
# The bead store's database engine. Runs as a SQL server in the `beadstore`
# service and is also used by bd from the `city` service.
RUN curl -fsSL -o /tmp/dolt.tar.gz \
      "https://github.com/dolthub/dolt/releases/latest/download/dolt-linux-${TARGETARCH}.tar.gz" \
 && tar -xzf /tmp/dolt.tar.gz -C /opt \
 && ln -s "/opt/dolt-linux-${TARGETARCH}/bin/dolt" /usr/local/bin/dolt \
 && rm /tmp/dolt.tar.gz \
 && dolt config --global --add user.email softwarefactory-v4@example.com \
 && dolt config --global --add user.name "Software Factory v4 Prototype" \
 && dolt version

# --- bd (Beads CLI) ---------------------------------------------------------
RUN curl -fsSL -o /tmp/bd.tgz \
      "https://github.com/${BD_REPO}/releases/download/v${BD_VERSION}/beads_${BD_VERSION}_linux_${TARGETARCH}.tar.gz" \
 && tar -xzf /tmp/bd.tgz -C /tmp \
 && install -Dm0755 /tmp/bd /usr/local/bin/bd \
 && rm -f /tmp/bd.tgz /tmp/bd \
 && bd version

# --- node + claude-code -----------------------------------------------------
RUN curl -fsSL "https://deb.nodesource.com/setup_${NODE_MAJOR}.x" -o /tmp/nodesource.sh \
 && bash /tmp/nodesource.sh \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends nodejs \
 && rm -f /tmp/nodesource.sh /var/lib/apt/lists/* -rf \
 && npm install -g "@anthropic-ai/claude-code${CLAUDE_CODE_VERSION:+@${CLAUDE_CODE_VERSION}}" \
 && claude --version

# --- gc (from build stage) --------------------------------------------------
COPY --from=gcbuild /out/gc /usr/local/bin/gc
COPY --from=gcbuild /GASCITY_COMMIT /etc/gascity-commit
RUN chmod +x /usr/local/bin/gc && gc version

# --- claude onboarding pre-acks --------------------------------------------
# Interactive `claude` (what gc launches per agent in tmux) otherwise hangs on
# three first-run dialogs forever. Bake the GLOBAL acks here; the city
# entrypoint writes the per-path `projects` map (it knows the runtime paths):
#   1. theme picker      -> hasCompletedOnboarding / hasSeenWelcome / theme
#   2. trust-this-folder -> projects[path].hasTrustDialogAccepted
#   3. bypass-permissions-> bypassPermissionsModeAccepted
RUN mkdir -p /root/.claude \
 && cat > /root/.claude.json <<'JSON'
{
  "firstStartTime": "2026-01-01T00:00:00.000Z",
  "hasCompletedOnboarding": true,
  "hasSeenWelcome": true,
  "theme": "dark",
  "bypassPermissionsModeAccepted": true
}
JSON

ENV PATH="/usr/local/bin:/usr/bin:/bin"

# --- workspace + pack -------------------------------------------------------
# All mutable city state lives under /workspace (bind/volume-mounted).
RUN mkdir -p /workspace/city /workspace/rigs /pack

# Pack content (pack.toml + any prompt/formula overlays) baked in for the demo
# path. Bind-mount ./pack in compose to live-edit it.
COPY pack /pack
COPY city.toml.example /pack/city.toml.example

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# Keep large dolt transfers from tripping default HTTP buffers (harmless here).
RUN git config --system http.postBuffer 524288000

WORKDIR /workspace/city
# Default to the city flow; the `beadstore` service overrides the entrypoint.
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
