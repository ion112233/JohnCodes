# JohnCodes

Generate vertical **YouTube Shorts for Python interview questions** from a single
JSON file per question. Each Short is:

```
title card  →  the solution typed out in a PyCharm-style IDE (voiceover)  →  takeaway card
```

- **Visuals** — pure Pillow + ffmpeg, frame by frame. Darcula theme, gutter,
  minimap, project pane, blinking caret, auto-scroll. No browser, no Node.
- **Voiceover** — [Kokoro](https://github.com/hexgrad/kokoro) TTS, fully local.
- **Audio bed** — synthesised keystroke clicks + optional background music,
  ducked under the narration.
- **Content** — one JSON per question, designed to be produced by Claude
  (see [`prompts/generate_question.md`](prompts/generate_question.md)).

## Setup

```bash
brew install ffmpeg espeak-ng
python3 -m pip install -r requirements.txt
```

First run downloads the Kokoro model (~330 MB) and a small spaCy model, once,
to `~/.cache/huggingface` and the spaCy cache.

**JetBrains Mono** (PyCharm's editor font, OFL-licensed) is bundled in
`assets/fonts/`. If it's missing the renderer falls back to **Menlo**.

## Use

```bash
# list questions
python3 -m johncodes list

# fast visual check — one PNG, no audio, ~1s
python3 -m johncodes preview content/questions/0001-two-sum.json --at 0.6

# render one Short  ->  output/two-sum/two-sum.mp4
python3 -m johncodes build content/questions/0001-two-sum.json

# render all of them
python3 -m johncodes build --all
```

`make build Q=content/questions/0001-two-sum.json` wraps the same thing (and sets
`PYTHONPATH` for you). Or `pip install -e .` and call `johncodes …` directly.

## Adding a question

1. Ask Claude with [`prompts/generate_question.md`](prompts/generate_question.md).
2. Save the JSON as `content/questions/NNNN-<slug>.json`
   (validate against [`content/question.schema.json`](content/question.schema.json)).
3. `python3 -m johncodes build content/questions/NNNN-<slug>.json`.

Key authoring constraint: **code lines ≤ 42 characters**, 6–16 lines. Narration
is spoken, so write it how you talk ("target minus n", not "target - n").

## Config

All defaults are in [`johncodes/config.py`](johncodes/config.py). Override any
subset with a JSON file:

```bash
python3 -m johncodes build content/questions/0001-two-sum.json --config my.json
```

See [`config.example.json`](config.example.json). Common knobs: `tts_voice`
(default is the `am_michael,am_fenrir` blend; any Kokoro voice id or comma-list
works), `captions` (on/off), `music_path`, `fps`, `crf`.

## Layout

```
johncodes/
  config.py        settings + path resolution
  question.py      JSON schema loader
  theme.py         Darcula palette + Pygments token map
  fonts.py         JetBrains Mono → Menlo fallback chain
  highlight.py     code → per-line coloured spans, prefix reveal
  typing_plan.py   per-character keystroke schedule
  ide.py           the editor window renderer (Pillow)
  scenes.py        title card / typing scene / takeaway card
  audio.py         Kokoro TTS + keystroke/music mixdown
  render.py        scenes → frames → ffmpeg → mp4
  pipeline.py      question.json → finished Short
  cli.py           `python -m johncodes …`
content/
  questions/*.json
  question.schema.json
prompts/generate_question.md
assets/{fonts,music,sfx}/     (gitignored; drop your own files here)
output/                       (gitignored; rendered Shorts)
```
