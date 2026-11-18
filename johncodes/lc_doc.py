"""LeetCode problem statement -> one tall image (the left-hand "Description" panel).

``Doc`` parses LeetCode's statement HTML into blocks (paragraphs, example boxes,
bullet lists, images), lays them out with mixed fonts (sans / mono chips / bold /
superscripts) and renders the whole thing once. The scenes then just crop it at a
scroll offset, so scrolling is free.
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

from PIL import Image, ImageDraw

from . import lc_theme as C
from .fonts import FontBook

SANS = 24
MONO = 21
LINE_H = 38


# ------------------------------------------------------------------- parsing
@dataclass
class Run:
    text: str
    code: bool = False
    bold: bool = False
    italic: bool = False
    sup: bool = False
    grp: int = 0


@dataclass
class Block:
    kind: str                       # p | heading | example | li | img
    runs: list[Run] = field(default_factory=list)
    lines: list[list[Run]] = field(default_factory=list)   # example
    bullet: str = ""
    src: str = ""
    anchor: str = ""
    mixed: bool = False


class _Parser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks: list[Block] = []
        self.runs: list[Run] = []
        self.flags = {"code": 0, "bold": 0, "italic": 0, "sup": 0}
        self.pre = 0
        self.in_example_div = 0
        self.example_lines: list[list[Run]] = []
        self.list_stack: list[list] = []     # ["ul"|"ol", counter]
        self.example_heading = False
        self.skip = 0
        self.code_id = 0

    # -- helpers
    def _add_text(self, text: str):
        if not text:
            return
        if self.pre:
            text = text.replace("\xa0", " ")
        else:
            text = re.sub(r"[\s\xa0]+", " ", text)
        self.runs.append(Run(text, code=bool(self.flags["code"]), bold=bool(self.flags["bold"]),
                             italic=bool(self.flags["italic"]), sup=bool(self.flags["sup"]),
                         grp=self.code_id if self.flags["code"] else 0))

    def _flush(self, kind="p", bullet=""):
        runs = self.runs
        self.runs = []
        # trim edges
        while runs and not runs[0].text.strip():
            runs.pop(0)
        while runs and not runs[-1].text.strip():
            runs.pop()
        if not runs:
            return
        runs[0].text = runs[0].text.lstrip()
        runs[-1].text = runs[-1].text.rstrip()
        if self.in_example_div:
            self.example_lines.append(runs)
            return
        text = "".join(r.text for r in runs)
        if kind == "p" and all(r.bold for r in runs) and re.match(r"(Example|Constraints|Follow)", text):
            anchor = ""
            m = re.match(r"Example\s+(\d+)", text)
            if m:
                anchor = f"ex{m.group(1)}"
            elif text.startswith("Constraints"):
                anchor = "constraints"
            elif text.startswith("Follow"):
                anchor = "followup"
            self.blocks.append(Block("heading", runs=runs, anchor=anchor))
            return
        self.blocks.append(Block(kind, runs=runs, bullet=bullet))

    # -- events
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("meta", "br") and tag == "br":
            if self.pre:
                self._add_text("\n")
            else:
                self._add_text(" ")
            return
        if tag == "p":
            self._flush()
        elif tag == "pre":
            self._flush()
            self.pre += 1
        elif tag == "div":
            self._flush()
            if "example-block" in (a.get("class") or ""):
                self.in_example_div += 1
                self.example_lines = []
        elif tag in ("ul", "ol"):
            self._flush()
            self.list_stack.append([tag, 0])
        elif tag == "li":
            self._flush()
            if self.list_stack:
                self.list_stack[-1][1] += 1
        elif tag in ("code", "tt"):
            if not self.flags["code"]:
                self.code_id += 1
            self.flags["code"] += 1
        elif tag in ("strong", "b"):
            self.flags["bold"] += 1
        elif tag in ("em", "i"):
            self.flags["italic"] += 1
        elif tag == "sup":
            self.flags["sup"] += 1
        elif tag == "img":
            self._flush()
            self.blocks.append(Block("img", src=a.get("src", "")))
        elif tag in ("script", "style"):
            self.skip += 1

    def handle_endtag(self, tag):
        if tag == "p":
            self._flush()
        elif tag == "pre":
            self._flush_pre()
            self.pre -= 1
        elif tag == "div":
            self._flush()
            if self.in_example_div:
                self.in_example_div -= 1
                if self.example_lines:
                    self.blocks.append(Block("example", lines=self.example_lines, mixed=True))
                self.example_lines = []
        elif tag in ("ul", "ol"):
            self._flush()
            if self.list_stack:
                self.list_stack.pop()
        elif tag == "li":
            kind, n = self.list_stack[-1] if self.list_stack else ("ul", 1)
            self._flush("li", bullet="•" if kind == "ul" else f"{n}.")
        elif tag in ("code", "tt"):
            self.flags["code"] = max(0, self.flags["code"] - 1)
        elif tag in ("strong", "b"):
            self.flags["bold"] = max(0, self.flags["bold"] - 1)
        elif tag in ("em", "i"):
            self.flags["italic"] = max(0, self.flags["italic"] - 1)
        elif tag == "sup":
            self.flags["sup"] = max(0, self.flags["sup"] - 1)
        elif tag in ("script", "style"):
            self.skip = max(0, self.skip - 1)

    def handle_data(self, data):
        if self.skip:
            return
        self._add_text(data)

    def _flush_pre(self):
        # split accumulated runs at "\n" into lines
        lines: list[list[Run]] = [[]]
        for r in self.runs:
            parts = r.text.split("\n")
            for i, part in enumerate(parts):
                if i > 0:
                    lines.append([])
                if part:
                    lines[-1].append(Run(part, code=True, bold=r.bold, italic=r.italic))
        self.runs = []
        while lines and not "".join(x.text for x in lines[-1]).strip():
            lines.pop()
        while lines and not "".join(x.text for x in lines[0]).strip():
            lines.pop(0)
        if lines:
            self.blocks.append(Block("example", lines=lines))

    def close(self):
        super().close()
        self._flush()


_LABEL = re.compile(r"(Input|Output|Explanation)\s*:?")


def _group_examples(blocks: list[Block]) -> list[Block]:
    """<p>Input: ..</p><p>Output: ..</p> paragraphs after an Example heading -> one box."""
    out: list[Block] = []
    cur: Block | None = None
    for b in blocks:
        is_label = (b.kind == "p" and b.runs and b.runs[0].bold
                    and _LABEL.match(b.runs[0].text.strip()))
        if is_label and out and (out[-1].kind == "heading" and out[-1].anchor.startswith("ex")
                                 or cur is not None):
            if cur is None:
                cur = Block("example", mixed=True)
                out.append(cur)
            cur.lines.append(b.runs)
            continue
        if cur is not None and b.kind == "p" and cur.lines and not _LABEL.match(
                (b.runs[0].text.strip() if b.runs else "")) and \
                cur.lines[-1][0].text.strip().startswith("Explanation"):
            cur.lines.append(b.runs)      # continuation of the explanation
            continue
        cur = None
        out.append(b)
    return out


def parse(content: str) -> list[Block]:
    p = _Parser()
    p.feed(content)
    p.close()
    return _group_examples(p.blocks)


# -------------------------------------------------------------------- layout
@dataclass
class _Word:
    text: str
    run: Run
    space_before: bool
    first: bool = False     # first word of a code run
    last: bool = False
    font: object = None
    width: float = 0.0


class Doc:
    def __init__(self, fonts: FontBook, problem: dict, width: int, image_dir: Path):
        self.fonts = fonts
        self.problem = problem
        self.width = width
        self.image_dir = image_dir
        self.blocks = parse(problem["content"])
        self.anchors: dict[str, int] = {"top": 0}
        self.image: Image.Image | None = None

    # -- text measurement
    def _font(self, run: Run, mono_in_example=False):
        f = self.fonts
        if run.code:
            m = f.mono(MONO if not mono_in_example else MONO)
            return m.bold if run.bold else m.regular
        if run.sup:
            return f.ui(SANS - 8, bold=run.bold)
        return f.ui(SANS, bold=run.bold)

    def _words(self, runs: list[Run], example=False) -> list[_Word]:
        words: list[_Word] = []
        pending_space = False
        for r in runs:
            if r.sup:
                f = self.fonts.mono(MONO - 7).regular if r.code else self.fonts.ui(SANS - 8, bold=r.bold)
                w = _Word(r.text.strip(), r, False, font=f)
                w.width = f.getlength(w.text)
                words.append(w)
                continue
            toks = re.findall(r"\s+|\S+", r.text)
            if r.text[:1].isspace():
                pending_space = True
            for t in toks:
                if t.isspace():
                    pending_space = True
                    continue
                w = _Word(t, r, pending_space and bool(words), font=self._font(r, example))
                w.width = w.font.getlength(t)
                words.append(w)
                pending_space = False
            if r.text[-1:].isspace():
                pending_space = True
        if not example:
            def cont(i):   # word i continues the chip of word i-1
                a, b = words[i - 1], words[i]
                return a.run.code and b.run.code and (a.run.grp == b.run.grp or not b.space_before)
            for i, w in enumerate(words):
                if not w.run.code or w.run.sup:
                    continue
                w.first = i == 0 or not cont(i)
                w.last = i == len(words) - 1 or not cont(i + 1)
                w.width += (6 if w.first else 0) + (6 if w.last else 0)
        return words

    def _wrap(self, words: list[_Word], max_w: float, example=False) -> list[list[tuple[_Word, float]]]:
        space_w = self.fonts.ui(SANS).getlength(" ") if not example else self.fonts.mono(MONO).char_w
        lines: list[list[tuple[_Word, float]]] = [[]]
        x = 0.0
        for w in words:
            sp = space_w if (w.space_before and lines[-1]) else 0
            if lines[-1] and x + sp + w.width > max_w:
                lines.append([])
                x = 0.0
                sp = 0
            x += sp
            lines[-1].append((w, x))
            x += w.width
        return lines

    # -- drawing
    def _draw_line(self, d: ImageDraw.ImageDraw, x0: float, y: float, line, example=False,
                   lh: int = LINE_H):
        mono = self.fonts.mono(MONO)
        # chip backgrounds for contiguous words of one code run
        if not example:
            i = 0
            while i < len(line):
                w, x = line[i]
                if w.run.code:
                    j = i
                    while (j + 1 < len(line) and line[j + 1][0].run.code and
                           (line[j + 1][0].run.grp == w.run.grp or not line[j + 1][0].space_before)):
                        j += 1
                    xs = x0 + x
                    xe = x0 + line[j][1] + line[j][0].width
                    d.rounded_rectangle([xs, y + 3, xe, y + lh - 5], radius=6, fill=C.CHIP_BG,
                                        outline=C.CHIP_LINE)
                    i = j + 1
                else:
                    i += 1
        for w, x in line:
            col = C.TEXT_STRONG if (w.run.bold or w.run.code) else C.TEXT
            if example:
                col = C.TEXT_STRONG if w.run.bold else C.TEXT
            tx = x0 + x + (6 if w.first else 0)
            ty = y + (lh - (MONO if w.run.code else SANS) * 1.2) / 2 - 1
            if w.run.code:
                ty = y + (lh - MONO * 1.15) / 2 - 3
            if w.run.sup:
                ty = y + 4
            d.text((tx, ty), w.text, font=w.font, fill=col)

    def _img_for(self, src: str) -> Image.Image | None:
        name = re.sub(r"^https?://assets\.leetcode\.com/uploads/", "", src).replace("/", "__")
        name = name.replace("-", "_")
        p = self.image_dir / name
        if not p.exists():
            return None
        im = Image.open(p)
        return im.convert("RGBA")

    def render(self) -> Image.Image:
        W = self.width
        pad = 36
        cw = W - 2 * pad
        ops: list = []          # (y, callable(draw, img))
        y = 26

        # ---- title row
        tf = self.fonts.ui(34, bold=True)
        title = f"{self.problem['questionFrontendId']}. {self.problem['title']}"
        ops.append(("title", y, title))
        y += 62
        ops.append(("meta", y, None))
        y += 70

        for b in self.blocks:
            if b.kind == "heading":
                if b.anchor:
                    self.anchors[b.anchor] = y
                words = self._words(b.runs)
                lines = self._wrap(words, cw)
                y += 16
                for ln in lines:
                    ops.append(("line", y, ln, pad, False, LINE_H))
                    y += LINE_H
                y += 6
            elif b.kind == "p":
                words = self._words(b.runs)
                lines = self._wrap(words, cw)
                for ln in lines:
                    ops.append(("line", y, ln, pad, False, LINE_H))
                    y += LINE_H
                y += 14
            elif b.kind == "li":
                words = self._words(b.runs)
                lines = self._wrap(words, cw - 40)
                ops.append(("bullet", y, b.bullet, pad + 12))
                for ln in lines:
                    ops.append(("line", y, ln, pad + 40, False, LINE_H))
                    y += LINE_H
                y += 4
            elif b.kind == "example":
                mono = self.fonts.mono(MONO)
                inner = cw - 34
                all_lines = []
                for runs in b.lines:
                    words = self._words(runs, example=not b.mixed)
                    all_lines += self._wrap(words, inner, example=not b.mixed) or [[]]
                lh = LINE_H if b.mixed else 34
                h = len(all_lines) * lh
                y += 4
                ops.append(("bar", y, h))
                for ln in all_lines:
                    ops.append(("line", y, ln, pad + 22, not b.mixed, lh))
                    y += lh
                y += 18
            elif b.kind == "img":
                im = self._img_for(b.src)
                if im is None:
                    continue
                s = min(1.0, (cw - 8) / im.width) * 1.0
                nw, nh = max(1, int(im.width * s)), max(1, int(im.height * s))
                y += 6
                ops.append(("img", y, im.resize((nw, nh), Image.LANCZOS), pad))
                y += nh + 18

        H = y + 400
        img = Image.new("RGB", (W, H), C.PANEL_BG)
        d = ImageDraw.Draw(img)
        for op in ops:
            kind = op[0]
            if kind == "title":
                d.text((pad, op[1]), op[2], font=tf, fill=C.TEXT_STRONG)
            elif kind == "meta":
                self._draw_meta(d, pad, op[1])
            elif kind == "line":
                _, yy, ln, x0, ex, lh = op
                self._draw_line(d, x0, yy, ln, example=ex, lh=lh)
            elif kind == "bullet":
                _, yy, b, x0 = op
                if b == "•":
                    d.ellipse([x0 + 2, yy + 16, x0 + 10, yy + 24], fill=C.MUTED)
                else:
                    d.text((x0 - 4, yy + 4), b, font=self.fonts.ui(SANS), fill=C.TEXT)
            elif kind == "bar":
                _, yy, h = op
                d.rounded_rectangle([pad, yy, pad + 3, yy + h], radius=2, fill=hex_line())
            elif kind == "img":
                _, yy, im, x0 = op
                d.rounded_rectangle([x0, yy, x0 + im.width, yy + im.height], radius=6,
                                    fill=(255, 255, 255))
                img.paste(im, (x0, yy), im)
        self.image = img
        self.total_h = y
        return img

    def _draw_meta(self, d: ImageDraw.ImageDraw, x: int, y: int):
        f = self.fonts.ui(21, bold=True)
        f2 = self.fonts.ui(21)
        diff = self.problem["difficulty"]
        col = {"Easy": C.EASY, "Medium": C.MED, "Hard": C.HARD}[diff]
        bg = {"Easy": (18, 51, 47), "Medium": (60, 47, 10), "Hard": (62, 22, 32)}[diff]
        w = d.textlength(diff, font=f) + 36
        d.rounded_rectangle([x, y, x + w, y + 38], radius=19, fill=bg)
        d.text((x + 18, y + 7), diff, font=f, fill=col)
        x += w + 14
        for label, kind in (("Topics", "tag"), ("Companies", "build"), ("Hint", "bulb")):
            tw = d.textlength(label, font=f2)
            ww = tw + 62
            d.rounded_rectangle([x, y, x + ww, y + 38], radius=19, fill=C.BAR_BG)
            cx, cy = x + 25, y + 19
            if kind == "tag":
                d.polygon([(cx - 8, cy - 7), (cx + 3, cy - 7), (cx + 9, cy), (cx + 1, cy + 8),
                           (cx - 8, cy)], outline=C.MUTED, width=2)
            elif kind == "build":
                d.rectangle([cx - 7, cy - 8, cx + 7, cy + 8], outline=C.MUTED, width=2)
                d.line([(cx, cy - 4), (cx, cy + 5)], fill=C.MUTED, width=2)
            else:
                d.ellipse([cx - 7, cy - 9, cx + 7, cy + 5], outline=C.MUTED, width=2)
                d.line([(cx - 3, cy + 9), (cx + 3, cy + 9)], fill=C.MUTED, width=2)
            d.text((x + 44, y + 8), label, font=f2, fill=C.MUTED)
            x += ww + 12

    def scroll_for(self, target: str, view_h: int) -> int:
        if self.image is None:
            self.render()
        y = self.anchors.get(target, 0)
        off = max(0, y - 24) if target != "top" else 0
        return int(min(off, max(0, self.total_h - view_h + 40)))


def hex_line():
    return (74, 74, 74)
