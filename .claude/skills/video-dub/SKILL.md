---
name: video-dub
description: Dub a clip or short into another language while keeping the original's cadence, so speech starts and stops when the speaker's mouth does. Segments the clip at real pauses, translates each slot under a time budget, speaks it with neural TTS at a computed speaking rate, retunes the lines that measurement shows do not fit, and renders the result with captions timed from the dub itself. Use when asked to translate a video, dub it into English or another language, add a foreign-language voiceover, lip-sync a translation, or make a localized version of a short.
---

# Dubbing a clip without losing its cadence

The failure mode to design against: translate the clip, read the translation
over the top, and it drifts within a few seconds and never recovers. What a
viewer actually notices is not phoneme-level mismatch — it is **cadence**. Sound
starting when the mouth opens, stopping when it closes, pausing where the
speaker pauses.

So the clip is cut into speech units at the pauses the speaker actually took,
and each unit is dubbed into its own slot on the original timeline.

## The workflow

```powershell
cd C:\instafill\video-editing

# 1. plan only -- check the segmentation before spending anything
python scripts/dub-clips.py --manifest config/clips/<id>-vertical.json `
    --only <clip-id> --plan-only

# 2. translate, speak, fit  -> outputs/dub/<name>.en.wav + .en.words.json
python scripts/dub-clips.py --manifest config/clips/<id>-vertical.json --only <clip-id>

# 3. render; captions come from the dub's own word timings
python scripts/cut-clips.py --manifest config/clips/<id>-vertical.json `
    --only <clip-id> --dub outputs/dub
```

No API key is needed: the voice is edge-tts and the default translation engine
shells out to the Claude Code CLI. Output is `…-en.mp4`; the original is never
overwritten.

## Step 1 — check the segmentation first

`--plan-only` is cheap and catches the thing most likely to be wrong. Look for
units in the 1.5–4s range. If you see one much longer, the transcript has a
stretch with no measurable pause, and the translation for that slot will drift
inside it.

Do **not** reach for punctuation to fix it. On a real transcript Whisper stopped
punctuating entirely near the end of the clip, and a punctuation-driven split
produced a single 25-second "unit". Gap-driven recursive splitting handled the
same stretch fine. Lower `--max-dur` instead.

## Step 2 — the translation is length-constrained, not just accurate

Each slot goes to the translator with the whole passage as context and a time
budget, plus a shorter `tight` fallback used when the natural line will not fit
without pushing the voice past where it sounds human.

**The trap, hit for real:** give a translator a word budget and it treats it as
a ceiling. The first run came in short on 14 of 26 lines, and the fitter drawled
the voice at its `-18%` floor trying to cover the gaps. Word the budget as a
target to *hit*, and say why — silence under a moving mouth reads worse than a
slightly long line.

When a line has to be exact, hand-write it:

```powershell
python scripts/dub-clips.py --manifest ... --only <clip-id> `
    --engine manual --translation my-lines.json     # [{"i":1,"text":"...","tight":"..."}]
```

## Step 3 — fitting, and why rate beats stretching

To make a line land in its slot, ask the **voice** to speak faster, don't
stretch the rendered audio. `rate` is a prosodic control: the voice re-times
phonemes the way a person would, where a resampler smears the formants. Measured
duration tracks `1/(1+rate)` closely enough to aim straight at a target and land
within a few tens of milliseconds. rubberband is the last resort and stays small.

A unit may also run into the pause that follows it — borrowing that silence is
free and saves speeding the voice up. That is the `hard` field in the plan.

## Step 4 — verify with the number, not by listening

`sync` in `outputs/dub/<name>.dub.json` is the share of the clip where dub and
original agree about whether anyone is talking. It drops when the dub speaks
over a pause and when it goes silent under a moving mouth.

Reference run — `01-silver-button`, 78s, 26 units:

| | first pass | after retune |
|---|---|---|
| sync | 85.8% | **94.4%** |
| slot error, mean | 0.42s | **0.17s** |
| slots overrunning their gap | 0 | 0 |
| slots at the slow-down floor | 14 | **2** |

Treat **sync above ~93%** and **mean slot error under ~0.2s** as good. If sync
is low, look at `fits[]` in the report: lots of `rate-18%` means the
translations are too short, lots of `tight`/`squeeze` means too long. Fix it in
the prompt or `--words-per-sec`, not by widening the rate clamps.

The render step separately proves caption sync on sampled frames (`sync probes:
24/24 correct`) and asserts output duration against the plan. Don't skip it.

## Traps

- **edge-tts defaults to `SentenceBoundary`.** Ask for `boundary="WordBoundary"`
  or you get audio and no word marks — and the captions are timed from those.
- **It pads ~0.36s of silence onto a line's tail.** Trim it *and* shift the word
  marks by the same amount, or every dubbed phrase starts late.
- **It intermittently returns no audio** for a line it rendered a moment
  earlier. One dropped request would abandon a 26-slot run, so `speak()` retries.
- **The dub transcript must use faster-whisper's envelope** (`{"file", "duration",
  "language", …, "words": [...]}`), not a bare list. The caption builder indexes
  `data["words"]` and dies on a list.
- **Append the dub input *after* the badge PNGs.** `handle-overlay` addresses
  those by absolute index (`[1:v]`, `[2:v]`, …), so an input inserted ahead of
  them silently repoints the badge at the wav.
- **`--copy` cannot carry a dub.** A keyframe-snapped cut starts the picture
  somewhere the dub was never aligned to; `cut-clips.py` refuses.

## Files

| | |
|---|---|
| `scripts/dub-clips.py` | orchestrator: segment → translate → fit → place |
| `scripts/dub-translate.py` | per-slot translation and the retune round |
| `scripts/dub-tts.py` | neural TTS, word boundaries, rate control |
| `outputs/dub/<name>.plan.json` | the segmentation, for inspection |
| `outputs/dub/<name>.translation.json` | editable; reused unless `--retranslate` |
| `outputs/dub/<name>.dub.json` | the fit report and `sync` score |
