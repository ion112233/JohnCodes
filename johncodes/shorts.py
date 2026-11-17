"""Vertical YouTube Shorts (1080x1920, 31-57 s) cut from an already-rendered episode.

Workflow
    1. ``build`` / ``timeline`` write ``output/<id>/video/timeline.json`` — every scene's
       time range and every spoken word's timestamp.
    2. ``plan_shorts`` scans that timeline for the most watchable 31-57 s windows
       (error reveals, quick-check cards, terminal payoffs), cut on sentence boundaries
       so nothing starts or ends mid-word, and writes ``shorts/plan.json`` (editable).
    3. ``render_short`` re-frames the source video for a phone: blurred-free branded
       background, the IDE (or card) cropped and enlarged so the code stays readable,
       a big hook headline, word-by-word captions with the spoken word highlighted,
       and a "full lesson" end card. Audio is cut straight from the source.

Every Short is verified to land strictly inside YouTube's 30-60 s window.
"""
from __future__ import annotations

import bisect
import dataclasses
import json
import re
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from . import theme
from .config import Config
from .fonts import FontBook
from .question import Question
from .scenes import CompareScene, QuestionCard, ReplScene, TopicCard
from .thumbnail import INK, SKY, SOFT, WHITE, YELLOW, _heavy
from .util import ease_out_cubic, wrap_text

SW, SH = 1080, 1920
FPS = 30
MIN_S, MAX_S, IDEAL_S = 31.0, 57.0, 45.0     # strictly inside 30-60 s
SRC_W, SRC_H = 1920, 1080

PANEL_W, PANEL_H = 1000, 850
SLOT_CENTER = 925                             # vertical centre of the video panel
CAPTION_Y = 1450                              # centre of the caption line
HOOK_TOP = 165

# Editor scenes are cropped out of the source video (the IDE can't be re-laid-out);
# the console crop keeps the Run panel's full-width text. Cards / REPL / compare are
# re-rendered natively at panel size from the script, so their text stays big.
_CROPS = {"ide": (324, 52, 1504, 1055), "term": (0, 52, 960, 868), "card": (120, 0, 1800, 1080)}
_KIND_CROP = {"code": "ide", "terminal": "term", "gotcha": "term"}
_NATIVE = {"question", "topic", "repl", "compare"}

_WEIGHT = {"gotcha": 3.0, "question": 3.0, "compare": 1.0, "terminal": 1.5, "repl": 1.5,
           "code": 1.0, "topic": 0.4, "episode": -4.0, "title": -4.0, "recap": -4.0,
           "explain": -4.0}
_HOOKY = re.compile(r"^(here|notice|watch|careful|but|why|what|never|most|imagine|look|remember|"
                    r"one|this|every|if you)\b", re.I)


# --------------------------------------------------------------------------- plan
@dataclass
class ShortPlan:
    start: float
    end: float
    hook: str
    title: str
    description: str
    tags: list[str]
    score: float
    why: str
    chapter: str = ""

    @property
    def duration(self) -> float:
        return self.end - self.start

    @property
    def slug(self) -> str:
        return re.sub(r"[^a-z0-9]+", "-", self.hook.lower()).strip("-")[:42] or "short"


@dataclass
class _Sentence:
    start: float
    end: float
    text: str
    scene: int


def load_timeline(cfg: Config, q: Question) -> dict:
    path = cfg.video_dir(q.id) / "timeline.json"
    if not path.exists():
        raise SystemExit(f"{q.id}: no timeline.json — run `python -m johncodes timeline "
                         f"{q.source_path}` (or rebuild the video) first")
    return json.loads(path.read_text())


def _sentences(tl: dict) -> list[_Sentence]:
    out: list[_Sentence] = []
    for clip in tl["clips"]:
        cur: list = []
        for w, s, e in clip["words"]:
            cur.append((w, s, e))
            if re.search(r"[.!?][\"')\]]*$", w):
                out.append(_Sentence(cur[0][1], cur[-1][2], " ".join(x[0] for x in cur), clip["scene"]))
                cur = []
        if cur:
            out.append(_Sentence(cur[0][1], cur[-1][2], " ".join(x[0] for x in cur), clip["scene"]))
    out.sort(key=lambda s: s.start)
    return out


