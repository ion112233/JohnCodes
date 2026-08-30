"""Keystroke schedule for the typing animation.

Produces a monotonically increasing list of timestamps (seconds, relative to the
start of typing) — one per character of the source. The renderer maps a frame
time to "characters revealed" with a binary search; the audio mixer drops a
keystroke click at (most of) these timestamps.
"""
from __future__ import annotations

import bisect
import hashlib
from dataclasses import dataclass


@dataclass
class TypingPlan:
    times: list[float]          # len == len(code)
    duration: float
    click_times: list[float]    # subset: audible keystrokes

    def revealed_at(self, t: float) -> int:
        return bisect.bisect_right(self.times, t)


def _rng_stream(seed: str):
    """Deterministic pseudo-random floats in [0, 1) from a seed string."""
    h = hashlib.sha256(seed.encode()).digest()
    i = 0
    while True:
        if i >= len(h):
            h = hashlib.sha256(h).digest()
            i = 0
        yield h[i] / 255.0
        i += 1


def build_plan(code: str, duration: float, *, seed: str = "johncodes") -> TypingPlan:
    """Weight each character with a 'cost', then scale costs to fill ``duration``."""
    rng = _rng_stream(seed + code[:64])
    weights: list[float] = []
    at_line_start = True
    for ch in code:
        if ch == "\n":
            w = 5.5                      # pause at end of line
            at_line_start = True
        elif ch == " " and at_line_start:
            w = 0.15                     # indentation flies in
        elif ch in " ":
            w = 0.9
            at_line_start = False
        elif ch in ".,:()[]{}":
            w = 1.4
            at_line_start = False
        else:
            w = 1.0
            at_line_start = False
        w *= 0.75 + 0.6 * next(rng)      # human jitter
        weights.append(w)

    total_w = sum(weights) or 1.0
    scale = duration / total_w
    times: list[float] = []
    acc = 0.0
    for w in weights:
        acc += w * scale
        times.append(acc)

    click_times = [
        t for ch, t in zip(code, times)
        if not (ch == " " or ch == "\n")
    ]
    return TypingPlan(times=times, duration=duration, click_times=click_times)
