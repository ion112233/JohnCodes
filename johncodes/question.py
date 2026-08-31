"""Script schema + loader.

A script is one JSON file: metadata plus an ordered ``segments`` list compiled
into scenes. Two flavours share the format:

* interview question  — has ``complexity``; auto title + takeaway cards
* course episode      — has ``episode`` + ``targetMinutes``; auto episode card,
                        explicit ``card_recap`` segment closes it

See ``content/question.schema.json`` and ``prompts/``.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

_DIFFICULTIES = {"Easy", "Medium", "Hard"}
_SEGMENT_TYPES = {
    "narration", "code", "terminal", "repl", "gotcha", "compare",
    "card_topic", "card_question", "card_recap",
}
_BEATS = {"hook", "walkthrough", "takeaway"}


@dataclass
class Complexity:
    time: str
    space: str


@dataclass
class Episode:
    number: int
    of: int
    series: str


@dataclass
class ReplLine:
    input: str
    output: str = ""


@dataclass
class Segment:
    type: str
    # narration
    text: Optional[str] = None
    beat: Optional[str] = None
    # code
    code: Optional[str] = None
    # terminal
    command: Optional[str] = None
    output: Optional[str] = None
    # repl
    lines: list[ReplLine] = field(default_factory=list)
    # gotcha
    bad_line: Optional[int] = None
    error: Optional[str] = None
    # compare
    left_label: Optional[str] = None
    left_code: Optional[str] = None
    right_label: Optional[str] = None
    right_code: Optional[str] = None
    verdict: Optional[str] = None
    # card_topic
    card_title: Optional[str] = None
    card_subtitle: Optional[str] = None
    # card_question
    question: Optional[str] = None
    answer: Optional[str] = None
    # card_recap
    points: list[str] = field(default_factory=list)
    next_up: Optional[str] = None


@dataclass
class Question:
    id: str
    title: str
    topic: str
    prompt: str
    segments: list[Segment]
    difficulty: str = "Easy"
    complexity: Optional[Complexity] = None
    episode: Optional[Episode] = None
    target_minutes: Optional[float] = None
    filename: str = "solution.py"
    source_path: Optional[Path] = None

    @property
    def is_episode(self) -> bool:
        return self.episode is not None

    @property
    def final_code(self) -> str:
        code = ""
        for s in self.segments:
            if s.type == "code" and s.code:
                code = s.code
        return code

    def narration_beat(self, beat: str) -> Optional[str]:
        for s in self.segments:
            if s.type == "narration" and s.beat == beat and s.text:
                return s.text
        return None


def _err(path: Path, msg: str):
    raise SystemExit(f"{path.name}: {msg}")


def _require(d: dict, key: str, path: Path):
    if key not in d:
        _err(path, f"missing required field '{key}'")
    return d[key]


def _parse_segment(raw: dict, path: Path, i: int) -> Segment:
    if not isinstance(raw, dict):
        _err(path, f"segments[{i}] must be an object")
    st = raw.get("type")
    if st not in _SEGMENT_TYPES:
        _err(path, f"segments[{i}].type must be one of {sorted(_SEGMENT_TYPES)} (got {st!r})")

    seg = Segment(type=st)
    if st == "narration":
        seg.text = str(_require(raw, "text", path)).strip()
        beat = raw.get("beat")
        if beat is not None and beat not in _BEATS:
            _err(path, f"segments[{i}].beat must be one of {sorted(_BEATS)}")
        seg.beat = beat
    elif st == "code":
        seg.code = str(_require(raw, "code", path)).rstrip("\n")
        if not seg.code.strip():
            _err(path, f"segments[{i}].code is empty")
    elif st == "terminal":
        seg.command = str(_require(raw, "command", path))
        seg.output = str(_require(raw, "output", path)).rstrip("\n")
    elif st == "repl":
        rl = _require(raw, "lines", path)
        if not isinstance(rl, list) or not rl:
            _err(path, f"segments[{i}].lines must be a non-empty array")
        seg.lines = [ReplLine(input=str(_require(x, "input", path)),
                              output=str(x.get("output", "")).rstrip("\n")) for x in rl]
    elif st == "gotcha":
        seg.code = str(_require(raw, "code", path)).rstrip("\n")
        seg.error = str(_require(raw, "error", path)).rstrip("\n")
        seg.bad_line = int(raw["badLine"]) if "badLine" in raw else None
    elif st == "compare":
        seg.left_label = str(raw.get("leftLabel", "")).strip() or None
        seg.left_code = str(_require(raw, "left", path)).rstrip("\n")
        seg.right_label = str(raw.get("rightLabel", "")).strip() or None
        seg.right_code = str(_require(raw, "right", path)).rstrip("\n")
        seg.verdict = str(raw.get("verdict", "")).strip() or None
    elif st == "card_topic":
        seg.card_title = str(_require(raw, "cardTitle", path)).strip()
        seg.card_subtitle = str(raw.get("cardSubtitle", "")).strip() or None
    elif st == "card_question":
        seg.question = str(_require(raw, "question", path)).strip()
        seg.answer = str(raw.get("answer", "")).strip() or None
    elif st == "card_recap":
        pts = _require(raw, "points", path)
        if not isinstance(pts, list) or not pts:
            _err(path, f"segments[{i}].points must be a non-empty array")
        seg.points = [str(p).strip() for p in pts]
        seg.next_up = str(raw.get("next", "")).strip() or None
    return seg


def load_question(path: str | Path) -> Question:
    path = Path(path)
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        _err(path, f"invalid JSON — {e}")

    qid = str(_require(data, "id", path))
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", qid):
        _err(path, f"'id' must be kebab-case (got {qid!r})")

    difficulty = str(data.get("difficulty", "Easy"))
    if difficulty not in _DIFFICULTIES:
        _err(path, f"'difficulty' must be one of {sorted(_DIFFICULTIES)}")

    complexity = None
    if "complexity" in data:
        cd = data["complexity"]
        if not isinstance(cd, dict) or "time" not in cd or "space" not in cd:
            _err(path, "'complexity' must be an object with 'time' and 'space'")
        complexity = Complexity(time=str(cd["time"]), space=str(cd["space"]))

    episode = None
    if "episode" in data:
        ed = data["episode"]
        if not isinstance(ed, dict):
            _err(path, "'episode' must be an object")
        episode = Episode(number=int(_require(ed, "number", path)),
                          of=int(_require(ed, "of", path)),
                          series=str(_require(ed, "series", path)))

    raw_segments = _require(data, "segments", path)
    if not isinstance(raw_segments, list) or not raw_segments:
        _err(path, "'segments' must be a non-empty array")
    segments = [_parse_segment(s, path, i) for i, s in enumerate(raw_segments)]
    if not any(s.type in ("code", "gotcha", "compare") for s in segments):
        _err(path, "at least one 'code', 'gotcha' or 'compare' segment is required")

    return Question(
        id=qid,
        title=str(_require(data, "title", path)).strip(),
        topic=str(_require(data, "topic", path)).strip(),
        prompt=str(_require(data, "prompt", path)).strip(),
        segments=segments,
        difficulty=difficulty,
        complexity=complexity,
        episode=episode,
        target_minutes=float(data["targetMinutes"]) if "targetMinutes" in data else None,
        filename=str(data.get("filename", "solution.py")).strip() or "solution.py",
        source_path=path,
    )


def discover(content_dir: str | Path = "content") -> list[Path]:
    out: list[Path] = []
    for sub in ("questions", "episodes"):
        d = Path(content_dir) / sub
        if d.is_dir():
            out += sorted(p for p in d.iterdir() if p.suffix == ".json")
    return out
