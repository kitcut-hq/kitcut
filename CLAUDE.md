# Notes for Claude

Tooling for turning raw footage into finished video: captions burned onto a whole
talking-head recording, vertical shorts cut out of it, a dub that keeps the
original's cadence, an edit assembled from a screen recording and a camera take
that were never in sync, and the upload afterwards. The repo is **tooling only**
— every source video, audio file, transcript and render is gitignored
third-party content.

Full detail lives in `README.md` and the skills under `.claude/skills/`. This
file is the map.

Nothing here is a one-off. A task that ends in a rendered file and no reusable
script has not ended — see `## House rules`.

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

## The five pipelines

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

**4. Multicam** — one film out of a screen recording plus a camera take of you
narrating. `sync-tracks.py` (measure the offset, prove it) → `screencast-cut.py`
(plan the cut, composite, one NVENC pass).

```powershell
python scripts/sync-tracks.py    --manifest config/screencast/<id>.json --verify
python scripts/screencast-cut.py --manifest config/screencast/<id>.json --list
python scripts/screencast-cut.py --manifest config/screencast/<id>.json
```

The **camera is the master clock**: it carries the sound and it brackets the
screen recording at both ends. So the film is laid out in camera time and the
acts fall out of the footage rather than being declared — camera full-frame
where the screen was not rolling yet, screen with a square PiP where it was, and
camera again wherever the screen has stopped being worth looking at.

**Sync when one track is silent.** `creation_time` subtracts to a ±1 s seed
(both containers stamp capture *start*, in UTC). A screen-change-vs-key-clicks
correlation is attempted and **refused** when the peak is mush — it scored
z=2.3 here, because output streams silently and speech moves the audio without
touching the screen. Phrase anchors settle it, but an anchor only counts if its
screen time can be read off the screen *alone*.

What the cut does, all manifest keys under `cut`:

| key | |
|---|---|
| `min_silence` / `air` | ignore gaps shorter than this; keep this much breath at each join |
| `require_frozen` | only cut where the screen is static too |
| `force_over` | …except a silence this long, which goes **even if the screen is moving** |
| `camera_when_frozen_over` | screen still longer than this → the camera takes the whole frame |
| `cutaway_lead_out` | come back to the screen this early, before it moves again |

**Sweep, do not pick.** `--list` prices any setting without encoding anything.
Dropping `min_silence` from 1.5 s to 0.7 s took this film from 27 s of pauses
removed to 49 s; below 0.7 s the cut count climbs faster than the runtime falls.
Test `camera_when_frozen_over` against the frozen **runs**, not against kept
segments — pause-cutting chops a dead region into pieces too short to qualify
individually, and the first version silently cut away for 0.0 s.

`bookends` bring in clips shot separately, and each may carry `broll`.
**Transcribe every extra clip before deciding what it is for** — one with no
speech in it is picture, not a scene, and belongs in a `broll` list, where the
bookend's own sound keeps running while only the picture cuts away.

Get footage off a phone with `scripts/import-iphone.ps1` (`-DeviceName` for
anything that is not an iPhone). It waits for the byte count to stop moving and
compares it against the device, because the shell creates the destination file
instantly and a truncated take still probes clean — it just reports a shorter
duration.

Four traps, all with evidence in the README gotchas: **`aselect` passes every
audio frame** on this ffmpeg, so cutting uses `trim`/`atrim`; a phone's
**rotation tag can be wrong**, and `-noautorotate` copies the bogus matrix onto
the output, so `camera_rotate` drives `-display_rotation` instead; a looped PNG
mask needs **`shortest=1`** or `alphamerge` waits forever and the file never
gets a `moov` atom; and **never measure leftover silence on the rendered file** —
`loudnorm` lifts the room tone and `silencedetect` then finds nothing at any
threshold. Measure the source and intersect with the keep-list.

**5. Publish** — upload it, then give it chapters.

```powershell
python scripts/yt-upload.py outputs/screencast/<id>.mp4 --title "..." `
    --description-file config/screencast/<id>.description.txt `
    --channel @instafill_ai --privacy unlisted --dry-run
python scripts/yt-set-chapters.py <video-id> --chapters config/chapters/<id>.txt --dry-run
python scripts/yt-audit-chapters.py --channel @instafill_ai --none-only
```

`--channel` is not decoration: one Google login can own several channels and the
grant picks one silently, so it asserts which channel the token really points at
before a byte leaves. Uploads are resumable, are re-read afterwards to confirm
the title and privacy came back as asked, and write a `.youtube.json` sidecar
beside the render. Privacy defaults to `unlisted` — the end you can widen later.
Both scripts share the one `youtube.force-ssl` grant, so there is no second
consent to give.

## Layout

| path | what |
|---|---|
| `scripts/` | all tooling; `_env.py` first, then the pipeline scripts |
| `config/clips/` | which episodes to cut, and their crop sidecars |
| `config/screencast/` | multicam manifests, their `.sync.json` / `.cuts.json` sidecars, and the YouTube description text |
| `config/presets/` | caption styling |
| `config/handles/` | the animated handle badge |
| `config/chapters/` | chapter lists, one `MM:SS Title` per line |
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
- **Ship a mode that prices the decision.** Every script here has `--list`,
  `--plan`, `--dry-run` or `--plan-only`, and it exists so a threshold can be
  swept instead of guessed. Picking `min_silence` by eye would have left 22
  seconds of dead air in a film; pricing four settings took no encode at all.
  A new tool is not finished until you can ask it what a choice costs.
- **Record traps with the reason,** not just the fix — see `## Gotchas` in the
  README, which is where the ffmpeg and libass landmines are written down.
