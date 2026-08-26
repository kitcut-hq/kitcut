---
name: video-shorts
description: Extract shorts/episodes from a long video, optionally reframed to vertical 9:16, and stamp them with an animated Instagram-handle badge. Reads the word-level transcript to pick self-contained episodes, resolves cut boundaries by quoting what is said (not by timecodes), face-tracks the crop window so the subject stays in frame, re-renders captions at vertical size, and burns everything in one NVENC pass. Use when asked to make shorts, extract clips or episodes from a video, to make a video vertical for Reels/Shorts/TikTok, or to add a social-handle watermark to clips.
---

# Shorts out of a long video, with a handle badge

The whole workflow, once a manifest exists:

```powershell
cd C:\instafill\video-editing
python scripts/cut-clips.py --manifest config/clips/<id>.json --list   # plan only
python scripts/cut-clips.py --manifest config/clips/<id>.json          # cut
```

Clips land in `outputs/shorts/` as `<prefix>-<clipid>.mp4`, each with a `.json`
sidecar recording exact boundaries and encoder settings. Cutting runs ~3x
realtime on this machine (five ~75s clips ≈ 2 minutes). Existing outputs are
skipped, so editing one manifest entry and re-running rebuilds only that entry;
`--only <ids>` / `--force` narrow it further.

**Prerequisite:** a word-level transcript at `transcripts/<id>.words.json`. If
there isn't one, run the captions pipeline first (see the `video-captions`
skill) or just its transcribe stage — everything below keys off that file.
Prefer cutting from the **captioned master** in `outputs/` so the shorts carry
the burned-in subtitles.

## Step 1 — analyze: pick the episodes

Dump the transcript as timestamped lines and read it end to end:

```powershell
python scripts/transcript-outline.py transcripts/<id>.words.json --outline
```

What makes a good as-is short (no editing pass to save it later):

- **Self-contained arc** — opens on the start of a thought, closes on a payoff
  or punchline. Never open mid-sentence.
- **60–90 s** for talking-head content; under 60 s for a single gag/story.
- Prefer segments with emotion, concrete numbers, a strong visual, or a
  controversial thesis — those carry a clip with zero extra editing.
- **Skip the video's intro** (it never stands alone) and **skip sponsor reads**;
  check that a chosen segment doesn't start right inside one.

Verify each candidate boundary before writing the manifest:

```powershell
python scripts/transcript-outline.py transcripts/<id>.words.json --find "exact phrase"
```

## Step 2 — the manifest

`config/clips/<id>.json`. Boundaries are **quoted speech**, not timecodes, so
the manifest reads like the edit decisions that were made:

```json
{
  "source": "outputs/<id>-captioned-1080p60.mp4",
  "words": "transcripts/<id>.words.json",
  "outdir": "outputs/shorts",
  "prefix": "<id>",
  "pad": { "head": 0.15, "tail": 0.35 },
  "handle": { "text": "@kris_zahrebelna", "preset": "config/handles/default.json" },
  "clips": [
    { "id": "01-slug", "title": "…",
      "start_text": "ну що, тільки що кур'єр",
      "end_before_text": "наступне, друге" }
  ]
}
```

- `start_text` starts where that phrase begins; `end_text` ends where that
  phrase ends; `end_before_text` ends just before that phrase begins (use it to
  cut right before the next thought). Matching ignores case, punctuation and
  spacing, so phrases pasted from the outline (words run together) and typed
  ones both hit. Plain `start`/`end`/`duration` seconds also work.
- Pads never eat a neighbouring word — when the transcript says speech continues
  inside the pad, the boundary meets it halfway. So don't hand-tune pads per
  clip; the defaults are right.
- Cuts re-encode (NVENC) and are frame-accurate. `--copy` stream-copies —
  instant but keyframe-snapped, and it cannot burn in the handle.

## Step 3 — the handle badge

