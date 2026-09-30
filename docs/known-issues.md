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

### KI-027 · limitation · import · yt-dlp needs a JavaScript runtime to reach video streams

**Symptom.** Every yt-dlp call warns "No supported JavaScript runtime could be
found. Only deno is enabled by default". Captions and chapters still come back,
so the warning reads as cosmetic; a format listing is quietly missing the
high-bitrate video streams.
**Cause.** YouTube keeps its signature and `n`-parameter logic inside the player
JavaScript. yt-dlp no longer reimplements that in Python, it runs the player, so
a JS engine is a hard requirement for stream URLs. Without one the formats that
survive are throttled, and the path is deprecated upstream.
**Workaround.** `--js-runtimes bun` (or `node`). Only `deno` is enabled by
default and `requirements.txt` installs none of the three, so the runtime is an
undeclared external dependency. Not needed for what this repo actually asks
yt-dlp for: `yt-fetch-transcripts.py`, `yt-audit-chapters.py` and
`chapter-thumbs.py` want captions, chapters and metadata, and all three were
measured working with the warning present.
**Evidence.** yt-dlp 2026.08.19 on macOS, `g-YDNJcyuck`: the 1080p avc1 rung is
absent from `-F` without a runtime and present with `--js-runtimes bun`.

### KI-028 · limitation · all · cv2 and av bundle different FFmpeg builds, and macOS says so

**Symptom.** On macOS every script that ends up holding both `cv2` and `av`
prints two lines before it does anything: `objc[...]: Class AVFFrameReceiver is
implemented in both .../cv2/.dylibs/libavdevice.61.3.100.dylib and
.../av/.dylibs/libavdevice.62.3.102.dylib ... This may cause spurious casting
failures and mysterious crashes.` Nothing has actually failed because of it.
**Cause.** The two wheels vendor different FFmpeg majors -- OpenCV ships 7.x,
PyAV ships 8.x -- and both register the same AVFoundation Objective-C classes.
The Objective-C runtime allows only one implementation per class name and warns
on the second. Windows has no such runtime, which is why this never appeared
before. Measured: `cv2` alone is silent, `faster_whisper` alone is silent, the
pair warns.
**Reach.** Wider than it first looks. `faster_whisper` imports `av`, and so does
`scenedetect` -- at import time, while registering its backends, before any
`open_video` call -- so `auto-reframe.py` triggers it too. Passing
`backend="opencv"` does not help: `av` is already loaded by then.
**Workaround.** None in this repo's code beyond process isolation, which
`check-env.py` now does for its own import probe because a doctor may as well
be quiet. Removing it for real means aligning the two wheels on one FFmpeg
major (pinning `av` down to a 7.x build, which faster-whisper may refuse) or
building `av` against a system FFmpeg. Neither is worth a warning that has not
yet cost a render.
**Evidence.** macOS 15 arm64, opencv-python 4.14.0.94, av 18.1.0,
scenedetect 0.7.1; `auto-reframe.py` on `bbg-nvidia-hf` warns and then completes
with faces found in 186/186 and 158/160 sampled frames.

### KI-029 · limitation · render · With no GPU, the browser's H.264 takes a bitrate, not a quality

