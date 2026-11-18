"""Scenes compiled from a question's segment list.

Auto scenes:  TitleCard ............. from title / prompt / difficulty / topic
              ExplainCard .......... from complexity + the takeaway-beat narration
Segment scenes:
  code       -> TypingScene   (types from the previous buffer to this one)
  terminal   -> TerminalScene (PyCharm Run panel slides up, command runs)
  card_topic -> TopicCard
  card_question -> QuestionCard
  narration  -> voiceover attached to the next code/terminal/card scene, or a
                standalone hold if nothing follows
"""
from __future__ import annotations

import re

from PIL import Image, ImageDraw

from . import theme
from .fonts import FontBook
from .highlight import Line, highlight_python, prefix
from .ide import STATUS_H, IDE
from .question import Question, ReplLine
from .typing_plan import TypingPlan, build_plan
from .util import ease_out_cubic, wrap_text


# --------------------------------------------------------------------------- base
class Scene:
    duration: float
    narration_audio = None          # np.ndarray | None, filled by the pipeline
    narration_offset: float = 0.3   # seconds into the scene the voice starts

    def render(self, t: float) -> Image.Image:  # pragma: no cover
        raise NotImplementedError


def _tri(d, x, cy, h, color):
    d.polygon([(x, cy - h / 2), (x, cy + h / 2), (x + h * 0.88, cy)], fill=color)


def _lc(s: str | None) -> str:
    """Card BODY text (titles, questions, answers, subtitles, recap points,
    verdicts) renders lowercase — the channel's house style.
    (Code inside code/terminal/repl/gotcha/compare panels is never touched.)"""
    return s.lower() if s else ""


def _uc(s: str | None) -> str:
    """Card LABEL text — the little kicker over a card ("RECAP", "QUICK CHECK",
    "BASIC PYTHON · EPISODE 1 / 15", "THE TAKEAWAY", panel badges, "NEXT") —
    renders uppercase."""
    return s.upper() if s else ""


def _next_label(s: str | None) -> str:
    """Recap card's 'what's next' line. "EP 3 — Strings, ..." renders as
    "EP 3 — Strings, string methods & f-strings" — EP uppercase, the episode
    title capitalised on its first letter, everything after that lowercase."""
    if not s:
        return ""
    m = re.match(r"^\s*ep\s*(\d+)\s*[—–-]\s*(.+)$", s.strip(), re.I)
    if not m:
        return _lc(s)
    num, title = m.group(1), m.group(2).strip().lower()
    title = title[:1].upper() + title[1:]
    return f"EP {num} — {title}"


def _gradient_bg(W: int, H: int) -> Image.Image:
    img = Image.new("RGB", (W, H), theme.CARD_BG)
    d = ImageDraw.Draw(img)
    a, b = theme.CARD_BG, theme.CARD_BG2
    for i in range(H):
        f = i / H
        d.line([(0, i), (W, i)], fill=(round(a[0] + (b[0] - a[0]) * f),
                                      round(a[1] + (b[1] - a[1]) * f),
                                      round(a[2] + (b[2] - a[2]) * f)))
    return img


def _pill(difficulty: str):
    return {"Easy": theme.PILL_EASY, "Medium": theme.PILL_MEDIUM,
            "Hard": theme.PILL_HARD}.get(difficulty, theme.PILL_MEDIUM)


def _common_prefix_len(a: str, b: str) -> int:
    n = 0
    for ca, cb in zip(a, b):
        if ca != cb:
            break
        n += 1
    return n


