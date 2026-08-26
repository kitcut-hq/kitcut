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
python scripts/transcript-outline.py transcripts/<id>.words.json --outline
python scripts/transcript-outline.py transcripts/<id>.words.json --find "so anyway"

# resolve every boundary and print the plan without encoding anything
python scripts/cut-clips.py --manifest config/clips/<id>.json --list
python scripts/cut-clips.py --manifest config/clips/<id>.json
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
python scripts/auto-reframe.py --manifest config/clips/<id>-vertical.json
# 2. cut: crop -> scale -> captions -> badge, one encode
python scripts/cut-clips.py --manifest config/clips/<id>-vertical.json
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
# translate, speak and fit -- writes outputs/dub/<name>.en.wav + .en.words.json
python scripts/dub-clips.py --manifest config/clips/<id>-vertical.json --only <clip-id>

# render the dubbed cut; captions come from the dub's own word timings
python scripts/cut-clips.py --manifest config/clips/<id>-vertical.json `
    --only <clip-id> --dub outputs/dub
```

The output is named `…-<tag>.mp4` (`en` by default), so the original is never
overwritten.

Two voices are available. edge-tts needs no key and has the wider speed range;
ElevenLabs sounds better and needs `ELEVENLABS_API_KEY` in `.env`. Give each run
its own `--tag` and they coexist:

```powershell
python scripts/dub-clips.py --manifest ... --only <id> `
    --tts elevenlabs --voice jessica --tag en-el
python scripts/cut-clips.py --manifest ... --only <id> --dub outputs/dub --dub-tag en-el
```

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
| `--voice` | `ava` | `--list-voices` on `dub-tts.py` for the rest |
| `--max-dur` | `4.0` | longer slots translate better and sync worse |
| `--words-per-sec` | `3.2` | the per-slot word budget handed to the translator |
| `--tune-rounds` | `1` | measure-then-rewrite passes |
| `--engine` | `claude` | translation: or `openai` (needs a key), or `manual` |
| `--tts` | `edge` | or `elevenlabs` |
| `--voice` | `ava` / `jessica` | default follows `--tts` |
| `--tag` | `en` | names this run's artifacts; one per backend |

`--engine manual` takes a hand-written `[{"i":1,"text":"...","tight":"..."}]`
via `--translation`, which is the escape hatch when a line has to be exact.

## Chapter markers on a published video

Turn a transcript into YouTube chapters, then write them into the video's own
description:

```powershell
python scripts/transcribe-words.py audio/<id>.m4a --out transcripts/<id>.words.json --language en
python scripts/transcript-outline.py transcripts/<id>.words.json --outline   # read, pick boundaries
# write config/chapters/<id>.txt as "MM:SS Title" lines, then:
python scripts/yt-set-chapters.py <id> --chapters config/chapters/<id>.txt --dry-run
python scripts/yt-set-chapters.py <id> --chapters config/chapters/<id>.txt
```

Picking the boundaries is editorial and stays a human/model judgement — the
script's job is to make the result *valid* and the write *safe*.

It refuses to upload a list YouTube would silently ignore: the first chapter
must be at `00:00`, there must be at least three, and consecutive marks must be
at least 10 s apart. YouTube does not report any of these as errors; it just
renders no chapters at all, which is easy to mistake for a failed update.

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

The first run opens a browser for consent and caches a refresh token at
`.yt-oauth/token.json`; later runs are non-interactive. Quota note: `videos.update`
costs 50 units of the default 10,000/day, while the `videos.list` read costs 1.

## Setup

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup-python.ps1   # build .venv
python scripts/check-env.py                                          # prove it works
```

That is the whole setup. Afterwards every script runs as plain
`python scripts/<name>.py` from any shell — they re-exec themselves into `.venv`
via `scripts/_env.py`, so there is nothing to activate and no `-E` to remember.
`check-env.py` is also the first thing to run when an import breaks; it reports
the cause rather than leaving you to infer it from a DLL error.

Needed on the machine itself:

- **Python 3.13** (`py -3.13`). Package versions are pinned in `requirements.txt`.
- **`ffmpeg`/`ffprobe` built with libass and rubberband** — `check-env.py`
  verifies both, plus NVENC.
- **Optional NVIDIA GPU.** CUDA needs `nvidia-cublas-cu12`, since ctranslate2
  bundles cuDNN but not cuBLAS; `check-env.py` counts the DLLs it can see,
  because without them transcription silently drops to CPU and runs ~3x slower.
- **Network**, for `edge-tts` during dubbing. No API key is needed for either
  the voice or (with `--engine claude`) the translation.

The `opencv-python<5` pin is load-bearing: version 5 ships no Haar cascades at
all, and its `FaceDetectorYN` replacement wants a model from an external host.

## Repo layout

| Path | |
|---|---|
| `CLAUDE.md` | orientation: how to run things, and the house rules |
| `scripts/_env.py` | re-execs every script into `.venv`; import it first |
| `scripts/setup-python.ps1` | builds/repairs the environment, idempotent |
| `scripts/check-env.py` | the doctor — run this when an import breaks |
| `scripts/run-captions.py` | the orchestrator — start here |
| `scripts/transcribe-words.py` | faster-whisper → word-level JSON |
| `scripts/detect-overlays.py` | finds the source's own lower-third graphics |
| `scripts/build-captions-ass.py` | words + preset → styled ASS |
| `scripts/verify-captions.py` | proves sync by probing rendered frames |
| `scripts/transcript-outline.py` | skim a transcript; find the time of a phrase |
| `scripts/yt-set-chapters.py` | write chapter markers into a video's description |
| `scripts/cut-clips.py` | manifest → standalone clips cut out of a long video |
| `scripts/handle-overlay.py` | animated social-handle badge, drawn and burned in |
| `scripts/dub-clips.py` | translate a clip and speak it back into its own cadence |
| `scripts/dub-translate.py` | per-slot translation under a time budget |
| `scripts/dub-tts.py` | neural TTS with word boundaries and rate control |
| `config/presets/` | all visual styling |
| `config/chapters/` | chapter lists, one `MM:SS Title` per line |
| `config/clips/` | clip manifests (which episodes to cut, and where) |
| `config/handles/` | handle-badge styling and motion |
| `fonts/` | Montserrat Bold (SIL OFL 1.1, see `fonts/OFL.txt`) |
| `docs/karaoke-captions.md` | design notes and the traps behind them |
| `.claude/skills/` | Claude Code skills: captions, shorts, dub |

`sources/`, `audio/`, `transcripts/`, `outputs/`, `temp/` are working
directories and are **git-ignored** — they hold third-party video and material
derived from it, which is never committed.

Of those, `transcripts/` is the only expensive artifact (minutes of GPU time);
everything in `temp/` regenerates in seconds.

## Gotchas worth knowing

These are load-bearing; `docs/karaoke-captions.md` has the full list with
evidence.

- **A venv does not protect you from `PYTHONPATH`,** and neither does pip. A
  global `PYTHONPATH` aimed at another Python's site-packages makes 3.13 load
  3.11's compiled extensions (`DLL load failed`, or a bare segfault under Git
  Bash) — *and* convinces pip those dependencies are already satisfied, so it
  installs a venv quietly missing `yaml` and `idna`. `setup-python.ps1` clears
  the variable before installing and finishes with `pip check`; `_env.py` clears
  it for every child process. This is handled now: run scripts as plain
  `python scripts/<name>.py`.
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
`WORKSPACE-SETUP.md` documents that original scaffold and is partly stale.
