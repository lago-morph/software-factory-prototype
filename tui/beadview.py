#!/usr/bin/env python3
"""Gascity progress tracker — v0.1 placeholder.

This file is the slot for the progress-tracker TUI (an operator instrument that
ships baked into the city image and runs via the `sftui` shim). The first real
version is built by the prototype itself via the chunk-1 dogfood bead:

    chunk 1 — browse beads across all scopes (city + each rig); arrow keys to
              navigate; Enter for a bead's details; Esc back to the list; q quit;
              keyboard help always shown; read-only; --dump for a non-interactive
              self-check.

Once the chunk-1 build lands, its output replaces this placeholder in tui/ and
the image rebuild bakes the real viewer in. Until then this placeholder just
explains itself so `sftui` runs cleanly. Stdlib only (no pip, no network).

See tui/README.md for the chunk ladder and build approach, and the durable plan
at lago-morph/software-factory: architectures/v4/tui-operator-instrument-plan.md
"""
import sys

MESSAGE = (
    "Gascity progress tracker - v0.1 placeholder.\n"
    "The real chunk-1 viewer (browse beads; arrow keys; Enter=details; Esc=back;\n"
    "q=quit) is built by the prototype via the chunk-1 dogfood bead.\n"
    "See tui/README.md.\n"
)


def main(argv):
    # --dump is the non-interactive self-check that the chunk-1 build must keep:
    # it prints the collected bead list (here, just this message) and exits 0,
    # so the build can verify it reaches gc without needing a TTY.
    sys.stdout.write(MESSAGE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