# --------------------------------------------------------------------------- title
class TitleCard(Scene):
    def __init__(self, cfg, fonts: FontBook, q: Question, duration: float):
        self.cfg, self.fonts, self.q, self.duration = cfg, fonts, q, duration
        self._bg = _gradient_bg(cfg.width, cfg.height)

    def render(self, t: float) -> Image.Image:
        W, H = self.cfg.width, self.cfg.height
        img = self._bg.copy()
        d = ImageDraw.Draw(img)
        dy = int((1 - ease_out_cubic(min(1.0, t / 0.5))) * 34)

        title_font = self.fonts.ui(118, bold=True)
        title_lines = wrap_text(_lc(self.q.title), title_font, W * 0.8)
        pf = self.fonts.ui(38)
        prompt_lines = wrap_text(_lc(self.q.prompt), pf, W * 0.66)[:3]

        kh, th, gap1, ph, gap2, pmh = 40, 132, 44, 60, 52, 50
        block_h = kh + gap1 + len(title_lines) * th + gap1 + ph + gap2 + len(prompt_lines) * pmh
        y = (H - block_h) / 2 - 20 + dy

        kicker = self.fonts.ui(38, bold=True)
        ktext = getattr(self.q, "kicker", None) or "PYTHON   ·   INTERVIEW"
        d.text(((W - d.textlength(ktext, font=kicker)) / 2, y), ktext, font=kicker, fill=theme.ACCENT)
        y += kh + gap1
        for ln in title_lines:
            d.text(((W - d.textlength(ln, font=title_font)) / 2, y), ln,
                   font=title_font, fill=theme.CARD_FG)
            y += th
        y += gap1

        pill_font = self.fonts.ui(30, bold=True)
        label = _uc(self.q.difficulty)
        pw = d.textlength(label, font=pill_font)
        topic_font = self.fonts.ui(30)
        topic = _lc(self.q.topic)
        tw = d.textlength(topic, font=topic_font)
        gap = 26
        x = (W - (pw + 52 + gap + tw)) / 2
        d.rounded_rectangle([x, y, x + pw + 52, y + 54], radius=27, fill=_pill(self.q.difficulty))
        d.text((x + 26, y + 10), label, font=pill_font, fill=(18, 22, 18))
        d.text((x + pw + 52 + gap, y + 11), topic, font=topic_font, fill=theme.CARD_MUTED)
        y += ph + gap2

        for ln in prompt_lines:
            d.text(((W - d.textlength(ln, font=pf)) / 2, y), ln, font=pf, fill=theme.CARD_MUTED)
            y += pmh
        return img


# -------------------------------------------------------------------------- typing
class TypingScene(Scene):
    def __init__(self, cfg, fonts: FontBook, q: Question, *, start_code: str,
                 end_code: str, duration: float, lead: float, seed: str):
        self.cfg, self.fonts, self.q = cfg, fonts, q
        self.duration, self.lead = duration, lead
        self.end_code = end_code
        self.n0 = _common_prefix_len(start_code, end_code)
        self.full_lines: list[Line] = highlight_python(end_code)
        self.total_lines = len(self.full_lines)
        self.ide = IDE(
            cfg, fonts, filename=q.filename, project=cfg.project_name,
            python_label=cfg.python_label, n_code_lines=self.total_lines,
            max_line_len=max((len(x) for x in end_code.split("\n")), default=0),
            code=end_code,
        )
        tail = end_code[self.n0:]
        # natural fixed-speed typing — finishes when it finishes, does NOT
        # stretch (or shrink) to fit the narration.
        self.plan: TypingPlan = build_plan(
            tail or " ", cps=cfg.typing_cps, newline_pause=cfg.typing_newline_pause,
            seed=seed)

    def render(self, t: float) -> Image.Image:
        typed_t = max(0.0, t - self.lead)
        n = self.n0 + (self.plan.revealed_at(typed_t) if typed_t > 0 else 0)
        n = min(n, len(self.end_code))
        spans, caret = prefix(self.full_lines, n)
        done = n >= len(self.end_code)
        return self.ide.render(spans, caret, t, total_lines=self.total_lines,
                               show_caret=not done or (t % 1.06) < 0.62)

    def keystroke_times(self, scene_start: float) -> list[float]:
        base = scene_start + self.lead
        return [base + ct for ct in self.plan.click_times]


