# Known issues and limitations

The register. One entry per thing that bit us or that the tools cannot do,
with a fixed shape so a person and a script can both read it. This is the
canonical home; `docs/reference.md ## Gotchas` keeps the prose for traps in tools we
do not control (ffmpeg, libass, YouTube), project journals keep the history,
`docs/retro-*.md` keep the post-mortems — all three link here by id.

**Status** is the field that matters:

- `limitation` — by design; the tool cannot do this and the manifest must
  carry a hand decision. Do not spend time "fixing" it; know it.
- `open` — a real bug or cost we know about and have not fixed. Next work.
- `fixed` — kept for the symptom → cause lookup. Do not delete fixed entries;
  the symptom is what somebody will search for.

**Stage** names which pipeline stage the entry touches
(`import proxies activity ocr track recall review smoke render gate upload`,
or `all`). `screencast-pipeline.py` reads this file at start and prints every
`open` and `limitation` entry for the stages it is about to run, so the
register is seen, not merely stored.

Entry header format is fixed — `### KI-nnn · status · stage · title` — and
`check-screen.py` parses it.

---

### KI-001 · limitation · ocr,track · Recipient names are not redacted

**Symptom.** A recipient's name beside a blurred phone number stays readable.
**Cause.** The OCR model reads Latin and digits reliably and Cyrillic poorly;
a name is never a hit, so it never becomes a template. Promising to cover
names would be a promise the tool cannot keep.
**Workaround.** Decide per project: hand rects where a name sits beside a
tracked field in a regular layout, or accept (the user did, 2026-08-31 —
"they commented publicly; phones and addresses are the private part").
**Evidence.** `projects/books-giveaway/review-notes.md`.

### KI-002 · limitation · track · Selected (recoloured) text does not match its template

**Symptom.** A card number goes sharp exactly while the user highlights it.
**Cause.** NCC compares pixels; white-on-blue is not black-on-white.
**Workaround.** A hand rect over the field for the clip's duration; the
`--recall` harness names the frame.
**Evidence.** `desktop-104945`, journal 2026-08-31.

### KI-003 · limitation · track · Window-switcher thumbnails render secrets at arbitrary scale

**Symptom.** Alt-Tab shows a Notepad card titled `*4111… - Notepad` and the
PAN in its thumbnail; neither matches a template.
**Cause.** Thumbnail scale is not one of the three scales searched, and the
title text is a different font.
**Workaround.** Hand rect over the switcher card while it is up.
**Evidence.** `desktop-105144` @ 24–42 s.

### KI-004 · limitation · track · Photographed screens (handheld footage) track poorly

**Symptom.** Recall drops on a phone-camera clip of a laptop screen.
**Cause.** Moiré, lens softness and motion between frames; NCC at 0.86
holds only intermittently. Measured 85.7 % on `PXL_20260831_181726168`
after the timestamp fix (14 % before it — that number was the bug).
**Workaround.** One hand rect per field, gated to the seconds it is on
screen; `--recall` counts hand rects as coverage.

### KI-005 · open · track · Tracking cost: half the frame-diff, half the sweeps

**Symptom.** Tracking 47 minutes of footage took **82 minutes** with five
workers (was 8 minutes before pooling and the full-resolution search); after
the first round of work, **10:04**.
**Measured breakdown** (2026-08-31, on `desktop-115024` — 17 min, 31,334
frames, the longest source and therefore the wall time of the parallel stage):

| part | cost |
|---|---|
| change detection, every frame | ~191 s |
| full sweeps (28,824 × 9.2 ms) | ~266 s |
| decode / pipe raw gray frames | ~64 s |
| local matches (6,633 × 1.5 ms) | ~10 s |

