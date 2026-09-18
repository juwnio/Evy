#!/usr/bin/env python3
"""
A horizontal, rotating double helix for your terminal — monochrome,
DNA-strand style, lying flat and spinning along its own axis.

Run:  python3 helix.py
Quit: q or Ctrl+C
"""

import curses
import math
import time


def main(stdscr):
    curses.curs_set(0)
    stdscr.nodelay(True)
    curses.start_color()
    curses.use_default_colors()

    # Black & white shading: strand in front is bold, strand behind is dim,
    # rungs sit in between. No color pairs used.
    FRONT = curses.A_BOLD
    BACK = curses.A_DIM
    RUNG = curses.A_NORMAL

    # --- CHARACTER SET -----------------------------------------------------
    # Swap these to restyle the helix. strand_char draws the two backbones,
    # rung_char draws the base-pair connectors between them.
    strand_char = "✱"                 # default backbone character
    rung_char = "|"                   # default rung character
    # strand_char, rung_char = "*", "."
    # strand_char, rung_char = "#", "="
    # strand_char, rung_char = "●", "·"
    # strand_char, rung_char = "0", "~"
    # -------------------------------------------------------------------

    amplitude_scale = 0.35   # vertical squash, since terminal chars are tall
    wavelength = 3.0         # smaller = more visible coils = reads as "spin"
    speed = 0.10             # rotation speed per frame
    rung_every = 2           # draw a connecting rung every N columns

    # --- SIZE / POSITION -----------------------------------------------
    # A helix spanning the full terminal mostly reads as a wave scrolling
    # past, not something spinning in place. Keeping it a fixed, centered
    # length — with several full coils packed into that length — is what
    # actually sells the "rotating in place" look. Tweak helix_length to
    # taste (it's clamped to whatever fits the terminal).
    helix_length = 44
    # ---------------------------------------------------------------------

    phase = 0.0

    while True:
        try:
            key = stdscr.getch()
            if key in (ord("q"), 27):
                break

            height, width = stdscr.getmaxyx()
            cy = height / 2.0
            radius = min(height * amplitude_scale, 4.0)

            length = min(helix_length, width - 2)
            start_x = max(0, (width - length) // 2)

            stdscr.erase()

            for u in range(length):
                x = start_x + u
                theta = (u / wavelength) + phase

                y1 = cy + math.sin(theta) * radius
                y2 = cy + math.sin(theta + math.pi) * radius

                depth1 = math.cos(theta)          # >0 means "toward viewer"
                depth2 = math.cos(theta + math.pi)

                # Draw the strand that's further back first, so the front
                # strand visually overlaps it where they cross.
                order = sorted([(depth1, y1), (depth2, y2)], key=lambda p: p[0])

                for depth, y in order:
                    yi = int(round(y))
                    if 0 <= yi < height:
                        attr = FRONT if depth >= 0 else BACK
                        try:
                            stdscr.addstr(yi, x, strand_char, attr)
                        except curses.error:
                            pass

                # Base-pair rungs, only drawn when the strands are far enough
                # apart to look like a rung rather than a smear.
                if u % rung_every == 0 and abs(y1 - y2) > 1.2:
                    top, bottom = sorted([y1, y2])
                    for yi in range(int(round(top)) + 1, int(round(bottom))):
                        if 0 <= yi < height:
                            try:
                                stdscr.addstr(yi, x, rung_char, RUNG)
                            except curses.error:
                                pass

            stdscr.refresh()
            phase += speed
            time.sleep(0.04)

        except KeyboardInterrupt:
            break


if __name__ == "__main__":
    curses.wrapper(main)