**Symptom.** On a machine with no GPU encoder (the studio's Azure VM) `sketch-render.py --encode
browser` prints `no-encoder: this browser will not encode {...prefer-hardware...}` and renders
through the ffmpeg pipe instead, at a third of the speed.
**Cause.** WebCodecs' H.264 on the GPU accepts `bitrateMode: "quantizer"` (a fixed QP, the `cq`
contract). The browser's software H.264 (OpenH264) does not: Edge 154 on Ubuntu 24.04 offers only
`variable` and `constant`. VP9 and AV1 take quantizer in software, but the master must be H.264.
**Workaround.** `VIDEDIT_WEBCODECS=software` (or `render.webcodecs`) asks for the software encoder
at `VIDEDIT_WEBCODECS_BITRATE` (default 24M). The VM runs 12M: VMAF 99.1 on a painted film, 99.99
on line art; 5M scored 91.6 on the painted film. A bitrate is a ceiling the film does not choose,
so a much busier look than any film so far may want more.
**Evidence.** `studio/deploy/README.md`: D8ads_v5 35 fps software vs 18.8 fps pipe, same frames.

### KI-030 · limitation · all · A laptop film's Claude session does not resume on the VM

**Symptom.** Resuming a timed-out film's Claude session (`ClaudeAgentOptions(resume=sid)`, the
`resume_film.py` route) fails, or works in the wrong folder, for a film made before the studio
moved to the Azure VM.
**Cause.** Claude Code keys a session transcript to its working directory, and the copied
transcripts under `STUDIO_HOME/claude/<film>` record the laptop's `C:\` paths.
**Workaround.** Finish such a film from its files (the studio's tools), not by resuming the
session. Films made on the VM resume as before.

### KI-031 · fixed · studio · A ship stopped a film and called it cancelled, then restarted onto the old code

**Symptom.** A kitcut.ai film (`studio-20260928-165122-rts664`, 150 s) stopped 28 minutes in with
"The film was cancelled." Nobody had pressed Stop. The studio came back on the release it already
ran, not the one being shipped.
**Cause.** Three things at once. (1) Three `ops.sh ship` runs overlapped, with no lock. (2) The
first one's drain waited its 20 minutes (a 150 s film on the VM may take ~2 h), then restarted
anyway. (3) `serve.sh release` ran `release.py` without `STUDIO_HOME`, so the release was built in
`/srv/kitcut/kitcut-studio`, while the server reads `/srv/kitcut/studio/releases/current`: the
restart changed nothing. On a restart, SIGTERM reaches `make_film` as a plain task cancel, the
same path as the Stop button, so the film was recorded `cancelled`. A film that was mixing or
rendering was recorded cancelled too, so the next server never finished it.
**Fix.** `serve.sh` reads `STUDIO_HOME` from the unit, refuses to restart unless `current` names
what it built, skips a restart onto what is already live, and holds `deploy.lock`. `ops.sh resume`
(`studio/resume.py`) finishes a stopped film through Claude's own saved session, in the same film,
its earlier cost carried. A stopping server tells its films why (`server.shutdown()`): one Claude
was writing is recorded `interrupted` with a line on its page, one being mixed or rendered is left
`finishing` for the next server, and the unit runs `KillMode=mixed`. Then (2026-09-29) one server per release: a ship starts the new release as its own
`kitcut-studio@<instance>` beside the running one, which finishes its films and exits; nothing
waits and nothing is stopped (`studio/peers.py`, `serve.sh switch`, `studio/deploy/README.md`). Live on the VM since 2026-09-28 21:55 PDT.
**Evidence.** VM journal 2026-09-28 17:19:13 PDT (`Stopping kitcut-studio.service` in the same second
as the film's last event); `/srv/kitcut/kitcut-studio/releases/266ba5829609` built beside the
server's home; ship sessions from the laptop at 16:58, 17:08 and 17:13.

### KI-032 · fixed · studio · On the VM every film step ran with no memory cap

**Symptom.** The studio's log on the VM: `procs: no delegated cgroup ([Errno 16] Device or resource
busy): steps run with no memory cap` (2026-09-28 13:40 and 16:08, once per server start). The unit's
cgroup had no `server/` leaf and an empty `cgroup.subtree_control`.
**Cause.** `procs.cgroup_root()` was set up lazily, at the first step. By then the first film's
Claude Code child was already running in the unit's cgroup, and cgroup v2 refuses to hand the memory
controller to children while the group itself holds a process. The failure is cached, so the
server ran uncapped for its whole life.
**Fix.** `server.main()` (and `resume.py`) call `procs.cgroup_root()` at start, before any child.
**Evidence.** `/sys/fs/cgroup/system.slice/kitcut-studio.service`: `subtree_control` empty, no
`server/`, on 2026-09-28 after films had run; the same EBUSY in the first `ops.sh resume` unit.

### KI-033 · fixed · studio · A switch hung one request ~5 s through the tunnel

**Symptom.** At each of the first two switches on the VM, one request through studio.kitcut.ai
took the probe's whole timeout (5-8 s) about 3 s after the old server handed over; 398 requests
straight to the port in another switch all answered in 2 ms.
**Cause.** The old server closed the tunnel's held keep-alive connections itself at the handoff
(aiohttp `pre_shutdown`), which can cut a request already on one.
**Fix.** `server.bye()`: after the handoff the old server answers what still reaches it on those
connections and tells the client to close each after its reply. Measured after: 44 requests through
a switch, none failed, slowest 1.2 s. The first switch after shipping this fix still blips once
(the old code does the handing over).
**Verified on the VM 2026-09-29.** A film made on an old server through two switches finished done;
rollback took 11 s and stopped nothing; a SIGKILLed leader restarted, led, and marked its orphaned
film interrupted with a line on its page, leaving another server's films alone. Still to check at a
quiet moment: a reboot (`kitcut-studio-boot` starting the current instance).

### KI-034 · fixed · studio · A long film's picture, written in one reply, never came back

**Symptom.** The 8-minute film llwtme sat for about an hour, twice, right after its narration was
recorded: no events, no cost, the Claude Code process alive, its transcript showing `Request timed
out.` every 5 minutes (retry n of 10). The API answered other requests at once.
**Cause.** The next reply was the whole picture: 56,863 output tokens, 7.7 minutes (measured once
the timeout was raised). Claude Code's request timeout was shorter, so it cut the reply off and
asked again from scratch, forever. Three things grow with a film's length and meet here: the
reply that writes the picture (57k tokens at 8 minutes; one reply may not pass 128K), the context
Claude carries (73k at the start, 371k at the end: ~37k a minute of film, against a 1M window),
and the narration tool's results (all 67 lines' word timings, 24,000 characters, every recording).
**Fix.** `API_TIMEOUT_MS` 30 min and `CLAUDE_CODE_MAX_OUTPUT_TOKENS` 128000 (agent.claude_env); a film
over 90 s is told to write its picture in parts and to leave a closing breath (agent.LONG_FILM,
closing_s); a long narration's result carries each line's span and only the re-recorded line's
words (tools.timeline_text); and a stall watchdog (agent.Pulse, talk_to_claude): 20 minutes with
no message from Claude Code, no event and no tool at work cuts the reply off and picks the session
up again with "shorter replies", at most twice -- then the film fails, and is refunded, instead of
waiting hours. `ops.sh claude-log <film>` shows a film's replies, waits and stalls in one page.
**Still open.** The film is one file written by one conversation that grows with it: past ~18
minutes the picture cannot be written in one reply at all, past ~25 the conversation outgrows the
window. The plan -- scenes as the unit of work, each in a fresh bounded conversation -- is in
`docs/todo.md`.
**Evidence.** `ops.sh claude-log studio-20260928-220505-llwtme --all`.

### KI-035 · limitation · thumbnails · OCR cannot vouch for a thumbnail's words in Cyrillic

**Symptom.** `thumb-options.py --ocr` (and the bake-off) report `None` for a Ukrainian option's
legibility at feed size.
**Cause.** RapidOCR's recognition model reads Latin script only: at 168 px it read "Знахідка в
лісі" as "3HAXIAKA BΛICI" -- the shapes are legible, the alphabet is not its own.
**Workaround.** None needed for the check that gates: the cap height at 168 px (>= 8 px) is
measured from the layout and holds for any script. Only the second opinion is missing.

### KI-036 · limitation · thumbnails · Saliency misses a painted film's big subjects

**Symptom.** On painted films (`look: painted`), the subject map lights scattered specks and
leaves the hedgehog and the squirrel that fill the frame dark; words placed by it alone would sit
on them.
**Cause.** Spectral-residual saliency finds what is small and different; a subject that fills half
a painted frame is neither. Coarser scales did not fix it and lit up whole clean frames instead
(bake-off 2026-09-29, `docs/reference.md` "Thumbnail options").
**Workaround.** The draft's Claude call, which sees the moments, names each option's `place`; the
subject map only fine-tunes inside it. An option with no `place` on a painted film can still land
on a subject.

### KI-037 · limitation · youtube · A channel that is not verified cannot take a custom thumbnail

**Symptom.** A kitcut.ai publish finishes, and the dialog says "The thumbnail wasn't set: YouTube
lets a channel use its own thumbnails once the channel is verified...". The video has YouTube's
own frame.
**Cause.** Custom thumbnails are an "intermediate" YouTube feature (support.google.com/youtube/
answer/9890437): the channel needs a verified phone number. `thumbnails.set` answers 403
`forbidden` without one.
**Workaround.** The person verifies at youtube.com/verify and picks the thumbnail in YouTube Studio.
The publish itself never fails on it (`api/youtube.js` setThumb).

### KI-038 · limitation · thumbnails · A film that titles itself without SK.txt gets a stock type

**Symptom.** A film's thumbnail words are in the tooling's Montserrat (or Balsamiq on a drawn
film), coloured in the film's own text and accent colours, rather than in the type its titles use.
**Cause.** The probe (`sketch/thumb.js`) learns a film's type from its `SK.txt` calls. The wine
film `studio-20260928-110106-skiird` writes every title with its own vector pen
(`P.lineText`, strokes in code, no font file), so there is no font to measure or draw with; 1 of
40 films on the laptop (2026-09-29).
**Workaround.** None yet. If more films take the pen, the probe can report its advance widths and
`thumb.js` draw with it; the layout needs only widths and a cap height.

### KI-039 · limitation · thumbnails · A card, panel or glow can cover the edge of a drawing

**Symptom.** A thumbnail's words sit on a glow or card that hides the bottom of a calendar card
or a phone in the frame: readable, but it looks like a collision.
**Cause.** Only the film's *words* are protected exactly (OCR boxes: hidden whole or not at all).
Everything else is weighed by the subject map, which misses flat UI drawings on clean films as
it misses big painted subjects (KI-036).
**Workaround.** The draft's `place` steers it; the person picks one of four and can choose
another.

### KI-040 · fixed · studio · A scene pass thought past its whole allowance before writing a line

**Symptom.** The first real film made in scenes (i4d52n, 8 minutes, 12 scenes, collage, on the
login) failed with "the scene did not finish in 2 tries". Scene 2 read its files, then Claude
Code received only keep-alive pings (36 bytes every 30 s, `[Stall] stream_idle_partial`) until
the pass's time ran out, twice. No API errors, no rate limit; the login's output speed matched the
key's (316 vs 317-321 tokens/s on comparable films).
**Cause.** At effort xhigh, Opus thought for over 10 minutes before the first token of a
40-second scene, and a scene pass got 8 min + 3 per minute of scene, i.e. 10 minutes. The
director had also needed a second try: its 28 minutes went on narration retakes. And the film's
own limit (film.limits, sized for one conversation: 136 min at 8 minutes) could not have held
a director plus eleven scenes at any per-scene figure that works.
**Fix.** Passes in scenes mode think at `scenes.EFFORT` = high (a picked-up pass too); a scene
gets 20 min + 3 per minute, the director 40 min + 20 s per minute of film; a scenes film's Claude
time is the sum of its passes' (`scenes.film_claude_s`). i4d52n was resumed onto it.
**Evidence.** `ops.sh claude-log studio-20260929-103129-i4d52n --all`.

### KI-041 · fixed · studio · A narration that ran past the film's end failed the whole film at the mux

**Symptom.** u3edgl (2:30, painted, on the login) wrote, painted and rendered all 9,000 frames,
then failed: `mux failed ... rendered 150.96s, expected 150.00s`. Its twin from the same prompt
(w3vfyn) came out fine.
**Cause.** Its narration overran: it spent the film's six recordings ("keep the narration you
have") and its last line was placed at 150.99 s of 150. `_sketch.captions` clamped each cue's end
to the film's end but not its start, so the last cue ran backwards (`00:02:30,987 -->
00:02:29,950`); ffmpeg's `-t` trims the audio and video but a mov_text sample keeps its length, so
the subtitle track outlasted the picture and the duration check refused the file. Claude never
knew: `sketch-vo.py` prints "voice ends at ..., after the film's ..." only to its own log, and the
voice tool hands back just the timeline.
**Fix.** No cue from the film's end on, none backwards, none past the picture (`_sketch.captions`,
check-sketch "captions: nothing after the film's end"); the voice tool's result opens with a NOTE
when the narration ends after the film (`tools.timeline_text`, test_server). Still open: a film
that has used its last recording can only keep the overrun, and loses the words past the end.
**Evidence.** `/srv/kitcut/studio/projects/studio-20260929-121021-u3edgl` (events.jsonl,
outputs/film.srt).

### KI-042 · fixed · studio · A collage film made in scenes could order no cut-outs

**Symptom.** i4d52n (collage, 8 minutes, scenes) has no pictures at all: every scene drew its
bikes in code ("there are no painted images yet"), and scene 2 went looking for
`images/spec-epic.webp`, which was never painted.
**Cause.** The director's write list allowed `paint.json` only when `film.look == "painted"`.
Collage paints too (its recipe carries `cutouts`), so the director's two writes of `paint.json`
(at 395 s and 1992 s) were refused, and no later pass may write it.
**Fix.** `agent.director_files()` allows it whenever `film.paint_kinds(film.caps)` is not empty;
`test_scenes.py` checks every look.
**Evidence.** `blocked` events at 395.1 and 1991.6 in i4d52n's events.jsonl.

### KI-043 · fixed · studio · A non-English narration's word timing starves behind renders on the 4-vCPU VM

**Symptom.** c6ckpu (90 s, Spanish, drawn, 2026-09-29) spent 17.6 of its 38 Claude minutes in
one `voice` call, then stalled 13 minutes thinking before its first line of film.js and ran out
("Claude ran past the 38-minute limit"). Resumed, it wrote the whole film in 124 s of Claude time.
Its Ukrainian twin 4kr5hv (90 s, collage, started 16 minutes later) went the same way: its first
`voice` + `paint` call took 19.5 minutes, two more voice runs 10, then the limit. Both English
films made beside them (small.en) finished on time.
**Cause.** sketch-vo.py's `score` stage (Whisper, word times for Gemini's takes) took 1,040 s for
13 lines, and 288 s to re-time one. English scores on small.en; every other language on
large-v3, on the CPU (int8). At that moment the 4-vCPU machine was rendering four things (load
9-13): two films on the handed-off server, one on the new leader, and a `resume --finish` unit.
Each server and each resume unit has its own pools (browser 4, cpu 2), so a ship's handover or a
resume multiplies the machine's real concurrency; and the step cgroups enable only the memory
controller, so nothing gives a scoring step priority over a render.
**Measured.** On the laptop's CPU, int8, 4 threads, the real takes of c6ckpu (13 es) and 4kr5hv
(15 uk): large-v3 128 s / 157 s, large-v3-turbo 103 s / 113 s (1.2x / 1.4x faster); mean acc
0.904 -> 0.908 (es), 0.947 -> 0.967 (uk), turbo equal or better on every line; word starts differ
by a median 0.08-0.10 s, max 0.72 s. So the model is not the lever -- uncontended, large-v3 times
a 90 s narration in ~2 minutes; contention cost 15 more.
**Options (not done).** Make renders yield: `cpu` in the delegated subtree_control and a low
`cpu.weight` on the final render's and web copy's step cgroups (nice works only inside one
server's cgroup, and this incident's load came from other units); count other servers' and
resume units' renders in the browser pool; turbo as the multilingual default (measured above:
modest speed, no loss).
**Fixed (2b364f6, 2026-09-29).** The studio's takes are scored off the machine, by Whisper
large-v3 on Groq through OpenRouter (`studio/procs.py` SCORER), 8 at once, and a take's score is
remembered (`<take>.score.json`). The Ukrainian freelancers episode (pzk2ay) scored its
narration in 667 s and 607 s; the blogger episode (gkyv6q, same series, same length class, the
next morning) in 3.0 s and 2.5 s. Held to a local large-v3 on the same Ukrainian takes: no bad
take missed, word starts 0.08 s apart (docs/studio-speed.md). Renders still do not yield to
other steps; that part of the options above stands for whatever runs on the CPU next.
**Evidence.** `/srv/kitcut/studio/projects/studio-20260929-130142-c6ckpu/temp/pipeline/runs/`,
`ops.sh claude-log studio-20260929-130142-c6ckpu`.

### KI-044 · open · studio · A film that ends on a fade or on bare paper gets a blank gallery card

**Symptom.** Apollo 13 (w3vfyn, painted) showed in kitcut.ai's gallery as a black tile with a
ghost of its title: its poster is the frame 0.4 s before the end (`film.py`: `poster_t`), which
was the fade-out of its closing card.
**Measured.** The 70 posters in the public gallery on 2026-09-29: 2 near-black (mean < 30,
contrast < 25: 2ohqb3, ekvghs) and 4 near-white bare paper (mean > 250, contrast < 10: l7bd42,
il6box, 7c7q5d, ebqs2d) -- 6 of 70. `media.make_card` already swaps a mid-fade poster for the
liveliest of four frames, but only for card.jpg (link previews); the gallery and the film page
show the poster itself.
**Workaround.** Replace `outputs/film_poster.png` with a chosen frame, delete `card.jpg`, then
`studio/media.py --film <id>` in the current release with the studio's env (done for w3vfyn at
144 s). **Fix (not done):** give the poster make_card's fallback, or let the gallery use the card.

### KI-045 · fixed · studio · A share back-fill held 15 GB, and the films being made could not start Claude

**Symptom.** 2026-09-29 21:38 PDT: two films failed 80 s in with `Control request timeout:
initialize` (wtv3gp, and g3lna7, a Pro project episode). The Claude CLI could not start: the VM
had 132 MB available of 16 GB. The page then showed the failed episode as a dead tile (site
f567f72 fixed that: open, Try again, Edit idea).
**Cause.** `ops.sh share --missing` (studio/share.py, started 19:41 for 97 films) ran every film's
thumbnails in one process, and `scripts/_thumb.py load_still` kept every decoded still in a
module-level dict, never evicted. Measured: 55 films' stills on disk = 2,196 stills of 1920x1080
= 13.66 GB decoded RGB, against the process's 15.4 GB RSS. The server makes one film's pictures at
a time and never grew enough to notice; a back-fill does many. Its own pictures then failed too
("no progress from the page for 90s"), because the browser had no memory either.
**Fix.** `load_still` is a least-recently-used cache capped at `THUMB_STILLS_MB` (600: two films
at once); 200 stills now hold 597 MB instead of 1,244. `ops.sh share` runs the back-fill with
`MemoryHigh=2G MemoryMax=3G Nice=10`, so a leak there kills the back-fill, not the films. The two
films were made again as their owners through the site's createFilm (pzk2ay, py7ko5).
**Lesson.** A batch job beside the live server needs a memory cap before it starts; watch
`free -m` while it runs.

### KI-046 · limitation · studio · YouTube labels some studio films "Made with AI", and we cannot see why

**Symptom.** `watMf06668M` and `V25n5_k7v_c` (public studio films on @kitcut-hq) show "How this was
made: Made with AI" under the player. No upload on either channel has `containsSyntheticMedia` set,
and an explicit "no" through `yt-set-disclosure.py` did not remove it.
**Cause (likely, not proven).** YouTube's own labelling from Google's SynthID watermark in the
Gemini TTS voice every studio film uses. Other studio films carry no label yet, so the voice is not
a sufficient trigger on its own, or the check runs late.
**Limit.** The watermark is not visible to local analysis (reference: "Can we see the watermark
ourselves?"). Only Google's detectors can confirm it: the Gemini app, or the SynthID Detector
portal behind its waitlist.
**Evidence.** `yt-set-disclosure.py --list --labels` on both channels, 2026-09-30; the Gemini vs
ElevenLabs vs edge-tts probe in the same reference section.

### KI-047 · mitigated · studio · The narrator mis-stresses a name, and no check can hear it

**Symptom.** The Ocheretyne Economics School series (p-mii4mannfx, Ukrainian, Gemini
Sadachbia): «Очеретинська» must be stressed on its third syllable (ОчерЕтинська). The openings of
the freelancers, blogger and cashback episodes said ОчеретИнська; their closings, the same word,
were mostly right. The person heard it; nothing in the pipeline did.
**Cause.** The TTS picks a word's stress afresh on every take -- a rare name has no entry to look
up, so it guesses by analogy (-инська like «українська»). The check after recording (Whisper)
turns speech into text, and both stresses are the same text: a mis-stressed take scores 1.00.
**Measured (2026-09-30, 12 takes of one line, two LLM judges x 3 votes).** Plain text right in
about half the takes. A stress mark (Очере́тинська) 2/6 on every take -- worse; a capital vowel
3-5/6; a spoken instruction in the style 0-2/6 -- worse. Gemini-TTS documents no phoneme input;
Chirp 3 HD's custom pronunciations exclude uk-UA. The LLM judges (Gemini 3.5 Flash, 3.1 Pro)
read the film's own right and wrong lines right at temperature 0, but gave the same greeting 6/6
alone and 3/6 inside a joined line: a hint, not a gate.
**Mitigation.** A project's approved voice lines (docs/studio-voice-lines.md): a recording the
person approved plays for the same words in the same voice in every later episode, never
re-recorded. The series' greeting and sign-off are approved (`studio/voicelines.py`), so its
openings and closings are right from now on. The three episodes above were repaired by hand:
the approved greeting joined to each opening's own «Сьогодні — про ...» in the sentence pause
(cut at the RMS dip: Whisper's word boundary once fell inside «ки»), re-rendered with
`ops.sh resume --finish --patched`.
**Open.** The name elsewhere in a narration is not protected. Next: a watch-word list with each
word's stress, several takes of a line containing one, the take picked by comparing the word with
an approved recording of it -- once that comparison is measured against takes the person labels
by ear.

### KI-048 · fixed · studio · A collage film's thumbnails, moments sheet and share picture had no cut-outs

**Symptom.** 2026-09-30: the four YouTube thumbnail options for gvenrk (a collage kids' episode,
clay doctor and cashier on cut paper) were slides with empty starbursts where the characters
should be -- the channel's owner called them "a random still". The moments sheet the draft's
Claude call chooses from had the same holes, so it chose frames without seeing their subjects,
and so did every collage film's share-page picture.
**Cause.** `_thumb.film_images` kept its own copy of where a painted picture lives and knew only
`images/<name>.jpg`; a cut-out is `.webp` (it keeps its transparency). The stills' manifest copy
drops `paint` and lists the pictures itself, so none of the cut-outs reached the page and
`SK.cutout` drew nothing.
**Fix.** One rule, `_sketch.painted_images()`, used by the render and the thumbnails alike; the
stills cache key names how stills are drawn (`_thumb.STILLS`, now v2), so every film's stills are
made again, and options saved under the old design are remade (`_thumb.DESIGN`).
**Lesson.** Two copies of one path rule drift; and a check that reads only the finished picture
(legible, in contrast) passes a picture of nothing. Look at the frames.

### KI-049 · fixed · studio · A narration past the film's end, with no recording left, failed the film at its mix

**Symptom.** 2026-09-30: film ewwd6b (a 3-minute KitCut explainer, owner account) failed after 24
minutes with `ValueError: operands could not be broadcast together with shapes (0,) (189094,)`
from `_sketchaudio.build_vo`. Its narration ended at 199.8 s of 180.
**Cause.** Two things. The prompt asked for more than 3 minutes of narration: the first recording
ran 267 s. The second ran past the end too, and Claude spent the other four recordings (the
limit is 6, retakes included) re-taking lines whose Gemini takes had long tails, which never made
the narration shorter. With no recording left it could not fit the narration, could not edit
`timeline.json`, and every sound check crashed. A line that *starts* after the end has nowhere to
go; `x[: len(vo) - i0]` with a negative stop is not empty, hence numpy's error.
**Fix.** `build_vo` names the lines that start after the end. The sound tool says the same before
it runs, with the recordings left. While the narration does not fit, a film may record
`tools.FIT_RUNS` (2) times past its limit. After a recording that does not fit, the voice tool
says how many are left and that only fewer words make a line shorter. (`check-sketch.py`,
`test_server.py`.)
**Lesson.** A limit with no way out turns a fixable fault into a failed film: when a limit stops
the fix, the fix gets its own allowance. And a dense brief is the first cause. The remake with
the narration held to about 400 words fitted (36 lines, 206.8 s of 210).

### KI-050 · fixed · studio · A YouTube draft was refused as a pasted brief when a chapter heading met the next sentence

**Symptom.** 2026-09-30: `ytdraft.py` on film wm4ioh (the KitCut explainer) gave up with "the draft
kept repeating the brief (it repeats the brief: "making a film say the idea the")", every retry.
**Cause.** `leak()` flattened the draft and the brief into one stream of words each, so a run of
seven could cross a sentence's end. The brief had the heading "Making a film." over "Say the
idea, the length and the look"; the draft had the chapter "Making a film" over the narration's
own "say the idea, the length and the look". Neither side pasted anything, and the narration
check could not help, because it says "To make a film".
**Fix.** Runs are counted inside one sentence or line of each (`_clauses`). A paste of the brief's
sentence is still caught (`test_ytdraft.py`).
**Lesson.** A prompt with headings is how people write structured briefs, and a good draft names
its chapters after the film's parts. A copy check has to respect sentences, or it flags exactly
the drafts that follow the film most closely.
**Still open.** After the fix, wm4ioh's draft was refused for "make a whole film without leaving
your": the brief's hook, which the film says with one word more ("without ever leaving") and
writes on screen ("A whole film, without leaving your chat."). Only the narration, the maker's
notes and the sources count as the film's own words; its on-screen words do not. A brief that
scripts the film's lines can still leave the person to write the draft themselves.

### KI-051 · mitigated · studio · A person's own voice can stop speaking half-way through a film

**Symptom.** A film narrated in a person's own ElevenLabs voice depends on their account for as
long as it is being made: it can run out of characters, have its key deleted or a permission
removed, or lose the voice, after the film has started. Before, any refusal from ElevenLabs ended
the step with ElevenLabs' own words, and Claude could only fail the film.
**Cause.** Nothing about another company's account can be settled before the film starts: the
site's check (it can still speak, the voice is there, characters enough when the key may say)
lowers the odds, not to zero -- and a credit limit on the key itself is invisible to it.
**Mitigation.** The film pauses instead of failing: `sketch-vo.py` says why in one
`VOICE-BLOCKED` line and exits 75, `tools.voice` tells Claude to stop and `agent.Parked` ends the
session whole, the film is `waiting` (not final: the site keeps its credits held), and Continue
picks the session up (`server.continue_film`, `agent.RESUME_VOICE`). The takes already made are
kept and not paid for again. A film waits up to `STUDIO_WAITING_DAYS` (7), then it is put down and
refunded.
**Lesson.** Where a film leans on a person's own account, a failure there is theirs to fix, not
the film's to die of: pause, say what to fix, keep what was made.

### KI-052 · open · studio · Professional voice clones are not measured on eleven_v3

**Symptom.** The site sends a professional clone in `eleven_multilingual_v2` and every other
ElevenLabs voice in `eleven_v3` where ElevenLabs lists the voice for it (`lib/narrator.js
pickModel`). Whether v3 reads a professional clone as well, as like the person, and as cleanly at
the end of a line, is not known here.
**Cause.** The team's own ElevenLabs plan is below the tier that makes professional clones, so
none could be measured. Instant clones, designed and library voices can be.
**Next.** `scripts/vo-model-bench.py` (planned: accuracy by the production scorer, clipping,
speaker similarity to a reference recording, a blind listening page) on a professional clone,
before the default changes.

### KI-053 · open · studio · A release before waiting films existed reads one as lost

**Symptom.** A server of a release from before 2026-09-30 does not know the state `waiting`: its
status route calls such a film `lost`, and it would not continue it.
**Cause.** A new state name in `studio.json`, read by every release that shares the home.
**Rule.** Never roll back past the release that brought `waiting` while any film is waiting
(`ops.sh` status lists them). A continued film pays one uncached re-read of its Claude context,
about $0.5-1 on a long film: the cost of pausing, instead of failing and making it again.