# ------------------------------------------------------------------------ terminal
class TerminalScene(Scene):
    SLIDE = 0.32

    def __init__(self, cfg, fonts: FontBook, q: Question, *, code: str,
                 command: str, output: str, duration: float, lead: float, seed: str):
        self.cfg, self.fonts, self.q = cfg, fonts, q
        self.duration, self.lead = duration, lead
        self.command = command
        self.output_lines = output.split("\n") if output else []
        self.full_lines = highlight_python(code) if code else [[]]
        self.total_lines = len(self.full_lines)
        self.ide = IDE(
            cfg, fonts, filename=q.filename, project=cfg.project_name,
            python_label=cfg.python_label, n_code_lines=self.total_lines,
            max_line_len=max((len(x) for x in code.split("\n")), default=0),
            code=code,
        )
        self._editor = self.ide.render(prefix(self.full_lines, len(code))[0], None, 0.0,
                                       total_lines=self.total_lines, show_caret=False)
        self._dock = self.ide.code_block_bottom(self.total_lines) + 10
        self.cmd_type = min(1.6, 0.05 * len(command) + 0.4)
        self.out_stream = 0.9

    def _phase(self, t: float):
        s = self.SLIDE
        slide = min(1.0, t / s)
        after = max(0.0, t - s)
        cmd_chars = None
        if after < self.cmd_type:
            cmd_chars = int(len(self.command) * (after / max(self.cmd_type, 1e-3)))
        vis_out = 0
        finished = False
        if after >= self.cmd_type:
            oa = after - self.cmd_type - 0.25
            if oa > 0 and self.output_lines:
                vis_out = min(len(self.output_lines),
                              1 + int(len(self.output_lines) * oa / self.out_stream))
            else:
                vis_out = 0
            if oa > self.out_stream + 0.2:
                finished = True
        return slide, cmd_chars, vis_out, finished

    def render(self, t: float) -> Image.Image:
        img = self._editor.copy()
        slide, cmd_chars, vis_out, finished = self._phase(t)
        self.ide.draw_run_panel(
            img, command=self.command, output_lines=self.output_lines[:vis_out],
            finished=finished, slide=slide, cmd_chars=cmd_chars,
            run_name=self.ide.module, docked_top=self._dock,
        )
        return img

    def keystroke_times(self, scene_start: float) -> list[float]:
        base = scene_start + self.SLIDE
        n = len(self.command.replace(" ", ""))
        if n == 0:
            return []
        return [base + self.cmd_type * i / n for i in range(n)]


# --------------------------------------------------------------------------- cards
class TopicCard(Scene):
    def __init__(self, cfg, fonts: FontBook, title: str, subtitle: str | None,
                 duration: float):
        self.cfg, self.fonts, self.duration = cfg, fonts, duration
        self.title, self.subtitle = title, subtitle
        self._bg = _gradient_bg(cfg.width, cfg.height)

    def render(self, t: float) -> Image.Image:
        W, H = self.cfg.width, self.cfg.height
        img = self._bg.copy()
        d = ImageDraw.Draw(img)
        dy = int((1 - ease_out_cubic(min(1.0, t / 0.5))) * 30)
        tf = self.fonts.ui(96, bold=True)
        lines = wrap_text(_lc(self.title), tf, W * 0.78)
        sf = self.fonts.ui(40)
        subs = wrap_text(_lc(self.subtitle), sf, W * 0.62) if self.subtitle else []
        block = len(lines) * 108 + (40 + len(subs) * 52 if subs else 0)
        y = (H - block) / 2 - 10 + dy
        # accent rule
        d.rectangle([(W - 90) / 2, y - 40, (W + 90) / 2, y - 34], fill=theme.ACCENT_ORANGE)
        for ln in lines:
            d.text(((W - d.textlength(ln, font=tf)) / 2, y), ln, font=tf, fill=theme.CARD_FG)
            y += 108
        if subs:
            y += 40
            for ln in subs:
                d.text(((W - d.textlength(ln, font=sf)) / 2, y), ln, font=sf, fill=theme.CARD_MUTED)
                y += 52
        return img


class QuestionCard(Scene):
    """Quick check. The question shows (and is read: "Quick check. <question>"),
    then sits for ``reveal_at`` seconds, then the answer appears and is read too.
    Pipeline supplies the two narration clips and their timing.
    """

    def __init__(self, cfg, fonts: FontBook, question: str, answer: str | None,
                 duration: float, reveal_at: float):
        self.cfg, self.fonts, self.duration = cfg, fonts, duration
        self.question, self.answer = question, answer
        self.reveal_at = reveal_at if answer else duration + 1
        self._bg = _gradient_bg(cfg.width, cfg.height)

    def render(self, t: float) -> Image.Image:
        W, H = self.cfg.width, self.cfg.height
        img = self._bg.copy()
        d = ImageDraw.Draw(img)
        dy = int((1 - ease_out_cubic(min(1.0, t / 0.5))) * 28)

        qf = self.fonts.ui(62, bold=True)
        qlines = wrap_text(_lc(self.question), qf, W * 0.74)
        af = self.fonts.ui(48, bold=True)
        alines = wrap_text(_lc(self.answer), af, W * 0.72) if self.answer else []
        block = 56 + len(qlines) * 80 + (72 + len(alines) * 60 if alines else 0)
        y = (H - block) / 2 - 10 + dy

        kicker = self.fonts.ui(34, bold=True)
        kt = "QUICK CHECK"
        d.text(((W - d.textlength(kt, font=kicker)) / 2, y), kt, font=kicker, fill=theme.ACCENT_ORANGE)
        y += 56
        for ln in qlines:
            d.text(((W - d.textlength(ln, font=qf)) / 2, y), ln, font=qf, fill=theme.CARD_FG)
            y += 80

        if alines and t >= self.reveal_at:
            a = ease_out_cubic(min(1.0, (t - self.reveal_at) / 0.4))
            y += 72
            d.line([(W * 0.30, y - 36), (W * 0.70, y - 36)], fill=theme.BORDER_LT, width=2)
            for ln in alines:
                col = tuple(round(theme.CARD_BG[i] + (theme.GOOD[i] - theme.CARD_BG[i]) * a)
                            for i in range(3))
                d.text(((W - d.textlength(ln, font=af)) / 2, y), ln, font=af, fill=col)
                y += 60
        return img


