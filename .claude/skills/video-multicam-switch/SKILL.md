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

## Stage 2: choosing the cut from the sound

```powershell
python scripts/auto-switch.py --manifest projects/<id>/anglecut-auto.json --list
python scripts/auto-switch.py --manifest projects/<id>/anglecut-auto.json --sweep `
                              --score projects/<id>/<id>.shots.json
python scripts/auto-switch.py --manifest projects/<id>/anglecut-auto.json
python scripts/angle-cut.py   --manifest projects/<id>/anglecut-auto.json `
                              --out projects/<id>/outputs/<id>-autocut.mp4
```

Needs the speaker models under `models/diarization/` (gitignored, ~200 MB):
`sherpa-onnx-pyannote-segmentation-3-0` and `nemo_en_titanet_large.onnx`, both
from the sherpa-onnx GitHub releases. `pip install sherpa-onnx` — it runs on the
ONNX runtime that is already here, so no torch and no gated download.

**The manifest needs three things stage 1 did not.** Explicit `anchor` frames
(the picture anchor is derived from a plan, and here the plan is the output —
use the values stage 1 measured); `film.frames` (the in and out points are
given, because what is scored is the switching, not the trim); and `speakers`,
one `{camera, at}` hint per person naming a moment when that person is talking.
That hint is the only human knowledge in the stage and says nothing about when
to cut.

**Read the separation line before believing any of it.** Cosine distance within
a speaker against between speakers — 0.59 vs 0.82 on the a16z clip. If within
exceeds between the voices did not separate, and every cut after that is a
guess; the script says so. Sherpa's built-in clustering merged two of three
speakers into one 33-second block, which is why the clustering is done in the
script and not by the library. Suspect the clustering before the model.

**Expect the wide to score zero.** It is nobody's close-up, so a
speaker-following rule can never predict a cut to it. On this film that is 14.2%
of the timeline, which puts the ceiling at ~85.8%; the measured 77.68% is 90% of
what is reachable. Quote the ceiling alongside the score or the number is
misleading.

**`compare-videos.py` will FAIL a stage-2 cut, and should.** Its bar is stage
1's frame-exactness. The number to read is the timeline agreement, which it
computes independently of `auto-switch --score` — if the two disagree, one of
them is broken.

**Knobs swept on one film are fitted to it.** `--sweep --score` reads the answer;
it is the harness's mode. Report what it found *and* that it was fitted, and get
the real number from a film the knobs have never seen. On this one the sweep
killed a plausible idea: forcing a periodic wide cutaway drops agreement from
77.7% to 64.6% while placing more cuts near the human's — right times, wrong
camera.

## Debug notes, and reading a stage-2 render

```powershell
python scripts/angle-cut.py --manifest projects/<id>/anglecut.json --debug
```

Burns a bottom-left commentary: the shot, the tape frames, the anchor, the sync,
**why this camera**, and a warning where the tape is held. Style is
`config/overlays/debug-notes.json`; check placement for free with
`debug-notes.py --frame T --video f.mp4`.

`--debug` writes `<id>-anglecut-debug.mp4` and never touches the clean render.
Burning text changes pixels, so a debug copy of a stage-1 cut is no longer
frame-identical and would fail its own comparison. Keep both.

**A stage-2 render freezes wherever it disagrees with the human, and that is
not a bug.** A synthetic tape only carries real frames where the original editor
used that angle, so choosing any other camera asks for footage that does not
exist. Expect it, say so when reporting, and never present a stage-2 render as
a watchable film — it is a diagnostic. On the a16z clip the disagreement
(22.32%), the frames below 0.90 SSIM (624) and the frozen frames (624) are the
same 22.3%.

**Calibrate any new detector against stage 1.** Its plan is the human's own
edit, so every frame provably has real footage and any frozen run reported
there is a false positive. Both frozen thresholds in this repo were set that
way: 0.0015 over half a second called 12.8% of a pixel-identical render frozen,
0.0005 over a second calls 0.0% while still catching all 624 in stage 2. Free
ground truth — use it.

## The wide shot

It is nobody's close-up, so a speaker-following rule scores 0% on it. Before
concluding that is a hard ceiling, know what is already measured: the editor
cuts wide on **crosstalk**. The two wide shots hold the two densest patches of
overlapping speech in the film (11.7% and 18.0%, against a median of 0.0% over
every close-up longer than three seconds), and six of nine short interjections
land within 0.31 s of a human cut.

Detect it with the segmentation model, never with windowed embeddings — a
window holding a speaker plus somebody's "yeah" embeds as the speaker, and
measured churn inside the wide shots was identical to outside them.

`wide_overlap_pct` implements the rule and is **off by default**. Crosstalk is
4.5% of the film and the wide is 14.2%: overlap is close to necessary and
nowhere near sufficient, and the best of 30 swept settings gained one point on
a film with two wide shots in it. Turn it on when a second film says it earns
its place, and do not quote the sweep's winner as a result.

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
