# KitCut technical reference

The human-facing overview is the root `README.md`. This file is the full
reference: every command, setting and trap, one section per pipeline.
It was the README until 2026-09-03 and is still what CLAUDE.md, the skills
and `check-script.py` mean by "the reference".

---

# video-captions

Add word-synced burned-in captions to a video — a "real time transcript" where
the currently-spoken word is highlighted — from a YouTube URL or a local file.

Runs entirely locally: `faster-whisper` for word-level timestamps, a generated
ASS subtitle file for styling, and NVENC to burn it in. No API keys, nothing
uploaded.

```powershell
python scripts/run-captions.py --url "<URL>" --style config/presets/red-card.json
```

Roughly **0.5–0.9x the video duration** end to end on a laptop RTX 3050 Ti.
A 16-minute video takes about 9 minutes.

## What it does

```
download → audio → transcribe ∥ overlays → ass → verify → render
```

- **Stages are resumable.** Each is skipped when its artifact exists; `--force
  <stage>` reruns it and everything after; `--stop-after <stage>` stops early.
- **Transcription and overlay detection run in parallel.** They're independent;
  overlay detection drops to CPU decode so the ASR model keeps the GPU.
- **Sync is proven, not assumed.** Before rendering, the caption layer is drawn
  onto black, sampled at word midpoints, and each probe asserts the word in the
  highlight colour is the one that should be active. The pipeline refuses to
  render if this fails.
- **The output is checked too** — duration match, bitrate sanity, faststart box
  order — and a manifest with tool versions and input hashes is written beside it.

## Styling

Every visual choice lives in a preset under `config/presets/`. Never edit code
to change how captions look.

| Key | Effect |
|---|---|
| `font.family` / `font.file` / `font.fontsdir` | typeface |
| `font.cap_height_px` | **preferred way to size text** — nominal size is derived |
| `font.bold` | 1 requests weight 700 |
| `text.uppercase`, `apostrophe`, `outline_px`, `shadow_px` | text treatment |
| `card.enabled`, `colour`, `alpha`, `corner_radius_px`, `pad_*_px` | the background card |
| `card.rule.colour` / `px` / `side` | a solid strip the full width of the card, above or below it — a broadcast lower third's accent bar |
| `layout.anchor_x`, `bottom_margin_px`, `max_lines`, `max_line_width_px` | placement |
| `states.base` / `active` / `spoken` | `spoken == base` → spotlight; `spoken == active` → progressive karaoke fill |
| `pop.*` | scale animation on the active word |
| `grouping.*`, `timing.*` | words per card, breaks, lead-in/hold, fades |
| `overlays.colour` | colour of the *source's own* lower-third graphics, to dodge them |
| `render.*` | encoder, preset, cq, bitrate caps |

Presets are authored on a 1920x1080 canvas and every pixel value is scaled
automatically to the actual video, so 720p / 1440p / vertical all work.

`card.rule` exists because an accent bar is what makes a broadcast lower third
read as itself — Bloomberg Tech's banner is a white slab with a 14 px mint strip
under it, and the same slab without the strip is just a white box.
`layout.bottom_margin_px` stays the distance to the bottom of the **whole**
graphic, rule included, so adding one does not silently lift every caption.

Eight presets ship. Four are house styles: `red-card` (solid red info-card,
yellow spotlight), `red-card-vertical` (the same re-authored for 9:16, used by
the shorts pipeline), `dark-card` (near-black slab at 12% transparency,
sentence case, mint spotlight) and `dark-card-uk` (the same, widened for
Cyrillic). Four are **channel styles**, each measured off
that channel's own frames rather than invented — `eu-navy` (Europeiska Pravda:
EU-flag blue, star-yellow spotlight), `bloomberg-tech` and
`bloomberg-tech-vertical` (white banner, square corners, mint rule, amber
spotlight), and `lennys-podcast-vertical` (55%-opacity black box, white
sentence case, campfire spotlight). Every channel preset carries a `_measured`
block naming the frames it came from and the numbers read off them; that block
is the difference between a style and a guess. See **Deriving a channel's
style** in the `video-shorts` skill for the procedure.

`red-card` and `dark-card` are the two ends of a real choice, and it is not a
taste one. `red-card` was measured off a news channel: a saturated slab in
uppercase, designed to be read on a phone at arm's length over a talking head.
Put it on a **screen recording** and it competes with the product it is pointing
at — the frame is already busy, mostly white, and full of the UI the viewer is
supposed to be looking at. `dark-card` is the screencast answer: the slab
recedes, the type is sentence case rather than uppercase (word shape is what
makes a line readable at a glance, and uppercase throws it away), the lines are
narrower, and the spotlight is the accent mint `#13BA82` — the same token
`config/cards/brands/mint.json` and the lower third use, so captions, a
name label and an end card on one film read as one channel rather than three.

Its `_geometry` block records what the placement was fitted around: a webcam
bubble in the bottom-left corner and the Windows taskbar along the bottom.
`bottom_margin_px` and `max_line_width_px` are the two numbers that keep the
card clear of both, and widening the line past ~1150 makes it collide with the
bubble.

**No NVIDIA card?** `run-captions.py --encoder libx264` (and the same flag on
`cut-clips.py`) renders on CPU. The flag exists because the render blocks are
authored for NVENC, whose `-rc vbr -cq -spatial-aq` flags kill libx264 on
sight — `_overlay.cpu_encoder_args()` translates instead: `cq` becomes `crf`,
the `p1–p7` ladder becomes x264's named presets, and the NVENC-only quality
knobs are dropped rather than mis-scaled. Captions and shorts are the only
pipelines with a CPU path; screen-cut and the multicam renders need NVENC.

### Grouping is a tuned pair, and it fails typographically

`grouping.max_words` and `layout.max_line_width_px` are one setting in two
numbers: a group one word too wide for its line wraps, and the wrap orphans that
word onto a line of its own. `selfcheck` cannot see it — nothing is out of sync,
off-canvas or overlapping — so it ships. "the models are going / **to**" did.

The builder prices it, so sweep instead of guessing:

```
cards wrapping to >1 line 1/25 (4%) | of those, 0 orphan a single word onto its own line
```

Measured on the two channel presets, the shipped-then-fixed settings were in
both cases the *worst* cell of their sweep:

| preset | was | wrapped / orphans | now | wrapped / orphans |
|---|---|---|---|---|
| `lennys-podcast-vertical` (sentence case) | 5 words × 400 | 67% / 7 | **4 × 470** | 4% / 0 |
| `bloomberg-tech-vertical` (uppercase) | 4 words × 500 | 35% / 10 | **3 × 560** | 4% / 2 |

**Uppercase runs ~15% wider**, which is why the same frame takes 4 words in
sentence case and 3 in caps. And `max_line_width_px` is clamped to
`0.94 × frame − 2 × pad_x`, so past that point widening it measures identically
and the only lever left is `max_words`.

Two smaller things worth copying rather than rediscovering: `strip_trailing`
should match what the channel actually does — Lenny's keep every comma and full
stop, so the `","` inherited from `red-card` was stripping punctuation they
keep — and `text.capitalize_i` fixes the English pronoun, because Whisper's
casing is per-segment and inconsistent (312 correct "I" against 78 lowercase
from one speaker in one recording; one of them landed in a caption card).

### Highlighting the main points, not just the current word

The spotlight moves word by word and says *"this is being said now"*. It cannot
say *"this is the sentence that matters"*. `states.emphasis` is the second axis:

```powershell
python scripts/run-captions.py --input <film> --style <preset> \
    --emphasis-file projects/<id>/emphasis.txt
```

`emphasis.txt` is one phrase per line (JSON list or `{"phrases": […]}` also
work); the preset supplies the colour. Every word a phrase covers wears the
emphasis colour **for the whole life of its card** — before and after the
spotlight passes over it — so a viewer skimming a nine-minute briefing can see
where the decisions are without waiting for the highlight to arrive.

Two rules make it survive:

- **A phrase that matches nothing is a failure, not a no-op.** Borrowed from
  `apply_corrections()` for the same reason: a highlight list that quietly stops
  applying after a re-transcription is worse than no highlights, because nobody
  looks again. Quote what the transcript says *after* the manifest's
  `corrections`.
- **Emphasis and the spotlight must not be the same colour.** On
  `dark-card-uk.json` the spotlight is mint and emphasis is amber; if emphasis
  reused the mint, "this is the point" and "this is the current word" would be
  one signal and neither would read. Pick emphasis against the *card*, not
  against the base text.

One phrase every ~40 s of finished film is a good density — dense enough to
carry a skim, sparse enough that the colour still means something.

Cyrillic needed its own preset for the reason the table above predicts:
`dark-card-uk.json` widens `max_line_width_px` to **1296** and changes nothing
else. Ukrainian words are materially longer than the English its parent style
was measured on, and at 1080 the same six-word groups wrapped 37 of 219 cards
and orphaned 33. Widening the line beat carrying fewer words: 6 × 1296
gives 219 cards and 1 orphan, where 4 × 1080 also reaches ~0 orphans but at 304
cards — a card change every 1.5 s instead of every 2.1 s, and on a static
talking head the card is the only thing moving.

### Deriving a style from a reference

Measure, don't eyeball. Pull a few seconds of the reference, extract frames, and
take cap height / colours / radius / margins off a **native-resolution** frame.
For brand colours, mask a channel thumbnail to saturated pixels, quantise, and
read the dominant buckets.

## Cutting shorts out of a long video

Once a video has a `transcripts/<id>.words.json`, episodes can be pulled out of
it by quoting what is said rather than by hunting for timecodes.

```powershell
# skim the whole thing as [mm:ss] lines, then find where a line lands
python scripts/transcript-outline.py transcripts/<id>.words.json --outline
python scripts/transcript-outline.py transcripts/<id>.words.json --find "so anyway"

# resolve every boundary and print the plan without encoding anything
python scripts/cut-clips.py --manifest projects/<id>/clips.json --list
python scripts/cut-clips.py --manifest projects/<id>/clips.json
```

A manifest names the source, the transcript, and the clips:

```json
{
  "source": "outputs/<id>-captioned-1080p60.mp4",
  "words": "transcripts/<id>.words.json",
  "outdir": "projects/<id>/outputs/shorts",
  "prefix": "<id>",
  "pad": { "head": 0.15, "tail": 0.35 },
  "clips": [
    { "id": "01-something", "title": "…",
      "start_text": "ну що, тільки що кур'єр",
      "end_before_text": "наступне, друге" }
  ]
}
```

- **Boundaries are phrases.** `start_text` / `end_text` / `end_before_text` are
  matched against the transcript ignoring case, punctuation and spacing, so a
  phrase pasted out of the outline and one typed normally both hit. Plain
  `start` / `end` / `duration` in seconds still work.
- **Pads never eat a neighbour.** The pad is a guess about silence; when the
  transcript says a word is still being spoken inside it, the boundary meets it
  halfway instead, so a clip does not open on the tail of the previous sentence.
- **Cuts are frame-accurate**, because the source is re-encoded. `--copy`
  stream-copies instead — instant, but the cut snaps to a keyframe.
- Existing outputs are skipped, so editing one entry and re-running rebuilds only
  that entry; `--only <ids>` and `--force` narrow it further. Each clip gets a
  `.json` sidecar recording the exact source, boundaries and encoder settings.
- Cutting is roughly **3x realtime** on a laptop RTX 3050 Ti — five ~75 s clips
  take about two minutes.

## Vertical 9:16

Cropping the captioned master does not work: its caption cards run to ~1180 px
on a 1920 canvas while a 9:16 window is 607 px, so the crop slices the
subtitles. Cut from the **clean source** and re-render captions after the crop —
then they are sized for the frame the viewer actually sees.

```powershell
# 1. face-track the crop window
python scripts/auto-reframe.py --manifest projects/<id>/clips-vertical.json
# 2. cut: crop -> scale -> captions -> badge, one encode
python scripts/cut-clips.py --manifest projects/<id>/clips-vertical.json
```

A vertical manifest adds three keys to the ordinary one:

```json
"vertical": { "width": 1080, "height": 1920 },
"captions": { "style": "config/presets/red-card-vertical.json", "samples": 24 },
"handle":   { "text": "@name", "preset": "config/handles/vertical.json" }
```

- **Every shot is decided separately.** `auto-reframe.py` splits each clip at its
  shot boundaries and picks a treatment per shot: **static** where the face
  barely moves, **pan** where it does, and **pad** — don't crop at all, show the
  whole frame letterboxed over a blurred fill — where there is no face. Keys go
  to a sidecar that `cut-clips.py` turns into a crop whose `x` is an expression
  in `t`.
- **That default was measured, not guessed.** `--mode compare` scores each
  strategy on how far the subject sits from the crop centre and how much the
  window moves. Over these five episodes:

  | | off-centre mean | p95 | near-edge | motion |
  |---|---|---|---|---|
  | `pan` (track everything) | 27.9 px | 77 px | 0.5% | 10.5 px/s |
  | `shot` (static per shot) | 32.0 px | 102 px | 1.7% | **4.0 px/s** |
  | `hybrid` (default) | **24.8 px** | **73 px** | **0.5%** | 8.4 px/s |

  `shot` alone is steadier but loses the subject; it wins outright where she
  sits still and fails where she walks. `hybrid` beat both on every clip.
- **`pad` only ever means "no face found here".** Usually that is b-roll, but a
  shot where the subject looks away reads the same. Review them.
- **Precedence:** per-clip `crop_keys` overrides the sidecar. `crop_x` and
  `crop_pad` do NOT — a sidecar entry wins over both, and `cut-clips.py` prints
  a note when a clip sets one anyway. To override a sidecar decision, edit the
  sidecar: clear its `pad` and add `keys` across that span.
- **Captions get a slice, not a copy.** The ASS builder's `--range` /
  `--time-offset` already exist, so each clip is a view onto the one transcript
  and no sliced word files are written. Sync is still proven per clip before
  rendering.
- **Both presets need a vertical variant**, and for opposite reasons: captions
  scale by the HEIGHT ratio, so vertical makes text ×1.78 bigger in a narrower
  frame; the badge scales by the WIDTH ratio, so a landscape preset comes out
  tiny.
- **A crop cannot save wide burned-in graphics** — no 607 px window contains a
  full-width lower-third. That is what `pad` is for: those shots are letterboxed
  whole instead of sliced. It is switched by `enable` on an overlay rather than
  by cutting and concatenating segments, so it still costs one encode. Captions
  and the badge composite on top, so they are never letterboxed with the shot.

### A short out of a screen recording: `crop_rect`, `place` and `mask`

Face-tracking has nothing to track in a screencast, and the 9:16 window it would
crop to is 607 px of a 1280 px browser — unreadable. So a clip may instead name
the **rectangle to keep** on the source, which is fitted to the canvas width and
placed on a background. `crop_rect` and `place` sit on the manifest (one framing
usually serves the batch) and a clip overrides either.

```json
"crop_rect": [215, 72, 900, 535],
"place": {
  "y": 544,
  "background": "#0B0D10",
  "mask": [ { "rect": [12, 488, 190, 186], "mode": "delogo" } ]
}
```

- **`crop_rect` is `[x, y, w, h]` on the source**, and it takes precedence over
  `crop_box`, `crop_keys` and the reframe sidecar (the sidecar is not even
  loaded when the manifest sets a rect). `place.y` is the picture's top on the
  output canvas; omit it and it centres. `place.background` is `blur` (a blurred
  blow-up of the frame, as in `pad`) or any colour — **a white browser page
  blurs to a white void, so a screencast wants a flat dark ground**, which also
  gives the picture an edge and leaves the lower third free for captions.
- **`mask` removes things before anything else looks at them**, which is what
  makes the rect free to be chosen for readability. Measured on real frames
  here, only `delogo` — the default — actually disappears: it interpolates the
  rectangle from its own border pixels, so over a flat page background the patch
  *is* that background. `blur` turned a dark webcam into a grey smudge, and
  copying a neighbouring strip duplicated the buttons beside it. Both are kept
  for regions delogo cannot reach.
- **This is what a re-voiced screencast needs.** Replacing the sound makes a
  burned-in caption card contradict the new voice and a webcam PiP's lips
  disagree with it. The caption card and the taskbar sit below the rect, so the
  crop drops them; the webcam shares a band with the buttons the demo is about,
  so masking it is the only way to keep both.
- **Verify it on the render, with a detector, not an eyeball.** A stray talking
  head in a re-voiced short is the one failure nobody forgives. YuNet found the
  webcam in 30/30 sampled source frames and 0/80 sampled frames across the two
  finished shorts — and the source number is the half that makes the zero mean
  anything.
- **`place.pan`** moves the window over time as `[[t, [x, y]], ...]`, linear
  between keys and held flat past both ends. The window keeps ONE size: `crop`
  evaluates `w`/`h` once and only `x`/`y` per frame, so a window that changes
  size cannot be done in this pass at all.
- **`--list` prices the framing** — rect, output size, placement, zoom factor,
  pan keys and mask count — without encoding anything.

## Where the caption card goes

**A caption position is only safe relative to a FRAMING.** `bottom_margin_px` is
a distance from the frame bottom, not a promise about what is there: 602 px
lands on the chest of a loose podcast two-shot and across the mouth of a tight
news close-up. So the moment a crop changes, the placement is stale — and on
`g-YDNJcyuck` the crop changed twice to clear a broadcast lower third, magnified
the face, and put the card straight over two speakers' mouths. It passed every
check that existed: frame-accurate cut, right duration, 24/24 caption-sync
probes, hook inside 3 s, settled opening frame. Nothing was looking at the video
and the captions in the same coordinate system.

**`cut-clips.py` now runs this itself** after rendering any vertical captioned
manifest — the guard being a separate script nobody was obliged to run is how
the defect shipped. A failing check fails the run (the renders stay on disk for
inspection); `--no-caption-space-check` opts out, a machine without the YuNet
model under `models/face/` gets a loud skip, and dubbed cuts are skipped because
their captions are timed from dub words this checker does not read. Standalone
runs are for re-checking without an encode:

```powershell
python scripts/check-caption-space.py --manifest projects/<id>/clips-vertical.json
python scripts/check-caption-space.py --manifest ... --list   # every frame, exit 0
```

It reads the **render** — deriving where the card will land from the manifest
means re-deriving the crop, which is where two separate bugs already lived
(`docs/retro-books-giveaway.md`). Per caption group it takes the card rectangle
from `build-captions-ass.py --debug-out` and the face box and mouth landmarks
from YuNet, both in output pixels, and intersects them. FAIL is the mouth
covered or ≥15% of the face; a reviewed exception goes in the clip's
`caption_space_ok`, like `open_ok` and `checked_utc` elsewhere. The checker
resolves the style through the same per-clip override path the render uses
(`clip_style`) — its first version rebuilt geometry from the bare preset and
reported +319 px of clearance for a card position that was not on the video,
which is a guard passing for the wrong reason. To regression-prove it after
changing it: copy a manifest whose renders exist, force the known-bad margin on
one clip via a per-clip `captions` override, and run the checker against the
existing renders — same footage, same faces, so it must reproduce the shipped
failure (MOUTH covered, exit 1) without an encode. It did.

Three things it taught that no amount of looking would have:

- **Its confidence floor must be LOWER than a detector's, not equal.** A face
  the card is sitting on is a partly occluded face, so the frames the check
  exists to catch are the ones the detector is least sure about. The worst frame
  scored **0.67** and was silently skipped at `shot-detect.py`'s 0.7, while every
  well-behaved frame scored 0.72–0.80. A check that fails open on its own worst
  case is worse than none, so it also warns when a third of sampled frames have
  no face at all.
- **Test a band, not the landmark.** YuNet's mouth point is the midpoint of the
  two corners; the lower lip and chin run ~10% of the face height below it. The
  shipped frame had the landmark at y 1163 and the card top at y 1173 — a 10 px
  "miss" that a viewer reads as the mouth being gone.
- **Sometimes there is no safe placement, and that is the finding.** On a tight
  close-up the card must clear the face box (bottom y≈1345) while staying above
  the Shorts UI (y≈1540): a 174 px two-line card does not fit between them.
  Above the head is then the only option — and where the subject fills the frame
  top to bottom, even that fails and the *framing* has to change. That is what
  `crop_pad` letterboxing is for: the full source frame over a blurred fill
  keeps the channel's own graphics intact and unsliced and opens clear space
  under the band for the card.

Two clips in one manifest can therefore need different placements. A clip may
carry its own `captions` block overriding `bottom_margin_px`, `max_lines` or
`max_line_width_px`; cut-clips patches a copy of the preset into `temp/` and
says so. Only `layout` keys are overridable — colour, font and grouping are what
make a preset a channel's style, and a clip that wants those wants its own
preset.

## Where a short opens

**The hook comes first and the frame second, and getting that backwards is the
expensive mistake.** A short has about two seconds to earn the watch. On
`dHYrpun-XTs` a bad opening frame was fixed by moving the start back one
sentence — which bought a closed mouth at the price of seven seconds of
back-reference to a calculation made *before the clip began*. Frame perfect,
short ruined, re-cut a third time. Find the first concrete self-contained claim,
cut there, and only then place the exact frame within the couple of frames
around that word. If a better frame costs the hook, keep the hook.

**Check the render's caption, not only its picture.** A head that lands inside
the previous word appears in the first caption card as a word the viewer never
properly hears — that is how a cut 0.06 s inside `кажуть,` was caught, after the
picture alone had looked fine. `check-openings.py` now flags any boundary that
falls inside a word's transcript span unconditionally — that one is mechanical,
and no `open_ok` excuses it. Word boundaries are in the transcript, so land in
the gap *between* them (`кажуть,` ends 371.56, `людина` starts 371.58 → start at
371.57). A numeric `"start"` is the right tool: `resolve()` skips the pad block
when there is no `start_text` anchor, so the value lands frame-exact.

A clip that starts mid-word — mouth half open, eyes down, a hand frozen
mid-gesture — reads as a botched cut, and it is the first thing anyone sees.
Nothing else here catches it: the caption-sync probes and the duration assert
both pass, because nothing about such a clip is out of sync or the wrong length.
It is only ugly.

```powershell
python scripts/check-openings.py --manifest projects/<id>/clips-vertical.json
python scripts/check-openings.py --manifest ... --sheet     # then LOOK at the png
```

It measures **lead-in silence** — the gap between the previous word's end and
the cut — and flags anything under 0.20 s. Watch for the halving: `resolve()`
pads meet speech halfway, so a 0.24 s gap in the transcript becomes ~0.12 s of
actual lead-in.

**The number decides less than you would like.** A mouth stays open across a
short gap, so silence is not evidence the picture is settled; and some speakers
never stop. On `dHYrpun-XTs` the largest pause in the 37 seconds around one clip
was 0.28 s, so no boundary in reach was clean and the start had to be chosen by
picture. `--sheet` contact-sheets every frame inside the nearby pauses, plus the
first eight frames of the render as shipped.

That is how the clip was fixed. Opening on the phrase that carried the idea put
frame 0 mid-word; every frame of the 360.38–360.62 gap was mouth-open, and every
frame of an earlier 0.28 s gap was mouth-closed and facing camera. The start
moved back one sentence **for the picture, not for the words** — which is not a
decision the phrase-matching boundary logic can ever make for you.

A short lead-in that has been looked at and accepted is recorded on the clip as
`"open_ok": "<why>"`, so the check keeps its teeth instead of being tuned away —
the same bargain `checked_utc` strikes with the project doctor.

**A mouth-openness detector was tried and rejected**; do not re-attempt it
blind. YuNet's five landmarks give mouth *corners* but no lip contour, so
openness has to come from how dark the mouth region is. Measured against eight
frames already judged by eye, that score separated them cleanly and *backwards*
— closed mouths read darker (0.33–0.47) than open ones (0.11–0.18), because the
speaker was looking down in the open frames and the score was reading head pose
and shadow rather than lips. Eight frames from one shot, separating for the
wrong reason, is the same shape of mistake as the redaction tracker that scored
27% on frames it cut its own templates from. Doing it properly needs a
lip-contour model and a labelled set across several films.

## The handle badge

A camera glyph above an `@handle`, hopping between anchor points on a timer and
alternating between a flat glyph and a gradient one — a moving mark is harder to
crop out or paint over than a fixed corner watermark.

```powershell
# eyeball the style without encoding anything
python scripts/handle-overlay.py --badges-only --handle "@name"

# burn it into an existing file
python scripts/handle-overlay.py --video in.mp4 --handle "@name"
```

Better, put it in the clip manifest and let `cut-clips.py` apply it **while
cutting** — one encode instead of two, so the clips are not re-compressed:

```json
"handle": { "text": "@name", "preset": "config/handles/default.json" }
```

`--handle` / `--handle-preset` / `--no-handle` override the manifest per run.

The split is deliberate: the badge is drawn once per colour variant into a PNG
by Pillow — where fonts, gradients and outlines are easy — and the animation is
an ffmpeg `overlay` whose `x`, `y` and `enable` are expressions in `t`. So the
motion costs one filter pass and no per-frame Python. ASS could not have done
it: libass has no gradients.

Styling lives in `config/handles/*.json`, authored on a 1920x1080 canvas and
scaled to the real video like the caption presets.

| Key | Effect |
|---|---|
| `font.cap_height_px` / `tracking_px` / `uppercase` | the handle text |
| `text.outline_px` / `outline_colour` | dark edge so white text survives a bright frame |
| `icon.size_px` / `stroke_px` / `corner_radius_px` / `gap_px` | the glyph |
| `icon.gradient` / `gradient_angle_deg` | colours of the gradient variant |
| `motion.positions` | badge **centre** points, visited in order |
| `motion.move_every_s` / `colour_every_s` | the two independent cycles |
| `motion.colour_cycle` | which variants alternate (`flat`, `gradient`) |
| `motion.opacity` / `start_index` | |

Keep `motion.positions` clear of the caption card at the bottom of the frame.

The glyph is drawn from primitives — a rounded square, a lens circle, a
viewfinder dot — not lifted from a brand asset. It reads as a camera mark; treat
using it as attribution, and check the platform's brand guidelines if that
matters to you.

## Dubbing into another language

`dub-clips.py` translates a clip and speaks it back into the original's rhythm.
The goal is not a fluent translation on its own — it is that sound starts when
the mouth opens and stops when it closes. Read a translation straight over the
top and it drifts within seconds; what the eye catches is cadence, not phonemes.

```powershell
# translate, speak and fit -- writes <outdir>/<name>.en.wav + .en.words.json
python scripts/dub-clips.py --manifest projects/<id>/clips-vertical.json --only <clip-id>

# render the dubbed cut; captions come from the dub's own word timings
python scripts/cut-clips.py --manifest projects/<id>/clips-vertical.json `
    --only <clip-id> --dub projects/<id>/outputs/dub
```

The output is named `…-<tag>.mp4` (`en` by default), so the original is never
overwritten.

Two voices are available. edge-tts needs no key and has the wider speed range;
ElevenLabs sounds better and needs `ELEVENLABS_API_KEY` in `.env`. Each backend
gets its own default `--tag` (`en` for edge, `en-el` for ElevenLabs) so the two
coexist without overwriting each other:

```powershell
python scripts/dub-clips.py --manifest ... --only <id> --tts elevenlabs
python scripts/cut-clips.py --manifest ... --only <id> --dub projects/<id>/outputs/dub --dub-tag en-el
```

Pointing a second backend at a tag that already holds another one's dub is
refused rather than silently skipped or overwritten. Voice names are validated
before anything is rendered, against `config/elevenlabs-voices.json` — which is
also where the model comes from (`--el-model` overrides it).

Measured against each other through the identical pipeline they tie on timing
(sync 95.0% vs 93.9%, mean slot error 0.15s vs 0.18s), so choose on how the
voice sounds. The one difference clearly owned by the backend: ElevenLabs caps
`speed` at 0.7-1.2, so 14 of 26 lines sit pinned against that limit where edge
pinned 5 — it just still fits.

### How it works

1. **Segment.** Split the clip at the pauses the speaker actually took, then
   recursively split anything still longer than `--max-dur` at its best internal
   gap. Punctuation is a hint, not the rule: on this transcript Whisper stops
   punctuating entirely near the end, and a punctuation-driven split produced a
   single 25-second "unit". Gap-driven splitting gave 26 units averaging 2.9s.
2. **Translate.** Every slot goes to the translator in one request, with the
   whole passage as context and a per-slot time budget, plus a shorter `tight`
   fallback. Default engine is the Claude Code CLI, which needs no API key.
3. **Fit.** Speak the line, measure it, then re-render at a computed speaking
   *rate* so it lands in its slot. `rate` is prosodic — the voice re-times
   phonemes the way a person would — so it beats stretching the waveform.
   Duration tracks `1/(1+rate)` closely enough to aim straight at a target.
   rubberband is the last resort, and stays under ~18%.
4. **Retune.** How long a sentence takes to say is a guess until you say it.
   Slots that came out wrong go back to the translator *with the measurements*
   and only those get re-rendered.
5. **Place.** Each unit is laid at the exact time the original phrase began.

### Does it work

`sync` is the share of the clip where dub and original agree about whether
anyone is talking. It drops when the dub speaks over a pause, and when it falls
silent under a moving mouth. Measured on `01-silver-button` (78s, 26 units):

| | first pass | after retune |
|---|---|---|
| sync | 85.8% | **94.4%** |
| slot error, mean | 0.42s | **0.17s** |
| slots overrunning their gap | 0 | 0 |
| slots stuck at the slow-down floor | 14 | **2** |

That last row is the one that mattered. The first prompt gave the word budget as
a ceiling, so every line came in short and the voice had to drawl at `-18%` to
cover the gap. Rewording it as a target to *hit*, plus the retune round, fixed
it. Both numbers came from measuring, not from listening and guessing.

### Knobs

| flag | default | |
|---|---|---|
| `--max-dur` | `4.0` | longer slots translate better and sync worse |
| `--min-dur` | `0.9` | shorter than this and a slot sounds clipped |
| `--words-per-sec` | `3.2` | the per-slot word budget handed to the translator |
| `--tune-rounds` | `1` | measure-then-rewrite passes |
| `--engine` | `claude` | translation: or `openai` (needs a key), or `manual` |
| `--model` | — | model override for the translation engine |
| `--tts` | `edge` | or `elevenlabs` |
| `--voice` | `ava` / `jessica` | default follows `--tts`; `dub-tts.py --list-voices` prints both sets |
| `--el-model` | from config | ElevenLabs model id |
| `--tag` | `en` / `en-el` | names this run's artifacts; default follows `--tts` |
| `--outdir` | `outputs/dub` | where the artifacts land |
| `--plan-only` | — | segment and print, spend nothing |
| `--retranslate` | — | throw the cached text away and ask again |
| `--force` | — | re-render the audio, keep the cached text |

`--engine manual` takes a hand-written `[{"i":1,"text":"...","tight":"..."}]`
via `--translation`, which is the escape hatch when a line has to be exact. It
covers one clip (pair it with `--only`), and the retune round leaves it alone
rather than rewriting your file.

A cached translation records a fingerprint of the plan and engine it was made
for. Change `--max-dur`, `--min-dur`, `--engine` or the target language and the
reuse is refused instead of mapping old lines onto new slots by index.

### A written voice-over that replaces the sound: `--script`

`build_plan` derives every slot from the *original speaker's* pauses. That is
right for a dub — the mouth on screen is still moving — and wrong when the point
of the exercise is to replace a narration, because the old rhythm is usually the
thing being fixed. `--script` supplies the slots directly, timed against the
**picture**:

```json
[ {"t": 0.4,  "text": "Flattening turns a fillable PDF into a plain one."},
  {"t": 6.0,  "text": "Ninety-seven form fields, merged into the page in seconds.",
               "tight": "Ninety-seven form fields, merged in seconds."} ]
```

```powershell
python scripts/dub-clips.py --manifest projects/<id>/clips-vertical.json --only <clip-id> `
    --script projects/<id>/vo/<clip-id>.json --tts elevenlabs --voice brian `
    --tag vo --outdir projects/<id>/outputs/dub --plan-only
```

`t` is seconds from the start of the clip; a line runs until the next one begins
(less a breath), or to the end of the clip. Everything downstream is unchanged —
rate fitting, placement, loudnorm, the faster-whisper-shaped `.words.json`, and
`cut-clips.py --dub`, which replaces the audio outright and rebuilds the captions
from the voice-over's own timings.

- **`--script` implies `--engine manual`.** There is nothing to translate, and
  the retune round must not quietly rewrite words a human chose — it reports
  which slots overran and changes nothing, which is the signal to edit the
  script. It is for ONE clip, so it refuses unless `--only` narrows to one.
- **Script slots are `free`, and a short line is a pause, not a hole.** The dub
  path draws a short line out to fill its slot, because dead air under a moving
  mouth reads worse than a slightly long line. With nothing lip-syncing, that
  same stretch is just a drawl, so `fit_unit` skips it for script units.
- **`sync` in the report does not apply here.** It measures agreement with the
  original speech, which a voice-over deliberately discards; it read 79% on a
  perfectly good take. The gate for a written voice-over is instead: every line
  reports **`natural`** (no rate change, no `tight` fallback, nothing squeezed),
  no slot overruns the clip, and the spoken words are the written ones.
- **Verify the words by transcribing the voice-over back.** A TTS engine can
  garble a numeral or an abbreviation and the fit report will not notice. Run
  `transcribe-words.py` over the generated wav and diff it against the script —
  it is local, free, and it is the only check that reads what was actually said.
- **Expect to re-time two or three passes.** A neural voice reads faster than a
  words-per-second estimate, so the first pass comes in short everywhere; then
  the tail turns out to have no slack and each fix moves the squeeze along.
  Shorten a line rather than letting ElevenLabs run at its +20% speed cap.

## A screencast out of two recordings

A screen capture and a phone pointed at your face are two clocks and one story.
`sync-tracks.py` lines them up and proves it, `screencast-cut.py` throws away the
dead air and composites the result in a single NVENC pass.

```powershell
# 1. measure the offset -- and look at the frames that prove it
python scripts/sync-tracks.py --manifest projects/<id>/screencast.json --verify

# 2. read the timeline before spending an encode
python scripts/screencast-cut.py --manifest projects/<id>/screencast.json --list