Declared in the manifest (`handle` key, above) and applied **during the cut** —
one encode, no second generation loss. CLI overrides: `--handle "@name"`,
`--handle-preset <path>`, `--no-handle`.

The badge is a camera glyph above the @handle that hops between anchor points
every `move_every_s` and alternates flat-white/gradient every `colour_every_s`
(two independent cycles — the combination doesn't repeat quickly, which is the
anti-crop point). All styling and motion lives in `config/handles/*.json`,
authored on 1920x1080 and scaled to the real video. Keep `motion.positions`
(badge centres) clear of the caption card at the bottom.

Standalone use on any existing file:

```powershell
python scripts/handle-overlay.py --badges-only --handle "@name"      # preview PNGs
python scripts/handle-overlay.py --video in.mp4 --handle "@name"     # burn in
```

Architecture, if editing it: Pillow draws the badge once per colour variant into
a PNG (fonts, gradients, outlines are easy there); ffmpeg animates it with
`overlay` using `x`/`y`/`enable` expressions in `t`. One filter pass, no
per-frame Python. Don't try to move this into ASS — libass has no gradients.

## Vertical 9:16

Do **not** crop the captioned master — its caption cards are up to ~1180 px wide
on a 1920 canvas and a 9:16 window is only 607 px, so the crop slices the
subtitles. Cut from the **clean source** and re-render captions after the crop.
Use a second manifest for it (`config/clips/<id>-vertical.json`) so the
landscape build stays intact:

```json
"source": "sources/<id>-1080p60.mp4",
"vertical": { "width": 1080, "height": 1920 },
"captions": { "style": "config/presets/red-card-vertical.json", "samples": 24 },
"handle":   { "text": "@name", "preset": "config/handles/vertical.json" }
```

Order inside the single encode is crop → scale → captions → badge, so captions
and badge are both sized for the frame the viewer sees.

**Reframe first.** A fixed centre crop is a bet that the subject is centred;
over a real video they are not.

```powershell
python scripts/auto-reframe.py --manifest config/clips/<id>-vertical.json
```

It writes `config/clips/<id>-vertical.reframe.json`, which `cut-clips.py` picks
up automatically. The default `--mode hybrid` splits each clip at its shot
boundaries and decides every shot on its own:

| | when | result |
|---|---|---|
| `static` | face barely moves in the shot | window frozen |
| `pan` | face moves | window tracks it |
| `pad` | no face found | **not cropped** — whole frame letterboxed over a blurred fill |

`pad` is what saves full-width burned-in graphics and b-roll, which no 607 px
window can contain. It is switched by `enable` on an overlay, so it still costs
one encode, and captions and badge composite on top of it.

Report the detection rate and the per-shot plan it prints. Two things to check
by eye every time:

- **A `pad` decision only ever means "no face found here."** Usually b-roll, but
  a shot where the subject looks down or away reads identically — one clip here
  letterboxed a shot she is actually in, because she was holding something up
  and her head was above the source frame.
  **"No face" is not "nothing to crop to."** Letterboxing shrank a perfectly
  good subject to a third of the screen; cropping to what she was holding looked
  far better. Review every `pad` on screen, and when one is wrong, override it in
  the `.reframe.json` sidecar — that file exists to be edited: clear the `pad`
  entry and add `keys` across the span.
- Below ~60% detection means it mostly held a guess.

Per-clip `crop_x` (static), `crop_keys` (inline `[[t, x], ...]`) and `crop_pad`
override the sidecar.

**Do not swap the default on a hunch — measure.** `--mode compare` scores every
strategy on off-centre distance and window motion, writing nothing:

```powershell
python scripts/auto-reframe.py --manifest ... --mode compare
```

That is how `hybrid` was chosen: `pan` 27.9 px mean / 77 p95 / 10.5 px/s,
`shot` 32.0 / 102 / 4.0, `hybrid` 24.8 / 73 / 8.4 — hybrid beat both on every
clip. Note the off-centre metric is scored against detected faces, so it
structurally favours a face-following track; the near-edge and out-of-frame
columns are the ones describing real damage. `--mode pan` is the older behaviour
and is the automatic fallback when `scenedetect` is not installed.

