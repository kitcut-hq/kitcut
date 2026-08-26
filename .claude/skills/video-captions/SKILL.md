---
name: video-captions
description: Add word-synced burned-in captions ("real time transcript" subtitles) to a video from a YouTube URL or local file. Transcribes locally with faster-whisper, generates a styled ASS subtitle file with per-word highlighting, and burns it in with NVENC. Use when asked to add subtitles, captions, or transcripts to a video, or to restyle existing caption output.
---

# Word-synced burned-in captions

One command, from URL to captioned MP4:

```powershell
cd C:\instafill\video-editing
python scripts/run-captions.py --url "<YOUTUBE_URL>" --style config/presets/red-card.json
```

Local file instead: `--input path\to\video.mp4 --id myclip`

Output lands at `outputs/<id>-captioned.mp4`, with a reproducibility manifest at
`outputs/<id>.manifest.json` (tool versions, style/transcript hashes, timings).
Total runtime is roughly **0.5-0.9x the video duration** on this machine with
CUDA available; transcription and overlay detection run in parallel.

Works at any resolution: presets are authored for a 1920x1080 canvas and every
pixel value is scaled to the actual video automatically (720p, 1440p, vertical).
ASR language is autodetected unless you pass `--lang`; if CUDA is unavailable or
fails mid-run, transcription falls back automatically (cuda/int8 → cpu/int8).

## Always do these two things first

1. **Check the audio tracks.**
   `.venv/Scripts/python.exe -m yt_dlp -F <URL> | grep "audio only"`. If you see both an
   `original` and a `dubbed-auto` track, the pipeline's selector already prefers
   `original` — but confirm the transcript's detected language after the run.
   Transcribing a YouTube AI dub silently produces a perfect transcript of the
   wrong language. One Shorts video carried **21** audio tracks (1 original + 20
   AI dubs), so this is not a rare edge case.

   Always invoke yt-dlp as `.venv/Scripts/python.exe -m yt_dlp`, never as bare `yt-dlp` — see traps.
2. **Pick or derive the style.** Never edit code to change appearance. Either use
   a preset in `config/presets/`, or measure a reference frame and write a new one.

## Deriving a style from a reference video

```powershell
.venv/Scripts/python.exe -m yt_dlp --download-sections "*MM:SS-MM:SS" -f "<vfmt>+<afmt>" -o "temp/ref.%(ext)s" "<URL>"
ffmpeg -i temp/ref.mp4 -vf "fps=5" -q:v 3 "temp/ref/f_%03d.jpg"
```
Read the frames, then measure the caption band on a **native-resolution** frame
(cap height in px, card colour, corner radius, padding, margins) rather than
eyeballing it. Put the numbers in a new preset.

For brand colours, sample the channel thumbnail: mask to saturated pixels
(`sat>0.45`), quantise, and take the most common buckets.

## Style presets

`config/presets/*.json` — every visual choice lives here.

| Key | Effect |
|---|---|
| `font.family` / `font.file` / `font.fontsdir` | typeface; family must match the file's real family name |
| `font.cap_height_px` | **preferred way to size text** — nominal size is derived |
| `font.size` | explicit nominal size; overrides `cap_height_px` |
| `font.bold` | 1 requests weight 700; must match the file or libass substitutes |
| `text.uppercase`, `text.apostrophe`, `text.strip_trailing` | text transforms |
| `text.outline_px` / `outline_colour`, `shadow_px` / `shadow_colour` | stroke + drop shadow |
| `card.enabled` | `false` = no background card, text only |
| `card.colour`, `card.alpha`, `card.corner_radius_px`, `card.pad_x_px`, `card.pad_y_px` | the card |
| `card.collision_gap_px` | clearance when dodging the source's own graphics |
| `layout.anchor_x`, `bottom_margin_px`, `max_lines`, `max_line_width_px`, `line_height_px` | placement |
| `states.base` / `states.active` / `states.spoken` | **`spoken == base` → moving spotlight; `spoken == active` → progressive karaoke fill** |
| `pop.enabled`, `pop.scale`, `pop.rise_ms`, `pop.settle_ms` | scale pop on the active word |
| `grouping.*` | words per card, pause/sentence breaks, max duration |
| `timing.*` | lead-in, hold-out, min highlight, fade |
| `render.*` | encoder, preset, cq, bitrate caps |

## Dodging the source's own graphics

`detect-overlays.py` finds lower-third graphics already burned into the source so
caption cards can be lifted clear of them. Set the colour to hunt for in the
preset's `overlays.colour` — this is the **source graphic's** colour, not your
card's.

