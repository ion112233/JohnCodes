"""Command-line interface: ``python -m johncodes <command>``."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import Config
from .question import discover, load_question


def _add_config_arg(p: argparse.ArgumentParser) -> None:
    p.add_argument("--config", metavar="FILE", help="JSON config overrides")


def cmd_build(args) -> int:
    from .pipeline import build_short
    from .audio import Narrator

    cfg = Config.load(args.config)
    if args.draft:
        cfg.fps, cfg.crf, cfg.x264_preset = 15, 30, "ultrafast"
        print("draft mode: 15fps / crf 30 / ultrafast")
    if args.all:
        paths = discover(args.content)
        if not paths:
            print(f"no questions found in {args.content}")
            return 1
    else:
        if not args.question:
            print("provide a question file, or --all")
            return 2
        paths = [Path(args.question)]

    narrator = Narrator(cfg)  # reuse the loaded model across questions
    built = []
    for p in paths:
        built.append(build_short(p, cfg, narrator=narrator,
                                 keep_intermediates=args.keep))
    print(f"\ndone — {len(built)} short(s):")
    for b in built:
        print(f"  {b}")
    return 0


def cmd_preview(args) -> int:
    """Render a single still frame of a scene — fast visual iteration, no audio."""
    from .fonts import FontBook
    from .scenes import (CompareScene, EpisodeCard, ExplainCard, GotchaScene, QuestionCard,
                         RecapCard, ReplScene, TerminalScene, TitleCard, TopicCard, TypingScene)

    cfg = Config.load(args.config)
    q = load_question(args.question)
    fonts = FontBook(cfg.fonts_path, cfg.mono_font, cfg.ui_font)
    frac = max(0.0, min(1.0, args.at))
    kind = args.scene
    first = lambda ty: next((s for s in q.segments if s.type == ty), None)

    if kind in ("title", "opener"):
        scene = EpisodeCard(cfg, fonts, q, 6.0) if q.is_episode else TitleCard(cfg, fonts, q, 6.0)
    elif kind in ("takeaway", "recap"):
        seg = first("card_recap")
        scene = (RecapCard(cfg, fonts, seg.points, seg.next_up, 20.0,
                           [1.0 + 3.0 * i for i in range(len(seg.points))]) if seg
                 else ExplainCard(cfg, fonts, q, 6.0))
    elif kind == "topic":
        seg = first("card_topic")
        scene = TopicCard(cfg, fonts, seg.card_title if seg else q.topic,
                          seg.card_subtitle if seg else None, 5.0)
    elif kind == "question":
        seg = first("card_question")
        scene = QuestionCard(cfg, fonts, seg.question if seg else "Why?",
                             seg.answer if seg else "Because.", 20.0, 10.0)
    elif kind == "terminal":
        seg = first("terminal")
        scene = TerminalScene(cfg, fonts, q, code=q.final_code,
                              command=seg.command if seg else "python solution.py",
                              output=seg.output if seg else "[]", duration=8.0, lead=0.0, seed=q.id)
    elif kind == "repl":
        seg = first("repl")
        scene = ReplScene(cfg, fonts, seg.lines, 10.0, lead=0.0)
    elif kind == "gotcha":
        seg = first("gotcha")
        scene = GotchaScene(cfg, fonts, q, code=seg.code, bad_line=seg.bad_line,
                            error=seg.error, duration=8.0, lead=0.0)
    elif kind == "compare":
        seg = first("compare")
        scene = CompareScene(cfg, fonts, left_label=seg.left_label, left_code=seg.left_code,
                             right_label=seg.right_label, right_code=seg.right_code,
                             verdict=seg.verdict, duration=6.0)
    else:
        scene = TypingScene(cfg, fonts, q, start_code="", end_code=q.final_code,
                            duration=12.0, lead=0.0, seed=q.id)

    img = scene.render(t=scene.duration * frac + 0.001)
    out = Path(args.out or (cfg.output_path / f"{q.id}-preview.png"))
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    print(f"wrote {out}  (font: {fonts.mono_family})")
    return 0


def cmd_timeline(args) -> int:
    """Back-fill output/<id>/video/timeline.json (TTS only, no video render)."""
    from .audio import Narrator
    from .pipeline import build_short

    cfg = Config.load(args.config)
    paths = ([p for p in discover(args.content) if load_question(p).is_episode]
             if args.all else [Path(p) for p in args.question])
    if not paths:
        print("provide script file(s), or --all")
        return 2
    narrator = Narrator(cfg)
    for p in paths:
        build_short(p, cfg, narrator=narrator, timeline_only=True)
    return 0


def cmd_shorts(args) -> int:
    """Cut 30-60 s vertical Shorts from rendered episodes -> output/<id>/shorts/."""
    from .shorts import make_shorts

    cfg = Config.load(args.config)
    paths = ([p for p in discover(args.content) if load_question(p).is_episode]
             if args.all else [Path(p) for p in args.question])
    if not paths:
        print("provide script file(s), or --all")
        return 2
    total = 0
    for p in paths:
        total += len(make_shorts(cfg, load_question(p), count=args.count, replan=args.replan,
                                 plan_only=args.plan_only))
    if not args.plan_only:
        print(f"\n{total} Short(s)")
    return 0


def cmd_thumbnail(args) -> int:
    """Render the 1280x720 YouTube thumbnails (four layouts) for one script or all."""
    from .thumbnail import VARIANTS, render_thumbnails

    cfg = Config.load(args.config)
    paths = discover(args.content) if args.all else [Path(p) for p in args.question]
    if not paths:
        print("provide script file(s), or --all")
        return 2
    wanted = [v.strip() for v in args.variants.split(",")] if args.variants else None
    if wanted and set(wanted) - set(VARIANTS):
        print(f"--variants must be from {', '.join(VARIANTS)}")
        return 2
    total = 0
    for p in paths:
        q = load_question(p)
        out = render_thumbnails(cfg, q, Path(args.out) if args.out else None, wanted)
        total += len(out)
        print(f"[{q.id}]")
        for o in out:
            print(f"  {o}  ({o.stat().st_size / 1e3:.0f} KB)")
    print(f"\n{total} thumbnail(s)")
    return 0


def cmd_tts(args) -> int:
    from .audio import Narrator
    from scipy.io import wavfile
    import numpy as np

    cfg = Config.load(args.config)
    if args.voice:
        cfg.tts_voice = args.voice
    clip = Narrator(cfg).say(args.text)
    out = Path(args.out)
    wavfile.write(str(out), cfg.sample_rate, (clip.audio * 32767).astype(np.int16))
    print(f"wrote {out}  ({clip.duration:.2f}s, voice {cfg.tts_voice})")
    return 0


def cmd_list(args) -> int:
    paths = discover(args.content)
    if not paths:
        print(f"no questions in {args.content}")
        return 0
    for p in paths:
        try:
            q = load_question(p)
            tag = f"EP{q.episode.number:>2}" if q.is_episode else q.difficulty
            extra = f"  (~{q.target_minutes:g}m)" if q.target_minutes else ""
            print(f"  {q.id:<28} {tag:<7} {q.title}{extra}")
        except SystemExit as e:
            print(f"  {p.name:<28} !! {e}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="johncodes", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="render a Short (or all of them)")
    b.add_argument("question", nargs="?", help="path to a question .json")
    b.add_argument("--all", action="store_true", help="build every question")
    b.add_argument("--content", default="content")
    b.add_argument("--keep", action="store_true", help="keep intermediate files")
    b.add_argument("--draft", action="store_true", help="fast low-quality render (15fps)")
    _add_config_arg(b)
    b.set_defaults(func=cmd_build)

    p = sub.add_parser("preview", help="render one still PNG of a scene (no audio)")
    p.add_argument("question")
    p.add_argument("--scene", default="typing",
                   choices=["typing", "terminal", "repl", "gotcha", "compare",
                            "opener", "title", "recap", "takeaway", "topic", "question"])
    p.add_argument("--at", type=float, default=0.6, help="progress fraction 0..1 (default 0.6)")
    p.add_argument("--out")
    _add_config_arg(p)
    p.set_defaults(func=cmd_preview)

    tm = sub.add_parser("timeline", help="back-fill timeline.json for already-rendered videos")
    tm.add_argument("question", nargs="*", help="script .json file(s)")
    tm.add_argument("--all", action="store_true", help="every course episode in --content")
    tm.add_argument("--content", default="content")
    _add_config_arg(tm)
    tm.set_defaults(func=cmd_timeline)

    sh = sub.add_parser("shorts", help="cut 30-60 s vertical Shorts from rendered episodes")
    sh.add_argument("question", nargs="*", help="script .json file(s)")
    sh.add_argument("--all", action="store_true", help="every course episode in --content")
    sh.add_argument("--content", default="content")
    sh.add_argument("--count", type=int, help="force this many Shorts (default: 2-4 by potential)")
    sh.add_argument("--replan", action="store_true", help="ignore shorts/plan.json and re-pick")
    sh.add_argument("--plan-only", action="store_true", help="print the picks, render nothing")
    _add_config_arg(sh)
    sh.set_defaults(func=cmd_shorts)

    th = sub.add_parser("thumbnail", help="render YouTube thumbnails (1280x720) for a script")
    th.add_argument("question", nargs="*", help="script .json file(s)")
    th.add_argument("--all", action="store_true", help="every script in --content")
    th.add_argument("--content", default="content")
    th.add_argument("--variants", help="comma list of: headline,code,curiosity,number (default all)")
    th.add_argument("--out", help="output dir (default output/<id>/thumbnails)")
    _add_config_arg(th)
    th.set_defaults(func=cmd_thumbnail)

    t = sub.add_parser("tts", help="synthesise a line of narration to wav")
    t.add_argument("text")
    t.add_argument("out")
    t.add_argument("--voice")
    _add_config_arg(t)
    t.set_defaults(func=cmd_tts)

    ls = sub.add_parser("list", help="list discovered questions")
    ls.add_argument("--content", default="content")
    ls.set_defaults(func=cmd_list)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\ninterrupted")
        return 130


if __name__ == "__main__":
    sys.exit(main())
