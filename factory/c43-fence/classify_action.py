#!/usr/bin/env python3
"""C43 fence — deterministic blast-radius typing (boundary-typing half).

Usage:
    python3 classify_action.py <action.json>

An action describes an external/cross-partition interaction:

    {
      "actor_rig":  "r1",                 # the rig the actor is scoped to
      "target":     "r1-build-step-7",    # bead id / path / resource
      "op":         "read" | "write",
      "env":        "sandbox" | "production"
    }

The tool deterministically types the action's blast radius and emits a verdict:
  - allow  -> exit 0   (in-bounds, bounded blast radius)
  - refuse -> exit 1   (a refused blast-radius class, with reason)

It is pure-stdlib, deterministic, and side-effect-free (reads only its inputs,
writes only to stdout/stderr). NO LLM judgment participates in the path
(F51 deterministic-primary-guard invariant).

Faithful to: architectures/v4/spec/C43-isolation-boundary.md (boundary-typing
half). Policy lives in blast-radius-policy.json beside this file.
"""

import json
import os
import sys

POLICY_FILENAME = "blast-radius-policy.json"


def _die(msg, code=2):
    sys.stderr.write("classify_action: error: %s\n" % msg)
    sys.exit(code)


def load_policy():
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, POLICY_FILENAME)
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (OSError, ValueError) as e:
        _die("cannot load policy %s: %s" % (path, e))


def known_scopes(policy):
    """The set of recognised partition scopes: city scope + every rig."""
    pm = policy["partition_model"]
    scopes = {pm["city_scope"]["name"]}
    for rig in pm["rigs"]:
        scopes.add(rig["name"])
    # Also accept any scope listed in default_scopes (forward-compatible).
    scopes.update(pm.get("default_scopes", []))
    return scopes


def resolve_target_scope(target, policy):
    """Resolve a target (bead id / path / resource) to its partition scope.

    Scope is the prefix segment before the first separator, e.g.:
      "r1-build-step-7"  -> "r1"
      "gp-city-config"   -> "gp"
      "r2/worktree/x"    -> "r2"
    Returns (scope, recognised: bool).
    """
    if not isinstance(target, str) or not target:
        return None, False
    sep = policy["partition_model"].get("scope_separator", "-")
    # Split on the configured separator OR a path separator, whichever is first.
    head = target
    for cut in (sep, "/"):
        idx = head.find(cut)
        if idx != -1:
            head = head[:idx]
    scope = head
    return scope, scope in known_scopes(policy)


def classify(action, policy):
    """Return (verdict, blast_radius_class, reason).

    verdict is 'allow' or 'refuse'. Refusal rules are applied in policy order
    (production first, then cross-partition write) so the verdict is stable.
    """
    actor = action.get("actor_rig")
    target = action.get("target")
    op = action.get("op")
    env = action.get("env", policy["defaults"]["env"])

    # ---- input validation (deterministic, fail-closed) ----
    if not actor:
        return "refuse", "invalid_action", "missing required field: actor_rig"
    if not target:
        return "refuse", "invalid_action", "missing required field: target"
    if op not in ("read", "write"):
        return "refuse", "invalid_action", "op must be 'read' or 'write' (got %r)" % op
    if env not in ("sandbox", "production"):
        return "refuse", "invalid_action", "env must be 'sandbox' or 'production' (got %r)" % env
    if actor not in known_scopes(policy):
        return "refuse", "invalid_action", "actor_rig %r is not a recognised partition scope" % actor

    target_scope, recognised = resolve_target_scope(target, policy)

    # ---- refusal rules, applied in policy order ----
    # Rule 1 (D-20 default): a production-typed action is blocked.
    if env == "production":
        return (
            "refuse",
            "production_action",
            "E-C43-PROD: production-typed action blocked (D-20 default); "
            "production reach requires an explicit per-pack production-scissors "
            "declaration, not granted in the boundary-typing-half fence",
        )

    # Rule 2: a cross-partition write is refused.
    same_partition = recognised and (target_scope == actor)
    if op == "write" and not same_partition:
        if not recognised:
            detail = "target scope %r is not a recognised partition" % target_scope
        else:
            detail = "target partition %r != actor partition %r" % (target_scope, actor)
        return (
            "refuse",
            "cross_partition_write",
            "E-C43-XP-WRITE: cross-partition write refused (%s); an agent must "
            "not write outside its own rig partition (blast-radius bound, D-13)" % detail,
        )

    # ---- in-bounds (allow) ----
    if recognised and same_partition:
        scope_note = "same-partition (%s) " % target_scope
    else:
        # A read whose target scope is foreign/unrecognised is still allowed
        # in the boundary-typing half: reads do not extend blast radius, and a
        # twin/isolated read is the default-reachable posture (F56). The
        # distinct holdout read-isolation boundary is C34's, not C43's (D-13).
        scope_note = "read-only (no blast-radius extension) "
    return (
        "allow",
        "in_bounds",
        "%sin %s env — bounded blast radius" % (scope_note, env),
    )


def main(argv):
    if len(argv) != 2:
        _die("usage: python3 classify_action.py <action.json>", code=2)
    path = argv[1]
    try:
        with open(path, "r") as f:
            action = json.load(f)
    except (OSError, ValueError) as e:
        _die("cannot read action %s: %s" % (path, e))

    policy = load_policy()
    verdict, brclass, reason = classify(action, policy)

    out = {
        "verdict": verdict,
        "blast_radius_class": brclass,
        "reason": reason,
        "action": {
            "actor_rig": action.get("actor_rig"),
            "target": action.get("target"),
            "op": action.get("op"),
            "env": action.get("env", policy["defaults"]["env"]),
        },
    }
    sys.stdout.write(json.dumps(out, indent=2, sort_keys=True) + "\n")
    sys.exit(0 if verdict == "allow" else 1)


if __name__ == "__main__":
    main(sys.argv)
