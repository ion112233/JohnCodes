"""Scenes for the LeetCode-site layout.

LCSearch  — the problem-set page: type the title into the search box, click the hit.
LCWork    — the problem page: description panel (left, scrolls) + code editor
            (right) with paste-the-template / type-the-solution / Run + results.
Both draw the same LeetCode dark chrome (navbar, rounded panels).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from PIL import Image, ImageDraw

from . import lc_theme as C
from .fonts import FontBook
from .highlight import prefix
from .lc_doc import Doc
from .scenes import Scene, _common_prefix_len
from .typing_plan import build_plan
from .util import clamp, ease_in_out, ease_out_cubic

NAV_H = 52
GAP = 10
TOP = NAV_H + GAP
LEFT_X0, LEFT_X1 = 10, 950
RIGHT_X0, RIGHT_X1 = 960, 1910
PANEL_Y1 = 1072
BAR_H = 48
CODE_SIZE = 26


# ------------------------------------------------------------------ helpers
def _lerp(a, b, t):
    return a + (b - a) * t


def _arrow(d: ImageDraw.ImageDraw, x: float, y: float, s: float = 1.0):
    pts = [(0, 0), (0, 24), (6, 19), (10, 28), (14, 26), (10, 17), (18, 17)]
    pts = [(x + px * s, y + py * s) for px, py in pts]
    d.polygon(pts, fill=(255, 255, 255), outline=(0, 0, 0))


def _logo(d: ImageDraw.ImageDraw, x: int, y: int):
    # simplified LeetCode mark: grey chevron + orange bar + orange bracket
    d.line([(x + 6, y + 8), (x + 0, y + 15), (x + 6, y + 22)], fill=(180, 180, 180), width=3)
    d.line([(x + 12, y + 4), (x + 12, y + 26)], fill=C.ORANGE, width=4)
    d.line([(x + 16, y + 22), (x + 26, y + 22)], fill=(180, 180, 180), width=3)


def draw_nav(d: ImageDraw.ImageDraw, fonts: FontBook, active: str = "Problems"):
    d.rectangle([0, 0, 1920, NAV_H], fill=C.NAV_BG)
    _logo(d, 24, 11)
    f = fonts.ui(25, bold=True)
    d.text((62, 10), "LeetCode", font=f, fill=C.TEXT_STRONG)
    x = 222
    nf = fonts.ui(21)
    nfb = fonts.ui(21, bold=True)
    for name in ("Explore", "Problems", "Contest", "Discuss", "Interview", "Store"):
        font = nfb if name == active else nf
        d.text((x, 14), name, font=font, fill=C.TEXT_STRONG if name == active else C.MUTED)
        x += d.textlength(name, font=font) + 34
    # right side
    pf = fonts.ui(19, bold=True)
    pw = d.textlength("Premium", font=pf) + 30
    d.rounded_rectangle([1920 - 80 - pw, 10, 1920 - 80, 42], radius=8, fill=(58, 44, 20))
    d.text((1920 - 80 - pw + 15, 14), "Premium", font=pf, fill=C.ORANGE)
    d.ellipse([1920 - 58, 10, 1920 - 26, 42], fill=(70, 70, 70))
    d.ellipse([1920 - 48, 15, 1920 - 36, 27], fill=(150, 150, 150))
    d.pieslice([1920 - 53, 29, 1920 - 31, 53], 180, 360, fill=(150, 150, 150))


def _icon_code(d, x, y, col):
    d.line([(x + 6, y + 3), (x, y + 10), (x + 6, y + 17)], fill=col, width=2)
    d.line([(x + 14, y + 3), (x + 20, y + 10), (x + 14, y + 17)], fill=col, width=2)
    d.line([(x + 11, y + 1), (x + 9, y + 19)], fill=col, width=2)


# ------------------------------------------------------------------- search
@dataclass
class SearchData:
    query: str
    target_slug: str
    default_rows: list = field(default_factory=list)   # [{frontendQuestionId,title,acRate,paidOnly,difficulty}]
    results: list = field(default_factory=list)


class LCSearch(Scene):
    def __init__(self, cfg, fonts: FontBook, data: SearchData, duration: float, seed: str,
                 lead: float = 0.9):
        self.cfg, self.fonts, self.data, self.duration, self.lead = cfg, fonts, data, duration, lead
        self.plan = build_plan(data.query, cps=9.0, newline_pause=0.0, seed=seed)
        self.type_end = lead + self.plan.duration
        self.swap_at = self.type_end + 0.45
        self.click_at = self.swap_at + 1.5
        self.rows_x0, self.rows_x1 = 300, 1620
        self.row_h = 56
        self.rows_y0 = 250
        res = data.results
        self.target_idx = next((i for i, r in enumerate(res) if r["titleSlug"] == data.target_slug), 0)
        self._base = self._make_base()

    def _make_base(self):
        W, H = self.cfg.width, self.cfg.height
        img = Image.new("RGB", (W, H), C.PAGE_BG)
        d = ImageDraw.Draw(img)
        draw_nav(d, self.fonts, "Problems")
        # topic strip
        tf = self.fonts.ui(21)
        x = self.rows_x0
        for name, n in (("Array", 2281), ("String", 901), ("Hash Table", 847), ("Math", 712),
                        ("Dynamic Programming", 689), ("Sorting", 542)):
            d.text((x, 108), name, font=tf, fill=C.TEXT)
            x += d.textlength(name, font=tf) + 10
            nb = str(n)
            nw = d.textlength(nb, font=self.fonts.ui(17)) + 16
            d.rounded_rectangle([x, 108, x + nw, 136], radius=7, fill=C.BAR_BG)
            d.text((x + 8, 112), nb, font=self.fonts.ui(17), fill=C.MUTED)
            x += nw + 26
        # filter pills row
        px = self.rows_x0
        for label, active in (("All Topics", True), ("Algorithms", False), ("Database", False),
                              ("Shell", False), ("Concurrency", False), ("JavaScript", False)):
            f = self.fonts.ui(22, bold=active)
            w = d.textlength(label, font=f) + 44
            d.rounded_rectangle([px, 160, px + w, 204], radius=22,
                                fill=C.TEXT_STRONG if active else C.BAR_BG)
            d.text((px + 22, 169), label, font=f, fill=(20, 20, 20) if active else C.TEXT)
            px += w + 14
        return img

    def _draw_search_box(self, d, text: str, caret_on: bool, focus: bool):
        x0, y0, x1, y1 = self.rows_x0, 226, self.rows_x0 + 480, 272
        d.rounded_rectangle([x0, y0, x1, y1], radius=10, fill=C.BAR_BG,
                            outline=(110, 110, 110) if focus else None, width=2)
        d.ellipse([x0 + 16, y0 + 13, x0 + 34, y0 + 31], outline=C.MUTED, width=2)
        d.line([(x0 + 33, y0 + 30), (x0 + 40, y0 + 37)], fill=C.MUTED, width=2)
        f = self.fonts.ui(23)
        if text:
            d.text((x0 + 56, y0 + 9), text, font=f, fill=C.TEXT_STRONG)
            cx = x0 + 56 + d.textlength(text, font=f) + 2
        else:
            d.text((x0 + 56, y0 + 9), "Search questions", font=f, fill=C.MUTED)
            cx = x0 + 56
        if caret_on:
            d.line([(cx, y0 + 10), (cx, y0 + 36)], fill=C.TEXT_STRONG, width=2)
        sf = self.fonts.ui(22)
        st = "0/4115 Solved"
        d.text((self.rows_x1 - d.textlength(st, font=sf), y0 + 9), st, font=sf, fill=C.MUTED)

    def _rows(self, d, rows, hover_idx: Optional[int], pressed: bool):
        f = self.fonts.ui(23)
        fs = self.fonts.ui(23)
        for i, r in enumerate(rows):
            y = self.rows_y0 + 44 + i * self.row_h
            bg = (38, 38, 38) if i % 2 == 0 else C.PAGE_BG
            if hover_idx == i:
                bg = (60, 60, 60) if pressed else (48, 48, 48)
            d.rounded_rectangle([self.rows_x0, y, self.rows_x1, y + self.row_h - 4], radius=8, fill=bg)
            d.ellipse([self.rows_x0 + 18, y + 17, self.rows_x0 + 36, y + 35], outline=(95, 95, 95), width=2)
            title = f"{r['frontendQuestionId']}. {r['title'].strip()}"
            d.text((self.rows_x0 + 60, y + 11), title, font=f, fill=C.TEXT_STRONG)
            a = r['acRate']
            ac = f"{(a * 100 if a <= 1 else a):.1f}%"
            d.text((1290 - d.textlength(ac, font=fs), y + 11), ac, font=fs, fill=C.TEXT)
            diff = r["difficulty"]
            lab = {"Easy": "Easy", "Medium": "Med.", "Hard": "Hard"}[diff]
            col = {"Easy": C.EASY, "Medium": C.MED, "Hard": C.HARD}[diff]
            d.text((1430, y + 11), lab, font=fs, fill=col)
            if r.get("paidOnly"):
                lx = 1580
                d.rounded_rectangle([lx, y + 21, lx + 18, y + 36], radius=3, outline=C.MUTED, width=2)
                d.arc([lx + 3, y + 10, lx + 15, y + 26], 180, 360, fill=C.MUTED, width=2)

    def render(self, t: float) -> Image.Image:
        img = self._base.copy()
        d = ImageDraw.Draw(img)
        typed = self.plan.revealed_at(max(0.0, t - self.lead)) if t > self.lead else 0
        text = self.data.query[:typed]
        swapped = t >= self.swap_at
        self._draw_search_box(d, text, (t % 1.06) < 0.62 or t < self.type_end, True)
        rows = self.data.results if swapped else self.data.default_rows[:8]
        hover = None
        pressed = False
        # cursor
        cx0, cy0 = 1500.0, 640.0
        ty = self.rows_y0 + 44 + self.target_idx * self.row_h + 22
        cx1, cy1 = 700.0, float(ty)
        if swapped:
            f = clamp((t - self.swap_at - 0.15) / 0.9, 0, 1)
            f = ease_in_out(f)
            cx, cy = _lerp(cx0, cx1, f), _lerp(cy0, cy1, f)
            if f >= 1.0:
                hover = self.target_idx
                pressed = t >= self.click_at
            _arrow(d, cx, cy)
        self._rows(d, rows, hover, pressed)
        if swapped:
            # redraw cursor on top of rows
            f = ease_in_out(clamp((t - self.swap_at - 0.15) / 0.9, 0, 1))
            _arrow(d, _lerp(cx0, cx1, f), _lerp(cy0, cy1, f))
        return img

    def keystroke_times(self, scene_start: float) -> list[float]:
        return [scene_start + self.lead + ct for ct in self.plan.click_times]


# --------------------------------------------------------------------- work
@dataclass
class CaseView:
    inputs: list          # [(name, value_str)]
    output: str
    expected: str
    ok: bool


class LCWork(Scene):
    """Problem page. ``mode``:
         paste  — editor empty, then the template is pasted in one go
         type   — types ``end_code`` after ``start_code``
         run    — Run button, console slides up, results appear
         hold   — nothing moves (narration over the current state)
    """

    def __init__(self, cfg, fonts: FontBook, doc: Doc, *, mode: str, start_code: str, end_code: str,
                 duration: float, scroll_from: int, scroll_to: int, seed: str,
                 lead: float = 0.6, cases: Optional[list] = None, console_open: bool = False,
                 console_cases: Optional[list] = None, paste_at: float = 1.0, case_switch_at=None,
                 filename_label: str = "Python"):
        self.cfg, self.fonts, self.doc = cfg, fonts, doc
        self.mode, self.duration, self.lead = mode, duration, lead
        self.start_code, self.end_code = start_code, end_code
        self.scroll_from, self.scroll_to = scroll_from, scroll_to
        self.cases = cases or []
        self.console_open0 = console_open
        self.console_cases = console_cases or []
        self.paste_at = paste_at
        self.case_switch_at = case_switch_at
        self.mono = fonts.mono(CODE_SIZE)
        self.full_lines = __import__("johncodes.lc_theme", fromlist=["highlight"]).highlight(end_code)
        self.n0 = _common_prefix_len(start_code, end_code)
        self.plan = build_plan(end_code[self.n0:] or " ", cps=cfg.typing_cps,
                               newline_pause=cfg.typing_newline_pause, seed=seed)
        self.run_press = 0.9
        self.console_h = 540
        self._base = self._make_base()
        self.nav_h = NAV_H
        self.view_h = PANEL_Y1 - TOP - BAR_H
        self.view_w = LEFT_X1 - LEFT_X0
        if doc.image is None:
            doc.render()

    # ---- static chrome
    def _make_base(self) -> Image.Image:
        W, H = self.cfg.width, self.cfg.height
        img = Image.new("RGB", (W, H), C.PAGE_BG)
        d = ImageDraw.Draw(img)
        draw_nav(d, self.fonts, "Problems")
        d.rounded_rectangle([LEFT_X0, TOP, LEFT_X1, PANEL_Y1], radius=10, fill=C.PANEL_BG)
        d.rounded_rectangle([RIGHT_X0, TOP, RIGHT_X1, PANEL_Y1], radius=10, fill=C.PANEL_BG)
        # left tab bar
        d.rounded_rectangle([LEFT_X0, TOP, LEFT_X1, TOP + BAR_H], radius=10, fill=C.BAR_BG)
        d.rectangle([LEFT_X0, TOP + 20, LEFT_X1, TOP + BAR_H], fill=C.BAR_BG)
        f = self.fonts.ui(21)
        fb = self.fonts.ui(21, bold=True)
        x = LEFT_X0 + 22
        for i, name in enumerate(("Description", "Editorial", "Solutions", "Submissions")):
            col = C.TEXT_STRONG if i == 0 else C.MUTED
            d.rectangle([x, TOP + 15, x + 14, TOP + 33], outline=col, width=2)
            d.text((x + 24, TOP + 11), name, font=fb if i == 0 else f, fill=col)
            x += 24 + d.textlength(name, font=fb if i == 0 else f) + 38
            d.line([(x - 20, TOP + 14), (x - 20, TOP + 34)], fill=(70, 70, 70), width=1)
        # right header
        d.rounded_rectangle([RIGHT_X0, TOP, RIGHT_X1, TOP + BAR_H], radius=10, fill=C.BAR_BG)
        d.rectangle([RIGHT_X0, TOP + 20, RIGHT_X1, TOP + BAR_H], fill=C.BAR_BG)
        _icon_code(d, RIGHT_X0 + 22, TOP + 14, C.GREEN)
        d.text((RIGHT_X0 + 54, TOP + 11), "Code", font=fb, fill=C.TEXT_STRONG)
        # language row
        ry = TOP + BAR_H
        d.rectangle([RIGHT_X0, ry, RIGHT_X1, ry + 48], fill=C.PANEL_BG)
        lf = self.fonts.ui(21)
        d.text((RIGHT_X0 + 24, ry + 10), "Python", font=lf, fill=C.TEXT)
        px = RIGHT_X0 + 24 + d.textlength("Python", font=lf) + 12
        d.line([(px, ry + 20), (px + 6, ry + 27), (px + 12, ry + 20)], fill=C.MUTED, width=2)
        ax = px + 44
        d.rounded_rectangle([ax - 12, ry + 8, ax + d.textlength("Auto", font=lf) + 38, ry + 40],
                            radius=8, fill=C.BAR_BG)
        d.text((ax + 4, ry + 10), "Auto", font=lf, fill=C.MUTED)
        for k in range(4):   # right-hand icons
            ix = RIGHT_X1 - 40 - k * 44
            d.rounded_rectangle([ix, ry + 12, ix + 20, ry + 32], radius=5, outline=C.MUTED, width=2)
        # editor surface
        self.ed_x0, self.ed_y0 = RIGHT_X0, ry + 48
        self.ed_x1 = RIGHT_X1
        self.ed_y1 = PANEL_Y1 - 60            # bottom bar below
        d.rectangle([self.ed_x0, self.ed_y0, self.ed_x1, self.ed_y1], fill=C.EDITOR_BG)
        # bottom bar
        by = PANEL_Y1 - 60
        d.rectangle([RIGHT_X0, by, RIGHT_X1, PANEL_Y1 - 10], fill=C.PANEL_BG)
        d.rounded_rectangle([RIGHT_X0, PANEL_Y1 - 30, RIGHT_X1, PANEL_Y1], radius=10, fill=C.PANEL_BG)
        return img

    # ---- phases
    def _code_chars(self, t: float) -> tuple[int, float]:
        """(chars of end_code visible, selection alpha 0..1)"""
        total = len(self.end_code)
        if self.mode == "paste":
            if t < self.paste_at:
                return 0, 0.0
            a = 1.0 - clamp((t - self.paste_at) / 0.9, 0, 1)
            return total, a
        if self.mode == "type":
            tt = max(0.0, t - self.lead)
            n = self.n0 + (self.plan.revealed_at(tt) if tt > 0 else 0)
            return min(n, total), 0.0
        return total, 0.0

    def _console_slide(self, t: float) -> float:
        if self.mode == "run":
            s = self.run_press + 0.25
            return ease_out_cubic(clamp((t - s) / 0.4, 0, 1))
        return 1.0 if self.console_open0 else 0.0

    def render(self, t: float) -> Image.Image:
        img = self._base.copy()
        d = ImageDraw.Draw(img)

        # --- left: description crop
        f = ease_in_out(clamp(t / 1.2, 0, 1))
        sy = int(_lerp(self.scroll_from, self.scroll_to, f))
        crop = self.doc.image.crop((0, sy, self.view_w, sy + self.view_h))
        img.paste(crop, (LEFT_X0, TOP + BAR_H))
        # round the bottom corners of the left panel
        d.rounded_rectangle([LEFT_X0, TOP, LEFT_X1, PANEL_Y1], radius=10, outline=C.PAGE_BG, width=2)

        # --- right: editor
        n, sel_a = self._code_chars(t)
        done = n >= len(self.end_code)
        spans, caret = prefix(self.full_lines, n)
        slide = self._console_slide(t)
        self._draw_editor(img, d, spans, caret, t, n, sel_a, slide, done)

        # --- bottom bar (Console / Run / Submit)
        self._draw_bottom(d, t, slide)

        # --- console
        if slide > 0:
            self._draw_console(img, d, t, slide)
        return img

    def _draw_editor(self, img, d, spans, caret, t, n, sel_a, slide, done):
        x0, y0, x1 = self.ed_x0, self.ed_y0, self.ed_x1
        vis_h = (self.ed_y1 - y0) - int(self.console_h * slide)
        lh = self.mono.line_h
        gut = 70
        n_lines = len(self.full_lines)
        # keep the caret / last line in view
        row = caret[0]
        content_h = (max(row + 1, n_lines if self.mode != "type" else row + 1)) * lh + 20
        avail = vis_h - 36
        want_bottom = (row + 1) * lh + 28
        scroll = max(0, want_bottom - avail)
        if self.mode in ("run", "hold") or done:
            scroll = max(0, (n_lines) * lh + 28 - avail)
        layer = Image.new("RGB", (x1 - x0, max(1, vis_h)), C.EDITOR_BG)
        ld = ImageDraw.Draw(layer)
        for i, line in enumerate(spans):
            y = 10 + i * lh - scroll
            if y < -lh or y > vis_h:
                continue
            # selection (paste flash)
            if sel_a > 0.02 and line:
                w = sum(ld.textlength(s.text, font=self.mono.regular) for s in line)
                col = tuple(int(_lerp(C.EDITOR_BG[k], C.SELECT[k], sel_a)) for k in range(3))
                ld.rectangle([gut + 14, y, gut + 14 + w, y + lh - 2], fill=col)
            cur = i == row
            nf = self.fonts.mono(CODE_SIZE - 3).regular
            nt = str(i + 1)
            ld.text((gut - 14 - ld.textlength(nt, font=nf), y + 5), nt, font=nf,
                    fill=C.TEXT_STRONG if cur else C.GUTTER)
            x = gut + 14
            for s in line:
                ld.text((x, y + 2), s.text, font=self.mono.regular, fill=s.color)
                x += ld.textlength(s.text, font=self.mono.regular)
        # caret
        if (not done or (t % 1.06) < 0.62) and not (self.mode == "run" and slide > 0.5):
            r, c = caret
            cx = gut + 14 + c * self.mono.char_w
            cy = 10 + r * lh - scroll
            ld.rectangle([cx, cy + 3, cx + 2, cy + lh - 4], fill=C.TEXT_STRONG)
        img.paste(layer, (x0, y0))
        # status strip (Saved ... Ln, Col) at the bottom of the visible editor
        sy1 = self.ed_y0 + vis_h
        sf = self.fonts.ui(19)
        d.rectangle([x0, sy1 - 30, x1, sy1], fill=C.EDITOR_BG)
        d.line([(x0, sy1 - 30), (x1, sy1 - 30)], fill=(48, 48, 48), width=1)
        d.text((x0 + 22, sy1 - 26), "Saved", font=sf, fill=C.MUTED)
        lc = f"Ln {caret[0] + 1}, Col {caret[1] + 1}"
        d.text((x1 - 22 - d.textlength(lc, font=sf), sy1 - 26), lc, font=sf, fill=C.MUTED)

    def _draw_bottom(self, d, t, slide):
        by = PANEL_Y1 - 56
        f = self.fonts.ui(22)
        fb = self.fonts.ui(22, bold=True)
        # status text
        r, c = (0, 0)
        d.text((RIGHT_X0 + 24, by + 14), "Console", font=f, fill=C.MUTED)
        cx = RIGHT_X0 + 24 + d.textlength("Console", font=f) + 12
        d.line([(cx, by + 29 if not slide else by + 22), (cx + 6, by + 22 if not slide else by + 29),
                (cx + 12, by + 29 if not slide else by + 22)], fill=C.MUTED, width=2)
        # buttons
        pressed = self.mode == "run" and self.run_press <= t < self.run_press + 0.35
        rw = d.textlength("Run", font=fb) + 70
        sw = d.textlength("Submit", font=fb) + 40
        sx1 = RIGHT_X1 - 18
        sx0 = sx1 - sw
        rx1 = sx0 - 12
        rx0 = rx1 - rw
        d.rounded_rectangle([rx0, by + 6, rx1, by + 48], radius=9,
                            fill=(78, 78, 78) if pressed else C.BTN_BG)
        d.polygon([(rx0 + 20, by + 18), (rx0 + 20, by + 36), (rx0 + 34, by + 27)], fill=C.TEXT_STRONG)
        d.text((rx0 + 46, by + 13), "Run", font=fb, fill=C.TEXT_STRONG)
        d.rounded_rectangle([sx0, by + 6, sx1, by + 48], radius=9, fill=(40, 100, 60))
        d.text((sx0 + 20, by + 13), "Submit", font=fb, fill=(190, 240, 205))
        # status strip text inside bar centre
        self._run_btn = ((rx0 + rx1) / 2, by + 27)
        st = self.fonts.ui(19)
        sm = "Saved"
        # Ln/Col lives at the editor bottom
        if self.mode == "run" and self.run_press - 0.7 < t < self.run_press + 0.45:
            # cursor travelling to the Run button
            f0 = ease_in_out(clamp((t - (self.run_press - 0.7)) / 0.7, 0, 1))
            cx0, cy0 = 1500.0, 520.0
            _arrow(d, _lerp(cx0, self._run_btn[0], f0), _lerp(cy0, self._run_btn[1] - 4, f0))

    def _draw_console(self, img, d, t, slide):
        h = int(self.console_h * slide)
        y1 = PANEL_Y1 - 60
        y0 = y1 - h
        x0, x1 = RIGHT_X0, RIGHT_X1
        d.rectangle([x0, y0, x1, y1], fill=C.CONSOLE_BG)
        d.line([(x0, y0), (x1, y0)], fill=(60, 60, 60), width=2)
        if h < 200:
            return
        f = self.fonts.ui(21)
        fb = self.fonts.ui(21, bold=True)
        # tabs
        tabs = ("Testcase", "Test Result")
        x = x0 + 26
        active = 1 if (self.mode == "run" or self.console_cases) else 0
        for i, nme in enumerate(tabs):
            col = C.TEXT_STRONG if i == active else C.MUTED
            d.text((x, y0 + 14), nme, font=fb if i == active else f, fill=col)
            if i == active:
                d.line([(x, y0 + 50), (x + d.textlength(nme, font=fb), y0 + 50)], fill=C.TEXT_STRONG, width=2)
            x += d.textlength(nme, font=f) + 44
        d.line([(x0, y0 + 52), (x1, y0 + 52)], fill=(58, 58, 58), width=1)
        cy = y0 + 70

        # result state
        if self.mode == "run":
            tr = t - (self.run_press + 0.65)
            cases = self.cases
        else:
            tr = 99.0
            cases = self.console_cases
        if tr < 0 or not cases:
            return
        pending = tr < 1.1
        if pending and self.mode == "run":
            dots = "." * (1 + int(t * 3) % 3)
            d.text((x0 + 26, cy + 6), "Running" + dots, font=self.fonts.ui(30, bold=True), fill=C.MUTED)
            return
        all_ok = all(c.ok for c in cases)
        head = "Accepted" if all_ok else "Wrong Answer"
        d.text((x0 + 26, cy), head, font=self.fonts.ui(34, bold=True), fill=C.GREEN if all_ok else C.RED)
        # case tabs
        idx = 0
        if self.case_switch_at is not None and self.mode == "run":
            idx = int(clamp(int((tr - 1.1) // self.case_switch_at), 0, len(cases) - 1))
        elif self.mode != "run":
            idx = 0
        tx = x0 + 26
        ty = cy + 60
        for i, c in enumerate(cases):
            label = f"Case {i + 1}"
            w = d.textlength(label, font=f) + 56
            d.rounded_rectangle([tx, ty, tx + w, ty + 38], radius=9,
                                fill=(70, 70, 70) if i == idx else C.BAR_BG)
            d.ellipse([tx + 14, ty + 14, tx + 24, ty + 24], fill=C.GREEN if c.ok else C.RED)
            d.text((tx + 34, ty + 6), label, font=f, fill=C.TEXT_STRONG if i == idx else C.MUTED)
            tx += w + 10
        case = cases[idx]
        yy = ty + 56
        lf = self.fonts.ui(19)
        mf = self.fonts.mono(22).regular
        bw = (x1 - x0) - 52

        def box(label, value, y):
            d.text((x0 + 26, y), label, font=lf, fill=C.MUTED)
            vals = value
            bh = 44
            d.rounded_rectangle([x0 + 26, y + 28, x0 + 26 + bw, y + 28 + bh], radius=8, fill=C.BOX_BG)
            txt = vals
            while d.textlength(txt, font=mf) > bw - 28 and len(txt) > 4:
                txt = txt[:-2]
            if txt != vals:
                txt = txt[:-1] + "…"
            d.text((x0 + 40, y + 28 + 8), txt, font=mf, fill=C.TEXT_STRONG)
            return y + 28 + bh + 14

        for name, val in case.inputs[:2]:
            yy = box(f"{name} =", val, yy)
        if len(case.inputs) > 2:
            extra = ", ".join(f"{n} = {v}" for n, v in case.inputs[2:])
            yy = box("more inputs", extra, yy)
        yy = box("Output", case.output, yy)
        box("Expected", case.expected, yy)

    def keystroke_times(self, scene_start: float) -> list[float]:
        if self.mode == "type":
            return [scene_start + self.lead + ct for ct in self.plan.click_times]
        if self.mode == "paste":
            return [scene_start + self.paste_at, scene_start + self.paste_at + 0.12]
        return []

    @property
    def typing_duration(self) -> float:
        return self.plan.duration
