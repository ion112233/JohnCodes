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

from PIL import Image, ImageDraw

from . import theme
from .fonts import FontBook
from .highlight import Line, highlight_python, prefix
from .ide import STATUS_H, IDE
from .question import Question
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
        title_lines = wrap_text(self.q.title, title_font, W * 0.8)
        pf = self.fonts.ui(38)
        prompt_lines = wrap_text(self.q.prompt, pf, W * 0.66)[:3]

        kh, th, gap1, ph, gap2, pmh = 40, 132, 44, 60, 52, 50
        block_h = kh + gap1 + len(title_lines) * th + gap1 + ph + gap2 + len(prompt_lines) * pmh
        y = (H - block_h) / 2 - 20 + dy

        kicker = self.fonts.ui(38, bold=True)
        ktext = "PYTHON   ·   INTERVIEW"
        d.text(((W - d.textlength(ktext, font=kicker)) / 2, y), ktext, font=kicker, fill=theme.ACCENT)
        y += kh + gap1
        for ln in title_lines:
            d.text(((W - d.textlength(ln, font=title_font)) / 2, y), ln,
                   font=title_font, fill=theme.CARD_FG)
            y += th
        y += gap1

        pill_font = self.fonts.ui(30, bold=True)
        label = self.q.difficulty.upper()
        pw = d.textlength(label, font=pill_font)
        topic_font = self.fonts.ui(30)
        tw = d.textlength(self.q.topic, font=topic_font)
        gap = 26
        x = (W - (pw + 52 + gap + tw)) / 2
        d.rounded_rectangle([x, y, x + pw + 52, y + 54], radius=27, fill=_pill(self.q.difficulty))
        d.text((x + 26, y + 10), label, font=pill_font, fill=(18, 22, 18))
        d.text((x + pw + 52 + gap, y + 11), self.q.topic, font=topic_font, fill=theme.CARD_MUTED)
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
        self.plan: TypingPlan = build_plan(tail or " ", max(0.8, duration - lead - 0.8), seed=seed)

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
        lines = wrap_text(self.title, tf, W * 0.78)
        sf = self.fonts.ui(40)
        subs = wrap_text(self.subtitle, sf, W * 0.62) if self.subtitle else []
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
    def __init__(self, cfg, fonts: FontBook, question: str, answer: str | None,
                 duration: float):
        self.cfg, self.fonts, self.duration = cfg, fonts, duration
        self.question, self.answer = question, answer
        self._bg = _gradient_bg(cfg.width, cfg.height)
        self.reveal_at = min(duration * 0.55, duration - 1.6) if answer else duration + 1

    def render(self, t: float) -> Image.Image:
        W, H = self.cfg.width, self.cfg.height
        img = self._bg.copy()
        d = ImageDraw.Draw(img)
        dy = int((1 - ease_out_cubic(min(1.0, t / 0.5))) * 28)

        qf = self.fonts.ui(64, bold=True)
        qlines = wrap_text(self.question, qf, W * 0.74)
        af = self.fonts.ui(48, bold=True)
        alines = wrap_text(self.answer, af, W * 0.72) if self.answer else []
        block = 60 + len(qlines) * 82 + (70 + len(alines) * 60 if alines else 0)
        y = (H - block) / 2 - 10 + dy

        kicker = self.fonts.ui(34, bold=True)
        kt = "QUICK CHECK"
        d.text(((W - d.textlength(kt, font=kicker)) / 2, y), kt, font=kicker, fill=theme.ACCENT_ORANGE)
        y += 60
        for ln in qlines:
            d.text(((W - d.textlength(ln, font=qf)) / 2, y), ln, font=qf, fill=theme.CARD_FG)
            y += 82

        if alines and t >= self.reveal_at:
            a = ease_out_cubic(min(1.0, (t - self.reveal_at) / 0.4))
            y += 70
            d.line([(W * 0.30, y - 34), (W * 0.70, y - 34)], fill=theme.BORDER_LT, width=2)
            for ln in alines:
                col = tuple(round(theme.CARD_BG[i] + (theme.ACCENT_GREEN[i] - theme.CARD_BG[i]) * a)
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

        take = self.q.narration_beat("takeaway") or ""
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
        ct = "follow for daily Python interview prep"
        cw = d.textlength(ct, font=cta)
        fy = H * 0.84
        _tri(d, (W - cw) / 2 - 46, fy + 22, 32, theme.ACCENT)
        d.text(((W - cw) / 2, fy), ct, font=cta, fill=theme.ACCENT)
        return img
