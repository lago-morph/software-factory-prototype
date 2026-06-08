# HANDOFF — Software Factory v4 prototype (autonomous dispatch + doc fixes)

**Read this first.** It is the complete pickup brief for the next session. The
dockerized Gas City prototype in this repo is **working and verified live**,
including **autonomous dispatch** — a plain `gc bd create --rig rigN …` is now
worked end-to-end with no manual nudge or sling. The two follow-ups this brief
originally scoped are **both done** (see §1 — kept for the record); §2–§5 are the
durable state, build/test plumbing, and gotchas the next session still needs.

Branch used for that work: `claude/stoic-ptolemy-Hvsiv` (PRs #9 and #10, both
merged to `main`). For new work, branch fresh off `origin/main`.
Git discipline: sign commits (`-S`, committer `noreply@anthropic.com`), feature
branch → commit → push → **ready PR** → merge (the operator merges everything;
merge after pushing). Repos in scope: `lago-morph/software-factory` (design +
specs + retrospectives), `lago-morph/software-factory-prototype` (this repo, the
implementation), `lago-morph/gascity-prototype` (reference only).

---

## 1. The two tasks — both DONE (kept for the record)

### Task #1 — fix the `gc session nudge` doc bug ✅ DONE (PR #9, merged)
`gc session nudge` requires a **message** arg: `gc session nudge <id-or-alias>
<message...>` (cobra `MinimumNArgs(2)`); the bare form errors `requires at least 2
arg(s), only received 1`. Every documented invocation in `README.md` and
`docs/GETTING-STARTED.md` now passes a quoted message. Live-confirmed:
`gc session nudge <mayor-id> "Check open beads and dispatch actionable work."`
prints `Nudged gastown.mayor`, exit 0.

### Task #2 — autonomous dispatch ✅ DONE (PR #10, merged)
Implemented as a city-level **`exec` order**,
[`pack/orders/route-rig-tasks.toml`](../pack/orders/route-rig-tasks.toml), on a
30s `cooldown`: the controller (no agent, no LLM, no token spend) slings ready,
unrouted, top-level **task** beads in each rig directly to that rig's
`gastown.polecat` on `sf-small-task`, side-stepping the mayor's triage. The filter
selects only `issue_type=task` + `status=open` with **no** `gc.routed_to` /
`gc.step_ref` / `gc.root_bead_id` and `gc.kind != "workflow"`, so it never
re-pours molecule scaffolding and is idempotent. `entrypoint.sh` now symlinks the
pack's `orders/` dir into the city scope (gc scans an `orders/` dir beside each
formula layer). Approach (b) loosening the wake budget and (c) a mayor-policy
change were considered and rejected — see [`docs/PLAN.md`](PLAN.md) "Autonomous
dispatch" decision. **Verified live** (shipped `docker compose`, real token): a
plain `gc bd create --rig rig1` auto-routed at t+69s → `in_progress` → polecat
commit → refinery merged into `rig1` main → bead `closed`, ~10 min, unattended.

The original problem statement, kept because the root-cause analysis is still the
clearest explanation of *why* the order is needed:

**Goal:** the operator runs `gc bd create --rig rigN …` and the city works it
**without a manual nudge**. Before PR #10 it did NOT, for two compounding reasons
proven live:
1. **The mayor doesn't continuously poll.** It wakes on a cadence + on nudges,
   triages, then idles. A bead created after its last wake sits `open` until the
   next wake or a nudge. (Verified: a bead created 19 min after the mayor's last
   wake was never seen until nudged.)
2. **The wake-budget throttle** (`deferred_by_wake_budget`) rate-limits session
   wakes/spawns, so even periodic wakes are infrequent and polecat spawns lag
   minutes.

Once a bead **is** routed, the rest is fully automatic and verified end-to-end:
mayor `gc sling rigN/gastown.polecat <bead>` sets `gc.routed_to` → the polecat
pool auto-scales 0→1 → a polecat claims it (`in_progress`) → commits on a
worktree branch → the **refinery** merges it into the rig and closes the bead.
(Verified: real commit `542f2ef` merged into `rig1` main; and again live with a
plain `gc bd create` + one nudge.)