class ExplainCard(Scene):
    def __init__(self, cfg, fonts: FontBook, q: Question, duration: float):
        self.cfg, self.fonts, self.q, self.duration = cfg, fonts, q, duration
        self._bg = _gradient_bg(cfg.width, cfg.height)

    def render(self, t: float) -> Image.Image:
        W, H = self.cfg.width, self.cfg.height
        img = self._bg.copy()
        d = ImageDraw.Draw(img)
        dy = int((1 - ease_out_cubic(min(1.0, t / 0.5))) * 30)

        take = _lc(self.q.narration_beat("takeaway"))
        tf = self.fonts.ui(48, bold=True)
        take_lines = wrap_text(take, tf, W * 0.66) if take else []
        kh, gap1, chip_h, gap2, lh = 40, 52, 160, 70, 66
        block_h = kh + gap1 + chip_h + (gap2 + len(take_lines) * lh if take_lines else 40)
        y = (H - block_h) / 2 - 40 + dy

        kicker = self.fonts.ui(38, bold=True)
        kt = "THE TAKEAWAY"
        d.text(((W - d.textlength(kt, font=kicker)) / 2, y), kt, font=kicker, fill=theme.ACCENT_GREEN)
        y += kh + gap1

        val_font = self.fonts.ui(56, bold=True)
        label_font = self.fonts.ui(25, bold=True)
        chips = [("TIME", self.q.complexity.time), ("SPACE", self.q.complexity.space)]
        chip_w, gap = 420, 44
        x0 = (W - (chip_w * 2 + gap)) / 2
        for i, (lab, val) in enumerate(chips):
            cx = x0 + i * (chip_w + gap)
            d.rounded_rectangle([cx, y, cx + chip_w, y + chip_h], radius=22,
                                fill=theme.CARD_BG2, outline=theme.BORDER, width=2)
            d.text((cx + (chip_w - d.textlength(lab, font=label_font)) / 2, y + 30), lab,
                   font=label_font, fill=theme.CARD_MUTED)
            d.text((cx + (chip_w - d.textlength(val, font=val_font)) / 2, y + 70), val,
                   font=val_font, fill=theme.ACCENT_ORANGE)
        y += chip_h + gap2

        for ln in take_lines:
            d.text(((W - d.textlength(ln, font=tf)) / 2, y), ln, font=tf, fill=theme.CARD_FG)
            y += lh

        cta = self.fonts.ui(34, bold=True)
        ct = "follow for daily python interview prep"   # body text — stays lowercase
        cw = d.textlength(ct, font=cta)
        fy = H * 0.84
        _tri(d, (W - cw) / 2 - 46, fy + 22, 32, theme.ACCENT)
        d.text(((W - cw) / 2, fy), ct, font=cta, fill=theme.ACCENT)
        return img


# ================================================================ course scenes
def _fit_mono(fonts: FontBook, code_lines: list[str], max_w: float, hi=34, lo=17) -> int:
    longest = max((len(x) for x in code_lines), default=1)
    for fs in range(hi, lo - 1, -1):
        if fonts.mono(fs).char_w * longest <= max_w:
            return fs
    return lo


def _panel_height(fonts: FontBook, code: str, w: float) -> float:
    lines = code.split("\n")
    fs = _fit_mono(fonts, lines, w - 2 * 24 - 46)
    return 30 + len(lines) * fonts.mono(fs).line_h + 26


