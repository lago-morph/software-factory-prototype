# Project conventions for AI agents — software-factory-prototype

Conventions for agents working in this repo, loaded via [`CLAUDE.md`](./CLAUDE.md).
Keep this short and current.

## Always test fixes — no exceptions, ever

**Every fix and every change MUST be tested by executing it against the real
running system before you claim it works, mark it "verified", or merge it. No
exceptions. Ever.** "Reasoned from the source / from the error message" is a
hypothesis, not a test. `bash -n`, `py_compile`, and linters check syntax, not
behavior — they are not tests of a fix. In this Dockerized repo, testing a fix
means building the image and running the actual `docker compose` stack (see the
sandbox recipe below), reproducing the original failure, and confirming the fix
removes it. Docker is available here, so "I couldn't test it" is almost never
true; if a runtime genuinely cannot be exercised, say so explicitly and do NOT
claim the change works.

## The sandbox HAS Docker — start the daemon, don't assume it's absent

This repo is a Dockerized Gas City deployment; building and testing it needs
Docker. In Claude Code on the web sandboxes, **Docker is fully available** — the
`docker` client, `dockerd`, and `docker compose`, running as root. The daemon is
simply **not started at session boot**. Do **not** conclude "there is no Docker
here" and ship changes as unverified. Start it:

```bash
sudo dockerd >/tmp/dockerd.log 2>&1 &   # then `docker info` to confirm (~6s)
```

A SessionStart hook ([`.claude/hooks/session-start.sh`](./.claude/hooks/session-start.sh))
does this automatically for web sessions, so a fresh session usually already has
a running daemon. If `docker info` fails, run the command above.

> This was a recurring agent mistake: reporting "no Docker / can't verify in this
> environment" when the daemon merely needed starting. The prototype has been
> built and live-tested end-to-end in the sandbox many times — see the recipe
> below.

## Full sandbox build + live-test recipe

Starting the daemon is only step 1. The sandbox's TLS-inspection proxy blocks
HTTPS **inside build containers**, so the image needs the sandbox CA injected,
and a real subscription token is available for agent execution. The complete,
verified recipe — CA-trusting verify image, compose override, token location,
tokenless-vs-token checks, and driving long live tests from a subagent to keep
context lean — lives in [`docs/HANDOFF.md`](./docs/HANDOFF.md) under
**§3 "How to build + test IN THE SANDBOX"**. Read it before a build/verify pass.

## Verify the shipped artifact, not a proxy

Because Docker is available, "I can't run it here" is rarely true. Verify
packaging changes (Dockerfile, entrypoint, compose) by building and running the
**real** image/compose stack, not a hand-rolled approximation. A change derived
from reading source is a hypothesis until it is exercised against the running
stack — label it unverified until then.

## Git discipline

Feature branch → commit → push → **ready-for-review** PR → operator merges. Don't
push to `main`. PRs default to ready-for-review, not draft.