def _chapter_at(tl: dict, t: float) -> str:
    label = ""
    for ts, name in tl["chapters"]:
        if ts <= t + 1.0:
            label = name
    return label


def _windows(tl: dict, sents: list[_Sentence]):
    """Every [start, end] that begins/ends on sentence boundaries and fits MIN_S..MAX_S."""
    scenes = tl["scenes"]
    for i, si in enumerate(sents):
        sc = scenes[si.scene]
        ws = max(sc["start"], si.start - 0.8) if (i == 0 or sents[i - 1].scene != si.scene) \
            else si.start - 0.35
        ws = max(0.0, ws)
        for j in range(i, len(sents)):
            sj = sents[j]
            nxt = sents[j + 1].start - 0.05 if j + 1 < len(sents) else 1e9
            we = min(sj.end + 0.8, scenes[sj.scene]["end"], nxt, tl["total"])
            if we - ws > MAX_S:
                break
            if we - ws >= MIN_S:
                yield i, j, ws, we


def _score(tl: dict, sents, i, ws, we):
    scenes, score, tags = tl["scenes"], 0.0, []
    present = {}
    for sc in scenes:
        ov = min(we, sc["end"]) - max(ws, sc["start"])
        if ov >= 2.5:
            present[sc["kind"]] = present.get(sc["kind"], 0.0) + ov
            w = _WEIGHT.get(sc["kind"], 0.0)
            if sc["kind"] == "question" and ov < (sc["end"] - sc["start"]) - 1.5:
                w = 0.5            # half a quick-check is worse than none
            score += w
            if w >= 1.5:
                tags.append(sc["kind"])
    first = sents[i]
    if "?" in first.text or _HOOKY.match(first.text):
        score += 1.5
        tags.append("hooky opener")
    sc0 = scenes[first.scene]
    if ws <= sc0["start"] + 0.9:
        score += 1.0
    if any(we >= sc["end"] - 0.05 for sc in scenes if ws < sc["end"] <= we + 0.01):
        score += 1.0
    for sc in scenes:                      # a Short stays inside one topic
        if sc["kind"] == "topic" and ws + 1.0 < sc["start"] < we - 1.0:
            score -= 2.5
    score -= abs((we - ws) - IDEAL_S) / 12.0
    return score, tags, present


_ERR = re.compile(r"^([A-Za-z]*(?:Error|Exception|Warning))\b")


