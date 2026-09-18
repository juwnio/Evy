"""Shared double-helix animation geometry.

Host-agnostic: ``render()`` produces a list of ``(x, y, char, layer)`` triplets
where ``layer`` is ``"front"``, ``"back"`` or ``"rung"``. Each host maps those
layers onto its own styling — curses attributes in helix.py, Rich markup in the
Textual splash, canvas colours in the web control panel.

The animation itself lives here so there is a single source of truth for the
math, character set and tuning constants.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# --- CHARACTER SET ---------------------------------------------------------
# Swap these to restyle the helix. strand_char draws the two backbones,
# rung_char draws the base-pair connectors between them.
DEFAULT_STRAND_CHAR = "✱"
DEFAULT_RUNG_CHAR = ":"
# strand_char, rung_char = "*", "."
# strand_char, rung_char = "#", "="
# strand_char, rung_char = "●", "·"
# strand_char, rung_char = "0", "~"
# ---------------------------------------------------------------------------

# --- TUNING ----------------------------------------------------------------
AMPLITUDE_SCALE = 0.35  # vertical squash, terminal cells are taller than wide
WAVELENGTH = 3.0        # smaller = more visible coils = reads as "spin"
SPEED = 0.10            # phase advance per frame
RUNG_EVERY = 2          # draw a connecting rung every N columns
HELIX_LENGTH = 44       # clamped to whatever fits the host
FRAME_DELAY = 0.04      # seconds between frames (~25fps)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HelixCell:
    x: int
    y: int
    char: str
    layer: str  # "front" | "back" | "rung"


def render(
    width: int,
    height: int,
    phase: float,
    *,
    helix_length: int = HELIX_LENGTH,
    amplitude_scale: float = AMPLITUDE_SCALE,
    wavelength: float = WAVELENGTH,
    rung_every: int = RUNG_EVERY,
    strand_char: str = DEFAULT_STRAND_CHAR,
    rung_char: str = DEFAULT_RUNG_CHAR,
) -> list[HelixCell]:
    """Render one frame of the helix centered in a ``width`` x ``height`` area.

    Returns cells in draw order (back strand first, then front strand) so a
    host painting them in sequence gets the correct overlap at crossings.
    """
    if width <= 0 or height <= 0:
        return []

    cy = height / 2.0
    radius = min(height * amplitude_scale, 4.0)

    length = min(helix_length, width - 2)
    if length <= 0:
        return []
    start_x = max(0, (width - length) // 2)

    cells: list[HelixCell] = []

    for u in range(length):
        x = start_x + u
        theta = (u / wavelength) + phase

        y1 = cy + math.sin(theta) * radius
        y2 = cy + math.sin(theta + math.pi) * radius

        depth1 = math.cos(theta)          # >0 means "toward viewer"
        depth2 = math.cos(theta + math.pi)

        # Draw the strand that's further back first so the front strand
        # visually overlaps it where they cross.
        order = sorted([(depth1, y1), (depth2, y2)], key=lambda p: p[0])
        for depth, y in order:
            yi = int(round(y))
            if 0 <= yi < height:
                layer = "front" if depth >= 0 else "back"
                cells.append(HelixCell(x, yi, strand_char, layer))

        # Base-pair rungs, only drawn when the strands are far enough apart
        # to look like a rung rather than a smear.
        if u % rung_every == 0 and abs(y1 - y2) > 1.2:
            top, bottom = sorted([y1, y2])
            for yi in range(int(round(top)) + 1, int(round(bottom))):
                if 0 <= yi < height:
                    cells.append(HelixCell(x, yi, rung_char, "rung"))

    return cells


def advance(phase: float, speed: float = SPEED) -> float:
    """Advance the rotation phase by one frame."""
    return phase + speed
