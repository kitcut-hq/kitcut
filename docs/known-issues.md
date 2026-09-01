# Known issues and limitations

The register. One entry per thing that bit us or that the tools cannot do,
with a fixed shape so a person and a script can both read it. This is the
canonical home; `README.md ## Gotchas` keeps the prose for traps in tools we
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

**Symptom.** Alt-Tab shows a Notepad card titled `*4149… - Notepad` and the
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

### KI-005 · open · track · Tracking cost is quadratic in pooled templates

**Symptom.** Tracking 47 minutes of footage took **82 minutes** with five
workers (was 8 minutes before pooling and the full-resolution search).
**Cause.** Every lost template (~85 per source after pooling, × 3 scales) is
swept at full resolution on every change frame while warm and every 15th
frame while cold. With most templates absent from most of the film, that is
hundreds of full-frame NCCs per change frame.
**Done so far (2026-08-31, 131 s → 42 s on the 60-second test source, recall
unchanged).** Coarse-first for every template — a permissive half-scale
prefilter (0.50) with full-resolution confirmation of a few candidates, instead
of full-resolution sweeps for small text; foreign templates (pooled in from
another recording) patrolled every 60 frames instead of 15 and never on a page
change; "warm" shortened from 3 s to 1 s; no sweeps at all for a caret-blink
change; scale variants only for a warm template on a big change; one OpenCV
thread budget per worker (`--threads`, set by the pipeline).
**Still open.** Bound sweeps to the windows the OCR cache says a secret is on
screen, with a slow patrol outside them — that is where the next 3× is.
**Evidence.** `projects/books-giveaway/temp/pipeline/track.json` (4950 s before).

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
