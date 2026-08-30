"""Question schema + loader.

A question is a single JSON file: metadata plus an ordered ``segments`` list that
is compiled into scenes. See ``content/question.schema.json`` and
``prompts/generate_question.md``.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

_DIFFICULTIES = {"Easy", "Medium", "Hard"}
_SEGMENT_TYPES = {"narration", "code", "terminal", "card_topic", "card_question"}
_BEATS = {"hook", "walkthrough", "takeaway"}


@dataclass
class Complexity:
    time: str
    space: str


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
    # card_topic
    card_title: Optional[str] = None
    card_subtitle: Optional[str] = None
    # card_question
    question: Optional[str] = None
    answer: Optional[str] = None


@dataclass
class Question:
    id: str
    title: str
    difficulty: str
    topic: str
    prompt: str
    complexity: Complexity
    segments: list[Segment]
    filename: str = "solution.py"
    source_path: Optional[Path] = None

    # ---- convenience derived from segments ----
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
    elif st == "card_topic":
        seg.card_title = str(_require(raw, "cardTitle", path)).strip()
        seg.card_subtitle = str(raw.get("cardSubtitle", "")).strip() or None
    elif st == "card_question":
        seg.question = str(_require(raw, "question", path)).strip()
        seg.answer = str(raw.get("answer", "")).strip() or None
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

    difficulty = str(_require(data, "difficulty", path))
    if difficulty not in _DIFFICULTIES:
        _err(path, f"'difficulty' must be one of {sorted(_DIFFICULTIES)}")

    cd = _require(data, "complexity", path)
    if not isinstance(cd, dict) or "time" not in cd or "space" not in cd:
        _err(path, "'complexity' must be an object with 'time' and 'space'")
    complexity = Complexity(time=str(cd["time"]), space=str(cd["space"]))

    raw_segments = _require(data, "segments", path)
    if not isinstance(raw_segments, list) or not raw_segments:
        _err(path, "'segments' must be a non-empty array")
    segments = [_parse_segment(s, path, i) for i, s in enumerate(raw_segments)]
    if not any(s.type == "code" for s in segments):
        _err(path, "at least one 'code' segment is required")

    return Question(
        id=qid,
        title=str(_require(data, "title", path)).strip(),
        difficulty=difficulty,
        topic=str(_require(data, "topic", path)).strip(),
        prompt=str(_require(data, "prompt", path)).strip(),
        complexity=complexity,
        segments=segments,
        filename=str(data.get("filename", "solution.py")).strip() or "solution.py",
        source_path=path,
    )


def discover(content_dir: str | Path = "content/questions") -> list[Path]:
    d = Path(content_dir)
    if not d.is_dir():
        return []
    return sorted(p for p in d.iterdir() if p.suffix == ".json")