# 3. render
python scripts/screencast-cut.py --manifest projects/<id>/screencast.json
```

### The camera is the master clock, not the screen

The phone is the stream that has the sound, and it is the one that covers the
whole shoot -- recording starts before you begin talking and stops after you
finish, while the screen recorder is started and stopped in the middle. So the
film is laid out in camera time and falls into three acts, decided from the
footage rather than declared:

| act | when | layout |
|---|---|---|
| intro | camera rolling, no screen yet | camera fills the frame |
| core | both rolling | screen, camera as a square |
| outro | camera still rolling, screen stopped | camera fills the frame |

Nothing configures this. Segments are split at the screen-coverage edges and
each one gets the only layout it can have. A shoot where the two happen to start
together simply has no intro act.

### Finding the offset when one track is silent

A screen recorder that captured no audio leaves nothing to cross-correlate
against. Three sources, in increasing order of trust:

- **`creation_time`** — both containers stamp the *start* of capture in UTC, so
  they subtract directly. Whole-second granularity, so it is a seed good to
  about ±1 s, not an answer. Sanity-check the direction: if a stamp were the
  *end* of capture, a long take would have to overlap the clip recorded before
  it, which one camera cannot do.
- **`--correlate`** — the screen changes when keys are pressed and the mic hears
  those keys, so screen change-energy against high-band audio energy should
  spike at the true offset. On a Claude Code session it does not: output streams
  silently and speech moves the audio without touching the screen. The peak's
  z-score against the rest of the search curve is reported and anything under
  `--min-confidence` is **refused**, not quietly used. On this shoot it scored
  2.3 and was thrown away.
- **anchors** — a phrase in the transcript pinned to a time on screen. The good
  ones are events you can date from the screen alone and that the narration
  names as they happen: a session picker opening while he says *"here are
  several sessions"*. Two of those, 341 s apart, agreed to 0.11 s and landed
  within 0.17 s of the metadata seed.

`--verify` writes paired frames — screen on the left, camera on the right — at
the moments the screen moved most, because a frozen frame proves nothing: two
identical screenshots look aligned at every offset.

### The cutting rule

A pause is dropped only where the speaker is silent **and** the screen is not
doing anything. Silence alone is the wrong test on a screencast: the long wait
while output streams is the one silence a viewer needs to see. On the shoot this
was built for, 91% of the screen was a frozen frame, so it is the freeze mask
that keeps the cut from being driven by breathing alone.

Each drop keeps `air` seconds at both ends, so a join never clips the words
around it, and anything left shorter than `min_drop` is not worth a cut.

### The manifest

```json
{
  "id": "claude-demo",
  "screen": "sources/screen-2026-08-26.mp4",
  "camera": "sources/IMG_2695.MOV",
  "camera_rotate": "none",
  "words": "transcripts/claude-demo.words.json",
  "canvas": { "width": 1920, "height": 1080, "fit": "pad" },
  "pip": { "corner": "bottom-left", "size_px": 360, "margin_px": 48,
           "crop_x": 0.46, "corner_radius_px": 18, "border_px": 3 },
  "cut": { "min_silence": 0.7, "air": 0.22, "min_drop": 0.3,
           "silence_db": -34, "freeze_db": -60, "require_frozen": true,
           "force_over": 1.2,
           "camera_when_frozen_over": 100.0, "cutaway_lead_out": 3.5 }
}
```

- **`camera_rotate`** is `auto` (believe the file), `none` (the tag is wrong) or
  an angle. Look at a frame before choosing — see the gotcha below.
- **`fit`** is `pad` (pillarbox, nothing lost) or `crop`. A 3840x2280 capture is
  32:19, *taller* than 16:9, so `pad` lands it at 1818x1080 with 51 px bars and
  `crop` trims 120 px of source height instead.
- **`crop_x` / `crop_y`** place the square inside the camera frame, 0 to 1. The
  square itself is `min(iw,ih)` — an expression, not a probed number, so it
  stays square whichever way round the source turns out to be.
- **`cut`** knobs are the tightness dial. `--list` prints what each setting
  actually costs before anything is encoded.

`--plan` writes `projects/<id>/<id>.cuts.json`, a keep-list of
`[start, end, layout]` in camera time. Edit it and re-run with `--cuts` to
override any decision the planner made.

### Tuning the cut

Three knobs decide how hard the cut bites, and one decides when the screen stops
being worth looking at:

| key | |
|---|---|
| `min_silence` | ignore gaps shorter than this |
| `air` | seconds of breath kept at each end of a cut |
| `force_over` | a silence this long goes **even if the screen is moving** |
| `camera_when_frozen_over` | once the screen has sat still longer than this, show the camera full-frame instead |
| `cutaway_lead_out` | come back to the screen this early, before it moves again |

`force_over` exists because `require_frozen` is a guard against jump cuts
mid-animation, not a reason to sit through a long dead spell just because output
happened to be scrolling behind it. On this shoot it recovered another 4 s that
the freeze mask was protecting for no good reason.

`camera_when_frozen_over` is the one that changes the film rather than its
length. A picture-in-picture does not rescue a frozen frame — 95% of the canvas
is still dead — so past a threshold the camera takes the whole frame and the
screen comes back when it has something to show. **Test the frozen RUN, not the
overlap with a kept segment:** pause-cutting chops a dead region into many short
segments, and asking each to clear the threshold on its own means the deadest
stretch in the film qualifies for nothing. That was the first version, and it
silently cut away for 0.0 s.

`cutaway_lead_out` matters more than it looks. Narration points at the screen
("внизу можна подивитися…") a second or two *before* the thing it points at
happens, so returning on the exact frame the screen moves leaves the viewer
staring at a face during the sentence that sends them to the screen.

Sweep them before committing to any — `--list` prices each setting without
encoding anything. On this shoot:

| min_silence / air / force_over | cuts | removed | core |
|---|---|---|---|
| 1.5 / 0.40 / off | 11 | 27.1 s | 7:53 |
| 0.8 / 0.25 / 1.2 | 33 | 45.6 s | 7:35 |
| **0.7 / 0.22 / 1.2** | **37** | **49.0 s** | **7:32** |
| 0.5 / 0.15 / off | 62 | 58.2 s | 7:22 |

Below about 0.7 s the cut count climbs faster than the runtime falls — 62 cuts
in seven minutes is one every seven seconds, and 0.15 s of air starts clipping
consonants.

### Where the film starts and ends

`film.start_text` / `film.end_text` quote what is said rather than naming a
timecode, so the bound survives a re-transcribe. Left out, the film runs from
0.6 s before the first word to 0.8 s after the last.

A phrase lands on the word's own edge, which cuts the instant the speaker stops
— audibly abrupt, and tighter than that default. `start_pad` / `end_pad` buy the
breath back. They default to 0, so a manifest already cut against a phrase keeps
the timing it shipped with.

```json
"film": { "end_text": "Desktop Sharing", "end_pad": 0.8 }
```

Worth cutting to: `claude-demo` ends there because the speaker turns away at
7:37 of the finished film and gives the last sentence in profile, to a phone
that is switched off. The audio is fine; the picture is not. **Read the picture,
not just the transcript** — a sentence that reads well can be delivered to
nobody.

### Bookends, and picture that has nothing to say

Footage shot separately — an intro recorded after the fact, a silent shot of the
rig — goes in `bookends.open` / `bookends.close`. Each is a clip from a source of
its own, rendered to the same canvas and concatenated as another act:

```json
"bookends": {
  "open": [
    { "id": "px-intro",
      "source": "sources/PXL_20260716_160930856.mp4",
      "start": 0.6, "end": 23.1,
      "broll": [
        { "source": "sources/PXL_20260716_155547234.mp4",
          "at": 8.8, "dur": 7.6, "from": 48.0 }
      ] }
  ],
  "close": []
}
```

`start` / `end` accept `start_text` / `end_text` instead, resolved against a
`words` transcript of that clip.

**`broll` is how a silent clip earns a place.** The bookend's own sound runs the
whole way; only the picture cuts away and back. `at` is the offset into the
bookend, `dur` how long the cutaway lasts, `from` the in-point in the b-roll
source. The parts are checked to tile the bookend exactly — a gap or an overlap
would leave the picture and the sound different lengths, and that is refused
before anything renders rather than discovered afterwards.

The setup take on this shoot transcribed to **zero words**. As an act of its own
it would be 75 seconds of silence; laid under the line about combining files
from two phones, it is the only shot in the film that shows the rig.

Because acts are concatenated, each one is normalised to the canvas and to
48 kHz stereo before the join. That matters more than it sounds: the camera here
is mono 44.1 kHz and the bookend was shot on a different phone at stereo 48 kHz,
and `concat` refuses a mismatch outright.

### What it checks before shipping

Duration against the keep-list, output dimensions against the canvas, that the
output carries no rotation, and that the audio is **not silent** — which is the
failure that made this pipeline necessary in the first place.

## A screencast with no soundtrack at all

`screencast-cut.py` above cuts a screen recording against a camera take that
carries the sound. Sometimes there is no camera and no microphone: Windows'
window capture, started from the Game Bar, writes a **digitally silent** AAC
track — `-91 dB` mean *and* max, which is not room tone, it is zero — and the
voice-over is recorded later against the finished film.

That breaks every silence-driven decision in that pipeline. `min_silence`,
`force_over`, the whole keep-list: they all reduce to "cut everything" or "cut
nothing" when the audio never crosses any threshold. Measure the picture
instead.

### One command, twelve stages, two stops

```powershell
python scripts/screencast-pipeline.py --project <id> --target 8:00
python scripts/screencast-pipeline.py --project <id> --target 8:00 --approve --upload unlisted
```

The first edit of this kind took six hours as ~40 hand-typed commands; the
retro is `docs/retro-books-giveaway.md`. The pipeline runs the same work in
the only order that does not waste it, and every stage fingerprints its inputs
into `temp/pipeline/<stage>.json` so a rerun after one manifest edit costs one
piece and one gate:

| stage | script | what it guarantees |
|---|---|---|
| import | `import-footage.py` | desktop + phone captures found, duplicates dropped, ordered by real capture start, audio checked |
| proxies | `make-proxies.py` | everything after reads the working size, once |
| activity | `screen-activity.py` | per-region motion; the panel divider *found* (`--find-panel`) |
| ocr | `scan-pii.py` | every sampled frame read **once**, cached; rules are a second pass |
| track | `track-blur.py` | each secret's pixels followed; templates pooled across the session |
| recall | `track-blur.py --recall` | the tracker measured against the OCR hits; **stops below the bar** |
| review | `redaction-review.py` | **the stop**: a before/after sheet of every redaction; nothing renders unapproved |
| smoke | `screen-cut.py --smoke` | 30 s of the busiest source through the full graph, in a minute |
| draft | `screen-cut.py --hot --draft` | **the second stop**: a half-resolution trailer of the riskiest minute, for a human to watch |
| render | `screen-cut.py` | content-addressed pieces, stream-copy join |
| gate | `render-gate.py` | the secrets' own pixels searched on the *render*; `--patch` and loop |
| upload | `yt-upload.py` | unlisted, only after a clean gate and an approved look |

The individual tools remain usable on their own; the pipeline is what makes
the order and the caching un-forgettable.

### Drafts: proof cheaper than the product

The render is the product, not the proof. Two levers, kept separate because
they answer different questions:

- `--draft` — half resolution, fast encoder preset, ~4× faster. Every rect in
  this pipeline is a fraction of the frame, so a draft is a *valid* review of
  the redaction; what it cannot judge is fine text legibility, which the final
  and the gate cover.
- `--range 2:00-3:00` or `--hot` — a stretch of *film* time mapped back
  through the cut, or the risky moments (every secret's first appearance and
  every hand rect, a few seconds each, ~a minute). For reviewing one issue.

They combine (`--hot --draft` is the pipeline's `draft` stage), write to their
own output name and their own piece cache, and never touch the film the
manifest names. The 30-second `--smoke` stays at final settings on purpose —
its job is the filter graph and the encoder, which a draft cannot validate.

### The register: `docs/known-issues.md`

One entry per thing that bit us or that the tools cannot do — id, status
(`limitation` / `open` / `fixed`), stage, symptom, cause, fix. It is the
canonical home; Gotchas below keeps the prose for traps in tools we do not
control, and journals and retros link to it by id. The pipeline **reads it at
start** and prints every open issue and limitation for the stages it is about
to run, so the register is seen on every run rather than remembered on some.

### The reviewer's recording is an input

The best review of the first cut was the user's own: they scrubbed the film in
a player with its timecode visible in the corner, recorded the screen, and said
what was wrong. Turning that into a ticket list by hand — transcribe, read the
timecode off each frame, map film time back through the cut — took forty
minutes. `review-ingest.py` does it in two:

```powershell
python scripts/review-ingest.py --manifest projects/<id>/screen.json --recording <review.mp4> --target 8:00
```

It transcribes the narration, OCRs the player's timecode from the bottom-left
corner **per segment**, groups consecutive segments that read the same
timecode into one remark (one remark per frame paused on — the reviewer's own
unit, not a speech pause), and maps each through the render plan to a source
and a source time. It appends a dated table to `projects/<id>/review-notes.md`
with an empty *disposition* column and changes nothing else: what to do about
a remark is a decision, and the manifest is edited by the person or the gate.

```powershell
python scripts/screen-activity.py --src <proxy> --list --probe-motion
python scripts/scan-pii.py        --src <proxy> --out temp/pii/<base>.pii.json --report
python scripts/track-blur.py      --src <proxy> --outdir temp/track/<base> --manifest <screen.json> --recall
python scripts/screen-cut.py      --manifest <screen.json> --list --sweep
python scripts/screen-cut.py      --manifest <screen.json> --target 8:00 --smoke
python scripts/render-gate.py     --manifest <screen.json> --target 8:00 --patch
```

### Activity is measured per region, not per frame

`screen-activity.py` decodes small and slow (gray, 320 px wide, 6 fps) and
counts the fraction of pixels that changed by more than a noise floor. A static
screen scores ~0; typing and scrolling score high. The threshold is on the pixel
**delta**, not on equality, because H.264 at 4K re-quantizes flat areas between
keyframes and an untouched screen still flickers by a few levels.

One number for the whole frame is not enough, and the footage says so. On a
screencast of an agent working, two very different things both read as "the
screen is moving": the human clicking through a checkout, and an AI streaming
text into a side panel. So activity is measured per **named region** and the
edit is a three-way decision:

| what is moving | what the cut does |
|---|---|
| `main` — the browser | keep at `keep_speed` (1x by default) |
| only `panel` — Claude thinking | run at `speed` |
| nothing | drop it |

`--probe-motion` finds the panel for you rather than making you hunt: it reports
which eighth-of-the-frame cells move during otherwise-still stretches. On the
`books-giveaway` footage every recording named the same column, and measuring
the vertical edge across six timestamps per file put the Edge side-panel divider
at **x = 0.748** on all five recordings that had it open.

Without the region split there is nothing to fast-forward *with*: whole-frame
activity says 80% of that footage is dead, but the interesting 20% and the
boring 20% look identical to it.

### A spinner never stops, so `ignore` it

A "thinking" animation, a blinking caret, a taskbar clock or the recorder's own
running timer keeps a dead screen permanently above any threshold, and nothing
is ever cut. `ignore` rectangles are given in **fractions** of frame size, so
they survive a resolution change, and are blanked before the difference is
taken. The phone screen recordings here ignore `0,0,1,0.04` — the status bar
with its clock and the red recording dot.

### Hold, or the film strobes

Thresholding the raw activity track produced **1094 segments** across 47 minutes
and a film that flickered between 1x and 6x several times a second. Screen
activity is bursty in a way that means nothing: text arrives in packets, a
scroll is a flick and a wait, a caret blinks.

`hold` dilates each region's boolean track forward and back — "it moved within
the last second, so it is still moving", which is what a viewer perceives
anyway. `panel_hold` is longer (2 s) because streaming text is burstier than a
mouse. That one change took the same footage to **579 segments**.

Then any run shorter than its class minimum is absorbed into a **neighbour**,
repeatedly, until nothing short is left — into the *longer* neighbour, not
always back to "keep". Absorbing to keep put a visible hitch in the middle of
every fast-forward, because half a second of panel flicker inside a two-minute
wait belongs to the wait.

Finally `air` hands back a fraction of a second at each end of a dropped run
**at 1x**, so a cut lands on stillness. The first version handed it back as
*sped* footage, which is not breath — it is a quarter-second lurch on either
side of every join.

### Length is a decision, so price it

`--list` prints where the runtime actually goes, and the answer is usually not
where you would guess:

```
  source                                      in    drop      1x sped in     out  segs
  TOTAL                                  47:14.4  3:17.2 21:45.5 22:11.7 25:27.4   579
```

Only 3:17 of 47 minutes is truly dead — the spinner means something is nearly
always moving. Raising `speed` from 6x to 12x only moves the film from 25:27 to
23:36, because **21:45 is held at 1x** and no panel setting touches it. That is
what `keep_speed` is for, and `--target M:SS` solves for both together, keeping
the panel:work ratio the manifest asked for:

```
  --target 8:00.0: x3.18 on both speeds -> work 3.18x, waiting 19.07x, giving 8:00.5
```

`hold_1x` windows on a source are forced to 1x whatever the picture is doing and
do **not** scale with `--target`. That is the point of them: "show each of the
eight books" is a content requirement, and no motion metric knows which page
matters. The solver reports the floor they impose.

`--sweep` prices a grid without encoding anything; `--sheet` writes one frame per
kept segment and per blur rect, which is the check that costs nothing.

### Blur runs in source time, before the cut

This is the same trap as the name label's `at` being *film* time. Once segments
are dropped and others run at 19x, a window measured against a source timecode
no longer lands where it was measured. Rather than map every window through the
cut, the **mask** is painted upstream of the trim — the tracked mask stream
plus one white `drawbox` per hand rect, `enable`-gated in source time — so a
rect verified against a source frame stays verified. The mask is then cut on
exactly the boundaries the picture is cut on, and the one gaussian runs
**after** the trim, on the frames that survive.

The order inside the pass is deliberate: `scale → paint mask → trim → concat →
blur → pad`. Scaling first makes everything run at 1080p instead of 4K; the
first version blurred before the trim, which kept the windows in source time
but spent the gaussian on all 47 minutes of footage to keep 8 — measured on 60 s
of a real proxy producing the same 10 s: 8.4 s before the cut, 3.5 s after it
(KI-021). Padding after the concat means the canvas is applied once. `box` and
`pixelate` rects stay per-rect and upstream, because a crop is cheap and a
mosaic has to be built at the rect's own scale.

`mode: "blur"` is the default — the user's words were "blur, not black out" —
and it is one downscale/gblur/upscale of the whole frame shown through the
mask, so rect count adds nothing to per-frame cost. `pixelate` remains as a
per-rect mode for a field that should read as deliberately hidden: a `crop →
scale down → scale up with `neighbor``, `enable`-gated to its window.

### Finding what to blur, instead of scrubbing for it

A screencast of somebody buying things is a screencast of somebody typing their
card number, with other people's names, phones and delivery addresses sitting on
the page while it happens. Deciding what to blur by scrubbing is how a phone
number reaches YouTube: the eye skips the one frame between two identical-looking
ones, and 4K screen text is unreadable at the zoom a human scrubs at.

`scan-pii.py` samples, OCRs (RapidOCR on onnxruntime — no torch), and matches
patterns that describe the **shape** of the secret rather than its value: a card
number is 13–19 digits that pass Luhn, a CVV is three digits next to the word, a
Ukrainian mobile is `+380` and nine more, an IBAN is `UA` and 27. Each hit is
reported with the time it is on screen **and** the box it occupies in frame
fractions — exactly the shape a `blur` entry wants — and `--emit` writes those
entries so the manifest is generated from measurement rather than typed from
memory.

Two things it taught us on this footage:

- **Luhn is what makes the card rule usable.** `Замовлення #1806413786` is ten
  digits in a row and is not a card. Without the checksum every order number on
  every confirmation page becomes a false positive.
- **Match the mask's shape, not its glyph.** Privat24 draws a bullet; this OCR
  model returns `----`, another returns `****`, a third drops it. Requiring the
  full 27-character IBAN found *nothing* — the field is always drawn part-masked
  (`UA57 ---- 1111111`). The prefix plus any digits is the real signature.

`--match NAME=REGEX` rides the same pass, because the expensive half is the OCR,
not the matching — so "where does each order confirmation appear" costs nothing
once the frames are being read anyway.

A third lesson cost a proof frame to find: **the country code is optional.**
The first phone rule required `+38`, and a Claude panel summary reading
`(Київ, відділення 57, 0XXXXXXXXX, <recipient name> — «Іздрик…», 430 грн)`
sailed through it — city, branch, phone and full name, in the clear, in the
national `0XX` form. A Ukrainian mobile is 0 plus nine digits however it is
punctuated, and `check-screen.py` holds that shape as a fixture (with
synthetic values: the fixtures test shapes, and this file is shared).

**It is a net, not a clearance.** OCR misses rotated, low-contrast and
partly-scrolled text, and it cannot know that a first name plus a Nova Poshta
branch identifies a real person. A clean report means "nothing obvious left",
never "safe to publish" — look at the `--sheet` frames before you encode.

Two habits make the net much tighter:

- **`--sheet` composites every rect active at that instant**, not one at a
  time. The one-rect proof is actively misleading: it showed a card panel
  "covered" while a full IBAN two rects away sat in the clear, because the rect
  meant to catch it was drawn on its own frame.
- **Scan the RENDER, not just the sources.** The film is 1080p and eight
  minutes, so a pass over it costs a few minutes and checks the thing you are
  actually about to publish — including anything a source-time window missed
  because the cut moved it.

```powershell
python scripts/scan-pii.py --src projects/<id>/outputs/<id>.mp4 --report --fps 0.25
```

Anything that comes back is a rect that did not land. Fix it in the manifest,
not by trimming the film.

### Transcode once, at the size the work happens

Every pass over this footage decoded 3840x2280 and threw most of it away in its
first filter: `screen-activity.py` analyses at 320 px wide, the render's first
step is a scale to 1080p, the contact sheets are 480 px tiles. That decode is
the dominant cost of the whole pipeline and it was being paid on every
iteration.

```powershell
python scripts/make-proxies.py --manifest projects/<id>/screen.json --list
python scripts/make-proxies.py --manifest projects/<id>/screen.json --verify
```

It writes one file per source at the canvas fit size and records the path on
each source; `screen-cut.py` reads it automatically, and `--no-proxy` goes back
to the originals. On this project the proxies are **3% of the source bytes**
(4.5 GB -> 38 MB for the longest recording).

Why this is safe rather than a quality trade:

- **Every rectangle in this pipeline is a FRACTION of the frame, never a pixel
  box.** Blur rects, `ignore` rects and region definitions all are. Proxy and
  original are interchangeable by construction, so there is no "now apply the
  decisions to the big one" step to get wrong.
- **The proxy is the working resolution, not a preview.** The deliverable is
  1080p, so the scale has to happen anyway — doing it once up front is strictly
  less resampling than doing it inside every render.
- `screen-cut.py` **skips the scale filter entirely** when the input already
  matches the fit size, so the proxy is not resampled a second time.
- Screen text is where H.264 hurts most, so the proxy is encoded at `cq 16` and
  `--verify` scores it against the source frame by frame rather than assuming.

**OCR reads the proxies too.** An earlier version of this section claimed OCR
needed the originals because text recognition is resolution-bound. It is — but
the scan runs at 1600 px wide and the proxy is 1818 px, so nothing is lost, and
decoding 4K for it was pure cost. The lever on OCR time is fewer frames
(`--skip-static`) and the per-frame cache, not larger ones.

### Blur follows the pixels, not the clock

A blur rectangle anchored to a **time window** is the wrong primitive, and
every leak this project chased came from that one mismatch: scan-pii reports
"this phone number is at (x,y) around t=204", the page scrolls, the field
moves, the rect does not. The blur lands on the wrong rows and the secret
stays sharp somewhere else. Widening rects, merging rows, blanketing whole
panels — all of it was compensation for anchoring to the wrong thing.

The right primitive is standard, and editors call it **tracked redaction**:
detect once, then track. A screen recording is the *easy case* for it,
because a browser renders the same text pixel-identically every frame it
appears — no lighting, no noise, no perspective. So:

```powershell
python scripts/track-blur.py --src <proxy> --pii <pii.json> --outdir <trackdir> --manifest <screen.json> --list
```

`track-blur.py` cuts each secret scan-pii found out of the frame as a pixel
**template**, then finds those pixels in every frame with normalized
cross-correlation (`cv2.matchTemplate`). Wherever they are — scrolled,
repeated twice on screen, back after a page change — that is where the blur
goes, sized exactly to the match. Content-anchored, and minimal by
construction. The manifest points a source at its track dir with `track`, and
`screen-cut.py` feeds the resulting mask stream as a second input: the frame
is blurred **once** and shown through the mask, so box count adds nothing to
per-frame filter cost.

The cost model is what makes it fast: unchanged frames reuse the previous
boxes (60–80 % of a screencast); a tracked instance is re-found in a local
window; only a lost template pays a full-frame sweep, at half scale, and only
every 15th frame once it has gone cold. A 55-second clip tracks in 26 s.

Three findings that are now constants in the script, all verified on the
Privat24 clip:

- **Match across scale.** The app draws the same account number at list,
  detail and form sizes, and NCC only matches its own size. A template is
  searched at ×0.75 / ×1.0 / ×1.3, and one variant is kept per rendered
  height that OCR saw.
- **Refuse tiny templates.** A 39×11 "UA39" patch carries so little structure
  it cleared 0.90 NCC against a *face*. Anything under 48 px wide or 12 σ of
  contrast is not evidence and is dropped at collection; the wider templates
  on the same row cover it.
- **The mask stream must outlive the source.** `alphamerge` pairs frames
  one-to-one; a mask that ends early stalls the graph exactly like the
  looped-PNG alpha in the shorts pipeline. The concat listing is written
  seconds longer than the source on purpose.
- **Pool the templates across recordings.** One session's secrets cross its
  recordings: the card number typed into the Claude panel in one capture was
  OCR-read only in *another*, so a per-source pool left it sharp exactly where
  it mattered. `--pii` takes every same-geometry scan at once; the pixels are
  still cut from the file each hit was found in, at working resolution.

And the honest boundary, written down so nobody re-learns it: tracking loses
where the pixels themselves change — text the user *selects* (white-on-blue
does not match a template captured black-on-white), a window-switcher
thumbnail rendering a title at arbitrary scale, a photographed screen
(handheld footage: 14 % recall), and anything OCR never saw, which has no
template at all. Those cases carry hand `blur` rects in the manifest, each
with its reason. Tracking is the tool for consistently-rendered browser
footage; it does not replace looking at the frames.

The masks are one PNG per stretch of stable boxes — a still page costs one
PNG however long it holds — turned into a stream by the concat demuxer.
Hand-measured `blur` rects still work and ride the same pass; they are for
what OCR cannot see at all (the monobank card faces).

### Redact the film, not the footage: `film-redact.py`

Tracking in **source** time is right for a film that is mostly its footage.
It stopped being right for this one, and the numbers said so before any
argument did: a readable secret is on screen for **148 of the film's 480 s**
(31 %), 133 of 160 gate hits sat in the stretches running at 3x, and one
round of render → gate → patch cost **2 h 16 m**. Secrets were not a few
patches on this film; they were its normal state.

Worse, every serious bug lived in one place — the **mapping** from source
time back to film time, through the cut, the speed change and the pad. Twice
the `fps` filter labelled a sampling slot rather than a frame (KI-006,
KI-022); at 19x, half a second of mislabelling is nine seconds of source, so
the gate patched windows the secret was never in and four rounds converged on
nothing.

So the film-time pipeline removes the mapping instead of debugging it:

```powershell
python scripts/screen-cut.py  --manifest projects/<id>/screen.json --target 8:00 --no-redact
python scripts/film-redact.py --project <id> --states --detect -j 8
python scripts/redaction-review.py --manifest projects/<id>/screen.json --states --html
python scripts/film-redact.py --project <id> --blur
python scripts/film-redact.py --project <id> --gate
```

Cut the film unredacted, then work on the film itself. One timebase, no
mapping, and a gate that asks the answerable question — *is every box we
found actually blurred on the render* — instead of re-scanning 14,400 frames
for secrets it has already located.

**The unit of work is the screen state, not the frame.** The film has 14,400
frames and about 500 page-scale changes; detecting on every frame is 28x the
work for the same answer. `--states` segments the film into runs showing the
same thing — 1,330 of them here, in 1:56 — writes one representative frame
per state, and `--detect` OCRs those. The boxes then carry across the state's
whole run, and `--blur` paints one mask per stretch of identical boxes.

Two traps found while building the segmenter, both worth the reader's time:
`select`'s frame counter **restarts when the decoder re-initialises** (it does,
at the portrait phone clip), so a frame must be asked for by TIME and never by
index; and piping full-resolution frames out of ffmpeg to write them in Python
is 89 GB of pipe for this film — let ffmpeg write the PNGs itself, which does
700 in 28 s.

**What detection actually costs, measured rather than hoped.** 2.7 s per rep
frame (0.86–4.36 s over ten reps spread across the film). One process alone
manages 0.37 rep/s; **eight workers manage 0.44** — 19 % more, not eight
times more, because the OCR model is memory-bound and not core-bound. Two
things follow. Do not size `-j` as though it scaled: `--jobs 8 --threads 1` is
about the ceiling this machine has. And onnxruntime **ignores** `OMP_NUM_THREADS`
and every other thread environment variable — its pool must be set in the
constructor (`--threads`, KI-024), and left unset each of eight workers opens
a pool per core and the pool runs *slower than one process*.

An hour of OCR will be interrupted, so `--detect` checkpoints every 25 reps
and resumes where it stopped (`--fresh` to start over), and it should be
launched detached rather than under anything with a timeout. Losing 17 minutes
of finished work to a killed run is a fixable mistake and only had to happen
once (KI-025).

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

Nothing renders unreviewed here either: `redaction-review.py --states` builds
the same before/after sheet from the film's own states and detections, asks
once per KIND of secret rather than once per appearance, and `film-redact.py
--blur` honours the `decisions.json` it produces — a state marked *clear* is a
false positive and keeps its pixels.

### The arithmetic and the rules have their own test

```powershell
python scripts/check-screen.py
```

No GPU, no files, no OCR. It covers the two halves a render cannot check for
you: the PII rules against the exact strings that came off these frames
(including both false positives), and hold/absorb/air on a synthetic label
track. A stutter or a missed PAN otherwise costs an encode to discover.

### The render carries no audio at all

`-an`, deliberately. The sources are silent, and the voice-over is recorded
against the finished cut; muxing a silent AAC track just invites a later pass to
mix onto it and produce nothing.
## A film cut by hand from a few takes, with an honest clock over the wait