### How the tracking actually works, and where it breaks

Deliberately the cheapest thing that worked, so know what you are trusting:

- **The subject is whichever face has the largest box** — no identity
  association across frames. It holds because a talking head dwarfs the people
  behind her. If a nearer background face ever measured larger, the window would
  jump to them, and nothing in the design prevents that.
- **Detection is Haar** (2001-era, frontal + profile) at 3 fps on 480 px
  greyscale. The quality comes from the smoothing, not the detector: median over
  1.2 s, then EMA, with jumps over 280 px snapping as scene cuts. A genuinely
  fast movement is therefore tracked late.
- **Misses hold the last position** rather than predicting, so a long faceless
  stretch parks the window wherever the last face was.
- **Only `x` is driven.** `y` sits at frame centre — headroom and eyeline are
  not controlled at all.

If better framing is asked for, the worked-out upgrade path, best value first —
all of these install cleanly on this machine's Python 3.13:

1. ~~`scenedetect` per-shot framing + blur-pad fallback~~ — **done**, this is
   `--mode hybrid`. Worth knowing what the measurement showed: per-shot framing
   *alone* was a regression (steadier, but it loses the subject), and scene
   detection alone did **not** fix the b-roll — the pad fallback did. Both
   halves were needed; the first half shipped alone would have looked like a
   failed idea.
2. **YuNet** (`cv2.FaceDetectorYN`, already in the installed cv2 — needs one
   ~350 KB ONNX from opencv_zoo) to replace Haar. Its 5 landmarks let you place
   the eyeline on the upper third, i.e. finally drive `y`. It would also cut the
   false `pad` decisions, which are purely detection misses.
3. **Kalman / constant-velocity filter** over detections, replacing hold-last.
4. Person detection (`ultralytics`) only if faces genuinely are not the subject.

`cv2.saliency` is NOT available: that lives in `opencv-contrib-python`, not
`opencv-python`.

Both presets need a vertical variant, because both are authored on a landscape
canvas:

- **Captions** scale by the HEIGHT ratio, so vertical enlarges text ×1.78 while
  the frame gets narrower. `red-card-vertical.json` cuts words-per-group so the
  cards don't turn into tall multi-line blocks.
- **The badge** scales by the WIDTH ratio, so a landscape preset comes out tiny.
  `handles/vertical.json` is authored on 1080x1920 with anchors that stay clear
  of the caption card (below y≈1450).

## Step 4 — verify before declaring done

The cutter already asserts output duration against the plan. Additionally:

1. `--list` first, and sanity-check the resolved times and lengths.
2. Pull 4–5 frames per clip across the badge's cycle and LOOK at them —
   position hops, colour alternation, captions intact, badge not overlapping
   the caption card:
   ```powershell
   ffmpeg -v error -ss 6 -i outputs/shorts/<clip>.mp4 -frames:v 1 -vf scale=760:-1 -y temp/chk.png
   ```
3. Check both ends of one clip for clipped words (frame at t=0.2 and t=dur-0.2).

## Traps (all hit for real)

- **`crop` has no `eval` option** — that is `scale`/`overlay`/`drawtext`. Its
  `x`/`y` are flagged runtime-tunable and already re-evaluated every frame,
  which is what makes the pan work. Passing `eval=frame` is a hard error.
- **Never pass a Windows path to the `ass` filter with backslashes.** libass
  reads `temp\05-x.ass` as an escape and silently looks for `temp05-x.ass`.
  Forward slashes everywhere.
- **`SELFCHECK: group N overlaps group N-1` is a real defect, not noise.** A
  group's per-word `min_active_ms` cascade ran past the next group's start, so
  the card would outlive its slot. It depends on where the group seam falls, so
  it appears and disappears as `grouping.max_words` changes — and `max_words`
  and `min_active_ms` interact. Tune them **as a pair and re-test every clip**
  (build the ASS alone, no encode, it takes seconds). Never edit the builder to
  silence it.
