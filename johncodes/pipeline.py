"""End-to-end: script JSON -> output/<id>/<id>.mp4 (+ chapters.txt).

Segments compile to a scene list:

    opener   TitleCard (question) | EpisodeCard (course episode)   [hook narration]
    <segments, in order>
    closer   ExplainCard (question) | RecapCard (episode)          [takeaway narration]

A ``narration`` segment voices the next code/terminal/card/gotcha/compare/repl
scene; leftover narration plays as a short hold on the editor.
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
from .scenes import (CompareScene, EpisodeCard, ExplainCard, GotchaScene, QuestionCard,
                     RecapCard, ReplScene, Scene, TerminalScene, TitleCard, TopicCard,
                     TypingScene)


def _say(narrator: Narrator, text: str | None, cache: dict):
    if not text:
        return None, 0.0
    if text not in cache:
        cache[text] = narrator.say(text)
    return cache[text].audio, cache[text].duration


def _say_all(narrator: Narrator, segs: list, cache: dict, sr: int):
    """Concatenate several queued narration segments with a short gap between."""
    parts, dur = [], 0.0
    gap = np.zeros(int(0.35 * sr), np.float32)
    for i, s in enumerate(segs):
        a, dd = _say(narrator, s.text, cache)
        if a is None:
            continue
        if parts:
            parts.append(gap)
            dur += len(gap) / sr
        parts.append(a)
        dur += dd
    if not parts:
        return None, 0.0
    return np.concatenate(parts), dur


def _fmt(sec: float) -> str:
    m, s = divmod(int(round(sec)), 60)
    return f"{m}:{s:02d}"


def _cp(a: str, b: str) -> str:
    n = 0
    for ca, cb in zip(a, b):
        if ca != cb:
            break
        n += 1
    return a[:n]


def build_short(question_path: str | Path, cfg: Config, *,
                narrator: Narrator | None = None, keep_intermediates: bool = False) -> Path:
    q: Question = load_question(question_path)
    fonts = FontBook(cfg.fonts_path, cfg.mono_font, cfg.ui_font)
    outdir = cfg.output_path / q.id
    outdir.mkdir(parents=True, exist_ok=True)
    narrator = narrator or Narrator(cfg)
    tts_cache: dict = {}

    tag = f"EP {q.episode.number}" if q.is_episode else q.difficulty
    print(f"[{q.id}] {q.title}  ({tag} · {q.topic})")
    print(f"  mono font: {fonts.mono_family}")
    print("  synthesising voiceover (kokoro)…")
    t0 = time.time()

    hook_audio, hook_dur = _say(narrator, q.narration_beat("hook"), tts_cache)
    take_audio, take_dur = _say(narrator, q.narration_beat("takeaway"), tts_cache)

    scenes: list[Scene] = []
    narration_at: list[tuple[float, np.ndarray]] = []
    narration_windows: list[tuple[float, float]] = []
    keystroke_times: list[float] = []
    chapters: list[tuple[float, str]] = []
    clock = 0.0

    def add(scene: Scene, audio=None, adur: float = 0.0, voice_offset: float = 0.3,
            chapter: str | None = None, voices: list | None = None):
        """voices: optional list of (offset_seconds, audio, duration) — for scenes
        that carry more than one narration clip (quick check, recap)."""
        nonlocal clock
        if chapter:
            chapters.append((clock, chapter))
        scenes.append(scene)
        for off, a, dd in (voices or ([(voice_offset, audio, adur)] if audio is not None else [])):
            narration_at.append((clock + off, a))
            narration_windows.append((clock + off, clock + off + dd))
        clock += scene.duration

    # ---- opener ----
    if q.is_episode:
        odur = max(cfg.episode_min, (hook_dur + cfg.title_pad) if hook_dur else cfg.episode_min)
        add(EpisodeCard(cfg, fonts, q, odur), hook_audio, hook_dur, 0.25, chapter="Intro")
    else:
        odur = max(cfg.title_min, (hook_dur + cfg.title_pad) if hook_dur else cfg.title_min)
        add(TitleCard(cfg, fonts, q, odur), hook_audio, hook_dur, 0.25)

    code_buffer = ""
    pending: list[Segment] = []
    recap_seg: Segment | None = None
    idx = 0

    for seg in q.segments:
        if seg.type == "narration":
            if seg.beat in ("hook", "takeaway"):
                continue
            pending.append(seg)
            continue
        if seg.type == "card_recap":
            recap_seg = seg
            continue

        p_audio, p_dur = _say_all(narrator, pending, tts_cache, cfg.sample_rate)
        pending = []
        idx += 1
        seed = f"{q.id}-{idx}"

        if seg.type == "code":
            end = seg.code or ""
            # narration (if any) drives the hold; typing runs at natural speed
            # inside it and simply finishes early.
            sc = TypingScene(cfg, fonts, q, start_code=code_buffer, end_code=end,
                             duration=1.0, lead=cfg.typing_lead, seed=seed)
            natural = cfg.typing_lead + sc.plan.duration + cfg.typing_pad
            sc.duration = max(cfg.typing_min, natural,
                              (p_dur + cfg.typing_lead + cfg.typing_pad) if p_dur else 0)
            keystroke_times += sc.keystroke_times(clock)
            add(sc, p_audio, p_dur, cfg.typing_lead)
            code_buffer = end

        elif seg.type == "terminal":
            body = 3.0 + 0.05 * len(seg.command or "") + 0.5 * len((seg.output or "").split("\n"))
            sc = TerminalScene(cfg, fonts, q, code=code_buffer, command=seg.command or "",
                               output=seg.output or "", duration=max(body, (p_dur + 1.0) if p_dur else 0),
                               lead=cfg.typing_lead, seed=seed)
            keystroke_times += sc.keystroke_times(clock)
            add(sc, p_audio, p_dur, TerminalScene.SLIDE + 0.1)

        elif seg.type == "repl":
            body = 1.0 + sum(0.05 * len(l.input) + 0.6 + 0.4 * len((l.output or "").split("\n"))
                             for l in seg.lines)
            sc = ReplScene(cfg, fonts, seg.lines, max(cfg.repl_min, body, (p_dur + 1.0) if p_dur else 0),
                           lead=0.4)
            keystroke_times += sc.keystroke_times(clock)
            add(sc, p_audio, p_dur, 0.4)

        elif seg.type == "gotcha":
            n_err = len((seg.error or "").split("\n"))
            body = 2.5 + 0.4 * n_err
            sc = GotchaScene(cfg, fonts, q, code=seg.code or "", bad_line=seg.bad_line,
                             error=seg.error or "",
                             duration=max(cfg.gotcha_min, body, (p_dur + 1.2) if p_dur else 0),
                             lead=0.3)
            add(sc, p_audio, p_dur, GotchaScene.SLIDE + 0.1)

        elif seg.type == "compare":
            sc = CompareScene(cfg, fonts, left_label=seg.left_label, left_code=seg.left_code or "",
                              right_label=seg.right_label, right_code=seg.right_code or "",
                              verdict=seg.verdict,
                              duration=max(cfg.compare_min, (p_dur + 1.2) if p_dur else cfg.compare_min))
            add(sc, p_audio, p_dur, 0.35)

        elif seg.type == "card_topic":
            dur = max(cfg.topic_min, (p_dur + 1.0) if p_dur else cfg.topic_min)
            add(TopicCard(cfg, fonts, seg.card_title or "", seg.card_subtitle, dur),
                p_audio, p_dur, 0.35, chapter=seg.card_title)

        elif seg.type == "card_question":
            # the question and the answer are both read aloud; the answer appears
            # `question_reveal_gap` seconds after the question shows up.
            q_audio, q_dur = _say(narrator, f"Quick check. {seg.question}", tts_cache)
            a_audio, a_dur = _say(narrator, seg.answer, tts_cache) if seg.answer else (None, 0.0)
            reveal = max(cfg.question_reveal_gap, q_dur + 1.0)
            dur = reveal + (a_dur + 2.0 if seg.answer else 1.5)
            voices = [(0.3, q_audio, q_dur)]
            if a_audio is not None:
                voices.append((reveal + 0.2, a_audio, a_dur))
            add(QuestionCard(cfg, fonts, seg.question or "", seg.answer, dur, reveal),
                voices=voices)

    if pending:
        p_audio, p_dur = _say_all(narrator, pending, tts_cache, cfg.sample_rate)
        sc = TypingScene(cfg, fonts, q, start_code=code_buffer, end_code=code_buffer or " ",
                         duration=max(cfg.typing_min, p_dur + 1.2), lead=0.0, seed=f"{q.id}-hold")
        add(sc, p_audio, p_dur, 0.3)

    # ---- closer ----
    if recap_seg is not None:
        # optional takeaway prose plays first, then each bullet appears exactly
        # as it is read out.
        voices: list = []
        t_off = 0.35
        if take_audio is not None:
            voices.append((t_off, take_audio, take_dur))
            t_off += take_dur + 0.5
        reveal_times: list[float] = []
        for pt in recap_seg.points:
            pa, pd = _say(narrator, pt, tts_cache)
            reveal_times.append(t_off)
            if pa is not None:
                voices.append((t_off, pa, pd))
            t_off += pd + 0.55
        rdur = t_off + 2.2
        add(RecapCard(cfg, fonts, recap_seg.points, recap_seg.next_up, rdur, reveal_times),
            voices=voices, chapter="Recap")
    elif q.complexity is not None:
        edur = max(cfg.explain_min, (take_dur + cfg.explain_pad) if take_dur else cfg.explain_min)
        add(ExplainCard(cfg, fonts, q, edur), take_audio, take_dur, 0.35)

    total = clock
    print(f"    voiceover ready ({time.time() - t0:.1f}s) · {len(scenes)} scenes · {_fmt(total)}")
    if q.target_minutes:
        target = q.target_minutes * 60
        off = (total - target) / target
        flag = "  ⚠" if abs(off) > cfg.runtime_tolerance else "  ✓"
        print(f"    runtime {_fmt(total)} / target {_fmt(target)}  ({off:+.0%}){flag}")

    # ---- chapters ----
    ch_path = outdir / "chapters.txt"
    ch_path.write_text("\n".join(f"{_fmt(0 if i == 0 else tm)} {label}"
                                 for i, (tm, label) in enumerate(chapters)) + "\n")

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

    print(f"  ✓ {final}  ({final.stat().st_size / 1e6:.1f} MB, {_fmt(total)})")
    print(f"  ✓ {ch_path}")
    return final