`screen-cut.py` chooses what to keep from motion. That is right for an hour of
capture and wrong for five takes somebody has already watched: the decisions
are editorial ("the second download is the better one", "two seconds of that
hover, not fifteen"), and a motion metric cannot make them. On `bpo-realtor` it
called the whole two-minute fill "still", because a progress bar moves below any
threshold that also ignores cursor jitter. `edl-cut.py` takes the decisions as
data: an edit decision list in film order, one `_why` per line.

```powershell
python scripts/edl-cut.py --manifest projects/<id>/edit.json --list          # EDL, runtime, counter span
python scripts/edl-cut.py --manifest projects/<id>/edit.json --frame 1:33    # one finished frame, card included
python scripts/edl-cut.py --manifest projects/<id>/edit.json
```

```json
"sources": {"take3": {"path": "...", "bg": "#ece6fd",
                      "paint": [{"rect": [x, y, w, h], "color": "#d3e1f8"}],
                      "blur":  [{"rect": [x, y, w, h], "when": [168.8, 190.0]}]}},
"edl": [{"src": "take3", "from": 61.3, "to": 168.8, "speed": 10, "_why": "the fill"}],
"counters": [{"src": "take3", "start": 58.0, "end": 168.88,
              "label": "AI filling the form", "done_label": "Form filled"}]
```

**The counter runs on source time, not film time.** Every film frame is mapped
back through the EDL to the source instant it shows, and the card reads
(that instant − `start`). So it races under a 10x segment, crawls at 1x, jumps
honestly across anything cut from inside its span (`--list` says how much), and
lands on the true interval at the frame the footage reaches `end`, whatever
speeds you choose. Measure `start`/`end` to the frame off the source (a crop's
mean brightness across a 1/60 s scan finds a click or a message appearing).
A counter whose start or end is not in the film is refused: it would either
never appear or freeze mid-count.

**If the app prints its own duration, decide which clock you are showing.**
The app wrote "processed in 1 minute and 28 seconds", its server's interval;
Submit to that message on screen is 1:50. Two different numbers side by side
read as a mistake, so the manifest blurs the app's line (`blur`, source time)
and the card shows click-to-result, which is what a user waits.

The card is drawn by Pillow, one PNG per distinct state, and piped into a short
PNG-in-MOV clip with alpha that is overlaid inside the film's one encode.
Montserrat's figures are proportional, so each digit gets a fixed cell sized to
the widest figure. Without that, the clock shifts sideways every second. A
`▶▶ 10×` chip shows while the footage is sped up, so the viewer knows why the
digits are racing. Style is `config/overlays/elapsed-counter.json`.

`paint` fills a source rect with a flat colour. Use it for browser chrome: tab
titles and a `C:/Users/<name>/...` path, painted over in the chrome's own
sampled colours so the Cursorful window keeps its shape. A crop would lose that
framing and not match the takes that have no chrome. Sources of different
heights are padded to the canvas with `bg`, sampled off the frame edge, so no
seam shows. Segment lengths are whole frames, and every film offset is a sum of
them, so the card and the picture cannot drift apart across segments. The
render asserts its duration against that sum.

**A fixed paint rect breaks the moment the recorder zooms.** Cursorful zooms
toward the cursor. On review 1 the chrome slid out from under the rects, so
blue stripes landed on the page while the real address bar, file path and all,
came into view beside them. Now every frame the EDL uses is tested. At rest, a
paint rect is mostly its own colour. Where it is not, the chrome has moved, and
for that run the rects are carried by a tracked similarity transform (ORB on
the chrome band, RANSAC):

- The tracker works frame to frame, fitting only the residual after warping by
  the last transform. At 1.5× a single-scale match against the unzoomed frame
  found 3 inliers of 400.
- It refuses to guess. If it loses the chrome or the residual grows, it stops
  and prints the time.
- `--list` prints the followed runs, and the transforms are cached under
  `temp/edl/`.
- The rects go into a half-resolution alpha clip upscaled with **nearest**.
  Bilinear blends the clear pixels' black into each edge and draws a dark
  outline round every rect.

**Zooms** are accents. They are authored in source time on a canvas rect
(`zooms: [{src, from, to, rect: [x, y, w], in, out}]`) and rendered by
`zoompan` on a 2× upscale inside the same pass. A zoom's window ends at the
first frame that leaves its source. An earlier rule ("last frame at or before
`to`") let a zoom that ended on a cut to the phone reach across the cutaway and
magnify it. Check where the counter card lands inside a zoom: at 1.95× Submit
went under it, so that stretch uses 1.6×. A zoom is also a way to keep
something out of shot. The Submit framing starts below a warning banner, fully
in before the banner appears, and leaves on a hard cut, because an ease-out
showed the banner again.

**Phone takes:** `rotate: 180` handles a missing or wrong rotation tag. This
one had none and played upside down. A phone that did not roll through the
take it cuts into is B-roll, and the manifest says so. `sync-tracks.py`, click
matching and brightness correlation all failed to pin the phone to take 5
(z ≤ 3.6 and mutually inconsistent). A 1.5 s cutaway of a click does not need
sync, but it must not be presented as the same click.

**Voice, captions and music in the same pass.** A silent film gets its voice
from `dub-clips.py --script` run over the picture-only render. Use one clip
spanning the film, with no `words` in its manifest: `--script` no longer needs
a source transcript, and a dub still refuses without one. `edl-cut.py` then reads:

```json
"audio":    {"voice": "<vo.wav>", "music": "<track or null>", "music_db": -22, "lufs": -14},
"captions": {"words": "<vo.words.json>", "style": "config/presets/band-dark.json",
             "display": {"five hundred and thirty-four": "534"}}
```

The music loops, fades in and out, and ducks under the voice through a
sidechain compressor keyed on the voice. The mix is loudness-normalised, and a
silent result is refused. Captions come from the voice-over's own word timings,
not from ASR over the film. `display` rewrites spoken phrases into how they
should read ("one minute and fifty seconds" becomes 1:50) and keeps the timing.
Transcribe the voice back and diff it against the script before trusting it.
On bpo-realtor every difference was number formatting, apart from one
"and"→"in" that ElevenLabs actually said.

**A vertical short from the same takes** is one more manifest (`canvas: [1080, 1920]`,
`config/examples/edl-short.example.json`):

- An EDL entry may carry `crop: [x, y, w, h]` in source pixels. It runs after
  paint and blur, so their rects stay in full-source pixels. Keep every crop at
  one aspect (5:4 here) so the picture box never changes shape between shots.
- `image_overlays` work as in `tighten-cut.py`, after the counter card and
  before the captions. The title card uses them.
- `counter_style` picks a vertical counter (`elapsed-counter-vertical.json`:
  `scale`, `top-centre`). On a short the counter takes the title band's place
  while the fill runs: under the picture it collided with the captions, so the
  title steps aside in two windows instead.
- `checklist-card.py` scales by `min(H/1080, W/1200)` so a vertical card is not
  wider than its frame. `window-vertical.json` is the faster variant for shorts.
- The caption preset for this layout is `vertical-band-dark.json`.

## Tightening one recording that is already composited

`screencast-cut.py` needs two tapes. Most screen recorders hand you one — screen,
webcam bubble and narration already burned together, one clock, nothing to sync.
That recording is usually 20–30% dead air, because talking to a screen while
operating it is not a fluent activity. `tighten-cut.py` is the subtractive pass
for that file: it shortens the pauses, swallows the stumbles, and takes out the
parts you name, in one encode.

```powershell
# price the decision -- prints the plan and a pause sweep, encodes nothing
python scripts/tighten-cut.py --manifest projects/<id>/tighten.json --list

# render
python scripts/tighten-cut.py --manifest projects/<id>/tighten.json
```

It never re-frames, never composites and never speeds anything up. It removes
three kinds of time, and nothing else:

| what | how it is decided |
|---|---|
| pauses | a silence longer than `min_silence` is **shortened to** `keep_pause`, not deleted |
| fillers | an "um" that leans on a pause is swallowed by that pause; one in mid-phrase is left alone |
| removals | a span you name by quoting what is said inside it |

### A pause is shortened, not deleted

The obvious design — drop every silence over a threshold — produces a film that
sounds like a ransom note. Speech has rhythm, and the pause before a new idea is
doing work. So the knob is what **survives**: `keep_pause` is how much of every
long silence is left, split evenly across the join so the cut lands in the middle
of room tone rather than against a word. One number, and it degrades gracefully —
set it to 2s and nothing is cut at all.

`--list` prices it on the real file:

```
  63 silences >= 0.80s at -34dB inside the film (94.2s of 294.3s)
  64 segments, 3:45.10 of 4:54.30 kept (24% removed)
  segment length: shortest 0.40s | median 2.43s | longest 13.80s (a cut every 3.6s)

  pause sweep (min_silence x keep_pause -> runtime)
    min_sil  keep         cuts  removed runtime
    0.60     0.30           85    84.0s 3:30.28
    0.80     0.45           63    65.9s 3:48.41
    1.50     0.60           26    40.5s 4:13.84
```

**Read the segment line, not just the runtime.** A cut is a jump for whatever is
moving in the frame, and on a screencast the only thing moving is the webcam
bubble. Runtime cannot see that; "a cut every 3.6s" and "shortest 0.40s" can.

### Fillers only go where a pause already is

Cutting an "um" out of the middle of a phrase costs an audible seam and buys a
third of a second. Cutting one that is already sitting against a pause costs
nothing, because the join was happening there anyway. `fillers.reach` is how
close to a dropped span a filler must be to qualify; the rest are left in.

### The removal you cannot detect

Every demo has a line no detector can find, because it is perfectly fluent
speech that simply should not be in the film — "let me pause the video while
this runs", a false start, a sentence you said better the second time. Those are
named, and named by **quoting them**, so the manifest survives a re-transcription:

```json
"remove": [
  {"from_text": "let's wait a few seconds",
   "to_text":   "it's almost done yeah",
   "why": "waiting for the conversion, plus the aside about pausing the video"}
]
```

`pad_in` / `pad_out` (0.25s each by default) take the breath on either side with
it — leaving the pause that framed a removed sentence is what makes a removal
audible.

### The joins are ramped, and the transcript comes with

Each segment's audio gets a `join_fade_ms` ramp (12ms) at both ends. Room tone
spliced to room tone at a different phase **clicks**, and a click is the one
artefact that makes an edit audible to somebody who was not looking for it. 12ms
is below the threshold of hearing as a fade and above it as a click.

The word transcript is remapped through the keep-list and written as
`<out>.words.json`, in the envelope `transcribe-words.py` produces. The remap is
exact — a cut only deletes, so a surviving word is the same word displaced by
however much was removed before it — which means the tightened film can be
captioned without paying for a second transcription:

```powershell
python scripts/tighten-cut.py --manifest projects/<id>/tighten.json
cp projects/<id>/outputs/<id>-tight.words.json projects/<id>/transcripts/<id>-tight.words.json
python scripts/run-captions.py --input projects/<id>/outputs/<id>-tight.mp4 `
    --id <id>-tight --project <id> --style config/presets/dark-card.json
```

`run-captions.py` is resumable and skips a stage whose artifact exists, so the
transcript being already in place is all it takes for the ASR stage to be free.

### Name labels and end cards ride along

`name_labels` and `image_overlays` work exactly as they do in
`screencast-cut.py` — same keys, same presets, applied after the concat so their
`at` is **film time**, and inside the same encode. A negative `at` on an overlay
still counts back from the end, so an end card survives a re-cut.

### What it checks before shipping

Duration against the keep-list, audio not silent, and every label and overlay
proved to start before the film ends — the failure that is otherwise silent,
because `enable` simply never turns true and the card never appears.

## A Zoom recording, and a talk recorded in parts

A Zoom local recording is a FOLDER, not a file, and `zoom-import.py` exists
because four things about that folder are not guessable.

```powershell
python scripts/zoom-import.py --since 2026-09-01                     # what is on this machine
python scripts/zoom-import.py --project <id> --meeting "<folder>" --list
python scripts/zoom-import.py --project <id> --join --meeting "<a>" --meeting "<b>"
```

**`recording.conf` is the authority, not the glob.** It is JSON —
`{"items":[{"video":…,"audio":…,"process":100}], "magic_number":…}` — and
`process` is a *percentage*. Below 100 means Zoom has not finished converting:
the folder then holds `double_click_to_convert_NN.zoom` plus `video*.mp4.tmp`,
and **the .tmp probes clean as a short, valid mp4**. One such folder here holds
a 181 MB `.zoom` next to a 551 KB stub of a 30-minute meeting. Globbing imports
the stub. An unconverted folder is refused, with the percentage in the message.

**The sidecar `audio<magic>.m4a` is the same mix as the mp4's own track.**
Measured, not assumed: decoded to 16 kHz mono, the first 60 s of both files have
identical MD5s. It is never muxed in — adding it as a second track doubles the
voice. It is a fallback for a damaged mp4 and a cheap transcription input.
The only genuinely separate audio Zoom writes is `Audio Record/`, per
participant, and only when that was switched on; a separately recorded screen
share is `as<magic>.mp4`. Both are reported, never inferred.

**`creation_time` on the mp4 is when Zoom finished CONVERTING.** Measured here:
a take whose folder is stamped `10:26:31` local (= 17:26:31Z) carries
`creation_time` 17:36:00Z — ten minutes later, and the gap is the conversion.
The folder NAME, `YYYY-MM-DD HH.MM.SS <topic>` in local time, is the only honest
capture start, so parts are ordered by that. Ordering Zoom parts by
`creation_time` orders them by how fast each one encoded.

**A talk in parts is one film.** Zoom opens a new folder every time the host
stops and restarts, so `--meeting` repeats and `--join` concatenates. The parts
carry identical encoder settings, so the concat demuxer joins them stream-copied
— seconds, no generation loss — and the result's duration is asserted against
the sum of the parts to within a frame, because a discontinuity otherwise
produces a film silently missing half a part. Joining is what buys the whole
downstream **one clock**: the cut, the word transcript, the caption times and
the Resolve timeline all address the same file, and no stage carries an offset.

A Zoom talking head then goes through `tighten-cut.py` (above) — one clock,
subtractive, nothing to sync.

### What it checks before shipping

`check-zoom.py` is the self-test, and it runs in seconds with no GPU and no
files: the folder rules against the shapes real recordings have — including
the unconverted folder whose `.tmp` probes clean — the folder-name ordering,
and the emphasis matcher's two rules. Run it after touching `zoom-import.py`
or the emphasis half of `build-captions-ass.py`.

Handing the resulting cut to DaVinci Resolve as an editable timeline is
`resolve-export.py` — see "Handing an edit to DaVinci Resolve" below, and
`docs/davinci-resolve.md` for what Resolve's own files are and are not.

## Cutting between cameras, and proving the cut is right

`screencast-cut.py` composites two tracks into one picture. `angle-cut.py`
chooses **between** tracks: N synchronised cameras, switching full frame, in one
NVENC pass. It exists on its own merits, and it also has a test harness that no
other pipeline here has — one that can take somebody else's finished multicam
film, rebuild the raw tapes it must have been cut from, re-cut it with these
scripts, and score the result against the original frame by frame.

That round trip is the point. If a film we assembled is indistinguishable from
the film a professional editor assembled, the edit is automatable.

```powershell
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

Five films have been through it, and **stage 1 passes exactly on all five** —
frame-for-frame, zero shifted frames, zero frozen filler, 100% angle agreement,
audio at 0.000 ms:

| project | film | shots / angles | angle mode | stage 1 | stage 2 |
|---|---|---|---|---|---|
| `a16z-altman` | 1:56 | 16 / 4 | frame | exact | 77.68% |
| `a16z-bornstein` | 0:59 | 6 / 3 | frame | exact | 78.77% |
| `a16z-agents` | 1:23 | 5 / 2 | frame | exact | **86.90%** |
| `a16z-sinofsky` | 1:45 | 7 / 2 | frame | exact | 73.27% |
| `up-interview-1` | **60:06** | 229 / 13 | **person** | exact | — |

The first is the worked example; the rest were run on a framework that had
never seen them, which is the only reason those columns mean anything.

`up-interview-1` is the scale test and the widest stretch of the machinery:
25 fps rather than 23.976, 13 hour-long tapes, 1.17 million encoded frames, a
229-segment filtergraph, and a shot list that only person mode could produce.
Its anchors behaved exactly as designed — one tape anchored at a 980× margin,
nine agreed independently at +0 frames, and three near-static angles correctly
self-reported as too still and took their placement from sound.
The spread — 73% to 87% — is the honest range, and each end has a cause:
`a16z-agents` has one framed speaker and an off-camera interjector, which a
speaker-follower handles almost perfectly; `a16z-sinofsky` is a single
106-second monologue, where the editor cut six times for rhythm alone and
nothing in the audio predicts any of it.

**Editing costs about half the film's runtime.** From raw tapes to finished
film — sync, decide, render — measured across the four: 0.46× to 0.57× realtime.
The decide step (speaker embeddings, CPU) is ~85% of it; the NVENC render is
roughly fifteen times faster than realtime.

### Real tapes are not on one grid, and nothing used to check

`angle-cut.py` trims every tape **by frame number** and concatenates the
pieces, so all of them must share one frame rate and one frame size.
Synthetic tapes do by construction. Real ones never do — a phone, a webcam and
a mirrorless are three rates and three sizes, and the phone is usually not even
on the rate it claims.

Nothing checked it. The rate and size were read off the **reference** tape and
applied to all of them, so a 60 fps webcam beside a 30 fps phone is addressed
at half speed on one of the two and the film is silently wrong. `angle-cut.py`
now refuses a mismatched set and names the offender; `conform-tapes.py` is what
fixes it.

```powershell
python scripts/conform-tapes.py --tapes a.mkv b.mp4 --outdir projects/<id>/tapes --id <id> --list
python scripts/conform-tapes.py --tapes a.mkv b.mp4 --outdir projects/<id>/tapes --id <id>
```

Three routes to a target rate, chosen by arithmetic and printed, never guessed:

| route | when | how |
|---|---|---|
| `regrid` | already at the target within `--rate-tol` (a phone claiming 30, delivering 30.03) | `setpts` by frame index; count asserted **unchanged** |
| `decimate` | an exact integer multiple (60 → 30) | `select` every k-th frame; count asserted to `ceil(n/k)` |
| `refuse` | anything else (50 → 30, 23.976 → 30) | resampling those invents or drops frames unevenly — a decision for a person |

The default target is the **lowest claimed rate**, not the lowest measured one,
and that distinction is load-bearing: measured rates are drift, and taking
drift as the target is how a clean 2:1 decimation stops looking like one.
Measured here — a webcam at 59.933 and a phone at 30.034. Against the phone's
*measured* 30.034 the ratio is 1.9952, which misses 2 by more than the
tolerance and refuses the whole tape; against a clean **30** both land, one by
regrid and one by decimate. Size is `scale`+`pad`, letterboxed and never
cropped: a tape is evidence, and a crop throws away picture the edit might
want while a pad is at least visible.

### Conform first, or a one-frame error has somewhere to hide

A file off the internet is usually a little variable — this one averaged
23.9765 fps against a nominal 24000/1001. So `--conform-only` rewrites it onto a
strict CFR grid **frame for frame**, with `setpts=N*1001/24000/TB` and
`-fps_mode passthrough`. Not the `fps` filter: that hits its target by
duplicating and dropping, which is the one thing this step exists to rule out.
The output frame count is asserted against the input, and the conformed
programme — not the download — is what the tapes are built from and what the
re-cut is scored against.

### Reading an edit back off a finished film

`shot-detect.py` makes three measurements in one decode pass:

| | |
|---|---|
| **cut** | a spike in frame-to-frame difference that is *also* a local maximum *and* far above the local median. The last two conditions separate a cut from a fade — a fade is a sustained moderate difference with no peak, and this clip ends on one |
| **angle** | shots cluster by their **median** fingerprint, not their mean. The speaker moves; the room behind them does not, and the median is the room. Complete linkage, so two angles never chain together through a shot that sits between them |
| **re-split** | a shot whose two halves have different medians was never one shot. Candidates are the *sub-threshold* peaks only, so a speaker standing up mid-shot — a real change, but a gradual one — cannot be mistaken for a cut |

**Angles are identified two ways, and the film picks which.** The frame
fingerprint reads the whole picture — in practice, the background behind the
speaker — and it is cheap and exact where cameras have visually different
backgrounds, which is all four a16z films (margin 4.7×). A studio that puts
every camera against the same black backdrop defeats it outright: two hour-long
Ukrainian interviews (`projects/up-interview-1`, `-2`) collapsed into 55 and 61
phantom angles, with within-angle distance *exceeding* between-angle (0.44×).
Three cheap rescues — a top-60% mask, contrast normalisation, a colour torso
patch with Haar face detection — were measured at 0.47×, 0.72× and 1.11×, all
rejected; Haar also missed one of the four people in five of five samples.

So `--angle-by person` identifies angles by **who is in frame** instead: YuNet
face detection plus SFace identity embeddings (both via the OpenCV already
installed; two small ONNX models under `models/face/`, curl commands in the
skill). Shots split by majority face count over sampled frames, and each family
got its rule the same way — by watching the previous rule fail on a real film:

- **One face**: cluster by identity, *average* linkage — pose stretches a
  person's own embeddings, and under complete linkage an outstretched arm and
  a thrown-back head each earned themselves a phantom camera. A single-shot
  "person" within SFace's published same-person bar (0.64) of a real person's
  centroid is that person mid-gesture and is absorbed. Calibration margin
  3.0× (same person ≤ 0.24, different people ≥ 0.72); the embeddings even
  corrected two hand-labelled shots.
- **Two-plus faces**: cluster by *which people* are in the shot — every face
  matched to the person centroids — then split by face layout only where the
  split is decisive. First tried frame fingerprints here, and the same black
  backdrop that broke the close-ups shattered one two-shot pairing into
  fifteen phantom angles. Faces too small to identify (under ~8.5% of frame
  width, i.e. everyone in a four-person wide) stay anonymous, because tiny-face
  identities are noise and split one wide camera six ways.
- **The `xtra` bin**: zero-face shots, plus any angle showing nobody from the
  *cast* — the people who hold ≥3% of the film between them. A camera in a
  shoot films the people in that shoot, so archive footage is an insert
  however often the editor returns to it. A Ukrainian culture show cut
  repeatedly to Queen and Joy Division music videos, vinyl-record animations
  and a picture-in-picture; each was about to become its own hour-long
  synthetic tape. Rarity was tried as the test first and dropped — it binned a
  legitimate wide the editor happened to use once, and rare is not the same as
  inserted. The bin sits outside the separation guard because its members are
  not supposed to look alike, or like anyone.

The separation guard for person mode is **centroid-based** — is every shot
closer to its own person than to any other — because pairwise distance fails
correct clusterings: absorbing a mid-gesture outlier is right, and pairwise
then reports that outlier's distance to its farthest team-mate as "within".
Face detections are cached under `temp/` per (file, params); iterating on
grouping logic cost a ten-minute hour-of-AV1 decode per attempt before that.
A single backdrop — or a green wall — is the *easy* case for all of this: the
less background there is, the more the frame is the person.

On the film that produced 55 phantom angles, person mode finds **13**: four
close-ups (their burned-in name-card shots correctly merged into their
cameras — impossible for frame sigs), two wide framings, six framings of the
two two-shot pairings (operated cameras genuinely reframe over an hour), and
one graphics angle. Every one is a real picture.

The default `--angle-by auto` runs frame first and switches to person only when
the separation guard fires, so the four a16z fixtures produce byte-identical
shot lists — and person mode run explicitly on `a16z-altman` finds the same 16
shots in the same 4-angle structure, two independent instruments agreeing on a
solved film. If **both** methods fail to separate, `shot-detect.py` still
refuses to write the shot list (unless `--force`) — the refusal is what stops
`split-cameras.py` from building one full-length tape per phantom angle.

`--list` sweeps the threshold instead of picking one. On the a16z clip the
answer is 15 cuts / 16 shots / 4 angles at **every** threshold from 0.030 to
0.120, which is a plateau rather than a lucky setting. It also prints the angle
separation: worst distance *within* an angle 0.0357, closest *between* two
angles 0.1692. A 4.7× margin is a decision; anything under 1× is a coin toss,
and it says so.

### What a synthetic tape looks like

`split-cameras.py` writes one tape per angle, each covering the **whole** shoot
the way a real camera does — not the handful of clips that angle contributed.

- **live** where the finished cut used this angle, the real frames.
- **frozen** everywhere else, its last live frame held, via
  `tpad=stop_mode=clone`. We do not have the footage a second camera shot while
  the editor was elsewhere, so the picture stops while the clock does not.
- **audio** the whole programme's sound on every tape, `adelay`ed by that
  camera's own start. Cameras fed from one recorder — and it is what gives
  `sync-audio.py` something to measure.
- **stagger** each tape starts and stops at its own moment, from a seeded
  generator, because nobody hits record on four cameras at once.

Freezing is deliberately *visibly* not real footage. Anything that scored the
edit by looking for **motion** would be reading the answer key, which is why
stage 2 is forbidden the picture entirely.

Frames, never seconds. The pads are frame counts and the audio delay is a
**sample** count: exact wherever 48 kHz divides the frame time (2002 a frame at
24000/1001, and every integer rate), rounded to the *nearest sample* where it
cannot (29.97: 1601.6 a frame) — at most half a sample, ten microseconds, and
it cannot accumulate because every boundary is computed from frame zero rather
than by summing deltas. An earlier version refused NTSC rates outright, which
was purity at the price of refusing half the videos on the internet.

### Sync, and the anchor that sync cannot give you

`sync-tracks.py` answers a different question and keeps its own shape — one
silent screen capture against one camera, correlating picture change against
sound. `sync-audio.py` is for N tapes that all carry the same programme audio,
so the sound is correlated against itself by FFT. On the a16z fixture it
recovered every stagger to the **exact frame** (+11, −2, −14), with a peak
z-score of 604 and a three-way residual of 0.125 ms.

Offsets are *relative*, though. Where programme frame zero sits on each tape is
a separate question, and `angle-cut.py`'s `anchor` settles it:

- `picture_start` — **measured**. ONE tape anchors the film from its picture:
  the one whose opening hold breaks most decisively, which in practice is a
  close-up. Every other tape is then placed by the audio offset, which is
  already exact to the frame. Watch the off-by-one: the held frame *is* the
  tape's first live frame repeated, so the first frame that *differs* is the
  second live one.
- a map of camera to frame — **declared**, the editor's in-point. A tape with
  footage running before the film starts has no motion onset to find.

**A wide angle cannot anchor itself, and this is why one tape anchors rather
than each.** Its people are small at analysis resolution and its live footage
barely moves, so a fixed motion threshold walks past the hold into near-still
live frames and reports the onset late — by +2, +30 and +6 frames on three
different films. Each tape whose own margin is clean still measures
independently and must agree to the frame; a tape too still to self-anchor says
so and reports its margin, so the weakness is visible rather than silent.

The cross-check is not decoration. It caught that late-onset bug three times
out of three before a single frame was encoded.

### Scoring it

`compare-videos.py` takes four measurements, because one number hides the
failure that matters:

| | |
|---|---|
| **ssim** | per frame, downscaled greyscale. Rules out gross corruption |
| **shift** | every frame scored against the reference frame *before*, *at* and *after* it, reporting which wins. **This is the measurement the test turns on** |
| **cuts** | both films read back through `shot-detect.py`, so it compares two recovered edits rather than an edit against a claim |
| **audio** | correlation offset, then the residual of the aligned waveforms |

The pass bar is on the worst join, the shift count and the frame count — all
exact — and SSIM is only asked to rule out corruption. Here is why, measured: a
deliberately broken render with **one camera one frame out** still scored a
median SSIM of 0.9992, against 0.9993 for the correct one. A global average
cannot see a one-frame join error, because 2795 of 2796 frames are still right.
The shift probe flagged 665 frames, starting at frame 932 — exactly where that
camera's first live span begins — each of them matching the reference's *next*
frame better than its own.

Run that negative control after changing anything: re-render with one anchor
moved by a frame and confirm the comparator fails. A harness that has never
failed has not been tested.

### Stage 2: choosing the cut from the sound alone

Stage 1 proves the machinery can replay an edit it was handed. `auto-switch.py`
has to *choose* one. It gets the tapes and nothing else — no shot list, no truth
sidecar, and **no picture**, because the frozen filler makes "which camera is
moving" the answer key.

```powershell
python scripts/auto-switch.py --manifest projects/<id>/anglecut-auto.json --list
python scripts/auto-switch.py --manifest projects/<id>/anglecut-auto.json --sweep `
                              --score projects/<id>/<id>.shots.json
python scripts/auto-switch.py --manifest projects/<id>/anglecut-auto.json
python scripts/angle-cut.py   --manifest projects/<id>/anglecut-auto.json --out <...>-autocut.mp4
```

1.5 s of audio every 0.5 s → a speaker vector per window (sherpa-onnx on the
already-installed ONNX runtime: no torch, no gated download) → average-linkage
agglomerative clustering to K people, K declared because how many were at the
table is a fact about the shoot. Each cluster is bound to a camera by **one hint
per person** — "at 0:45, the person talking is the one on cam2" — which is the
only human knowledge in the stage, and is what an editor has for free. Then the
grammar: be on the speaker, never cut faster than `min_shot`, arrive `lead`
frames early.

Sherpa's own clustering was tried first and merged two of the three speakers
into a single 33-second block. The embeddings were never the problem — measured
cosine distance is 0.59 within a speaker against 0.82 between — so the
clustering happens here instead. That is worth knowing before blaming a model.

**Results: 73–87% of the timeline on the same camera as the human editor**,
across four films (see the table above), three of which the framework had never
seen. Each score is computed twice by different routes — `auto-switch --score`
off the shot list and `compare-videos.py` off the rendered pixels — and they
agree to the second decimal.

Two structural limits explain most of the gap. The wide is nobody's close-up,
so a speaker-following rule can never predict a cut to it; on `a16z-altman`
that alone is 14.2% of the film, putting the ceiling near 85.8%. And a film
with one voice has no audio signal to cut on at all: `a16z-sinofsky` is a
106-second monologue where the editor cut six times purely for rhythm, and the
switcher correctly cut zero times — 73.27% is the honest floor of the method,
not a bug.

**It scales to an hour.** Clustering an hour of film means ~7200 windows, and
recomputing every pair from its members on every merge is upwards of 10^11
operations — it simply never returns. The merge now uses the Lance-Williams
update (a merged pair's distance to everyone else is the size-weighted mean of
the two rows it came from), and above 2000 windows it clusters an evenly spaced
sample and assigns the rest to the nearest centroid. Evenly, not randomly: a
voice that only speaks in the last ten minutes must still be represented. 7200
windows now cluster in about five seconds, and all four a16z films reproduce
their previous scores to the second decimal.

**Boundaries come from the segments, identity from the windows.** Windows vote
the voice centroids into existence; each speech segment is then embedded whole,
matched to the nearest centroid, and painted over the track with its own exact
edges. A 1.5 s window cannot resolve a 1.1 s interjection — it embeds as a
blend and lands on whichever voice dominates, which cost 20 seconds of wrong
camera on `a16z-bornstein` before painting was added (+4.8 points there, +1.4
on `a16z-agents`). The segmentation model's own speaker *labels* are never
used: its clustering merged two of three speakers on `a16z-altman`. Good
boundaries, bad identity — so take only the boundaries.

Painting is the default and `a16z-altman` pins it off, because there it loses
4.2 points: two of its male voices are close enough that whole-segment
embeddings land on the wrong man, while many independent window votes do not.
A default that wins on two unseen films and loses on one is worth shipping with
its counter-example committed next to it.

The sweep is where a plausible idea died. "Break a long monologue with the
wide" sounds obviously right, and it **loses**: agreement falls from 77.7% to
64.6%. It does place more cuts near the human's cuts (8 of 15 within a second,
against 4), which is the honest shape of the trade — it cuts at the right
*times* to the wrong *camera*. `min_shot` changed nothing at all on this film,
because the speaker runs are all longer than three seconds anyway.

**Knobs swept against one film are fitted to it.** The number that means
anything comes from the next film, which is what the framework is for. And note
`compare-videos.py`'s PASS/FAIL is the stage-1 bar — frame-exactness — so a
stage-2 cut *should* fail it; the number to read there is the agreement.

### Finishing a multicam film: labels and cards in the same pass

`angle-cut.py` reads `name_labels` and `image_overlays` and means exactly what
`screencast-cut.py` means by them — a lower third naming who is on screen, a
card or a logo over the film. They are spliced onto the tail of the cut, so
labelling a multicam film is **not** a re-encode of it:

```json
"name_labels":    [{"name": "УТ-2", "title": "fpv #33", "at": 3.0, "dur": 6.0}],
"image_overlays": [{"card": "projects/<id>/cards/outro.json", "at": -9.0,
                    "layout": {"corner": "centre", "width_frac": 0.52},
                    "in": {"type": "wipe", "dur": 1.1}, "background": {}}]
```

Order in the graph is labels → overlays → `--debug` commentary, so an end card
sits over a lower third and the commentary over both. `at` is **film time** —
after the switching — and a negative `at` on an overlay counts back from the
end, resolved once the runtime is known and asserted against it, because a
graphic past the end fails *silently*. `--list` prints both with their resolved
windows, which prices a placement without an encode.

Give a finished render its own manifest and its own output name. Burning
graphics changes pixels, so a labelled stage-1 cut is no longer frame-identical
to the programme and would fail its own comparison — the same reason `--debug`
writes a separate file.

### Debug notes: making the film explain itself

A finished render is silent about its own reasoning. `--debug` burns a running
commentary into the bottom-left corner — which shot this is, which tape and
which frames of it, what the anchor and the sync said, and **why** this camera:

```
ANGLE-CUT  stage 2 (chosen from sound)  plan: a16z-altman.autoplan.json
seg 02/08   cam2   0:21.27-0:53.26   767 frames
why: voice 1 is speaking -> cam2
tape cam2.mp4  f608-1375   anchor +98   sync +11.00 fr
!! cam2 is HELD for 10.5s of this shot -- no footage exists for this angle here
```

```powershell
python scripts/angle-cut.py --manifest projects/<id>/anglecut.json --debug
python scripts/debug-notes.py --notes n.json --out n.ass --frame 40 --video f.mp4
```

It is an ASS subtitle track, not a stack of overlays: libass already does
per-note timing and corner placement, so N notes cost **one** filter instead of
N image inputs, and it rides inside the existing NVENC pass. Style lives in
`config/overlays/debug-notes.json`. `debug-notes.py --frame T` composites onto a
real frame and writes a PNG, which is how to check placement before an encode.

A debug render is a **separate artifact, never a replacement**: burning text
changes pixels, so a debug copy of a stage-1 cut is no longer frame-identical to
the programme and would fail its own comparison. `--debug` writes
`<id>-anglecut-debug.mp4` and leaves the clean render alone.

That last warning line is the one that earns its place — see below.

### Frozen filler, and why stage-2 renders look broken

A synthetic tape only carries real frames where the original editor used that
angle. So whenever a stage-2 switcher picks a *different* camera, it is asking
for footage that does not exist anywhere, and the tape hands back a held frame.
The picture stops.

That is not a rendering bug and not a bad source: it is the fixture, and it is
unavoidable. It is also the **visible form of the disagreement**. On the a16z
clip the three numbers are the same number:

| | |
|---|---|
| timeline on a different camera than the human | 22.32% |
| frames scoring below 0.90 SSIM | 624 (22.3%) |
| frames of frozen filler | 624 (22.3%) |

So read a stage-2 render as a diagnostic, not a film. `compare-videos.py`
reports the frozen frames as a first-class number, counting only runs the
*reference* does not also have — a talking head sitting still belongs to both
films and is the source's own stillness, not the cut's.

**Calibrate detectors against stage 1.** It is the free ground truth in this
repo: its plan is the human's own edit, so every frame provably has real
footage, and any frozen run reported there is a false positive. That is how
both thresholds here were set rather than guessed — 0.0015 over half a second
called 12.8% of a pixel-identical render frozen; 0.0005 over a second calls
0.0%, while still catching all 624 in stage 2.

### The wide shot, and a hypothesis that half survived

The wide is nobody's close-up, so a speaker-following rule never cuts to it —
0% of 396 frames on this film. The obvious question is whether it is really
unpredictable, and the answer turns out to be measurable: the editor cuts wide
when several people talk at once.

That much is confirmed. The two wide shots are the two densest patches of
crosstalk in the film — **11.7%** and **18.0%** of their length with more than
one voice active — against a median of **0.0%** and a maximum of 6.9% across
every close-up longer than three seconds. Six of nine short interjections land
within 0.31 s of a human cut, one of them exact to the frame.

Detecting it needs the right instrument. Windowed speaker embeddings cannot:
a window holding a speaker plus somebody's "yeah" embeds as the speaker, and
measured speaker churn inside the wide shots was 0.015 changes per window —
*identical* to outside them. The segmentation model is multi-label, so two of
its segments overlapping in time is overlapping speech, and that finds it.

Acting on it is where it stops. `wide_overlap_pct` implements the rule and is
**off by default**: crosstalk is 4.5% of the film and the wide is 14.2%, so
overlap is close to necessary and nowhere near sufficient. Swept over 30
settings the best scored 78.79% against 77.68% for plain speaker-following —
one point, fitted to a film containing two wide shots, which is not a result.
A different setting matched far more of the human's cut *timing* (10 of 15
within a second, against 4) at slightly worse camera agreement, but it also
made 22 cuts against the human's 15 — which is why cut timing is now scored in
**both directions** (`cuts_within_1s` for recall of their cuts,
`my_cuts_near_theirs` for precision of ours; quote the pair, never either
alone). Knowing *why* an editor did something is not the same as being able to
predict it, and the next film is what settles this one.

### A channel that does not cut on the speaker at all

Everything above assumes the editor follows the voice. The УТ-2 podcast
(`yt2-fpv33-seg`, a Ukrainian three-camera show) does not, and it is worth
writing down because it is probably the common case rather than the exception.

Read its cut back and the grammar is unmistakable. 101 shots in 19.5 minutes,
mean **11.6 s**, median 11.0, and a transition matrix with no ambiguity in it:

| from | to the wide | to the other close-up |
|---|---|---|
| close-up A | 97% | 3% |
| close-up B | 92% | 8% |

A close-up is *never* followed by another close-up. The wide holds **52.4%** of
the runtime and the faces are the accents — the exact inverse of a
speaker-following grammar. Measured against their edit:

| grammar | fitted segment | held-out segment |
|---|---|---|
| sit on the wide and never cut | 52.4% | 44.8% |
| speaker-following, third man merged into a host | 45.0% | 49.5% |
| speaker-following, **all three voices separated** | 53.6% | **63.9%** |
| alternating close-up/wide (`wide_between`) | 58.1% | 51.0% |

Two lessons, and the second one is bigger than the first.

`alternating()` implements the metronome, snapping each beat to a gap between
speech segments (`snap_s`). Fitted against the first segment it won by 14
points — and **lost 14** on a different segment of the same film. That is what
fitting looks like, and it is why the second segment exists: `yt2-fpv33-val`
builds no tapes and renders nothing, it points three camera entries at the
programme's own soundtrack and scores a plan. Fifteen minutes, and it turned a
result into a non-result.

The bigger one: **a third man sat behind the camera**, and until he was given a
voice of his own the switcher spent his speech on a host's close-up. Separating
him is worth **+14 points on unseen footage** — far more than any grammar — and
it needed no tuning at all, only counting the people in the room. See
`cluster_people()` below.

So `wide_between` ships **off**, like `wide_overlap_pct`, with its evidence
written down. What the exercise did establish is worth as much as a win:

- On this channel a close-up does **not** mean that person is talking — they
  cut to listening faces. A speaker hint picked from a long close-up landed on
  the wrong voice, which on a speaker-following show is a safe way to choose
  one. Read `--list`'s own voice track instead.
- Speaker-following beats sitting on the wide by 19 points on unseen footage
  once every voice is separated, and nothing yet beats speaker-following.
- **Agreement with one human's edit is a harsh yardstick.** Two competent
  editors cutting the same tapes would not agree 100% either. Quote it with
  the always-wide baseline beside it, or it reads as a mark out of 100.

### The comparator cannot score a stage-2 cut

`compare-videos.py` prints a timeline agreement, and it was tempting to read it
as an independent check on `auto-switch --score`. It is not one on a stage-2
render. The comparator builds its angle map by **detecting** angles in both
films, and a stage-2 render is roughly half frozen — on this podcast it found
seven angles in a three-camera cut, mapped `cam2`→`cam3` and `cam3`→`cam2`, and
reported **44.76%** where the plan it rendered actually scores **53.57%**
name-for-name against the reference shot list (which is what `auto-switch
--score` computes, and it agreed to two decimal places).

On a **stage-1** render nothing is frozen, the map is sound, and the cross-check
is worth having. On stage 2, quote the scorer and use the comparator only for
what it measures directly: shifted frames, frozen frames, SSIM, audio offset.

### K counts people, not clusters

Declaring `K` — hints plus `off_camera_speakers` — says how many were at the
shoot. Agglomerative clustering does not spend its splits on people, though: it
peels outliers first, a cough or a clipped word or a bar of music, so asking for
exactly `K` groups hands speaker slots to noise while two real speakers stay
fused. And a fused pair is the expensive kind of wrong — the film sits on the
wrong face for as long as that person talks.

| | asked for K | what came back |
|---|---|---|
| fitted segment | 3 | 84.1 / 15.3 / 0.6 — the third man inside the 84 |
| | 4 | 47.1 / 37.5 / 14.9 / 0.4 — split, correct |
| held-out segment | 4 | 82.4 / 17.5 / 0.1 / 0.1 — still fused |
| | 8 | 42.4 / 39.6 / 16.9 + five specks — split, correct |

One number could not fix both. `cluster_people()` raises `k` until `K` groups
clear 2% of the windows and lets the specks keep their own labels — an unmapped
voice already falls back to the wide, which is where an editor puts a sound with
no face. The two segments now settle at k=4 and k=8 from the same honest `K=3`.

### The speaker model has a hard length ceiling

TitaNet's ONNX export builds its mask for **12288 feature frames — 122.88 s** at
the model's 10 ms hop, and one frame more raises

```
Attempting to broadcast an axis by a dimension other than 1. 12288 by 12298
```

from inside the encoder. Measured here: 122.8 s embeds, 123.0 s throws. Nothing
documents it and it is not a truncation — the run dies. `embed_span()` therefore
embeds a long span in 60-second pieces and averages the unit vectors, which is
identical to the old behaviour under the cap and keeps the whole span
represented. A 132-second answer with no pause the segmentation model would
split on is what found it; four earlier films never held the floor that long.

### The sweep grid is manifest data

`--sweep` walks `DEFAULT_SWEEP` unless the manifest names its own `sweep`, one
list per grammar knob; a knob with a single value is held fixed and its column
is not printed. This exists because the axis a channel's style lives on is not
knowable in advance — the a16z films wanted `min_shot_s` and `wide_overlap_pct`,
УТ-2 wanted `wide_after_s`, and pricing a new axis must never mean editing the
script.

### The arithmetic has its own test

The round trip is frame arithmetic wearing a video costume, and every part of it
is otherwise reachable only through a GPU render and a five-minute comparison —
which is how the anchor's off-by-one got written in the first place.

```powershell
python scripts/check-multicam.py
```

Costs nothing, touches no file: tape layouts tile gaplessly under every pad,
sample-per-frame arithmetic is exact, the anchor's off-by-one holds for four
known head pads, correlation recovers known lags, SSIM of a frame against
itself is 1, the generated filtergraph trims from the right tape frames, the
audio is one `atrim` and never a concat, and a fade is not mistaken for a cut.
Run it after touching any of the five scripts.

## A lower-third name label

A dark rounded card with a name over a title, and a mint rounded rectangle
sitting nine pixels down-right of it so an accent sliver shows along the bottom
and right edges. It fades up, holds, and fades out.

```powershell
# eyeball the card on its own
python scripts/name-label.py --card-only --name "Jane Doe" --title "CEO, Example"

# prove where it lands on THIS footage -- one still, no encode
python scripts/name-label.py --video outputs/film.mp4 --frame 4.0 `
    --name "Jane Doe" --title "CEO, Example"

# burn it into an existing file
python scripts/name-label.py --video outputs/film.mp4 `
    --name "Jane Doe" --title "CEO, Example" --at 2.0 --dur 5.5
```

Better, put it in the screencast manifest and let `screencast-cut.py` apply it
**while cutting** — the card goes on after the concat, inside the film's
existing NVENC pass, so a labelled film is not a re-encode of an unlabelled one:

```json
"name_labels": [
  {"name": "Oleksandr Gamaniuk", "title": "CEO, Instafill.ai", "at": 2.0, "dur": 5.5}
]
```

`at` is **film time** — the time on the finished scrubber. The overlay is
applied after the cut, so the pauses the cut removed are already off the clock.

### Where the numbers came from

Every default in `config/labels/lower-third.json` was measured, not chosen. The
reference is [this clip](https://x.com/RiskReversal/status/2092685768833605757),
whose label is up between t=4.7 and t=10.4. Reading it off a single frame is
guesswork, because the card sits over a moving shot; so the frame at t=9.0 was
diffed against t=10.6 — the label's **own fade-out** — which isolates exactly
the pixels the label owns and nothing else. Those pixels were then classified
into card, accent and text by colour:

| | measured (720p) | preset (1080p) |
|---|---|---|
| card rect | x 458–897, y 468–555 | 440×88 → scaled ×1.5 |
| accent sliver | 6 px on the right and bottom | `offset_*_px: 9` |
| accent colour | rgb(19, 186, 130) | `#13BA82` |
| name cap height | 34 px | 51 |
| title cap height | 19 px | 28 |
| fade up ends / out starts | 5.2 s / 10.3 s | 0.4 s / 0.35 s |

The accent turned out not to be a stroke along two edges but a **whole rounded
rectangle offset behind the card** — which is why the sliver has a rounded
corner at bottom-right and tapers out at top-right and bottom-left. Drawing it
as a two-sided stroke gets the colour right and the corners wrong.

The reference sets its type in a humanist sans; Montserrat is substituted
because the captions and the handle badge already use it, so a labelled film
reads as one channel rather than two.

### Style

`config/labels/lower-third.json`, authored on a 1920×1080 canvas and scaled to
whatever frame it lands on. `accent.colour` is the single key to change to
rebrand it. `layout.corner` takes `bottom-left` (the default), `bottom-right`,
`top-left`, `top-right`, or anything else for centred; `layout.max_width_px`
shrinks an over-long name to fit and says so on stderr rather than letting it
run off the frame.

Type is sized by **cap height** rather than nominal size, for the same reason
the caption presets are: nominal size includes ascent and descent, which differ
between weights, so sizing by it would set the two lines at a ratio nobody chose.

`fonts/Montserrat-Medium.ttf` carries the title line and was instanced from
`temp/fontsrc/Montserrat-var.ttf` at `wght=500` with `fontTools.varLib.instancer`.
It is covered by the same `fonts/OFL.txt` as the bold.

## An image overlay, and end cards

Put a picture on top of the film — a logo, an end card, a chart, a screenshot —
with an entrance animation, real transparency, and optionally a **treatment** on
the footage underneath it.

The grammar is lifted from the end card at 1:26:25 of
[this episode](https://x.com/patrick_oshag/status/1985693514357756286), read
frame by frame: over about a second and a half the wide shot desaturates, blurs
and dims **while it keeps playing**, and the show's logo reveals left to right
behind a hard edge. Two animations, one moment — and the reason it looks
expensive is that the footage never freezes and never cuts.

The image comes from one of three places, and nothing downstream can tell which:

| source | when |
|---|---|
| `image` | a file that already exists — a supplied logo, a screenshot, a chart |
| `card` | a **spec**: template + brand + words. The designed route — see below |
| `html` | a page written by hand, for a design no template covers |

```powershell
# a file you already have
python scripts/image-overlay.py --video outputs/film.mp4 --image assets/logo.png `
    --at -12 --background --frame 440        # free: one composited still

# a designed card -- no HTML written by hand
python scripts/make-card.py --list           # templates, brands, line styles
python scripts/image-overlay.py --video outputs/film.mp4 `
    --card projects/<id>/cards/outro.json --at -12 --background --frame 440

# a hand-written page
python scripts/html-to-image.py --check      # which browser will render it
python scripts/html-to-image.py --html projects/<id>/assets/end-card.html `
    --out projects/<id>/temp/end-card.png
```

Better, put it in the manifest and let the pipeline apply it inside the film's
existing NVENC pass, so an end card is not a re-encode of the film:

```json
"overlay_preset": "config/overlays/end-card.json",
"image_overlays": [
  {
    "html": "projects/<id>/assets/end-card.html",
    "at": -11.0,
    "layout": {"corner": "centre", "width_frac": 0.56},
    "in": {"type": "wipe", "dur": 1.1, "direction": "left", "feather_px": 18},
    "out": {"type": "none"},
    "background": {}
  }
]
```

Both `screencast-cut.py` and `cut-clips.py` read it. Overlays composite **after**
the name labels, so a card sits on top of a lower third rather than under it.

| key | |
|---|---|
| `image` / `card` / `html` | the source, exactly one of them; anything generated is cached against the mtime of what it was generated from |
| `at` | when it appears. **Negative counts back from the end** — an end card written as `-11` follows the cut instead of being stranded at a timecode a re-cut moved |
| `dur` | how long it stays; omitted means to the end |
| `layout` | `corner` (as the name label) plus `width_frac`, which sizes the image against the frame so one card fits a 1080p film and a 9:16 short |
| `in` / `out` | `{"type": "wipe" \| "fade" \| "slide" \| "none", "dur":, "direction":, "feather_px":}` |
| `background` | opt-in treatment of the film underneath; `{}` takes the preset's defaults |

### Why it animates the way it does

`fade` is a `fade` on the image's alpha and `slide` is a clipped linear
expression for the overlay's x/y — both the name label's idiom. **`wipe` is a
`geq`** that multiplies the image's own alpha by a ramp across X or Y, so a logo
with transparent gaps stays transparent: it reveals the picture rather than
painting a rectangle over it. `geq` is a per-pixel interpreter, so it is
`enable`-gated to the wipe window itself — a second, at logo size — and the rest
of the film pays nothing.

The treatment is a `split`: one branch untouched, the other desaturated, blurred
and dimmed, then cross-faded over the first on its alpha. Fading a constant
fully-treated layer looks identical to ramping the blur and needs no `sendcmd`.
Those filters are `enable`-gated too, or a gaussian blur would run over ten
minutes of film to be seen for eight seconds of it.

Animated `crop` width is **not** an option for a wipe: crop's `w`/`h` are
evaluated once when the filter is configured and only `x`/`y` re-evaluate per
frame — the same trap noted for the vertical pan.

### Designing a card

`make-card.py` is the design half: it turns a spec into a page, and the page
into a transparent PNG. Nothing about a design is in the script —

- the **shape** is a template under `config/cards/templates/`
- the **look** is a brand under `config/cards/brands/`
- the **words** are the spec

so swapping the brand makes the same card another company's, and swapping the
template makes the same brand another kind of card.

```json
{
  "template": "stacked-blocks",
  "brand": "mint",
  "lines": [
    {"style": "kicker", "text": "ВІДЕО ЗІБРАНЕ ТУЛІНГОМ"},
    {"style": "hero",   "text": "INSTAFILL<span class='em'>.AI</span>"},
    {"style": "accent", "text": "@instafill_ai"}
  ]
}
```

```powershell
python scripts/make-card.py --list                       # what exists
python scripts/make-card.py --spec projects/<id>/cards/outro.json --png
python scripts/make-card.py --template stat --brand mono `
    --text "hero:49s" --text "body:OF DEAD AIR REMOVED" --out temp/c.html --png
```

| template | |
|---|---|
| `stacked-blocks` | each line its own filled slab. **The one built for a wipe** — the reveal edge crosses type and fill together |
| `centred-lockup` | one panel, centred lines, accent rule. Calmer; pairs with a fade |
| `corner-tag` | a small pill for a persistent stamp rather than a moment |
| `quote` | a pull quote with an accent bar; the last line becomes the attribution |
| `stat` | one very large figure over a label |

Line styles are `kicker`, `hero`, `accent`, `body`, `ghost`; any line may
override `size_px`, `fill`, `colour` or `tracking_px` without the template
growing a branch. `text` is raw HTML, so `<span class="em">` picks up the
brand's accent inside a word.

A brand is only tokens — `ink`, `paper`, `accent`, `accent_ink`, `muted`, two
font paths, `radius_px`, `tracking_px`. Copy `config/cards/brands/mono.json`,
change the colours, and every template draws that company's card.

Templates use a very small mustache (`{{x}}`, `{{{x}}}` raw, `{{#x}}…{{/x}}`
for a list or flag, `{{^x}}…{{/x}}` for its absence). That is deliberately not
a real template language: a card that needs logic wants a new template.

### An animated checklist end screen: `checklist-card.py`

A full-frame card for the end of a demo. The headline rises in, then each line's box
pops, the text slides in beside it, and a tick draws itself into the box, one
line after another. The call to action comes last. It is drawn by Pillow from
`t`, so a `--png T` still is exactly the frame the render will contain.

```powershell
python scripts/checklist-card.py --spec projects/<id>/cards/checklist.json --style config/cards/checklist/window.json --list
python scripts/checklist-card.py --spec ... --style ... --png          # final state
python scripts/checklist-card.py --spec ... --style ... --sheet        # a strip across the animation
```

The words are the spec (`headline`, `items`, `cta`). The look and the timing
are the style: `window` is a white window on the recorder's lavender, `plain`
is type straight on the backdrop, and `chips` has dark lines in the counter
card's colour. Put it in a film as an `edl-cut.py` entry,
`{"card": <spec>, "style": <style>}`. It is rendered once and cached, then
plays as a source. Draw shapes on their own layer: `ImageDraw` on an RGBA
image **replaces** pixels rather than blending, and a "clear" fill wrote an
opaque green box before its tick was due.

For captions on a Cursorful-framed film, `band-light` and
`band-dark` set one line low, in the lavender band under the window
(bottom margin 44 of the 140 px band), so a caption never covers the app. The
dark one uses the counter card's colour and radius.

### Writing the page by hand

Two rules, both enforced rather than assumed:

- **Nothing may paint a background.** `--default-background-color=00000000` is
  what makes the browser composite onto nothing, but `body { background: #fff }`
  beats it every time, so the alpha channel is checked after the shot and a
  fully opaque PNG **fails with the reason** instead of becoming a white slab on
  the film.
- **The artwork is the only ink.** The PNG is cropped to its own alpha bbox, and
  that crop is what `corner` and `width_frac` then size and place. Use the
  alpha channel's bbox, not the image's — `Image.getbbox()` counts a
  coloured-but-transparent pixel and keeps the margin it is trying to remove.

`projects/<id>/assets/` holds the page (authored, committed — it is the editable
control); the rendered PNG goes to `projects/<id>/temp/`, gitignored, because
browser output is not byte-deterministic and regenerates in seconds.

Load repo fonts with a relative `@font-face` `src` so a card matches the
captions and the lower third — `projects/claude-demo/assets/end-card.html` is
the worked example.

> `msedge --version` on Windows does **not** print a version — it hands the
> argument to the running instance, opens a window and exits 0. `--check` reads
> the version-numbered folder Chromium installs beside its exe instead, so a
> free check stays free.

## Handing an edit to DaVinci Resolve

A finished render is a flat clip: somebody who wants to *change* the edit needs
the decisions, not the pixels. `resolve-export.py` writes those decisions as an
interchange file Resolve opens — in the **free edition**, with no scripting
permission and no licence.

```powershell
# what would be exported, what each format drops, and nothing written
python scripts/resolve-export.py --manifest projects/<id>/tighten.json --list

# the timeline, the EDL and the subtitles
python scripts/resolve-export.py --manifest projects/<id>/tighten.json --format all

# one format, somewhere else
python scripts/resolve-export.py --manifest projects/<id>/screencast.json `
    --format otio --outdir projects/<id>/handover
```

In Resolve: Media Pool right-click → Timelines → Import → OpenTimelineIO (or
AAF/EDL/XML), and File → Import → Subtitle for the `.srt`.

The input is the keep-list the cutter already writes — `<manifest>.cuts.json`
from `tighten-cut.py --plan`, `<id>.cuts.json` from `screencast-cut.py` — plus
the manifest, for the media paths, the bookends and the windows that become
markers. Both keep-list dialects are read; nothing else needs to know which
cutter ran.

### What travels, and what does not

| | |
|---|---|
| `otio` | leads. Two video tracks, an audio track, per-clip media paths, markers with their notes. Plain JSON against a published schema, written by hand so nothing new lands in `requirements.txt` |
| `edl` | the universal fallback. One video track, no paths (Resolve conforms by reel and timecode), no markers |
| `fcpxml` | FCP7 XML. Carries paths like `otio`, but **every media reference needs a duration**, so it is the one format that cannot be written without reading the sources — it refuses by name rather than writing a file Resolve rejects |
| `srt` | the words, remapped onto film time from the same transcript the caption builder reads |

**Cut decisions travel; pixels do not.** The PiP transform, the crop window, the
caption card, the redaction blurs and the loudnorm are renders, and a render is
what Resolve would import as a flat clip anyway. `--list` prints that list
rather than hiding it — run it before promising anybody an editable file.

The timeline is laid out as the film reads: **V1 is the picture** (screen where
the cut says `pip`, camera where it says `full`), **V2 is what sits over it**
(the PiP, or a bookend's b-roll), **A1 is the sound**. So V1 alone is already a
watchable rough cut, and the only thing missing from V2 is the transform.

Every editorial decision the repo already records rides along as a **marker**:
each named removal with the reason the manifest gave for it, each name label,
each image overlay at the place it was burned. The reasoning arrives with the
cut instead of staying behind in a manifest nobody else can read.

### Five traps, four of them measured

- **A keep-list is not the film.** On `claude-demo` the keeps run 427.867s
  against a 450.367s render: the 22.5s difference is the opening bookend, which
  lives in the manifest. The exporter builds bookends as clips and **refuses**
  when the timeline still under-runs the keep-list's own stated runtime;
  `--skip-bookends` exports the body alone and says so.
- **An EDL does not state its frame rate.** It travels out of band, so the
  import dialog has to be told. At 29.97 and 59.94 the timecode must also be
  **drop-frame** (`;` and `FCM: DROP FRAME`) or it drifts ~3.6s an hour.
- **CMX3600 reel names are 8 characters.** `IMG_2695.MOV` becomes `IMG2695`.
  That is the format, not a bug — it is why `otio` leads.
- **Resolve has no ASS importer.** It reads SRT, VTT, TTML and XML, and draws
  its own subtitle: the card, the outline and the per-word highlight do not
  travel. The SRT grouping in `config/resolve/export.json` is therefore tuned
  for reading, not for burning — a 3-word karaoke card is right burned in and
  unreadable as a Resolve subtitle.
- **Speed changes are half-portable.** OTIO carries a `LinearTimeWarp`; the
  FCP7 XML adapter drops it silently (measured). Whether Resolve honours the
  OTIO one is untested here — nothing in this repo has opened Resolve.

Styling and defaults are `config/resolve/export.json`: which formats `--format
all` writes, the SRT grouping, the marker colours. Per-video decisions stay in
the project's own manifest, as everywhere else.

After touching `resolve-export.py`, run `python scripts/check-resolve.py` — 56
checks over the film-time model, the bookend guard, the OTIO schema, EDL record
continuity and drop-frame timecode, the FCP7 XML refusal and the SRT remap. No
Resolve, no media, no encode, about a second.

**What is deliberately not built:** writing Resolve's own project files. A
`.drp` is a plain ZIP of UTF-8 XML whose clip effects are hex-wrapped structures
with no published schema — editable enough to *rescue* a crashing project, not
enough to author one. The evidence, the field-by-field breakdown and the
Studio-only scripting/MCP situation are in
[`docs/davinci-resolve.md`](davinci-resolve.md).

## Connecting a YouTube channel

Everything that publishes -- `yt-upload.py`, `yt-set-chapters.py`,
`yt-audit-chapters.py` -- rides one `youtube.force-ssl` grant. Creating that
grant used to be a side effect of the first real command, which is a bad place
to discover that Google's chooser handed you a personal account instead of the
brand account that owns the videos: the fix is a re-consent, and you find out
mid-publish. `yt-connect.py` is that step on its own.

```powershell
python scripts/yt-connect.py --check                        # free: am I connected, and as whom?
python scripts/yt-connect.py --channel @yourhandle        # connect, asserting the channel
python scripts/yt-connect.py --channel @yourhandle --reauth --no-browser   # the brand-account route
```

Once per machine, before the first run:

1. Google Cloud Console -> any project -> **enable "YouTube Data API v3"**.
2. **OAuth consent screen**: User type External; add the channel's Google
   account as a Test user. Then **press "Publish app"** -- while the screen is
   in *Testing*, Google expires every refresh token after **seven days**, and
   publishing then fails weekly with `invalid_grant`. The unverified-app
   warning that replaces it is about other people's data; this grant only ever
   touches your own channel.
3. **Credentials -> OAuth client ID -> Desktop app**, download the JSON.
4. Save it as `.yt-oauth/client_secret.json` (gitignored).
5. Run `--channel`. A browser opens: pick the **brand account** that owns the
   channel, not the personal login it sits under.

### The brand-account trap

Measured on a brand-account channel, 2026-09-23, at a cost of about an hour. A channel is
usually a **brand account** that a login merely manages, and OAuth authenticates
the **login** -- so `channels.list(mine=True)` returns the login's own channel
(on that run: the operator's personal channel, 5 videos) rather than the one you
meant (the brand account's channel, 46 videos). The
brand account has to be picked at Google's chooser, and **two settings suppress
that chooser entirely**:

- **An `Internal` consent screen.** A brand account is not an organisation
  account, so Google does not merely hide it -- picking it fails outright with
  `Error 403: org_internal`. The audience must be **External**. For a Workspace
  login `Internal` is the tempting choice, because it needs no test users and
  has no token expiry; it cannot work here.
- **A browser that is already signed in.** Google reuses the session, picks the
  login's channel silently and completes the whole flow without rendering a
  chooser -- `prompt=consent` does not help, because it re-asks for *scopes*,
  not for *identity*. Revoke the app at `myaccount.google.com/connections`, then
  use **`--no-browser`** and paste the URL into a **private window**, where
  there is no session to reuse. That is what finally worked.

`External` + `Testing` costs a re-consent every seven days. Moving to
`In production` needs an app home page and a privacy policy URL on the Branding
page (the company's site and its privacy page for this
channel), plus domain verification -- worth doing once, but not a blocker: the
weekly symptom is a refresh that fails, and `--check` names it.

The grant is filed per channel (`.yt-oauth/token-<handle>.json`), so a second
channel does not burn the first one's consent. A grant that comes back for the
wrong channel is **deleted rather than filed** -- keeping it would make every
later run confidently wrong. The channel is asserted by handle and reported by
**id**, because an owner can rename a handle and cannot change an id; the id is
what belongs in a project file.

## A thumbnail in the channel's style: `make-thumbnail.py`

```powershell
python scripts/make-thumbnail.py --spec projects/<id>/thumbnail.json --list   # layout, shrink warnings
python scripts/make-thumbnail.py --spec projects/<id>/thumbnail.json          # 1280x720 PNG, 2 MB checked
python scripts/yt-upload.py <mp4> ... --thumbnail projects/<id>/thumbnail.png
```

The grammar was read off the channel's six latest public uploads: a dark purple
field, an Anton headline with one phrase on a yellow slab, the form tilted on
the right with a shadow, a round yellow time badge, a yellow caption strip, and
the logo top-left, its lettering re-inked white. The spec holds the words, the
frame grab plus crop, and the colours. Lines are spaced by ink, not by font
metrics: Anton's ascent is much taller than its capitals, and metric spacing
ran the headline off the frame. `html-to-image.py` is not used because it
refuses opaque pages. `yt-upload.py --thumbnail` sets the image after the
upload. A failure there (an unverified channel) is printed and does not undo
the upload.

## Thumbnail options: four moments of the film, made like YouTube's (`thumb-options.py`, `_thumb.py`)

kitcut.ai's "Publish to YouTube" offers four thumbnails, and the person picks one. Each is **a
moment of the film itself**, made the way YouTube thumbnails are: the film's own titles and labels
left out of the frame, its subject pushed in large on one side, and at most four big words on the
other -- the first option the video's main message -- in the film's title type and outline, with
its logo on options 1 and 3. No stock art, no generated imagery.
The studio makes them (`studio/thumbs.py`, see `studio/README.md`); the machinery is
`scripts/_thumb.py`, and this CLI runs it on any finished sketch film:

```powershell
python scripts/thumb-options.py --film <film dir> --moments                 # the labelled moments sheet only
python scripts/thumb-options.py --film <film dir> --concepts c.json --list  # frames, layouts, every check; no JPEGs
python scripts/thumb-options.py --film <film dir> --concepts c.json --title "..." [--ocr] [--logo all|none]
python scripts/thumb-options.py --film <film dir> --auto                    # the baseline: frames at 25/50/75%, no words
python studio/ytdraft.py --film <film dir> --thumbs                         # Claude's own concepts, then the options
python scripts/check-thumbnail.py                                           # the rules, plus the example film drawn
python studio/test_thumbs.py                                                # end to end on the example film
```

A concept is `{"at": s, "words": "Can't *sleep*?", "layout": "headline|card|panel",
"place": "left|right|top|bottom"}` -- the writer gives headline, card, panel, headline (an older
draft's `slab` is read as `card`; its `still` takes the free layout and is asked for words; the
still is now only the last fallback); one word may be starred for the film's accent colour. Output: `thumb-N.jpg`
(1920x1080, well under YouTube's 2 MB), `sheet.jpg` (side by side) and `feed.jpg` (at YouTube's
360/246/168-px sizes, dark and light).

**The film draws its own thumbnail.** A thumbnail has to look like the film it sells -- an
Instafill film's thumbnail in Instafill's serif, amber and white cards, a crayon film's in its
hand lettering on its paper. So nothing is laid over the picture from outside: the words, cards,
panels and logo are drawn by the film's own engine, in the film's own type and palette, by
`sketch/thumb.js`, which runs ahead of the film's code (the manifest's `head` scripts, a
`sketch-render.py` key for exactly this) and does three jobs:

- *The probe* wraps `SK.txt`, `SK.card` and `SK.image` -- and on a collage film `SK.headline`,
  `SK.tape` and `SK.cutout`, which set its titles, labels and cut-outs -- while the stills
  render and notes every text style (font, weight, colour, largest size, outline, case), card
  (fill, corners, outline, shadow, area), label strip (its colour and ink) and picture the film
  draws. With the palette (`SK.C`), the ground and the style (crayon boils, clean does not),
  `SK.REPORT()` returns it; `player.html` posts it to `/report` after the stills and
  `sketch-render.py` writes it as `report.json` beside them. `_thumb.film_style()` reads it
  (cached as `style.json`, merged over every stills run).
- *The clean picture*: on an option marked `declutter`, and always on the `4000+t` pass, the film's
  own words are left out -- `SK.txt` from `declutter.min_words_px` (34) up, every `SK.headline`,
  `SK.tape`, `SK.ransom`, `SK.stamp` and marker (`SK.mark`, `SK.arrow`) -- by drawing them onto
  nothing (the calls still run, so what they return and cache is unchanged). Pictures, cards,
  charts and small print (an app's screen) stay. The `4000+t` pass records where each picture,
  card, burst and left-out word landed (`boxes.json` beside the stills); an option's `hide` names
  the bursts and cards that would show empty (a disc that carried a chapter number, a title card
  whose words are out -- a card only when its inside is flat on the clean picture).
- *The overlay*: `SK.THUMB.options`, keyed by a still's time, says what to add -- lines of word
  runs in the film's outline, a card or strips like the film's labels, a panel with a rule, the
  logo as a round paper badge, a glow, the camera's push and slide -- already laid out in Python.
  A still's time picks the pass: `t` the film alone, `1000+t` the thumbnail, `2000+t` its letters
  white on black, `3000+t` everything it added white on black (grain and vignette off for the two
  masks), `4000+t` the clean picture alone. One browser run draws every option's three passes.

**How an option is made.**
1. *Stills* come from a copy of the film's manifest without its `tail`: a Free film's "made with
   kitcut.ai" mark sits exactly under YouTube's duration stamp and cannot be read at feed size, so
   thumbnails are clean on every plan. All paths in the copy are absolute (fonts and images
   too); it renders into its own folder (`temp/thumbs/stills-<film key>/`), never the film's
   outputs. The probe rides along.
2. *Moments*: just before each narration line ends (what the line is about is drawn by then),
   6-12 of them, a second apart, on one labelled sheet that the draft's Claude call sees.
3. *Settle*: around each chosen moment (±0.6 s) the frame whose ±0.2 s neighbours differ least,
   among the ones that are not thin (a scene not drawn in yet, a fade). The same run draws each
   candidate's clean picture (`4000+t`).
4. *The film's look* (`film_style`): its titles biggest first (its headline type: `SK.txt`, and
   `SK.headline` on a collage film; a label's type after them) with their colours, case --
   a film that titles in capitals gets capitals -- tracking and outlines, then the tooling's
   type for words its type has no glyphs for or a film with no text of its own; its *outline*
   (`outline_of`: the edge of its biggest outlined title, the most neutral outlined fill for the
   words and another for the starred one -- a collage film's cream and lemon Oswald in indigo);
   its paper, text, ink and accent; its label strip when it labels with strips more than it uses
   cards, else its biggest card (else one of its paper edged in its accent -- a hand-drawn note on
   crayon); a picture named `*logo*`, round when it is an opaque square picture. A `.woff2` film
   font is measured through the tooling's `.ttf` of the same family (the example film's Caveat), a
   variable font at the weight the film draws it.
5. *Compose* (`compose`): the subject is the pictures the film drew in the frame (not its logo,
   not a painted scene filling it, not a speck or a prop under 40% of the biggest), else where the
   clean picture's saliency holds its middle 80%. Every side for the words (half the frame across,
   40% down), push (1.0 to 1.5x; 1.15x on a painted scene, 1.25x on a guessed subject) and
   position is scored: the subject's height on screen, less what of it is under the words or off
   screen, less every other picture or card cut in two, less the small print and the film's own
   frame border left in view (a progress bar's labels are cropped), never the logo cut in two; the
   writer's `place` breaks near-ties. The film draws itself again at the push, so nothing is
   stretched.
6. *Layout*, in Python, on the pushed clean picture, with the font files the page draws with: the
   largest cap height (250 down to 110 px) that fits in at most three lines (four on a panel),
   each line as wide as its ink (a hand font's swash included); in the film's outline when it has
   one, else its ink where it reads with a margin (`ink_margin`) and otherwise the nearest of its
   colours deepened just enough, the starred word in its accent; the film's logo above the words
   on options 1 and 3 (`logo.options`), unless the frame already shows it. Layouts: *headline*
   (words on the picture -- first, in each of the three best sides, a place that crosses none of
   the film's pictures and cards and, without an outline, no edge of what is drawn; then the best
   side's quietest place; on a busy spot without an outline, a soft glow of the film's paper),
   *card* (strips like the film's labels, a line to a strip, tilted as it tilts them; else the
   film's card, tilted a touch on crayon), *panel* (the film's paper on the words' side, a rule of
   its accent, the picture slid so the subject sits in the middle of what stays in view), *still*
   (the frame as the film drew it -- the last fallback only).
7. *Draw* (`paint`): one browser run of the film with the spec, three passes an option;
   `thumb.js` holds each line to the width Python planned, so a page that draws a font wider
   trims it rather than letting it leave its box.
8. *Checks* on the finished picture through the letters and footprint passes (outlined letters
   read against their outline); *fallbacks*
   (headline -> headline with its glow -> card -> still; panel -> card -> still; card -> still)
   until every option passes.

**The rules** (`config/thumbnails/thumbnails.json`, each with its source there):

| rule | value | why |
|---|---|---|
| cap height at 168 px wide | >= 8 px (>= 92 px at 1080p) | the "up next" sidebar is YouTube's smallest place with a title |
| contrast, letters vs the ring around them | >= 4.5:1 at the 10th percentile | WCAG 2.2 1.4.3; read on the picture smoothed by 1.5 px, because a crayon film's grain lies over its words too |
| no letters in the bottom-right 15% x 15%, bottom 3%, 5% margins | 0 px | YouTube's duration stamp and progress bar |
| words | <= 4 words, 32 characters; the first says the title's message | the channel owner read words that avoided the title as "a random still" (2026-09-30); was "<= half of them in the title" |
| film's own words | words on the picture touch none; a card, panel or glow hides a line whole (>= 90%) or not at all; <= 40 px otherwise | "On for everyone" set over an "AI MODEL UPDATE" label read as a collision; a half-hidden "Month-e" reads broken, a covered chip does not |
| layouts | headline, card, panel, headline; the still only as a fallback | four options are only a choice if they differ, and a picture with no words is not a thumbnail |
| the film's own words | left out of the picture under the thumbnail's (34 px and up), with the discs and cards they leave empty | one message: a card saying "Від чого залежить зарплата?" sat over the film's own heading saying the same |
| cap height | 110-250 px at 1080p | 96-200 read as a caption on a slide |

**Measured** (2026-09-29, 8 studio films -- three crayon, a clean app film, a blueprint, a dark
wine film, a photographic one and a painted Ukrainian one -- from Claude's own concepts; the
film's-own-look version, 8-14 s of options a film):
- all 24 worded options passed on the layout Claude asked for (no fallbacks); cap height 8.4-16.8
  px at 168 px; RapidOCR read every word back on the 21 Latin-script ones at 246 and 360 px and
  all but one word of one at 168 px. OCR cannot read Cyrillic (KI-035); for the Ukrainian film
  only the cap height vouches.
- contrast 4.81-11.08:1, median 5.89 -- lower than the stock-type version's 9.07 because the
  words now wear the film's own colours (a crayon film's brown ink on its cream paper) rather
  than white with a black outline; every one clears 4.5.
- the type was the film's own on every film that titles itself with `SK.txt` (7 of 8); the wine
  film draws its titles with its own pen and got Montserrat in its cream and gold (KI-038).
- YouTube-like frames at 25/50/75% caught the film moving (mean difference over ±0.2 s > 0.03) in
  10 of 24; the settled frames in 6 of 32; median movement 0.0149 -> 0.0054.

**What the bake-off changed, and why** -- each was a visible defect in a round of 32 options:
- *Saliency* (spectral residual, Hou & Zhang 2007) finds the characters, a phone, a bottle and
  ignores hatching on drawn and clean films, and misses big subjects on painted ones (KI-036). So
  Claude names a `place` from the sheet, and saliency only fine-tunes inside it.
- *The film's own words* may not be cut into: a panel slides the picture to keep them wholly in
  view or wholly under it, or moves side, widens, or falls back to a card.
- *The quiet threshold* was 0.35 on a scale where an empty ground scores 0.001-0.02 and a busy
  one 0.04-0.13: the largest size always won. It is 0.045, measured.
- *Moments two seconds apart* was stricter than the sheet (moments one second apart), and cost a
  second paid call on the first film. It is one second now.
- *The prompt's example words* ("Only *3* steps") came back as "Just 4 steps": the example is now
  just `*word*`, and the thumbnail words are held to the film like the description is.

**What the first real publish changed** (2026-09-29, a 45 s film on kitcut.ai):
- *A film's own fonts.* A film that fetched a web font keeps it in its own folder
  (`web/fonts/Inter-400.ttf`, in its `sketch.json`); the manifest copy left that path relative,
  sketch-render looked for it beside the tooling, and every still failed ("font missing"). The
  copy now makes a font path absolute when the film has the file. `studio/test_thumbs.py`'s
  fixture carries one.
- *The wait.* The draft made the moments sheet before its Claude call, so the title and
  description took 25-35 s where they had taken 10-16. A finished film now makes its sheet in the
  background (`thumbs.premake`, from `server.run`), and one film's sheet is made once however many
  ask at the same moment.

**What the film's own look changed** (2026-09-29). The first version set every film's words in
Anton or Balsamiq, white or near-black with an outline, on a stock slab and a scrim: legible, and
on an Instafill film nothing like Instafill -- no Source Serif, no amber, no white cards, no logo.
Rebuilt so the film draws its own thumbnail (above). What the rebuild had to learn:
- *Protecting every word the film shows left no room on an app screen*, which is full of small
  print. Words drawn straight on the picture avoid every line of the film's words 12 px and up;
  a card, panel or glow may hide one whole, like a sticker, never cut through it.
- *A busy spot re-places the words with the glow planned in* rather than adding a glow that
  reaches past the block (it ghosted a UI card). The glow is the block, 97% opaque.
- *A crayon film's own ink on its own paper read 4.2-4.5:1 once drawn* under its grain and
  vignette though the colours alone measure more: the ink and the accent need a 0.8 margin, and
  contrast is read on the picture smoothed by 1.5 px (grain is finer than any stroke allowed).
- *A film that outlines its titles* (cream letters edged in its ink, to read over dark scenes)
  gets its thumbnail's words edged the same way.
- *Canvas drew Caveat wider than Pillow measured it*: `thumb.js` holds each line to the width
  planned here.
- *A film with no cards of its own* got a stock white card, which sat on the black-and-gold wine
  film like a label from another shop; it gets one of its paper edged in its accent now.

The draft costs ~$0.01 more with the sheet and four concepts. Thumbnails are opt-out, never
forced: the dialog has "Let YouTube pick a frame", and a channel that YouTube will not let use
custom thumbnails (unverified, KI-037) gets its video published with YouTube's frame and a line
saying why.

**What the first channel owner's review changed** (2026-09-30, the Ocheretyne channel's
episode 3, a collage film of clay characters on cut paper): the options "don't look like YouTube
ones... we need to have the main message or a video title there... there is no logo". Four
things were wrong, one of them a bug:
- *The cut-outs were missing* (KI-048): every clay character, heart and scale was an empty paper
  burst in the stills, the moments sheet and the share picture.
- *The film's own words stayed*, so each option read as a slide from the film with a sticker on it
  -- once, a card saying the same as the heading behind it. They are left out now.
- *The probe never saw a collage film's titles*: they are set with `SK.headline`, so the words
  came out in the film's handwriting for asides, not its capitals in an indigo outline.
- *The words were small and avoided the title*: caps of 96-136 px, and a rule against repeating it.
Measured after, on the same eight films as the first bake-off plus the collage film, from the
concepts they already had (36 options): all 36 kept the
layout asked for, one headline with its glow, every one in the film's own type; caps 9.6-19.2 px
at 168 px wide, median 10.5 (were 8.4-17.5); contrast 5.05-11.0:1, median 6.7; the collage film's
subject read off its pictures and pushed 1.1-1.5x, the other films' off saliency at 1.1-1.24x;
13-15 s of options a film on the laptop once its stills exist. What is still weak: on a painted
film the subject is guessed (KI-036), and a panel can cut it at the frame's edge; a crayon film's
busy town leaves a headline no clean place, and it takes the quietest; a film that draws its
titles with its own pen keeps them (KI-038).

## Share title and image

Every finished film on kitcut.ai gets a public page of its own (`kitcut.ai/v/<short>/<slug>`),
and a link to it shows a preview wherever it is posted. The studio writes what that page and its
preview say, the moment the film is done (`studio/share.py`):

- **a title** a person would click -- at most 70 characters, no full stop, in the film's language,
  never the request pasted back and never "AI-generated";
- **a description** of one or two sentences saying what the film shows (at most 155 characters, the
  length a search result or a link preview shows whole);
- **a picture in the film's own look**: a still of the film with a few words on it, drawn by the
  film itself -- the same machinery as the YouTube thumbnail options (`thumbs.py`,
  `scripts/_thumb.py`), asked for two concepts (a headline and a card) instead of four. The first
  one whose words survive the checks is used, cut two ways: `outputs/share.jpg` (1200x628, the link
  preview, the whole frame in the middle with blurred sides, exactly as `card.jpg` is made) and
  `outputs/thumb.jpg` (1280x720).

The words come from what the YouTube draft reads (`ytdraft.material`: the narration with its
times, who it was made for, what Claude said, the pages its facts came from, the sheet of the
film's moments), in one Claude call with no tools; a pasted brief or a film called generated is
asked once more, then given up. The two pictures go to the same Azure container as the film
as `<id>/share-<v>.jpg` and `<id>/thumb-<v>.jpg`, where `<v>` is the first 8 hex characters of a
hash of the two pictures' bytes. The film's record -- `studio.json` and `kitcut.studio_runs`,
where only `share` is set -- then holds what the site reads:

```json
"share": {"title": "<= 70 chars", "description": "<= 155 chars", "language": "en",
          "image": "https://kitcutst.blob.core.windows.net/films/<id>/share-0c636175.jpg",
          "thumb": "https://kitcutst.blob.core.windows.net/films/<id>/thumb-0c636175.jpg",
          "at": "2026-09-29T23:33:24Z", "key": "<draft key>"}
```

`language` is a short code (`en`, `uk`, `es`) whatever the film's voice settings say (`en-US`,
`Ukrainian`). `image` and `thumb` are left out when the picture could not be made or copying online
is off (the site then shows `card.jpg`); the files stay in `outputs/`. `GET /api/films/{id}` answers
`share` = `{title, description, language, image, thumb}` for a film that has one.

**It never fails a film.** It starts as a background task beside the moments sheet once the film is
`done`; a failure is logged as `SHARE <id> failed: ...` and noted on the record as `share_error`,
and the film's state is never touched. `STUDIO_SHARE=0` turns it off; it also stays off while
Claude is a stub (the studio's tests), so a test never makes a paid call.

**Cost:** about $0.05-0.13 a film on the key (one call with the moments sheet; occasionally two),
kept on the record as `share_cost_usd` and added to `cost_usd`; on the Claude login it is counted
but not charged. The draft is kept in `share/draft.json`, keyed by what it was written from, so
asking again costs nothing until the film changes. The picture is CPU and a headless browser, at
most `STUDIO_THUMB_JOBS` at once.

```bash
python studio/share.py --film <id>                     # write (or remake) one film's share
python studio/share.py --missing [--limit N]           # every finished film without one, newest first
python studio/share.py --missing --dry-run             # which films, and the estimated cost; no call
bash studio/deploy/ops.sh share <id>                   # the same on the VM: the price first, then the work
bash studio/deploy/ops.sh share --missing --limit 20   #   in a unit of its own (goes on if the laptop sleeps)
bash studio/deploy/ops.sh share --missing --dry-run    # price only
python studio/test_share.py                            # stubbed: the rules, the pictures, the record, the API
```

`--missing` also picks up a film whose share has no picture online when copying is on: its draft
is kept, so that costs no model time.

**Why the names carry a version.** The pictures go up with the film files' year-long immutable
cache header. Under a fixed name, a remade picture would keep being served stale by any browser or
link-preview cache that had fetched the old one. With the version in the name, the same picture
keeps its URL and a different one gets a new URL. A remake leaves the older copies in place,
because a preview already posted may still point at them. `media.py --delete <id>` removes the
pair the record names (and any unversioned `share.jpg`/`thumb.jpg`).

## A channel's banner

```powershell
python scripts/yt-set-banner.py projects/<id>/branding/banner-2560x1440.jpg --channel @handle --dry-run
python scripts/yt-set-banner.py projects/<id>/branding/banner-2560x1440.jpg --channel @handle
python scripts/yt-set-banner.py <image> --channel @handle --reauth    # a channel this machine has no grant for
```

Two calls: `channelBanners.insert` uploads the image and returns a URL, then
`channels.update(part=brandingSettings)` sets `brandingSettings.image.bannerExternalUrl`.
**The update replaces the whole part**, so the channel's `brandingSettings.channel` block
(description, keywords, country, language, trailer) is read first and sent back as fetched --
leave it out and the description and keywords are wiped. After the write the channel is
re-read: the new URL and the unchanged channel fields are both asserted.

The image is checked before any consent is spent: JPEG/PNG, 16:9, at least 2048x1152, under
6 MB. Only the middle 1235x338 shows on every device. It needs `youtube.force-ssl` -- the grant
`yt-connect.py` files -- and **not** kitcut.ai's grant, which is `youtube.upload` +
`youtube.readonly` and can upload a banner image but not set it. A first `--reauth` sends
`prompt=select_account consent`, which is what the site's own handshake uses to reach a brand
channel from a signed-in browser. The avatar cannot be set through the API at all; it is
uploaded by hand in Studio -> Customization -> Branding.

## Chapter markers on a published video

Turn a transcript into YouTube chapters, then write them into the video's own
description:

```powershell
python scripts/transcribe-words.py audio/<id>.m4a --out transcripts/<id>.words.json --language en
python scripts/transcript-outline.py transcripts/<id>.words.json --outline   # read, pick boundaries
# write projects/<id>/chapters.txt as "MM:SS Title" lines, then:
python scripts/yt-set-chapters.py <id> --chapters projects/<id>/chapters.txt --dry-run
python scripts/yt-set-chapters.py <id> --chapters projects/<id>/chapters.txt
```

Picking the boundaries is editorial and stays a human/model judgement — the
script's job is to make the result *valid* and the write *safe*.

It refuses to upload a list YouTube would silently ignore: the first chapter
must be at `00:00`, there must be at least three, and consecutive marks must be
at least 10 s apart. YouTube does not report any of these as errors; it just
renders no chapters at all, which is easy to mistake for a failed update.

### Which videos actually need them

```powershell
python scripts/yt-audit-chapters.py --channel @instafill_ai
python scripts/yt-audit-chapters.py --channel @instafill_ai --none-only
```

`NONE` is the list worth working through. `AUTO` means YouTube generated the
chapters itself — they render, but nobody chose them, so writing real ones
takes control back. `RETRY` means the read failed, **not** that chapters are
missing; see below.

**The watch page is the authority, not the description.** The first version of
this audit judged descriptions against the familiar "first mark at 0:00, at
least three, ten seconds apart" rules and was wrong on 11 of 46 videos —
it declared nine of them broken while every one was rendering fine. Measuring
what YouTube really shows (`yt-dlp`'s `chapters` field) against the descriptions
that produce it found that **none of those rules are enforced** the way they are
usually quoted:

| assumption | what actually happens |
|---|---|
| first mark must be `00:00` | YouTube prepends an `<Untitled Chapter 1>`; the rest render |
| marks must be ≥10 s apart | a 4-second chapter renders fine |
| marks must be in order | an out-of-order pair still renders |

So `yt-set-chapters.py` now *warns* about these instead of refusing. Only the
three-chapter minimum is still enforced, and that one is inherited from
documentation rather than measured — treat it with the same suspicion.

Two failure modes are deliberately never reported as "no chapters": a scheduled
live event (`LIVE`), and YouTube's bot check after too many fetches (`RETRY`).
Auditing a 46-video channel a few times in a row is enough to trip it. A read
that failed must not look like an empty one, or you go and write chapters for a
video that already has them.

**Check whether the video already has chapters before generating any.** Several
of these videos were published with hand-written ones, and a freshly generated
list is not automatically an improvement — the ones on the CMS-1500 video were
finer-grained than what a first pass produced. The script prints an old-vs-new
diff and **refuses** to overwrite an existing block without `--replace`; the old
text is gone for good once written, since the API keeps no history.

The write itself preserves the rest of the description. `videos.update` replaces
the **entire** snippet, so the script sends back the snippet it just fetched with
only `description` changed — dropping `title` or `categoryId` from that body is
how you blank a video's title. A chapter block already in the description is
replaced in place; otherwise the new one is appended. After writing it re-fetches
and asserts the block is really there.

### One-time auth

The API writes as the channel owner, so it needs the owner's own OAuth consent —
an API key cannot do this.

1. Google Cloud Console → a project → enable **YouTube Data API v3**.
2. **OAuth consent screen**: External, and add yourself as a test user.
3. **Credentials → OAuth client ID → Desktop app**, download the JSON to
   `.yt-oauth/client_secret.json` (gitignored).

The first run opens a browser. **At the account chooser, pick the channel that
owns the videos, not your personal account** — this is the one step that goes
wrong. A personal-account token reads those videos perfectly and cannot write
them, so everything looks fine until the update returns a bare `403`. The script
compares the token's channel against the video's owner and names both.

The resulting grant is written into `.env` as `YOUTUBE_CLIENT_ID`,
`YOUTUBE_CLIENT_SECRET` and `YOUTUBE_REFRESH_TOKEN`, which is where this repo
keeps its secrets and what later runs read; `.yt-oauth/token.json` remains as a
fallback. Keeping it in `.env` also means deleting `.yt-oauth/` — the fix for
having consented as the wrong channel — no longer destroys the grant too.

Quota note: `videos.update` costs 50 units of the default 10,000/day, while the
`videos.list` read costs 1.

Two ids on this channel begin with `-`, which argparse reads as a flag. Pass
those as `--video=-qKcpLSk0iU`.

## Deleting an upload

Removing a video is the one publish operation with no undo, so `yt-delete.py`
is dry-run by default: without `--yes` it fetches each id and prints the title
and privacy it *would* delete, and stops.

```powershell
python scripts/yt-delete.py <id-or-url> [<id-or-url> ...] --channel @instafill_ai
python scripts/yt-delete.py <id-or-url> ... --channel @instafill_ai --yes
```

`--channel` is required here for the same reason `yt-upload.py` guards it: one
Google login can own several channels and the grant picks one silently. The
script asserts the handle or title the token actually points at before anything
is removed. It reuses the one `youtube.force-ssl` grant, so there is no second
consent to give.

An id that is already gone, or that belongs to another channel, prints
`NOT FOUND` and is skipped rather than failing the batch — deleting the same
list twice is safe.

Ids are accepted as bare ids or as any YouTube URL form, so the `url` field
from a render's `.youtube.json` sidecar can be pasted straight in. After
deleting, drop the deliverable's entry from `projects/<id>/project.json` and
its `.youtube.json` sidecar yourself — no script records a deletion.

## The "Made with AI" label

A watch page can show "How this was made / Made with AI — Sounds or visuals
were altered or fully generated". Two different things put it there, and only
one of them is ours to change:

- **The creator's disclosure**: Studio's "Altered content" box, which the Data API calls
  `status.containsSyntheticMedia`. No script here sets it on upload.
- **YouTube's own labelling**, from C2PA content credentials in the file or its
  own detection. The API cannot see this label and cannot clear it.

```powershell
python scripts/yt-set-disclosure.py --channel @kitcut-hq --list --labels   # which pages carry it
python scripts/yt-set-disclosure.py --channel @kitcut-hq --set no --dry-run
python scripts/yt-set-disclosure.py --channel @kitcut-hq --set no --video <id>
```

Measured 2026-09-30: every upload on both channels read as not-"yes". Two
@kitcut-hq videos carried the label anyway (`watMf06668M`, `V25n5_k7v_c`, both
studio films with an AI voice), and `watMf06668M` kept it after an explicit
`--set no`. So on our footage the label comes from YouTube, not from the flag,
and flipping the flag channel-wide would spend about 13,000 quota units to
change nothing.

Two traps. The API returns the flag **only when it is "yes"**, so "no" and
never-set read back identically (`-`). And `videos.update` replaces the whole
status part, so the script sends back privacy, `publishAt`, licence, embeddable,
stats visibility and made-for-kids exactly as it read them. `--labels` reads the
public watch pages anonymously, with a 2 s pause per page, because YouTube
answers 429 after about 130 back-to-back pages. A 429 prints as `429?` rather
than failing the run.

### Widening an upload: `yt-set-privacy.py`

Uploads go up unlisted; once the owner approves a video, this makes it public (or back). It
sends the whole status part back as read, with only the privacy changed, drops a scheduled
`publishAt` when going public, and reads the answer back.

```powershell
python scripts/yt-set-privacy.py --channel @kitcut-hq --video <id> --privacy public --dry-run
python scripts/yt-set-privacy.py --channel @kitcut-hq --video <id> --privacy public
```

### Can we see the watermark ourselves? No (measured 2026-09-30)

YouTube says it labels undisclosed content from C2PA metadata and Google's
SynthID. Every studio film's voice is Gemini TTS (`studio/film.py`, `VO_PINNED`),
and Google watermarks Gemini audio with SynthID. So the likely trigger is the
voice. We probed 18 raw Gemini takes (Sulafat ×2 films, Leda) against 12
ElevenLabs takes (lily, george) and 6 edge-tts lines (Aria, Guy):

| probe | result |
|---|---|
| C2PA / provenance metadata | none. The API returns bare PCM with no container to carry it, and none of our renders carries a `c2pa`/`jumb` box (the one grep hit was bytes inside the compressed video) |
| narrow tones in the quiet floor | none common to the Gemini takes |
| periodic modulation (5–60 Hz, 4–11 kHz band) | only the syllable rate (5–10 Hz), the same in every engine |
| noise floor | **Gemini never reaches silence.** Its quietest frames sit 10–30 dB above ElevenLabs (MP3 floor) and edge-tts (exact digital zero between words), and the floor's shape correlates 0.95–0.97 across Gemini voices |

The floor fingerprints the engine; it is not the watermark. SynthID's audio
mark is keyed and learned to sit under the speech, so without Google's detector
it cannot be found by inspection, and a spectrum does not show it. The detectors
that exist are Google's: the Gemini app ("was this made with Google AI?") and
the SynthID Detector portal (waitlist). Both are cloud uploads, so they suit a
published film's audio, not unpublished footage.

Policy: YouTube requires "yes" for realistic content that could mislead, such as
a real person's cloned voice or a photo of a real person made to speak.
Animation with a generic narrator does not need it.

## Sketch films: an explainer written as code

A sketch film is an animated explainer with no footage at all: the picture is JavaScript,
the voice is text-to-speech, the music is a score played on sampled instruments, and every
sound effect is synthesised. Three scripts take one manifest from script to finished MP4, and
the same code plays live in a browser as a self-contained HTML player.

```powershell
python scripts/sketch-vo.py     --manifest projects/<id>/sketch.json --plan   # price the voice
python scripts/sketch-vo.py     --manifest projects/<id>/sketch.json          # takes, pick, word times, captions
python scripts/sketch-render.py --manifest projects/<id>/sketch.json --stills 2,9.5,31 --sheet
python scripts/sketch-audio.py  --manifest projects/<id>/sketch.json --levels # score + sfx + mix + master
python scripts/sketch-render.py --manifest projects/<id>/sketch.json          # the video
python scripts/sketch-render.py --manifest projects/<id>/sketch.json --timings
python scripts/check-sketch.py                                                # free self-test
```

Start a film by copying `config/sketch/example/` to `projects/<id>/` (the scripts write
`audio/ outputs/ temp/` next to the manifest). The example runs end to end for free: its
voice is edge-tts.

### The pieces

| file | what it is |
|---|---|
| `sketch/engine.js` | the renderer: strokes that boil, cel fills, write-on text, camera, flight paths, paper, grain; `SK.setStyle('crayon' \| 'clean')`; the ground, `SK.setGround(name)` (paper, white, kraft, sky, mint, butter, blush, night, chalkboard, blueprint: the paper, its grain and the text colours that read on it, `C.text` `C.textSoft` `C.accent` `C.accentText`), or `ground: (t) => name` in `SK.film`; backdrops that cover whatever the camera shows: `SK.sky`, `SK.band` (ground, hills, waves, grass; returns `edge(x)`), `SK.stars` |
| `sketch/collage.js` | the collage pieces, a module a film opts into (`"modules": ["collage"]`, loaded after the props): cut-out pictures, torn sheets, tape labels, headlines, stamps, bursts, halftone dots, ransom letters, marker lines, masking tape, a newspaper backdrop, groups, and the in/out motion they share; `SK.setStyle('collage')` (see "Collage films") |
| `sketch/space.js` | a little 3D, a module a film opts into (`"modules": ["space"]`): a perspective camera (`SK.view3`), faces drawn with the ordinary 2D engine and laid onto 3D quads (`SK.face3`), boxes (`SK.box3`), lit flat polygons (`SK.poly3`) and blurred or smeared layers (`SK.fx`) (see "Motion-design films") |
| `sketch/props.js` | the cast: ticket character, seated person with poses, a standing/walking/sitting kid (`P.kid`, also the grown-up at s ~1.4), paper plane, laptop, table, lightbulb, rocket, padlock, coin, stamp, browser window, thought bubble, confetti, architectural houses, phone, window (cracks), street siren, delta-wing drone, missile, stopwatch, debris; scenery: tree (round, pine, bare), bush, cloud, sun, moon (full, crescent), mountain, building |
| `config/sketch/grounds/` | every ground and three places built from the backdrops, one a second: render its stills after changing any of them |
| `sketch/player.html` | the page: player UI, and the export modes the renderer drives |
| `projects/<id>/film.js` | the film: `SK.film({duration, camera, draw(t, vis)})` |
| `projects/<id>/score.json` | the music, as data (notation below) |
| `projects/<id>/sfx.json` | timed sound cues |

**A closing after the film** is the manifest's `tail`: `{"secs": 3, "scripts": [...], "images":
{...}, "audio": "closing.wav"}`. The scripts run after film.js and lengthen `SK._film` (Sketch
Studio's `studio/outro.js` holds the last frame and draws over it); sketch-render renders `secs`
more, and sketch-audio ends the film's sound at the film's end as always, then plays `audio`
after it, as loud as the narration. `poster_t` stays in the film.

**A cast of recurring characters** is the manifest's `cast`: a folder (`"cast": "cast"`) whose
`<name>.js` files each run in their own scope after props.js and before film.js, and register one
member as `SK.cast.<name> = {about, draw(x, y, o)}`. An error in one names its file. Sketch
Studio keeps each signed-in person's cast between their films (`studio/library.py`).

**Engine modules** are the manifest's `modules`: engine extensions only some films need
(`["collage"]`), each `sketch/<name>.js` -- or the same file in the film's own `engine` folder,
which wins -- inlined after props.js and before the cast. A film that does not ask does not
carry it, and an error in one names the file it ran from (`sketch/collage.js`, or
`engine/collage.js` for a film's own copy). A name with no file stops the bundle.

**A film in scenes** is the manifest's `scenes`: a folder (`"scenes": "scenes"`) whose
`NN-slug.js` files each run in their own scope after film.js, in name order, and register one
scene: `SK.scene({id, lines: [a, b], draw(t, local, vis), camera?, out?, lead = .3})`. film.js then
holds only what every scene shares -- the look, helpers in `SK.look`, the camera -- and calls
`SK.film({duration, camera})` without a `draw`: the film draws the scene covering t. A scene
starts `lead` s before line a is spoken (the scene of line 0 at 0 s) and ends where line b+1
would start, so a stretch whose scene is not written yet draws nothing instead of failing the
render or letting the scene before it run on; `local` is seconds since the scene began (its camera
runs on it), `t` the film clock for `SK.w` cues, and `out` cross-fades into the scene that follows.
A scene that throws at load names its file in the error; one that does not parse is named by a
syntax check (a script that fails to parse never reads its own name -- cast members alike). A film
without `scenes` renders exactly as before. Sketch Studio makes films this way past
`STUDIO_SCENES_OVER_S` (`studio/scenes.py`; why: docs/known-issues.md KI-034).

**Every frame is a pure function of time.** Nothing in a film may keep state between frames
(no physics integration, no `Math.random`); randomness is `SK.rnd(seed)`, motion is `t`. That
single rule is what lets the browser play the film against its audio *and* the renderer export
frame 2,317 on its own.

**Cue visuals to words, not to seconds.** The bundler injects the voice timeline, and
`SK.w(line, "word")` returns when a word starts. A film written that way survives a
re-recorded line: the visuals move with the voice. Hand-copied timestamps silently drift the
first time a take changes.

**Three looks, one engine** (the third, `collage`, has its own section below). `crayon` re-jitters every line 8 times a second (the traced-cel
boil), adds a faint second pencil pass, and prints fills a few pixels off their outlines;
`clean` turns all of that off for crisp editorial line art with flat fills, soft card shadows
(`SK.card`), a drafting grid and letters that rise instead of pop. Both have shipped: a
whimsical 40 s crayon film, and a 60 s clean real-estate film for a brand.

### The voice: `sketch-vo.py`

Per line: N takes (cached by a fingerprint of text + voice + model + settings, so an edit
re-renders only that line), each cut at the silence before a throwaway tail word, scored by
Whisper against the script, the best one picked (accuracy, then a clean cut, then the take
nearest the median length) unless the line names `"pick"`. Lines are placed at their `start`
or after the previous line plus `gap`; word times come from the ElevenLabs character
alignment, minus `[audio tags]` and the tail. Writes `audio/vo/timeline.json` and
`outputs/<slug>.srt/.vtt`.

`"hotwords"` go to Whisper as its initial prompt, so a brand name is heard as one word
instead of costing its take a lower rank.

`--jobs N` (or `vo.jobs`) records N takes at once; the default is 1, one after another, and the
studio passes 8 (`studio/tools.py` `VOICE_JOBS`). The services answer a line in seconds, so a
long film waited minutes on them: measured on the 8-minute studio film (70 lines of Gemini 3.1
Flash TTS, 2026-09-28), synth took **341 s one at a time and 52 s eight at a time** (6.6x), with
the same word accuracy (mean 0.932, the same 21 lines under 0.9) and the same cost ($0.25). A
429 or 5xx from Gemini (Vertex or the Gemini API) or ElevenLabs is asked again with jittered,
doubling waits (`BUSY`, `busy_wait`) -- N at once meets the rate limit that one at a time never
did. The takes are cached exactly as before, the `.json` written last, so an interrupted run
keeps what it finished. Word timing (`score`, Whisper) is unchanged and was the other 239 s.

Measured, 9 lines x 3 takes of `eleven_v3` (839 characters, ~2,500 credits): synth 91 s,
trim 2.5 s, Whisper scoring (small.en, CPU) 81-99 s.

**The scorer.** A take's score is remembered beside it (`<take>.score.json`, keyed on the
audio, the line, the hotwords, the language and the scorer), so a re-recording scores only
what changed. `SKETCH_SCORER` (the machine) or `vo.whisper` (the film) picks who listens:
a local faster-whisper model, or `openrouter:<model>` -- a transcription model OpenRouter
serves, scored `--jobs` at a time, needing `OPENROUTER_API_KEY`, and falling back to local
Whisper for a take the service fails. The studio uses `openrouter:openai/whisper-large-v3`
(Groq). OpenRouter drops a transcription prompt, so the hotwords reach only Azure's
`microsoft/mai-transcribe-2`, as a phrase list. Compare scorers on a finished film with
`scripts/vo-scorer-bench.py --reference large-v3`: agreeing with the film's own scorer proves
nothing, so hold them to a stronger one. `--plan` prices them, and a model that gives no word
times is reported as unmeasurable, not quietly scored locally. The numbers, and why the first
pick (MAI) was wrong, are in `docs/studio-speed.md`.

**A film in another language** sets `vo.language` (ISO 639-1) and a `tail` in that language
(`"Добре."` for Ukrainian -- an English tail flips the voice's accent on the line's last
words). Scoring then runs a multilingual Whisper (`vo.whisper`, default `large-v3` on the
GPU, CPU if CUDA will not load), the words are compared letter-class-agnostic, `SK.w()`
matches Cyrillic cue words, and the MP4's subtitle track is tagged with the language.
Fonts must carry the script: the committed woff2 files are Latin subsets, so a Ukrainian film
uses the complete `.ttf` fonts in `fonts/` (`Caveat-Cyrillic-VF.ttf`, `BalsamiqSans-*.ttf`).
Voice choice is measured, not guessed: synthesize one line with each candidate and let
Whisper large-v3 detect the language unprompted -- its confidence is an accent score. For
Ukrainian on `eleven_v3`, `lily` came first (p = 0.997, 100% of words; 8 voices tried).
Measured on the first Ukrainian film (10 lines x 3 takes, 738 characters): synth 142 s,
scoring on large-v3/GPU 48 s. Lily speaks Ukrainian at ~1.8 words a second, not the 2.6 the
`--plan` estimate assumes: budget ~100 words for a minute.

**A line Gemini will not read.** Gemini TTS's content filter refuses some lines outright
(`PROHIBITED_CONTENT`: a line naming the investor Carl Icahn in the Dell film, wine words
in `ssemfm`), and asking again does not help. The same words may pass on another run, or
with a different voice direction -- the filter is not repeatable. `gemini_take` now raises
`Refused` for a content block (a glitch with no audio still gets its three tries), and with
`vo.backup` set -- the studio pins `{"tts": "elevenlabs", "model": "eleven_v3",
"voices": {"low": "brian", "high": "sarah"}}` -- that one line is read by ElevenLabs
and the rest stays Gemini's:
- **low or high** is measured, not looked up: the median pitch of the film's Gemini takes
  already recorded (`pitch_hz`, below 165 Hz is low). Only when nothing is recorded yet does
  the Gemini voice's label decide (`GEMINI_FEMALE`). Labels and voices disagree: a voice
  direction moved Puck, Fenrir and Sadachbia above 220 Hz and Gacrux to 130 in real films.
- **levelled** to the Gemini lines' median speech level (-18.4 dBFS over 40 lines; v3 came
  out at -18.1, Turbo at -22.4), trimmed and timed by Whisper exactly as a Gemini take.
- **recorded** in the timeline as `backup_voice`, and costed at the ElevenLabs API price
  (`EL_USD_PER_CHAR`: v3 $0.10 per 1,000 characters) into the same `tts_cost_usd`.
- the studio's `voice` tool tells Claude which line the backup read, so it can keep it or
  reword it.

Why ElevenLabs, measured 2026-09-27 (`scratchpad voice_bakeoff.py`; the refused line, a
normal one, a wine line and a Ukrainian one): every candidate read the refused and the wine
lines; Whisper accuracy was equal; speaker similarity to the film's Gemini narrator (NeMo
TitaNet, 0.60 for Gemini against itself) was 0.17-0.33 for ElevenLabs `brian` and
0.03-0.10 for OpenRouter's Microsoft MAI Voice 2 (one English voice, female; its Ukrainian
slipped into Russian forms). Gemini through OpenRouter is the same model and the same
filter, so it is no backup. Voice cloning on OpenRouter (Mistral Voxtral, Fish Audio) was
not reachable with the key's allowed providers; MAI 2 Flash has no cloning endpoint there.

### The soundtrack: `sketch-audio.py`

Stages: fetch any missing instrument notes (FluidR3 GM, MIT, into
`models/soundfonts/FluidR3_GM/`, shared by every project), render the score, render the cues,
place the voice, duck the music under it (fast attack, slow release), hold it at least
`mix.voice_margin_db` (8) under the voice wherever the voice speaks, mix, and master with a
two-pass `loudnorm` to -14 LUFS / -1.5 dBTP. `--levels` prints music / ducked / heard / sfx /
voice RMS per 2 s, which is how the balance is judged without listening; `--stems` writes them
out. Every run also writes `audio/balance.json` (the same table, and what the voice gate did),
which is what Sketch Studio's `sound` tool shows Claude.

**The voice gate** is the backstop the ducker is not: the ducker follows the voice but trusts
the score's own level, so a score written too loud buries the narration however well it
ducks. The gate measures, in 1 s windows, the music over the whole window against the voice
only while it sounds (a window counts when the voice sounds for 40% of it), and pulls the
music down to the margin where it is closer -- at once, releasing over 0.6 s, and free again
after the last word. Measured on the 13 finished studio films: at 8 dB it touches one of them
by 1.4 dB for 1.2 s (6 dB: none; 9 dB: two by ~2 dB); on the one bad film it cuts up to 18 dB
from 16 s to the end. The first version measured the voice over whole windows, where the pauses
between lines diluted it by 8-11 dB, and it cut 2-4 s off the music of films that were fine.
A score with any volume outside 0..1.5 is refused before anything renders (`check_score`).

Measured on the 60 s film: samples 45 s the first time (69 notes), 0.5 s after; music 16.7 s;
sfx 4.1 s; voice 3.5 s; mix 1.5 s; master 8.1 s.

**Score notation** (`_sketchaudio.py` carries the full reference):

```json
{"bpm": 96, "drum_gain": 0.45, "events": [
  {"inst": "acoustic_grand_piano", "vel": 0.3, "notes": "0 D4+F#4+A4 .5; .5 D4+F#4+A4 .5"},
  {"type": "strum", "at": 22, "chord": "F3+A3+C4+F4+A4", "vel": 0.55, "pattern": "bar"},
  {"type": "gliss", "from": 31.2, "to": 32, "lo": "D4", "hi": "D6", "v0": 0.12, "v1": 0.3, "root": "D"},
  {"type": "roll", "inst": "timpani", "note": "C2", "from": 44, "to": 47.4, "v0": 0.12, "v1": 0.67},
  {"type": "drums", "from": 32, "bars": 5, "kit": {"kick": "x.....x...x.....", "clap": "....x.......x..."}}
]}
```

Times are in beats; every volume (`vel`, a note's own velocity, `v0`/`v1`, `drum_gain`, and
`"swell": [g0, g1]`, each note's own volume ramp such as `[0.3, 1]`) is a gain from 0 to 1.5,
never a time. **Choose the tempo so bar lines land on the story**: at 96 bpm a bar is
2.5 s, which put the drop exactly on "Now, drop the files" (20.0 s) and the stabs on
"Confirm" (40.0 s). A long score is easier to generate from chord charts with a small script
beside it than to type by hand.

**Cue notation** (`sfx.json`): `{"t", "fx", "db", "pan", "send", "args"}`, plus
`"times": [...]` for a repeat. `fx` is any generator in `_sketchaudio.FX` (whoosh, pop, boing,
thunk, clink, crash, rumble, boom, zip, blip, click, scribble, crinkle, keys, shimmer,
swoosh_soft, tick, chime, siren -- a softened civil-defence wail), `"sample"` (an instrument note or a run of notes), or `"air"`:
airflow that follows a moving object's speed and screen position, from the film's
`automation` tracks (`sketch-render.py --automation` writes them).

### The paintings: `sketch-paint.py`, and choosing a painter with `paint-compare.py`

A painted film animates pictures made by an image model. The manifest's `paint` block (inline,
or `"paint": "paint.json"`) lists them as `{"name", "prompt", "ref"?}`, with one `style` line
in front of every prompt and a no-lettering, no-border suffix behind it. Each becomes
`images/<name>.jpg` and joins the manifest's `images`, so `film.js` draws it with
`SK.image(name, x, y, w)`. Paintings are cached by a fingerprint of backend, model, style,
prompt and reference; `max_images` caps a film's total (Sketch Studio sets 8).

Backends:
- **`openrouter`**: any model OpenRouter's Image API serves (`"model": "<vendor>/<model>"`).
  Each model is sent only what its entry in the public catalogue
  (`/api/v1/images/models/<id>/endpoints`) lists. That means 16:9 or the landscape ratio
  nearest it, 2K or the nearest size below, and JPEG where offered. `quality` is sent only to
  models that have the setting (OpenAI's). The price comes back with each picture.
- **`muse`**: the same backend pinned to `meta/muse-image`, the studio's painter. It is served
  but missing from the catalogue, so it gets the settings it always got (2K, 16:9, PNG) and
  answers 1920x1280 whatever ratio was asked. It costs about $0.01 a picture and takes 15-30 s.
- **`gemini`**: Vertex AI.

`ref` names a painting already made. It goes in as a reference picture (`input_references`,
a data URL) wherever the model takes one, and is how a character stays the same from scene to
scene. Muse takes no reference, so it paints the second scene from the words alone.

**Choosing a painter.** `paint-compare.py` paints one paint block with several models side by
side.
- An image may carry its own `style`, so one test set can hold scenes from several films.
- A `ref` is painted from the same model's own painting of the scene it names.
- It writes into `temp/paint-compare/`: a contact sheet per model, a sheet per prompt with every
  model's picture labelled (price, seconds, size), and `results.csv`/`results.json`.
- `--plan` prices the run from the catalogue, and `--cap` stops it at a spend.
- A rerun reuses every picture already painted.
- The test set used on 2026-09-26 is `projects/paint-bakeoff/`: six scenes from studio films,
  plus one character painted and then re-used as the reference for two more scenes. That run
  painted 72 pictures on 8 models for $1.78, with no lettering or borders from any model.
- **Muse is the best picture per dollar we can reach.** It gives $0.01 at 1920x1280 with the
  most detail. The alternatives:
  - GPT Image 2.5 Flare is $0.009, or $0.02 with a reference. It takes 14 s and composes well,
    but its textures look blocky at full size.
  - MAI Image 2.6 Flash is $0.02 and takes 14 s. It holds a character best and looks clean, but
    comes out at only 1365x768.
  - GPT Image 2 and MAI 2.6 look good, but cost 3-4 times as much.
  - GPT Image 1 Mini is flat and sepia.
  - The weighted scores are in the journal.

**OpenRouter's allowed-providers setting overrides the model name.** A model whose only
providers are outside the account's allow-list fails with `404 No allowed providers are
available for the selected model`. On 2026-09-26 the kitcut key permitted only
meta, azure, openai and typesafe. So Seedream, Qwen, FLUX.2, Recraft, Riverflow and Gemini all
refused, even though they are in the catalogue at a price. `--plan` cannot see that setting;
paint one scene per model before trusting a price.

### The picture: `sketch-render.py`

Bundles engine + props + film + fonts + images + voice timeline + mastered MP3 into
`outputs/<slug>.html` (one file, plays offline) and `outputs/artifact/<slug>.html` (the same
without html/head/body, for claude.ai Artifacts). `--stills` and `--sheet` are the review
loop: 18 stills in 8.6 s. The video is rendered by opening the page in headless Edge/Chrome
(`html-to-image.py`'s browser finder, so no Node and no Playwright): the page draws each frame
and POSTs its raw pixels to a local server here, which pipes them into ffmpeg with
`_encode.video_args`. The mux uses `-t`, never `-shortest` (see the gotchas), asserts the
duration, and adds a soft subtitle track and the poster.

**The first frame is the film's cover.** X, iMessage and a phone's `<video>` before play all
show frame 0 of the file, and a film that opens on bare paper -- most do, the picture is drawn
in -- showed there as an empty rectangle (the Collage launch film on X, 2026-09-30). So frame 0
draws the poster instead (`poster_t`, the payoff), or, when the film ends on paper, the
livelier of a few later moments (0.5/0.65/0.8/0.92 of the film, the tail excluded): the same
rule, and the same 1.4x contrast margin, as the studio's link-preview card (`studio/media.py`),
so the card and the first frame agree. It is one frame -- 17 ms at 60 fps, unseen in play --
and replaces rather than inserts, so duration and sound are untouched; the frame after it is
encoded as a keyframe, because it is a cut. The choice costs one browser and five stills (~7 s)
and is printed with each candidate's contrast. Manifest `cover`: a number is that film time,
`false` keeps the film's own opening; `--from` other than 0 has no cover.

The frames are drawn in chunks (`--chunk`, 8 s of film each), each in a fresh browser: measured
on the 63.5 s air-raid film, a single session fell from 13.8 to 1.5 frames a second and then
stopped answering at frame ~2,700 of 3,810. `--jobs` browsers draw chunks at once (default a
quarter of the logical cores, at most 6), each into its own encoder and segment file under
`temp/`, and the segments are joined by stream copy. One browser is serial -- draw, read the
canvas back, POST 8 MB, wait for the encoder -- so it left most of the machine idle. A film
shorter than jobs x chunk is split evenly across the browsers instead, down to 1 s each.

Every segment's frames are counted (`ffprobe -count_packets`) before it is accepted, and a
chunk that fails or comes back short is redrawn from its start, up to three times -- safe
because every frame is a pure function of t. The count is not paranoia: the first parallel
run produced a segment with no moov atom whose chunk had reported clean, and the join is
where that surfaced. The joined file is counted again against the frame total.

Measured on an i9-11900H (8 cores/16 threads) + RTX 3050 Ti laptop, shared with other sessions:

| render | jobs | wall clock | frames/s |
|---|---|---|---|
| air-raid, 63.5 s at 60 fps | 1 (the old serial path) | 809 s | 4.7 |
| air-raid, 63.5 s at 60 fps | 4 | 269 s | 14.1 |
| 32 s of it, chunk 4 | 2 / 4 / 6 / 8 | 219 / 108 / 102 / 95 s | 8.8 / 17.8 / 18.9 / 20.3 |
| a 5 s studio-length film | 1 / 4 | 28 / 15 s | 10.8 / 20.1 |

Past four browsers the gain flattens, which is why the default is a quarter of the cores.
Speed also moves with the machine: the same 6 s ran at 13.8 fps and, an hour later with other
sessions busy, at 2.3. A parallel render is not bit-identical to a serial one after the first
chunk (SSIM 0.98 between them): each segment is its own encode, so a frame's compression no
longer leans on the chunk before it. The drawn picture is the same -- against a lossless still
of t = 30 s both renders score 0.972. `--draft` renders 30 fps.

#### Encoding in the browser: `--encode browser`

`--encode browser` (or `render.encode: "browser"`) has the page encode its own frames with the
browser's hardware H.264 encoder (WebCodecs `VideoEncoder`, `_encode.webcodecs()`) and POST
only the stream, one second of film per POST; ffmpeg wraps it without re-encoding
(`-c copy`), tagging it BT.709. The script's default is still `pipe`; the studio passes `browser` (`studio/tools.py` `RENDER_ENCODE`, since 2026-09-28, after a blind test on three films in `docs/studio-speed.md`). A
browser that cannot encode says `no-encoder` and the render falls back to `pipe`, loudly, for
every remaining chunk.

Why: profiled per frame on one browser (2026-09-28), a frame costs ~3 ms of draw calls, ~50 ms
of actual drawing (deferred until the pixels are read), ~3 ms to copy them out, and ~28 ms to
POST 8 MB to Python and ffmpeg; ffmpeg alone encodes ~170 frames/s. The POST is why `pipe`
stopped scaling: the 33 s Clamly film took 87 s at 3 browsers and 91 s at 6. In the browser
the frame never leaves the GPU:

| film | pipe (today) | browser, 6 jobs |
|---|---|---|
| Clamly, 33 s at 60 fps | 87 s at 3 jobs (145 s with the machine busy) | 26-28 s |
| the 8-minute studio film, 28,800 frames | 2,218 s at 3 jobs (13 fps) | **536 s (54 fps)** |

Quality, scored against the true frames (PNG stills of the same t -- frames are a pure
function of t -- decoded with each file's own colour matrix):

| render | PSNR | SSIM (worst) | size |
|---|---|---|---|
| Clamly, pipe cq 18 | 38.8 dB | 0.967 (0.963) | 108 MB |
| Clamly, browser QP 18 / 17 / 16 | 39.0 / 39.2 / 39.6 | 0.959 / 0.963 / 0.967 | 110 / 141 / 177 MB |
| Clamly, browser at pipe's bitrate (VBR 26 Mbps) | 39.0 | 0.957 | 111 MB |
| 8-min film, one minute: pipe cq 18 | 37.8 | 0.951 (0.907) | 273 MB |
| same minute, browser QP 18 / 20 / 22 | 38.8 / 37.6 / 35.9 | 0.959 / 0.935 / 0.878 | 485 / 373 / 182 MB |
| 8-min film, whole | pipe 38.1 dB, 0.955 (0.938), 2.2 GB | browser QP 18: 38.6 dB, 0.959 (0.956), 3.8 GB | |

QP = cq (`WEBCODECS_QP_OFFSET` 0) is the one setting at least as good as pipe on both films;
its price is file size on a grainy film (+75% here), because a fixed QP spends bits where
NVENC's VBR and adaptive quantisation would not. Viewers get the 5 Mbps web copy either way;
the master's size costs upload time and storage.

The colour matrix: the browser encodes BT.709 and writes no tags; `pipe`'s rgba -> yuv420p is
BT.601, also untagged. Decoded as BT.709 -- what a browser assumes for untagged HD -- the pipe
render is 5.6 levels too dark in green (PSNR 33.6 dB against 38.8 read as BT.601). The browser
path's wrap writes the BT.709 tags; the pipe path is untouched here and still untagged.

What the machine offers (headless Edge, 2026-09-28): H.264 on the GPU in every bitrate mode
including `quantizer`; HEVC not at all; AV1 in software only.

### From the web: `web-grab.py`

A film about something real shows the real thing: its logo, its product, its type. `web-grab.py`
brings each in beside the film's manifest and registers it there, so film.js only names it:

```powershell
python scripts/web-grab.py --manifest <film>/sketch.json --picture <url> --name logo   # web/logo.png, SK.image('web_logo', ...)
python scripts/web-grab.py --manifest <film>/sketch.json --page https://example.com --name site --size 1920x1080
python scripts/web-grab.py --manifest <film>/sketch.json --font "Inter" --weights 400,700
python scripts/web-grab.py --check <url>                                               # allowed? fetches nothing
```

A picture's format is read from its bytes, not its Content-Type: PNG, JPEG, WebP, GIF (first
frame), ICO (its largest size) and SVG, which the browser draws at `--width` as an `<img>` (so it
loads nothing and runs no script) and which is cropped to its own ink. A picture with
transparency is kept as PNG, a large opaque one becomes a JPEG (the bundle inlines every
picture), and nothing is kept larger than 2560 px. A URL that turns out to be an HTML page is
refused with the hint to take the picture's own URL or photograph the page. `--font` asks Google
Fonts as a client that is not a browser: a browser is sent per-script WOFF2 slices, anything else
one whole TTF per weight (Inter: 325 KB, Latin, Cyrillic and Greek). A family Google does not
have still answers 200, with a stand-in served from `/l/font` -- measured with "Helvetica Neue"
-- so only files under `/s/` count and the rest is refused. The manifest's `fonts` resolve beside
the manifest first (`_sketch.font_file`), then in the repo. Every source is in `web/sources.json`.

**`--page` is a real browser, and it measures the brand.** It drives headless Edge over the
DevTools protocol rather than `--screenshot`, because what a site is made of is only known inside
it: WebFetch reads a page as text (instafill.ai came back with "no font specifications"), and the
first film to research its subject then named Poppins as Instafill's font when the page sets its
headlines in Source Serif 4 and its text in the reader's system font. The page reports, measured
in the page: the fonts of its headings, text, buttons and links (by role, weighted by text length
x size -- a whole-page tally put the headline face at 1 % under the body text), the web fonts it
loaded, its text colours, the colours it paints by area (buttons weighted up), its logo and icon
files (header images, `*logo*` images, icons, og:image), and every logo it draws inline as SVG,
serialised with the page's computed fills baked in and rasterised to `web/<name>_logo1.png` (the
page's CSS does not travel with the markup; Cloudflare's cloud and OpenAI's wordmark exist only
this way). Its words go to `web/<name>.txt`, the facts to `web/<name>.json`. A real browser also
reads pages that refuse WebFetch: openai.com answered it 403 and gave the browser the whole GPT-6
Sol announcement. **Every request the page makes is intercepted** (`Fetch.requestPaused`) and
failed unless `_web.public_url` passes its host, so a page cannot make the browser reach a
private address either; the final URL is checked again before anything is kept.

**Only the public internet.** The fetching machine may sit on a private network, and in the
studio the URL is chosen by a stranger's prompt. `_web.py` resolves the host and refuses any
address that is private, loopback, link-local (169.254.169.254, the cloud's metadata service),
shared (100.64/10), multicast or Azure's host address 168.63.129.16, and it does so **at connect
time for every connection, redirects included** -- a name that passed the check and then
resolved to 10.x (DNS rebinding) is refused when it connects, not when it was checked. `ftp:` and
`file:` never reach it (the opener has only http and https). `studio/test_web.py` covers it
offline, including a "public" server redirecting to 127.0.0.1.

### How long a film takes

Machine time for the 60 s film, from its run logs (`--timings` prints them):

| stage | seconds |
|---|---|
| voice (27 takes, scoring, placing) | ~185 |
| soundtrack (first run, incl. sample fetch) | ~80 |
| review stills (per round of 18) | ~9 |
| final render, 60 fps | ~420 |

The rest is authoring. Measured on the second film built with these tools (60 s, clean look,
a brand explainer), wall clock:

| phase | minutes |
|---|---|
| research: the product's claims and their sources, the brand's rules and assets | 9 |
| script + manifest | 2 |
| voice (`sketch-vo.py`, 27 takes) | 5 |
| `film.js`, first pass | 5 |
| review rounds (stills), fixes, score and cue list | 8 |
| final render | 8 |
| **total** | **~37** |

The first film, which produced these tools, took most of a day; the saving is the engine,
the cast, the voice/audio/render pipeline and the traps already paid for.

### The picture: `sketch-render.py`

Bundles engine + props + film + fonts + images + voice timeline + mastered MP3 into
`outputs/<slug>.html` (one file, plays offline) and `outputs/artifact/<slug>.html` (the same
without html/head/body, for claude.ai Artifacts). `--stills` and `--sheet` are the review
loop: 18 stills in 8.6 s. The video is rendered by opening the page in headless Edge/Chrome
(`html-to-image.py`'s browser finder, so no Node and no Playwright): the page draws each frame
and POSTs its raw pixels to a local server here, which pipes them into ffmpeg with
`_encode.video_args`. The mux uses `-t`, never `-shortest` (see the gotchas), asserts the
duration, and adds a soft subtitle track and the poster.

**The first frame is the film's cover.** X, iMessage and a phone's `<video>` before play all
show frame 0 of the file, and a film that opens on bare paper -- most do, the picture is drawn
in -- showed there as an empty rectangle (the Collage launch film on X, 2026-09-30). So frame 0
draws the poster instead (`poster_t`, the payoff), or, when the film ends on paper, the
livelier of a few later moments (0.5/0.65/0.8/0.92 of the film, the tail excluded): the same
rule, and the same 1.4x contrast margin, as the studio's link-preview card (`studio/media.py`),
so the card and the first frame agree. It is one frame -- 17 ms at 60 fps, unseen in play --
and replaces rather than inserts, so duration and sound are untouched; the frame after it is
encoded as a keyframe, because it is a cut. The choice costs one browser and five stills (~7 s)
and is printed with each candidate's contrast. Manifest `cover`: a number is that film time,
`false` keeps the film's own opening; `--from` other than 0 has no cover.

The frames are drawn in chunks (`--chunk`, 8 s of film each), each in a fresh browser: measured
on the 63.5 s air-raid film, a single session fell from 13.8 to 1.5 frames a second and then
stopped answering at frame ~2,700 of 3,810. `--jobs` browsers draw chunks at once (default a
quarter of the logical cores, at most 6), each into its own encoder and segment file under
`temp/`, and the segments are joined by stream copy. One browser is serial -- draw, read the
canvas back, POST 8 MB, wait for the encoder -- so it left most of the machine idle. A film
shorter than jobs x chunk is split evenly across the browsers instead, down to 1 s each.

Every segment's frames are counted (`ffprobe -count_packets`) before it is accepted, and a
chunk that fails or comes back short is redrawn from its start, up to three times -- safe
because every frame is a pure function of t. The count is not paranoia: the first parallel
run produced a segment with no moov atom whose chunk had reported clean, and the join is
where that surfaced. The joined file is counted again against the frame total.

Measured on an i9-11900H (8 cores/16 threads) + RTX 3050 Ti laptop, shared with other sessions:

| render | jobs | wall clock | frames/s |
|---|---|---|---|
| air-raid, 63.5 s at 60 fps | 1 (the old serial path) | 809 s | 4.7 |
| air-raid, 63.5 s at 60 fps | 4 | 269 s | 14.1 |
| 32 s of it, chunk 4 | 2 / 4 / 6 / 8 | 219 / 108 / 102 / 95 s | 8.8 / 17.8 / 18.9 / 20.3 |
| a 5 s studio-length film | 1 / 4 | 28 / 15 s | 10.8 / 20.1 |

Past four browsers the gain flattens, which is why the default is a quarter of the cores.
Speed also moves with the machine: the same 6 s ran at 13.8 fps and, an hour later with other
sessions busy, at 2.3. A parallel render is not bit-identical to a serial one after the first
chunk (SSIM 0.98 between them): each segment is its own encode, so a frame's compression no
longer leans on the chunk before it. The drawn picture is the same -- against a lossless still
of t = 30 s both renders score 0.972. `--draft` renders 30 fps.

#### Encoding in the browser: `--encode browser`

`--encode browser` (or `render.encode: "browser"`) has the page encode its own frames with the
browser's hardware H.264 encoder (WebCodecs `VideoEncoder`, `_encode.webcodecs()`) and POST
only the stream, one second of film per POST; ffmpeg wraps it without re-encoding
(`-c copy`), tagging it BT.709. The script's default is still `pipe`; the studio passes `browser` (`studio/tools.py` `RENDER_ENCODE`, since 2026-09-28, after a blind test on three films in `docs/studio-speed.md`). A
browser that cannot encode says `no-encoder` and the render falls back to `pipe`, loudly, for
every remaining chunk.

Why: profiled per frame on one browser (2026-09-28), a frame costs ~3 ms of draw calls, ~50 ms
of actual drawing (deferred until the pixels are read), ~3 ms to copy them out, and ~28 ms to
POST 8 MB to Python and ffmpeg; ffmpeg alone encodes ~170 frames/s. The POST is why `pipe`
stopped scaling: the 33 s Clamly film took 87 s at 3 browsers and 91 s at 6. In the browser
the frame never leaves the GPU:

| film | pipe (today) | browser, 6 jobs |
|---|---|---|
| Clamly, 33 s at 60 fps | 87 s at 3 jobs (145 s with the machine busy) | 26-28 s |
| the 8-minute studio film, 28,800 frames | 2,218 s at 3 jobs (13 fps) | **536 s (54 fps)** |

Quality, scored against the true frames (PNG stills of the same t -- frames are a pure
function of t -- decoded with each file's own colour matrix):

| render | PSNR | SSIM (worst) | size |
|---|---|---|---|
| Clamly, pipe cq 18 | 38.8 dB | 0.967 (0.963) | 108 MB |
| Clamly, browser QP 18 / 17 / 16 | 39.0 / 39.2 / 39.6 | 0.959 / 0.963 / 0.967 | 110 / 141 / 177 MB |
| Clamly, browser at pipe's bitrate (VBR 26 Mbps) | 39.0 | 0.957 | 111 MB |
| 8-min film, one minute: pipe cq 18 | 37.8 | 0.951 (0.907) | 273 MB |
| same minute, browser QP 18 / 20 / 22 | 38.8 / 37.6 / 35.9 | 0.959 / 0.935 / 0.878 | 485 / 373 / 182 MB |
| 8-min film, whole | pipe 38.1 dB, 0.955 (0.938), 2.2 GB | browser QP 18: 38.6 dB, 0.959 (0.956), 3.8 GB | |

QP = cq (`WEBCODECS_QP_OFFSET` 0) is the one setting at least as good as pipe on both films;
its price is file size on a grainy film (+75% here), because a fixed QP spends bits where
NVENC's VBR and adaptive quantisation would not. Viewers get the 5 Mbps web copy either way;
the master's size costs upload time and storage.

The colour matrix: the browser encodes BT.709 and writes no tags; `pipe`'s rgba -> yuv420p is
BT.601, also untagged. Decoded as BT.709 -- what a browser assumes for untagged HD -- the pipe
render is 5.6 levels too dark in green (PSNR 33.6 dB against 38.8 read as BT.601). The browser
path's wrap writes the BT.709 tags; the pipe path is untouched here and still untagged.

What the machine offers (headless Edge, 2026-09-28): H.264 on the GPU in every bitrate mode
including `quantizer`; HEVC not at all; AV1 in software only.

### How long a film takes

Machine time for the 60 s film, from its run logs (`--timings` prints them):

| stage | seconds |
|---|---|
| voice (27 takes, scoring, placing) | ~185 |
| soundtrack (first run, incl. sample fetch) | ~80 |
| review stills (per round of 18) | ~9 |
| final render, 60 fps | ~420 |

The rest is authoring. Measured on the second film built with these tools (60 s, clean look,
a brand explainer), wall clock:

| phase | minutes |
|---|---|
| research: the product's claims and their sources, the brand's rules and assets | 9 |
| script + manifest | 2 |
| voice (`sketch-vo.py`, 27 takes) | 5 |
| `film.js`, first pass | 5 |
| review rounds (stills), fixes, score and cue list | 8 |
| final render | 8 |
| **total** | **~37** |

The first film, which produced these tools, took most of a day; the saving is the engine,
the cast, the voice/audio/render pipeline and the traps already paid for.

### Motion-design films: a square frame, 3D pieces, cut-out people, music only

The first film made this way is a 26 s speaker promo for Web Summit 2026 (`projects/websummit-speakers/`,
local): the structure of a motion designer's After Effects promo for another conference -- logo on
a moving pattern, the date as 3D type, a creature carrying a ticket, a speaker carousel with a
name block that turns, the ticket, a poster -- rebuilt in the conference's own look. Its film.js is
written for any frame: every scene reads `SK.W`/`SK.H` (`CX`, and `WIDE` where a landscape frame
wants a different layout -- a wider ring, a counter beside the name block, a poster with the speakers
on its right), so the one film renders 1920x1080 for YouTube or 1080x1080 for a feed by changing
`"frame"`. Five pieces it needed that the engine did not have; each is general.

**A frame of any shape.** The manifest's `"frame": [1080, 1080]` (or `[1080, 1920]` for a
vertical film) sets the canvas, `SK.W`/`SK.H`, the player's aspect, the renderer's window, the
raw-frame size and the browser encoder's size; 1920x1080 without it. `_sketch.frame(m)` refuses
an odd, tiny (< 320) or huge (> 3840) side. Everything drawn in `SK.W`/`SK.H` terms follows; a
film written for 16:9 in literal pixels does not.

**`sketch/space.js`: 3D for motion design.** Canvas 2D has only affine transforms, so a face in
perspective is drawn into an offscreen canvas (`SK.drawInto` points every engine primitive at it)
and laid onto its projected quad as a grid of cells, each with its own affine map. The camera
(`SK.view3({x, y, z, yaw, pitch, roll, d, zoom, sx, sy})`) looks along +z at a target that lands
at (`sx`, `sy`) -- the frame's middle unless set -- where a face at the target's depth is drawn at
scale 1, so a 3D piece lines up with 2D drawing around it. `sx`/`sy` are what let a name block sit
low in the frame while the camera looks at it level: moving the target instead looks down on it
and shows a top face as deep as the block.

- **Cells overlap; they are not clipped.** The first version clipped each cell's two triangles
  (grown 0.6, then 1.1 px from their centroids) and left a hatch of faint ground-coloured lines
  along every diagonal of a cream name block and boarding pass: growing a thin triangle about its
  centroid barely moves its long edges. Now each cell draws its whole source rectangle, 1.5 px
  over its edges, with the mean of its two triangles' affine maps, unclipped: neighbours cover
  each other's anti-aliased edges, and the mean splits the perspective error between the corners.
  A see-through face (`alpha` < 1) is laid down whole on its own layer and faded as one, or the
  overlaps would show.
- **A box that turns to the next name** (`SK.box3`, the carousel's name block) is square in plan,
  so a quarter turn brings a face of the same width to the front. At rest the side face is seen at
  ~30 degrees, compressed to half its width, so its type is drawn 1.55x wide (`SIDE_STRETCH` in
  the film) and reads as normal; the face that is about to come round shows its old words fading
  out, is blank edge-on, and wipes its new name on as it arrives.
- Lighting is Lambert against `o.light` over `o.ambient`, as a dark wash over the face.
  `SK.fx(fn, {blur, smear, angle, dx, dy, alpha})` draws `fn` on its own layer and lays it down
  blurred (canvas `filter`) or smeared along a direction (copies averaged): a whip pan between two
  scenes is two smeared layers sliding past each other.

**People cut out of their photos: `scripts/portrait-cutout.py`.** A conference's headshots come
in every crop and background. It mattes each person off with a local BiRefNet ONNX model (nothing
leaves the machine), and with `--frame` puts every face at the same place and size: YuNet finds
the eyes, `--face 0.30` of the side is the face's width, `--eyes 0.42` the eye line. The
photographer's crop across the body is faded out, and a photo cut so tight that the fade would
land above `--floor 0.85` is scaled up until it does not (4 of 19 speakers, x1.07-1.23). `--tone
mono` makes the person black and white (the colour stays in the film's own circles), `duo:#a,#b`
a duotone. Measured on 4 headshots cut to 800 px and laid on magenta and teal: `birefnet-lite`
(224 MB, 10.5 s a photo on this laptop's CPU) and `birefnet-portrait` (973 MB, 18.9 s) could not be
told apart at the hair, so lite is the default. `--plan` prices a run; a missing model prints its
download command. The cut-outs join the manifest's `images` and are drawn inside a clip.

```powershell
python scripts/portrait-cutout.py --src projects/<id>/sources/speakers --out projects/<id>/images/speakers --frame --tone mono --plan
python scripts/portrait-cutout.py --src projects/<id>/sources/speakers --out projects/<id>/images/speakers --frame --tone mono
```

**A film with no narration.** Leave out `vo`: sketch-audio mixes the score and the effects and
masters them, and nothing is ducked. Its cues then come from film.js's own clock rather than a
voice timeline -- written by the film itself (below), so every click lands on its flap's frame.
The score was checked against the reference promo's own soundtrack with a band-by-band spectrum
(each band relative to its own total): the first mix sat 7-20 dB brighter above 1.6 kHz and thin
below 630 Hz. The synthesised snare, clap and hats are band-passed noise and carried the top end,
so the project's `KIT_GAINS` hold them at .16-.45; and the General MIDI basses carry almost
nothing under 60 Hz, which is where a produced track keeps its weight, so the score engine gained
one instrument that is not a sample: `sub_bass`, a sine with a trace of its 2nd and 3rd harmonics
(`_sketchaudio.SYNTHS`; check-sketch asserts it sounds at its note and needs no download). The
effects were set by their level over the music at their moment: impacts +1 to +4 dB, the whip
+6.5, a turn's swoosh and thunk 4-7 dB under.

**A film that is a template: its content in `"data"`, its sound from its own code.** For kitcut.ai's
templates the promo was made so another conference is a data edit, proven by rendering it both ways:
with the Web Summit content moved out of the code it reproduces the approved master at 60 moments in
both frames (118 of 120 stills pixel-identical, the other two one level off), its score byte for byte
and its 275 sounds exactly.

- `"data": {"content": "content.json"}` in the manifest: each named JSON file is the film's
  `SK.DATA.<name>`, inlined into the page in a script block of its own before the engine's film code
  runs (`sketch-render.film_data`). The promo's `content.json` holds every word (`event`, and `copy`
  for the labels, whose `{year}`/`{city}`/`{city_code}` are filled from the event), the `palette`,
  the `logo` and the `speakers`. Nothing of the event is left in film.js.
- **Three colours are enough.** `palette` needs `ground` (the dark one the type sits on), `accent` and
  `second`; film.js works out every shade it draws (flap cells, the board, shadows, the soft text)
  by HSL lightness from those three unless the file names it, and darkens a ground too light for its
  light type until they reach 7:1.
- **A logo with or without what was measured off it.** `logo.mark` (the symbol as two polygons,
  and the point to dive into) and `logo.letters` (column spans) make the symbol rise and the letters
  rise one by one, as Web Summit's did; without them the whole image wipes on, and the opening dives
  into a disc of the accent instead of the symbol's peak.
- **Content that never moves the clock.** The carousel always makes 5 stops: the speakers with a
  `name` are the featured, in order, and fewer than five come round again (the counter reads 01/03,
  02/03, 01/03...); the ring always has at least 12 slots, repeating people when a line-up is short;
  a long city or venue name is fitted, not cut. So the timing, and every sound on it, is the same
  for any content -- checked with a made-up Helsinki event, three featured of seven, a green and
  orange palette and a logo with no measurements.
- **`SK.film({sound: {score(), sfx()}})` and `sketch-render.py --sound-data`.** The film returns
  its own score.json object and sfx.json list, worked out from its clock and its content: one flap
  click per letter the board actually flips (from the same `SK.rnd` the picture uses), one pop per
  ring slot, one tick per measured logo letter. `--sound-data` opens the page with `?sound=1` and
  writes the manifest's `audio.score`/`audio.sfx`; then sketch-audio mixes them as any. The project
  scripts `score.py`/`sfx.py` and their hand-copied constants are retired. A sound that repeats
  with the same level and pan is one cue with `times` (render_sfx already played them), which took
  the promo from 275 cues to 143, under the studio's 200.

```powershell
python scripts/sketch-render.py --manifest projects/<id>/sketch.json --sound-data
python scripts/sketch-audio.py  --manifest projects/<id>/sketch.json
```

**A copy to post: `sketch-render.py --web`.** The browser-encoded master of a 1080x1080 60 fps
film runs ~31 Mbps (26 s: 110 MB). `--web` writes `<slug>_web.mp4` beside it through `_encode`,
capped at 8 Mbps (`WEB`; a manifest `web` block overrides): 25.6 MB, VMAF 98.3 against the master.

Rendering is quick: 1,560 frames of the square promo in 16 s at 60 fps (4 browsers, encoded in
the browser), stills at ~3 a second.

### Collage films: cut-outs and mixed media (`sketch/collage.js`)

A collage film animates pictures cut out of paper rather than whole painted scenes: each
picture is one object (an engraving, a product photograph) with a transparent background and a
white scissor-cut border, pinned onto coloured sheets with torn edges, and the motion design is
everything around it -- display type, tape labels, rubber stamps, marker arrows, ransom-note
letters, halftone dots, a running timeline. `SK.setStyle('collage')` turns it on; the pieces are
`sketch/collage.js`, an engine module: the manifest's `"modules": ["collage"]` has the bundler
load it after engine.js and props.js, so film.js can override any piece (the film's engine
copy of it when it has one, `sketch/collage.js` otherwise). A film that does not ask for it
does not carry it.

**Why it exists.** On 2026-09-28 a Runway employee (@notiansans, status 2104676565829505527)
posted a 60 s "newspaper cutout / mixed media" history of ice cream made by Opus 5.5 with the
Runway MCP, prompt verbatim: *Create a [60 second] motion graphic explainer video about [the
history of ice cream from the inception, to present day]. All of the visual images should be
handled by Runway, and all the motion graphics elements and animations should be handled by
you. The art style should be [newspaper cutout / mixed media aesthetic] with a high degree of
polish.* Measured off the post (1440 frames, 24 fps, 1080p): ten chapters of about 5 s, one per
narration line (136 words over a swing groove, visuals cued to words); 18-20 cut-outs, each with
a white scissor-cut border and a paper shadow; every piece shifts by a pixel or so on every
second frame (frame differences alternate ~1 and 4-14 grey levels) and the grain re-rolls at
12 fps -- stop motion on twos. Runway's hosted MCP (`https://mcp.runwayml.com/mcp`, OAuth,
Pro/Max plans) lists `generate_image`, `remove_image_background`, `generate_speech` and
`generate_music`, which is every asset in the film; the post does not say what rendered it.
Everything else in it was already this engine's: the page is code, frames are a pure function
of t, the voice is timed word by word. What was missing -- pictures as cut-outs, the collage
pieces, print typefaces and the 12 fps nudge -- is this section.

**The pieces.** Every one takes `in` / `out` specs `{t, type, d, from, dist, spin}`, `rot`,
`s`, `alpha`, `nudge` (0 for none), and draws centred on its x, y:

| piece | what | notable options |
|---|---|---|
| `SK.cutout(name, x, y, w)` | a cut-out picture with its paper shadow | `shadow` (fractions of its long side), `flip` |
| `SK.sheet(x, y, w, h)` | a sheet of paper; torn sides show a white fibre rim | `col`, `edges` ('tblr', '' for cut), `amp`, `rim`, `tex`, `light`, `seed` |
| `SK.tape(text, x, y)` | a strip of paper or tape carrying words; returns {w, h} | `font`, `size`, `col`, `ink` (reads on col by default), `ends` (cut, torn, zig), `distress` |
| `SK.headline(text, x, y)` | display type in one piece | `font`, `size`, `italic`, `ls`, `align`, `distress` (letterpress), `stroke`, `maxW` |
| `SK.stamp(x, y)` | a rubber stamp printed in ink (multiply) | `shape` (circle, rect), `text`, `top`/`bottom` (round the ring), `col`, `t` (its hit) |
| `SK.burst(x, y, r)`, `SK.disc` | a starburst; a hand-cut paper circle | `spikes`, `inner`, `col`, `spin` |
| `SK.halftone(x, y, w, h)` | printed dots fading away from a side or corner | `from`, `step`, `max`, `pow`, `angle` |
| `SK.ransom(text, x, y)` | letters cut from different pages, landing in turn | `size`, `fonts`, `cols`, `stagger` |
| `SK.mark(pts)`, `SK.arrow(x1, y1, x2, y2)` | a marker line drawn on | `in.d`, `col`, `w`, `head`, `bow` |
| `SK.maskingTape(x, y, w)` | translucent masking tape with torn ends | `rot` |
| `SK.newsprint()` | a newspaper page behind everything | `text`, `heads`, `headEvery`, `cols`, `size`, `ink` |
| `SK.layer(o, fn)` | a group: everything fn draws moves, enters and leaves together | `w`, `h` (for a wipe), `steps` |

`SK.motion(o, t)` is the state behind every entrance, `SK.place(o, w, h, fn)` draws in an
element's own frame, `SK.step(t)` holds t on a 12 fps clock, `SK.nudge(seed)` is the per-piece
shake. Entrance types: `pop` (overshooting scale and a turn), `grow`, `drop` (falls onto the
page and settles), `slap` (a label slapped down), `thump` (a stamp), `slide` (a sheet from a
side, landing with no overshoot), `wipe` (revealed from a side), `rise`, `fade`, `none`.

**The stop-motion feel is the style, not the film.** Under `collage` every piece is nudged
(~1 px, ~0.2 degrees) twelve times a second, entrances run on the same 12 fps clock (a layer
with `steps: 0` moves smoothly: a full-width sheet stepped at 12 fps jumps 240 px a frame), the
grain re-rolls at 12 fps (`style.grainFps`) and there is no handheld camera. Render at 24 fps,
like the reference; it also halves the frames against 60.

**Cut-outs** are painted by `sketch-paint.py` (see above): `"cutout": true` on an image, the
block's `"cutouts"` for the model, quality, border and cut. The default model,
`openai/gpt-image-2.5-flare`, is asked for `background: transparent` because OpenRouter's
catalogue lists it; any model without it is asked for a white ground, keyed off it
(`matte_white`: the near-white region connected to the picture's edge), and the paper border
covers any hole the key leaves where the subject's own white touched the ground. Then specks
under 1.5% of the subject are dropped, the subject is trimmed and scaled to 1024 px, and a
border of `border` px is cut round it: the mask dilated by the border, closed over notches up
to ~5 borders wide (scissors do not follow every notch) and simplified to straight snips
(`approxPolyDP`) for `scissor`, or left smooth for `round`. Saved as WebP with alpha: 70-340 KB
each, against 1.1-1.8 MB for the PNG the model sends.

Measured (2026-09-28): 17 cut-outs for the example film at medium quality, $0.197 in all
($0.0107-0.0137 each), 78 s of wall clock four at a time; one repaint $0.011. Tested both ways
on three subjects (an engraved freezer, a photographed cone, an engraved portrait): Flare's
alpha and Muse-on-white keyed by `matte_white` both came out clean enough that the border hid
any difference. Flare takes 16 reference pictures; Muse takes none but has the most detail per
dollar. One cut-out of 17 came back with a white paper shape painted behind it (an engraving
of barley); "drawn alone with nothing behind it" in the prompt fixed it.

**Fonts** (`fonts/SOURCES.md`): Abril Fatface (headlines), UnifrakturMaguntia (mastheads),
Oswald (labels), Old Standard TT (body, datelines, with an italic), Playfair Display (italic
kickers, heavy display in Cyrillic), Courier Prime (typewriter), with Anton and Caveat already
here. Only Oswald, Old Standard TT and Playfair Display carry Cyrillic. A manifest font entry
takes `"style": "italic"` for an italic face of a family.

**Performance.** Each sheet, sticker, stamp, burst, dot field and label is drawn once per render
chunk into an offscreen canvas with its shadow baked in; a frame is then a few dozen
`drawImage` calls. The 66 s example (1584 frames) renders in 24-28 s with six browsers
encoding in the browser (57-67 fps) on the laptop; a round of ten review stills takes ~8 s.

**The example**, `config/sketch/collage-example/` (made as the local project
`collage-paperwork` and copied in): "A Brief History of Paperwork", 66 s, eleven
narration lines (Gemini 3.1 Flash TTS, Charon, $0.07), 17 cut-outs, ten scenes, a timeline
ruler, a swing score from a chord chart (`score.py`) and 109 sound cues computed from the word
times (`sfx.py`). `film.js` is ~320 lines: a `scene(t0, from, draw)` per sheet, drawn inside
one sliding `SK.layer`, older scenes first. Built in one evening together with the pieces
themselves; the review rounds are in the project journal.

**The studio makes them too** (`studio/looks/collage.md`, the third look). Given the Runway
post's own prompt, 60 s, the studio (Opus 5.5, CLI, 2026-09-28) planned ten pages, chose one
medium for all 17 cut-outs ("hand-tinted antique copperplate engraving", none repainted, $0.20),
and invented its own furniture with the pieces: a newspaper header and footer on every page, a
flip counter of years, a code-drawn thermometer that falls to -21 C as "ICE + SALT" lands, a "?"
burst that turns into the waffle cone. 21 minutes from prompt to MP4 (Claude 20.3, render 1.0),
43 turns, Claude $4.43 at API prices, voice $0.11, -14.0 LUFS. It recorded the narration four
times to fit (Gemini's pace again) and once asked the drum kit for a `crash` it does not have;
`validate.py` now names an unknown drum before the soundtrack is rendered.

**Made to sell (2026-09-29).** Four changes before the look is offered:
- **Cyrillic.** Abril Fatface, Anton, Courier Prime and UnifrakturMaguntia have no Cyrillic
  (fontTools over the Ukrainian alphabet), and the pieces default to Abril, so a Ukrainian
  headline fell back to a system face. `SK.face(family, wt, text)` now sets a line with
  Cyrillic letters in a stand-in from `SK.NO_CYRILLIC` -- Playfair Display 900, Oswald 700,
  Old Standard TT 700, IBM Plex Mono (added) -- in every piece: headline, tape, ransom,
  stamp, newsprint. `check-sketch` holds the table to the font files. `SK.txt` and a film's
  own canvas text do not swap: the brief says to give them a face that has the letters.
- **The clock at 30 fps.** 12 ticks a second hold 2 frames then 3 at 30 fps (a Free film).
  `SK.stepFps(want)` picks the rate nearest 12 that divides the frame rate being rendered
  (`SK.FPS`, which the player sets for `?export` and `?encode`): 12 at 24 and 60 fps, 10 at
  30. Stills, which have no rate, keep 12.
- **Less newspaper.** The only collage example is a newspaper, so the studio's copy of it
  (`agent._reference`) leaves out what is marked `// studio: cut` ... `// studio: end cut`:
  the "Daily Form" front page and closing page, the newsprint under every page, and three
  of the ten pages. The collage prompt went from 196 KB to 189 KB.
- **Variety.** A collage film records its cut-outs' medium (paint.json `style`), the print
  faces its code names most and whether a newspaper page lies under it; the next collage
  films are told (`recent_note`: "print faces", "a newspaper page under the film: n of the
  last m"), as drawn films are told their grounds.

Traps, each found on the example:
- **A sheet that overshoots bares the page under it** (the first slide bounced 4.5%, 90 px on a
  full-width sheet, and showed the title page at the edge): slides land with no overshoot now.
- **A payoff on a line's last word gets covered** by the next sheet. Start a sheet 0.15 s before
  its line, let a page arrive composed (label, title, main picture ride in on the sheet) and
  land only details on words, and move a big reveal to an earlier word.
- **Text on a card must shake with the card**: the card is its own `SK.layer({nudge: 1})`
  and what is written on it takes `nudge: 0`, or the words drift across the paper.
- **Gemini narration ran 24% longer than `--plan`'s 2.6 words a second** (140 words: 72 s, not
  58 s); a "brisk" style note barely moved it. Budget ~1.9 words a second.

### Talking heads: photos that speak (`sketch/heads.js`, `head-rig.py`)

A photo of a person becomes a character who talks in the film: the head cut out of the photo
and stuck on a drawn body (a bobble-head), a cut-out whose chin drops like a puppet's, a
ventriloquist's dummy, a head whose top lifts off like a lid (South Park's Canadians), or the
whole photo -- a newspaper picture, a painting in a frame -- where only the mouth moves (the
Clutch Cargo / Painty the Pirate trick). Several speakers in one film each get their own voice,
and each mouth moves only on its own lines. No video model is involved: the photo is measured
once on the CPU, and the engine animates it as a pure function of t like everything else.

```powershell
python scripts/head-rig.py --fetch-models                                   # once per machine
python scripts/head-rig.py --manifest projects/<id>/sketch.json --list     # which rigs would be built
python scripts/head-rig.py --manifest projects/<id>/sketch.json --sheet    # build + a proof sheet each
python scripts/sketch-vo.py --manifest projects/<id>/sketch.json           # "cast" + "who": one voice each
python scripts/sketch-render.py --manifest projects/<id>/sketch.json --stills 1,3 --sheet
```

**The rig** (`head-rig.py`, a folder per photo under `rigs/<name>/`, rebuilt only when the
photo or `RIG_VERSION` changes): OpenCV's YuNet finds the face -- small ones in big frames too,
which MediaPipe's own detector missed on a 1905 glass plate -- then a square crop 3.1 faces wide
goes through MediaPipe's face landmarker (478 points) and its multiclass selfie segmenter (hair,
face skin, body skin, clothes, other, background). The head is hair + face skin + things worn,
kept only where it touches the face, only inside a head-shaped ellipse (a grey studio wall and a
painted backdrop were both called hair and joined the head until then), cut at the jaw line
(carried outwards and *down* past the jaw angles: level, it took the ears off), holes filled and
the edge snapped to the photo's own edges by a guided filter. `rig.json` holds, in the photo's
pixels: the face outline, the lips (inner and outer, upper and lower), lids, brows, irises, the
face's own axes (`right`, `down`: the face may be tilted), the jaw piece each rigid mouth moves,
the flap's cut (from the mouth corners out to the silhouette's edge, measured on the mask), and a
mesh: the 468 face points plus a still ring round the face, Delaunay-triangulated, with the
inner mouth left as a hole, and per point how far it follows the jaw (`wj`), the upper lip's
lift (`wu`), the lips spreading (`wc`) and a blink (`b`). ~1-2 s a photo on the laptop CPU.

A photo of several people is several rigs: `"face": n` counts the photo's people left to right
(faces at least a third the area of the biggest; a passer-by or a face on a poster is not one
of them), so two founders photographed together are `"face": 0` and `"face": 1`. The rig says
how many there were, and warns (`warnings` in rig.json, printed by the build) about a face
turned from the camera (the nose over 45% of the half-face off centre: a mouth moved on it reads
best small or as a puppet's; on the Curies' 1904 lab photo Marie, looking down at her work,
measured 149%) and about a head the photo cuts off (a cut-out of it has a straight edge there).

Runtime: MediaPipe 1.0.1's wheel asks for `opencv-contrib-python`, which would fight the venv's
`opencv-python` over the one `cv2` (and `setup-python.ps1`'s pip-check repair would install it),
so `--fetch-models` installs it `--no-deps` into `models/heads/py/`, beside its two models
(`face_landmarker.task`, `selfie_multiclass_256x256.tflite`, both Apache-2.0), and only
head-rig.py puts that folder on `sys.path`. Its vision package imports matplotlib for drawing
helpers never called here; a missing matplotlib is stood in for.

**The voices.** `vo.cast` names each speaker's voice, laid over the film's own, and each line
says who speaks it (`sketch-vo.py`):

```json
"vo": {"tts": "gemini", "voice": "Kore",
       "cast": {"alex": {"voice": "Puck"}, "ada": {"voice": "Kore", "style": "dry, amused"}},
       "lines": [{"who": "alex", "text": "..."}, {"who": "ada", "text": "..."}, {"text": "narrator"}]}
```

Every cast voice is checked before anything is spent; a speaker's voice is part of its lines'
cache key (the narrator's lines keep theirs, so an existing film re-renders nothing); a Gemini
refusal in a film with a cast takes the backup voice by the speaker's label (the film's takes
are several people's, so their measured pitch means nothing). The timeline keeps each line's
`who`.

**The mouth** (`scripts/_heads.py`, at bundle time, cached by the line's audio): every voice-over
line gets its speaker and a 50 Hz mouth track measured from its own audio -- `o`, the speech
band's (250-3500 Hz) loudness on a scale set by the line's own loud parts (a quiet voice opens
as wide as a loud one), shut where the voice stops and on the m/b/p that are quiet in that band;
`w`, the share above 1.8 kHz against below 900 Hz (spread lips on "ee" and "s", rounded on "oo"),
opening faster than it closes, 80 ms ahead of the sound. Measured on edge voices: open ~60% of
the way mid-speech, 3-4 openings a second, which is the syllable rate. `SK.talk(who, t)` reads
it; `SK.speaker(t)` says who is talking.

**Measured against a real mouth** (`mouth-bench.py`: the real lip gap on every frame of a video
of somebody talking, against the track made from that video's own audio). On two phone takes
of a man talking to camera (claude-demo, 83 s): the whole signals barely correlate (r 0.0-0.1),
because a real mouth also opens to breathe before a sentence and holds open between words,
which no sound shows; over the syllable band (2-8 Hz) r peaks at 0.20-0.23 with the real mouth
80-140 ms ahead of its sound. The first lead, 40 ms, was late by that much; at 80 ms the frontal
take is in step and the other within 60 ms. What this says: the mouth opens and shuts on the
syllables, at the right moments -- it does not shape the vowels, and a photo made to talk this
way reads as a puppet or a talking painting, not as the person. `--sweep` prices the track's
other knobs (range, curve, attack, release) on the same footage; none moved r by more than 0.03.

**Drawing** (`SK.head(name, x, y, h, o)`, the module added by itself when a manifest names
"heads"): `x, y` is the middle of the face (hairline to chin), `h` its height; `SK.headBox`
gives the whole head's box (hair included) to lay heads out with. `style`: `cutout` (with a
paper edge and a shadow), `photo` (`crop` in face heights), `bobble` (a body drawn in the film's
own pen under the chin, the head on a spring: it nods on each of its speaker's words). `mouth`:
`warp` (the photo's own lips part and its jaw drops through the mesh; the dark of the mouth,
teeth lit like the face and a tongue drawn under it), `chin` (a puppet's chin drops between the
mouth corners), `dummy` (the same with the slits drawn), `muppet` (the whole lower face drops),
`flap` (the top of the head lifts off), `none`. `tone`: `color`, `mono`, `sepia`, `news`
(halftone dots on a 45-degree screen sized to the face). Eyes blink on a clock seeded by the
rig's name; a collage film's mouths move on its 12 fps clock and nudge with its pieces.

Traps, each found on the test footage:
- **A mesh triangle bridging the lips** smears lip across the open mouth and hides the teeth
  (seen on a 3/4 painted face): every lip ring counts, not just the inner one -- no triangle may
  join a point that stays with the skull to one that goes with the jaw between the corners.
- **A rigid jaw cut into two complementary pieces leaves a seam** (both pieces' anti-aliased
  edges let the background through): draw the whole picture, the dark over the gap, then the
  jaw piece on top.
- **Nearly shut, a rigid jaw is a red scar**: below 14% open it stays shut.
- **Levels from the whole picture print a backlit face black** in `news` and `mono`: they are
  taken from the face's own box.
- **A white teeth band glows in a dim photo**: teeth take the face's skin colour, lightened.

**Characters drawn from the photo** (`"look"` on a head, `scripts/_toon.py`,
`config/heads/looks.json`). The owner's verdict on the first round (2026-09-30): the photo that
talks and the photoreal models look cringe; the drawn looks are the product. So a head can be
the person *redrawn*: `"heads": {"alex": {"photo": "sources/alex.png", "look": "brick"}}`. An
image model (gpt-image-2.5-flare through OpenRouter, the photo -- cropped to that person, head and
shoulders -- as its reference) draws the character, then draws it four more times with one change
each: the mouth a little open ("eh"), open ("ah"), rounded ("oo"), and the eyes shut. The edits
come back aligned to within half a pixel (phase correlation over 15 pairs: 0.1-0.4 px), so only
what changed is kept: MediaPipe's landmarks on the drawn character place a window round the mouth
(or each eye), the change inside it, joined to an ellipse there, grown and feathered, becomes a
patch. The film draws the character and lays the mouth the voice asks for over it -- shut under
15% open, "oo" when the lips round, "eh" under half open, "ah" above -- changing on twos (12 a
second) like stop-motion replacement mouths, and the blink patch on the rig's blink clock.
Looks: `brick` (a toy brick minifigure), `blocky` (a voxel game character), `newspaper` (a
stipple "hedcut"), `caricature`, `clay`. Prompts name objects, never trademarks (check-sketch).

Measured on three people (a phone frame, a NASA portrait, a 1905 glass plate) and a painting:
likeness held in every look; the landmarker found the face on 12 of 15 drawn characters as drawn
and on the stipple portraits once their dots are blurred into tones; every mouth patch and blink
landed. A character costs five pictures, **$0.11** (0.022 each), 30-60 s; everything is cached by
photo, prompt and model, so a rebuild is free. The picture is cropped to the character's outline
(it comes with wide empty margins) so `SK.headBox` lays it out by what is visible.

Traps: **the photo leaves the machine** (to the image model) -- the one step in talking heads that
does; **OpenAI's safety filter refuses some pictures, not repeatably**: an edit refused once was
drawn on the next try (so a refusal is retried twice), but the 1840 Lovelace portrait (bare
shoulders) was refused as a toy brick figure four times in a row while two photographs went
through; the build names the head it could not make and carries on with the rest. A picture the
model redraws whole (a stipple portrait re-stipples everywhere) still swaps cleanly, because only
the window round the mouth is ever taken from the edit. Search the change globally and a stipple
portrait's noise wins: the first cut put one mouth in an image corner.

**The example**, `config/sketch/heads-example/`: "The Brothers Speak", 9.5 s, a 1903 front page
(collage) whose two public-domain photos of Wilbur and Orville Wright talk in halftone, one
voice each (edge, free), a stamp on "seconds" from `sfx.py`. `wilbur.landmarks.json` is the
face measured once from its photo: `check-sketch.py` tests the cuts, the mouth hole and the
blink against it without MediaPipe. A 13 s six-style test on a phone frame and a painting took
27 s to render at 30 fps on the laptop; ten review stills ~5 s.

**In the studio** (kitcut.ai's "Add a person"): a film request may carry `people` (up to
`film.MAX_PEOPLE` = 4 image uploads, each with an optional name) and `character_style` (`auto` or
one of `config/heads/looks.json` `"studio"` -- the thirteen drawn looks, in the site's order; the
toy-brick and voxel ones stay for local films). `Film.create` copies each photo to
`inputs/person<i>.<ext>`, writes it into the manifest's `heads` as `p1..p4` (and `images`, the
fallback), and adds the `people` capability (`film.CAPS`): the `heads` engine module and
`studio/people.md` in the brief, so a film without people keeps a byte-identical prompt. `auto`
is the look's nearest style (`film.PEOPLE_AUTO`: crayon, watercolour, paper cut-out). The
characters are drawn in the background as the film starts (`agent.draw_people`: `head-rig.py
--jobs 4`, one person refused is tried once more as a sticker), into `rigs/ready.json`; the
picture tools wait for it (up to 7 minutes, off the film's clock) and tell Claude, once, who could
not be drawn -- that person is shown with `SK.image` instead. Claude reads the photos, writes
`vo.json` with a `cast` voice per person and `who` on their lines (`validate.py` checks both), and
places them with `SK.head`. Spend is `rigs/spend.jsonl`, counted by `agent.price`. `/api/limits`
publishes `people` (count, styles, auto, name length); the site holds its list to it. Measured on
a 20 s film with two people (a phone frame and the 1840 Lovelace painting, crayon): both drawn in
parallel before Claude needed them, $0.22 of pictures, 38 turns, 15.5 minutes in all.

The site's style tiles are cut from the thirteen-looks film with `speaker-loops.py`: each
speaker's own line, cropped square and looped, silent, with a poster frame. `--cycle <name>`
makes the "Add a person" tile's one loop instead: every style talking for `--step` (1.95 s) and
dissolving into the next over `--fade` (0.35 s), the last back into the first, trimmed so the
loop point falls between two identical frames (25 s, 246 KB for thirteen). Each window is one
step plus one dissolve and must end `--clear` (0.45 s) before the film's next line, when the next
character arrives -- `--list` names any that would not (`--trim-in 0.2` fits all thirteen).

```powershell
python scripts/speaker-loops.py --page <film>.html --video <film>.mp4 --outdir <site>/people `
    --crop 960,450,720 --size 200 --only crayon,papercut,news --rename news=newspaper --list
python scripts/speaker-loops.py --page <film>.html --video <film>.mp4 --outdir <site>/people `
    --cycle cycle --trim-in 0.2 --only crayon,papercut,news,woodcut,watercolour,popart,courtroom,chalk,sticker,felt,knit,peg,sock
```

### Sketch Studio: a prompt box that makes a short film (`studio/`)

A prompt-to-film web app on this engine, set up with `pip install -r requirements-studio.txt`:

- `python studio/server.py` (or `studio\serve.ps1`, with a public tunnel) serves a page on
  127.0.0.1:8765 with one prompt box and a JSON API; the public site is create.kitcut.ai.
- Claude (always Opus 5.5, `MODEL` in `agent.py`), through the Claude Agent SDK, writes the
  narration, `film.js`, `score.json` and `sfx.json` (and for the painted look, the paintings),
  reviews its own stills, and the studio renders the MP4.
- **Several films are made at once, each in a sandbox of its own**: a folder per film under
  `STUDIO_HOME` (its own engine copy, its own Claude session, no shell -- the pipeline is the
  studio's typed tools), a scheduler for the machine (Claude sessions, browsers, CPU), secrets kept
  out of every process that does not need them, an offline renderer the film's code cannot reach
  out of, and every step in a Windows Job Object. The server runs from a release snapshot
  (`studio/release.py`), so edits in the working tree never reach a film being made.
- `python studio/agent.py "<idea>"` does the same from the command line, `--smoke` checks the
  key, and `--auth login` runs on this machine's Claude Code login instead.

`studio/README.md` has the sandbox, the scheduler, the permission model (tested by
`studio/test_guard.py`, `test_isolation.py`, `test_sched.py`, `test_server.py`), the API and the
limits. The pipeline scripts support it generically: a manifest `engine` folder,
`SKETCH_RENDER_OFFLINE`, `SKETCH_WHISPER_DEVICE`, `KITCUT_DOTENV=0`, `KITCUT_LOCKS_DIR`, and
names of paintings and instruments that can never be paths.

Measured on the first two films (one at a time, before narration), wall clock from prompt to MP4:

| film | Claude | render | total | turns | API cost |
|---|---|---|---|---|---|
| paper plane brings coffee (command line) | 113 s | 23 s | 136 s | 20 | $0.56 |
| sticky-note rocket, SHIP IT (web page) | 110 s | 32 s | 141 s | 19 | $0.54 |

Most of the cost is cache reads of the ~100 KB system prompt that carries the engine and the
cast; it depends only on the look, so films made close together share the cache.

**A look is a recipe of capabilities** (`studio/film.py` `CAPS`, `RECIPES`). The person picks a
look (drawn, painted, collage); a capability is one kind of material and everything the studio
does for it -- the engine modules a film carries, the fonts, the pictures it may paint (their
pins, cap and keys in paint.json), the prompt references only its looks' briefs use, and the
choices recorded for the recent-films note. Drawn is `grounds`, painted `paintings`, collage
`cutouts` + `collage`. A film's capabilities are written into its record when it is made, so a
later recipe change never reaches a film in the making. Granting a capability to another look
is a recipe change, and so a brief change: proven with `studio/bakeoff.py` first. Refactored
onto capabilities on 2026-09-29 with the drawn, painted and collage system prompts and new
films' files byte-identical before and after.

At 192k, the AAC encode pushed the rocket's confetti transients to -0.1 dBFS, against -1.5 dBTP
in the master WAV, so the template now encodes at 320k.

#### Pictures and voice notes: `studio/uploads.py`, and choosing a transcriber with `stt-compare.py`

A film request can carry pictures and voice notes as well as words, or instead of them
(`studio/README.md` has the API). A picture reaches Claude as a file it Reads; Claude decides
whether it is material to show (`SK.image('upload1', ...)`), a reference to match, or the brief
itself, and says which. A voice note reaches it written out, by `scripts/_stt.py`: one call over
several engines (`openrouter:`, `gemini:`, `vertex:`, `openai:`, `whisper:`), every note normalised
to 16 kHz mono FLAC first.

`scripts/stt-compare.py` picks the engine instead of guessing. `--make-clips` writes a test set of
film briefs read by edge-tts voices (English, Ukrainian, Spanish, brand names, one over noise, one
silent) encoded as Chrome and Safari record them; every engine hears the same clips, and the table
weighs accuracy 40, names spelt right 15, speed 20, cost 10, robustness 15. Measured 2026-09-26,
eight clips:

| engine | score | WER | names | median s | $/min |
|---|---|---|---|---|---|
| whisper:large-v3-turbo (CPU) | 97.1 | 2.0% | 18/21 | 15.2 | 0 |
| vertex:gemini-3.1-flash-lite | 96.3 | 1.8% | 19/21 | 2.5 | 0.0012 |
| openrouter:openai/gpt-audio-mini | 94.2 | 7.3% | 18/21 | 2.6 | 0.0010 |
| vertex:gemini-3.5-flash-lite | 92.3 | 2.1% | 18/21 | 3.2 | 0.0011 |
| vertex:gemini-3.8-flash | 80.2 | 1.4% | 20/21 | 5.4 | 0.0046 |
| whisper:large-v3 (CPU) | 79.1 | 1.8% | 18/21 | 25.5 | 0 |
| whisper:medium (CPU) | 77.4 | 9.8% | 19/21 | 18.4 | 0 |
| openrouter:openai/gpt-audio | 75.3 | 15.4% | 16/21 | 3.5 | 0.021 |

(Turbo ran on its own; its speed score is against itself, so its total is not comparable -- at
15 s against 2.5 s it is the fallback, not the first choice.) The studio uses Gemini 3.1 Flash
Lite first and Whisper turbo if that fails. Three things the table does not show:

- **Every language model invents words for silence** -- a French sentence, "He is making a lot of
  noise", the list of names it was given as hints. `_stt.transcribe()` therefore asks the Silero
  VAD first and returns nothing for a note with under 0.4 s of speech, without calling any engine.
- **A chat audio model can answer the note instead of writing it down.** A voice note is a film
  brief, i.e. an instruction; `gpt-audio` replied "I'm sorry, but I can't assist with that" to one
  and `gpt-audio-mini` skipped its first sentence. The Gemini models wrote every note down.
- **Whisper medium turned Ukrainian into Russian** (61% WER on the mixed clip).

#### Publishing a studio film to YouTube: `studio/youtube.py`

A person connects one or more YouTube channels on kitcut.ai and publishes a finished film of their
own to any of them. The design and the page are in the site's README ("YouTube"). This is the
studio's half: the bytes, and the draft of the title and description (next section).

- **The site owns everything Google-facing.** It holds the channel grants, sealed in
  `kitcut.youtube_channels`, and opens a resumable upload session with the title, description and
  privacy. It then posts that session's address to `POST /api/films/<id>/youtube`
  `{"to", "key"}`. The studio never holds a Google token. A leaked session address can only
  finish that one upload, into that one channel, within a week.
- **What the studio refuses:**
  - any address that is not `https://www.googleapis.com/upload/youtube/v3/videos?...upload_id=`;
  - a film that is not finished;
  - a client (`X-Client-Ip`) other than the film's own.
- **How it sends.** It streams `outputs/film.mp4` in 8 MiB pieces; the protocol wants multiples
  of 256 KiB. A 308 names the last byte kept. After a 5xx or a dropped connection, the studio asks
  with `Content-Range: bytes */<size>` and carries on from there. A 404 or 410 means the session
  expired.
- **Sends are keyed by the site's post id.** Asking twice sends once, and asking after a restart
  resumes. Sends live in memory only, and the site asks again whenever `GET .../youtube/<key>`
  answers 404.
- **Two things Google decides, not the code:**
  - **The YouTube API audit.** Every video uploaded through an unaudited project created after
    2020-07-28 is locked private. The final answer's `status.privacyStatus` shows it, and the
    page reports it rather than claiming the video is public.
  - **OAuth verification.** Both scopes are sensitive. Until the app is verified, people see an
    "unverified app" screen and at most 100 of them can connect.
- **The test.** `python studio/test_youtube.py` runs a stand-in for YouTube's endpoint that
  half-keeps one piece and answers 503. It checks:
  - every byte arrives in order;
  - a pre-filled session gets only the rest;
  - a repeated key sends nothing new;
  - someone else's send is invisible.

#### The title and description: `studio/ytdraft.py`

The publish dialog opens with a title, a description and tags written from the film, not the
prompt pasted in. Each side brings what only it has:

- **The site brings the channel's voice.** With the `youtube.readonly` scope it already holds, it
  reads the channel's latest uploads (titles, descriptions, tags; KitCut's own earlier posts left
  out, so a pasted prompt cannot teach the voice). It posts them to
  `POST /api/films/<id>/youtube/draft` `{"channel": {"id", "title", "handle"}, "recent": [...]}`.
  Nothing of them is stored on either side.
- **The studio brings the film.** `material()` reads the narration with each line's times
  (`audio/vo/timeline.json`), who it was made for (film.js line 1) and the maker's note under it,
  the paintings' prompts, the pages the facts came from (`web/sources.json` for pages read in the
  browser, `events.jsonl` for WebFetch), what Claude said when it finished (its "please check"
  notes included), the project, and the review sheet as one image. The prompt goes in marked
  private: the request, not the film.
- **One call, no tools.** Opus 5.5 at effort medium: 6-13 s and $0.05-0.13 a draft, measured
  2026-09-28 on five films. Sonnet 5 wrote a correct but plainer draft at half the price; Opus
  followed the channel's own structure ("In this video:", its links, its tagline).
- **`check()` holds the answer to its inputs.** Only links that appear in the channel's own
  descriptions or among the pages read survive; chapters must start at 0:00, be in order and end
  inside the film, or the block goes with its heading; the title is one line cut at a word to 100
  characters, the description 4,500 bytes (the site adds its credit line), the tags 500
  characters counted YouTube's way. A draft that shares a run of 7 words with the prompt that
  the film itself does not say is asked for again once, then given up; the site falls back to
  its own defaults.
- **Kept, and costed.** A draft is saved as `youtube/draft-<channel>.json` in the film, keyed by
  everything it was written from, so asking again is free until the film or the uploads change
  (`ops.sh replace` makes a new one). `youtube_drafts` and `youtube_draft_cost_usd` go on the
  record and the run; on the key the cost joins `cost_usd`, so the day's budget sees it. At most
  12 drafts per film.
- **Try it by hand.** `python studio/ytdraft.py --film <id|folder> --sample-from @handle --plan`
  prints the ask and its price and calls nothing; without `--plan` it writes the draft (on this
  machine's login, not logged). `--sample-from` reads a public channel with yt-dlp.
- **The test.** `python studio/test_ytdraft.py` stands in for Claude: the material, the link and
  chapter rules, the prompt check, the cache, the cost, and the API (owner only, finished only,
  202 then the draft).

#### Workspaces, and the narrator a person picks: `studio/clients.py`, `voice-samples.py`

kitcut.ai makes every film, upload and library a **workspace's** (the site's `lib/orgs.js`): a
person's personal one, or an organisation of several people. The site sends
`X-Client-Ip: o:<workspace id>` (whose film, whose credits, whose library) and
`X-Member: u:<person id>` (who asked).

- **One owner, two names.** A person's personal workspace has the person's own id, and before
  workspaces the site sent the person as `u:<id>`. `clients.canon` makes `u:<id>` and `o:<id>` one
  owner, and every ownership check, library and limit compares with `clients.same`, never `==`. So
  a film made before the switch is still its owner's after it, with no record rewritten.
- **Libraries move themselves.** `library.dir_of` names a library's folder after the workspace.
  The first time a personal workspace's library is used, its old folder (named after `u:<id>`) is
  renamed to it: one rename on one disk, and two servers racing both end with it in place. Where it
  cannot move yet (a file open in it, on Windows), the old folder is used as it is.
- **Uploads are the person's**, keyed by `X-Member` (`server.uploader_of`). The members of one
  workspace never see each other's voice notes, and an upload made before the switch is still
  there after it.
- **Who asked is recorded.** The film's record (`studio.json`) and its run record (`studio_runs`)
  carry `member`.

**The narrator a person picks.** A film request may carry
`voice: {"source": "kitcut", "voice": "<a Gemini voice>"}`: the site's narrator setting, the
project's or else the workspace's (the site's `lib/narrator.js`).
- `server.narrator_of` checks the request. `studio.json` keeps it as `narrator`.
- `Film.vo_pins()` is what `vo.json` must hold: the studio's backend, model and takes, plus that
  voice. `guard.pin_vo` puts it back after every edit and tells Claude it did.
- Claude still chooses the voice direction (`style`) and the `language`. It learns the voice is
  fixed from `agent.voice_note`, in the first message. The system prompt and the voice tool's
  description stay the same for every film, so the prompt cache survives.
- The film's `direction` marks the voice `voice_pinned`, and the recent-films note leaves a picked
  voice out of the voices it counts: it was a person's pick, not a choice for other films to weigh.
- `GET /api/limits` lists the sources this studio knows (`voice.sources`) and KitCut's voices
  (`voice.kitcut_voices`); the site offers no other. No `voice`, or one with no voice in it: Claude
  picks, as before.
- Tests: `test_guard.py` (the pin, the note, the tally), `test_library.py` (the workspace cases).

**Samples for the picker.**
- `python scripts/voice-samples.py [--model M] [--lang en] [--plan]` records one sentence (from
  `config/sketch/voice-samples.json`) in each of the 30 voices. It uses the narration's own path,
  `sketch-vo.py gemini_take`, with no direction, and levels each clip to the narration's level, so
  the voices compare fairly.
- It writes `projects/voice-samples/outputs/<model>/<lang>/` (the clips, `index.json` and an
  `index.html` to listen through). The site commits the English clips as `voices/<Voice>.mp3`.
- Measured 2026-09-30: 30 clips of 6–7 s on `gemini-3.1-flash-tts-preview` (Vertex) cost $0.15.
  All 30 read the sentence word for word (checked with Whisper large-v3 through OpenRouter).
- `gemini-3.8-flash-tts` goes through the Gemini API. This laptop's Google project does not have
  it switched on; the studio VM does, through `GEMINI_API_KEY`. Record the production-model clips
  there.

**A person's own ElevenLabs voice** (`STUDIO_OWN_VOICE=1`). The request's `voice` is
`{"source": "elevenlabs", "voice": <id>, "model": <model>, "jobs": n, "chars": n, "grant": <grant>}`.
The site checked the key, the voice and the characters left before it held any credits, and
minted the **grant**: one film's permission to speak, in that voice and model, up to a character
cap. It never sends the key, and the studio never holds it.
- `narrator_of` checks the shape; `jobs` is clamped to `STUDIO_EL_JOBS_MAX` (4), the lines one
  account records at once. `studio.json` keeps the narrator **without** the grant, which is written
  to `temp/voice.json` (mode 0600) and nowhere else: not in `vo.json`, events, logs or argv.
- `procs.step_env("voice")` for such a film holds `OPENROUTER_API_KEY` (the scorer) and the relay's
  four variables, `ELEVENLABS_RELAY` (`STUDIO_VOICE_RELAY`, default
  `https://kitcut.ai/api/studio/voice`), `ELEVENLABS_GRANT`, `ELEVENLABS_FILM` and
  `KITCUT_SITE_TOKEN`. No studio ElevenLabs key and no Google keys, so a take cannot fall back to
  being paid by the studio.
- Whatever a step prints, a secret it was given comes back as `[redacted]` (`procs.scrubber`: every
  key named in `KNOWN_SECRETS`, the .env's secrets and the film's grant), in what reaches Claude, the
  film's events and the logs. `test_isolation.py` checks it, and that the grant is in no file but
  `temp/voice.json`.
- `sketch-vo.py el_take` sends its normal request to
  `<relay>/v1/text-to-speech/<voice>/with-timestamps` with `Authorization: Bearer <grant>`,
  `X-Studio-Token` and `X-Film` in place of `xi-api-key`. The site's relay checks all three, the
  voice, the model and the cap, then forwards with the workspace's current key and returns
  ElevenLabs' answer as it came. A dropped connection counts as busy, and is retried.
- **Who pays is written per take.** Each take in the person's voice appends a `payer: "user"` row
  to `audio/vo/spend.jsonl` as it is made. `agent.price` counts those as `user_tts_chars`, out of
  `tts_cost_usd`, `cost_usd` and the studio's daily budget: the characters are the person's.
- Models: the site picks `eleven_multilingual_v2` for a professional clone and `eleven_v3` for any
  other voice that lists it (KI-052). The tail word that keeps a line's last syllable follows the
  language (`TAILS`).

**When the voice stops speaking, the film waits.** ElevenLabs' refusal is classified by its
`detail.status` (`BLOCKED_BY`), never echoed: an invalid key, a missing permission, no characters
left, a voice gone, a plan that cannot use it, a blocked account.
1. `sketch-vo.py` prints one `VOICE-BLOCKED {"reason": ..., "status": ...}` line and exits 75
   (`PARK_EXIT`). The takes already made stay cached.
2. `tools.voice` sees it (`voice_blocked`), sets `self.parked`, and answers Claude with a
   `ToolError` that says to stop. `agent.run_claude` raises `Parked` right after that tool result,
   so the session ends whole and can be resumed.
3. `make_film` saves the film `waiting`, with `waiting: {reason, since, text}`. It is not final:
   the slot is free, and the site keeps the film's credits held (its `PARK_MS`, 8 days).
4. The site's **Continue** (`POST /api/films/<id>/continue`, whoever asked for the film) checks
   the voice works, may send a new narrator and grant, and the film goes back in the queue.
   `adopt` starts it with `RESUME_VOICE`: the same Claude session, told to record again (the
   cached takes cost nothing) and carry on. It pays one uncached re-read of the session (KI-053).
5. A film that waits more than `STUDIO_WAITING_DAYS` (7) is put down as failed, and its credits
   come back. Stop works on a waiting film at once.
- Tests: `check-sketch.py` (the relay's headers, the classification with no body leaked, exit 75,
  the per-take rows), `test_server.py` (`paused()`: waiting, not final, Continue, cancel, expiry).

## Projects: one folder and two files per video

Everything about one video lives in `projects/<id>/`: the manifests that drive
the pipelines and two committed metadata files at the top, the gitignored
content below.

```
projects/<id>/
  project.json          current state: renders, what is on them, what controls them
  journal.md            history, addressed to the next session working here
  screencast.json       multicam manifest        (role-named: the folder carries the id)
  clips.json, clips-vertical.json (+ .reframe.json)
  <id>.sync.json, <id>.cuts.json  chapters.txt  description.txt
  sources/  audio/  transcripts/  outputs/  temp/     gitignored content
```

The two metadata files exist because a later session — asked to move a label,
fix one dub line, recut with less air — otherwise has nothing to read: the
knowledge of what is burned onto a render dies with the session that made it.
The previous attempt at this, `config/video-specs.template.json`, was a
hand-authored document that no script read or wrote, and it rotted unnoticed.
That is the design constraint: **every field here is either written by a
script or read on the re-edit path.** The finishing scripts call
`_project.record()` the moment a render or upload lands; the AI adds only what
a script cannot know.

### project.json

| key | |
|---|---|
| `v` | schema version, currently 1; readers ignore unknown keys |
| `id`, `title`, `intent`, `pipelines`, `notes` | what this project is; `intent` and `notes` are prose |
| `inputs` | role → repo-relative path (`screen`, `camera`, `source`, `words`, `bookend-*`, `broll-*`) |
| `controls` | role → the file you edit to change that aspect: `manifest`, `sync`, `cuts`, `reframe`, `caption-style`, `label-style`, `handle-style`, `chapters`, `description` |
| `deliverables` | keyed by output path — the heart of the file, one entry per render |

Each deliverable:

| key | |
|---|---|
| `kind` | `captioned`, `short`, `short-dubbed`, `screencast`, `dub-audio` — a new pipeline adds a new string, nothing structural |
| `status` | `current` \| `superseded` \| `deleted`. Scripts only ever upsert `current`; demoting is an editorial act, with a `_why` |
| `built_utc`, `script`, `manifest` | provenance: when, by what, from which manifest |
| `burned` | prose list of what is on the pixels/audio — statements, not machine-parsed |
| `sidecars` | role → path of the per-render evidence (clip sidecar, dub report, render manifest) |
| `published` | `url`, `privacy`, and the `.youtube.json` sidecar. Duplicated inline on purpose: the sidecar is gitignored, so this is the only committed record of the link |
| `checked_utc` | acknowledges a later manifest edit as non-material (a path fix proven by a `--list` diff); the doctor compares the manifest mtime against `max(built_utc, checked_utc)` |
| `_why` and friends | prose. Neither `record()` nor the scanner ever overwrites prose it did not write |

All paths are repo-relative with forward slashes. `scripts/_project.py` is the
only writer scripts use: `record()` appends a journal event line and upserts
the deliverable, merging — and it deliberately never raises into a pipeline,
because it runs after a render that may have cost 20 minutes; it warns loudly
instead.

### journal.md

Append-only markdown, one `## YYYY-MM-DD` section per day. Scripts stamp
`- HH:MM render … -> path (argv)` lines automatically; the AI ends an editing
session with a short prose note — what was asked, which knob changed, why, and
anything the next session should not have to rediscover. History lives here and
not in project.json so the state file stays a one-screen read no matter how
long a project runs.

### project-scan.py

```powershell
python scripts/project-scan.py --init <id>        # new skeleton
python scripts/project-scan.py --id <id> --list   # what a scan would change, no write
python scripts/project-scan.py --id <id>          # scan the folder into project.json
python scripts/project-scan.py --all --check      # doctor everything, exit 1 on findings
```

The scan is mechanical and additive: existing values win, prose is never
touched, scan-inferred `burned` lines are marked `(scanned)`. The doctor
reports `MISSING` (deliverable file gone), `STALE` (controlling manifest newer
than the render and not acknowledged), `UNRECORDED UPLOAD` (a `.youtube.json`
with no `published` block), `AMBIGUOUS` (two `current` renders of a kind that
should have one), and `BADPATH` (backslashes or absolute paths). On its first
run against the real repo it found a genuinely ambiguous pair — two published
claude-demo renders, the labelled one newer — which is the exact confusion it
exists to prevent.

## The status line, and watching a render from outside it

`.claude/settings.json` points the Claude Code status line at `statusline.py`
— project-scoped on purpose, so every session opened in this folder gets it
and no session anywhere else does. It shows the session, not the work:

```
kitcut | ⎇ main | Fable 5 (1M context) | effort: xhigh | ctx: 33% (334k) | 5h: 26% 2h58m | wk: 60% 2d18h
```

Everything on it comes from the JSON Claude Code feeds the command on stdin
(`model`, `effort.level`, `context_window`, `rate_limits.five_hour` /
`.seven_day` — captured from a live session, not assumed) except the branch,
which the script asks git for. The context token figure is
`total_input_tokens` alone, because `used_percentage` is input-only by
definition and the two numbers should sit on one basis. Any absent field drops
its segment rather than erroring; rate limits in particular only appear on
subscription accounts after the first response.

Render progress used to be appended to this line and that was reverted — an
encode's position belongs to a watch tool, not the prompt. A render is still
minutes of NVENC behind `capture_output=True`, so when you want to see one:

```powershell
python scripts/render-status.py
```

```
claude-demo ██████░░░░  61%  4:34/7:30  1.4x  eta 2:07
```

The plumbing is ffmpeg's own `-progress` writer: give it a path and it appends
`out_time` and `speed` twice a second. That says how far the encode has come but
not how far it has to go, so `_progress.begin()` writes a sidecar carrying the
runtime the script already computed, and the reader takes the pair.
`screencast-cut.py` and `cut-clips.py` both publish; the job is cleared in a
`finally`, so a crashed or cancelled render does not leave the bar stuck at 61%.
A job whose progress file has gone untouched for 90s is reported as stalled
rather than left frozen at its last position.

Three things `statusline.py` has to get right, all because of where it runs:

- **stdlib only, no `_env`.** It re-runs on every refresh, and the repo's usual
  re-exec into `.venv` would spawn a subprocess each time. It needs no package.
- **it never raises.** An exception blanks the status line with no explanation,
  so the body is guarded and every missing field degrades to absence.
- **it forces UTF-8 on stdout.** Windows hands a child `cp1252`, which cannot
  encode the branch glyph or the progress bar at all — the line would die on a
  `UnicodeEncodeError`. Measured: `sys.stdout.encoding` really is `cp1252` here
  even though the terminal renders UTF-8 fine.

## Setup

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup-python.ps1   # build .venv
python scripts/check-env.py                                          # prove it works
```

Add `-Recreate` to delete and rebuild `.venv` — the answer when it exists but
sits on the wrong Python version, which the script now refuses to install into.

That is the whole setup. Afterwards every script runs as plain
`python scripts/<name>.py` from any shell — they re-exec themselves into `.venv`
via `scripts/_env.py`, so there is nothing to activate and no `-E` to remember.
`check-env.py` is also the first thing to run when an import breaks; it reports
the cause rather than leaving you to infer it from a DLL error.

Needed on the machine itself:

- **Python 3.13** (`py -3.13`). Package versions are pinned in `requirements.txt`.
- **`ffmpeg`/`ffprobe`.** libass is required and `check-env.py` fails without
  it; rubberband is a warning, because a dub can fit without the stretcher.
  Any working H.264 encoder will do — see **## Which encoder** below.
- **Optional NVIDIA GPU.** CUDA needs `nvidia-cublas-cu12`, since ctranslate2
  bundles cuDNN but not cuBLAS; `check-env.py` counts the DLLs it can see,
  because without them transcription silently drops to CPU and runs ~3x slower.
- **Network**, for `edge-tts` during dubbing. No API key is needed for either
  the voice or (with `--engine claude`) the translation — that engine shells
  out to the `claude` CLI, so `check-env.py` checks it is on PATH.

Note on licensing: edge-tts reaches the endpoint behind Edge's Read Aloud
feature. It is free and needs no account, but those voices are not licensed for
commercial redistribution, and the endpoint can change without notice. For
published client work, ElevenLabs on a paid plan is the one that grants
commercial rights.

The `opencv-python<5` pin is load-bearing: version 5 ships no Haar cascades at
all, and its `FaceDetectorYN` replacement wants a model from an external host.

`sherpa-onnx` is pinned too, and was not for a long time: `auto-switch.py`
imports it and nothing else does, so a clean machine passed `check-env.py` and
then failed at the one import only stage 2 of the multicam round trip reaches.
It is in `requirements.txt` and in the doctor's probe list now. The ONNX
*models* under `models/` remain a manual download — see the multicam-switch
skill.

### One heavy run at a time: the GPU lock

The card is 4 GB and a `large-v3` load is 2-3 GB of it, so it fits exactly one.
Three `transcribe-words.py` runs were once started inside two minutes by
sessions working in this repo at the same time, and all three thrashed: the GPU
read 100% busy and 3.9/4.0 GB used for twenty minutes while **none** of them
wrote a transcript. Nothing errored — that is what made it expensive. There was
no failure to read, only three jobs each permanently nearly done, and finding
out took a `Get-CimInstance` sweep of every python process's command line.

So a GPU run now takes a lock first and the rest queue behind it. Serialising
beats refusing: the same work still gets done, one at a time, which is the only
way any of it finishes.

```powershell
python scripts/gpu-lock.py                 # who holds it (free; the default)
python scripts/gpu-lock.py --list          # every lock under temp/locks/
python scripts/gpu-lock.py --clear         # drop it, but only if it is dead
```

`transcribe-words.py` takes it automatically and only on a CUDA rung, so an
explicit `--device cpu` run never queues. `--gpu-wait` sets how long to queue
(default 2 h; `0` refuses immediately) and `--no-gpu-lock` skips it, which is
only ever right when you know the card is free.

**The lock survives its holder being killed, which is how these runs usually
end.** A kill runs no `atexit` and no `finally`, so the file outlives the
process — and a lock nobody can release would fence off the card forever, which
is worse than the deadlock it replaced. The defence is that liveness is checked
on every contended acquire rather than trusted to the holder: a dead pid is
stolen, not waited on. Pid reuse is the residual hole, so a lock held past
`MAX_AGE_S` (6 h) is stale whatever its pid claims. A holder also only ever
deletes *its own* lock, because a stale token must not remove the file of
whoever legitimately took it afterwards.

`--clear` refuses a live holder on purpose; breaking it would put a second job
on the card, which is the whole thing being prevented. `--force` is for when you
have already killed the holder yourself and the liveness check disagrees.

`scripts/check-gpulock.py` proves all of it with no GPU and no files outside a
temp dir — including by really spawning a holder, really hard-killing it, and
checking the next acquirer gets in. Run it after touching `_gpulock.py`:

```powershell
python scripts/check-gpulock.py
```

One thing it caught that is worth keeping: under `_env` the running interpreter
is the venv's `python.exe`, and on Windows that can be a shim which launches the
real interpreter under a *different* pid — so `Popen(...).pid` is not the pid
that holds the card. The lock records `os.getpid()` from inside the working
process, which is always the right one; a test asserting against Popen's pid is
asserting the wrong thing.
## Which encoder

Nothing in the pipeline scripts spells an encoder key any more. A manifest or
preset states an *intent* — quality, speed, bitrate ceiling — and
`scripts/_encode.py` renders it into whatever family the chosen encoder
belongs to:

| | speed | rate control |
|---|---|---|
| `*_nvenc` | `-preset p5` | `-rc vbr -cq N -b:v 0` |
| `*_amf` | `-quality balanced` | `-rc qvbr -qvbr_quality_level N` |
| `*_videotoolbox` | *nothing: it has none* | `-q:v N` |
| `lib*` | `-preset medium` | `-crf N` |
| `*_qsv` | `-preset medium` | `-global_quality N -look_ahead 1` |

This is why the split exists. Every render script used to spell
`-c:v <encoder> -preset p5 -rc vbr -cq 21 -b:v 0` inline, six times over, next
to an encoder that was *configurable*. So setting `render.encoder` to
`libx264` on a machine with no NVIDIA card did not help: `-preset p5` and
`-rc vbr` travelled with it, and both x264 and AMF die on
`invalid preset 'p5'`. The encoder was a setting and the keys around it were
not, which made the setting a lie.

**Speed is carried on NVENC's p1..p7 scale**, because every preset and
manifest committed here already speaks it. A `"preset": "p5"` written before
any of this still means p5 — it is *translated* into the target family rather
than ignored, and it is never passed through to an encoder that would reject
it.

**Quality is one number across all five, and smaller always means better.**
That is the contract `cq` carries — it is what `-cq` and `-crf` already mean —
and each family is responsible for expressing it in its own terms. **Two of
the five run backwards.** AMF's `-qvbr_quality_level` does, so
`_encode.amf_quality()` inverts it (`51 - cq`); VideoToolbox's `-q:v` runs
1..100 the same way round, so `_encode.videotoolbox_quality()` inverts it too.
See `## Gotchas`, where both measured curves are. Getting this wrong is
invisible from the outside, because too *little* quality makes a *smaller* file
and small files look like a win.

VideoToolbox is also the one family with **no speed control at all** — no
preset ladder, and its three lookalikes (`-prio_speed`, `-realtime`,
`-spatial_aq`) were each measured to return a byte-identical file in the same
time. A speed tier reaching it is dropped rather than invented.

**`profile` and `level` follow the codec, not the family** — a separate axis.
The values in these configs (`high`, `4.2`) are H.264 ones, so on HEVC the
profile becomes `main` and the level is dropped rather than guessed:
`libx265` wants `4.2` and `hevc_amf` wants the integer `126`, and a
compatibility hint is not worth a units bug. `check-encode.py` found this by
rendering a caption pass through `hevc_amf` and getting `Invalid argument`.

### Which one you get

Resolution is `render.encoder` in the manifest or preset → `$VIDEDIT_ENCODER`
→ the first of `h264_nvenc`, `h264_amf`, `h264_qsv`, `h264_videotoolbox`,
`libx264` that **actually encodes a frame here**. Same shape as
`_env.workspace()`: the assumption gets one home. Hardware sits ahead of
software throughout: on an M-series Mac, 30 s of grainy 1080p30 took 6.6 s
through VideoToolbox against 35.6 s through `libx264 -preset medium`, for a
slightly better VMAF at 111 MB against 260 MB.

An encoder a *committed file* names but this machine cannot run is
**substituted, loudly**, naming the key to edit for permanence — those files
are read on machines their author never saw, and twenty minutes into a
filtergraph is the wrong moment to learn the box has no NVIDIA card. One named
explicitly (`--encoder`, `$VIDEDIT_ENCODER`, or `$VIDEDIT_ENCODER_STRICT=1`)
is honoured strictly and fails instead: you asked for that one by name. Every
`--list` / `--plan` prints the encoder line it would send, so the choice is
legible before it is paid for.

```powershell
python scripts/check-encode.py                 # the self-test, ~10s, no project
python scripts/check-encode.py --table-only    # the mapping only, no ffmpeg
```

`check-encode.py` is the third one-button self-test beside `check-dub.py` and
`check-multicam.py`, and it has a half the others do not: it hands **every
encoder this machine can run** the exact argument list a clip, a conform and a
caption pass would send it, and requires a file out the other end. A table
test agrees with whatever the table says; ffmpeg does not, which is how the
HEVC profile bug surfaced within a minute of the test existing.

Run it after touching `_encode.py` or any render script's encoder path.

### Encoding is not decoding

`screen-cut.py`, `film-redact.py` and `make-proxies.py` were written while
this was in flight and each spelled `-c:v h264_nvenc -preset p5 -rc vbr -cq N`
by hand; they go through `_encode` now, which is what keeps "nothing spells an
encoder key" true rather than aspirational. `screen-cut.py` still reads the
`nvenc_preset` key its committed manifests use — it is translated, not
ignored, exactly like `p5` above.

`-hwaccel cuda` is a **different axis**: NVDEC on the input, not NVENC on the
output, and nothing translates it. On a machine with no NVIDIA driver it fails
the *input*, which reads as a broken source file rather than a missing card.

Eight call sites spelled it inline. Three (`screen-activity.py`,
`shot-detect.py`, `detect-overlays.py`) retried in software and were merely
wasting an attempt; `make-proxies.py` inferred it from the encoder; the four
in `scan-pii.py` and `film-redact.py` had **no fallback at all**, so on an AMD
box the PII scan and the film redaction could not read a frame while every
render on that box was fine. All eight ask `_encode.decode_args()` now, and
`check-script.py` FAILs a script that spells the flag itself — the same rule
the encoder keys get, for the same reason.

The probe is a real decode, not a capability string: `ffmpeg -hwaccels` lists
what the build has, which is the lie `-encoders` tells about NVENC, so
`nvdec_usable()` encodes a few frames and decodes one of them back through
`-hwaccel cuda`, cached against the ffmpeg version. It is deliberately **not**
read off the encoder — NVENC and NVDEC ship on different silicon and a card
can have one without the other — though `check-encode.py` does assert that a
box with no NVENC has no NVDEC either, because that case is a missing driver.

`check-env.py` says where the line now falls: encoding substitutes, GPU decode
is dropped automatically, and CUDA transcription is the one axis left that
wants the card — `transcribe-words.py` falls back to the CPU on its own, and
is slower for it.

### On the AMD box this was written against

`h264_amf` and `hevc_amf` both work; there is no NVENC (no `nvcuda.dll`).
Two things were measured rather than assumed, and both are recorded in
`_encode.py`:

- **AMF's tuning block is deliberately empty.** `-vbaq 1 -preanalysis 1` cost
  26% more wall clock (7.26 s against 5.76 s on 5 s of 1080p30) and moved the
  output by 8 bytes in 3.09 Mbps — VCN 1.0 ignores both. Re-measure on RDNA
  before adding them back.
- **No `-bf` on AMF.** This GPU answers `-bf 3` with *"The current GPU in use
  does not support H.264 B-frame encoding"*, proceeds without them, and the
  flag buys nothing but a warning.

`-b:v 0` stays NVENC-only, where it is load-bearing (see `## Gotchas`); AMF
and x264 already have a quality target and do not want a zero-bitrate VBR one
next to it.

### Where things live: ROOT, workspace, and one resolver

Two ideas, deliberately separated even though they currently name the same
folder:

| | |
|---|---|
| `_env.ROOT` | where the **tooling** lives: `scripts/`, `config/`, `fonts/`, `models/` |
| `_env.workspace()` | where the **user's work** lives: `projects/` under it |

`workspace()` resolves most-explicit-first — a `--workspace` flag
(`_env.add_workspace_arg()` / `set_workspace()`, wired into `project-scan.py`),
then `$VIDEDIT_WORKSPACE`, then a one-line `.workspace` pointer file beside the
repo, then `ROOT`. Today it is always `ROOT` and every manifest path assumes it.
The point of the function is that the assumption has **one** home: nothing in
the corpus joins `ROOT` with `"projects"` any more — `_project.projects_dir()`
does, once — so moving the work out of the tool's folder is a setting rather
than a refactor.

`_env.resolve(p, base=None)` is the path resolver: absolute stays, relative
joins `base` (default `ROOT`, because config and fonts are tooling rather than
work). Ten scripts carried their own copy of that one line, which meant every
new script acquired it by copy-paste and the base could never have been changed
in fewer than ten places. There is one copy now, and `check-script.py` fails any
absolute path written into a script, a skill or these docs.

## Repo layout

| Path | |
|---|---|
| `CLAUDE.md` | orientation: how to run things, and the house rules |
| `scripts/_env.py` | re-execs every script into `.venv`; import it first. Also the one path resolver and the ROOT/workspace split |
| `scripts/setup-python.ps1` | builds/repairs the environment, idempotent |
| `scripts/check-env.py` | the doctor — run this when an import breaks |
| `scripts/_encode.py` | the one place encoder keys are chosen: an intent in, one family's vocabulary out |
| `scripts/check-encode.py` | encoder self-test; proves the keys each encoder is sent are keys it takes |
| `scripts/check-dub.py` | dub self-test; no key, no TTS calls, no cost |
| `scripts/run-captions.py` | the orchestrator — start here |
| `scripts/transcribe-words.py` | faster-whisper → word-level JSON | (`--hotwords-file` for brand names it has never seen)
| `scripts/detect-overlays.py` | finds the source's own lower-third graphics |
| `scripts/build-captions-ass.py` | words + preset → styled ASS |
| `scripts/verify-captions.py` | proves sync by probing rendered frames |
| `scripts/transcript-outline.py` | skim a transcript; find the time of a phrase |
| `scripts/_ytchapters.py` | chapter-marker rules, and what YouTube really enforces |
| `scripts/yt-set-chapters.py` | write chapter markers into a video's description |
| `scripts/yt-set-banner.py` | set a channel's banner (header image), keeping its branding fields |
| `scripts/yt-audit-chapters.py` | which videos on a channel actually show chapters |
| `scripts/cut-clips.py` | manifest → standalone clips cut out of a long video |
| `scripts/_overlay.py` | drawing and filter helpers shared by the burned-in graphics |
| `scripts/_progress.py` | publishes an ffmpeg render's position for the status line |
| `scripts/render-status.py` | the Claude Code status line for this repo |
| `scripts/handle-overlay.py` | animated social-handle badge, drawn and burned in |
| `scripts/name-label.py` | lower-third name label, drawn and burned in |
| `scripts/image-overlay.py` | an image over the film — wipe/fade/slide, plus the background treatment |
| `scripts/html-to-image.py` | an HTML page → a transparent PNG, via headless Edge/Chrome |
| `scripts/make-card.py` | design a card: spec + template + brand → page → PNG |
| `scripts/dub-clips.py` | translate a clip and speak it back into its own cadence |
| `scripts/dub-translate.py` | per-slot translation under a time budget |
| `scripts/dub-tts.py` | neural TTS with word boundaries and rate control |
| `scripts/sync-tracks.py` | line up a silent screen capture with the camera take, and prove it |
| `scripts/screencast-cut.py` | drop the dead air and composite the two into one film |
| `scripts/screen-activity.py` | measure when a silent screen recording is doing something, per region |
| `scripts/screen-cut.py` | cut/speed/blur silent screen recordings into one film |
| `scripts/scan-pii.py` | OCR a recording for card numbers, CVVs, IBANs, phones and addresses |
| `scripts/make-proxies.py` | transcode a manifest's sources once, at the working size |
| `scripts/track-blur.py` | follow a secret's own pixels through a recording; emit the blur mask; `--recall` measures it |
| `scripts/redaction-review.py` | the before/after sheet of every redaction; the stop before a render |
| `scripts/render-gate.py` | search the secrets' pixels on the finished film; `--patch` the manifest |
| `scripts/_runlog.py` | the run log writer: one JSONL record per stage, flushed as it happens |
| `scripts/run-log.py` | the run log reader: what ran, how long, and how it ended |
| `scripts/_gpulock.py` | the single-run GPU lock: one heavy job on the 4 GB card, dead holders stolen rather than waited on |
| `scripts/gpu-lock.py` | the lock reader: who holds the card, and `--clear` when the holder is gone |
| `scripts/check-gpulock.py` | lock self-test incl. a real spawn/kill/recover cycle; no GPU, no files |
| `scripts/check-openings.py` | does a short open on a settled face? lead-in silence + contact sheets; no encode |
| `scripts/check-caption-space.py` | is the caption card sitting on the speaker's face? reads the RENDER, per caption group |
| `scripts/measure-caption-band.py` | where does a channel park its caption card? temporal median over their own shorts — a single frame cannot tell a caption from a black turtleneck |
| `scripts/audit-caption-glue.py` | which shipped renders carry split punctuation ("60 ,000") inside their actual window? free, per deliverable |
| `scripts/shortlist-moments.py` | verify a real SELECTION happened before any short is cut: resolves and prices every shortlist candidate; no opinion on counts or length — the user says what they want |
| `scripts/check-shorts.py` | shorts-path self-test: hook gate, pads, crop windows, grouping typography, caption-space geometry; no GPU, no encode |
| `scripts/import-footage.py` | desktop + phone captures into a project, ordered by real capture start |
| `scripts/screencast-pipeline.py` | the twelve stages in order, cached, with two stops (the sheet, the draft) |
| `scripts/review-ingest.py` | the user's narrated review recording → remarks mapped to source frames |
| `scripts/check-screen.py` | silent-screencast self-test; no GPU, no files, no OCR |
| `scripts/tighten-cut.py` | one already-composited recording: shorten its pauses, drop its stumbles, remove the parts you name |
| `scripts/shot-detect.py` | read an edit back off a finished film: where it cuts, and on which angle |
| `scripts/split-cameras.py` | conform a programme, then rebuild the camera tapes it was cut from |
| `scripts/conform-tapes.py` | put N recordings from different devices onto one frame rate and size, provably |
| `scripts/sync-audio.py` | line up N tapes that share a soundtrack, by FFT correlation |
| `scripts/angle-cut.py` | cut one film out of N synchronised cameras, switching full frame |
| `scripts/compare-videos.py` | score one film against another frame by frame, and pass or fail it |
| `scripts/auto-switch.py` | choose the camera from the soundtrack alone: diarize, then apply a cutting grammar |
| `scripts/debug-notes.py` | burn a running commentary onto a film: what the cut did here, and why |
| `scripts/check-multicam.py` | multicam self-test; no GPU, no files, no cost |
| `scripts/import-iphone.ps1` | pull footage off a phone over MTP, verified by byte count |
| `scripts/yt-upload.py` | upload a render to YouTube, channel-guarded and verified |
| `scripts/yt-delete.py` | delete videos from YouTube, channel-guarded, dry-run by default |
| `scripts/yt-set-disclosure.py` | read or set the "altered or synthetic content" flag; find which watch pages show "Made with AI" |
| `scripts/yt-fetch-transcripts.py` | pull audio + word transcripts for published channel videos |
| `scripts/yt-audit-chapters.py` | verdict per channel video: has chapters, needs them, or too short |
| `scripts/verify-chapters.py` | check a chapter list against the transcript before it goes live |
| `scripts/chapter-thumbs.py` | contact sheet of the frame each chapter timestamp lands on |
| `scripts/check-script.py` | conformance check for new/changed scripts (see the check-script skill) |
| `scripts/_project.py` | the project-metadata writer every finishing script calls |
| `scripts/project-scan.py` | bootstrap and doctor for project files |
| `projects/<id>/` | one video: metadata + manifests committed, content gitignored — see `## Projects` |
| `config/presets/` | all visual styling |
| `config/vocab/` | hotword lists — the brand names and acronyms an ASR model has never seen |
| `config/labels/` | the lower-third name label's styling |
| `config/handles/` | handle-badge styling and motion |
| `config/overlays/` | image-overlay animation, layout and background treatment |
| `config/cards/templates/` | card layout archetypes — the *shape* of a card |
| `config/cards/brands/` | brand tokens — the *look*; swap one to re-skin every template |
| `projects/<id>/cards/` | card specs (the *words*), committed |
| `projects/<id>/assets/` | authored overlay artwork — hand-written pages and logos, committed |
| `fonts/` | Montserrat Bold (SIL OFL 1.1, see `fonts/OFL.txt`) |
| `docs/karaoke-captions.md` | design notes and the traps behind them |
| `.claude/skills/` | Claude Code skills: captions, shorts, dub, multicam, name-label, image-overlay, project |

`sources/`, `audio/`, `transcripts/`, `outputs/`, `temp/` — at the top level
and inside each project folder — are working directories and are
**git-ignored**: they hold third-party video and material derived from it,
which is never committed. The top-level ones are the legacy shared layout;
new work lives under `projects/`.

Of those, `transcripts/` is the only expensive artifact (minutes of GPU time);
everything in `temp/` regenerates in seconds.

## Gotchas worth knowing

- **A cache that lives as long as the process grows with the batch, not with the film.** The
  studio server makes one film's pictures and moves on; `share.py --missing` ran 55 films in
  one process, `_thumb.load_still` kept every decoded still (2,196, 13.7 GB), and two films being
  made on the same 16 GB VM failed with `Control request timeout: initialize` -- Claude could not
  even start (KI-045). Two rules now, both enforced by `studio/test_memory.py` in the release
  gate: a module-level cache of anything large is bounded (`_thumb.STILLS_MB`, least recently
  used first); and every `systemd-run` in the deploy scripts carries `-p MemoryMax=` or says on
  the line above `# memory: uncapped -- <why>`. `ops.sh status` warns under 2 GB available and
  names the biggest process -- read it before and during any batch job on the VM.

- **`-shortest` with a subtitle track cuts the film where the subtitles end.** A film's last
  caption ends before its last frame, and `-shortest` counts the subtitle stream: a 40 s film
  came out 38.57 s with its end card gone. Mux with `-t <duration>` and assert the duration
  afterwards (`sketch-render.py` does).
- **`eleven_v3` clips the last syllable of most takes.** Measured: 16 of 18 takes ended above
  -30 dBFS, mid-word. Render "line + tail word" and cut in the silence before the tail
  (`sketch-vo.py`); the line also gets a sentence-final ending that way. `mp3_44100_192` is a
  403 below the Creator tier, so ask for `mp3_44100_128`; a TTS-scoped key gets 401 from the
  music and sound-effects endpoints, which is why sketch films synthesise both.
- **Chromium's blob store does not keep up with a frame export.** `canvas.toBlob()` per frame
  failed with "Failed to fetch" after ~100 frames; the export posts raw RGBA from
  `getImageData` instead (also twice as fast: no PNG encode or decode). An HTTP/1.0 server
  opened a new connection per 8 MB frame and a render died on the one that got reset, so the
  frame server speaks HTTP/1.1 keep-alive and the page retries a failed POST.
- **Killing Chromium's parent on Windows leaves its children running.** A 1.3 GB renderer
  outlived its run; `sketch-render.py` takes the whole tree with `taskkill /T`.
- **Python's `hash()` of a string is salted per process.** A drum seeded from `hash(piece)`
  sounded different every run; seed from the characters instead.
- **`"swell": [from, to]` read as beats.** In `gliss` and `roll`, `from`/`to` are beats, so a
  studio film wrote `"swell": [24, 30]` meaning "swell over beats 24-30". It is a gain ramp:
  every string chord played 24-30x (+28 dB), from 16.5 s to the end, over the narration. Two
  things let it through: nothing checked a score's volumes, and the studio's `sound` tool
  returned the script's last 15 lines -- the stage timings -- so even `levels: true` never
  showed Claude the balance. Now: `check_score` refuses volumes outside 0..1.5 (33 real scores
  peak at 0.95), the voice gate holds the music 8 dB under the voice, and the tool reads
  `audio/balance.json` (studio film ssemfm, 2026-09-26).
- **A film that opens on blank paper looks broken.** A 0.35 s fade in from the paper colour
  plus a draw-on that started at zero gave six identical blank frames and a slow fade: the
  first thing a viewer saw was nothing. `SK.film` no longer fades in unless asked, and the
  opening draw-ons start part-way. `ffmpeg ... -vf signalstats` on the first 40 frames
  (YAVG) shows where the picture actually starts.
- **A world-space paper texture balloons in a wide shot.** At zoom 0.4 its grain turned into
  blotches; the engine draws paper in screen space and slides it with the camera.

- **`-hwaccel cuda` fails the INPUT, so a missing card reads as a broken
  source file.** It is NVDEC on the input and a different axis from the NVENC
  keys on the output; nothing translates between them, and a build that lists
  `cuda` under `ffmpeg -hwaccels` lists it on a machine that has never had an
  NVIDIA driver — the same lie `-encoders` tells. Eight call sites spelled the
  flag inline; the four in `scan-pii.py` and `film-redact.py` had no fallback,
  so on an AMD box the redaction pipeline could not read a frame while every
  render on that box was fine. Ask `_encode.decode_args()`, which probes by
  decoding a frame it encoded itself and returns nothing when NVDEC is absent.
  Do not infer it from the encoder: NVENC and NVDEC ship on different silicon
  and a card can have one without the other.

- **Whisper emits punctuation as its own word, and a caption card joins words
  with a space.** The transcript for a number is `"60"` then `","000"`; for an
  abbreviation it is `"U"` then `".S."`; a percentage arrives as a bare `"%"`;
  a hyphenated word splits at the hyphen. Every word here is drawn as its own
  positioned event, so the obvious join shipped `60 ,000` and `15 ,000` onto a
  Bloomberg short, and `U .S.` behind it — and a dub sent `60 ,000` to its
  translator. The repair therefore lives in the ONE loader every consumer
  shares — `glue_words()` in `transcript-outline.py`, applied by
  `load_words()` — so captions, phrase anchors, dub units and outlines all see
  the same text; the raw `words.json` on disk stays verbatim ASR output.
  Gluing cannot break `start_text`/`hook` matching: `fold()` strips
  whitespace and punctuation and `index()` concatenates with no separator, so
  raw and glued words build the identical haystack (pinned in
  `check-shorts.py`). The merged word spans both timing windows so the
  caption spotlight stays honest.
  **Do not "glue anything that starts with punctuation".** Measured across this
  repo's nine transcripts there are 358 such tokens, and two families are
  words: 57 standalone en/em dashes (Ukrainian punctuation, spaces on both
  sides) and 19 opening guillemets (`«Дельта»`). A lone `&` is `Point & Figure`
  and a lone `-` is a dash; the same characters *attached* to something
  (`&A`, `-to`) are suffixes. `%` is the one glue character that is still glue
  when it stands alone. `$14` needs nothing — it already arrives whole.
  `check-shorts.py` pins all of it, negatives included.

- **`max_line_width_px` above ~539 does nothing on a vertical cut.**
  `scale_style()` scales it by the height ratio and then clamps it to
  `0.94*W - 2*pad_x` — 958 px on a 1080-wide frame — because the card, not the
  text, is what must fit. Going landscape → vertical multiplies by 1.78 while
  the frame gets *narrower*, so any authored value over about 539 hits the
  clamp and every larger number is the same number. Run
  `build-captions-ass.py --sweep` (with `--words --style --scale-to --range`)
  to see the table for the words that will actually render — a flat width
  column is the clamp binding, not a bug in the sweep. The structural answer
  is `grouping.wrap` in the preset, a CHANNEL property measured off their own
  graphics: `"none"` for a single-line-strap style like Bloomberg's (grouping
  refuses any card needing a second line, so long words carry fewer per
  card), `"no_orphan"` where two-line cards are on-style but a stranded
  single word is not (`layout()` pulls a word down — classic widow fixing),
  `"allow"` for the old behaviour. "HORRENDOUS JOB / HORRENDOUS" and "the
  models are going / to" both shipped before the policy existed; per-clip
  `max_words` overrides through `clip_style()` remain for the rare clip that
  genuinely differs from its channel.


- **A 9:16 crop does not remove the source's own lower third — it slices it.**
  Going 16:9 → 9:16 spends width, not height, so a broadcast banner at the
  bottom of the source survives the crop with its text cut mid-word. The first
  Bloomberg Tech short read `ED TALKS FOR HUGGING` across the bottom and cut the
  `Ian King` name card in half, under our own caption card — two competing lower
  thirds, one of them broken. Fix it in the crop, not with the overlay-dodge:
  `overlays.colour` only *lifts* our card clear of theirs, it cannot delete
  theirs. Measure where their graphics start (Bloomberg's name card steps in at
  source y=697, the banner's white at y=920), then set `crop_zoom` and `crop_y`
  so the window ends above it. And check whether the shot is boxed: a studio
  frame has its background above the video box too (top edge at y=63 here), so
  the window has to start below that or a hard band lands across the top.

- **The tracker will pan across the seam of a two-box shot.** `auto-reframe.py`
  classifies an interview two-shot as `pan` and interpolates between the two
  faces, which walks the window off one subject and onto the gap, ending with
  half of each box in frame. It is not a `pad` case, so nothing warns you.
  Review any shot where the x keys move a long way in a short time, find the
  real cut (a centre-column brightness step: 66 → 93 between two seconds here),
  and hold the window static on one subject in the `.reframe.json` sidecar.

- **The `fps` filter labels the slot, not the frame.** `-vf fps=0.25` emits,
  for the output frame stamped 16 s, whichever input frame fell inside that
  4-second slot — and rewrites its timestamp to 16.0. A template cut at exactly
  16.0 landed on a Notepad window instead of the spreadsheet cell OCR had read
  at ~20 s; tracker recall was 46 % on frames it had cut its own templates
  from. Sample with `select=not(mod(n\,STEP))` and read the frame's own
  `pts_time` from `showinfo` (`scan-pii.py`).
- **Reading a child's stderr before its stdout deadlocks.** Waiting for the
  `showinfo` line before reading the frame bytes blocks ffmpeg on a stdout
  nobody drains, while this side waits for a line ffmpeg has not reached.
  Read the frame first; the log line for it is already out.
- **A filtergraph on the command line has a 32 KB ceiling on Windows**, and it
  fails as `WinError 206: The filename or extension is too long`, which names
  the wrong thing entirely. Use `-filter_complex_script` (`screen-cut.py`).
- **`concat` over ten file inputs buffers the nine it is not reading**: 2.8 GB
  RSS and output frozen at 25 MB. Render per source; join with the concat
  demuxer and `-c copy`.
- **Per-rect blur chains are quadratic in the wrong thing.** 138 rects as 138
  split/crop/blur/overlay chains ran at 0.0024× — a 56-hour ETA. Blur the frame
  once and composite it back through one mask (`masked_blur`, or the tracked
  mask stream).
- **Pixelate costs 17× a filled box** (35 s vs 2 s per 10 s of video at 18
  rects), because each mosaic is its own scale-down/scale-up per frame.
- **`boxblur` caps chroma radius at half the luma cap** in yuv420p —
  `Invalid chroma_param radius value 21, must be >= 0 and <= 16` kills the
  render. Clamp the two planes separately.
- **`drawtext` with no `fontfile` dies on Windows** (`Fontconfig error: Cannot
  load default config file`). Always pass a font.
- **`_progress.begin()` returns the path ffmpeg must be given as `-progress`.**
  Declaring the job without wiring it leaves the status line reading an empty
  file and reporting "stalled" for the whole encode.

These are load-bearing; `docs/karaoke-captions.md` has the full list with
evidence.

- **A zero-length word from Whisper steals a centisecond from the next one.**
  Whisper emits `start == end` wherever it clips a word at a segment boundary
  (10 of 3795 words on one film here, 13 of 2768 on another). The caption
  builder gives such a word a synthetic 1 cs duration — and if the following
  word starts at that same instant, the two groups overlap by exactly 1 cs and
  `selfcheck` refuses the whole file. The refusal blames `min_active_ms` and
  `max_words`; on a dense 19-minute Ukrainian podcast **six settings of that
  pair all failed by exactly 1 cs**, which is the tell that neither was the
  cause. `sanitize()` now orders each word's start against the previous word's
  **end** rather than its start: a no-op on a well-formed transcript, a repair
  on a degenerate one.

- **A venv does not protect you from `PYTHONPATH`,** and neither does pip. A
  global `PYTHONPATH` aimed at another Python's site-packages makes 3.13 load
  3.11's compiled extensions (`DLL load failed`, or a bare segfault under Git
  Bash) — *and* convinces pip those dependencies are already satisfied, so it
  installs a venv quietly missing `yaml` and `idna`. `setup-python.ps1` clears
  the variable before installing and finishes with `pip check`; `_env.py` clears
  it for every child process. This is handled now: run scripts as plain
  `python scripts/<name>.py`.
- **A brand name Whisper has never heard becomes three different words, and
  captions burn that in.** One 5-minute demo produced "Instafili", "Instafil"
  and "Instafield" for the same product, plus "flat and PDF" for *flatten PDF*
  and "W994" for *W-9*. Patching the transcript afterwards is the wrong end of
  the problem — the timings belong to words the model actually decoded. Feed the
  vocabulary in first: `transcribe-words.py --hotwords-file config/vocab/<x>.txt`.
  It uses faster-whisper's `hotwords`, **not** `initial_prompt`, because
  `condition_on_previous_text` is off here (it caps a repetition loop at one
  window) and that also stops `initial_prompt` reaching past the first 30
  seconds. Keep the list to words the model gets wrong: every hotword nudges the
  decoder, so padding it with ordinary English makes the transcript worse.
- **A transcript correction that spans a pause deletes words two passes
  later.** Spreading the replacement evenly from the phrase's first word to its
  last puts words INSIDE the silences the phrase contains; the pause cut then
  removes those silences, the remap drops every word sitting in one, and the
  film is captioned "So you just tool." where the speaker said "So you can just
  open this tool." Nothing errors — the words are simply gone, and you only see
  it by reading the finished transcript. `transcript-outline.apply_corrections`
  retimes one-for-one where the word count matches (every case-and-punctuation
  fix does), and otherwise lays the replacement along **spoken time only**,
  walking the old words' spans and skipping the gaps.
- **The caption sync probe could fail a provably correct ASS.** It sampled a box
  of ±(font size)/2 around each word's centre, and in any tight-leading preset
  the font size exceeds the line spacing — so on a two-line card the box for a
  word on line 1 reached down into line 2 and read the spotlight colour from the
  word underneath it. `verify-captions.py` clamps the box to 45% of the measured
  line gap now. If a probe ever disagrees with you, read the `Dialogue:` lines
  covering that timestamp first: the ASS is the ground truth, not the probe.
- **A flat bitrate floor is not a quality check.** `run-captions.py` used to fail
  any render under 1.5 Mbps as evidence that `-cq` had been ignored. A 720p
  screen recording of mostly-static pages legitimately encodes to 0.6 Mbps with
  the form text still pin-sharp, and the check failed a good render. What it is
  really trying to catch collapses the output far below whatever the **source**
  cost, so the test is now both: absolutely low AND under half the source's rate.
- **Room tone spliced to room tone clicks.** A pause cut joins two samples of
  the same quiet room at different phases, and the discontinuity is audible even
  though neither side is. `tighten-cut.py` ramps `join_fade_ms` (12ms) into and
  out of every segment — below the threshold of hearing as a fade, above it as a
  click. This is the artefact that makes an edit audible to somebody who was not
  looking for one.
- **A name label past the end of the film fails silently.** The overlay's
  `enable` expression simply never turns true; ffmpeg reports nothing, the
  render succeeds, and the card is not in it. `screencast-cut.py` checks every
  `name_labels` entry against the cut runtime — which is only known after the
  cut — for exactly this reason. `image_overlays` is checked the same way, and
  it is where a negative `at` gets resolved into a real time.
- **NVENC does not re-encode an identical frame identically.** A frozen stretch
  built with `tpad=stop_mode=clone` decodes back differing from itself by up to
  3/255, so `freezedetect` at the −60 dB this repo uses for screen recordings
  finds *nothing* in a 95-second freeze, and its span count is not even
  monotonic in the threshold. Do not verify synthetic footage with a freeze
  detector. `split-cameras.py` fingerprints every sampled frame and compares it
  against the programme frame the layout says it should be showing — which
  proves the *right* picture is in the *right* place, not merely that something
  is static. It scores 0.0002 against a 0.02 limit.
- **A global SSIM average cannot see a one-frame join error.** Measured: a
  render with one camera a single frame out scored a median SSIM of 0.9992,
  versus 0.9993 for the correct render. The signal is not in the average, it is
  in *which* reference frame each frame matches best — score every frame against
  the reference frame before, at and after it, and a shifted segment lights up
  immediately (665 frames, starting exactly at the offending camera's first
  live frame). Any comparator that reports only an average is reporting that it
  did not look.
- **ASS alpha is inverted, and `00` is opaque.** Writing an opacity straight
  into the alpha byte gets you `FF`, which is invisible — the text renders as
  nothing at all while the background box appears exactly as designed, so the
  filter looks like it half-worked. `debug-notes.py` takes an *opacity* and
  inverts it in one place for that reason.
- **A filter option value cannot hold a Windows absolute path.** ffmpeg splits
  filter options on colons, so `ass=filename=C:/x.ass` parses as an option `C`
  and a stray `/x.ass`, and the filterchain fails to build. Pass repo-relative
  forward-slash paths and run ffmpeg from the repo root — which also dodges the
  older trap that a backslash reaches libass as an escape and silently turns
  `temp\x.ass` into `tempx.ass`.
- **A downloaded file is usually not on the frame rate it claims.** The a16z
  clip averaged 23.9765 fps against a nominal 24000/1001. Conform before
  measuring anything to the frame, and conform with `setpts` by frame index
  rather than the `fps` filter — `fps=` hits its target by duplicating and
  dropping frames, so it silently changes the very thing being measured. Assert
  the frame count across the conform; `split-cameras.py` exits if it moved.
- **`crop`'s width and height are evaluated once,** when the filter is
  configured; only `x` and `y` re-evaluate per frame. So an animated crop cannot
  wipe a graphic on — the image overlay ramps the alpha with `geq` instead. The
  vertical pan works for the same reason in reverse: it moves `x` only.
- **`msedge --version` does not print a version on Windows.** It hands the
  argument to the already-running browser, opens a window, and exits 0; Chrome's
  hangs instead. Read the version-numbered folder Chromium installs beside its
  exe — otherwise a "free" check pops a browser open on someone's desktop.
- **A headless screenshot is opaque unless you ask twice.**
  `--default-background-color=00000000` gets you a transparent canvas, but any
  `background` on `html`/`body` paints over it, and the result is a white
  rectangle that looks like a filter bug. `html-to-image.py` checks the alpha
  channel afterwards and fails with the cause. Crop to the **alpha channel's**
  bbox, too: `Image.getbbox()` counts coloured-but-transparent pixels and keeps
  the margin you were removing.
- **Don't re-exec with `os.execve` on Windows.** It spawns a new process and
  kills the current one rather than replacing it, so the shell sees the parent
  die abnormally and the exit code is lost. `subprocess.run` + `sys.exit(rc)`.
- **libass sizes fonts by `usWinAscent + usWinDescent`, not `unitsPerEm`.** For
  Montserrat that's 1562 vs 1000, so a nominal 43 px renders at 0.64x. This is
  why `font.cap_height_px` exists.
- **Variable fonts don't work** — libass registers only the default instance, so
  requesting weight 700 silently falls back to Arial. Use a static TTF.
- **YouTube AI auto-dubs** appear as extra audio tracks; a naive format selector
  can hand you a dubbed language and produce a fluent transcript of the wrong
  words. The selector pins the original track.
- **Never seek with plain `-ss` when burning subtitles** — it rebases PTS to 0 so
  libass renders the wrong lines. Use `--preview`, which regenerates a shifted ASS.
- **`-b:v 0` is required with `-cq`** or NVENC ignores the quality target. It
  is NVENC's alone: AMF's `qvbr` and x264's `crf` already carry a quality
  target, so `_encode.py` emits it for the nvenc family only.
- **AMF's quality scale runs BACKWARDS from every other encoder here.** `-cq`,
  `-crf` and a raw QP all mean "smaller number, better picture". AMF's
  `-qvbr_quality_level` means the opposite. Measured on this Vega 10 by VMAF
  against a crf-12 reference, 20 s of 1080p30 of real footage:

  | `qvbr_quality_level` | VMAF | size |
  |---|---|---|
  | 10 | 81.92 | 505 KB |
  | 21 | 88.26 | 1130 KB |
  | 28 | 91.68 | 1527 KB |
  | 34 | 92.87 | 1875 KB |
  | 40 | 93.64 | 2240 KB |
  | 46 | 94.55 | 2781 KB |

  Monotonic across the range, and inverted. Handing the manifest's number
  straight over — which `_encode.py` did at first — makes `cq: 16`, the value a
  conform uses *because* it wants the highest quality, ask AMF for nearly its
  lowest. Every AMF render came out quietly worse than asked, and the symptom
  reads as a *virtue*: the file is smaller, which looks like efficiency rather
  than loss. `amf_quality()` inverts it, and `check-encode.py` now asserts the
  direction on every family — that cq 16 really does ask for better pictures
  than cq 30, whatever key the family spells it with. It also asserts that the
  list of families it walks still covers `_encode.RATE`, so a family added
  without a direction test fails rather than passing unexamined.
- **VideoToolbox runs backwards too, and its quality key is not in its own
  option list.** There is no `-cq` and no `-crf` on `h264_videotoolbox`;
  constant quality is the generic `-q:v`, which `ffmpeg -h
  encoder=h264_videotoolbox` does not print at all because it is
  AVCodecContext's `global_quality`. It runs 1..100 with **bigger meaning
  better**. The mapping is anchored on libx264 rather than stretched to fill
  the range, because what a manifest means by `cq: 21` is "what crf 21 looked
  like" — measured by VMAF on clean 1080p and on the same clip with grain:

  | | clean | grainy |
  |---|---|---|
  | `crf 21` | 97.38 | 96.93 |
  | `-q:v 62` | 97.32 | 97.21 |
  | `crf 16` | 98.77 | |
  | `-q:v 69` | 98.20 | |

  which puts the slope at 1.4 points of `-q:v` per point of `cq`. On the grainy
  clip the VideoToolbox file was less than half the size at the better score.
- **`ffmpeg -encoders` lists what the BUILD supports, not what this machine
  can do.** A full Windows build lists `h264_nvenc` whether or not an NVIDIA
  driver was ever installed — so the string test `check-env.py` used to run
  passed on an AMD box and reported "environment OK" while every render died
  with `Cannot load nvcuda.dll`. A doctor whose test the broken machine passes
  is worse than no doctor. Encoders are probed by **encoding a frame**, cached
  against the ffmpeg version.
- **A probe frame that is too small reports a working card as broken** — the
  same lie the other way round. A hardware encoder refuses a frame under its
  alignment with the same "could not open encoder" it gives a missing driver.
  Measured on this Vega 10: 64x64 fails, **160x120 fails** (120 is not a
  multiple of 16), 128x128 and 176x144 pass. `_encode.PROBE_SIZE` is 320x240
  and is a measured floor, not a round number — do not shrink it to make the
  probe cheaper.
- **A `preset` is a per-family word, not a universal one — and one family has
  no such word at all.** `p5` is NVENC's; AMF's are
  `speed`/`balanced`/`quality`/`high_quality`; x264's are `medium`/`slow`/... .
  Give AMF or x264 a `p5` and it exits on `invalid preset 'p5'` before a frame
  is read. Worse, AMF's *numbers* are not portable either — `h264_amf`'s
  presets run 0..3 and `hevc_amf`'s run 0..15, so `-quality 2` means different
  things on the two. `_encode.py` passes AMF presets by **name**, which both
  accept. VideoToolbox has no preset ladder in any spelling, and the three
  options that look like one are no-ops: `-prio_speed 1`, `-realtime 1` and
  `-spatial_aq 1` each produced a byte-identical file in the same 1.44 s on an
  M-series. Its speed entry is empty for that reason, not by oversight — the
  same kind of measurement as AMF's empty tuning block above.
- **`crop` has no `eval` option** — that is `scale`/`overlay`/`drawtext`. Its
  `x`/`y` are flagged runtime-tunable and already re-evaluated per frame, which
  is what lets the vertical crop pan. Passing `eval=frame` is a hard error.
- **The `ass` filter eats Windows backslashes.** `temp\05-x.ass` reaches libass
  as `temp05-x.ass`, because `\0` is an escape. Forward slashes everywhere.
- **`grouping.max_words` and `timing.min_active_ms` interact.** The builder's
  `group N overlaps group N-1` check fires when a group's per-word min-active
  cascade runs past the next group's start — which depends on where the group
  seam happens to fall. Changing one of the two and re-testing only one clip
  will look fine and break another. Tune them as a pair, re-test every clip, and
  never edit the builder to silence the check.
- **`aselect` silently passes every audio frame on ffmpeg 8.0.1.** The
  `select`/`aselect` pair is the usual way to drop spans in one pass, and the
  video half works. Measured on the same file with the same expression: video
  came out at 4.00 s, audio at 518.36 s — the full tape, picture racing ahead of
  sound. `atrim` is exact. `screencast-cut.py` therefore cuts with
  `trim`/`atrim` + `concat` throughout, and its duration assertion is what
  caught this (a 40 s preview rendered 1036.80 s, which is 2x the camera).
- **A phone's rotation tag can be wrong, and `-noautorotate` is not the fix.**
  IMG_2695 was shot with the phone mounted flat, so iOS wrote `rotation=-90`
  onto footage that is already upright. `-noautorotate` stops ffmpeg *applying*
  it but the bogus matrix is then **copied onto the output**, and every player
  turns the finished 1920x1080 film on its side while `ffprobe` still reports
  1920x1080. `-display_rotation:v:0 0` before the input rewrites the value
  instead, and nothing propagates. Read the tag as evidence, look at a frame,
  then decide — this repo has been bitten from both directions: ignoring a real
  rotation gives portrait footage a landscape crop.
- **An image input used by `alphamerge` or `overlay` must be `-loop 1`, and then
  the filter needs `shortest=1`.** A bare PNG is a one-frame stream, so a
  rounded-corner mask applies its alpha for exactly one frame and the square
  turns opaque for the rest of the film. Add `-loop 1` and the stream becomes
  *infinite*, so `alphamerge` waits forever for it to end: ffmpeg writes a
  file that grows and never gets a `moov` atom. You need both.
- **`trim` does not seek, it decodes and discards.** Without an upper bound
  ffmpeg reads every input to EOF no matter how little of it the film uses. `-to`
  as an *input* option caps the read without shifting timestamps the way `-ss`
  would — which matters when the trim times are absolute.
- **CUDA decode is not automatically faster.** On the 4K screen capture,
  `-hwaccel cuda` measured 10.2 s per 60 s of footage against 3.6 s on CPU: the
  content is static screen capture that decodes trivially, and the round-trip to
  the GPU costs more than it saves. Measure before reaching for it.
- **An ffmpeg option before an `-i` belongs to THAT input.** Adding badge PNGs
  to a cut turned a `-t` that used to sit next to the source into the *PNG's*
  duration, and the clip silently ran to the end of the source. `-ss` before the
  source, `-t` after every input. `cut-clips.py` checks the output duration
  against the plan, which is how that showed up as an error rather than as five
  eight-minute "shorts".

- **edge-tts's default boundary mode is `SentenceBoundary`.** Ask for
  `boundary="WordBoundary"` or you get audio and no word marks at all — and the
  dub's captions are timed from those marks. It also pads ~0.36s of silence onto
  the tail of a line, which has to be trimmed with the marks shifted to match,
  or every dubbed phrase starts late.
- **Give a translator a word budget and it will treat it as a ceiling.** The
  first dub came in short on 14 of 26 lines, and the fitter drawled the voice at
  its `-18%` floor to cover the gaps. Word the budget as a target to hit and say
  why (silence under a moving mouth looks worse than a slightly long line).

- **ElevenLabs' character-level alignment returns overlapping words** where
  edge returns none, and the caption builder rightly refuses to write an ASS
  whose groups overlap. `dub-tts.monotonic()` fixes the marks — and has to run
  *after* the silence trim, not before: the trim shifts every mark and clamps at
  zero, which collapses each word that began inside the trimmed lead onto 0.0
  and recreates the exact overlaps. A guarantee established early is not a
  guarantee if a later transform can violate it.
- **A TTS-scoped ElevenLabs key cannot list voices.** `GET /v1/voices` and
  `/v1/user/subscription` 401 with `missing_permissions` while synthesis works
  fine, so voice ids have to be kept by hand in
  `config/elevenlabs-voices.json` — and only the ones marked `verified: true`
  there have actually been called. Two shipped ids in that file used to 404.
- **A media player holding the previous render open** makes the final rename
  fail with EACCES on Windows, discarding a finished encode over a file lock.
  `cut-clips.py` waits it out.

## Legacy

`scripts/transcribe-audio.py` (OpenAI Whisper API) and
`scripts/generate-voiceover.py` (ElevenLabs TTS + ducking) predate this pipeline
and are unrelated to captions. Both have known bugs — `transcribe-audio.py` puts
the transcript text in its `file` field, and `generate-voiceover.py` computes
per-line start times then concatenates clips end to end, ignoring them.
`WORKSPACE-SETUP.md` and `docs/QUICKSTART.md` documented that original scaffold
— shared `sources/ outputs/ audio/` folders, a hand `pip install requests`, no
`_env` bootstrap — and were deleted rather than half-corrected: a document that
contradicts the code is worse than no document, and git keeps them. The same
went for their `config/video-specs.template.json`, a hand-authored per-video
project document, when `projects/<id>/project.json` replaced the idea: no script
ever read or wrote the template, so it silently rotted, which is the failure
mode the project files are designed against (see `## Projects`).

<!-- dev-only: tester-export -->
## Sharing the tooling: the tester copy

The dev repo cannot be handed to an outside tester: it carries the business
docs, every project journal with our publish history, and manifests that quote
fragments of the very secrets the redaction pipelines blur.
`make-tester-repo.py` builds the copy that can be handed out — an **allowlist**
(scripts, config, fonts, skills, the reference docs), never an excludelist, so
nothing leaks that the script never read. `docs/tester-quickstart.md` ships as
the copy's `QUICKSTART.md`; `config/tester/settings.json` ships as its
`.claude/settings.json`, permission allow-list pre-seeded so a first session is
not forty prompts; the content dirs are recreated empty.

```powershell
python scripts/make-tester-repo.py --list             # what ships, what never does
python scripts/make-tester-repo.py --out ..\kitcut     # the tree, no history
python scripts/make-tester-history.py --list          # commits kept, text redacted
python scripts/make-tester-history.py --out ..\kitcut  # the tree AND the history
```

**`make-tester-history.py` is the one to use** — the commits are the record of
how the tooling was built and they are worth handing over. A plain clone cannot
do it: every excluded file still sits in the commit that added it, so the
history would ship what the tree does not. It rewrites all 79 commits with
`git-filter-repo` against the *same allowlist* (imported from the tree
exporter, so the two cannot drift), drops both exporters — they name the
excluded docs in their own constants — and redacts the text that points at what
stayed behind. Three failures found while building it, each now a check:
blanking a filename left CLAUDE.md's **summary** of the excluded doc in place,
so whole table rows go; a commit message's **body** spelled out the business
plan while its subject looked innocent, so full messages are scanned and a
flagged one that is neither rewritten nor explicitly reviewed FAILS the build;
and `config/` shipped wholesale, which included the chapter list of every video
we have published.

Three self-checks make the copy prove itself before it exists: CLAUDE.md is
scrubbed of references to the excluded docs by **exact-match replacements that
FAIL when the map's text drifts**; any region fenced by the dev-only HTML
comment markers in a shipped markdown file (like this section) is dropped —
and never write those markers literally *inside* such a region, the inner
close ends it early, which is how this paragraph's first draft shipped its
own tail; and the finished tree is scanned for excluded paths, forbidden
strings and surviving markers — a mention that survives fails the build
rather than shipping. A rebuild into a copy that
already has its `.venv`/`.git` is allowed, so iterating does not cost a
reinstall.
<!-- /dev-only -->