def _code_panel(img: Image.Image, fonts: FontBook, x: float, y: float, w: float, h: float,
                code: str, *, label: str | None = None, label_color=None, reveal: float = 1.0):
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([x, y, x + w, y + h], radius=14, fill=theme.EDITOR_BG,
                        outline=theme.BORDER_LT, width=2)
    if label:
        lf = fonts.ui(22, bold=True)
        lw = d.textlength(label, font=lf) + 34
        d.rounded_rectangle([x + 18, y - 23, x + 18 + lw, y + 23], radius=22,
                            fill=theme.CARD_BG, outline=label_color or theme.BORDER_LT, width=2)
        d.text((x + 35, y - 13), label, font=lf, fill=label_color or theme.FG_DEFAULT)
    text_lines = code.split("\n")
    pad = 24
    fs = _fit_mono(fonts, text_lines, w - 2 * pad - 46)
    mono = fonts.mono(fs)
    hl = highlight_python(code)
    if reveal < 1.0:
        hl, _ = prefix(hl, int(len(code) * reveal))
    cy = y + 30
    for i, ln in enumerate(hl):
        if cy + mono.line_h > y + h - 8:
            break
        d.text((x + pad, cy), str(i + 1), font=mono.regular, fill=theme.LINE_NUMBER)
        xx = x + pad + 46
        for sp in ln:
            d.text((xx, cy), sp.text, font=mono.pick(italic=sp.italic), fill=sp.color)
            xx += mono.char_w * len(sp.text)
        cy += mono.line_h


class EpisodeCard(Scene):
    def __init__(self, cfg, fonts: FontBook, q: Question, duration: float):
        self.cfg, self.fonts, self.q, self.duration = cfg, fonts, q, duration
        self._bg = _gradient_bg(cfg.width, cfg.height)

    def render(self, t: float) -> Image.Image:
        W, H = self.cfg.width, self.cfg.height
        ep = self.q.episode
        img = self._bg.copy()
        d = ImageDraw.Draw(img)
        dy = int((1 - ease_out_cubic(min(1.0, t / 0.5))) * 34)

        tf = self.fonts.ui(120, bold=True)
        tlines = wrap_text(_lc(self.q.title), tf, W * 0.82)
        lf = self.fonts.ui(37)
        llines = wrap_text(_lc(self.q.prompt), lf, W * 0.62)[:2]
        block = 44 + 46 + len(tlines) * 132 + 60 + 40 + len(llines) * 50 + 70
        y = (H - block) / 2 - 10 + dy

        kicker = self.fonts.ui(37, bold=True)
        kt = f"{_uc(ep.series)}   ·   EPISODE {ep.number} / {ep.of}"
        d.text(((W - d.textlength(kt, font=kicker)) / 2, y), kt, font=kicker, fill=theme.ACCENT)
        y += 44 + 46
        for ln in tlines:
            d.text(((W - d.textlength(ln, font=tf)) / 2, y), ln, font=tf, fill=theme.CARD_FG)
            y += 132
        y += 44
        d.rectangle([(W - 120) / 2, y, (W + 120) / 2, y + 6], fill=theme.ACCENT_ORANGE)
        y += 46
        for ln in llines:
            d.text(((W - d.textlength(ln, font=lf)) / 2, y), ln, font=lf, fill=theme.CARD_MUTED)
            y += 50
        # progress dots
        y += 46
        n, r, gap = ep.of, 7, 22
        x0 = (W - (n - 1) * gap) / 2
        for i in range(n):
            cx = x0 + i * gap
            fill = theme.ACCENT if i < ep.number else theme.BORDER_LT
            d.ellipse([cx - r, y - r, cx + r, y + r], fill=fill)
        return img


