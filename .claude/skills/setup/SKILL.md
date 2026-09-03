---
name: setup
description: Set this folder up to render video - install missing prerequisites (Python 3.13, ffmpeg full build, git), build the .venv, verify with check-env.py, and prove it with a small test render. Use when the user asks to set up, install, or get started, when .venv is missing, when check-env.py fails, or when any script dies with an import or DLL error.
---

# Setting up this folder

The user may be completely non-technical. **You run everything; they only
approve.** Never hand them a command to type. Narrate in plain language
("installing the video engine", not "adding ffmpeg to PATH"), one step at a
time, and finish with a rendered file they can watch — that is the moment
setup becomes real for them.

## Order of operations

**1. Diagnose first.** Run:

```powershell
python scripts/check-env.py
```

It names every problem and its fix. Read its output instead of guessing.
Three outcomes:

- **Command fails because Python itself is missing** → step 2.
- **It reports `.venv is missing`** or import/DLL failures → step 3.
- **`environment OK`** → step 5 (warnings are usually fine — see step 4).

**2. Missing prerequisites** — install via winget, one at a time:

```powershell
winget install Python.Python.3.13 --accept-package-agreements --accept-source-agreements
winget install Gyan.FFmpeg --accept-package-agreements --accept-source-agreements
winget install Git.Git --accept-package-agreements --accept-source-agreements
```

- ffmpeg must be **Gyan.FFmpeg** (the full build). The "essentials" build
  lacks the rubberband filter the dub pipeline needs.
- **The PATH trap:** a program installed by winget is not visible to the
  terminal session that installed it. After installing, ask the user to
  close Claude Code, reopen it in this folder, and say "continue setup" —
  then re-run the diagnosis. Do not fight this with absolute paths; the
  restart is the reliable fix and costs the user one sentence.

**3. Build the environment.** Idempotent, safe to re-run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup-python.ps1
```

If it reports the venv is broken beyond repair, re-run with `-Recreate`.
It ends by running check-env itself.

**4. Interpret the doctor's warnings** — do not chase all of them:

- `ELEVENLABS_API_KEY` / `OPENAI_API_KEY` not set → **fine.** Nothing in
  captions or shorts needs a key. Say so and move on.
- `claude CLI not on PATH` → fine here; it is already running.
- `h264_nvenc missing` (no NVIDIA card) → captions and shorts still work on
  CPU: add `--encoder libx264` to `run-captions.py` and `cut-clips.py`
  commands, and expect renders to take a few times longer. The
  screen-recording and multicam pipelines are unavailable without NVIDIA —
  tell the user plainly if they ask for those.
- Anything marked ✗ FAIL → fix it before proceeding; the message says how.

**5. Prove it with a render.** No sample video ships (media is gitignored),
so make one — speech first, then picture, then the real pipeline:

```powershell
python -m edge_tts --text "Welcome to KitCut. This sentence proves your setup renders word synced captions." --write-media temp/setup-voice.mp3
ffmpeg -y -f lavfi -i color=c=0x202030:s=1280x720:d=8 -i temp/setup-voice.mp3 -shortest -c:v libx264 -pix_fmt yuv420p -c:a aac temp/setup-sample.mp4
python scripts/run-captions.py --input temp/setup-sample.mp4 --style config/presets/red-card.json
```

Run `python -m edge_tts` through the venv's interpreter
(`.venv/Scripts/python.exe`) if the bare form cannot find the module.
The first transcription downloads the speech model (a few GB, one time) —
tell the user this is expected and part of setup, not a hang. On a machine
without NVIDIA add `--encoder libx264` to the last command.

When it finishes, give the user the absolute path of the captioned mp4 and
ask them to open and watch it. **Setup is done when they have seen it play,
not when the commands exited.**

**6. Tell them what to try next**, in their words: "Say *add captions to*
followed by the path of any video of yours — or drag the file into this
window." Shorts are the second thing to try.

## Updating later

When the user asks to update (or says things look outdated):

```powershell
git pull --ff-only
```

Their own work under `projects/`, and any rendered outputs, are untracked
and cannot be touched by a pull. If the pull is refused because the history
diverged, stop and report it rather than forcing anything — this repo's
history is append-only by policy.

## What not to do

- Do not install torch, CUDA toolkits, codec packs, or anything
  requirements.txt does not name. The doctor's list is complete.
- Do not edit scripts to fix an environment problem — the environment is
  the problem, and `setup-python.ps1 -Recreate` is the big hammer.
- Do not set PYTHONPATH, ever. A stray PYTHONPATH is the single documented
  cause of DLL-load failures here, and `_env.py` exists to defeat it.
