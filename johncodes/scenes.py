"""Scenes: title card -> full-screen IDE typing -> takeaway card (16:9)."""
from __future__ import annotations

from PIL import Image, ImageDraw

from . import theme
from .fonts import FontBook
from .highlight import Line, highlight_python, prefix
from .ide import STATUS_H, IDE
from .question import Question
from .typing_plan import TypingPlan
from .util import ease_out_cubic, split_sentences, wrap_text


class Scene:
    duration: float

    def render(self, t: float) -> Image.Image:  # pragma: no cover - interface
        raise NotImplementedError


def _tri(d: ImageDraw.ImageDraw, x: float, cy: float, h: float, color) -> None:
    """A right-pointing 'play' triangle (used instead of a ▶ glyph)."""
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


def _pill_color(difficulty: str):
    return {"Easy": theme.PILL_EASY, "Medium": theme.PILL_MEDIUM,
            "Hard": theme.PILL_HARD}.get(difficulty, theme.PILL_MEDIUM)


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

        pill_font = self.fonts.ui(32, bold=True)
        label = self.q.difficulty.upper()
        pw = d.textlength(label, font=pill_font)
        topic_font = self.fonts.ui(32)
        tw = d.textlength(self.q.topic, font=topic_font)
        gap = 26
        x = (W - (pw + 52 + gap + tw)) / 2
        d.rounded_rectangle([x, y, x + pw + 52, y + 54], radius=27, fill=_pill_color(self.q.difficulty))
        d.text((x + 26, y + 10), label, font=pill_font, fill=(18, 22, 18))
        d.text((x + pw + 52 + gap, y + 11), self.q.topic, font=topic_font, fill=theme.CARD_MUTED)
        y += ph + gap2

        for ln in prompt_lines:
            d.text(((W - d.textlength(ln, font=pf)) / 2, y), ln, font=pf, fill=theme.CARD_MUTED)
            y += pmh
        return img


# -------------------------------------------------------------------------- typing
class TypingScene(Scene):
    def __init__(self, cfg, fonts: FontBook, q: Question, plan: TypingPlan,
                 duration: float, lead: float):
        self.cfg, self.fonts, self.q, self.plan = cfg, fonts, q, plan
        self.duration, self.lead = duration, lead
        self.full_lines: list[Line] = highlight_python(q.code)
        self.total_lines = len(self.full_lines)
        self.ide = IDE(
            cfg, fonts, filename=q.filename, project=cfg.project_name,
            python_label=cfg.python_label,
            n_code_lines=self.total_lines, max_line_len=q.max_line_len,
            code=q.code,
        )
        self._caps = self._segment_captions(q.narration.walkthrough)

    def _segment_captions(self, text: str):
        sents = split_sentences(text)
        weights = [max(len(s), 1) for s in sents]
        tot = sum(weights)
        out, acc = [], 0.0
        span = max(0.1, self.duration - self.lead)
        for s, w in zip(sents, weights):
            start = self.lead + span * acc / tot
            acc += w
            out.append((start, self.lead + span * acc / tot, s))
        return out

    def _draw_caption(self, img: Image.Image, t: float) -> None:
        if not self.cfg.captions:
            return
        text = next((s for a, b, s in self._caps if a <= t < b), None)
        if not text:
            return
        W, H = self.cfg.width, self.cfg.height
        d = ImageDraw.Draw(img, "RGBA")
        font = self.fonts.ui(40, bold=True)
        lines = wrap_text(text, font, W * 0.68)
        lh = 54
        box_h = lh * len(lines) + 40
        box_w = W * 0.74
        box_x = (W - box_w) / 2
        box_y = H - STATUS_H - 44 - box_h
        d.rounded_rectangle([box_x, box_y, box_x + box_w, box_y + box_h],
                            radius=22, fill=(0, 0, 0, 180))
        y = box_y + 20
        for ln in lines:
            d.text(((W - d.textlength(ln, font=font)) / 2, y), ln, font=font,
                   fill=(255, 255, 255, 255))
            y += lh

    def render(self, t: float) -> Image.Image:
        typed_t = max(0.0, t - self.lead)
        n = min(self.plan.revealed_at(typed_t) if typed_t > 0 else 0, len(self.q.code))
        spans, caret = prefix(self.full_lines, n)
        done = n >= len(self.q.code)
        img = self.ide.render(spans, caret, t, total_lines=self.total_lines,
                              show_caret=not done or (t % 1.06) < 0.62)
        self._draw_caption(img, t)
        return img


# ------------------------------------------------------------------------- explain
class ExplainCard(Scene):
    def __init__(self, cfg, fonts: FontBook, q: Question, duration: float):
        self.cfg, self.fonts, self.q, self.duration = cfg, fonts, q, duration
        self._bg = _gradient_bg(cfg.width, cfg.height)

    def render(self, t: float) -> Image.Image:
        W, H = self.cfg.width, self.cfg.height
        img = self._bg.copy()
        d = ImageDraw.Draw(img)
        dy = int((1 - ease_out_cubic(min(1.0, t / 0.5))) * 30)

        tf = self.fonts.ui(52, bold=True)
        take_lines = wrap_text(self.q.narration.takeaway, tf, W * 0.66)
        kh, gap1, chip_h, gap2, lh = 40, 52, 160, 70, 66
        block_h = kh + gap1 + chip_h + gap2 + len(take_lines) * lh
        y = (H - block_h) / 2 - 40 + dy

        kicker = self.fonts.ui(38, bold=True)
        ktext = "THE TAKEAWAY"
        d.text(((W - d.textlength(ktext, font=kicker)) / 2, y), ktext,
               font=kicker, fill=theme.ACCENT_GREEN)
        y += kh + gap1

        val_font = self.fonts.ui(56, bold=True)
        label_font = self.fonts.ui(26, bold=True)
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
        ctext = "follow for daily Python interview prep"
        cw = d.textlength(ctext, font=cta)
        fy = H * 0.84
        _tri(d, (W - cw) / 2 - 46, fy + 22, 32, theme.ACCENT)
        d.text(((W - cw) / 2, fy), ctext, font=cta, fill=theme.ACCENT)
        return img