def _clean(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def _make_hook(q: Question, tl: dict, ws: float, we: float, variety: int) -> str:
    scenes = [sc for sc in tl["scenes"] if min(we, sc["end"]) - max(ws, sc["start"]) >= 2.5]
    by_kind = {sc["kind"]: sc for sc in scenes}
    secs = int(round((we - ws) / 5.0) * 5)
    if "gotcha" in by_kind:
        err = _clean((by_kind["gotcha"]["info"].get("error") or [""])[0])
        m = _ERR.match(err)
        if m:
            t = m.group(1)
            a = "an" if t[0] in "AEIOU" else "a"
            return [f"this {t} trips up every beginner", f"why does this raise {a} {t}?",
                    f"you will hit this {t} today"][variety % 3]
        return ["the mistake that bites every beginner", "this bug has no error message",
                "watch out for this one"][variety % 3]
    if "question" in by_kind:
        quest = _clean(by_kind["question"]["info"].get("question"))
        last = re.split(r"(?<=[.?!])\s+", quest)[-1] if quest else ""
        pick = quest if 0 < len(quest) <= 72 else last
        return (pick if 0 < len(pick) <= 72 else
                ["quick check: can you get this right?", "can you answer this?"][variety % 2])
    if "compare" in by_kind:
        l, r = by_kind["compare"]["info"].get("left"), by_kind["compare"]["info"].get("right")
        if l and r and len(l) <= 18 and len(r) <= 18:
            return f"{l} vs {r}".lower()
        return "which one is better?"
    topic = _clean(_chapter_at(tl, ws)).lower()
    if not topic or re.search(r"[\"_=()]|intro|recap", topic):
        topic = q.title.lower()
    return f"{topic} in {secs} seconds"


def _describe(q: Question, hook: str, tags: list[str]) -> tuple[str, str]:
    ep = q.episode
    series = f"{ep.series} — EP {ep.number}/{ep.of}" if ep else "Python interview question"
    title = (hook[:1].upper() + hook[1:])[:78] + " #Shorts"
    mins = f" (~{q.target_minutes:g} min)" if q.target_minutes else ""
    desc = (f"{hook[:1].upper() + hook[1:]}\n\n"
            f"A clip from {series}: {q.title}.\n"
            f"Watch the full lesson{mins}: [add the full video link here]\n\n"
            + " ".join(tags))
    return title, desc


def _tags(q: Question) -> list[str]:
    words = [w for w in re.findall(r"[a-z]+", q.title.lower()) if len(w) > 3][:2]
    return ["#python", "#learnpython", "#coding", "#programming", "#shorts"] + [f"#{w}" for w in words]


def plan_shorts(q: Question, tl: dict, count: int | None = None) -> list[ShortPlan]:
    sents = _sentences(tl)
    if not sents:
        raise SystemExit(f"{q.id}: timeline has no narration — nothing to cut")
    cands = []
    for i, j, ws, we in _windows(tl, sents):
        score, tags, _ = _score(tl, sents, i, ws, we)
        cands.append([score, ws, we, tags])

    def greedy(limit: int, floor: float):
        chosen, pool = [], [list(c) for c in cands]
        while len(chosen) < limit and pool:
            pool.sort(key=lambda c: -c[0])
            best = pool.pop(0)
            if best[0] < floor and chosen:
                break
            chosen.append(best)
            ch = _chapter_at(tl, best[1])
            pool = [c for c in pool if c[2] <= best[1] - 1.5 or c[1] >= best[2] + 1.5]
            for c in pool:                       # spread the Shorts across the lesson
                if _chapter_at(tl, c[1]) == ch:
                    c[0] -= 1.5
        return chosen

    minutes = tl["total"] / 60.0
    cap = 2 if minutes < 7 else 3 if minutes < 11 else 4
    if count is None:
        strong = len(greedy(4, 5.5))
        count = min(cap, max(2, strong))
    chosen = sorted(greedy(count, -99.0), key=lambda c: c[1])

    plans = []
    for k, (score, ws, we, tags) in enumerate(chosen):
        hook = _make_hook(q, tl, ws, we, q.episode.number + k if q.episode else k)
        tg = _tags(q)
        title, desc = _describe(q, hook, tg)
        plans.append(ShortPlan(round(ws, 2), round(we, 2), hook, title, desc, tg, round(score, 2),
                               ", ".join(dict.fromkeys(tags)) or "narration", _chapter_at(tl, ws)))
    return plans


def save_plan(path: Path, tl: dict, plans: list[ShortPlan]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"timeline_total": tl["total"],
                                "shorts": [asdict(p) for p in plans]}, indent=2, ensure_ascii=False))


def load_plan(path: Path, tl: dict) -> list[ShortPlan] | None:
    """Reuse an (editable) plan.json — unless the video was re-rendered since."""
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    if abs(data.get("timeline_total", -1) - tl["total"]) > 0.05:
        return None
    return [ShortPlan(**s) for s in data["shorts"]]


# --------------------------------------------------------------------------- render
def _fmt(sec: float) -> str:
    m, s = divmod(int(round(sec)), 60)
    return f"{m}:{s:02d}"


def _background() -> Image.Image:
    mask = Image.linear_gradient("L").resize((SW, SH))
    img = Image.composite(Image.new("RGB", (SW, SH), (13, 14, 17)),
                          Image.new("RGB", (SW, SH), (36, 38, 44)), mask).convert("RGBA")
    for cx, cy, r, color, alpha in ((900, 300, 420, theme.ACCENT, 95), (120, 1500, 380, YELLOW, 26)):
        layer = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
        ImageDraw.Draw(layer).ellipse([cx - r, cy - r, cx + r, cy + r], fill=(*color, alpha))
        img = Image.alpha_composite(img, layer.filter(ImageFilter.GaussianBlur(r * 0.45)))
    return img.convert("RGB")


def _caption_groups(words: list) -> list[dict]:
    groups, cur = [], []
    for w in words:
        cur.append(w)
        text = " ".join(x[0] for x in cur)
        if len(cur) >= 4 or len(text) >= 16 or re.search(r"[,.;:!?]$", w[0]):
            groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)
    out = []
    for k, g in enumerate(groups):
        nxt = groups[k + 1][0][1] if k + 1 < len(groups) else 1e9
        out.append({"start": g[0][1] - 0.04, "end": min(nxt, g[-1][2] + 0.35), "words": g})
    return out


