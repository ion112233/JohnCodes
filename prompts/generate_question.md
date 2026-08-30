# Prompt — generate a JohnCodes question

Paste this to Claude (or any capable model). Replace the topic line, or leave it
open and let the model pick.

---

You are writing one short-form video script for **JohnCodes**, a channel of
~45–60 second videos about Python coding-interview questions. Each video:

1. auto **title card** (from `title` / `prompt` / `difficulty` / `topic`)
2. the **segments** you write, played in order
3. auto **takeaway card** (from `complexity` + the `takeaway` narration)

Produce **exactly one JSON object** matching `content/question.schema.json`.
No prose, no code fences — just the JSON.

## Top-level fields

- `id`: kebab-case, matches the title (e.g. `valid-anagram`).
- `title`: canonical problem name, ≤ 40 chars.
- `difficulty`: `Easy` | `Medium` | `Hard`.
- `topic`: e.g. `Arrays & Hashing`, `Two Pointers`, `Sliding Window`,
  `Binary Search`, `Stack`, `Linked List`, `Trees`, `Heap`, `Dynamic Programming`.
- `prompt`: ONE sentence, ≤ 160 chars, plain-English problem statement.
- `complexity`: `{ "time": "O(n)", "space": "O(1)" }`.
- `filename` (optional): defaults to `solution.py`.

## `segments` — ordered list

Follow the beat pattern: **hook → walkthrough + code → terminal → (optional quick-check) → takeaway**

- `{ "type": "narration", "beat": "hook", "text": "..." }`
  1–2 sentences, plays over the title card (~4–7s). Name the problem, say why it matters.

- `{ "type": "narration", "beat": "walkthrough", "text": "..." }`
  3–6 sentences (~15–30s). Explain the *idea* and *why it works*, not a line-by-line
  reading. Mention the naive approach and why this beats it. This plays **while the
  next `code` segment types**, so the two should be adjacent and roughly matched in length.

- `{ "type": "code", "code": "def ...\\n    ..." }`
  Full idiomatic Python solution as it should be typed.
  - 4-space indent, **lines ≤ 42 characters** (hard limit).
  - 6–16 lines, one function, type hints on the signature.
  - Real, correct, runnable. No `print`, no test harness.
  - Multiple `code` segments are allowed — each holds the **full file** at that
    point; the editor keeps the common prefix and types the rest. Use a second
    `code` segment only to add to / evolve the solution.

- `{ "type": "narration", "text": "..." }` (no beat)
  A short line that becomes the voiceover of whatever segment follows it
  (e.g. one sentence before a `terminal`).

- `{ "type": "terminal", "command": "...", "output": "..." }`
  Shows a PyCharm Run panel: the command types out, then the output, then
  "Process finished with exit code 0". Keep `command` to one realistic line
  (e.g. `python -c 'from solution import two_sum; print(two_sum([2, 7, 11, 15], 9))'`)
  and `output` short (1–4 lines).

- `{ "type": "card_topic", "cardTitle": "...", "cardSubtitle": "..." }`
  A full-screen section divider. `cardTitle` ≤ 40, `cardSubtitle` ≤ 80 (optional).

- `{ "type": "card_question", "question": "...", "answer": "..." }`
  A full-screen "quick check": the question shows, then the answer fades in.
  `question` ≤ 120, `answer` ≤ 120 (optional). Use for the one non-obvious
  gotcha in the solution.

- `{ "type": "narration", "beat": "takeaway", "text": "..." }`
  1–2 sentences, the punchline / pattern to remember (~4–8s). Plays over the
  takeaway card.

## Voice

Narration is read by a TTS voice — write it the way a person talks. Spell out
symbols ("target minus n", not "target - n"). No parentheses, no bullet fragments.

Topic for this one: **<TOPIC OR "your choice">**
