# Notes for Claude

Tooling for turning long talking-head videos into captioned vertical shorts, and
now into dubbed ones. The repo is **tooling only** — every source video, audio
file, transcript and render is gitignored third-party content.

Full detail lives in `README.md` and the skills under `.claude/skills/`. This
file is the map.

## Run anything like this

```powershell
python scripts/<whatever>.py --help
```

No `-E`, no `-X utf8`, no activating anything, no `PYTHONPATH`. Every script
imports `scripts/_env.py` as its first non-stdlib line, which re-execs into
`.venv` with a clean environment. It works from a shell that still has the old
poisoned variable exported, and it works when launched by the wrong interpreter.

If something fails to import, run the doctor first — it names the cause instead
of making you guess:

```powershell
python scripts/check-env.py                                   # diagnose
powershell -ExecutionPolicy Bypass -File scripts/setup-python.ps1   # repair
```

After touching any `dub-*.py`, run `python scripts/check-dub.py` — it exercises
the fitting, retune and word-mark logic with no API calls, so it costs nothing
and catches what only a paid run would otherwise reach.

### Why the environment is like this

A user-level `PYTHONPATH` pointed Python 3.13 at Python **3.11's**
site-packages. Python then loaded 3.11's compiled extensions and died with
`DLL load failed` or `numpy.core.multiarray failed to import` — or, under Git
Bash, a bare segfault.

Two things about that are worth remembering, because both cost real time:

- **A venv does not protect you.** `PYTHONPATH` is prepended to `sys.path`
  inside a venv too.
- **pip reads it as well.** It saw the foreign packages, marked transitive
  dependencies as already satisfied, and declined to install them — producing a
  venv silently missing `yaml` and `idna`. `setup-python.ps1` therefore clears
  the variable *before* installing, and finishes with `pip check`.

The persisted variable is gone (its old value is in `temp/pythonpath.removed.txt`).
Don't reintroduce it, and don't use `os.execve` to re-exec on Windows — it
spawns rather than replaces, so the parent dies abnormally and the exit code is
lost. `_env.bootstrap()` uses `subprocess.run` and propagates the status.

## The three pipelines

Everything is manifest-driven. Nothing hardcodes a timecode, a colour or a font
size; those live in `config/`.

**1. Captions** — burn word-synced captions onto a whole video.
`transcribe-words.py` → `build-captions-ass.py` → `verify-captions.py` → `run-captions.py`

**2. Shorts** — cut episodes out of a long video, optionally vertical.
`transcript-outline.py` (find the episodes) → `auto-reframe.py` (crop plan) →
`cut-clips.py` (one NVENC pass: crop → captions → badge)

```powershell
python scripts/cut-clips.py --manifest config/clips/<id>-vertical.json --list
python scripts/auto-reframe.py --manifest config/clips/<id>-vertical.json
python scripts/cut-clips.py --manifest config/clips/<id>-vertical.json
```

**3. Dub** — translate a clip into another language, keeping its cadence.
`dub-clips.py` (segment → translate → fit → mix) → `cut-clips.py --dub`

```powershell
python scripts/dub-clips.py --manifest config/clips/<id>-vertical.json --only <clip-id>
python scripts/cut-clips.py --manifest config/clips/<id>-vertical.json --only <clip-id> --dub outputs/dub
```

Voice is `--tts edge` (free, no key) or `--tts elevenlabs` (needs
`ELEVENLABS_API_KEY`; `_env.py` loads `.env` automatically). Each backend has
its own default `--tag` -- `en` for edge, `en-el` for ElevenLabs -- so the two
never overwrite each other; pointing one at the other's tag is refused.

Voice names and the ElevenLabs model come from `config/elevenlabs-voices.json`
and are validated before anything is spent. A cached translation carries a
fingerprint of the plan and engine it was made for, so changing `--max-dur` (or
the engine, or the language) refuses the stale reuse instead of mapping old
lines onto new slots by index.

The dub writes `outputs/dub/<name>.en.wav` plus an `.en.words.json` in exactly
the envelope faster-whisper produces, so `cut-clips.py --dub` feeds it to the
normal caption builder with no special case. Output is named `…-en.mp4`; the
original is never overwritten.

## Layout

| path | what |
|---|---|
| `scripts/` | all tooling; `_env.py` first, then the pipeline scripts |
| `config/clips/` | which episodes to cut, and their crop sidecars |
| `config/presets/` | caption styling |
| `config/handles/` | the animated handle badge |
| `sources/` `audio/` `transcripts/` `outputs/` `temp/` | gitignored content |

## House rules

These come from how the repo is actually used — follow them without being asked.

- **Leave tooling behind, not just output.** A task ends as a config-driven
  script plus an example config, a README section, and an updated skill, then
  committed. Never hardcode styling or boundaries into a script.
- **Verify before spending an encode.** `cut-clips.py` proves caption sync on
  sampled frames and asserts the output duration before it renders. Keep that
  property; it is what caught a clip rendering 463s instead of 55s.
- **Measure a proposal before adopting it.** Score the alternative on the same
  footage and report where it loses. Per-shot framing looked obviously better
  and measured worse; the dub's first prompt looked fine and left 14 of 26 lines
  drawling at the slow-down floor. Both were caught by measuring, not reasoning.
- **Record traps with the reason,** not just the fix — see `## Gotchas` in the
  README, which is where the ffmpeg and libass landmines are written down.