class _Compositor:
    def __init__(self, cfg: Config, fonts: FontBook, q: Question, tl: dict, plan: ShortPlan):
        self.q, self.tl, self.plan = q, tl, plan
        self.dur = plan.duration
        self.bg = _background()
        self.starts = [sc["start"] for sc in tl["scenes"]]
        self.kinds = [sc["kind"] for sc in tl["scenes"]]
        words = [[w, s - plan.start, e - plan.start] for c in tl["clips"] for w, s, e in c["words"]
                 if e > plan.start and s < plan.end]
        self.groups = _caption_groups(words)
        self.cap_fonts = {sz: _heavy(fonts, sz, 900) for sz in range(56, 90, 2)}
        self.hook_lines, self.hook_font = self._fit_hook(fonts, plan.hook)
        self.hook_lh = self.hook_font.size * 1.14
        self.badge_y = int(HOOK_TOP + len(self.hook_lines) * self.hook_lh + 20)
        self.fonts, self.vcfg = fonts, dataclasses.replace(cfg, width=PANEL_W, height=PANEL_H)
        self._native: dict[int, object] = {}
        self.badge_font = _heavy(fonts, 34, 800)
        self.cta_font = _heavy(fonts, 46, 800)
        self._panel: dict[int, tuple[Image.Image, Image.Image]] = {}

    # -- layout pieces
    @staticmethod
    def _fit_hook(fonts, hook):
        """Biggest type that fits in 2 lines (3 only if it must), never splitting a word."""
        for max_lines, floor in ((2, 68), (3, 52)):
            for size in range(104, floor - 1, -4):
                f = _heavy(fonts, size, 900)
                lines = wrap_text(hook, f, 940)
                if len(lines) <= max_lines and max(f.getlength(ln) for ln in lines) <= 940:
                    return lines, f
        f = _heavy(fonts, 52, 900)
        return wrap_text(hook, f, 940)[:3], f

    def _native_scene(self, idx: int):
        """The scene re-rendered at panel size from the script, or None to crop the video."""
        if idx not in self._native:
            sc = self.tl["scenes"][idx]
            seg = self.q.segments[sc["segment"]] if sc["segment"] is not None else None
            dur, c, f, scene = sc["end"] - sc["start"], self.vcfg, self.fonts, None
            if seg is not None and sc["kind"] in _NATIVE:
                if sc["kind"] == "question":
                    scene = QuestionCard(c, f, seg.question or "", seg.answer, dur,
                                         sc["info"].get("reveal", 10.0))
                elif sc["kind"] == "topic":
                    scene = TopicCard(c, f, seg.card_title or "", seg.card_subtitle, dur)
                elif sc["kind"] == "repl":
                    scene = ReplScene(c, f, seg.lines, dur, lead=0.4)
                else:
                    scene = CompareScene(c, f, left_label=seg.left_label, left_code=seg.left_code or "",
                                         right_label=seg.right_label, right_code=seg.right_code or "",
                                         verdict=seg.verdict, duration=dur)
            self._native[idx] = scene
        return self._native[idx]

    def _panel_assets(self, ph: int):
        if ph not in self._panel:
            mask = Image.new("L", (PANEL_W, ph), 0)
            ImageDraw.Draw(mask).rounded_rectangle([0, 0, PANEL_W - 1, ph - 1], radius=28, fill=255)
            sh = Image.new("L", (PANEL_W + 160, ph + 160), 0)
            ImageDraw.Draw(sh).rounded_rectangle([80, 80, 80 + PANEL_W, 80 + ph], radius=28, fill=170)
            self._panel[ph] = (mask, sh.filter(ImageFilter.GaussianBlur(26)))
        return self._panel[ph]

    def scene_at(self, t_abs: float) -> int:
        return max(0, bisect.bisect_right(self.starts, t_abs) - 1)

    def _draw_caption(self, d: ImageDraw.ImageDraw, t: float) -> bool:
        grp = next((g for g in self.groups if g["start"] <= t < g["end"]), None)
        if grp is None:
            return False
        words = grp["words"]
        size = 84
        while size > 56:
            f = self.cap_fonts[size]
            if sum(f.getlength(w[0]) for w in words) + f.getlength(" ") * (len(words) - 1) <= 960:
                break
            size -= 2
        f = self.cap_fonts[size]
        sp = f.getlength(" ")
        total = sum(f.getlength(w[0]) for w in words) + sp * (len(words) - 1)
        active = max((k for k, w in enumerate(words) if w[1] <= t), default=0)
        x = (SW - total) / 2
        for k, w in enumerate(words):
            d.text((x, CAPTION_Y), w[0], font=f, anchor="lm",
                   fill=YELLOW if k == active else WHITE, stroke_width=9, stroke_fill=(10, 10, 12))
            x += f.getlength(w[0]) + sp
        return True

    def frame(self, src: Image.Image, t: float) -> Image.Image:
        t_abs = self.plan.start + t
        idx = self.scene_at(t_abs)
        native = self._native_scene(idx)
        if native is not None:
            panel = native.render(max(0.001, t_abs - self.starts[idx])).convert("RGB")
        else:
            box = _CROPS[_KIND_CROP.get(self.kinds[idx], "card")]
            panel = src.crop(box).resize((PANEL_W, round(PANEL_W * (box[3] - box[1]) / (box[2] - box[0]))),
                                         Image.BILINEAR)
        ph = panel.height
        mask, shadow = self._panel_assets(ph)
        x, y = (SW - PANEL_W) // 2, SLOT_CENTER - ph // 2

        img = self.bg.copy()
        img.paste((0, 0, 0), (x - 80, y - 80 + 16), shadow)
        img.paste(panel, (x, y), mask)
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([x, y, x + PANEL_W - 1, y + ph - 1], radius=28,
                            outline=theme.BORDER_LT, width=3)

        # hook headline (pops in), alternating white / yellow lines
        pop = 1.0 - ease_out_cubic(min(1.0, t / 0.35))
        for i, ln in enumerate(self.hook_lines):
            ty = HOOK_TOP + i * self.hook_lh + pop * 46
            col = WHITE if i % 2 == 0 else YELLOW
            d.text((SW / 2 + 4, ty + 6), ln, font=self.hook_font, fill=(8, 9, 11), anchor="mt")
            d.text((SW / 2, ty), ln, font=self.hook_font, fill=col, anchor="mt")

        # series badge
        ep = self.q.episode
        label = f"{ep.series.upper()}  ·  EP {ep.number}" if ep else "PYTHON INTERVIEW"
        bw = d.textlength(label, font=self.badge_font) + 56
        d.rounded_rectangle([(SW - bw) / 2, self.badge_y, (SW + bw) / 2, self.badge_y + 56], radius=28, fill=YELLOW)
        d.text((SW / 2, self.badge_y + 28), label, font=self.badge_font, fill=INK, anchor="mm")

        # word-by-word captions, or the end card when nobody is talking
        if not self._draw_caption(d, t) and t > self.dur - 3.2:
            d.text((SW / 2, CAPTION_Y), "full lesson · link in description", font=self.cta_font,
                   fill=SOFT, anchor="mm", stroke_width=7, stroke_fill=(10, 10, 12))

        # fade in / out
        f = min(1.0, t / 0.2, max(0.0, (self.dur - t) / 0.35))
        if f < 1.0:
            img = Image.blend(Image.new("RGB", img.size, (0, 0, 0)), img, max(0.0, f))
        return img


