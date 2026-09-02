---
name: video-screen-cut
description: Edit one or more screen recordings that carry NO usable audio into a single film — drop the dead air, fast-forward the stretches where only an AI side panel is streaming, and blur card numbers, CVVs, IBANs, phone numbers, emails and delivery addresses before anything is published. Use when asked to edit a screen recording or screencast that has no narration, to cut the pauses or boring parts out of a demo/desktop capture, to speed up or fast-forward parts of a screen recording, to hide or blur sensitive data (bank card, CVV, phone number, address, balance) in a video, or to turn a session of raw desktop captures into one watchable video with a voice-over added later.
---

# A film out of silent screen recordings

**Wrong skill?** If the screen recording is paired with a **camera take that
carries the sound**, use `video-multicam` (`sync-tracks.py` +
`screencast-cut.py`) — it cuts on speech and composites the two. This skill is
for recordings with **no usable audio at all**, where the picture is the only
signal and the voice-over is added afterwards.

```powershell
# from the repo root -- this is the whole job
python scripts/screencast-pipeline.py --project <id> --target 8:00            # stops at the review sheet
python scripts/screencast-pipeline.py --project <id> --target 8:00 --approve --upload unlisted
```

**Run the pipeline, not the scripts.** The first edit of this kind took six
hours as forty hand-typed commands (`docs/retro-books-giveaway.md`); the
pipeline runs import → proxies → activity → ocr → track → **recall** →
**review (STOP)** → smoke → render → gate → upload, caches every stage, and
refuses to render a look nobody has approved or a tracker whose recall is
below the bar. The individual scripts below are for diagnosis and for adding
capability, and each still has its free mode.

Before designing anything here, read `docs/known-issues.md` — the register of
what the tools cannot do (`limitation`), what is known and unfixed (`open`),
and what already bit us (`fixed`, kept for the symptom→cause lookup). The
pipeline prints the relevant entries at start; when you hit something new,
add an entry with the fixed header shape (`check-screen.py` parses it).

The pipeline stops **twice**: at the redaction sheet (stills) and at the
draft trailer (`--hot --draft`: the riskiest minute at half resolution,
motion). The final render starts only after both are approved. Proof must be
cheaper than the product, or nobody waits for it.

Three rules the pipeline enforces, learned the expensive way:

1. **Never render a look the user has not seen.** The review sheet
   (`temp/review/redaction-sheet.jpg`) is the stop. Blur, not boxes; fields,
   not regions; the AI panel stays readable except the sensitive field.
2. **Never adopt a detector you have not measured.** `track-blur --recall`
   scores the tracker against the OCR hits in seconds; the first tracker
   scored 27 % on frames it had cut its own templates from, and three renders
   went out before anyone asked.
3. **The gate reads the render, and closes the loop.** `render-gate.py`
   searches the secrets' own pixels on the output and `--patch`es the manifest
   for anything it finds; a sparse OCR "looks clean" is not a gate. Two
   things it must keep doing (KI-022): sample by the frame's **own** pts
   (`frames_of`, never `fps=` — the label is the slot, and at 19x a
   half-second of label is nine seconds of source), and turn each hit into
   the **span** it is sharp for before mapping it back. A loop that patches
   the same rect twice is not converging; it is patching the wrong seconds.

The worked example is `projects/books-giveaway/screen.json`. README has the
reference under "A screencast with no soundtrack at all".

## The project folder comes first

Every video lives in `projects/<id>/` — its manifests, its content dirs, and two
committed metadata files. Before doing anything, read
`projects/<id>/project.json` (create the folder with
`python scripts/project-scan.py --init <id>` if this is new) and skim
`projects/<id>/journal.md` if the ask touches past decisions. `screen-cut.py`
records its own renders; anything you run by hand you record yourself. End the
session with a prose note in `journal.md` for the next one.

## Check the audio before you plan anything

This whole pipeline exists because of one measurement. Run it first:

