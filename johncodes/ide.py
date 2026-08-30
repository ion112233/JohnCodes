"""Full-bleed PyCharm (classic Darcula) editor window, rendered with Pillow.

Fills the whole frame like a real screen recording:

    ┌──────────────────────────────────────────────────────────────┐
    │ ● ● ●   JohnCodes            [ solution ▾ ] ▶ 🐞 ■     🔍 ⚙   │  main toolbar
    ├──┬───────────────┬───────────────────────────────────────┬────┤
    │  │ ▾ johncodes   │ solution ▸ two_sum()                  │    │  tab + breadcrumb
    │▣ │  ▾ src        ├───────────────────────────────────────┤ ┃  │
    │≡ │   ● solution  │ 1  def two_sum(...):                  │ ┃  │  editor + scrollbar
    │⌥ │   ○ test_...  │ 2      seen = {}                      │    │
    │  │ ▸ tests       │ ...                                   │    │
    ├──┴───────────────┴───────────────────────────────────────┴────┤
    │ solution.py                        main ⑃  4:26  LF  UTF-8 …   │  status bar
    └──────────────────────────────────────────────────────────────┘

Chrome is drawn once and cached; only the editor body changes per frame.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from PIL import Image, ImageDraw

from . import theme
from .fonts import FontBook
from .highlight import Line

TOOLBAR_H = 52
TABBAR_H = 40
BREADCRUMB_H = 30
STATUS_H = 28
TOOLSTRIP_W = 44
PROJECT_W = 280
SCROLLBAR_W = 15
LEFT_W = TOOLSTRIP_W + PROJECT_W

GUTTER_ICON_W = 30           # room for the gutter run-arrow
GUTTER_VCS_W = 3             # VCS change stripe
GUTTER_NUM_PAD_L = 8
GUTTER_NUM_PAD_R = 16
CODE_PAD_L = 22
CODE_PAD_T = 14
FS_MAX = 38
FS_MIN = 24
INDENT_SPACES = 4


def hx3(v: int) -> tuple[int, int, int]:
    return (v, v, v)


@dataclass
class _Layout:
    fs: int
    char_w: float
    line_h: int
    gutter_w: int
    num_x_right: int
    code_x: int
    editor_x0: int
    editor_x1: int
    editor_y0: int
    editor_y1: int
    rows: int
    center_pad: int


def _extract_symbol(code: str) -> str:
    m = re.search(r"^\s*(?:async\s+)?def\s+(\w+)", code, re.M)
    if m:
        return m.group(1) + "()"
    m = re.search(r"^\s*class\s+(\w+)", code, re.M)
    return m.group(1) if m else ""


class IDE:
    def __init__(self, cfg, fonts: FontBook, *, filename: str, project: str,
                 python_label: str, n_code_lines: int, max_line_len: int,
                 code: str = ""):
        self.cfg = cfg
        self.fonts = fonts
        self.filename = filename
        self.module = filename[:-3] if filename.endswith(".py") else filename
        self.project = project
        self.python_label = python_label
        self.symbol = _extract_symbol(code)
        self.W, self.H = cfg.width, cfg.height

        editor_x0 = LEFT_W
        editor_x1 = self.W - SCROLLBAR_W
        editor_y0 = TOOLBAR_H + TABBAR_H + BREADCRUMB_H
        editor_y1 = self.H - STATUS_H

        gutter_digits = max(2, len(str(max(n_code_lines, 1))))
        base_gutter = GUTTER_ICON_W + GUTTER_VCS_W + GUTTER_NUM_PAD_L + GUTTER_NUM_PAD_R
        code_area_w = (editor_x1 - editor_x0) - base_gutter - CODE_PAD_L - 30

        fs = FS_MAX
        while fs > FS_MIN:
            cw = fonts.mono(fs).char_w
            if cw * (gutter_digits + max(max_line_len, 1)) <= code_area_w + gutter_digits * cw:
                if cw * max(max_line_len, 1) <= code_area_w:
                    break
            fs -= 1
        mono = fonts.mono(fs)
        gutter_w = int(base_gutter + gutter_digits * mono.char_w)
        num_x_right = editor_x0 + GUTTER_ICON_W + GUTTER_VCS_W + GUTTER_NUM_PAD_L \
            + int(gutter_digits * mono.char_w)

        rows = max(1, (editor_y1 - editor_y0 - CODE_PAD_T) // mono.line_h)
        center_pad = 0

        self.layout = _Layout(
            fs=fs, char_w=mono.char_w, line_h=mono.line_h, gutter_w=gutter_w,
            num_x_right=num_x_right,
            code_x=editor_x0 + gutter_w + CODE_PAD_L,
            editor_x0=editor_x0, editor_x1=editor_x1,
            editor_y0=editor_y0, editor_y1=editor_y1,
            rows=rows, center_pad=center_pad,
        )
        self._chrome: Image.Image | None = None

    # ================================================================ chrome
    def _draw_chrome(self) -> Image.Image:
        L = self.layout
        W, H = self.W, self.H
        img = Image.new("RGB", (W, H), theme.EDITOR_BG)
        d = ImageDraw.Draw(img)
        self._toolbar(d)
        self._tabbar(d)
        self._breadcrumb(d)
        self._toolstrip(d)
        self._project_pane(d)
        # gutter
        d.rectangle([L.editor_x0, L.editor_y0, L.editor_x0 + L.gutter_w, L.editor_y1],
                    fill=theme.GUTTER_BG)
        d.line([L.editor_x0 + L.gutter_w, L.editor_y0,
                L.editor_x0 + L.gutter_w, L.editor_y1], fill=theme.BORDER)
        # scrollbar track
        d.rectangle([W - SCROLLBAR_W, L.editor_y0, W, L.editor_y1], fill=theme.EDITOR_BG)
        # status bar
        self._statusbar_base(d)
        return img

    # ---- main toolbar ----
    def _toolbar(self, d: ImageDraw.ImageDraw) -> None:
        W = self.W
        ui = self.fonts.ui
        d.rectangle([0, 0, W, TOOLBAR_H], fill=theme.TOOLBAR_BG)
        d.line([0, TOOLBAR_H, W, TOOLBAR_H], fill=theme.BORDER)
        cy = TOOLBAR_H // 2

        for i, col in enumerate((theme.TRAFFIC_RED, theme.TRAFFIC_YELLOW, theme.TRAFFIC_GREEN)):
            cx = 26 + i * 24
            d.ellipse([cx - 7, cy - 7, cx + 7, cy + 7], fill=col)

        d.text((104, cy - 12), self.project, font=ui(19, bold=True), fill=theme.TITLE_FG)
        # a faint VCS branch widget
        bx = 104 + d.textlength(self.project, font=ui(19, bold=True)) + 34
        self._icon_branch(d, bx, cy, theme.ICON_DIM)
        d.text((bx + 20, cy - 11), "main", font=ui(16), fill=theme.ICON_DIM)

        # right cluster: run-config pill + run/debug/stop + search + settings
        x = W - 30
        for draw in (self._icon_gear, self._icon_search):
            x -= 26
            draw(d, x, cy, theme.ICON_FG)
            x -= 8
        x -= 14
        # stop (dim), debug, run
        x -= 22
        self._icon_stop(d, x, cy, theme.ICON_DIM)
        x -= 30
        self._icon_debug(d, x, cy, theme.DEBUG_GREEN)
        x -= 30
        self._icon_run(d, x, cy, theme.RUN_GREEN)
        x -= 16
        # run-config pill
        pill_txt = self.module
        pw = d.textlength(pill_txt, font=ui(16))
        x0 = x - (pw + 46)
        d.rounded_rectangle([x0, cy - 15, x, cy + 15], radius=6,
                            fill=hx3(0x35), outline=theme.BORDER_LT, width=1)
        self._icon_py_run(d, x0 + 12, cy)
        d.text((x0 + 26, cy - 10), pill_txt, font=ui(16), fill=theme.TITLE_FG)
        d.polygon([(x - 18, cy - 3), (x - 10, cy - 3), (x - 14, cy + 3)], fill=theme.ICON_DIM)

    # ---- tab strip ----
    def _tabbar(self, d: ImageDraw.ImageDraw) -> None:
        W = self.W
        ui = self.fonts.ui
        ty = TOOLBAR_H
        d.rectangle([0, ty, W, ty + TABBAR_H], fill=theme.TAB_INACTIVE_BG)
        d.line([0, ty + TABBAR_H, W, ty + TABBAR_H], fill=theme.BORDER)

        x = LEFT_W
        tabs = [(self.filename, True), ("__init__.py", False)]
        for name, active in tabs:
            tw = d.textlength(name, font=ui(17)) + 74
            if active:
                d.rectangle([x, ty + 3, x + tw, ty + TABBAR_H], fill=theme.TAB_ACTIVE_BG)
                d.rectangle([x, ty + TABBAR_H - 3, x + tw, ty + TABBAR_H],
                            fill=theme.TAB_UNDERLINE)
            self._icon_pyfile(d, x + 16, ty + TABBAR_H // 2)
            d.text((x + 34, ty + TABBAR_H // 2 - 11), name, font=ui(17),
                   fill=theme.FG_DEFAULT if active else theme.TAB_INACTIVE_FG)
            # close ×
            cxx = x + tw - 20
            cc = theme.ICON_FG if active else theme.ICON_DIM
            d.line([cxx - 4, ty + TABBAR_H // 2 - 4, cxx + 4, ty + TABBAR_H // 2 + 4], fill=cc, width=2)
            d.line([cxx - 4, ty + TABBAR_H // 2 + 4, cxx + 4, ty + TABBAR_H // 2 - 4], fill=cc, width=2)
            x += tw

    # ---- breadcrumb ----
    def _breadcrumb(self, d: ImageDraw.ImageDraw) -> None:
        W = self.W
        ui = self.fonts.ui(15)
        by = TOOLBAR_H + TABBAR_H
        d.rectangle([0, by, W, by + BREADCRUMB_H], fill=theme.EDITOR_BG)
        d.line([0, by + BREADCRUMB_H, W, by + BREADCRUMB_H], fill=theme.BORDER)
        crumbs = ["src", self.module]
        if self.symbol:
            crumbs.append(self.symbol)
        x = LEFT_W + 16
        cyc = by + BREADCRUMB_H // 2
        for i, c in enumerate(crumbs):
            if i:
                d.polygon([(x, cyc - 4), (x + 5, cyc), (x, cyc + 4)], fill=theme.ICON_DIM)
                x += 14
            fill = theme.TREE_FG if i == len(crumbs) - 1 else theme.STATUS_FG
            d.text((x, cyc - 9), c, font=ui, fill=fill)
            x += d.textlength(c, font=ui) + 10

    # ---- far-left tool window stripe ----
    def _toolstrip(self, d: ImageDraw.ImageDraw) -> None:
        H = self.H
        y0 = TOOLBAR_H
        d.rectangle([0, y0, TOOLSTRIP_W, H - STATUS_H], fill=theme.TOOLSTRIP_BG)
        d.line([TOOLSTRIP_W, y0, TOOLSTRIP_W, H - STATUS_H], fill=theme.BORDER)
        cx = TOOLSTRIP_W // 2
        # active "Project" tool window
        d.rectangle([0, y0 + 14, TOOLSTRIP_W, y0 + 46], fill=hx3(0x2f))
        d.rectangle([0, y0 + 14, 2, y0 + 46], fill=theme.TAB_UNDERLINE)
        self._icon_project(d, cx, y0 + 30, theme.ICON_FG)
        self._icon_commit(d, cx, y0 + 74, theme.ICON_DIM)
        self._icon_structure(d, cx, y0 + 114, theme.ICON_DIM)
        # bottom: terminal
        self._icon_terminal(d, cx, H - STATUS_H - 30, theme.ICON_DIM)

    # ---- project pane ----
    def _project_pane(self, d: ImageDraw.ImageDraw) -> None:
        ui = self.fonts.ui
        x0 = TOOLSTRIP_W
        y0 = TOOLBAR_H
        d.rectangle([x0, y0, x0 + PROJECT_W, self.H - STATUS_H], fill=theme.PANEL_BG)
        d.line([x0 + PROJECT_W, y0, x0 + PROJECT_W, self.H - STATUS_H], fill=theme.BORDER)

        # header
        d.rectangle([x0, y0, x0 + PROJECT_W, y0 + 34], fill=theme.PANEL_BG)
        d.text((x0 + 16, y0 + 9), "Project", font=ui(14, bold=True), fill=theme.TREE_HEADER_FG)
        # header gadget icons (right)
        gx = x0 + PROJECT_W - 24
        for draw in (self._icon_ellipsis, self._icon_collapse):
            draw(d, gx, y0 + 17, theme.ICON_DIM)
            gx -= 26
        d.line([x0, y0 + 34, x0 + PROJECT_W, y0 + 34], fill=theme.BORDER)

        # (depth, kind, name, selected, expanded)  — kind: folder | py | file
        rows = [
            (0, "folder", self.project, False, True),
            (1, "folder", "src", False, True),
            (2, "py", self.filename, True, False),
            (2, "py", "test_" + self.filename, False, False),
            (1, "folder", "tests", False, True),
            (2, "py", "conftest.py", False, False),
            (1, "folder", "assets", False, False),
            (1, "file", "README.md", False, False),
            (1, "file", "requirements.txt", False, False),
            (1, "file", "pyproject.toml", False, False),
        ]
        row_h = 30
        top = y0 + 34
        for i, (depth, kind, name, sel, expanded) in enumerate(rows):
            ry = top + 8 + i * row_h
            ind_x = x0 + 12 + depth * 20
            if sel:
                d.rectangle([x0, ry - 4, x0 + PROJECT_W, ry + row_h - 8],
                            fill=theme.TREE_SEL_BG)
            for lvl in range(1, depth + 1):
                gx2 = x0 + 12 + lvl * 20 - 10
                d.line([gx2, ry - 4, gx2, ry + row_h - 8], fill=theme.BORDER_LT)
            if kind == "folder":
                if expanded:  # ▾
                    d.polygon([(ind_x - 3, ry + 5), (ind_x + 7, ry + 5), (ind_x + 2, ry + 12)],
                              fill=theme.ICON_FG)
                else:         # ▸
                    d.polygon([(ind_x - 1, ry + 3), (ind_x - 1, ry + 13), (ind_x + 6, ry + 8)],
                              fill=theme.ICON_FG)
            self._tree_icon(d, ind_x + 16, ry + 8, kind)
            d.text((ind_x + 34, ry - 1), name, font=ui(16),
                   fill=(255, 255, 255) if sel else theme.TREE_FG)

    def _statusbar_base(self, d: ImageDraw.ImageDraw) -> None:
        W, H = self.W, self.H
        sy = H - STATUS_H
        d.rectangle([0, sy, W, H], fill=theme.PANEL_BG)
        d.line([0, sy, W, sy], fill=theme.BORDER)
        d.text((16, sy + 6), f"{self.module} › {self.symbol or self.module}",
               font=self.fonts.ui(13), fill=theme.STATUS_FG)

    # ================================================================ icons
    def _icon_run(self, d, x, cy, c):
        d.polygon([(x, cy - 8), (x, cy + 8), (x + 13, cy)], fill=c)

    def _icon_debug(self, d, x, cy, c):
        d.ellipse([x - 6, cy - 6, x + 6, cy + 6], outline=c, width=2)
        for ang in ((-7, -6), (7, -6), (-8, 0), (8, 0), (-7, 6), (7, 6)):
            d.line([x, cy, x + ang[0], cy + ang[1]], fill=c, width=1)

    def _icon_stop(self, d, x, cy, c):
        d.rounded_rectangle([x - 6, cy - 6, x + 6, cy + 6], radius=2, fill=c)

    def _icon_search(self, d, x, cy, c):
        d.ellipse([x - 8, cy - 8, x + 3, cy + 3], outline=c, width=2)
        d.line([x + 2, cy + 2, x + 8, cy + 8], fill=c, width=2)

    def _icon_gear(self, d, x, cy, c):
        d.ellipse([x - 7, cy - 7, x + 7, cy + 7], outline=c, width=2)
        d.ellipse([x - 2, cy - 2, x + 2, cy + 2], fill=c)

    def _icon_branch(self, d, x, cy, c):
        d.ellipse([x - 2, cy - 9, x + 4, cy - 3], outline=c, width=2)
        d.ellipse([x - 2, cy + 3, x + 4, cy + 9], outline=c, width=2)
        d.line([x + 1, cy - 3, x + 1, cy + 3], fill=c, width=2)

    def _icon_py_run(self, d, x, cy):
        d.rounded_rectangle([x, cy - 7, x + 7, cy + 1], radius=2, fill=(75, 139, 190))
        d.rounded_rectangle([x + 4, cy - 1, x + 11, cy + 7], radius=2, fill=(255, 212, 59))

    def _icon_pyfile(self, d, x, cy):
        d.rounded_rectangle([x, cy - 9, x + 8, cy + 1], radius=2, fill=(75, 139, 190))
        d.rounded_rectangle([x + 5, cy - 1, x + 13, cy + 9], radius=2, fill=(255, 212, 59))

    def _icon_project(self, d, x, cy, c):
        d.rectangle([x - 8, cy - 6, x + 8, cy + 7], outline=c, width=2)
        d.line([x - 8, cy - 1, x + 8, cy - 1], fill=c, width=2)

    def _icon_commit(self, d, x, cy, c):
        d.ellipse([x - 7, cy - 7, x + 7, cy + 7], outline=c, width=2)
        d.line([x - 3, cy, x - 1, cy + 3], fill=c, width=2)
        d.line([x - 1, cy + 3, x + 4, cy - 3], fill=c, width=2)

    def _icon_structure(self, d, x, cy, c):
        for i, yy in enumerate((-6, 0, 6)):
            d.rectangle([x - 6 + (i == 2) * 6, cy + yy - 2, x + 2 + (i == 2) * 6, cy + yy + 2], fill=c)

    def _icon_terminal(self, d, x, cy, c):
        d.rectangle([x - 9, cy - 7, x + 9, cy + 7], outline=c, width=2)
        d.line([x - 5, cy - 2, x - 1, cy + 1], fill=c, width=2)
        d.line([x - 1, cy + 1, x - 5, cy + 4], fill=c, width=2)

    def _icon_ellipsis(self, d, x, cy, c):
        for dx in (-6, 0, 6):
            d.ellipse([x + dx - 1, cy - 1, x + dx + 1, cy + 1], fill=c)

    def _icon_collapse(self, d, x, cy, c):
        d.line([x - 6, cy - 4, x, cy + 2], fill=c, width=2)
        d.line([x, cy + 2, x + 6, cy - 4], fill=c, width=2)

    def _tree_icon(self, d, x, cy, kind):
        if kind == "folder":
            # one plain folder icon for every folder (PyCharm default)
            c = theme.FOLDER_ICON
            d.polygon([(x - 9, cy - 6), (x - 2, cy - 6), (x, cy - 3), (x - 9, cy - 3)], fill=c)
            d.rounded_rectangle([x - 9, cy - 4, x + 9, cy + 6], radius=2, fill=c)
        elif kind == "py":
            self._icon_pyfile(d, x - 6, cy)
        else:
            d.rectangle([x - 6, cy - 8, x + 6, cy + 8], outline=(150, 152, 155), width=2)
            d.line([x - 3, cy - 3, x + 3, cy - 3], fill=(150, 152, 155), width=2)
            d.line([x - 3, cy + 1, x + 3, cy + 1], fill=(150, 152, 155), width=2)
            d.line([x - 3, cy + 5, x + 1, cy + 5], fill=(150, 152, 155), width=2)

    # ================================================================ frame
    def render(self, spans_lines: list[Line], caret_rc: tuple[int, int] | None,
               t: float, *, total_lines: int, show_caret: bool = True) -> Image.Image:
        if self._chrome is None:
            self._chrome = self._draw_chrome()
        img = self._chrome.copy()
        d = ImageDraw.Draw(img)
        L = self.layout
        mono = self.fonts.mono(L.fs)
        caret_row = caret_rc[0] if caret_rc else 0

        # always top-anchored; the gutter shows continuous line numbers all the
        # way down the screen, even past the end of the file (like a real editor)
        first = 0
        if total_lines > L.rows and caret_row >= L.rows - 3:
            first = min(caret_row - (L.rows - 4), total_lines - L.rows)
        first = max(0, first)
        y_top = L.editor_y0 + CODE_PAD_T

        def row_y(ln: int) -> int:
            return y_top + (ln - first) * L.line_h

        def visible(ln: int) -> bool:
            return first <= ln < first + L.rows

        vcs_x = L.editor_x0 + L.gutter_w - GUTTER_VCS_W - 1
        # current-line highlight
        if caret_rc and visible(caret_row):
            hy = row_y(caret_row)
            d.rectangle([L.editor_x0 + L.gutter_w + 1, hy, L.editor_x1, hy + L.line_h],
                        fill=theme.CARET_ROW)
            d.rectangle([L.editor_x0, hy, L.editor_x0 + L.gutter_w, hy + L.line_h],
                        fill=hx3(0x34))

        # indent guides
        for ln in range(len(spans_lines)):
            if not visible(ln):
                continue
            text = "".join(s.text for s in spans_lines[ln])
            levels = (len(text) - len(text.lstrip(" "))) // INDENT_SPACES
            y = row_y(ln)
            col = theme.INDENT_GUIDE_CUR if (caret_rc and ln == caret_row) else theme.INDENT_GUIDE
            for lvl in range(1, levels + 1):
                gx = L.code_x + int(mono.char_w * lvl * INDENT_SPACES) - 1
                d.line([gx, y, gx, y + L.line_h], fill=col)

        # line numbers for every visible row — including the blank ones below EOF
        for vis in range(L.rows):
            ln = first + vis
            y = row_y(ln)
            if y + L.line_h > L.editor_y1 + 2:
                break
            num = str(ln + 1)
            col = theme.LINE_NUMBER_CUR if (caret_rc and ln == caret_row) else theme.LINE_NUMBER
            d.text((L.num_x_right - d.textlength(num, font=mono.regular), y), num,
                   font=mono.regular, fill=col)

        # VCS "added" stripe only next to real lines
        for ln in range(total_lines):
            if not visible(ln):
                continue
            y = row_y(ln)
            d.rectangle([vcs_x, y, vcs_x + GUTTER_VCS_W, y + L.line_h], fill=theme.VCS_ADDED)

        # gutter run-arrow next to the def / class line
        for ln in range(len(spans_lines)):
            if not visible(ln):
                continue
            text = "".join(s.text for s in spans_lines[ln]).lstrip()
            if text.startswith(("def ", "class ", "async def ")):
                y = row_y(ln) + L.line_h // 2
                ax = L.editor_x0 + 8
                d.polygon([(ax, y - 7), (ax, y + 7), (ax + 11, y)],
                          outline=theme.RUN_GREEN, width=2)

        # code
        for ln in range(len(spans_lines)):
            if not visible(ln):
                continue
            x = L.code_x
            y = row_y(ln)
            for span in spans_lines[ln]:
                d.text((x, y), span.text, font=mono.pick(italic=span.italic), fill=span.color)
                x += mono.char_w * len(span.text)

        # caret
        if show_caret and caret_rc and visible(caret_row):
            if (t % 1.06) < 0.62:
                cx = L.code_x + int(round(mono.char_w * caret_rc[1]))
                cyt = row_y(caret_row)
                d.rectangle([cx, cyt + 2, cx + 2, cyt + L.line_h - 2], fill=theme.CARET)

        self._scrollbar(d, first, total_lines)
        self._status_dynamic(d, caret_rc)
        return img

    def _scrollbar(self, d: ImageDraw.ImageDraw, first: int, n_lines: int) -> None:
        L = self.layout
        x0 = self.W - SCROLLBAR_W + 3
        x1 = self.W - 4
        track_top, track_bot = L.editor_y0 + 2, L.editor_y1 - 2
        if n_lines <= L.rows:
            frac_h, frac_y = 1.0, 0.0
        else:
            frac_h = L.rows / n_lines
            frac_y = first / n_lines
        h = track_bot - track_top
        ty0 = track_top + h * frac_y
        ty1 = ty0 + max(40, h * frac_h)
        d.rounded_rectangle([x0, ty0, x1, ty1], radius=5, fill=(74, 77, 78))

    def _status_dynamic(self, d: ImageDraw.ImageDraw, caret_rc: tuple[int, int] | None) -> None:
        ui = self.fonts.ui(13)
        sy = self.H - STATUS_H
        row, coln = (caret_rc[0] + 1, caret_rc[1] + 1) if caret_rc else (1, 1)
        text = "      ".join([f"{row}:{coln}", "LF", "UTF-8", "4 spaces", self.python_label])
        w = d.textlength(text, font=ui)
        total = w + 54 + 40
        d.rectangle([self.W - total - 10, sy + 1, self.W, self.H], fill=theme.PANEL_BG)
        bx = self.W - total
        self._icon_branch(d, bx, sy + STATUS_H // 2, theme.STATUS_FG)
        d.text((bx + 16, sy + 6), "main", font=ui, fill=theme.STATUS_FG)
        d.text((self.W - w - 20, sy + 6), text, font=ui, fill=theme.STATUS_FG)