def _probe(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", str(path)], capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def render_short(cfg: Config, q: Question, tl: dict, video: Path, plan: ShortPlan,
                 out_mp4: Path, cover_png: Path, fonts: FontBook) -> float:
    """Render one Short; returns its verified duration in seconds."""
    comp = _Compositor(cfg, fonts, q, tl, plan)
    n = int(round(plan.duration * FPS))
    dur = n / FPS
    dec = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-ss", f"{plan.start:.3f}", "-t", f"{dur:.3f}", "-i", str(video),
         "-vf", f"fps={FPS}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        stdout=subprocess.PIPE)
    enc = subprocess.Popen(
        ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{SW}x{SH}",
         "-r", str(FPS), "-i", "-", "-ss", f"{plan.start:.3f}", "-t", f"{dur:.3f}", "-i", str(video),
         "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "medium", "-crf", "19",
         "-pix_fmt", "yuv420p", "-r", str(FPS),
         "-af", f"afade=t=in:st=0:d=0.12,afade=t=out:st={dur - 0.4:.2f}:d=0.4",
         "-c:a", "aac", "-b:a", "192k", "-t", f"{dur:.3f}", "-movflags", "+faststart", str(out_mp4)],
        stdin=subprocess.PIPE)
    frame_bytes, last, cover_at = SRC_W * SRC_H * 3, None, int(1.6 * FPS)
    try:
        for k in range(n):
            buf = dec.stdout.read(frame_bytes)
            if len(buf) == frame_bytes:
                last = Image.frombuffer("RGB", (SRC_W, SRC_H), buf, "raw", "RGB", 0, 1)
            elif last is None:
                break
            out = comp.frame(last, k / FPS)
            if k == cover_at:
                cover_png.parent.mkdir(parents=True, exist_ok=True)
                out.save(cover_png)
            enc.stdin.write(out.tobytes())
    finally:
        enc.stdin.close()
        dec.stdout.close()
        enc.wait()
        dec.wait()
    got = _probe(out_mp4)
    if not (30.0 < got < 60.0):
        out_mp4.unlink(missing_ok=True)
        raise SystemExit(f"{out_mp4.name}: rendered {got:.1f}s — outside the 30-60 s Shorts window")
    return got


