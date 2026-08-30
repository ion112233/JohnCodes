"""Runtime configuration.

Defaults live here. Override any subset with a JSON file (see ``config.example.json``)
passed as ``--config path.json`` on the CLI.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Config:
    # ---- video ----
    width: int = 1920
    height: int = 1080
    fps: int = 30
    crf: int = 18
    x264_preset: str = "medium"

    # ---- scene pacing (seconds) ----
    title_min: float = 3.0
    title_pad: float = 0.7
    typing_min: float = 9.0
    typing_pad: float = 1.0
    typing_lead: float = 0.6     # silent beat before typing starts
    explain_min: float = 3.5
    explain_pad: float = 1.1
    fade: float = 0.35           # global fade in/out

    # Code types at a natural, fixed speed and is ALLOWED to finish before the
    # narration does (it then just sits there complete). Do NOT stretch typing to
    # fill the narration — that looks robotic. ~22 chars/sec ≈ a brisk human.
    typing_cps: float = 22.0
    typing_newline_pause: float = 0.22   # extra seconds at each line break

    # card_question: the question sits on screen this long before the answer
    # appears. Both the question and the answer are read aloud.
    question_reveal_gap: float = 10.0

    # ---- course-episode scenes ----
    episode_min: float = 4.0
    topic_min: float = 2.6
    recap_min: float = 5.0
    gotcha_min: float = 5.0
    compare_min: float = 5.0
    repl_min: float = 4.0
    question_min: float = 4.0
    runtime_tolerance: float = 0.08   # warn if |actual-target|/target exceeds this

    # ---- captions ----
    captions: bool = False

    # ---- audio ----
    sample_rate: int = 24000
    tts_voice: str = "am_michael,am_fenrir"  # Kokoro voice id, or comma-list to blend
    tts_lang: str = "a"          # 'a' = American English, 'b' = British
    # Keep this at (or very near) 1.0. The voice was chosen at 1.0; slowing it
    # down makes it sound artificial. To hit an episode's target runtime, write
    # MORE narration — never slow the voice.
    tts_speed: float = 1.0
    narration_gain_db: float = 0.0
    keystroke_gain_db: float = -23.0   # keystroke clicks sit well under the voice
    music_gain_db: float = -22.0
    music_duck_db: float = -6.0   # extra attenuation while narration plays
    music_path: Optional[str] = None  # None -> first file in assets/music/

    # ---- paths (relative to repo root unless absolute) ----
    assets_dir: str = "assets"
    output_dir: str = "output"
    fonts_dir: str = "assets/fonts"

    # ---- fonts (optional explicit overrides) ----
    mono_font: Optional[str] = None   # e.g. assets/fonts/JetBrainsMono-Regular.ttf
    ui_font: Optional[str] = None

    # ---- IDE cosmetics ----
    project_name: str = "JohnCodes"
    python_label: str = "Python 3.12"

    def _abs(self, value: str) -> Path:
        p = Path(value)
        return p if p.is_absolute() else (REPO_ROOT / p)

    @property
    def assets_path(self) -> Path:
        return self._abs(self.assets_dir)

    @property
    def output_path(self) -> Path:
        return self._abs(self.output_dir)

    @property
    def fonts_path(self) -> Path:
        return self._abs(self.fonts_dir)

    def resolved_music_path(self) -> Optional[Path]:
        if self.music_path:
            p = self._abs(self.music_path)
            return p if p.exists() else None
        music_dir = self.assets_path / "music"
        if music_dir.is_dir():
            for f in sorted(music_dir.iterdir()):
                if f.suffix.lower() in {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}:
                    return f
        return None

    def keystroke_paths(self) -> list[Path]:
        sfx_dir = self.assets_path / "sfx"
        if not sfx_dir.is_dir():
            return []
        return [f for f in sorted(sfx_dir.iterdir())
                if f.suffix.lower() in {".wav", ".mp3", ".m4a", ".aac", ".ogg", ".flac"}]

    @classmethod
    def load(cls, path: Optional[str | Path] = None) -> "Config":
        cfg = cls()
        if path:
            data: dict[str, Any] = json.loads(Path(path).read_text())
            known = {f.name for f in fields(cls)}
            unknown = set(data) - known
            if unknown:
                raise SystemExit(f"Unknown config keys: {', '.join(sorted(unknown))}")
            for k, v in data.items():
                setattr(cfg, k, v)
        return cfg