Sums to ~9.7 min against an observed 10:04, so the model is trustworthy.
**Half of it was not template matching at all** — see KI-020, now fixed, which
takes the first row from ~191 s to ~15 s.
**Done so far (131 s → 42 s on the 60-second test source, recall unchanged).**
Coarse-first for every template — a permissive half-scale prefilter (0.50) with
full-resolution confirmation of a few candidates, instead of full-resolution
sweeps for small text; foreign templates (pooled in from another recording)
patrolled every 60 frames instead of 15 and never on a page change; "warm"
shortened from 3 s to 1 s; no sweeps at all for a caret-blink change; scale
variants only for a warm template on a big change; one OpenCV thread budget per
worker (`--threads`, set by the pipeline).
**Still open — and now the whole cost.** Sweeps. 95 templates are considered on
every changed frame, and a template that is absent is swept on a timer (every
15 frames own, 60 foreign) whether or not the secret could be on screen. Bound
the patrol to the windows the OCR cache says that secret appears in, with a
slow patrol outside them. **Sized before building:** per-secret spans on the two
big sources average 28–33 % of the source, but the top secrets span 86–98 % (the
user's own phone and email sit in persistent UI) — so the honest ceiling is
maybe 2×, not the 3× guessed earlier, and the persistent templates are already
cheap because they stay locked and go through `local_search` at 1.5 ms.
**Evidence.** `projects/books-giveaway/temp/pipeline/track.json`.

### KI-018 · open · recall · Recall against the OCR hits overstates coverage

**Symptom.** Every source scored 90–100 % recall, and a dense OCR of the
rendered trailer then found **23 readable secrets in 75 seconds** — IBANs and
PANs on the Privat24 clip that recall had scored 9/10.
**Cause.** `--recall` scores the tracker against the same sparse OCR hits the
templates were cut from (0.25 fps = one frame in four seconds). A tracker that
covers exactly those frames and nothing between them scores ~100 %. The metric
shares its blind spots with the thing it measures.
**Fix.** Do not trust recall as an acceptance test — it is a *regression* test
for the tracker, useful because it is seconds. Acceptance is a dense scan of
RENDERED output: `scan-pii --fps 1 --skip-static 0` on the draft (75 s, ~2 min)
in the inner loop, and `render-gate.py` on the final. Raising the OCR sample
rate would narrow the gap but never close it.
**Evidence.** `projects/books-giveaway/temp/pii/DRAFT.pii.json`, 2026-08-31.

### KI-019 · fixed · review · The sheet shows first appearances, so it clears a secret its later frames leak

**Symptom.** The reviewer approved "iban 57" from the sheet; the same IBAN was
readable at 0:08–0:12 of the trailer.
**Cause.** One tile per secret is the right density for a human, but the tile
is its FIRST appearance — where the tracker is most likely to have it, since
that frame is usually the one OCR read.
**Fix.** The sheet remains the look review; correctness is the draft scan and
the gate. The sheet now says so in its header.

### KI-006 · fixed · ocr,track · The `fps` filter labels the sampling slot, not the frame

**Symptom.** Templates cut from OCR hit times were blank; tracker recall 46 %
on frames it had cut its own templates from; 183 leaks on a rendered film.
**Cause.** `-vf fps=0.25` emits, for the output frame stamped 16 s, whichever
input frame fell inside that 4-second slot — and rewrites its pts to 16.0. The
hit was at ~20 s.
**Fix.** `scan-pii.py` samples with `select=not(mod(n\,STEP))` and reads the
frame's own `pts_time` from `showinfo`. `track-blur.py` also probes the slot
when cutting a template, so scans made before the fix still work.
**Evidence.** `docs/retro-books-giveaway.md`; recall 46 % → 92 % on
`desktop-105144` from this alone.

### KI-007 · fixed · ocr · Rule changes forced a full re-OCR

**Symptom.** Three 30-minute OCR passes over the same footage in one session.
**Cause.** Only the matching hits were persisted; a rule tweak had nothing to
re-run against.
**Fix.** `--ocr-cache` keeps every OCR line per frame; `--from-cache` re-applies
the rules in seconds.

### KI-008 · fixed · render · A filtergraph on the Windows command line dies at 32 KB

**Symptom.** `WinError 206: The filename or extension is too long` — which
names the wrong thing entirely.
**Fix.** `-filter_complex_script`; `screen-cut.py` always writes the graph to a
file.

### KI-009 · fixed · render · `concat` over many file inputs buffers the ones it is not reading

**Symptom.** 2.8 GB RSS, output frozen at 25 MB, no error.
**Fix.** Render per source; join with the concat demuxer and `-c copy`.

### KI-010 · fixed · render · Per-rect blur chains are quadratic in rect count

**Symptom.** 138 rects as 138 split/crop/blur/overlay chains ran at 0.0024×
(a 56-hour ETA).
**Fix.** Blur the frame once and composite it through one mask — the tracked
mask stream, or `masked_blur()` for hand rects.

### KI-011 · fixed · render · Reading a child's stderr before its stdout deadlocks

**Symptom.** The sampler hung with ffmpeg alive and idle.
**Cause.** Waiting for the `showinfo` line before reading the frame blocks
ffmpeg on a stdout nobody drains.
**Fix.** Read the frame first; the log line for it is already out.

### KI-012 · fixed · review · A render was the first time the user saw the look

**Symptom.** Five full renders with black boxes, then pixelated panels, then
two sources cut — the ask was to blur a field. ~1.5 h.
**Fix.** `redaction-review.py`: a before/after sheet and a fingerprinted
approval; the pipeline refuses to render an unapproved look. Rule in the
skill: *if the user has not seen it, it is not approved.*

### KI-013 · fixed · recall · A detector was adopted without measuring it

**Symptom.** Three renders with a tracker whose recall was 27 %.
**Fix.** `track-blur.py --recall` — the OCR hits are a free ground truth; the
pipeline stops below `--recall-min`.

### KI-014 · fixed · gate · A sparse OCR gate read "clean" over a visible card number

**Symptom.** Sampling every 2 s missed the PAN in a Notepad window title;
dense OCR found it 25 minutes later.
**Fix.** `render-gate.py` searches the secrets' own pixels on the render at
1 fps and `--patch`es the manifest; sampling is not a safety check.

### KI-015 · limitation · ocr · OCR is CPU-only here

**Symptom.** ~3 s per 4K-page frame; 12–27 minutes per session.
**Cause.** The venv's `onnxruntime` has no CUDA provider, and swapping in
`onnxruntime-gpu` would replace the build `sherpa-onnx` depends on.
**Workaround.** Parallel per-source processes (`screencast-pipeline.py -j`),
`--skip-static`, the OCR cache. Revisit if a CUDA build that coexists with
sherpa-onnx becomes available.

### KI-016 · fixed · all · A long run piped through `tail` into a log kept only the tail

**Symptom.** The per-source recall table was not in the log and had to be
re-run to be read.
**Fix.** Stages write their own log; never `| tail` a background run.

### KI-017 · limitation · track · Templates only exist for what OCR read somewhere in the session

**Symptom.** A secret typed into a panel in grey 11-px text was never read by
OCR in that recording and had no template until another recording's scan was
pooled in.
**Cause.** The tracker follows pixels it was given; OCR is the only source.
**Workaround.** Pool every same-geometry scan (`--pii` defaults to the whole
manifest); for a secret OCR never reads anywhere, a hand rect.

### KI-020 · fixed · track,activity · A numpy frame-diff was half the tracker's runtime

**Symptom.** The tracker spent ~191 s on the 17-minute source before matching a
single template; nobody suspected the "did this frame change?" test.
**Cause.** `(np.abs(fr.astype(np.int16) - prev) > 12).mean()` upcasts 2 M
pixels into a fresh 4 MB int16 array and then walks it four more times — 5.7 ms
per frame, on **every** frame, changed or not.
**Fix.** `frame_change()` in `track-blur.py`: `cv2.absdiff` + `countNonZero` in
uint8, SIMD, no allocation. **0.35 ms — 13× faster and bit-identical**, verified
over 1800 real frames (max difference 0.0, every `CHANGE_SKIP` decision
unchanged) and end-to-end on `desktop-104945`, whose 12 mask PNGs, `masks.txt`
and box timeline came back byte-identical. `check-screen.py` locks the
equivalence against the numpy spelling, boundary case included.
The same line was in `screen-activity.py` (it needs the boolean array, so
`cv2.absdiff(fr, prev) > delta`): 3.99 ms → 0.23 ms, array-equal.
**Measured and rejected.** Computing the diff at quarter scale — 2.6 ms, *worse*
than full-res OpenCV (the resize costs more than the diff it saves) and it
changes the value, so `CHANGE_SKIP` would need re-tuning for nothing.

### KI-021 · fixed · render · The film was blurred before it was cut, so 83 % of the blur was discarded

**Symptom.** Rendering an 8-minute film out of 47 minutes of footage takes
6:30, and the encode is not the reason.
**Cause.** `build_filter()` applies the blur chain *before* the trims, so the
full-frame gaussian runs over all 47 minutes to keep 8. Measured on 60 s of a
real proxy, producing the same 10 s of output: decode only 1.1 s; cut, no blur
1.7 s; **blur before the cut 8.4 s; blur after the cut 3.5 s**.
**Disproved on the way.** Segment count is free — 100 trims cost 1.66 s against
1.72 s for one, so the 276-cut source is not slow *because* of its cuts. Decode
is free — 56× realtime.
**Fix.** Cut first, then blur. `build_filter()` now paints ONE mask upstream of
the trim -- the tracked mask stream plus a white `drawbox` per `blur`-mode hand
rect, each `enable`-gated in **source** time, which is the only timebase a human
can verify a rect against -- cuts that mask on exactly the picture's segment
boundaries, and runs a single gaussian after the concat. `box` and `pixelate`
rects stay per-rect and upstream: a crop is cheap and a mosaic must be built at
the rect's own scale. Where no tracker ran, the mask is a black frame derived
from the video, never a `color` source (the infinite-source alphamerge stall).
**Measured.** The longest piece (`desktop-115024`, 17 min in, 3:15 out), same
machine, nothing else running: **533 s -> 161 s, 3.3x**. In the pipeline the
render stage went from 0.37x to 1.6x realtime, because the old graph carried
TWO full-frame gaussians -- the tracked mask and the hand rects each brought
their own -- over all 47 minutes.
**Proved equivalent.** Every piece re-rendered and compared frame by frame
against the old-graph render: 14,400 frames, mean SSIM 0.9893-1.0000 per piece,
minimum 0.9839, and **zero frames below 0.98**. Same picture.
**Guarded.** `check-screen.py` asserts the shape: exactly one gaussian, after
the concat; the mask cut on the picture's own boundaries; every soft rect
painted and gated; a box rect still upstream; and no gaussian at all when there
is nothing to redact.

### KI-022 · fixed · gate · The gate sampled with `fps=`, so it patched the wrong seconds — four rounds, no change

**Symptom.** The render→gate→patch loop ran four rounds and rounds 2–4 found
the identical 9 hits; the manifest held the same three rects appended three
times. The frames the gate named were, on inspection, already blurred.
**Cause.** Two. `render-gate.py` sampled the render with `-vf fps=1` — the
slot-labelling trap of KI-006, in the one tool whose job is to name a frame.
The frame it called 133.0 s was at 133.47 s; that stretch of the film runs at
19x, so the label mapped to source 46.6 s while the sharp pixels were at
55.5 s, six seconds outside every window it wrote. And a hit was treated as
an instant: ±3 s of source around a guess, when at 19x one film-second is
nineteen source-seconds and the secret was sharp for a span.
**Fix.** Pass A samples with `scan-pii.frames_of` (`select` + `showinfo`, the
frame's own pts). Every template hit is then **refined** at full rate over
the interval between its neighbouring samples — one template, sixty frames,
sub-second — into the film span it is actually sharp for; the span is mapped
back through the cut and padded by a second, not the sample. An OCR hit,
which has no template to refine by, is widened by the local speed over the
whole unsampled interval. A patch that overlaps an existing gate rect for the
same secret **extends** it instead of appending a twin.
**Still true.** Pass A at 1 fps of film sees one frame in thirty; at 3.18x a
secret shown for under ~3 s of source can fall between samples. `--fps 2`
halves that window at twice the cost (pass A is ~7 min at 1 fps here).
**Evidence.** `projects/books-giveaway/temp/pipeline/converge.log` rounds 2–4;
the 30-fps sweep that located the sharp frames is in the journal, 2026-09-01.

### KI-023 · fixed · all · The Store Python's execution alias broke twice, and every script died invisibly

**Symptom.** Eight parallel workers printed their header line and vanished --
no traceback, no output files, no exit message. Then nothing python would run
at all: `python` gave `Permission denied` under Git Bash, `.venv\Scripts\
python.exe` gave `Unable to create process ... The specified disk or diskette
cannot be accessed`, and the real binary under `WindowsApps\...\python.exe`
gave `Access is denied`. Python 3.11 at `AppData\Local\Programs\Python\
Python311` kept working, which is what proves it is not the disk.
**Cause.** `%LOCALAPPDATA%\Microsoft\WindowsApps\python.exe` is an app
execution alias -- a reparse point, normally 0 bytes with a target. Its target
was gone (`LinkType` and `Target` both empty), so the alias resolved to
nothing. The venv is a shim onto that same alias, so the venv died with it.
`Get-AppxPackage` still reported `Status: Ok`: the package is fine, the alias
is not, and the package state does not tell you so.
**What did not work.** `Add-AppxPackage -DisableDevelopmentMode -Register`
failed with `0x80073D02` -- "resources it modifies are currently in use" --
because python processes were still alive (the status line runs one
continuously, and the killed workers left several). Killing the ones that
could be killed was not enough; some would not die.
**What triggers it.** Both breakages followed the same event: a pool of eight
`python3.13` workers killed hard, mid-run. Once the alias is dead the damage
self-sustains -- the status line spawns `python` every 3 s, each spawn fails
but still opens the package, and `Add-AppxPackage -Register` can then never
win the race (five attempts, 0x80073D02 every time).
**Fix, and it is structural.** A reboot cures the symptom and the next killed
worker pool brings it back. So this repo no longer depends on the Store
Python at all: python.org **3.13.15** installed user-scope via
`winget install --id Python.Python.3.13 --scope user`, and `.venv` repointed
at it -- `pyvenv.cfg` rewritten (`home`/`executable`/`command`) and the dead
alias stubs moved out of `WindowsApps`. Same `cp313` ABI, so `site-packages`
carried over untouched: no multi-GB reinstall, and `numpy 2.5.2 / cv2 4.14 /
onnxruntime 1.29` all import as before. **Do not copy the base `python.exe`
into `.venv\Scripts`** -- it then cannot find `python313.dll` and dies with
`0xC0000135`. The venv's own 255 KB redirector is correct; it reads
`pyvenv.cfg`, so repointing the cfg is the whole job.
**What proved the design.** `_env.bootstrap()` re-execs into `.venv` from
whatever interpreter starts it, so with the aliases gone `python scripts/x.py`
still worked -- entering through the leftover 3.11 and landing in 3.13.15.
That property is advertised in CLAUDE.md; this is the day it paid.
**The lesson that is ours, not Windows'.** A worker pool must write per-worker
logs and its parent must print their tails on failure. Eight children sharing
one stdout produced a silent death that looked like a hang, and an hour went
into blaming thread oversubscription for something that was never running.
`film-redact.py --detect` now gives each shard its own `detect.<i>.log`.

### KI-024 · fixed · ocr · Eight OCR workers were slower than one, and no env var could stop it

**Symptom.** `film-redact.py --detect` on 8 workers managed **0.21 rep/s**.
One process doing the same work, unthreaded, does **0.37 rep/s** -- the pool
was 1.8x slower than not having a pool, and the first 25 reps per worker ran
at 9.5 s/rep while the next 25 took 29 s/rep as the machine warmed up.
**Cause.** onnxruntime does not read `OMP_NUM_THREADS`, `ORT_NUM_THREADS`,
`OPENBLAS_NUM_THREADS` or `MKL_NUM_THREADS` for its intra-op pool. The parent
set all four and every worker still opened a pool per core: eight processes x
eight cores = 8:1 oversubscription, and the machine spent its time switching.
Measured proof that the variables did nothing: with them set to 2, a rep cost
3.28 s; unset, 3.54 s -- the same number.
**Fix.** Tell the constructor: `RapidOCR(intra_op_num_threads=n)`, exposed as
`--threads` and defaulting to **1**. It is measurably real -- 5.40 s/rep at
one thread against 4.35 s with the default -- and that 1.24x is the whole
scaling onnxruntime has to offer here, which is why the parallelism belongs
between processes and not inside them.
**The number to quote.** **2.7 s/rep**, sampled across the film (0.86-4.36 s,
ten reps spread over all 1,330). The "1.75 s/rep, ~6 min" in the journal was
optimistic by 1.5x and the honest figure for 1,330 reps on 8 workers is
~15 min, not 6.

### KI-025 · fixed · ocr · A killed detection run lost every rep it had OCR'd

**Symptom.** 17 minutes and ~200 reps of OCR vanished when the run was killed
at the tool's 10-minute ceiling. Nothing was corrupt; there was simply nothing
on disk to keep.
**Cause.** Each shard held its results in memory and wrote `detect.json.<i>`
once, at the end. A run that never reaches its end writes nothing at all --
and an hour-long OCR pass over 1,330 frames *will* be interrupted.
**Fix.** Shards checkpoint every `CHECKPOINT` (25) reps -- write a temp file,
`os.replace` it over the real one, so a reader never sees a half-written
file -- and record `done` alongside `per`, so a re-run resumes instead of
re-OCRing. `--fresh` forces the old behaviour. The cost of an interruption is
now one checkpoint per worker, about a minute.
**The other half.** Run it detached (`Start-Process`), not under a tool with
a timeout. A long job should not be hostage to the lifetime of the thing that
launched it -- the same lesson as KI-016, one layer down.

### KI-026 · fixed · render · Film-time redaction had no way to blur what OCR cannot read

**Symptom.** Moving redaction into film time carried the detections across but
not the escape hatch. `sources[].blur` and `blur_extra` are measured in SOURCE
time and mean nothing to `film-redact.py`, so the cases the source-time route
always needed hand rects for — a card face drawn as artwork, text the user has
SELECTED (KI-002), a field OCR never read (KI-017), a name in Cyrillic
(KI-001) — had no route to the mask at all. The only human control was
`decisions.json`, which can *clear* a false positive and cannot add anything.
Left alone, the new pipeline would have leaked in precisely the places the old
one was patched by hand.
**Fix.** A `film_blur` list on the manifest, in FILM time:
`{"rect": [x, y, w, h], "when": [t0, t1], "why": "..."}` — fractions of the
frame, seconds of the film. `mask_runs()` unions them into every state whose
span overlaps the window, and a review decision never clears one: it is there
because a person looked at the frame and the detector could not.
`redaction-review.py --states` shows each on the first state its window
covers, and the approval fingerprint covers the list, so adding a rect
un-approves the look rather than slipping in behind it.
**Watch for.** The gate still only asks whether *detected* boxes are blurred.
It cannot tell you a hand rect is missing, because nothing detected it — that
is what the review sheet is for.