def write_summary(path: Path, q: Question, plans: list[ShortPlan], files: list[tuple[str, float]]) -> None:
    ep = f"{q.episode.series} — EP {q.episode.number}/{q.episode.of}: " if q.episode else ""
    lines = [f"{ep}{q.title}  ·  {len(plans)} Shorts",
             "Each is 30-60 s, 1080x1920. Upload as a YouTube Short; copy the title / description below.", ""]
    for k, (p, (name, got)) in enumerate(zip(plans, files), 1):
        lines += [f"[{k}] {name}   {got:.0f}s",
                  f"    cut from the full video @ {_fmt(p.start)} – {_fmt(p.end)}"
                  + (f"   (chapter: {p.chapter})" if p.chapter else ""),
                  f"    why: {p.why}  (score {p.score})",
                  f"    title: {p.title}",
                  "    description:"] + [f"      {ln}" for ln in p.description.split("\n")] + [""]
    path.write_text("\n".join(lines))


def make_shorts(cfg: Config, q: Question, *, count: int | None = None, replan: bool = False,
                plan_only: bool = False) -> list[Path]:
    video = cfg.video_dir(q.id) / f"{q.id}.mp4"
    if not video.exists():
        raise SystemExit(f"{q.id}: no rendered video at {video}")
    tl = load_timeline(cfg, q)
    if abs(_probe(video) - tl["total"]) > 0.25:
        raise SystemExit(f"{q.id}: timeline.json doesn't match the rendered video — "
                         f"re-render it (`build`) so the cuts line up")
    out_dir = cfg.shorts_dir(q.id)
    plan_path = out_dir / "plan.json"
    plans = None if (replan or count) else load_plan(plan_path, tl)
    if plans is None:
        plans = plan_shorts(q, tl, count)
        save_plan(plan_path, tl, plans)
    print(f"[{q.id}] {len(plans)} Shorts")
    for k, p in enumerate(plans, 1):
        print(f"  {k}. {_fmt(p.start)}–{_fmt(p.end)} ({p.duration:.0f}s)  score {p.score:>5}  "
              f"{p.hook!r}   [{p.why}]")
    if plan_only:
        return []

    fonts = FontBook(cfg.fonts_path, cfg.mono_font, cfg.ui_font)
    for old in out_dir.glob("short-*.mp4"):
        old.unlink()
    paths, files = [], []
    for k, p in enumerate(plans, 1):
        name = f"short-{k}-{p.slug}"
        mp4 = out_dir / f"{name}.mp4"
        got = render_short(cfg, q, tl, video, p, mp4, out_dir / "thumbnails" / f"{name}.png", fonts)
        print(f"    ✓ {mp4.name}  ({got:.1f}s, {mp4.stat().st_size / 1e6:.1f} MB)")
        paths.append(mp4)
        files.append((mp4.name, got))
    write_summary(out_dir / "shorts.txt", q, plans, files)
    return paths
