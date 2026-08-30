"""Question schema + loader.

A question is a single JSON file. See ``content/question.schema.json`` and
``prompts/generate_question.md`` for the authoring contract.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

_DIFFICULTIES = {"Easy", "Medium", "Hard"}


@dataclass
class Narration:
    hook: str
    walkthrough: str
    takeaway: str


@dataclass
class Complexity:
    time: str
    space: str


@dataclass
class Question:
    id: str
    title: str
    difficulty: str
    topic: str
    prompt: str
    code: str
    narration: Narration
    complexity: Complexity
    filename: str = "solution.py"
    source_path: Optional[Path] = None

    @property
    def code_lines(self) -> list[str]:
        return self.code.split("\n")

    @property
    def max_line_len(self) -> int:
        return max((len(ln) for ln in self.code_lines), default=0)


def _require(data: dict, key: str, path: Path) -> object:
    if key not in data:
        raise SystemExit(f"{path.name}: missing required field '{key}'")
    return data[key]


def load_question(path: str | Path) -> Question:
    path = Path(path)
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        raise SystemExit(f"{path.name}: invalid JSON — {e}") from None

    qid = str(_require(data, "id", path))
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", qid):
        raise SystemExit(f"{path.name}: 'id' must be kebab-case (got {qid!r})")

    difficulty = str(_require(data, "difficulty", path))
    if difficulty not in _DIFFICULTIES:
        raise SystemExit(f"{path.name}: 'difficulty' must be one of {sorted(_DIFFICULTIES)}")

    code = str(_require(data, "code", path)).rstrip("\n")
    if not code.strip():
        raise SystemExit(f"{path.name}: 'code' is empty")

    nd = _require(data, "narration", path)
    if not isinstance(nd, dict):
        raise SystemExit(f"{path.name}: 'narration' must be an object")
    narration = Narration(
        hook=str(_require(nd, "hook", path)).strip(),
        walkthrough=str(_require(nd, "walkthrough", path)).strip(),
        takeaway=str(_require(nd, "takeaway", path)).strip(),
    )

    cd = data.get("complexity", {})
    complexity = Complexity(
        time=str(cd.get("time", "O(n)")),
        space=str(cd.get("space", "O(1)")),
    )

    return Question(
        id=qid,
        title=str(_require(data, "title", path)).strip(),
        difficulty=difficulty,
        topic=str(data.get("topic", "Python")).strip(),
        prompt=str(_require(data, "prompt", path)).strip(),
        code=code,
        narration=narration,
        complexity=complexity,
        filename=str(data.get("filename", "solution.py")).strip() or "solution.py",
        source_path=path,
    )


def discover(content_dir: str | Path = "content/questions") -> list[Path]:
    d = Path(content_dir)
    if not d.is_dir():
        return []
    return sorted(p for p in d.iterdir() if p.suffix == ".json")
