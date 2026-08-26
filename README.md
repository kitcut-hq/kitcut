# video-captions

Add word-synced burned-in captions to a video — a "real time transcript" where
the currently-spoken word is highlighted — from a YouTube URL or a local file.

Runs entirely locally: `faster-whisper` for word-level timestamps, a generated
ASS subtitle file for styling, and NVENC to burn it in. No API keys, nothing
uploaded.

```powershell
python -X utf8 -E scripts/run-captions.py --url "<URL>" --style config/presets/red-card.json
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
| `layout.anchor_x`, `bottom_margin_px`, `max_lines`, `max_line_width_px` | placement |
| `states.base` / `active` / `spoken` | `spoken == base` → spotlight; `spoken == active` → progressive karaoke fill |
| `pop.*` | scale animation on the active word |
| `grouping.*`, `timing.*` | words per card, breaks, lead-in/hold, fades |
| `overlays.colour` | colour of the *source's own* lower-third graphics, to dodge them |
| `render.*` | encoder, preset, cq, bitrate caps |

Presets are authored on a 1920x1080 canvas and every pixel value is scaled
automatically to the actual video, so 720p / 1440p / vertical all work.

Two presets ship: `red-card` (solid red info-card, yellow spotlight) and
`eu-navy` (EU-flag blue, star-yellow spotlight).

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
python -X utf8 -E scripts/transcript-outline.py transcripts/<id>.words.json --outline
python -X utf8 -E scripts/transcript-outline.py transcripts/<id>.words.json --find "so anyway"

# resolve every boundary and print the plan without encoding anything
python -X utf8 -E scripts/cut-clips.py --manifest config/clips/<id>.json --list
python -X utf8 -E scripts/cut-clips.py --manifest config/clips/<id>.json
```

A manifest names the source, the transcript, and the clips:

```json
{
  "source": "outputs/<id>-captioned-1080p60.mp4",
  "words": "transcripts/<id>.words.json",
  "outdir": "outputs/shorts",
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
python -X utf8 -E scripts/auto-reframe.py --manifest config/clips/<id>-vertical.json
# 2. cut: crop -> scale -> captions -> badge, one encode
python -X utf8 -E scripts/cut-clips.py --manifest config/clips/<id>-vertical.json
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
- Per-clip `crop_x` (static), `crop_keys` (inline) and `crop_pad` override the
  sidecar.
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

## The handle badge

A camera glyph above an `@handle`, hopping between anchor points on a timer and
alternating between a flat glyph and a gradient one — a moving mark is harder to
crop out or paint over than a fixed corner watermark.

```powershell
# eyeball the style without encoding anything
python -X utf8 -E scripts/handle-overlay.py --badges-only --handle "@name"

# burn it into an existing file
python -X utf8 -E scripts/handle-overlay.py --video in.mp4 --handle "@name"
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

## Requirements

- Python 3.12+ with `faster-whisper`, `ctranslate2`, `fonttools`, `numpy`, `pillow`
- `opencv-python<5` and `scenedetect` — only for `auto-reframe.py`, which falls
  back to `--mode pan` without the latter. The OpenCV pin is load-bearing:
  version 5 ships no Haar cascades, and its `FaceDetectorYN` replacement wants a
  model downloaded from an external host.
- `ffmpeg`/`ffprobe` built with **libass** (check: `ffmpeg -filters | grep ass`)
- `yt-dlp`
- Optional NVIDIA GPU. CUDA also needs `nvidia-cublas-cu12` — ctranslate2 bundles
  cuDNN but not cuBLAS. Without a working GPU the pipeline falls back
  automatically (`cuda/int8_float16 → cuda/int8 → cpu/int8`); CPU runs at roughly
  1x realtime instead of ~3x.

## Repo layout

| Path | |
|---|---|
| `scripts/run-captions.py` | the orchestrator — start here |
| `scripts/transcribe-words.py` | faster-whisper → word-level JSON |
| `scripts/detect-overlays.py` | finds the source's own lower-third graphics |
| `scripts/build-captions-ass.py` | words + preset → styled ASS |
| `scripts/verify-captions.py` | proves sync by probing rendered frames |
| `scripts/transcript-outline.py` | skim a transcript; find the time of a phrase |
| `scripts/cut-clips.py` | manifest → standalone clips cut out of a long video |
| `scripts/handle-overlay.py` | animated social-handle badge, drawn and burned in |
| `config/presets/` | all visual styling |
| `config/clips/` | clip manifests (which episodes to cut, and where) |
| `config/handles/` | handle-badge styling and motion |
| `fonts/` | Montserrat Bold (SIL OFL 1.1, see `fonts/OFL.txt`) |
| `docs/karaoke-captions.md` | design notes and the traps behind them |
| `.claude/skills/video-captions/` | Claude Code skill |

`sources/`, `audio/`, `transcripts/`, `outputs/`, `temp/` are working
directories and are **git-ignored** — they hold third-party video and material
derived from it, which is never committed.

Of those, `transcripts/` is the only expensive artifact (minutes of GPU time);
everything in `temp/` regenerates in seconds.

## Gotchas worth knowing

These are load-bearing; `docs/karaoke-captions.md` has the full list with
evidence.

- **`python -X utf8 -E` is required** on the dev machine — a global `PYTHONPATH`
  pointing at another Python version breaks `faster_whisper`, and `sys.path` is
  frozen at startup so fixing it in-process doesn't work. `-E` also disables
  UTF-8 stdio on a cp1252 console, hence `-X utf8` too.
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
- **`-b:v 0` is required with `-cq`** or NVENC ignores the quality target.
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
- **An ffmpeg option before an `-i` belongs to THAT input.** Adding badge PNGs
  to a cut turned a `-t` that used to sit next to the source into the *PNG's*
  duration, and the clip silently ran to the end of the source. `-ss` before the
  source, `-t` after every input. `cut-clips.py` checks the output duration
  against the plan, which is how that showed up as an error rather than as five
  eight-minute "shorts".

## Legacy

`scripts/transcribe-audio.py` (OpenAI Whisper API) and
`scripts/generate-voiceover.py` (ElevenLabs TTS + ducking) predate this pipeline
and are unrelated to captions. Both have known bugs — `transcribe-audio.py` puts
the transcript text in its `file` field, and `generate-voiceover.py` computes
per-line start times then concatenates clips end to end, ignoring them.
`WORKSPACE-SETUP.md` documents that original scaffold and is partly stale.
