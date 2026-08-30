"""Small shared helpers."""
from __future__ import annotations

import re

RGB = tuple[int, int, int]


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


def ease_out_cubic(t: float) -> float:
    t = clamp(t, 0.0, 1.0)
    return 1 - (1 - t) ** 3


def ease_in_out(t: float) -> float:
    t = clamp(t, 0.0, 1.0)
    return 3 * t * t - 2 * t * t * t


def mix_color(a: RGB, b: RGB, t: float) -> RGB:
    return (round(lerp(a[0], b[0], t)), round(lerp(a[1], b[1], t)), round(lerp(a[2], b[2], t)))


def wrap_text(text: str, font, max_width: float) -> list[str]:
    """Greedy word wrap using a PIL font's pixel metrics."""
    lines: list[str] = []
    for para in text.split("\n"):
        words = para.split()
        if not words:
            lines.append("")
            continue
        cur = words[0]
        for w in words[1:]:
            if font.getlength(f"{cur} {w}") <= max_width:
                cur += " " + w
            else:
                lines.append(cur)
                cur = w
        lines.append(cur)
    return lines


_SENT_SPLIT = re.compile(r"(?<=[.!?;:])\s+")


def split_sentences(text: str) -> list[str]:
    parts = [p.strip() for p in _SENT_SPLIT.split(text.strip()) if p.strip()]
    return parts or [text.strip()]


def db_to_gain(db: float) -> float:
    return 10.0 ** (db / 20.0)
