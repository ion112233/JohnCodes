# Prompt — generate a JohnCodes question

Paste this to Claude (or any capable model). Replace the topic line, or leave it
open and let the model pick.

---

You are writing one short-form video script for **JohnCodes**, a channel of
60-second YouTube Shorts about Python coding-interview questions. Each Short:
title card → the solution being typed in an IDE with a voiceover → a takeaway
card.

Produce **exactly one JSON object** matching `content/question.schema.json`.
No prose, no code fences — just the JSON.

Rules:

- `id`: kebab-case, matches the title (e.g. `valid-anagram`).
- `title`: the canonical problem name, ≤ 40 chars.
- `difficulty`: `Easy` | `Medium` | `Hard`.
- `topic`: e.g. `Arrays & Hashing`, `Two Pointers`, `Sliding Window`,
  `Binary Search`, `Stack`, `Linked List`, `Trees`, `Heap`, `Dynamic Programming`.
- `prompt`: ONE sentence, ≤ 160 chars, plain-English problem statement.
- `code`: the full idiomatic Python solution, as it should be typed.
  - 4-space indentation, **lines ≤ 42 characters** (hard limit — long lines get
    shrunk and look bad).
  - 6–16 lines total. One function. Type hints on the signature.
  - Real, correct, runnable Python. No `print`, no test harness, no comments
    unless one genuinely earns its place.
  - Prefer the optimal approach an interviewer wants to see.
- `narration.hook`: 1–2 sentences. Name the problem, say why it matters. ~4–7s.
- `narration.walkthrough`: 3–6 sentences, spoken while the code is typed.
  Explain the *idea* and *why it works*, not a line-by-line reading. Mention the
  naive approach and why this beats it. ~15–30s.
- `narration.takeaway`: 1–2 sentences. The punchline / pattern to remember. ~4–8s.
- Narration is read by a TTS voice: write it the way a person talks. Spell out
  symbols ("target minus n", not "target - n"). Avoid parentheses and bullet
  fragments.
- `complexity.time` / `complexity.space`: big-O strings.

Topic for this one: **<TOPIC OR "your choice">**
