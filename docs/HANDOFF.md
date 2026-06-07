# HANDOFF — Software Factory v4 prototype (autonomous dispatch + doc fixes)

**Read this first.** It is the complete pickup brief for the next session. The
dockerized Gas City prototype in this repo is **working and verified live**; two
follow-ups remain. Everything below is hard-won (often by booting the real
container with a real token) — trust it and don't re-derive it.

Branch for all work (all three repos): `claude/software-factory-v4-setup-vTSqG`.
Git discipline: sign commits (`-S`, committer `noreply@anthropic.com`), feature
branch → commit → push → **ready PR** → merge (the operator merges everything;
merge after pushing). Repos in scope: `lago-morph/software-factory` (design +
specs + retrospectives), `lago-morph/software-factory-prototype` (this repo, the
implementation), `lago-morph/gascity-prototype` (reference only).

---

## 1. The two tasks for the next session

### Task #1 — fix the `gc session nudge` doc bug (small, verified)
`gc session nudge` requires a **message** arg: `gc session nudge <id-or-alias>
<message...>`. The docs show it without the message (`gc session nudge
<mayor-id>`), which errors `requires at least 2 arg(s), only received 1`.
- Files: `README.md`, `docs/GETTING-STARTED.md` (grep `gc session nudge`).
- Fix to: `gc session nudge <mayor-id> "Check open beads and dispatch actionable work."`
- Acceptance: every documented `gc session nudge` includes a quoted message.

### Task #2 — autonomous dispatch (the real feature) + update docs accordingly
**Goal:** the operator runs `gc bd create --rig rigN …` and the city works it
**without a manual nudge**. Today it does NOT, for two compounding reasons proven
live:
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

**Approaches to evaluate (pick what works, verify live):**
- (a) **An order that nudges the mayor when rig beads are open.** gastown ships
  orders (see `examples/gastown/packs/gastown/orders/` in the gc source). A small
  scheduled/event order that runs `gc session nudge <mayor> "route open work"` (or
  directly `gc sling`s ready unrouted rig task beads to `rigN/gastown.polecat`)
  on a cadence would give hands-off dispatch. This is likely the cleanest.
- (b) **Loosen the wake budget** in `[daemon]` (city.toml) so the mayor wakes
  often enough to pick up beads promptly. Find the wake-budget knob in the gc
  source (`grep -rn wake_budget`/`WakeBudget` in `cmd/gc`). Combine with (a).
- (c) **Mayor policy/prompt change** so it auto-slings open task beads instead of
  triaging-and-waiting — heavier, and diverges from gastown's mayor design; only
  if (a)+(b) are insufficient.
- **Watch out:** the mayor *triages* (it judged a test bead "spurious" and
  declined). Auto-dispatch must not be defeated by triage — an order that slings
  ready beads directly side-steps the mayor's judgment.

**Acceptance for #2:** with a real token, `gc bd create --rig rig1 --type=task
"…"` (NO nudge, NO manual sling) results, within a few minutes, in the bead going
`in_progress` → a polecat committing → the refinery merging → bead `closed`.
**Then update README + docs/GETTING-STARTED** so the tutorial's Run 1 is "create
a bead and the city works it" (autonomous), with nudge/sling kept as the manual
override. Update `docs/PLAN.md` verification status too.

---

## 2. What is true NOW (verified, on `main`)

- **Builds + runs**: `docker compose up -d --build` (laptop) brings up one `city`
  service. Image bundles `gc` (built from source) + `dolt` + `bd` + node +
  claude-code + tmux + socat. **Pinned set** (in `Dockerfile`, matches gascity
  `deps.env` at tag v1.2.1): `GASCITY_REF=v1.2.1`, `DOLT_VERSION=2.1.0`,
  `BD_VERSION=1.0.4`, `GO_VERSION=1.26.4`. Do not float to `main`/`latest`.
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
  dispatch). Retrospectives in `software-factory`: `2026-06-06-1`, `2026-06-07-7`.

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
  socat-bridges the bead store, `gc start --foreground`.
- `city.toml.example` — `[beads] provider="bd"`, `[providers.claude]`, per-rig
  `[rigs.imports.gastown]`, no `[dolt]`.
- `pack/pack.toml` — imports gastown (city agents); `pack/formulas/sf-small-task.toml`
  — the 4-node example formula.
- `factory/` — Gate B1 backbone components (C20, C08/C09, C43, C29) + tests
  (`make -C factory test`).
- `docs/PLAN.md`, `docs/GETTING-STARTED.md`, `README.md` — keep accurate to
  observed behavior.
- Upstream gc source for reference: clone `github.com/gastownhall/gascity` at tag
  `v1.2.1` (or read `examples/gastown/` for the canonical config + orders).