**Approaches that were evaluated (chosen: a, direct sling):**
- (a) ✅ **An order that directly slings ready unrouted rig task beads** to
  `rigN/gastown.polecat` on a cadence. **Chosen** — it side-steps the mayor's
  triage entirely and costs nothing (controller-side `exec`, no agent wake). The
  shipped form slings rather than nudges (nudging would still route through the
  mayor's judgment); `exec` env gives `RIG1_NAME`/`RIG2_NAME` + the managed-Dolt
  `GC_DOLT_*` so plain `gc bd`/`gc sling` work from the script.
- (b) **Loosen the wake budget** (`[daemon].max_wakes_per_tick`, default 5):
  rejected as a primary fix — it only changes how fast sessions materialize, not
  whether the mayor routes a triaged-away bead. Left at default.
- (c) **Mayor policy/prompt change**: rejected — heavier, diverges from gastown's
  mayor design, and burns an LLM wake per cycle. Unnecessary once the order routes.
- **Watch-out that drove the design:** the mayor *triages* (it judged a test bead
  "spurious" and declined). The chosen order slings ready beads directly, so triage
  cannot defeat auto-dispatch.

**Acceptance for #2 — met.** With a real token, a plain `gc bd create --rig rig1
--type=task "…"` (NO nudge, NO sling) reached `in_progress` → polecat commit →
refinery merge → `closed` unattended. README + `docs/GETTING-STARTED` Run 1 is now
the autonomous "create a bead and the city works it" flow (nudge/sling kept as the
manual override), and `docs/PLAN.md` records the decision + verification.

---

## 2. What is true NOW (verified, on `main`)

- **Builds + runs**: `docker compose up -d --build` (laptop) brings up one `city`
  service. Image bundles `gc` (built from source) + `dolt` + `bd` + node +
  claude-code + tmux + socat. **Pinned set** (in `Dockerfile`, matches gascity
  `deps.env` at tag v1.2.1): `GASCITY_REF=v1.2.1`, `DOLT_VERSION=2.1.0`,
  `BD_VERSION=1.0.4`, `GO_VERSION=1.26.4`. Do not float to `main`/`latest`.
- **Autonomous dispatch works**: the `route-rig-tasks` exec order
  (`pack/orders/route-rig-tasks.toml`, 30s cooldown) auto-routes ready unrouted
  rig **task** beads to their polecat with no nudge/sling — so a plain
  `gc bd create --rig rigN …` is worked end-to-end (route → polecat commit →
  refinery merge → close). Controller-side script (no token spend); the entrypoint
  symlinks the pack's `orders/` dir into the city scope so gc discovers it.
  `gc session nudge`/`gc sling` remain manual overrides.
- **Bead store**: gc-managed Dolt on a hashed loopback port; the entrypoint
  socat-bridges it to `0.0.0.0:3307` (reachable as `city:3307` + host
  `127.0.0.1:3307`). **No `[dolt]` section** in city.toml (pinning the port
  breaks gc 1.1.1+ managed lifecycle). Local-only; no remote, no `dolt push`.
- **Runtime state lives in a NAMED VOLUME** (`sfv4-workspace`), NOT a host bind
  mount — Dolt is unusably slow on Docker Desktop's Windows/macOS host mount.
- **City scope is git-init'd** by the entrypoint — `bd` resolves a scope's
  context via its git root; without it the `bd_context_agreement` preflight fails
  and logs `native_store_unavailable`.
- **Do NOT set `GC_BEADS_FORCE_FALLBACK`** — it forces every read through a `bd`
  subprocess and blows gc-status's 3s snapshot budget. Native store on the fast
  volume is correct.
- **Rig roles expand** because each `[[rigs]]` in `city.toml.example` has its own
  `[rigs.imports.gastown]`. (`[defaults.rig.imports]` is only a template that
  `gc rig add` consumes; we declare rigs statically, so per-rig imports are
  required.) `gc agent list` shows `rigN/gastown.{witness,refinery,polecat}`.
- **Auth = Claude subscription** via `CLAUDE_CODE_OAUTH_TOKEN` (from `claude
  setup-token`), not an API key.
- **Worker agent is `rigN/gastown.polecat`** (not `rigN/claude`). Sling target:
  `gc sling rig1/gastown.polecat <bead> --on sf-small-task`.
- Merged PRs: prototype #1–#7 (substrate, Gate B1 components in `factory/`, docs,
  Windows/native-store/git-init/version fixes, doc-command fixes, native
  dispatch), then **#9** (nudge doc fix) and **#10** (autonomous dispatch order +
  doc rewrite). Retrospectives in `software-factory`: `2026-06-06-1`,
  `2026-06-07-7`.

---

## 3. How to build + test IN THE SANDBOX (critical plumbing)

The sandbox's TLS-inspection proxy blocks HTTPS **inside build containers** and
the in-container `claude` needs the sandbox CA. None of this is in the committed
files (they're laptop-clean); recreate it for testing only.

1. **Start docker**: `sudo dockerd >/tmp/dockerd.log 2>&1 &` (wait ~6s).
2. **Build a CA-trusting verify image** (gc-from-source build is ~13 min;
   it caches after): copy the repo to `/tmp/sfv4-verify`, drop the sandbox CA at
   `sandbox-ca.crt` (`cp /etc/ssl/certs/ca-certificates.crt`), and patch the
   Dockerfile to trust it in BOTH stages (insert after each `FROM`, before the
   first network use):
   ```
   RUN apt-get update -qq && apt-get install -y -qq --no-install-recommends ca-certificates
   COPY sandbox-ca.crt /usr/local/share/ca-certificates/sandbox-ca.crt
   RUN update-ca-certificates
   ```
   Build with `-f Dockerfile.verify -t software-factory-v4:latest`.
   - **npm uses its own CA bundle**, so the `update-ca-certificates` above does
     NOT fix the `npm install -g @anthropic-ai/claude-code` step — it fails
     `SELF_SIGNED_CERT_IN_CHAIN`. Also add
     `ENV NODE_EXTRA_CA_CERTS=/etc/ssl/certs/ca-certificates.crt` in the runtime
     stage before that npm step in `Dockerfile.verify`.
   - **Docker Hub may 429** on `FROM ubuntu:24.04` (rate limit). Pull the same
     image from a mirror (e.g. the AWS ECR public ubuntu mirror) and retag it
     locally as `ubuntu:24.04` before building.
3. **Sandbox compose override** (so agents reach api.anthropic.com): write
   `docker-compose.sandbox.yml` adding to the `city` service:
   `environment: NODE_EXTRA_CA_CERTS=/etc/ssl/certs/ca-certificates.crt`,
   `ANTHROPIC_BASE_URL=${ANTHROPIC_BASE_URL:-https://api.anthropic.com}`, and
   `volumes: /etc/ssl/certs/ca-certificates.crt:/etc/ssl/certs/ca-certificates.crt:ro`.
   Run `docker compose -f docker-compose.yml -f docker-compose.sandbox.yml up -d --no-build`.
   These two files (`Dockerfile.verify`, `docker-compose.sandbox.yml`,
   `sandbox-ca.crt`, `.env`) are sandbox-only — do NOT commit them.
4. **Real token** (for agent execution): at `/home/claude/.claude/remote/.oauth_token`.
   Build `.env` by reading the file directly; **NEVER print/echo the token**;
   verify with `grep -c '^CLAUDE_CODE_OAUTH_TOKEN=' .env`. Scrub `.env` back to a
   placeholder when done.
5. **Tokenless vs token**: config/agent-roster checks (`gc agent list`,
   `gc status`, rig-role expansion) need NO token — agents fail auth harmlessly.
   Agent *execution* (dispatch → commit) needs the real token.
6. **Long-running live tests**: drive them from a subagent so the orchestrator
   context stays lean; have the subagent tear the stack down (`docker compose
   down`, keep the volume) to end token spend, and return a concise timeline.
7. Useful diagnostics: `gc status`; `gc session list` (STATE / LAST ACTIVE /
   LAST NUDGE — compare mayor LAST ACTIVE to the bead's created time to know if a
   nudge is needed); `gc bd list --rig rig1`; `gc bd show <id> --json | jq
   '.[0] | {status, routed_to: .metadata."gc.routed_to", assignee}'`;
   `gc session peek <id>`; `gc order list` / `gc order check`.

---

## 4. Process discipline the operator insisted on (do not regress)
- **Execute documentation against the running system** before publishing — do not
  ship commands you only reasoned about (5 doc bugs were caught only by running).
- **Verify the SHIPPED config, not a proxy** — run the actual `docker-compose`
  with its actual volume/network config, not a hand-rolled `docker run`.
- **Reasoned-from-source ≠ verified** — run it before claiming it works.
- **Don't over-spawn background tasks**; they pile up in the operator's panel.
  Prefer one subagent doing a bounded job; stop stale tasks (`TaskStop`).
- Keep replies grounded in real output; surface the load-bearing finding up top.

---

## 5. Key files
- `Dockerfile` — multi-stage; pinned versions; ICU/CGO build of gc on ubuntu:24.04.
- `docker-compose.yml` — single `city` service; named volume `sfv4-workspace`;
  publishes `127.0.0.1:3307`.
- `entrypoint.sh` — renders city.toml, git-inits city, provisions local rigs,
  symlinks pack `prompts/formulas/agents/orders` into the city scope,
  socat-bridges the bead store, `gc start --foreground`.
- `city.toml.example` — `[beads] provider="bd"`, `[providers.claude]`, per-rig
  `[rigs.imports.gastown]`, no `[dolt]`.
- `pack/pack.toml` — imports gastown (city agents); `pack/formulas/sf-small-task.toml`
  — the 4-node example formula; `pack/orders/route-rig-tasks.toml` — the
  autonomous-dispatch exec order (30s cooldown).
- `factory/` — Gate B1 backbone components (C20, C08/C09, C43, C29) + tests
  (`make -C factory test`).
- `docs/PLAN.md`, `docs/GETTING-STARTED.md`, `README.md` — keep accurate to
  observed behavior.
- Upstream gc source for reference: clone `github.com/gastownhall/gascity` at tag
  `v1.2.1` (or read `examples/gastown/` for the canonical config + orders).
