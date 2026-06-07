#!/usr/bin/env python3
"""tui/beadview.py — read-only bead viewer TUI, v0.1 (stdlib only)"""

import argparse
import curses
import json
import subprocess
import sys

STATUS_SYM = {
    'open': '○',
    'in_progress': '◐',
    'blocked': '●',
    'closed': '✓',
    'deferred': '❄',
}

LIST_KEYS  = "↑/↓:move  Enter:detail  q:quit"
DETAIL_KEYS = "↑/↓:scroll  Esc:back  q:quit"


def _run(cmd):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        return r.stdout
    except Exception:
        return ''


def collect_beads():
    scopes = [
        ('city',  []),
        ('rig1',  ['--rig', 'rig1']),
        ('rig2',  ['--rig', 'rig2']),
    ]
    beads = []
    for name, extra in scopes:
        out = _run(['gc', 'bd', 'list', '--json'] + extra)
        try:
            items = json.loads(out) if out.strip() else []
        except json.JSONDecodeError:
            items = []
        for b in items:
            b['_scope'] = name
        beads.extend(items)
    return beads


def get_detail(bead):
    cmd = ['gc', 'bd', 'show', bead['id']]
    scope = bead.get('_scope', 'city')
    if scope in ('rig1', 'rig2'):
        cmd += ['--rig', scope]
    return _run(cmd) or '(no output)'


def _fmt_line(bead, width):
    sym   = STATUS_SYM.get(bead.get('status', ''), '?')
    scope = bead.get('_scope', '?')
    bid   = bead.get('id', '?')
    btype = bead.get('issue_type', '?')
    title = bead.get('title', '')
    prefix = f" {sym} [{scope:4}] {bid:<12} {btype:<10}  "
    avail = width - len(prefix)
    if avail > 0 and len(title) > avail:
        title = title[:avail - 1] + '…'
    return prefix + title


def dump_mode(beads):
    for b in beads:
        sym   = STATUS_SYM.get(b.get('status', ''), '?')
        scope = b.get('_scope', '?')
        bid   = b.get('id', '?')
        btype = b.get('issue_type', '?')
        status = b.get('status', '?')
        title  = b.get('title', '')
        print(f"{sym} [{scope}] {bid} {btype} {status} {title}")


# ── TUI ──────────────────────────────────────────────────────────────────────

def _tui(stdscr, beads):
    curses.curs_set(0)
    try:
        curses.use_default_colors()
        bg = -1
    except Exception:
        bg = curses.COLOR_BLACK

    curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_WHITE)   # selected row
    curses.init_pair(2, curses.COLOR_CYAN,  bg)                   # header
    curses.init_pair(3, curses.COLOR_YELLOW, bg)                  # footer

    sel          = 0
    list_scroll  = 0
    detail_text  = ''
    detail_scroll = 0
    view         = 'list'

    while True:
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        body_h   = h - 2   # row 0 = header, row h-1 = footer
        footer_y = h - 1

        if view == 'list':
            # ── header ──
            hdr = f" Bead Viewer v0.1  [{len(beads)} beads]"
            try:
                stdscr.addstr(0, 0, hdr.ljust(w)[:w],
                              curses.color_pair(2) | curses.A_BOLD)
            except curses.error:
                pass

            n = len(beads)
            if n == 0:
                try:
                    stdscr.addstr(1, 0, ' (no beads)')
                except curses.error:
                    pass
            else:
                sel = max(0, min(sel, n - 1))
                if sel < list_scroll:
                    list_scroll = sel
                if sel >= list_scroll + body_h:
                    list_scroll = sel - body_h + 1

                for i in range(body_h):
                    idx = list_scroll + i
                    if idx >= n:
                        break
                    line = _fmt_line(beads[idx], w)
                    y = i + 1
                    attr = curses.color_pair(1) if idx == sel else 0
                    try:
                        stdscr.addstr(y, 0, line.ljust(w)[:w], attr)
                    except curses.error:
                        pass

            # ── footer ──
            try:
                stdscr.addstr(footer_y, 0,
                              f" {LIST_KEYS}".ljust(w)[:w],
                              curses.color_pair(3))
            except curses.error:
                pass

            stdscr.refresh()
            key = stdscr.getch()

            if key in (ord('q'), ord('Q')):
                break
            elif key in (curses.KEY_UP, ord('k')):
                if sel > 0:
                    sel -= 1
            elif key in (curses.KEY_DOWN, ord('j')):
                if sel < len(beads) - 1:
                    sel += 1
            elif key in (curses.KEY_ENTER, 10, 13):
                if beads:
                    detail_text   = get_detail(beads[sel])
                    detail_scroll = 0
                    view = 'detail'

        else:  # detail view
            bead  = beads[sel]
            title = f" [{bead.get('id','?')}] {bead.get('title','')}"
            try:
                stdscr.addstr(0, 0, title.ljust(w)[:w],
                              curses.color_pair(2) | curses.A_BOLD)
            except curses.error:
                pass

            lines     = detail_text.splitlines()
            max_scroll = max(0, len(lines) - body_h)
            detail_scroll = max(0, min(detail_scroll, max_scroll))

            for i in range(body_h):
                idx = detail_scroll + i
                if idx >= len(lines):
                    break
                try:
                    stdscr.addstr(i + 1, 0, lines[idx][:w])
                except curses.error:
                    pass

            try:
                stdscr.addstr(footer_y, 0,
                              f" {DETAIL_KEYS}".ljust(w)[:w],
                              curses.color_pair(3))
            except curses.error:
                pass

            stdscr.refresh()
            key = stdscr.getch()

            if key in (ord('q'), ord('Q')):
                break
            elif key == 27:  # Esc
                view = 'list'
            elif key in (curses.KEY_UP, ord('k')):
                if detail_scroll > 0:
                    detail_scroll -= 1
            elif key in (curses.KEY_DOWN, ord('j')):
                if detail_scroll < max_scroll:
                    detail_scroll += 1


def main():
    ap = argparse.ArgumentParser(description='Read-only bead viewer TUI v0.1')
    ap.add_argument('--dump', action='store_true',
                    help='Print bead list as plain text and exit 0')
    args = ap.parse_args()

    beads = collect_beads()

    if args.dump:
        dump_mode(beads)
        sys.exit(0)

    if not beads:
        print('No beads found.', file=sys.stderr)
        sys.exit(1)

    curses.wrapper(_tui, beads)


if __name__ == '__main__':
    main()
