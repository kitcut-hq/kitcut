# KitCut — tester quickstart

Thanks for testing. This is a set of AI-driven video pipelines that run
entirely on your machine: burned-in word-synced captions, vertical shorts cut
out of long videos, dubbing, multicam edits. You drive them by talking to
Claude Code in this folder — a plain request like "add captions to this video"
finds the right pipeline on its own.

Nothing leaves your machine: transcription, face tracking and rendering are
all local. The only network use is downloading models on first run.

## You need

- **Windows 10/11.**
- **An NVIDIA GPU is recommended** (fast transcription + GPU encode). Without
  one, captions and shorts still work — add `--encoder libx264` and expect
  slower renders. The screen-recording and multicam pipelines need NVIDIA for
  now.
- **~10 GB free disk** (Python environment + models + working files).

## Install (once, ~10 minutes)

1. **Python 3.13** — `winget install Python.Python.3.13`
   (or from python.org — keep "py launcher" checked).
2. **ffmpeg, the *full* build** — `winget install Gyan.FFmpeg`, then open a
   NEW terminal. Full matters: the essentials build lacks filters the
   pipelines rely on.
3. **Git** — `winget install Git.Git` (if you don't have it).
4. **Claude Code** — https://claude.com/claude-code, install and sign in.
5. In this folder:

   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts/setup-python.ps1
   python scripts/check-env.py
   ```

   `check-env.py` is the doctor: it names anything missing and the fix.
   Warnings about API keys are fine — you need no key for this test.

## First render: captions on your own video

Open a terminal in this folder, run `claude`, and say:

> Add captions to C:\path\to\your-video.mp4

Or run it directly:

```powershell
python scripts/run-captions.py --input "C:\path\to\your-video.mp4" --style config/presets/red-card.json
```

No NVIDIA? Add `--encoder libx264` to either form.

The first run downloads the transcription model (a few GB, one time). A
16-minute video takes about 9 minutes on a laptop RTX GPU; the output lands in
`outputs/`.

## Then: shorts

Ask Claude in this folder:

> Cut three vertical shorts out of C:\path\to\your-video.mp4

It reads the transcript, picks self-contained episodes, face-tracks the crop
so the subject stays in frame, and re-renders the captions at vertical size.
This is the flow we most want tested on real footage.

## Skip for this test

- **YouTube upload** — needs your own Google OAuth setup; out of scope.
- **ElevenLabs voices** — a paid key; the free `--tts edge` voice works.
- **Multicam angle switching** — needs a separate model download; ask us if
  you want to try it.

## When something breaks

That is the test working. Send us:

1. What you asked for (the sentence, or the command).
2. The last ~20 lines of console output.
3. The output of `python scripts/check-env.py`.

And tell us where a result looked wrong even though nothing errored — a
caption out of sync, a crop that cuts a face, a short that opens mid-word.
That feedback is worth the most.