- **Haar cascades need `opencv-python<5`.** OpenCV 5 ships none, and its
  `FaceDetectorYN` wants a model downloaded from an external host.
- **An ffmpeg option before an `-i` binds to THAT input.** Adding badge PNG
  inputs turned a `-t` next to the source into the PNG's duration and the clip
  silently ran to the end of the source. `-ss` before the source input, `-t`
  after all inputs. The duration assert is what catches this class of bug.
- **`-b:v 0` is required with `-cq`** or NVENC ignores the quality target.
- **The environment is fixed; run scripts as plain `python scripts/<name>.py`.** A machine-wide `PYTHONPATH` used to point at another Python install and break `import faster_whisper` -- and a venv did not help, because `PYTHONPATH` is prepended inside one too. It has been removed, and every script now imports `scripts/_env.py` first, which re-execs into `.venv` with a clean environment and forces UTF-8 stdio on this cp1252 console. Run `python scripts/check-env.py` if an import ever breaks again.
- **Bare `yt-dlp` prints nothing under Git Bash** on this machine; always
  `.venv/Scripts/python.exe -m yt_dlp`.
- **Threads.com links can't be downloaded** — yt-dlp has no Threads extractor
  and the page is a logged-out JS shell with no og:video. Ask the user for the
  file or a DevTools-captured CDN URL.
- The badge animates on the **output** clock (t=0 at clip start), so every clip
  starts its cycle at the same place — that's intended, don't "fix" it.
- `scripts/transcript-outline.py` and `scripts/cut-clips.py` have hyphens in
  their names: import via `importlib.import_module("transcript-outline")`, and
  keep it that way for CLI ergonomics.

## Where to put the handle badge

Anchors live in `config/handles/<preset>.json` as centres on the output canvas.
Two constraints bound them: the caption card's top edge (near y=1412 on a
1080x1920 frame) caps how low the bottom pair can sit, and the badge's own
height caps how high the top pair can go. y=150 / y=1350 are the practical
extremes for a 357x111 badge.

Be honest about the limit: **in a tight close-up the face fills the whole frame
and no anchor clears it.** At the extremes the badge sits on hair rather than on
features, which is the best available rather than a fix. If that is not enough,
the real options are shrinking the badge or dropping the 4-position cycle for a
single fixed corner.

## Files

| Path | |
|---|---|
| `scripts/transcript-outline.py` | transcript → skimmable outline; `--find` a phrase's time |
| `scripts/cut-clips.py` | manifest → clips; crop, captions and badge in one encode |
| `scripts/handle-overlay.py` | badge rendering + ffmpeg animation graph |
| `scripts/auto-reframe.py` | per-shot framing decisions; `--mode compare` measures them |
| `config/clips/<id>.json` | one manifest per source video |
| `config/handles/default.json` / `vertical.json` | badge style + motion, per orientation |
| `config/presets/red-card-vertical.json` | caption preset for a 9:16 frame |
| `config/clips/egr4Y4oZgLM.json` | working example (5 episodes, handle, Ukrainian phrases) |
| `config/clips/egr4Y4oZgLM-vertical.json` | the same five, vertical + auto-reframed |

Requires `opencv-python<5` and `scenedetect` for auto-reframe (without
scenedetect it falls back to `--mode pan`); everything else is the captions
pipeline's existing dependency set.

## Dubbing one of these into another language

Use the **video-dub** skill. It reuses this manifest and this clip's
boundaries, then renders a `…-en.mp4` alongside the original:

```powershell
python scripts/dub-clips.py --manifest config/clips/<id>-vertical.json --only <clip-id>
python scripts/cut-clips.py --manifest config/clips/<id>-vertical.json --only <clip-id> --dub outputs/dub
```
