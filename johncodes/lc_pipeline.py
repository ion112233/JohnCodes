"""LeetCode-layout videos: script JSON + scraped problem data -> mp4.

Script (content/leetcode_easy/<nn>_<slug>.json)::

    { "id": "two_sum", "slug": "two-sum", "rank": 1,
      "prompt": "...", "complexity": {"time": "O(n)", "space": "O(n)"},
      "expected": ["[0,1]", "[1,2]", "[0,1]"],        # one per example test case
      "segments": [
         {"type": "narration", "beat": "hook", "text": "..."},
         {"type": "search",  "chapter": "Find it on LeetCode"},
         {"type": "paste"},                                # LeetCode's Python template
         {"type": "read",  "show": "ex1", "chapter": "..."},   # scroll the statement
         {"type": "code",  "body": "line\\nline"},            # method body, indent 0
         {"type": "run",   "chapter": "Run it"},
         {"type": "narration", "beat": "takeaway", "text": "..."} ] }

The problem statement, examples and template come from ``_data/<slug>.json``
(LeetCode's own GraphQL data). The Run results are produced by actually
executing the typed solution against the statement's example inputs.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from .audio import AudioSpec, Narrator, build_track
from .config import Config
from .fonts import FontBook
from .lc_doc import Doc
from .lc_scenes import CaseView, LCSearch, LCWork, SearchData, LEFT_X1, LEFT_X0, TOP, PANEL_Y1, BAR_H
from .pipeline import _fmt, _say, _say_all, _words
from .question import Complexity, Question, Segment
from .render import mux, render_video
from .scenes import ExplainCard, Scene, TitleCard

DATA_DIR = "content/leetcode_easy/_data"
SERIES = "leetcode_easy"

_PRELUDE = '''
from typing import *
class ListNode(object):
    def __init__(self, val=0, next=None):
        self.val = val
        self.next = next
class TreeNode(object):
    def __init__(self, val=0, left=None, right=None):
        self.val = val
        self.left = left
        self.right = right
'''


# ------------------------------------------------------------------ loading
def _err(path, msg):
    raise SystemExit(f"{Path(path).name}: {msg}")


def load(path: str | Path):
    path = Path(path)
    script = json.loads(path.read_text())
    for k in ("id", "slug", "rank", "prompt", "complexity", "expected", "segments"):
        if k not in script:
            _err(path, f"missing '{k}'")
    if not re.fullmatch(r"[a-z0-9][a-z0-9_]*", script["id"]):
        _err(path, "id must be snake_case")
    data_path = path.parent / "_data" / (script["slug"].replace("-", "_") + ".json")
    data = json.loads(data_path.read_text())
    py = next(c["code"] for c in data["codeSnippets"] if c["langSlug"] == "python")
    return script, data, py


def _signature(template: str):
    m = re.search(r"def (\w+)\(self,?\s*([^)]*)\)", template)
    name = m.group(1)
    params = [p.strip() for p in m.group(2).split(",") if p.strip()]
    types = dict(re.findall(r":type (\w+): ([^\n]+)", template))
    rtype = (re.search(r":rtype: ([^\n]+)", template) or [None, ""])[1]
    return name, params, types, rtype


# ---------------------------------------------------------- run the solution
def _fmt_val(v):
    mod = {}
    exec(_PRELUDE, mod)
    if v is None:
        return "null"
    if hasattr(v, "val") and hasattr(v, "next"):
        out, seen = [], set()
        while v is not None and id(v) not in seen:
            seen.add(id(v))
            out.append(v.val)
            v = v.next
        return json.dumps(out, separators=(",", ":"))
    return json.dumps(v, separators=(",", ":"))


def _build_list(vals, ListNode):
    head = cur = None
    nodes = []
    for x in vals:
        n = ListNode(x)
        nodes.append(n)
        if cur is None:
            head = cur = n
        else:
            cur.next = n
            cur = n
    return head, nodes


def _build_tree(vals, TreeNode):
    if not vals or vals[0] is None:
        return None
    nodes = [TreeNode(vals[0])]
    root = nodes[0]
    q, i = [root], 1
    while q and i < len(vals):
        n = q.pop(0)
        if i < len(vals) and vals[i] is not None:
            n.left = TreeNode(vals[i])
            q.append(n.left)
        i += 1
        if i < len(vals) and vals[i] is not None:
            n.right = TreeNode(vals[i])
            q.append(n.right)
        i += 1
    return root


def compute_cases(script, data, template: str, final_code: str) -> list[CaseView]:
    name, params, types, rtype = _signature(template)
    ns: dict = {}
    exec(_PRELUDE, ns)
    exec(final_code, ns)
    Solution = ns["Solution"]
    lines = [ln for ln in data["exampleTestcases"].split("\n")]
    builder = script.get("builder")
    n_args = {"cycle": 2, "intersection": 5}.get(builder, len(params))
    names = script.get("input_names") or params
    expected = script["expected"]
    cases: list[CaseView] = []
    for ci in range(len(lines) // n_args):
        raw = lines[ci * n_args:(ci + 1) * n_args]
        vals = [json.loads(x) for x in raw]
        sol = Solution()
        meth = getattr(sol, name)
        if builder == "cycle":
            head, nodes = _build_list(vals[0], ns["ListNode"])
            if vals[1] >= 0 and nodes:
                nodes[-1].next = nodes[vals[1]]
            out = meth(head)
            output = _fmt_val(out)
        elif builder == "intersection":
            iv, la, lb, sa, sb = vals
            ha, na = _build_list(la, ns["ListNode"])
            hb, nb = _build_list(lb, ns["ListNode"])
            if iv != 0:
                nb_prev = nb[sb - 1] if sb > 0 else None
                shared = na[sa]
                if nb_prev is None:
                    hb = shared
                else:
                    nb_prev.next = shared
            r = meth(ha, hb)
            output = "No intersection" if r is None else f"Intersected at '{r.val}'"
        else:
            args = []
            for pn, v in zip(params, vals):
                ty = types.get(pn, "")
                if "ListNode" in ty:
                    args.append(_build_list(v, ns["ListNode"])[0])
                elif "TreeNode" in ty:
                    args.append(_build_tree(v, ns["TreeNode"]))
                else:
                    args.append(v)
            out = meth(*args)
            if script.get("output") == "prefix":
                output = json.dumps(args[0][:out], separators=(",", ":"))
            elif "None" in rtype:
                first = next(a for a in args if isinstance(a, list))
                output = json.dumps(first, separators=(",", ":"))
            else:
                output = _fmt_val(out)
        shown_inputs = [(n, r) for n, r in zip(names, raw)]
        exp = expected[ci]
        cases.append(CaseView(inputs=shown_inputs, output=output, expected=exp, ok=(output == exp)))
    bad = [i + 1 for i, c in enumerate(cases) if not c.ok]
    if bad:
        raise SystemExit(f"{script['id']}: solution output != expected for case(s) {bad}: "
                         + "; ".join(f"{c.output} vs {c.expected}" for c in cases if not c.ok))
    return cases


# ------------------------------------------------------------------ question
def make_question(script, data) -> Question:
    segs = []
    for s in script["segments"]:
        if s["type"] == "narration":
            segs.append(Segment(type="narration", text=s["text"], beat=s.get("beat")))
    q = Question(
        id=script["id"], title=data["title"],
        topic=" · ".join(t["name"] for t in data["topicTags"][:2]),
        prompt=script["prompt"], segments=segs, difficulty=data["difficulty"],
        complexity=Complexity(**script["complexity"]),
        filename="solution.py")
    q.kicker = f"LEETCODE  ·  TOP 20 EASY  ·  #{script['rank']} OF 20"
    return q


def video_dir(cfg: Config, script) -> Path:
    return cfg.output_path / SERIES / script["id"] / "video"


# -------------------------------------------------------------------- build
def build(path: str | Path, cfg: Config, *, narrator: Narrator | None = None,
          keep_intermediates: bool = False, timeline_only: bool = False) -> Path:
    script, data, template = load(path)
    base = Path(path).parent
    fonts = FontBook(cfg.fonts_path, cfg.mono_font, cfg.ui_font)
    q = make_question(script, data)
    outdir = video_dir(cfg, script)
    outdir.mkdir(parents=True, exist_ok=True)
    narrator = narrator or Narrator(cfg)
    cache: dict = {}

    # solution = template (without its trailing indent) + typed body
    head = template[:template.rfind("\n") + 1]
    codes = []
    for s in script["segments"]:
        if s["type"] == "code":
            body = "\n".join(("        " + ln if ln.strip() else "") for ln in s["body"].split("\n"))
            codes.append(head + body)
    final_code = codes[-1]
    cases = compute_cases(script, data, template, final_code)
    print(f"[{script['id']}] {q.title}  — {len(cases)} example case(s) pass")

    doc_w = LEFT_X1 - LEFT_X0
    doc = Doc(fonts, data, doc_w, base / "_data" / "images")
    doc.render()
    view_h = PANEL_Y1 - TOP - BAR_H

    print("  synthesising voiceover (kokoro)…")
    t0 = time.time()
    hook_text, take_text = q.narration_beat("hook"), q.narration_beat("takeaway")
    hook_audio, hook_dur = _say(narrator, hook_text, cache)
    take_audio, take_dur = _say(narrator, take_text, cache)

    scenes: list[Scene] = []
    narration_at, narration_windows, keystroke_times = [], [], []
    chapters: list[tuple[float, str]] = []
    tl_scenes, tl_clips = [], []
    clock = 0.0

    def add(scene, audio=None, adur=0.0, voice_offset=0.3, chapter=None, words=None, segment=None,
            kind="other", voices=None):
        nonlocal clock
        if chapter:
            chapters.append((clock, chapter))
        scenes.append(scene)
        tl_scenes.append({"i": len(scenes) - 1, "kind": kind, "start": round(clock, 3),
                          "end": round(clock + scene.duration, 3), "segment": segment, "info": {}})
        for v in (voices or ([(voice_offset, audio, adur, words or [])] if audio is not None else [])):
            off, a, dd = v[0], v[1], v[2]
            narration_at.append((clock + off, a))
            narration_windows.append((clock + off, clock + off + dd))
            tl_clips.append({"scene": len(scenes) - 1, "start": round(clock + off, 3),
                             "end": round(clock + off + dd, 3),
                             "words": [[w, round(clock + off + s0, 3), round(clock + off + e0, 3)]
                                       for w, s0, e0 in (v[3] if len(v) > 3 else [])]})
        clock += scene.duration

    # ---- opener
    odur = max(cfg.title_min, (hook_dur + cfg.title_pad) if hook_dur else cfg.title_min)
    add(TitleCard(cfg, fonts, q, odur), hook_audio, hook_dur, 0.25, chapter="Intro",
        words=_words(cache, hook_text), kind="title")

    # ---- body
    pending: list[Segment] = []
    buffer = ""
    cur_scroll = 0
    console_cases: list = []
    console_open = False
    idx = 0
    page_open = False

    top_rows = json.loads((base / "_data" / "_problemset_top.json").read_text())

    def work(**kw):
        return LCWork(cfg, fonts, doc, **kw)

    for si, seg in enumerate(script["segments"]):
        st = seg["type"]
        if st == "narration":
            if seg.get("beat") in ("hook", "takeaway"):
                continue
            pending.append(Segment(type="narration", text=seg["text"]))
            continue
        p_audio, p_dur, p_words = _say_all(narrator, pending, cache, cfg.sample_rate)
        pending = []
        idx += 1
        seed = f"{q.id}-{idx}"
        chap = seg.get("chapter")
        pad = (p_dur + 1.0) if p_dur else 0.0

        if st == "search":
            sd = SearchData(query=script.get("search_query", data["title"].lower()),
                            target_slug=data["titleSlug"], default_rows=top_rows,
                            results=_search_rows(data))
            sc = LCSearch(cfg, fonts, sd, 1.0, seed)
            sc.duration = max(5.0, pad, sc.click_at + 0.7)
            keystroke_times += sc.keystroke_times(clock)
            add(sc, p_audio, p_dur, 0.4, chapter=chap, words=p_words, segment=si, kind="search")
            page_open = True

        elif st == "paste":
            sc = work(mode="paste", start_code="", end_code=template, duration=1.0,
                      scroll_from=0, scroll_to=0, seed=seed, paste_at=1.2)
            sc.duration = max(4.0, pad, 3.2)
            keystroke_times += sc.keystroke_times(clock)
            add(sc, p_audio, p_dur, 0.3, chapter=chap, words=p_words, segment=si, kind="code")
            buffer = template

        elif st == "read":
            target = doc.scroll_for(seg.get("show", "top"), view_h)
            sc = work(mode="hold", start_code=buffer, end_code=buffer, duration=max(4.0, pad),
                      scroll_from=cur_scroll, scroll_to=target, seed=seed,
                      console_open=console_open, console_cases=console_cases)
            add(sc, p_audio, p_dur, 0.3, chapter=chap, words=p_words, segment=si, kind="read")
            cur_scroll = target

        elif st == "code":
            end = head + "\n".join(("        " + ln if ln.strip() else "")
                                   for ln in seg["body"].split("\n"))
            target = doc.scroll_for(seg["show"], view_h) if seg.get("show") else cur_scroll
            sc = work(mode="type", start_code=buffer, end_code=end, duration=1.0,
                      scroll_from=cur_scroll, scroll_to=target, seed=seed, lead=cfg.typing_lead,
                      console_open=console_open, console_cases=console_cases)
            natural = cfg.typing_lead + sc.plan.duration + cfg.typing_pad
            sc.duration = max(cfg.typing_min, natural, (p_dur + cfg.typing_lead + cfg.typing_pad)
                              if p_dur else 0)
            keystroke_times += sc.keystroke_times(clock)
            add(sc, p_audio, p_dur, cfg.typing_lead, chapter=chap, words=p_words, segment=si,
                kind="code")
            buffer = end
            cur_scroll = target

        elif st == "run":
            switch = 2.2
            body = 0.9 + 0.65 + 1.1 + switch * len(cases) + 1.0
            sc = work(mode="run", start_code=buffer, end_code=buffer,
                      duration=max(body, pad + 0.5), scroll_from=cur_scroll, scroll_to=cur_scroll,
                      seed=seed, cases=cases, case_switch_at=switch)
            add(sc, p_audio, p_dur, 0.3, chapter=chap, words=p_words, segment=si, kind="terminal")
            console_open, console_cases = True, cases

    if pending:
        p_audio, p_dur, p_words = _say_all(narrator, pending, cache, cfg.sample_rate)
        sc = work(mode="hold", start_code=buffer, end_code=buffer,
                  duration=max(3.5, p_dur + 1.4), scroll_from=cur_scroll, scroll_to=cur_scroll,
                  seed=f"{q.id}-tail", console_open=console_open, console_cases=console_cases)
        add(sc, p_audio, p_dur, 0.3, words=p_words, kind="read")

    # ---- closer
    edur = max(cfg.explain_min, (take_dur + cfg.explain_pad) if take_dur else cfg.explain_min)
    add(ExplainCard(cfg, fonts, q, edur), take_audio, take_dur, 0.35, words=_words(cache, take_text),
        kind="explain")

    total = clock
    print(f"    voiceover ready ({time.time() - t0:.1f}s) · {len(scenes)} scenes · {_fmt(total)}")

    ch_path = outdir / "chapters.txt"
    ch_path.write_text("\n".join(f"{_fmt(0 if i == 0 else tm)} {label}"
                                 for i, (tm, label) in enumerate(chapters)) + "\n")
    (outdir / "timeline.json").write_text(json.dumps({
        "id": q.id, "total": round(total, 3), "fps": cfg.fps, "xfade": cfg.xfade,
        "scenes": tl_scenes, "clips": tl_clips,
        "chapters": [[round(tm, 3), label] for tm, label in chapters],
    }, ensure_ascii=False))
    final = outdir / f"{q.id}.mp4"
    if timeline_only:
        return final

    spec = AudioSpec(total_duration=total, narration_at=narration_at,
                     keystroke_times=keystroke_times, narration_windows=narration_windows)
    audio_path = outdir / "audio.wav"
    print("  mixing audio…")
    build_track(cfg, spec, audio_path)
    print("  rendering video…")
    silent = outdir / "video_silent.mp4"
    render_video(cfg, scenes, silent)
    mux(cfg, silent, audio_path, final)
    if not keep_intermediates:
        silent.unlink(missing_ok=True)
        audio_path.unlink(missing_ok=True)
    print(f"  ✓ {final}  ({final.stat().st_size / 1e6:.1f} MB, {_fmt(total)})")
    return final


def _search_rows(data) -> list[dict]:
    rows = [r for r in data.get("search_results", [])][:6]
    out = []
    for r in rows:
        out.append({"frontendQuestionId": r["frontendQuestionId"], "title": r["title"],
                    "titleSlug": r["titleSlug"], "acRate": r["acRate"] / 100 if r["acRate"] > 1 else r["acRate"],
                    "paidOnly": r["paidOnly"], "difficulty": r["difficulty"]})
    return out


def preview(path: Path, cfg: Config, *, scene: str, at: float, out: Path | None) -> Path:
    """Render one still without TTS: builds scenes with fixed durations."""
    script, data, template = load(path)
    base = Path(path).parent
    fonts = FontBook(cfg.fonts_path, cfg.mono_font, cfg.ui_font)
    head = template[:template.rfind("\n") + 1]
    body = next(s["body"] for s in script["segments"] if s["type"] == "code")
    end = head + "\n".join(("        " + ln if ln.strip() else "") for ln in body.split("\n"))
    cases = compute_cases(script, data, template, end)
    doc = Doc(fonts, data, LEFT_X1 - LEFT_X0, base / "_data" / "images")
    doc.render()
    view_h = PANEL_Y1 - TOP - BAR_H
    top_rows = json.loads((base / "_data" / "_problemset_top.json").read_text())
    if scene == "search":
        sd = SearchData(query=script.get("search_query", data["title"].lower()),
                        target_slug=data["titleSlug"], default_rows=top_rows, results=_search_rows(data))
        sc = LCSearch(cfg, fonts, sd, 8.0, "pv")
    else:
        kw = dict(scroll_from=0, scroll_to=0, seed="pv", duration=10.0)
        if scene == "paste":
            sc = LCWork(cfg, fonts, doc, mode="paste", start_code="", end_code=template, paste_at=1.2, **kw)
        elif scene == "read":
            sc = LCWork(cfg, fonts, doc, mode="hold", start_code=template, end_code=template,
                        **{**kw, "scroll_to": doc.scroll_for("ex1", view_h)})
        elif scene == "run":
            sc = LCWork(cfg, fonts, doc, mode="run", start_code=end, end_code=end, cases=cases,
                        case_switch_at=2.2, **kw)
        else:
            sc = LCWork(cfg, fonts, doc, mode="type", start_code=template, end_code=end, **kw)
    t = at * sc.duration if scene != "type" else sc.lead + sc.plan.duration * at
    out = out or (cfg.output_path / f"{script['id']}_{scene}_preview.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    sc.render(t).save(out)
    return out
