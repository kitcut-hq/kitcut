# Sketch Studio

A proof of concept: a web page with one prompt box. Type an idea, and Claude writes, reviews and
scores a **5-second hand-drawn film** on the kitcut sketch engine, and the page plays the MP4.

```powershell
pip install -r requirements-studio.txt           # once: the Claude Agent SDK (bundles Claude Code)
# .env: ANTHROPIC_API_KEY=sk-ant-api...
python studio/agent.py --smoke                   # API check: prints the key source, model and cost
python studio/test_guard.py                      # the permission model, no API calls
python studio/server.py                          # http://127.0.0.1:8765
python studio/agent.py "a paper plane delivers a coffee"   # the same, without the page
```

## How it works

1. `server.py` (aiohttp) takes the prompt and makes `projects/studio-<stamp>/` with a 5-second
   manifest (`template/sketch.json`).
2. `agent.py` runs Claude (**Opus 5.5 only**, `MODEL` in `agent.py`) through the **Claude
   Agent SDK**, which is Claude Code's agent loop as a library. The system prompt is `prompt.md`, with the engine, the cast, the example film and
   the sound notation read fresh from the repo. It is written to a file, because at ~100 KB it
   is too long for a Windows command line. Claude:
   1. writes `film.js`, `score.json` and `sfx.json`;
   2. renders review stills and looks at the contact sheet;
   3. fixes what it sees;
   4. checks that the soundtrack renders.
3. `agent.py` then runs the ordinary pipeline, `sketch-audio.py` and then `sketch-render.py`,
   and the page plays `outputs/film.mp4`.
4. Every step streams to the page as server-sent events: Claude's tool calls, the review sheet
   as it changes, render progress, the cost and the timings. `studio.json` in the job folder
   keeps the record.

## What Claude can touch

`guard()` in `agent.py` decides every tool call through a `PreToolUse` hook. `test_guard.py`
covers it. Claude can:

- **Read** anything in the repo except `.env*`, `.git` and `.venv`.
- **Write and Edit** only `film.js`, `score.json` and `sfx.json` in its own job folder.
- **Run** four exact commands and nothing else:
  - `node --check`
  - `sketch-render.py --stills`
  - `sketch-render.py --automation`
  - `sketch-audio.py`

  No chaining, pipes, redirection or `$()`.

The final render is not Claude's; the studio runs it.

## API only

The run gets `ANTHROPIC_API_KEY` from `.env` and a private `CLAUDE_CONFIG_DIR`
(`temp/studio-claude/`), with `setting_sources=[]`. So it never uses a local Claude Code login,
its settings, its memory or its skills. The SDK's init message reports the key source, and
`--smoke` prints it.

`CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS=1` is set because some organisations reject Claude
Code's default context-management beta with a 400. The error reads "not available for
HIPAA-regulated organizations without Zero Data Retention: context_management". A 5-second film
never needs that beta.

## Limits (it is a POC)

- Local only (127.0.0.1), no accounts, one film at a time; a second request queues.
- Every film spends the API key in `.env`; `STUDIO_MAX_USD` (default 5) caps one run.
- No voice-over. The sketch pipeline supports one (`sketch-vo.py`), but that adds ElevenLabs
  cost and about a minute.