class RecapCard(Scene):
    """Each recap point appears exactly as the teacher reads it out.

    ``reveal_times[i]`` is when point i's narration starts (pipeline computes it
    from the per-point TTS durations). ``next_up`` shows once the last point is
    on screen.
    """

    def __init__(self, cfg, fonts: FontBook, points: list[str], next_up: str | None,
                 duration: float, reveal_times: list[float]):
        self.cfg, self.fonts, self.duration = cfg, fonts, duration
        self.points, self.next_up = points, next_up
        self.reveal_times = reveal_times
        self._bg = _gradient_bg(cfg.width, cfg.height)

    def render(self, t: float) -> Image.Image:
        W, H = self.cfg.width, self.cfg.height
        img = self._bg.copy()
        d = ImageDraw.Draw(img)
        dy = int((1 - ease_out_cubic(min(1.0, t / 0.5))) * 30)

        bf = self.fonts.ui(44, bold=True)
        wrapped = [wrap_text(_lc(p), bf, W * 0.7) for p in self.points]
        rows = sum(len(w) for w in wrapped)
        block = 44 + 60 + rows * 56 + len(self.points) * 26 + (130 if self.next_up else 0)
        y = (H - block) / 2 - 30 + dy

        kicker = self.fonts.ui(38, bold=True)
        d.text(((W - d.textlength("RECAP", font=kicker)) / 2, y), "RECAP",
               font=kicker, fill=theme.ACCENT_GREEN)
        y += 60 + 20

        shown = sum(1 for rt in self.reveal_times if t >= rt)
        lx = W * 0.15
        for i, wlines in enumerate(wrapped):
            if i >= shown:
                break
            a = ease_out_cubic(min(1.0, (t - self.reveal_times[i]) / 0.35))
            d.ellipse([lx, y + 14, lx + 13, y + 27], fill=theme.ACCENT_ORANGE)
            for ln in wlines:
                col = tuple(round(theme.CARD_BG[k] + (theme.CARD_FG[k] - theme.CARD_BG[k]) * a)
                            for k in range(3))
                d.text((lx + 32, y), ln, font=bf, fill=col)
                y += 56
            y += 26

        if self.next_up and shown >= len(self.points):
            for wl in wrapped[shown:]:
                y += len(wl) * 56 + 26
            y += 46
            nf = self.fonts.ui(32, bold=True)
            nt = f"NEXT  ·  {_next_label(self.next_up)}"
            _tri(d, (W - d.textlength(nt, font=nf)) / 2 - 44, y + 20, 30, theme.ACCENT)
            d.text(((W - d.textlength(nt, font=nf)) / 2, y), nt, font=nf, fill=theme.ACCENT)
        return img


class ReplScene(Scene):
    def __init__(self, cfg, fonts: FontBook, lines: list[ReplLine], duration: float,
                 lead: float):
        self.cfg, self.fonts, self.duration, self.lead = cfg, fonts, duration, lead
        self.lines = lines
        self._bg = _gradient_bg(cfg.width, cfg.height)
        self.fs = _fit_mono(fonts, [ln.input for ln in lines] + sum(
            ([o for o in (ln.output or "").split("\n")] for ln in lines), []),
            cfg.width * 0.8, hi=34, lo=20)
        span = max(0.1, duration - lead - 0.6)
        self.slot = span / max(len(lines), 1)

    def _visible(self, t: float):
        tt = max(0.0, t - self.lead)
        out = []
        for i, ln in enumerate(self.lines):
            start = i * self.slot
            if tt < start:
                break
            local = tt - start
            type_time = min(self.slot * 0.5, 0.045 * len(ln.input) + 0.25)
            nin = len(ln.input) if local >= type_time else int(len(ln.input) * local / max(type_time, 1e-3))
            show_out = local >= type_time + 0.15
            out.append((ln.input[:nin], ln.output if show_out else None))
        return out

    def render(self, t: float) -> Image.Image:
        W, H = self.cfg.width, self.cfg.height
        img = self._bg.copy()
        d = ImageDraw.Draw(img)
        mono = self.fonts.mono(self.fs)
        lh = mono.line_h
        head_h = 48

        # size the console box to the full session, centred vertically
        total_rows = sum(1 + (len(l.output.split("\n")) if l.output else 0)
                         for l in self.lines)
        box_h = min(H - 140, head_h + 40 + total_rows * lh)
        box_w = W - 140
        bx, by = 70, (H - box_h) // 2

        d.rounded_rectangle([bx, by, bx + box_w, by + box_h], radius=18, fill=theme.EDITOR_BG,
                            outline=theme.BORDER_LT, width=2)
        d.rectangle([bx, by, bx + box_w, by + head_h], fill=theme.PANEL_BG)
        for i, c in enumerate((theme.TRAFFIC_RED, theme.TRAFFIC_YELLOW, theme.TRAFFIC_GREEN)):
            d.ellipse([bx + 22 + i * 22 - 6, by + 24 - 6, bx + 22 + i * 22 + 6, by + 24 + 6], fill=c)
        d.text((bx + 100, by + 14), f"{self.cfg.python_label} Console",
               font=self.fonts.ui(20), fill=theme.TITLE_FG)

        x, y = bx + 40, by + head_h + 22
        for inp, outp in self._visible(t):
            d.text((x, y), ">>> ", font=mono.regular, fill=theme.CONSOLE_PROMPT)
            d.text((x + mono.char_w * 4, y), inp, font=mono.regular, fill=theme.FG_DEFAULT)
            y += lh
            if outp:   # an assignment / statement with no result prints nothing
                for oln in outp.split("\n"):
                    d.text((x, y), oln, font=mono.regular, fill=theme.CONSOLE_OUT)
                    y += lh
            if y > by + box_h - lh:
                break
        return img

    def keystroke_times(self, scene_start: float) -> list[float]:
        base = scene_start + self.lead
        out = []
        for i, ln in enumerate(self.lines):
            tt = min(self.slot * 0.5, 0.045 * len(ln.input) + 0.25)
            k = len(ln.input.replace(" ", ""))
            out += [base + i * self.slot + tt * j / max(k, 1) for j in range(k)]
        return out


