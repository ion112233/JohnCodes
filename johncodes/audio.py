"""Voiceover (Kokoro) + keystroke SFX + music bed -> one wav track."""
from __future__ import annotations

import subprocess
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
from scipy.io import wavfile

from .config import Config
from .typing_plan import TypingPlan
from .util import db_to_gain

warnings.filterwarnings("ignore")


# --------------------------------------------------------------------------- TTS
@dataclass
class VoiceClip:
    audio: np.ndarray   # float32 mono, sample_rate
    duration: float
    # (word, start, end) in seconds from the start of ``audio`` — drives the
    # word-by-word captions on the Shorts. Punctuation stays attached to its word.
    words: list[tuple[str, float, float]] = field(default_factory=list)


class Narrator:
    """Thin wrapper around kokoro.KPipeline (lazy-initialised, reused)."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._pipe = None

    def _pipeline(self):
        if self._pipe is None:
            from kokoro import KPipeline  # heavy import; defer
            self._pipe = KPipeline(lang_code=self.cfg.tts_lang)
        return self._pipe

    def say(self, text: str) -> VoiceClip:
        pipe = self._pipeline()
        sr = self.cfg.sample_rate
        chunks: list[np.ndarray] = []
        words: list[list] = []
        offset = 0.0
        for res in pipe(text, voice=self.cfg.tts_voice, speed=self.cfg.tts_speed):
            audio = res.audio
            arr = audio.detach().cpu().numpy() if hasattr(audio, "detach") else np.asarray(audio)
            arr = arr.astype(np.float32)
            chunks.append(arr)
            glued = False                      # previous token had no trailing space
            for tok in res.tokens or []:
                if tok.start_ts is None or tok.end_ts is None:
                    glued = (tok.whitespace == "")
                    continue
                if glued and words:
                    words[-1][0] += tok.text
                    words[-1][2] = offset + tok.end_ts
                else:
                    words.append([tok.text, offset + tok.start_ts, offset + tok.end_ts])
                glued = (tok.whitespace == "")
            offset += len(arr) / sr
        if not chunks:
            return VoiceClip(np.zeros(1, np.float32), 0.0)
        full = np.concatenate(chunks)
        a, b = _trim_bounds(full, sr)
        lead = a / sr
        trimmed = full[a:b]
        dur = len(trimmed) / sr
        return VoiceClip(trimmed, dur,
                         [(w, max(0.0, s0 - lead), min(dur, max(0.0, e0 - lead)))
                          for w, s0, e0 in words])


def _trim_bounds(x: np.ndarray, sr: int, thresh: float = 0.006, pad_ms: int = 60) -> tuple[int, int]:
    if x.size == 0:
        return 0, 0
    idx = np.where(np.abs(x) > thresh)[0]
    if idx.size == 0:
        return 0, len(x)
    pad = int(sr * pad_ms / 1000)
    return max(0, idx[0] - pad), min(len(x), idx[-1] + pad)


# ------------------------------------------------------------------- click synth
def _synth_click(sr: int, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(1234 + seed)
    n = int(sr * 0.045)
    t = np.arange(n) / sr
    env = np.exp(-t * 120.0)
    noise = rng.standard_normal(n) * env
    tone = np.sin(2 * np.pi * 2100 * t) * env * 0.4
    click = noise * 0.6 + tone
    # gentle high-pass so it sounds like a keycap, not a thud
    click = np.diff(click, prepend=click[:1])
    return (click / (np.max(np.abs(click)) + 1e-9) * 0.8).astype(np.float32)


def _load_sfx(paths: list[Path], sr: int) -> list[np.ndarray]:
    out: list[np.ndarray] = []
    for p in paths:
        try:
            data = _decode_to_mono(p, sr)
            if data.size:
                out.append((data / (np.max(np.abs(data)) + 1e-9) * 0.8).astype(np.float32))
        except Exception:
            continue
    return out


def _decode_to_mono(path: Path, sr: int) -> np.ndarray:
    proc = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(sr),
         "-f", "f32le", "-"],
        capture_output=True, check=True,
    )
    return np.frombuffer(proc.stdout, dtype=np.float32).copy()


# ---------------------------------------------------------------------- assembly
@dataclass
class AudioSpec:
    total_duration: float
    narration_at: list[tuple[float, np.ndarray]]   # (start_seconds, audio)
    keystroke_times: list[float]                   # absolute seconds
    narration_windows: list[tuple[float, float]]   # for music ducking


def build_track(cfg: Config, spec: AudioSpec, out_path: Path) -> None:
    sr = cfg.sample_rate
    total = int(np.ceil(spec.total_duration * sr)) + sr // 2
    mix = np.zeros(total, np.float32)

    # --- narration ---
    narr = np.zeros(total, np.float32)
    for start, audio in spec.narration_at:
        s = int(start * sr)
        e = min(total, s + len(audio))
        narr[s:e] += audio[: e - s]
    mix += narr * db_to_gain(cfg.narration_gain_db)

    # --- keystrokes ---
    sfx = _load_sfx(cfg.keystroke_paths(), sr)
    if not sfx:
        sfx = [_synth_click(sr, i) for i in range(3)]
    ks = np.zeros(total, np.float32)
    for i, kt in enumerate(spec.keystroke_times):
        clip = sfx[i % len(sfx)]
        s = int(kt * sr)
        e = min(total, s + len(clip))
        if s < total:
            ks[s:e] += clip[: e - s] * (0.75 + 0.25 * ((i * 37) % 5) / 4)
    mix += ks * db_to_gain(cfg.keystroke_gain_db)

    # --- music bed (looped, ducked under narration, fade out) ---
    music_path = cfg.resolved_music_path()
    if music_path:
        try:
            m = _decode_to_mono(music_path, sr)
            if m.size:
                reps = int(np.ceil(total / len(m)))
                m = np.tile(m, reps)[:total]
                gain = np.full(total, db_to_gain(cfg.music_gain_db), np.float32)
                duck = db_to_gain(cfg.music_gain_db + cfg.music_duck_db)
                for a, b in spec.narration_windows:
                    s, e = int(a * sr), min(total, int((b + 0.3) * sr))
                    gain[s:e] = duck
                fade = int(1.5 * sr)
                gain[-fade:] *= np.linspace(1, 0, fade)
                gain[:int(0.4 * sr)] *= np.linspace(0, 1, int(0.4 * sr))
                mix += m * gain
        except Exception as e:  # noqa: BLE001
            print(f"  music skipped ({music_path.name}): {e}")

    # --- limit / normalise ---
    peak = float(np.max(np.abs(mix)))
    if peak > 0.98:
        mix = mix / peak * 0.98
    wavfile.write(str(out_path), sr, (mix * 32767).astype(np.int16))
