"""Font resolution.

Prefers JetBrains Mono (PyCharm's own font) if the user drops it in
``assets/fonts/``; otherwise falls back to Menlo, which ships with macOS and
looks close enough. UI text (window chrome, cards) uses a sans fallback chain.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PIL import ImageFont

# (path, ttc index) candidate chains, first hit wins
_MONO_REGULAR = [
    ("JetBrainsMono-Regular.ttf", 0), ("JetBrainsMonoNL-Regular.ttf", 0),
    ("FiraCode-Regular.ttf", 0), ("Hack-Regular.ttf", 0),
    ("/System/Library/Fonts/Menlo.ttc", 0),
    ("/System/Library/Fonts/SFNSMono.ttf", 0),
]
_MONO_BOLD = [
    ("JetBrainsMono-Bold.ttf", 0), ("FiraCode-Bold.ttf", 0), ("Hack-Bold.ttf", 0),
    ("/System/Library/Fonts/Menlo.ttc", 1),
]
_MONO_ITALIC = [
    ("JetBrainsMono-Italic.ttf", 0), ("Hack-Italic.ttf", 0),
    ("/System/Library/Fonts/Menlo.ttc", 2),
]
_UI_REGULAR = [
    ("/System/Library/Fonts/SFNS.ttf", 0),
    ("/System/Library/Fonts/HelveticaNeue.ttc", 0),
    ("/System/Library/Fonts/Helvetica.ttc", 0),
    ("/System/Library/Fonts/Menlo.ttc", 0),
]
_UI_BOLD = [
    ("/System/Library/Fonts/SFNS.ttf", 2),
    ("/System/Library/Fonts/HelveticaNeue.ttc", 1),
    ("/System/Library/Fonts/Helvetica.ttc", 1),
    ("/System/Library/Fonts/Menlo.ttc", 1),
]


def _resolve(candidates, fonts_dir: Path, explicit: Optional[str], size: int) -> ImageFont.FreeTypeFont:
    tries: list[tuple[str, int]] = []
    if explicit:
        tries.append((explicit, 0))
    for name, idx in candidates:
        p = Path(name)
        tries.append((str(p if p.is_absolute() else fonts_dir / name), idx))
    for path, idx in tries:
        try:
            return ImageFont.truetype(path, size, index=idx)
        except (OSError, ValueError):
            continue
    return ImageFont.load_default(size)


@dataclass
class MonoFont:
    regular: ImageFont.FreeTypeFont
    bold: ImageFont.FreeTypeFont
    italic: ImageFont.FreeTypeFont
    size: int
    char_w: float
    line_h: int

    def pick(self, bold: bool = False, italic: bool = False) -> ImageFont.FreeTypeFont:
        if italic:
            return self.italic
        return self.bold if bold else self.regular


class FontBook:
    def __init__(self, fonts_dir: Path, mono_override: Optional[str] = None,
                 ui_override: Optional[str] = None):
        self.fonts_dir = fonts_dir
        self._mono_override = mono_override
        self._ui_override = ui_override
        self._mono_cache: dict[int, MonoFont] = {}
        self._ui_cache: dict[tuple[int, bool], ImageFont.FreeTypeFont] = {}

    def mono(self, size: int) -> MonoFont:
        if size not in self._mono_cache:
            reg = _resolve(_MONO_REGULAR, self.fonts_dir, self._mono_override, size)
            bold = _resolve(_MONO_BOLD, self.fonts_dir, None, size)
            ital = _resolve(_MONO_ITALIC, self.fonts_dir, None, size)
            char_w = reg.getlength("M") or size * 0.6
            line_h = round(size * 1.5)
            self._mono_cache[size] = MonoFont(reg, bold, ital, size, char_w, line_h)
        return self._mono_cache[size]

    def ui(self, size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
        key = (size, bold)
        if key not in self._ui_cache:
            chain = _UI_BOLD if bold else _UI_REGULAR
            self._ui_cache[key] = _resolve(chain, self.fonts_dir, self._ui_override, size)
        return self._ui_cache[key]

    @property
    def mono_family(self) -> str:
        try:
            return self.mono(32).regular.getname()[0]
        except Exception:
            return "monospace"
