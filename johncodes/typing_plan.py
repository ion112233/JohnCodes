"""Keystroke schedule for the typing animation.

The code types at a **fixed, natural speed** (``cps`` chars/second, plus a short
pause at each line break). It is NOT stretched to match the narration — typing
usually finishes before the voice does and the finished code just sits there.
Stretching it to fill the narration is what made early cuts look robotic.

``times`` is a monotonically increasing list, one entry per source character;
the renderer maps a frame time to "characters revealed" with a binary search,
and the audio mixer drops a keystroke click at (most of) these timestamps.
"""
from __future__ import annotations

import bisect
import hashlib
from dataclasses import dataclass


@dataclass
class TypingPlan:
    times: list[float]          # len == len(code)
    duration: float             # when the last character lands
    click_times: list[float]    # subset: audible keystrokes

    def revealed_at(self, t: float) -> int:
        return bisect.bisect_right(self.times, t)


def _rng_stream(seed: str):
    h = hashlib.sha256(seed.encode()).digest()
    i = 0
    while True:
        if i >= len(h):
            h = hashlib.sha256(h).digest()
            i = 0
        yield h[i] / 255.0
        i += 1


def build_plan(code: str, *, cps: float = 22.0, newline_pause: float = 0.22,
               seed: str = "johncodes", max_duration: float | None = None) -> TypingPlan:
    """Schedule at ~``cps`` characters per second with human jitter.

    ``max_duration`` is only a safety clamp for pathologically long snippets; in
    normal use the natural pace wins and the typing ends early.
    """
    rng = _rng_stream(seed + code[:64])
    base = 1.0 / max(cps, 1.0)
    times: list[float] = []
    acc = 0.0
    at_line_start = True
    for ch in code:
        if ch == "\n":
            step = newline_pause + base
            at_line_start = True
        elif ch == " " and at_line_start:
            step = base * 0.25                 # indentation flies in
        elif ch in " ":
            step = base * 0.9
            at_line_start = False
        elif ch in ".,:()[]{}\"'":
            step = base * 1.15
            at_line_start = False
        else:
            step = base
            at_line_start = False
        step *= 0.7 + 0.6 * next(rng)          # jitter
        acc += step
        times.append(acc)

    if max_duration and acc > max_duration and acc > 0:
        scale = max_duration / acc
        times = [t * scale for t in times]
        acc = max_duration

    click_times = [t for ch, t in zip(code, times) if ch not in " \n"]
    return TypingPlan(times=times, duration=acc, click_times=click_times)
