# JohnCodes

Generate **16:9 videos for Python interview questions** from a single JSON file
per question:

```
title card  →  [ segments: code typing / terminal runs / cards, with voiceover ]  →  takeaway card
```

- **Visuals** — pure Pillow + ffmpeg, frame by frame. Full-bleed PyCharm
  (Darcula) editor: toolbar, tabs, breadcrumb, tool windows, gutter, run panel,
  scrollbar. No browser, no Node.
- **Voiceover** — [Kokoro](https://github.com/hexgrad/kokoro) TTS, fully local
  (`am_michael,am_fenrir` blend).
- **Audio bed** — synthesised keystroke clicks + optional background music,
  ducked under the narration.
- **Content** — one JSON per question (an ordered `segments` list), designed to
  be produced by Claude (see [`prompts/generate_question.md`](prompts/generate_question.md)).

## Setup

Requires **Python 3.9–3.12** (Kokoro TTS is capped at `<3.13` — 3.13/3.14 won't install).

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

A script is metadata + an ordered **`segments`** list, compiled to scenes.
Two flavours share the format:

- **interview question** (`content/questions/`) — has `complexity`; auto title +
  takeaway cards. Prompt: [`prompts/generate_question.md`](prompts/generate_question.md).
- **course episode** (`content/episodes/`) — has `episode` + `targetMinutes`;
  auto episode card, `card_recap` segment closes it. Prompt:
  [`prompts/generate_episode.md`](prompts/generate_episode.md).

| segment | becomes |
|---|---|
| `narration` (beat `hook` / `takeaway`) | voiceover on the opener / closer card |
| `narration` (beat `walkthrough`) | voiceover played *while the next `code` types* |
| `narration` (no beat) | voiceover of the segment that follows it |
| `code` | IDE typing scene (full file; keeps common prefix, types the rest) |
| `terminal` | PyCharm Run panel — command types, output prints |
| `repl` | interactive `>>>` console session |
| `gotcha` | broken code + red squiggle + traceback in the Run panel |
| `compare` | two code panels side by side + a verdict |
| `card_topic` | section divider (also a YouTube chapter marker) |
| `card_question` | quick-check, answer fades in |
| `card_recap` | closing bullets + "next episode" teaser |

`build` writes `output/<id>/chapters.txt` (YouTube timestamps) and, for episodes,
reports actual runtime vs `targetMinutes`. `--draft` renders fast at 15fps.

`python3 -m johncodes preview <script.json> --scene typing|terminal|repl|gotcha|compare|opener|topic|question|recap`
renders one still frame of any scene for fast iteration.

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
