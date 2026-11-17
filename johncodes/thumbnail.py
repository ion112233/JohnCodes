"""YouTube thumbnails: 1280x720, four layouts per episode.

Faceless-channel recipe: the type is the subject. Every layout shares one
palette (Darcula card dark + Python yellow) so the series reads as a brand in
a subscriber's feed, puts a 2-3 word headline at 110px+ so it survives the
120px mobile thumbnail, and keeps the bottom-right corner clear for YouTube's
duration stamp.

    1 headline   big headline + tilted editor window
    2 code       headline over a wide, bleeding code window
    3 curiosity  a big question, broken code, a red result strip, a huge "?"
    4 number     giant outlined episode number + progress bar

Copy comes from the optional ``thumbnail`` block of the script (see
``content/question_schema.json``); anything missing falls back to the script.
Drawn at 2x and downscaled with LANCZOS for clean edges.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

from . import theme
from .config import Config
from .fonts import FontBook
from .highlight import highlight_python
from .question import Question
from .scenes import _lc, _uc
from .util import mix_color, wrap_text

W0, H0 = 1280, 720
K = 2
YELLOW = theme.hx("FFD43B")
SKY = theme.hx("8FB8DE")
INK = theme.hx("1B1C1F")
WHITE = theme.hx("F5F6F8")
SOFT = theme.hx("C4C9D2")
ALERT = theme.hx("FF6B6B")
OK = theme.hx("7BD88F")
_SF = "/System/Library/Fonts/SFNS.ttf"
MAX_BYTES = 2_000_000        # YouTube's thumbnail upload limit is 2 MB

VARIANTS = ("headline", "code", "curiosity", "number")


def S(v: float) -> int:
    return int(round(v * K))


# --------------------------------------------------------------------------- copy
@dataclass
class _Copy:
    headline: list[str]
    hook: str
    snippet: str
    question: list[str]
    bad: str
    result: str
    result_ok: bool


def _first_code(q: Question, kinds=("code", "gotcha")) -> str:
    for s in q.segments:
        if s.type in kinds and s.code:
            return s.code
    return q.final_code


def _copy(q: Question) -> _Copy:
    t = q.thumbnail
    headline = (t.headline if t and t.headline else _lc(q.title)).split("\n")
    if len(headline) == 1 and len(headline[0]) > 14:
        words = headline[0].split()
        mid = max(1, len(words) // 2)
        headline = [" ".join(words[:mid]), " ".join(words[mid:])]
    snippet = (t.snippet if t and t.snippet else "\n".join(_first_code(q).split("\n")[:6]))

    gotcha = next((s for s in q.segments if s.type == "gotcha"), None)
    bad = t.bad if t and t.bad else (gotcha.code if gotcha else snippet)
    result = t.result if t and t.result else ""
    if not result and gotcha and gotcha.error:
        result = [ln for ln in gotcha.error.split("\n") if ln.strip()][-1].strip()
    question = (t.question if t and t.question else "\n".join(headline)).split("\n")
    return _Copy(headline=headline, hook=(t.hook if t and t.hook else _lc(q.prompt)[:48]),
                 snippet=snippet, question=question, bad=bad, result=result,
                 result_ok=bool(t and t.result_ok))


# --------------------------------------------------------------------------- type
_HEAVY: dict[tuple[int, int], ImageFont.FreeTypeFont] = {}


def _heavy(fonts: FontBook, size: int, weight: int = 900) -> ImageFont.FreeTypeFont:
    """SF at display weight — falls back to the UI bold if the variable font is absent."""
    key = (size, weight)
    if key not in _HEAVY:
        try:
            f = ImageFont.truetype(_SF, size)
            f.set_variation_by_axes([96, 96, 400, weight])    # width, optical, grade, weight
        except Exception:
            f = fonts.ui(size, bold=True)
        _HEAVY[key] = f
    return _HEAVY[key]


def _fit_block(fonts, lines, max_w, max_h, hi, lo, weight=900, lead=1.04):
    for size in range(S(hi), S(lo) - 1, -2):
        f = _heavy(fonts, size, weight)
        if (max(f.getlength(ln) for ln in lines) <= S(max_w)
                and size * lead * len(lines) <= S(max_h)):
            return f, size
    return _heavy(fonts, S(lo), weight), S(lo)


def _line_colors(n: int):
    return [YELLOW] if n == 1 else [WHITE if i % 2 == 0 else YELLOW for i in range(n)]


def _draw_lines(d, lines, font, size, x, y, lead=1.04) -> int:
    """Draw headline lines (top at y); returns the y just below the block."""
    cols = _line_colors(len(lines))
    for i, ln in enumerate(lines):
        base = y + size * 0.80 + i * size * lead
        d.text((x + S(4), base + S(6)), ln, font=font, fill=(8, 9, 11), anchor="ls")  # soft drop
        d.text((x, base), ln, font=font, fill=cols[i], anchor="ls")
    return int(y + size * lead * len(lines))


# --------------------------------------------------------------------------- pieces
def _background(glows) -> Image.Image:
    W, H = S(W0), S(H0)
    mask = Image.linear_gradient("L").resize((W, H))
    img = Image.composite(Image.new("RGB", (W, H), (13, 14, 17)),
                          Image.new("RGB", (W, H), (36, 38, 44)), mask).convert("RGBA")
    for cx, cy, r, color, alpha in glows:
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(layer).ellipse([S(cx - r), S(cy - r), S(cx + r), S(cy + r)],
                                      fill=(*color, alpha))
        img = Image.alpha_composite(img, layer.filter(ImageFilter.GaussianBlur(S(r * 0.45))))
    return img.convert("RGB")


def _badge(d, fonts, q: Question, x: float, y: float) -> None:
    if q.episode:
        label, series = f"EP {q.episode.number}", _uc(q.episode.series)
    else:
        label, series = q.difficulty.upper(), "PYTHON INTERVIEW"
    f = _heavy(fonts, S(40), 850)
    tw = d.textlength(label, font=f)
    padx, h = S(22), S(62)
    d.rounded_rectangle([S(x), S(y), S(x) + tw + 2 * padx, S(y) + h], radius=h // 2, fill=YELLOW)
    d.text((S(x) + padx, S(y) + h / 2), label, font=f, fill=INK, anchor="lm")
    d.text((S(x) + tw + 2 * padx + S(18), S(y) + h / 2), series,
           font=_heavy(fonts, S(30), 750), fill=SKY, anchor="lm")


def _window(fonts: FontBook, code: str, *, w: int, fs: int, max_h: int | None = None,
            filename: str = "solution.py", squiggle_last: bool = False) -> Image.Image:
    """A PyCharm-ish editor card (RGBA, rounded). Font shrinks to fit w / max_h."""
    lines = code.split("\n")
    longest = max(len(ln) for ln in lines)
    ndig, pad, tb = len(str(len(lines))), S(20), S(38)
    while fs > S(16):
        m = fonts.mono(fs)
        gut = m.char_w * ndig + S(22)
        h = tb + pad + len(lines) * m.line_h + pad - S(6)
        if m.char_w * longest + gut + 2 * pad <= w and (max_h is None or h <= max_h):
            break
        fs -= 1
    m = fonts.mono(fs)
    gut = m.char_w * ndig + S(22)
    h = int(tb + pad + len(lines) * m.line_h + pad - S(6))

    card = Image.new("RGBA", (w, h), theme.EDITOR_BG + (255,))
    d = ImageDraw.Draw(card)
    d.rectangle([0, 0, w, tb], fill=theme.PANEL_BG)
    for i, c in enumerate((theme.TRAFFIC_RED, theme.TRAFFIC_YELLOW, theme.TRAFFIC_GREEN)):
        cx = S(24) + i * S(26)
        d.ellipse([cx - S(7), tb / 2 - S(7), cx + S(7), tb / 2 + S(7)], fill=c)
    d.text((S(112), tb / 2), filename, font=fonts.ui(S(17)), fill=theme.TAB_INACTIVE_FG, anchor="lm")

    y = tb + pad
    for i, ln in enumerate(highlight_python(code)):
        d.text((pad, y), str(i + 1), font=m.regular, fill=theme.LINE_NUMBER)
        x = pad + gut
        for sp in ln:
            d.text((x, y), sp.text, font=m.italic if sp.italic else m.bold, fill=sp.color)
            x += m.char_w * len(sp.text)
        if squiggle_last and i == len(lines) - 1:
            _squiggle(d, pad + gut, x, y + m.line_h * 0.86)
        y += m.line_h

    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1], radius=S(16), fill=255)
    card.putalpha(mask)
    ImageDraw.Draw(card).rounded_rectangle([0, 0, w - 1, h - 1], radius=S(16),
                                           outline=theme.BORDER_LT, width=S(2))
    return card


def _squiggle(d, x0: float, x1: float, y: float) -> None:
    pts, x, up = [], x0, True
    while x < x1:
        pts.append((x, y - S(3) if up else y + S(3)))
        x += S(6)
        up = not up
    if len(pts) > 1:
        d.line(pts, fill=ALERT, width=S(3))


def _paste_card(img: Image.Image, card: Image.Image, x: float, y: float, angle: float = 0.0):
    if angle:
        card = card.rotate(angle, resample=Image.BICUBIC, expand=True)
    xy = (int(S(x)), int(S(y)))
    sh = card.split()[3].filter(ImageFilter.GaussianBlur(S(16))).point(lambda v: int(v * 0.65))
    img.paste((0, 0, 0), (xy[0], xy[1] + S(16)), sh)
    img.paste(card.convert("RGB"), xy, card.split()[3])


def _progress_dots(d, q: Question, x: float, y: float) -> None:
    if not q.episode:
        return
    for i in range(q.episode.of):
        cx = S(x) + i * S(24)
        r = S(7)
        d.ellipse([cx - r, S(y) - r, cx + r, S(y) + r],
                  fill=YELLOW if i < q.episode.number else theme.BORDER_LT)


def _wrap(d, text, font, max_w):
    return wrap_text(text, font, S(max_w))


# --------------------------------------------------------------------------- layouts
def _v_headline(fonts, q, c) -> Image.Image:
    img = _background([(1010, 540, 360, theme.ACCENT, 95), (140, 60, 300, YELLOW, 24)])
    d = ImageDraw.Draw(img)
    _badge(d, fonts, q, 64, 50)
    f, size = _fit_block(fonts, c.headline, 650, 300, 170, 96)
    y = _draw_lines(d, c.headline, f, size, S(64), S(150))
    hf = _heavy(fonts, S(40), 650)
    for ln in _wrap(d, c.hook, hf, 620)[:2]:
        d.text((S(64), y + S(26)), ln, font=hf, fill=SOFT)
        y += S(50)
    _paste_card(img, _window(fonts, c.snippet, w=S(500), fs=S(32), max_h=S(360)), 745, 285, -3.5)
    _progress_dots(d, q, 72, 684)
    return img


def _v_code(fonts, q, c) -> Image.Image:
    img = _background([(900, 640, 420, theme.ACCENT_ORANGE, 55), (1100, 60, 320, theme.ACCENT, 70)])
    d = ImageDraw.Draw(img)
    _badge(d, fonts, q, 64, 44)
    pf = _heavy(fonts, S(32), 700)
    pw = d.textlength(c.hook, font=pf) + S(44)
    d.rounded_rectangle([S(1216) - pw, S(48), S(1216), S(106)], radius=S(29),
                        outline=SKY, width=S(3))
    d.text((S(1216) - pw / 2, S(77)), c.hook, font=pf, fill=WHITE, anchor="mm")
    f, size = _fit_block(fonts, c.headline, 1150, 250, 132, 84)
    y = _draw_lines(d, c.headline, f, size, S(64), S(128))
    top = y + S(28)
    code = "\n".join(c.snippet.split("\n")[:4])
    _paste_card(img, _window(fonts, code, w=S(1152), fs=S(52), max_h=S(H0) - top - S(10)),
                64, top / K)
    return img


def _v_curiosity(fonts, q, c) -> Image.Image:
    img = _background([(1010, 380, 360, ALERT if not c.result_ok else OK, 60),
                       (1050, 330, 260, YELLOW, 40)])
    d = ImageDraw.Draw(img)
    _badge(d, fonts, q, 64, 44)
    f, size = _fit_block(fonts, c.question, 745, 260, 124, 76)
    y = _draw_lines(d, c.question, f, size, S(64), S(124))

    strip_h, gap = S(68), S(14)
    top = y + S(26)
    card = _window(fonts, c.bad, w=S(660), fs=S(30), max_h=S(H0 - 40) - top - strip_h - gap,
                   squiggle_last=bool(c.result) and not c.result_ok)
    _paste_card(img, card, 64, top / K)
    if c.result:
        sy = top + card.height + gap
        col = OK if c.result_ok else ALERT
        d.rounded_rectangle([S(64), sy, S(64) + S(660), sy + strip_h], radius=S(14),
                            fill=mix_color(theme.EDITOR_BG, col, 0.18), outline=col, width=S(3))
        rf = fonts.mono(S(26))
        text = c.result
        while rf.char_w * len(text) > S(660) - S(44) and rf.size > S(14):
            rf = fonts.mono(rf.size - 1)
        d.text((S(64) + S(22), sy + strip_h / 2), text, font=rf.bold, fill=col, anchor="lm")

    qm = Image.new("RGBA", (S(W0), S(H0)), (0, 0, 0, 0))
    ImageDraw.Draw(qm).text((S(1085), S(365)), "?", font=_heavy(fonts, S(600), 900),
                            fill=YELLOW + (255,), anchor="mm")
    qm = qm.rotate(9, resample=Image.BICUBIC, center=(S(1085), S(365)))
    glow = qm.filter(ImageFilter.GaussianBlur(S(26)))
    img = Image.alpha_composite(Image.alpha_composite(img.convert("RGBA"), glow), qm).convert("RGB")
    return img


def _v_number(fonts, q, c) -> Image.Image:
    img = _background([(900, 330, 400, theme.ACCENT, 90), (80, 700, 260, YELLOW, 22)])
    W, H = img.size
    num = f"{q.episode.number:02d}" if q.episode else q.difficulty.upper()
    nf = _heavy(fonts, S(450), 900)
    bb = nf.getbbox(num, anchor="ls")
    x = S(1250) - bb[2]
    y = S(330) - (bb[1] + bb[3]) // 2
    fill_m = Image.new("L", (W, H), 0)
    ImageDraw.Draw(fill_m).text((x, y), num, font=nf, fill=255, anchor="ls")
    outer = Image.new("L", (W, H), 0)
    ImageDraw.Draw(outer).text((x, y), num, font=nf, fill=255, anchor="ls",
                               stroke_width=S(6), stroke_fill=255)
    img.paste(YELLOW, mask=fill_m.point(lambda v: int(v * 0.18)))
    img.paste(YELLOW, mask=ImageChops.subtract(outer, fill_m))

    d = ImageDraw.Draw(img)
    series = (f"{_uc(q.episode.series)}  ·  EPISODE {q.episode.number} / {q.episode.of}"
              if q.episode else "PYTHON INTERVIEW")
    d.text((S(64), S(60)), series, font=_heavy(fonts, S(34), 800), fill=SKY, anchor="lm")
    d.rectangle([S(64), S(86), S(64) + S(110), S(86) + S(6)], fill=YELLOW)

    f, size = _fit_block(fonts, c.headline, 555, 300, 150, 90)
    block = int(size * 1.04 * len(c.headline))
    hook_f = _heavy(fonts, S(40), 650)
    top = S(560) - block
    y = _draw_lines(d, c.headline, f, size, S(64), top)
    d.text((S(64), y + S(18)), c.hook, font=hook_f, fill=SOFT)

    if q.episode:
        n, bx, by, bw, bh, g = q.episode.of, 64, 664, 1030, 16, 8
        seg = (bw - g * (n - 1)) / n
        for i in range(n):
            x0 = bx + i * (seg + g)
            col = (YELLOW if i == q.episode.number - 1 else
                   theme.ACCENT if i < q.episode.number - 1 else theme.BORDER_LT)
            d.rounded_rectangle([S(x0), S(by), S(x0 + seg), S(by + bh)], radius=S(8), fill=col)
    return img


_LAYOUTS = {"headline": _v_headline, "code": _v_code,
            "curiosity": _v_curiosity, "number": _v_number}


# --------------------------------------------------------------------------- api
def variants_for(q: Question) -> list[str]:
    return list(VARIANTS) if q.episode else [v for v in VARIANTS if v != "number"]


def _save(img: Image.Image, path: Path) -> Path:
    img.save(path, optimize=True)
    if path.stat().st_size > MAX_BYTES:        # YouTube rejects > 2 MB
        path.unlink()
        path = path.with_suffix(".jpg")
        img.save(path, quality=93, subsampling=0, optimize=True)
    return path


def render_thumbnails(cfg: Config, q: Question, out_dir: Path | None = None,
                      variants: list[str] | None = None) -> list[Path]:
    fonts = FontBook(cfg.fonts_path, cfg.mono_font, cfg.ui_font)
    out_dir = Path(out_dir or cfg.video_dir(q) / "thumbnails")
    out_dir.mkdir(parents=True, exist_ok=True)
    copy = _copy(q)
    paths = []
    for name in (variants or variants_for(q)):
        img = _LAYOUTS[name](fonts, q, copy).resize((W0, H0), Image.LANCZOS)
        n = VARIANTS.index(name) + 1
        paths.append(_save(img, out_dir / f"{q.id}_thumb_{n}_{name}.png"))
    return paths
