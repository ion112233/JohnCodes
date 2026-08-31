# Prompt — generate a Basic Python crash-course episode

Paste this to Claude with the chapter you want. One JSON object matching
`content/question.schema.json`, saved to `content/episodes/epNN-<slug>.json`.

---

You are writing one episode of **Basic Python**, a 15-part beginner crash course
on the JohnCodes channel. The audience has never programmed. Pace is slow and
patient — explain *why*, use plain language, spell out symbols for the TTS voice
("target minus n", "the hash symbol", not "-" or "#").

Produce **exactly one JSON object** — no prose, no code fences.

## Top level

```json
{
  "id": "epNN-<slug>",
  "title": "<chapter title from the course outline>",
  "topic": "Basic Python · Episode NN",
  "prompt": "<one line: by the end you can …>",
  "episode": { "number": NN, "of": 15, "series": "Basic Python" },
  "targetMinutes": <the Est. Time from the outline>,
  "segments": [ … ]
}
```

## Runtime

`targetMinutes` is a hard constraint — `build` warns past ±8%. The voice runs at
a fixed calm pace, so **runtime is set purely by how much narration you write**.
Rule of thumb: **~165 words per target minute** — a 12-minute episode ≈ 2,000
words, a 17-minute episode ≈ 2,800. Under-writing is the usual failure by a wide
margin; write two full, thorough sentences where you're tempted to write one.
Draft-build (`--draft`, ~2–3 min) and check the runtime line before the real render.

## Structure per episode

1. `narration` `beat: hook` — 60–90 words, over the auto episode card. What this
   episode covers and why it matters.
2. For each sub-topic in the chapter's "Covers" list:
   - `card_topic` `{ cardTitle, cardSubtitle }` — the section divider (also
     becomes a YouTube chapter marker).
   - `narration` `beat: walkthrough` immediately followed by a `code` segment —
     the narration plays *while the code types*, so match their lengths.
   - then 0–3 of: `terminal`, `repl`, `gotcha`, `compare`, `card_question`.
3. `narration` `beat: takeaway` — 40–70 words, over the recap card.
4. `card_recap` `{ points: [...], next: "EP N+1 — <title>" }` — 3–4 bullets.

## Segment reference

- `code` — full file at that point. The editor keeps the common prefix with the
  previous `code` segment and types the rest, so **grow one file across the
  episode**; only break the prefix when you genuinely want to show an edit.
  Lines ≤ 42 chars, 4-space indent, runnable.
- `terminal` `{ command, output }` — Run panel: command types, output prints,
  "Process finished with exit code 0". For `input()`, put the typed value in the
  output (`Your name? Ada`).
- `repl` `{ lines: [{ input, output }] }` — interactive `>>>` session. Great for
  showing a single idea fast (types, immediate result). Empty `output` = no
  output line (e.g. an assignment, or a `None` value at the prompt).
- `gotcha` `{ code, badLine, error }` — the broken code in the editor with a red
  squiggle on `badLine`, the traceback in the Run panel, exit code 1. Follow it
  with narration and usually a corrected `code` segment.
- `compare` `{ left, leftLabel, right, rightLabel, verdict }` — two snippets side
  by side (left = wrong/before, right = right/after) + a one-line verdict.
- `card_question` `{ question, answer }` — quick check. The question is read
  ("Quick check. <question>"), sits on screen ~10 s, then the answer appears and
  is read too. You do NOT need a narration segment for it — keep `question` and
  `answer` phrased so they read well aloud.
- `card_recap` — each `point` appears exactly as the teacher reads it. The
  `takeaway` narration (if any) plays first as a short lead-in — keep it to one
  or two sentences; the points carry the substance.
- `card_topic` — see above.

## Voice

Every `narration.text` is read aloud. Conversational, second person, short
sentences. No parentheses, no lists-as-fragments, no code syntax in the prose.

Chapter for this episode: **<PASTE THE ROW FROM THE COURSE OUTLINE>**
