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

## The project folder comes first

Every video lives in `projects/<id>/` — its manifests, its content dirs, and
two committed metadata files. Before doing anything, read
`projects/<id>/project.json` (create the folder with
`python scripts/project-scan.py --init <id>` if this is a new video) and skim
`projects/<id>/journal.md` if the ask touches past decisions. When the work
lands: the finishing scripts record renders and uploads into the project file
themselves; if you ran ffmpeg by hand or a script printed
"PROJECT FILE NOT UPDATED", record the deliverable and journal line yourself.
End an editing session by appending a short prose note to `journal.md`
addressed to the next session: what was asked, which knob changed, why, and
anything it should not have to rediscover. Details: `## Projects` in the
`docs/reference.md`; the re-edit entry point is the `video-project` skill.

## The workflow

```powershell
# from the repo root

# 1. plan only -- check the segmentation before spending anything
python scripts/dub-clips.py --manifest projects/<id>/clips-vertical.json `
    --only <clip-id> --plan-only

# 2. translate, speak, fit  -> projects/<id>/outputs/dub/<name>.en.wav + .en.words.json
python scripts/dub-clips.py --manifest projects/<id>/clips-vertical.json `
    --only <clip-id> --outdir projects/<id>/outputs/dub

# 3. render; captions come from the dub's own word timings
python scripts/cut-clips.py --manifest projects/<id>/clips-vertical.json `
    --only <clip-id> --dub projects/<id>/outputs/dub
```

Out of the box no API key is needed: the voice is edge-tts and the default
translation engine shells out to the Claude Code CLI. Output is `…-en.mp4`; the
original is never overwritten.

## Choosing a voice

```powershell
# free, no key, wide speed range
python scripts/dub-clips.py --manifest ... --only <id> --tts edge --voice ava `
    --outdir projects/<id>/outputs/dub

# better voice, needs ELEVENLABS_API_KEY in .env, costs characters
python scripts/dub-clips.py --manifest ... --only <id> `
    --tts elevenlabs --voice jessica --tag en-el --outdir projects/<id>/outputs/dub
python scripts/cut-clips.py --manifest ... --only <id> `
    --dub projects/<id>/outputs/dub --dub-tag en-el
```

`--tag` is what lets two versions coexist: it names every artifact for that run
(`.en-el.wav`, `.en-el.words.json`, `.en-el.dub.json`) and suffixes the rendered
mp4. It now defaults per backend (`en` for edge, `en-el` for ElevenLabs), and
aiming one backend at a tag that already holds another's dub is refused rather
than silently skipped or overwritten.

Measured head to head on `01-silver-button`, both through the identical
pipeline:

| | edge / Ava | 11labs / Jessica |
|---|---|---|
| sync | **95.0%** | 93.9% |
| slot error, mean | **0.15s** | 0.18s |
| needed the shorter rewrite | 9 / 26 | **4 / 26** |
| needed rubberband | 5 / 26 | **1 / 26** |
| sitting on a rate clamp | 5 | 14 |

They tie on timing, so **pick on how the voice sounds, not on these numbers**.
Two honest caveats: each run translates fresh, so some of the middle rows are
translation luck rather than the engine; and the last row is the one cleanly
attributable to the backend -- ElevenLabs is pinned against its speed limit
more than half the time, it just still fits.

Voice ids live in `config/elevenlabs-voices.json` — the single source, read at
runtime by `resolve_voice()`. An unknown name, or one marked `verified: false`,
is refused **before** anything is rendered or paid for. The model comes from the
same file (`--el-model` overrides it). A TTS-scoped key cannot list voices at
runtime (`GET /v1/voices` 401s with `missing_permissions`), which is why the
file is maintained by hand; `dub-tts.py --tts elevenlabs --list-voices` prints
it with the verified flags.

Before a first run, `python scripts/check-env.py` reports whether the `claude`
CLI (the default translation engine) is on PATH and whether
`ELEVENLABS_API_KEY` resolved from `.env`.

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

`sync` in `projects/<id>/outputs/dub/<name>.<tag>.dub.json` is the share of the clip where
dub and original agree about whether anyone is talking. It drops when the dub speaks
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

## A WRITTEN voice-over, not a translation — `--script`

If the task is "replace the sound" rather than "translate it", do not reach for
the translation path. `build_plan` lays the new lines on the *original
speaker's* pauses, which is right for a dub and wrong here: the old rhythm is
usually the thing being fixed.

```json
[ {"t": 0.4, "text": "Flattening turns a fillable PDF into a plain one."},
  {"t": 6.0, "text": "Ninety-seven form fields, merged into the page in seconds.",
              "tight": "Ninety-seven form fields, merged in seconds."} ]
```

```powershell
python scripts/dub-clips.py --manifest projects/<id>/clips-vertical.json --only <clip-id> `
    --script projects/<id>/vo/<clip-id>.json --tts elevenlabs --voice brian `
    --tag vo --outdir projects/<id>/outputs/dub --plan-only
```

`t` is seconds from the clip's start; a line runs until the next begins, or to
the clip's end. `--script` implies `--engine manual` and covers one clip.

**Write the lines to the picture, and get the picture first.** Sample the
RENDERED clip every one or two seconds, identify each beat, and put a line on
each. Do not write against the transcript — the whole reason the sound is being
replaced is that the old narration is not what you want said.