class GotchaScene(Scene):
    SLIDE = 0.3

    def __init__(self, cfg, fonts: FontBook, q: Question, *, code: str, bad_line: int | None,
                 error: str, duration: float, lead: float):
        self.cfg, self.fonts, self.duration, self.lead = cfg, fonts, duration, lead
        self.error_lines = error.split("\n") if error else []
        self.bad_line = bad_line
        self.full_lines = highlight_python(code)
        self.total_lines = len(self.full_lines)
        self.ide = IDE(cfg, fonts, filename=q.filename, project=cfg.project_name,
                       python_label=cfg.python_label, n_code_lines=self.total_lines,
                       max_line_len=max((len(x) for x in code.split("\n")), default=0), code=code)
        self._editor = self.ide.render(prefix(self.full_lines, len(code))[0], None, 0.0,
                                       total_lines=self.total_lines, show_caret=False,
                                       error_line=bad_line)
        self._dock = self.ide.code_block_bottom(self.total_lines) + 10

    def render(self, t: float) -> Image.Image:
        img = self._editor.copy()
        slide = min(1.0, t / self.SLIDE)
        after = max(0.0, t - self.SLIDE)
        n = min(len(self.error_lines), 1 + int(len(self.error_lines) * after / 0.9)) \
            if self.error_lines else 0
        finished = after > 1.2
        self.ide.draw_run_panel(img, command="python solution.py",
                                output_lines=self.error_lines[:n], finished=finished,
                                slide=slide, run_name=self.ide.module,
                                docked_top=self._dock, error=True)
        return img


class CompareScene(Scene):
    def __init__(self, cfg, fonts: FontBook, *, left_label, left_code, right_label,
                 right_code, verdict, duration: float):
        self.cfg, self.fonts, self.duration = cfg, fonts, duration
        self.left = (left_label, left_code)
        self.right = (right_label, right_code)
        self.verdict = verdict
        self._bg = _gradient_bg(cfg.width, cfg.height)

    def render(self, t: float) -> Image.Image:
        W, H = self.cfg.width, self.cfg.height
        img = self._bg.copy()
        d = ImageDraw.Draw(img)
        appear = ease_out_cubic(min(1.0, t / 0.5))

        pw = W * 0.42
        gap = W * 0.06
        x0 = (W - (pw * 2 + gap)) / 2
        ph = max(_panel_height(self.fonts, self.left[1], pw),
                 _panel_height(self.fonts, self.right[1], pw))
        vf = self.fonts.ui(38, bold=True)
        vlines = wrap_text(_lc(self.verdict), vf, W * 0.82) if self.verdict else []
        block = 46 + ph + (60 + len(vlines) * 50 if vlines else 0)
        top = (H - block) / 2 + 46 + int((1 - appear) * 18)

        for i, (label, code) in enumerate((self.left, self.right)):
            x = x0 + i * (pw + gap)
            col = theme.BAD if i == 0 else theme.GOOD
            _code_panel(img, self.fonts, x, top, pw, ph, code,
                        label=_uc(label) or None, label_color=col)

        if vlines:
            vy = top + ph + 60
            for ln in vlines:
                d.text(((W - d.textlength(ln, font=vf)) / 2, vy), ln, font=vf, fill=theme.CARD_FG)
                vy += 50
        return img
