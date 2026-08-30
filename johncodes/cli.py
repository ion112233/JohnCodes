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
    """Render a single still frame of the typing scene — fast visual iteration."""
    from .fonts import FontBook
    from .scenes import TypingScene
    from .typing_plan import build_plan

    cfg = Config.load(args.config)
    q = load_question(args.question)
    fonts = FontBook(cfg.fonts_path, cfg.mono_font, cfg.ui_font)
    plan = build_plan(q.code, duration=10.0, seed=q.id)
    scene = TypingScene(cfg, fonts, q, plan, duration=12.0, lead=0.0)
    frac = max(0.0, min(1.0, args.at))
    img = scene.render(t=plan.duration * frac + 0.001)
    out = Path(args.out or (cfg.output_path / f"{q.id}-preview.png"))
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    print(f"wrote {out}  (font: {fonts.mono_family}, size {scene.ide.layout.fs})")
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
            print(f"  {q.id:<24} {q.difficulty:<7} {q.title}")
        except SystemExit as e:
            print(f"  {p.name:<24} !! {e}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="johncodes", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="render a Short (or all of them)")
    b.add_argument("question", nargs="?", help="path to a question .json")
    b.add_argument("--all", action="store_true", help="build every question")
    b.add_argument("--content", default="content/questions")
    b.add_argument("--keep", action="store_true", help="keep intermediate files")
    _add_config_arg(b)
    b.set_defaults(func=cmd_build)

    p = sub.add_parser("preview", help="render one still PNG of the IDE typing scene")
    p.add_argument("question")
    p.add_argument("--at", type=float, default=0.6, help="progress fraction 0..1 (default 0.6)")
    p.add_argument("--out")
    _add_config_arg(p)
    p.set_defaults(func=cmd_preview)

    t = sub.add_parser("tts", help="synthesise a line of narration to wav")
    t.add_argument("text")
    t.add_argument("out")
    t.add_argument("--voice")
    _add_config_arg(t)
    t.set_defaults(func=cmd_tts)

    ls = sub.add_parser("list", help="list discovered questions")
    ls.add_argument("--content", default="content/questions")
    ls.set_defaults(func=cmd_list)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\ninterrupted")
        return 130


if __name__ == "__main__":
    sys.exit(main())