**The gate is different from a dub's, and using the dub's gate will mislead
you.** `sync` measures agreement with the original speech, which a voice-over
deliberately discards; it read 79% on a take where every line was right. Accept
when:

1. **every slot reports `natural`** — no `rate±%`, no `tight` fallback, nothing
   squeezed. A rate change means the line does not fit and will sound rushed;
   ElevenLabs caps at +20% and it is audible.
2. **nothing overruns the clip** — `place()` warns loudly if it does.
3. **the spoken words are the written words.** Transcribe the generated wav with
   `transcribe-words.py` and diff it against the script. A TTS engine can garble
   a numeral or an abbreviation and no fit number will notice. (Expect Whisper to
   write "97" where you wrote "Ninety-seven" — that is a match, not a fault.)

**Two things about timing that cost a pass each:**

- **A neural voice reads faster than a words-per-second estimate.** The first
  pass came in short on all seven slots — about 4 words/second for Brian against
  the 3.2 the planner assumes. That is fine, not a failure: script slots are
  marked `free`, so `fit_unit` leaves the slack as a pause instead of drawling
  the line out the way it would under a moving mouth.
- **The tail has no slack, and re-timing just moves the squeeze along.** Three
  lines over the last 7.4 s needed 7.3 s of speech, so every nudge pushed the
  problem to a neighbour. Shorten a line rather than re-timing a fourth time.

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
- **ElevenLabs' character alignment returns overlapping words** -- 9 pairs in a
  228-word clip, where edge returned none. The caption builder refuses to write
  an ASS with overlapping groups, so a dub built on those timings fails at the
  self-check. `dub-tts.monotonic()` nudges each start forward. Do not relax the
  check instead.
- **Sanitise last, not first.** That same fix was initially applied *before* the
  silence trim, and the trim then shifted every mark and clamped at zero --
  collapsing every word that began inside the trimmed lead onto 0.0 and
  recreating the exact overlaps it had just removed. A guarantee established
  early is not a guarantee if a later transform can violate it.
- **ElevenLabs rejects `speed` outside 0.7-1.2** outright, rather than clamping.
  `rate_limits()` reports that as -30%/+20% so the fitter never asks for more.
- **Give every backend its own `--tag`.** `plan.json` and `dub.json` used not to
  be tag-scoped, so a second voice silently overwrote the first one's report and
  the comparison was lost.
- **A media player holding the previous render open** makes the final rename
  fail with EACCES and throws away a finished encode. `cut-clips.py` waits the
  lock out, and if it never clears the clip is reported at the end with its
  `.part.mp4` intact instead of killing the rest of the batch.
- **A cached translation belongs to one plan.** Slots are matched by bare
  index, so a plan rebuilt with a different `--max-dur` would speak the right
  lines into the wrong holes. `translation.json` carries a fingerprint of the
  unit texts and knobs; a mismatch refuses and asks for `--retranslate`.
- **`--engine manual` never calls a model.** It used to fall through a two-way
  ternary into the OpenAI path — burning credits under a flag that promised no
  network, or failing with "OPENAI_API_KEY is not set" while you had asked for
  manual. The retune round now skips instead, and leaves your `--translation`
  file untouched.
- **A retune can make a slot worse.** Rewrites are re-measured and reverted if
  the new take fits worse than the old one; a model that returns the whole
  array instead of the requested slots has the extras discarded, so
  well-fitting lines are not re-rendered for nothing.
- **ElevenLabs glues punctuation to words**, edge does not, so the two backends
  tokenise the same script differently in `.words.json`. Captions render both
  fine; it only matters if you diff them.
- **Failures that a retry cannot fix are not retried.** A missing key, a bad
  voice or an exhausted quota aborts immediately with the service's own
  message; only 429 and genuine socket blips back off and try again.

## Files

| | |
|---|---|
| `scripts/dub-clips.py` | orchestrator: segment → translate → fit → place |
| `scripts/dub-translate.py` | per-slot translation and the retune round |
| `scripts/dub-tts.py` | neural TTS, word boundaries, rate control |
| `scripts/check-dub.py` | self-test for all of the above; free, run it after edits |
| `config/elevenlabs-voices.json` | voice ids and model; refuses unverified ids |
| `projects/<id>/outputs/dub/<name>.<tag>.plan.json` | the segmentation, for inspection |
| `projects/<id>/outputs/dub/<name>.<tag>.translation.json` | editable; reused unless `--retranslate` |
| `projects/<id>/outputs/dub/<name>.<tag>.dub.json` | the fit report and `sync` score |

Every artifact is tag-scoped. The skill's older, untagged names are gone; if
you see one in a doc, it is stale.

## Deferred — measure before adopting

Reviewed and deliberately not built, because each changes output and the house
rule is to score a proposal on real footage first (baseline: `01-silver-button`,
edge/Ava, sync 95.0%, mean slot error 0.15s):

- segmentation: `len(u) < 4` blocks splitting a long slow unit; slivers fold
  backwards only, so an opening sliver is stranded
- the retune word budget is a fixed 3.2 w/s, not the voice's measured rate —
  ElevenLabs needs a deeper cut than edge to shed the same time
- later translation batches cannot see earlier batches' English, so terminology
  can drift at the 20-slot boundary
- a word straddling the clip boundary is dropped from the translator's context
- the caption grouping pair (`max_words` / `min_active_ms`) was tuned on
  Ukrainian and is reused unchanged for English
