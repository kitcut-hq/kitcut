# KitCut — start here

KitCut turns raw footage into finished video on your own computer — burned-in
word-synced captions, vertical shorts cut out of long videos, dubs, multicam
edits. You don't operate it; you tell Claude what you want, and Claude
operates it. Nothing is uploaded anywhere: transcription, tracking and
rendering all happen on your machine.

## Set up (one time, ~15 minutes)

You do two things by hand. Claude does everything else.

1. **Install Claude Code** — https://claude.com/claude-code — and sign in
   with your Claude account.
2. **Open this folder in Claude Code** and say:

   > **Set this up.**

   Claude will check your machine, install what's missing (it asks before
   installing anything), build the environment, and finish by rendering a
   small test video for you to watch. If it asks you to close and reopen
   Claude Code partway through, that's normal — reopen this folder and say
   "continue setup."

   The first run also downloads the speech-recognition model (a few GB,
   one time) — not a hang, just a download.

## Use it

Say what you want, with the real path of one of your videos — or drag the
file into the window:

> Add captions to C:\Users\you\Videos\demo.mp4

> Cut three vertical shorts out of C:\Users\you\Videos\webinar.mp4

Claude tells you where every finished file lands. Captions and shorts are
the two flows we most want tested on your real footage.

Good to know:

- **An NVIDIA graphics card is recommended.** Without one, captions and
  shorts still work (renders take a few times longer); the screen-recording
  and multicam pipelines currently need NVIDIA.
- **No accounts or API keys are needed** for anything above. If Claude
  mentions missing keys, they're for optional features — skip them.
- **Skip YouTube uploading** for this test; it needs its own setup.

## Updating

Say:

> Update KitCut.

Your own projects and rendered videos stay put — updates only touch the
tooling. One ask: don't commit anything into this folder's git history;
it belongs to KitCut, and your work lives beside it untouched.

## When something goes wrong

That's the test working — please tell us. Say to Claude:

> Run the doctor.

…and send us what it prints, plus what you had asked for and the last
screen of output. And tell us when a result merely *looks wrong* even
though nothing errored — a caption out of sync, a crop that cuts off a
face, a short that opens mid-word. That feedback is worth the most.

---

*For technical users: the manual path is `scripts/setup-python.ps1` then
`python scripts/check-env.py`, prerequisites are Python 3.13, git, and
ffmpeg (Gyan full build), and every pipeline script answers `--help`. The
README documents everything in depth.*