Targeted mode is the reliable one: on the first video it found 9/9 real graphics
with zero false positives, including five that a keyframe-only scan had missed.

`overlays.auto` (colour-agnostic) is **experimental and not trustworthy** — on an
interview shot with a yellow and a red armchair in frame it invented 5 overlays
that did not exist, one spanning y 620..1076. If you enable it, read the printed
ranges and sanity-check a frame from each before rendering.

If a source uses a non-red lower third, set `overlays.colour` to it. If a source
has no graphics at all, 0 ranges is the correct answer, not a failure.

## Stages and resuming

`download → audio → transcribe ∥ overlays → ass → verify → render`

Each stage is skipped when its artifact exists. Rerun one stage and everything
after it with `--force ass`; stop early with `--stop-after <stage>`. Useful
flags: `--preview 380 25` (render just a 25 s window, with a correctly
time-shifted ASS), `--no-overlays`, `--samples N`, `--device cpu`,
`--min-free-gb N`.

Artifact locations matter: the transcript goes to `transcripts/<id>.words.json`
— the ONE artifact that costs minutes of GPU time — while everything in `temp/`
regenerates in seconds and is safe to delete.

Iterate on style with `--force ass --stop-after verify` (~9 s) or
`--force ass --preview <t> 20` for a watchable clip.

After a full render the pipeline verifies the output itself (duration match,
bitrate sanity — a ~2 Mbps result means `-cq` got ignored — and faststart box
order) and refuses to report success if any check fails.

## Non-obvious traps (all already handled — do not "fix" them)

- **The environment is fixed; run scripts as plain `python scripts/<name>.py`.** A machine-wide `PYTHONPATH` used to point at another Python install and break `import faster_whisper` -- and a venv did not help, because `PYTHONPATH` is prepended inside one too. It has been removed, and every script now imports `scripts/_env.py` first, which re-execs into `.venv` with a clean environment and forces UTF-8 stdio on this cp1252 console. Run `python scripts/check-env.py` if an import ever breaks again.
- **libass sizes fonts by `usWinAscent + usWinDescent`, not `unitsPerEm`.** For
  Montserrat that is 1562 vs 1000, so a nominal 43 px renders at 0.64x. This is
  why `font.cap_height_px` exists — use it.
- **Variable fonts do not work.** libass registers only the default instance, so
  requesting weight 700 falls back to Arial. Use a genuine static TTF.
  fontTools-instanced statics are also rejected.
- **CUDA needs cuBLAS on `PATH`.** ctranslate2 bundles cuDNN but not cuBLAS and
  loads it lazily via plain `LoadLibrary`, which ignores `os.add_dll_directory`.
- **Never seek with plain `-ss` when burning subtitles** — it rebases PTS to 0 so
  libass renders the wrong lines. Use `--preview`, which regenerates a shifted ASS.
- **`-b:v 0` is required with `-cq`** or NVENC ignores the quality target and text
  goes mushy.
- **Keep filter paths relative** and run ffmpeg from the workspace root.
- **Never invoke `yt-dlp` (or any console script) as a bare command.** The shim on
  PATH hardcodes the interpreter that installed it, so when that Python is removed
  or upgraded it dies *silently* — exit 1, zero bytes on stdout and stderr, no
  traceback to read. A reinstall often lands its replacement in a Scripts dir that
  is not on PATH, so the dead shim keeps winning. Use `.venv/Scripts/python.exe -m yt_dlp`.
- **Vertical video needs `--height 1920`.** The format selector filters on height,
  so the 1080 default picks a 608x1080 downscale of a 1080x1920 Short.
- **Clamping caption width must budget for card padding.** Going landscape →
  vertical scales every px value up ~1.78x while the frame gets *narrower*; the
  card is text width + 2x padding, so clamping the text alone puts the card off
  the edge. The self-check catches this.

## Verification

Two independent layers, both **fatal** — neither warns-and-continues:

1. **Structural self-check** (in `build-captions-ass.py`) — off-canvas cards,
   overlapping active windows, non-positive durations. Refuses to *write* the ASS.
2. **Sync probe** (`verify-captions.py`) — renders the caption layer onto black,
   probes frames at word midpoints, asserts the word in the active colour is the
   expected one. The pipeline refuses to *render* if this fails.

Do not skip either, and do not downgrade them to warnings. A check that reports a
defect and proceeds anyway is not a check — the off-canvas bug on the first
vertical video was detected correctly and shipped anyway for exactly that reason.

Full background: `docs/karaoke-captions.md`.
