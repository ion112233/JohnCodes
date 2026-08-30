"""End-to-end: question.json -> output/<id>/<id>.mp4."""
from __future__ import annotations

import time
from pathlib import Path

from .audio import AudioSpec, Narrator, build_track
from .config import Config
from .fonts import FontBook
from .question import Question, load_question
from .render import mux, render_video
from .scenes import ExplainCard, TitleCard, TypingScene
from .typing_plan import build_plan


def build_short(question_path: str | Path, cfg: Config, *,
                narrator: Narrator | None = None, keep_intermediates: bool = False) -> Path:
    q: Question = load_question(question_path)
    fonts = FontBook(cfg.fonts_path, cfg.mono_font, cfg.ui_font)
    outdir = cfg.output_path / q.id
    outdir.mkdir(parents=True, exist_ok=True)

    print(f"[{q.id}] {q.title}  ({q.difficulty} · {q.topic})")
    print(f"  mono font: {fonts.mono_family}")

    # --- 1. voiceover ---
    print("  synthesising voiceover (kokoro)…")
    t0 = time.time()
    narrator = narrator or Narrator(cfg)
    hook = narrator.say(q.narration.hook)
    walk = narrator.say(q.narration.walkthrough)
    take = narrator.say(q.narration.takeaway)
    print(f"    hook {hook.duration:.1f}s · walkthrough {walk.duration:.1f}s · "
          f"takeaway {take.duration:.1f}s  ({time.time() - t0:.1f}s)")

    # --- 2. timeline ---
    title_dur = max(cfg.title_min, hook.duration + cfg.title_pad)
    typing_dur = max(cfg.typing_min, walk.duration + cfg.typing_lead + cfg.typing_pad)
    explain_dur = max(cfg.explain_min, take.duration + cfg.explain_pad)

    plan = build_plan(q.code, duration=max(2.0, walk.duration + 0.4), seed=q.id)

    scenes = [
        TitleCard(cfg, fonts, q, title_dur),
        TypingScene(cfg, fonts, q, plan, typing_dur, cfg.typing_lead),
        ExplainCard(cfg, fonts, q, explain_dur),
    ]
    t_title, t_typing, t_explain = 0.0, title_dur, title_dur + typing_dur
    total = title_dur + typing_dur + explain_dur
    print(f"  timeline: {total:.1f}s  "
          f"(title {title_dur:.1f} + typing {typing_dur:.1f} + takeaway {explain_dur:.1f})")

    # --- 3. audio track ---
    spec = AudioSpec(
        total_duration=total,
        narration_at=[
            (t_title + 0.25, hook.audio),
            (t_typing + cfg.typing_lead, walk.audio),
            (t_explain + 0.35, take.audio),
        ],
        keystroke_times=[t_typing + cfg.typing_lead + ct for ct in plan.click_times],
        narration_windows=[
            (t_title + 0.25, t_title + 0.25 + hook.duration),
            (t_typing + cfg.typing_lead, t_typing + cfg.typing_lead + walk.duration),
            (t_explain + 0.35, t_explain + 0.35 + take.duration),
        ],
    )
    audio_path = outdir / "audio.wav"
    print("  mixing audio…")
    build_track(cfg, spec, audio_path)

    # --- 4. video + mux ---
    print("  rendering video…")
    silent = outdir / "video_silent.mp4"
    render_video(cfg, scenes, silent)

    final = outdir / f"{q.id}.mp4"
    mux(cfg, silent, audio_path, final)

    if not keep_intermediates:
        silent.unlink(missing_ok=True)
        audio_path.unlink(missing_ok=True)

    size_mb = final.stat().st_size / 1e6
    print(f"  ✓ {final}  ({size_mb:.1f} MB, {total:.1f}s)")
    return final
