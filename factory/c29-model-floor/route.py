#!/usr/bin/env python3
"""C29 model-floor policy engine (Software Factory v4, sweep-1).

Pure stdlib. Decides which concrete model a request runs on, applying:
  (1) the FLOOR rule  -- a request's chosen/requested model is never resolved
      below the declared minimum-acceptable model for its role/task_class. A
      below-floor choice is UPGRADED to the floor (or, per the noted error
      taxonomy, refused). Upgrading is the spec's E-C29-02 behaviour (clamp + warn).
  (2) the CROSS-FAMILY rule -- reports whether the route satisfies family
      independence between coder and judge. Advisory when policy
      cross_family_required == false (Phase-0 default): emits a note, never
      refuses. Fail-closed when true (Gate-B4 lever): a same-family judge is a
      hard violation -> non-zero exit.

Usage:
    python3 route.py <request.json>

A request is JSON: {"role": str, "task_class": str, "requested_model"?: str,
                    "coder_family"?: str}
  - requested_model: an explicit model pin to validate against the floor.
  - coder_family: for a judge request, the coder's resolved family, used by
    the cross-family rule. Defaults to the floor family.

Exit codes:
    0  route resolved (possibly with an upgrade and/or advisory note)
    2  hard rule violated (below-floor + refuse policy, or cross-family
       required but judge family == coder family)
    3  bad input / unresolvable request (no rule, unknown model, bad json)
"""

import json
import os
import sys

STYLESHEET = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "model-stylesheet.json")

# When a requested model is below floor, do we upgrade (clamp to floor) or
# refuse? Spec E-C29-02 = upgrade-and-warn. We upgrade by default.
BELOW_FLOOR_ACTION = "upgrade"  # "upgrade" | "refuse"


def load_stylesheet(path=STYLESHEET):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def lookup_rule(ss, role, task_class):
    """Resolve (role, task_class) -> rule, with precedence:
    exact -> role default '*' -> global '*'/'*'. Returns (rule, matched_key)."""
    rules = ss["rules"]
    for r_key in (role, "*"):
        role_block = rules.get(r_key)
        if not isinstance(role_block, dict):
            continue
        for t_key in (task_class, "*"):
            rule = role_block.get(t_key)
            if isinstance(rule, dict) and "chosen" in rule:
                return rule, "{}/{}".format(r_key, t_key)
    return None, None


def rank_of(ss, model_id):
    entry = ss["registry"].get(model_id)
    if entry is None:
        return None
    return entry["rank"]


def family_of(ss, model_id):
    entry = ss["registry"].get(model_id)
    return None if entry is None else entry["family"]


def floor_family(ss):
    # The floor anchor's family: derive from the global default's floor model.
    glob = ss["rules"].get("*", {}).get("*")
    if glob:
        fam = family_of(ss, glob.get("floor"))
        if fam:
            return fam
    return "anthropic"


def resolve(ss, request):
    """Return (result_dict, exit_code)."""
    role = request.get("role")
    task_class = request.get("task_class")
    if not role or not task_class:
        return {"error": "request must include 'role' and 'task_class'"}, 3

    rule, matched = lookup_rule(ss, role, task_class)
    if rule is None:
        return {"error": "no-matching-rule (E-C29-01) for role={!r} task_class={!r}"
                .format(role, task_class)}, 3

    chosen = rule["chosen"]
    floor = rule["floor"]

    # Validate that chosen + floor exist in the registry (E-C29-03).
    for mid in (chosen, floor):
        if rank_of(ss, mid) is None:
            return {"error": "model-not-in-registry (E-C29-03): {!r}".format(mid)}, 3

    floor_rank = rank_of(ss, floor)

    # Starting candidate: explicit requested_model if present, else the
    # stylesheet's chosen model.
    candidate = request.get("requested_model") or chosen
    if rank_of(ss, candidate) is None:
        return {"error": "model-not-in-registry (E-C29-03): {!r}".format(candidate)}, 3

    rationale = []
    rationale.append("matched rule [{}]: chosen={}, floor={}".format(matched, chosen, floor))
    if request.get("requested_model"):
        rationale.append("requested_model={} (explicit pin)".format(candidate))

    # ---- FLOOR rule (I1 / E-C29-02) ----
    upgraded = False
    if rank_of(ss, candidate) < floor_rank:
        if BELOW_FLOOR_ACTION == "refuse":
            return {
                "error": "below-floor (E-C29-02, refuse): {} is below floor {} for {}/{}"
                         .format(candidate, floor, role, task_class),
                "requested": candidate, "floor": floor,
            }, 2
        rationale.append("BELOW FLOOR: {} (rank {}) < floor {} (rank {}) -> UPGRADED to floor"
                         .format(candidate, rank_of(ss, candidate), floor, floor_rank))
        candidate = floor
        upgraded = True
    else:
        rationale.append("floor satisfied: {} (rank {}) >= floor {} (rank {})"
                         .format(candidate, rank_of(ss, candidate), floor, floor_rank))

    resolved_model = candidate
    resolved_family = family_of(ss, resolved_model)

    # ---- CROSS-FAMILY rule (I2) ----
    policy = ss.get("policy", {})
    cross_required = bool(policy.get("cross_family_required", False))
    cross_family = {"applies": False}
    if role == "judge":
        coder_family = request.get("coder_family", floor_family(ss))
        same_family = (resolved_family == coder_family)
        cross_family = {
            "applies": True,
            "cross_family_required": cross_required,
            "independence_level": policy.get("independence_level", "L1"),
            "coder_family": coder_family,
            "judge_family": resolved_family,
            "same_family": same_family,
        }
        if cross_required:
            if same_family:
                return {
                    "error": "family-conflict-under-cross-family-enforce (E-C29-04): "
                             "judge_family={} == coder_family={}"
                             .format(resolved_family, coder_family),
                    "resolved_model": resolved_model,
                    "cross_family": cross_family,
                }, 2
            rationale.append("cross-family ENFORCED and satisfied: judge {} != coder {}"
                             .format(resolved_family, coder_family))
        else:
            if same_family:
                rationale.append("cross-family ADVISORY (cross_family_required=false): "
                                 "judge family {} == coder family {} -> isolation by "
                                 "rig/role/prompt (L1), not family diversity"
                                 .format(resolved_family, coder_family))
            else:
                rationale.append("cross-family ADVISORY: judge {} already differs from coder {}"
                                 .format(resolved_family, coder_family))

    result = {
        "role": role,
        "task_class": task_class,
        "resolved_model": resolved_model,
        "resolved_family": resolved_family,
        "cost_tier": ss["registry"][resolved_model]["cost_tier"],
        "floor": floor,
        "upgraded": upgraded,
        "cross_family": cross_family,
        "rationale": rationale,
    }
    return result, 0


def main(argv):
    if len(argv) != 2:
        sys.stderr.write("usage: python3 route.py <request.json>\n")
        return 3
    try:
        with open(argv[1], "r", encoding="utf-8") as fh:
            request = json.load(fh)
    except (OSError, ValueError) as exc:
        sys.stderr.write("bad request file: {}\n".format(exc))
        return 3

    try:
        ss = load_stylesheet()
    except (OSError, ValueError) as exc:
        sys.stderr.write("bad stylesheet: {}\n".format(exc))
        return 3

    result, code = resolve(ss, request)
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
