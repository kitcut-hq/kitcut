---
name: video-shorts
description: Extract shorts/episodes from a long video and stamp them with an animated Instagram-handle badge. Reads the word-level transcript to pick self-contained episodes, resolves cut boundaries by quoting what is said (not by timecodes), cuts frame-accurately with NVENC, and burns in a hopping flat/gradient @handle overlay in the same encode. Use when asked to make shorts, extract clips or episodes from a video, or to add a social-handle watermark to clips.
---

# Shorts out of a long video, with a handle badge

The whole workflow, once a manifest exists:

```powershell
cd C:\instafill\video-editing
python -X utf8 -E scripts/cut-clips.py --manifest config/clips/<id>.json --list   # plan only
python -X utf8 -E scripts/cut-clips.py --manifest config/clips/<id>.json          # cut
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
python -X utf8 -E scripts/transcript-outline.py transcripts/<id>.words.json --outline
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
python -X utf8 -E scripts/transcript-outline.py transcripts/<id>.words.json --find "exact phrase"
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
python -X utf8 -E scripts/handle-overlay.py --badges-only --handle "@name"      # preview PNGs
python -X utf8 -E scripts/handle-overlay.py --video in.mp4 --handle "@name"     # burn in
```

Architecture, if editing it: Pillow draws the badge once per colour variant into
a PNG (fonts, gradients, outlines are easy there); ffmpeg animates it with
`overlay` using `x`/`y`/`enable` expressions in `t`. One filter pass, no
per-frame Python. Don't try to move this into ASS — libass has no gradients.

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

- **An ffmpeg option before an `-i` binds to THAT input.** Adding badge PNG
  inputs turned a `-t` next to the source into the PNG's duration and the clip
  silently ran to the end of the source. `-ss` before the source input, `-t`
  after all inputs. The duration assert is what catches this class of bug.
- **`-b:v 0` is required with `-cq`** or NVENC ignores the quality target.
- **`python -X utf8 -E` always** — cp1252 console + stale global PYTHONPATH;
  same story as the captions pipeline.
- **Bare `yt-dlp` prints nothing under Git Bash** on this machine; always
  `python -m yt_dlp`.
- **Threads.com links can't be downloaded** — yt-dlp has no Threads extractor
  and the page is a logged-out JS shell with no og:video. Ask the user for the
  file or a DevTools-captured CDN URL.
- The badge animates on the **output** clock (t=0 at clip start), so every clip
  starts its cycle at the same place — that's intended, don't "fix" it.
- `scripts/transcript-outline.py` and `scripts/cut-clips.py` have hyphens in
  their names: import via `importlib.import_module("transcript-outline")`, and
  keep it that way for CLI ergonomics.

## Files

| Path | |
|---|---|
| `scripts/transcript-outline.py` | transcript → skimmable outline; `--find` a phrase's time |
| `scripts/cut-clips.py` | manifest → clips, handle applied in the same encode |
| `scripts/handle-overlay.py` | badge rendering + ffmpeg animation graph |
| `config/clips/<id>.json` | one manifest per source video |
| `config/handles/default.json` | badge style + motion |
| `config/clips/egr4Y4oZgLM.json` | working example (5 episodes, handle, Ukrainian phrases) |