```powershell
ffmpeg -hide_banner -nostats -i <src> -af volumedetect -f null - 2>&1 | Select-String "mean_vol|max_vol"
```

`mean_volume: -91.0 dB` **and** `max_volume: -91.0 dB` is digital silence — not
room tone, literally zero samples. Windows' Game Bar window capture does this
when no microphone is selected. If you see that, `screencast-cut.py` cannot
help: every silence threshold it has resolves to "cut everything".

Do not skip to transcription to check. On this footage one recording had a
*little* ambient noise (-56 dB mean) and looked promising; faster-whisper
returned **0 words** from four minutes of it. Measure, don't hope.

## Order the sources by when they were shot, not by filename

Windows names a capture for the moment it *stopped*; Android names a screen
recording for when it *started*; a phone camera file is stamped in **UTC** while
the desktop files are local. Sorting a mixed set by name silently interleaves
them wrong.

- `PXL_YYYYMMDD_HHMMSS.mp4` — UTC, from the camera roll (`DCIM/Camera`)
- `screen-YYYYMMDD-HHMMSS-*.mp4` — local, an Android **screen recording**, and
  it lives in `Movies/`, **not** `DCIM/Camera`. Look there before concluding
  there is no screen recording on the phone.
- `Recording YYYY-MM-DD HHMMSS.mp4` — local, Windows Game Bar

Also: Windows writes the same capture to `Videos\` **and**
`Videos\Screen Recordings\` with timestamps a few seconds apart. They are byte
identical — check with `head -c 5000000 | sha1sum` before treating them as two
takes.

`Shell.Application` sorts MTP listings as **strings**, so `9/9/2025` sorts above
`8/31/2026`. Sort by the date embedded in the filename instead. Getting footage
off the phone: see the MTP section of the `video-multicam` skill.

## Transcode once, before anything else

```powershell
python scripts/make-proxies.py --manifest projects/<id>/screen.json --verify
```

Every other pass decodes the source and throws most of it away in its first
filter, and that decode is the dominant cost of the pipeline. One transcode to
the canvas fit size, recorded on each source, and `screen-cut.py` picks it up
automatically (`--no-proxy` opts out). Here: 4.5 GB -> 38 MB.

This is not a quality trade, because **every rectangle in this pipeline is a
fraction of the frame, never a pixel box** — proxy and original are
interchangeable, so there is no "apply the decisions to the big one" step. The
scale to 1080p has to happen anyway; doing it once is less resampling, and
`screen-cut.py` skips the scale filter when the input already matches.

OCR reads the proxies as well — the scan runs at 1600 px wide and the proxy is
wider, so the earlier "scan the originals" advice was wrong and cost a 4K
decode for nothing. `--skip-static` and the per-frame OCR cache
(`--ocr-cache` / `--from-cache`) are the levers on OCR time.

## Measure the picture, per region

`screen-activity.py` counts the fraction of pixels that changed by more than a
noise floor, per sampled frame. Give it **named regions** — without them there
is nothing to fast-forward *with*, because whole-frame activity cannot tell the
human working from an AI streaming text.

```json
"regions": { "main": [0, 0, 0.748, 0.98], "panel": [0.748, 0, 0.252, 0.98] }
```

| what is moving | what the cut does |
|---|---|
| `main` | keep at `keep_speed` |
| only `panel` | run at `speed` |
| nothing | drop |

**Find the divider, do not assume it.** `--probe-motion` reports which
eighth-of-the-frame cells move during otherwise-still stretches; a side panel
shows up as one column on every recording. Confirm it by taking the strongest
long vertical edge in the right half of a frame at several timestamps and using
the mode — on this footage that gave `x = 0.748` on all five recordings that had
the Edge panel open, while a single timestamp gave three different answers
because a dialog was on screen.

**Ignore the spinners.** A thinking animation, a caret, a clock or the
recorder's own timer keeps a dead screen above any threshold forever. `ignore`
rectangles are frame **fractions** so they survive a resolution change. Phone
screen recordings want `0,0,1,0.04` for the status bar.

## Blur before you cut, and find it by reading, not scrubbing

Run `scan-pii.py` on **every** source before planning the edit. It samples,
OCRs, and matches the *shape* of a secret — Luhn-valid 13–19 digits, three
digits next to "CVV", `+380` and nine more, `UA` and 27. `--emit` prints `blur`
entries ready to paste into the manifest.

Three things that decide whether it works:

- **Luhn is what makes the card rule usable.** An order number like
  `#1806413786` is ten digits in a row; without the checksum every confirmation
  page is a false positive.
