"""End-to-end: question.json -> output/<id>/<id>.mp4.

Segments are compiled to a scene list:

    TitleCard  [hook narration]
    <segments, in order>
    ExplainCard  [takeaway narration]

A ``narration`` segment becomes the voiceover of the next code / terminal / card
scene; if nothing follows it, it plays as a short hold on the current editor.
"""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np

from .audio import AudioSpec, Narrator, build_track
from .config import Config
from .fonts import FontBook
from .question import Question, Segment, load_question
from .render import mux, render_video
from .scenes import (ExplainCard, QuestionCard, Scene, TerminalScene, TitleCard,
                     TopicCard, TypingScene)


def _say(narrator: Narrator, text: str | None, cache: dict):
    if not text:
        return None, 0.0
    if text not in cache:
        cache[text] = narrator.say(text)
    clip = cache[text]
    return clip.audio, clip.duration


def build_short(question_path: str | Path, cfg: Config, *,
                narrator: Narrator | None = None, keep_intermediates: bool = False) -> Path:
    q: Question = load_question(question_path)
    fonts = FontBook(cfg.fonts_path, cfg.mono_font, cfg.ui_font)
    outdir = cfg.output_path / q.id
    outdir.mkdir(parents=True, exist_ok=True)
    narrator = narrator or Narrator(cfg)
    tts_cache: dict = {}

    print(f"[{q.id}] {q.title}  ({q.difficulty} · {q.topic})")
    print(f"  mono font: {fonts.mono_family}")
    print("  synthesising voiceover (kokoro)…")
    t0 = time.time()

    hook_txt = q.narration_beat("hook")
    take_txt = q.narration_beat("takeaway")
    hook_audio, hook_dur = _say(narrator, hook_txt, tts_cache)
    take_audio, take_dur = _say(narrator, take_txt, tts_cache)

    scenes: list[Scene] = []
    narration_at: list[tuple[float, np.ndarray]] = []
    narration_windows: list[tuple[float, float]] = []
    keystroke_times: list[float] = []
    clock = 0.0

    def add(scene: Scene, audio, adur: float, voice_offset: float = 0.3):
        nonlocal clock
        scenes.append(scene)
        if audio is not None:
            narration_at.append((clock + voice_offset, audio))
            narration_windows.append((clock + voice_offset, clock + voice_offset + adur))
        clock += scene.duration

    # ---- title ----
    title_dur = max(cfg.title_min, (hook_dur + cfg.title_pad) if hook_dur else cfg.title_min)
    add(TitleCard(cfg, fonts, q, title_dur), hook_audio, hook_dur, voice_offset=0.25)

    # ---- segments ----
    code_buffer = ""
    pending: Segment | None = None  # unconsumed narration
    seg_index = 0

    for seg in q.segments:
        if seg.type == "narration":
            if seg.beat in ("hook", "takeaway"):
                continue  # consumed by the auto cards
            pending = seg
            continue

        p_audio, p_dur = _say(narrator, pending.text if pending else None, tts_cache)
        pending = None
        seg_index += 1
        seed = f"{q.id}-{seg_index}"

        if seg.type == "code":
            end = seg.code or ""
            dur = max(cfg.typing_min,
                      (p_dur + cfg.typing_lead + cfg.typing_pad) if p_dur else
                      max(cfg.typing_min, len(end[len(_cp(code_buffer, end)):]) * 0.045 + 2.5))
            sc = TypingScene(cfg, fonts, q, start_code=code_buffer, end_code=end,
                             duration=dur, lead=cfg.typing_lead, seed=seed)
            keystroke_times += sc.keystroke_times(clock)
            add(sc, p_audio, p_dur, voice_offset=cfg.typing_lead)
            code_buffer = end

        elif seg.type == "terminal":
            body = 3.0 + 0.05 * len(seg.command or "") + 0.5 * len((seg.output or "").split("\n"))
            dur = max(body, (p_dur + 1.0) if p_dur else 0)
            sc = TerminalScene(cfg, fonts, q, code=code_buffer, command=seg.command or "",
                               output=seg.output or "", duration=dur,
                               lead=cfg.typing_lead, seed=seed)
            keystroke_times += sc.keystroke_times(clock)
            add(sc, p_audio, p_dur, voice_offset=TerminalScene.SLIDE + 0.1)

        elif seg.type == "card_topic":
            dur = max(2.6, (p_dur + 1.0) if p_dur else 2.6)
            add(TopicCard(cfg, fonts, seg.card_title or "", seg.card_subtitle, dur),
                p_audio, p_dur, voice_offset=0.35)

        elif seg.type == "card_question":
            dur = max(4.0, (p_dur + 1.4) if p_dur else 4.0)
            add(QuestionCard(cfg, fonts, seg.question or "", seg.answer, dur),
                p_audio, p_dur, voice_offset=0.35)

    if pending is not None:  # leftover narration -> hold on the editor
        p_audio, p_dur = _say(narrator, pending.text, tts_cache)
        dur = max(cfg.typing_min, p_dur + 1.2)
        sc = TypingScene(cfg, fonts, q, start_code=code_buffer, end_code=code_buffer or " ",
                         duration=dur, lead=0.0, seed=f"{q.id}-hold")
        add(sc, p_audio, p_dur, voice_offset=0.3)

    # ---- takeaway ----
    explain_dur = max(cfg.explain_min, (take_dur + cfg.explain_pad) if take_dur else cfg.explain_min)
    add(ExplainCard(cfg, fonts, q, explain_dur), take_audio, take_dur, voice_offset=0.35)

    total = clock
    print(f"    voiceover ready ({time.time() - t0:.1f}s) · {len(scenes)} scenes · {total:.1f}s")

    # ---- audio ----
    spec = AudioSpec(total_duration=total, narration_at=narration_at,
                     keystroke_times=keystroke_times, narration_windows=narration_windows)
    audio_path = outdir / "audio.wav"
    print("  mixing audio…")
    build_track(cfg, spec, audio_path)

    # ---- video + mux ----
    print("  rendering video…")
    silent = outdir / "video_silent.mp4"
    render_video(cfg, scenes, silent)
    final = outdir / f"{q.id}.mp4"
    mux(cfg, silent, audio_path, final)

    if not keep_intermediates:
        silent.unlink(missing_ok=True)
        audio_path.unlink(missing_ok=True)

    print(f"  ✓ {final}  ({final.stat().st_size / 1e6:.1f} MB, {total:.1f}s)")
    return final


def _cp(a: str, b: str) -> str:
    n = 0
    for ca, cb in zip(a, b):
        if ca != cb:
            break
        n += 1
    return a[:n]
