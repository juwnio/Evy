import contextlib
import itertools
import sys
import time

import animation
import cursor

# Monkey-patch _animate to use self.speed instead of hardcoded 0.3
_orig_animate = animation.Wait._animate


def _patched_animate(self):
    self._done = False
    cursor.hide()
    for c in itertools.cycle(self._animation):
        if self._done:
            break
        print(self.color(c), end="", flush=True)
        for _ in range(len(c)):
            sys.stdout.write("\b")
        time.sleep(self.speed)
    return


animation.Wait._animate = _patched_animate

thinking = [
    "⠋⠸⠦ Ruminating",
    "⠙⠼⠧ Ruminating",
    "⠹⠴⠇ Ruminating",
    "⠸⠦⠏ Ruminating",
    "⠼⠧⠋ Ruminating",
    "⠴⠇⠙ Ruminating",
    "⠦⠏⠹ Ruminating",
    "⠧⠋⠸ Ruminating",
    "⠇⠙⠼ Ruminating",
    "⠏⠹⠴ Ruminating",
]
thinking_animation = animation.Wait(thinking, color="blue", speed=0.1)

memorising = [
    "⠁ Memorising",
    "⠉ Memorising",
    "⠙ Memorising",
    "⠚ Memorising",
    "⠒ Memorising",
    "⠂ Memorising",
    "⠂ Memorising",
    "⠒ Memorising",
    "⠲ Memorising",
    "⠴ Memorising",
    "⠤ Memorising",
    "⠄ Memorising",
    "⠄ Memorising",
    "⠤ Memorising",
    "⠴ Memorising",
    "⠲ Memorising",
    "⠒ Memorising",
    "⠂ Memorising",
    "⠂ Memorising",
    "⠒ Memorising",
    "⠚ Memorising",
    "⠙ Memorising",
    "⠉ Memorising",
    "⠁ Memorising",
]
memorising_animation = animation.Wait(memorising, color="blue", speed=0.1)

acting = [
    "⠋ Working",
    "⠙ Working",
    "⠹ Working",
    "⠸ Working",
    "⠼ Working",
    "⠴ Working",
    "⠦ Working",
    "⠧ Working",
    "⠇ Working",
    "⠏ Working",
]
acting_animation = animation.Wait(acting, color="blue", speed=0.1)


@contextlib.contextmanager
def show_state(frames, color="blue", speed=0.1):
    """Synchronous spinner for brief operations. Yields, then clears."""
    anim = animation.Wait(frames, color=color, speed=speed)
    anim.start()
    try:
        yield
    finally:
        time.sleep(speed)
        anim.stop()
