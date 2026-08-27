---
name: video-multicam-switch
description: Cut a film out of several cameras that shot the same event, switching full frame between angles rather than compositing them — and test that cutter by taking somebody else's finished multicam video, rebuilding the raw camera tapes it was cut from, re-cutting it, and scoring the result frame by frame against the original. Use when asked to edit multi-camera footage, switch between angles, sync several cameras that share a soundtrack, detect the shots and angles in a finished video, or to verify/benchmark whether this repo's editing can reproduce a professionally edited cut.
---

# Cutting between cameras, and proving the cut is right

Two jobs in one set of scripts. `angle-cut.py` is a real multicam cutter: N
synchronised cameras, switching full frame, one NVENC pass. The rest is a test
harness that can take a finished film somebody else cut, rebuild the tapes it
must have come from, re-cut it here, and score the result against the original.

If a film we assembled is indistinguishable from the film a professional editor
assembled, the edit is automatable. That is the whole point; keep it in view.

Do not confuse this with `video-multicam`, which is `screencast-cut.py` —
a screen recording plus a camera, **composited** into one picture. This one
**chooses between** pictures. Different problem, different script.

README reference: "Cutting between cameras, and proving the cut is right".
Worked example: `projects/a16z-altman/`.

## The project folder comes first

Every video lives in `projects/<id>/`. Before doing anything, read
`projects/<id>/project.json` (create it with
`python scripts/project-scan.py --init <id>`) and skim `journal.md` if the ask
touches past decisions. The scripts record their own renders; anything you run
by hand, you record yourself. End the session with a prose note in the journal.

## The round trip, in order

```powershell
cd C:\instafill\video-editing
python scripts/split-cameras.py  --manifest projects/<id>/multicam-sim.json --conform-only
python scripts/shot-detect.py    --src projects/<id>/temp/program.mp4 --list --sheets
python scripts/shot-detect.py    --src projects/<id>/temp/program.mp4
python scripts/split-cameras.py  --manifest projects/<id>/multicam-sim.json --plan
python scripts/split-cameras.py  --manifest projects/<id>/multicam-sim.json
python scripts/sync-audio.py     --manifest projects/<id>/anglecut.json
python scripts/angle-cut.py      --manifest projects/<id>/anglecut.json --list
python scripts/angle-cut.py      --manifest projects/<id>/anglecut.json
python scripts/compare-videos.py --rendered projects/<id>/outputs/<id>-anglecut.mp4 `
                                 --reference projects/<id>/temp/program.mp4
```

Conform **first**. A downloaded file is rarely on the frame rate it claims, and
a one-frame error must not have timestamp jitter to hide behind. Everything
downstream is built from and scored against the conformed programme, never the
download.

For real footage you already have — no fixture, no round trip — you only need
the last four: `sync-audio.py`, then `angle-cut.py` with a plan you wrote or
`auto-switch.py` produced.

## The part that needs judgement

**Whether the shot detection is a decision or a coin toss.** `--list` sweeps the
threshold; look for a *plateau*, not a number that works. On the a16z clip the
answer is 15 cuts / 16 shots / 4 angles at every threshold from 0.030 to 0.120.
Then read the separation line: worst distance within an angle vs closest between
two angles. 0.036 vs 0.169 is a 4.7× margin. If within ≥ between it says so, and
you must look at `--sheets` before believing anything.

**Always look at `--sheets`.** One contact sheet per detected angle. This takes
ten seconds and is the only check that catches "these two clusters are the same
camera" or "this angle is actually two". Numbers cannot tell you the wide shot
is the wide shot.

**Which camera is the reference.** Any of them, but it must be one the plan
actually uses, and `sync-audio.py` and `anglecut.json` must name the same one —
angle-cut refuses a sync measured against a different reference.

**Where the film starts on each tape.** `anchor: "picture_start"` measures it
from the picture and is exact for tapes that open on a held frame. Real footage
that was rolling before the film starts has no motion onset to find; declare
`anchor` as a map of camera to frame instead. Whichever you use, the anchors
must reproduce the offsets the audio measured — the assertion runs before any
encode, and if picture and sound disagree, one of them is wrong and neither
should be trusted.

**Reading the comparator.** Look at the shift count first, not the SSIM. A
median SSIM of 0.999 is compatible with an entire camera being one frame out;
that was measured, not imagined. `PASS` means the frame count is exact, no
frame's best match is a neighbour, every cut is at offset 0, and the audio is
aligned.

## The leak rule

The frozen filler tells you which camera the editor used — a motion detector
would score 100% by reading the answer key rather than editing anything. So:

- **Stage 1** replays the known cut list. It tests the machinery: sync, anchors,
  frame arithmetic, the encode. It is allowed the shot list, because the shot
  list is what it is replaying.
- **Stage 2** (`auto-switch.py`) gets the tapes and **nothing else**. No
  `truth.json`, no `shots.json`, no picture. It decides from sound alone and is
  scored on agreement, not on pass/fail.

`truth.json` belongs to the harness. No script under test may read it, ever.

## Verify before spending

- `--list` / `--plan` on every script prices the decision without encoding.
- `split-cameras.py` fingerprints every sampled frame of every tape against the
  programme frame it should be showing, and refuses to ship a tape that is
  wrong — leaving the `.part.mp4` for inspection.
- `angle-cut.py` asserts anchors against the audio sync *before* the encode, and
  frame count, dimensions, frame rate, rotation and audio peak *after* it.
- `python scripts/check-multicam.py` tests the arithmetic with no GPU and no
  files. Run it after touching any of the five scripts.
- **Run the negative control after changing the comparator.** Re-render with one
  camera's anchor moved by a single frame and confirm `compare-videos.py` fails
  with a shift count. A harness that has never failed has not been tested.

## Do not

- **Do not verify synthetic footage with `freezedetect`.** NVENC re-encodes
  cloned frames independently, so a held frame differs from itself and the
  detector finds nothing at −60 dB. Fingerprint against the expected frame.
- **Do not judge a re-cut by average SSIM.** See above; it cannot see the error
  that matters.
- **Do not conform with the `fps` filter.** It duplicates and drops to hit its
  target, changing the thing you are about to measure. `setpts` by frame index,
  then assert the count.
- **Do not use `select`/`aselect` to drop spans.** `aselect` passes every audio
  frame on this ffmpeg. `trim`/`atrim` and `concat`, as everywhere in this repo.