- **Match the mask's shape, not its glyph.** The bank draws a bullet, one OCR
  model returns `----`, another `****`. Requiring a full 27-character IBAN found
  *nothing*, because the field is always drawn part-masked.
- **`--skip-static` is what makes it finish.** OCR is the entire cost and a
  screencast holds still. A frame close to the last one *read* is skipped and
  the previous reading is re-stamped at the current time, so windows stay
  accurate while the call count drops with the stillness, not the length.

**Redaction is TRACKED, not time-windowed.** A rect anchored to a time window
is the wrong primitive — the page scrolls, the field moves, the rect does not,
and the blur lands on the wrong rows. Every leak this pipeline chased before
tracking existed came from that mismatch. Instead:

```powershell
python scripts/track-blur.py --src <proxy> --pii <pii.json> --outdir <trackdir> --manifest <screen.json>
```

captures each secret's own pixels as a template and finds them per frame with
NCC (`cv2.matchTemplate`) — the standard "tracked redaction" of video editors,
and screen recordings are its easy case since a browser renders text
pixel-identically. Point the source's `track` key at the outdir;
`screen-cut.py` blurs the frame once and shows it through the tracked mask, so
box count adds nothing to per-frame cost. Blur as little as possible falls out
for free: the mask is exactly the matched pixels plus 6 px.

Three hard-won constants live in the script: match at three SCALES (an app
draws the same number at list/detail/form sizes and NCC only matches its own);
refuse templates under 48 px wide or 12 σ contrast (a 39×11 patch cleared 0.90
against a face); and write the mask stream LONGER than the source (a short
mask stalls `alphamerge` exactly like the looped-PNG alpha trap).

Hand `blur` rects remain for what OCR cannot read at all — stylised card
faces — and run in source time, upstream of the trim, same as ever.

- **The country code is optional.** Requiring `+38` let a panel summary reading
  `(Київ, відділення 57, 0XXXXXXXXX, <recipient> …)` straight through —
  city, branch, phone and full name, in the national `0XX` form.

**It is a net, not a clearance.** OCR misses rotated, low-contrast and
partly-scrolled text, and cannot know that a first name plus a delivery branch
identifies a real person. Look at the `--sheet` frames before you encode, and
**ask the person whose footage it is** what to hide — the answer is routinely
wider than the request. Asked here for "phone number, card and CVV", the footage
also held recipients' names, phones and home addresses, plus a bank balance; the
answer was "everything, but keep the city name".

Then **scan the render itself** — it is short and 1080p, so it costs minutes,
and it checks the thing you are about to publish:

```powershell
python scripts/scan-pii.py --src projects/<id>/outputs/<id>.mp4 --report --fps 0.25
```

Anything that comes back is a rect that did not land. Fix the manifest and
re-render; never trim the film to hide it.

Keep hand-written rects in a `blur_extra` list on the source, so regenerating
the scanned ones cannot silently drop the rects that exist *because* the OCR
missed something.

A handheld shot of a screen needs **one generous rect per field**, not the
per-frame boxes the scanner reports — the camera moves, so union them.

## When the secrets are the film, redact the film instead

