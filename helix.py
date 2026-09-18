#!/usr/bin/env python3
"""
A horizontal, rotating double helix for your terminal — monochrome,
DNA-strand style, lying flat and spinning along its own axis.

Run:  python3 helix.py
Quit: q or Ctrl+C

The animation math lives in utilities/scripts/helix_engine.py so the same
helix can also drive the Textual splash and the web control panel.
"""

import curses
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from utilities.scripts.helix_engine import (
    DEFAULT_RUNG_CHAR,
    FRAME_DELAY,
    advance,
    render,
)


def main(stdscr):
    curses.curs_set(0)
    stdscr.nodelay(True)
    curses.start_color()
    curses.use_default_colors()

    # Black & white shading: strand in front is bold, strand behind is dim,
    # rungs sit in between. No color pairs used.
    ATTRS = {
        "front": curses.A_BOLD,
        "back": curses.A_DIM,
        "rung": curses.A_NORMAL,
    }

    # Character set / tuning live in helix_engine.py — edit the defaults there.
    rung_char = DEFAULT_RUNG_CHAR

    phase = 0.0

    while True:
        try:
            key = stdscr.getch()
            if key in (ord("q"), 27):
                break

            height, width = stdscr.getmaxyx()
            stdscr.erase()

            for cell in render(width, height, phase, rung_char=rung_char):
                try:
                    stdscr.addstr(cell.y, cell.x, cell.char, ATTRS[cell.layer])
                except curses.error:
                    pass

            stdscr.refresh()
            phase = advance(phase)
            time.sleep(FRAME_DELAY)

        except KeyboardInterrupt:
            break


if __name__ == "__main__":
    curses.wrapper(main)
