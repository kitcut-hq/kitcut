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

Three presets ship: `red-card` (solid red info-card, yellow spotlight),
`red-card-vertical` (the same styling re-authored for a 9:16 canvas, used by
the shorts pipeline) and `eu-navy` (EU-flag blue, star-yellow spotlight).

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
video-editing | ⎇ main | Fable 5 (1M context) | effort: xhigh | ctx: 33% (334k) | 5h: 26% 2h58m | wk: 60% 2d18h
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
  it; rubberband and NVENC are warnings, because a dub can fit without the
  stretcher and a manifest can name `libx264` instead of `h264_nvenc`.
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

## Repo layout

| Path | |
|---|---|
| `CLAUDE.md` | orientation: how to run things, and the house rules |
| `scripts/_env.py` | re-execs every script into `.venv`; import it first |
| `scripts/setup-python.ps1` | builds/repairs the environment, idempotent |
| `scripts/check-env.py` | the doctor — run this when an import breaks |
| `scripts/check-dub.py` | dub self-test; no key, no TTS calls, no cost |
| `scripts/run-captions.py` | the orchestrator — start here |
| `scripts/transcribe-words.py` | faster-whisper → word-level JSON |
| `scripts/detect-overlays.py` | finds the source's own lower-third graphics |
| `scripts/build-captions-ass.py` | words + preset → styled ASS |
| `scripts/verify-captions.py` | proves sync by probing rendered frames |
| `scripts/transcript-outline.py` | skim a transcript; find the time of a phrase |
| `scripts/_ytchapters.py` | chapter-marker rules, and what YouTube really enforces |
| `scripts/yt-set-chapters.py` | write chapter markers into a video's description |
| `scripts/yt-audit-chapters.py` | which videos on a channel actually show chapters |
| `scripts/cut-clips.py` | manifest → standalone clips cut out of a long video |
| `scripts/_overlay.py` | drawing and filter helpers shared by the burned-in graphics |
| `scripts/_progress.py` | publishes an ffmpeg render's position for the status line |
| `scripts/render-status.py` | the Claude Code status line for this repo |
| `scripts/handle-overlay.py` | animated social-handle badge, drawn and burned in |
| `scripts/name-label.py` | lower-third name label, drawn and burned in |
| `scripts/dub-clips.py` | translate a clip and speak it back into its own cadence |
| `scripts/dub-translate.py` | per-slot translation under a time budget |
| `scripts/dub-tts.py` | neural TTS with word boundaries and rate control |
| `scripts/sync-tracks.py` | line up a silent screen capture with the camera take, and prove it |
| `scripts/screencast-cut.py` | drop the dead air and composite the two into one film |
| `scripts/import-iphone.ps1` | pull footage off a phone over MTP, verified by byte count |
| `scripts/yt-upload.py` | upload a render to YouTube, channel-guarded and verified |
| `scripts/yt-fetch-transcripts.py` | pull audio + word transcripts for published channel videos |
| `scripts/yt-audit-chapters.py` | verdict per channel video: has chapters, needs them, or too short |
| `scripts/verify-chapters.py` | check a chapter list against the transcript before it goes live |
| `scripts/chapter-thumbs.py` | contact sheet of the frame each chapter timestamp lands on |
| `scripts/check-script.py` | conformance check for new/changed scripts (see the check-script skill) |
| `scripts/_project.py` | the project-metadata writer every finishing script calls |
| `scripts/project-scan.py` | bootstrap and doctor for project files |
| `projects/<id>/` | one video: metadata + manifests committed, content gitignored — see `## Projects` |
| `config/presets/` | all visual styling |
| `config/chapters/` | legacy chapter lists for already-published channel videos; new projects keep `chapters.txt` in their folder |
| `config/labels/` | the lower-third name label's styling |
| `config/handles/` | handle-badge styling and motion |
| `fonts/` | Montserrat Bold (SIL OFL 1.1, see `fonts/OFL.txt`) |
| `docs/karaoke-captions.md` | design notes and the traps behind them |
| `.claude/skills/` | Claude Code skills: captions, shorts, dub, multicam, name-label, project |

`sources/`, `audio/`, `transcripts/`, `outputs/`, `temp/` — at the top level
and inside each project folder — are working directories and are
**git-ignored**: they hold third-party video and material derived from it,
which is never committed. The top-level ones are the legacy shared layout;
new work lives under `projects/`.

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
- **A name label past the end of the film fails silently.** The overlay's
  `enable` expression simply never turns true; ffmpeg reports nothing, the
  render succeeds, and the card is not in it. `screencast-cut.py` checks every
  `name_labels` entry against the cut runtime — which is only known after the
  cut — for exactly this reason.
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
`WORKSPACE-SETUP.md` documents that original scaffold and is partly stale.
Its `config/video-specs.template.json` — a hand-authored per-video project
document — was deleted when `projects/<id>/project.json` replaced the idea: no
script ever read or wrote the template, so it silently rotted, which is the
failure mode the project files are designed against (see `## Projects`).