Source-time tracking is the default and stays right when secrets are
occasional. Check before you commit to it: **how much of the finished film has
a secret on screen?** Under about a fifth, track the sources. Over it, the
mapping from source time back to film time — through the cut, the speed change
and the pad — becomes the thing you spend the day debugging. On
`books-giveaway` it was 31 % (148 s of 480 s), 133 of 160 gate hits were inside
the 3x stretches, and one gate round cost 2 h 16 m.

The film-time route removes the mapping rather than debugging it:

```powershell
python scripts/screen-cut.py  --manifest projects/<id>/screen.json --target 8:00 --no-redact
python scripts/film-redact.py --project <id> --states --detect -j 8
python scripts/redaction-review.py --manifest projects/<id>/screen.json --states --html
python scripts/film-redact.py --project <id> --blur
python scripts/film-redact.py --project <id> --gate
```

Four things to know before you run it:

- **The unit of work is the screen state.** 14,400 frames, ~500 real changes;
  `--states` writes one representative frame per state (1,330 here) and
  detection runs on those. Ask ffmpeg for a frame by TIME, never by index —
  `select`'s counter restarts when the decoder re-initialises.
- **Price it honestly: 2.7 s per rep frame.** One process does 0.37 rep/s and
  eight do 0.44 — the OCR is memory-bound, so `-j` buys 19 %, not 8x. Quote
  ~50 minutes for a 1,330-state film and do not promise six.
- **Set the OCR threads in the constructor.** onnxruntime ignores
  `OMP_NUM_THREADS` and friends; unbounded, eight workers oversubscribe the
  cores and run *slower than one process*. That is `--threads` (KI-024).
- **Launch it detached and let it checkpoint.** It resumes every 25 reps, so
  an interruption costs a minute, not the run — and it must not be launched
  under anything that will time out and kill it (KI-025).

**What the detector cannot read still needs a rect.** Film time gets its own
escape hatch, `film_blur` on the manifest, in the film's own seconds:

```json
"film_blur": [
  {"rect": [0.41, 0.22, 0.18, 0.05], "when": [131.0, 148.5],
   "why": "card face drawn as artwork; no text for OCR to find"}
]
```

`mask_runs()` unions those into every state their window overlaps, a review
decision never clears one, and the approval fingerprint covers the list — so
adding a rect un-approves the look instead of slipping in behind it. The gate
cannot help here: it asks whether *detected* boxes are blurred, and nothing
detected these (KI-026).

The review is not optional here either: `redaction-review.py --states` shows
before/after from the film's own frames, once per kind of secret, and writes
the `decisions.json` that `--blur` honours.

## Hold, or the film strobes

Thresholding raw activity gave **1094 segments** and a film flickering between
1x and 6x several times a second. `hold` dilates each region's boolean track
forward and back ("it moved within the last second, so it is still moving");
`panel_hold` is longer because streaming text is burstier than a mouse. Same
footage: **579 segments**.

Short runs are then absorbed into the **longer neighbour**, not promoted back to
keep — half a second of panel flicker inside a two-minute wait belongs to the
wait, and promoting it put a hitch in the middle of every fast-forward. `air` is
handed back at **1x**; handing it back sped is a lurch either side of every join.

## Price the length before you encode

`--list` shows where the runtime goes, and it is usually not where you'd guess:
on this footage only 3:17 of 47 minutes was truly dead, because the spinner means
something is nearly always moving. Raising `speed` 6x→12x moved the film 25:27 →
23:36 and no further, because **21:45 was held at 1x**. That is what
`keep_speed` is for.

`--target M:SS` solves for both speeds together, keeping the manifest's
panel:work ratio. `hold_1x` windows are forced to 1x and do **not** scale — use
them for the things the film exists to show, because no motion metric knows
which page matters. The solver reports the floor they impose.

`--sweep` prices a grid; `--sheet` writes a frame per kept segment and per blur
rect. Both encode nothing.

## Render with no audio

`-an`, deliberately. The sources are silent and the voice-over is recorded
against the finished cut; muxing a silent track invites a later pass to mix onto
it and produce nothing. The render asserts its own duration against the plan
before it reports success.
