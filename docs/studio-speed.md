# Where a studio film's time goes, and what would make it faster

Measured 2026-09-27/28 on the machine the studio runs on (i9-11900H laptop, 8 cores / 16
threads, RTX 3050 Ti 4 GB, 64 GB). Every number below comes from a run log, a film's
`events.jsonl`, or a test on a copy of a customer's film; estimates say so. Read this before
buying hardware for the studio or re-arguing any of the decisions it lists.

## The 8-minute film that took 2 h 21 min

`studio-20260927-171047-mgkibw` (the Dell/HP documentary, 480 s, 60 fps, Pro, $21.91):

| step | minutes | what is really happening |
|---|---|---|
| planning, script | 2 | Claude |
| **narration: 6 recordings of 70 lines** | **41** | Gemini reads the lines **one at a time** (~5 min a recording), then Whisper times the words on the CPU (~2.5-4 min); refusals forced re-recordings |
| timeline, cast, 938 lines of `film.js` | 31 | Claude |
| fixes, review stills | 5 | Claude, a little machine |
| **motion checks x2** | **13** | machine: ~960 full-size PNG stills a check |
| soundtrack: score + 4 renders | 8 | mostly machine (`master` alone is 66 s a render) |
| **final render** | **37** | machine: 28,800 frames at 13 fps |
| upload | 2 | network |

About 100 of the 141 minutes are machine and tool time; Claude writing is ~40. Across the last
dozen 10-30 s films the Claude phase runs at 64-84 output tokens a second -- generation speed --
so for a short film Claude is 85-90% of the wait and the machine is not the limit (`waited` in
`studio_runs.stages` is ~0 on almost every film).

## Why a faster PC alone changes little

- Claude's time does not run on this machine.
- The final render did not scale with browsers: per frame, ~3 ms of draw calls, ~50 ms of real
  drawing (deferred until the pixels are read), ~3 ms to copy them, ~28 ms to POST 8 MB to
  Python and ffmpeg; ffmpeg alone encodes ~170 frames/s. The 33 s Clamly film rendered in 87 s
  at 3 browsers and 91 s at 6. More cores would not have moved it.
- An estimate from published benchmarks, not a measurement: an i9-12900KF desktop would take a
  30 s film from ~13 to ~12 min and the 8-minute film from ~2 h 20 to ~1 h 50 on its own.

## The changes, and where each stands

| # | change | speeds up | this film, before -> after | status |
|---|---|---|---|---|
| 1 | record narration lines in parallel (`sketch-vo.py --jobs`) | narration | synth 341 s -> 52 s per recording (measured) | **on in the studio** (`studio/tools.py` `VOICE_JOBS` = 8), released 2026-09-28 |
| 2 | Whisper word timing on the GPU | narration | ~2.5-4 min -> ~20 s per recording (estimate) | not built; the studio reserves the laptop's 4 GB card for the renderer |
| 3 | backup voice for refused lines | narration | fewer re-recordings | shipped (b20966e), after this film |
| 4 | encode the video in the browser (`sketch-render.py --encode browser`) | final render | frames 2,218 s -> 536 s (measured, 4.1x) | **on in the studio** (`studio/tools.py` `RENDER_ENCODE`), released 2026-09-28 after the blind test below |
| 5 | 30 fps instead of 60 | final render | 15-38% on 30 s films (measured; fixed per-chunk costs) | shipped for Free by plan (2d13a0e); paid stays 60 |
| 6 | JPEG stills, motion check across 3 browsers | motion checks | PNG 123 ms -> JPEG 54 ms a still (measured); 13 -> ~3 min (estimate) | not built |
| 7 | soundtrack `master` stage | soundtrack | 66 s a render | not investigated |
| 8 | Claude fast mode | Claude writing | ~40 -> ~16 min (estimate), Claude cost x2 | not tried; a pricing decision |

With 1-7 the film is an estimated ~65 minutes; with 8 as well, ~45.

## 1. Narration in parallel: the test

A copy of the 8-minute film, all 70 lines recorded from nothing, Gemini 3.1 Flash TTS:

| | synth | trim | score (Whisper) | total | word accuracy (mean, lines < 0.9) | cost |
|---|---|---|---|---|---|---|
| one at a time | 341 s | 12 s | 239 s | 593 s | 0.932, 21 | $0.25 |
| eight at a time | 52 s | 4 s | 162 s | 218 s | 0.932, 21 | $0.26 |

No rate-limit answers at 8. The retry on 429/5xx exists for the day one comes.

## 4. Encoding in the browser: the test

Full numbers in `docs/reference.md` ("Encoding in the browser"). In short:

- **Speed:** 3.1-5.6x on a 33 s film depending on machine load; 4.1x on the 8-minute film.
- **Quality at the same `cq`:** at least as good on both films scored against the true frames
  (8-minute film: SSIM 0.959 vs 0.955, worst frame 0.956 vs 0.938).
- **Cost:** the master is bigger on a grainy film -- 3.8 GB instead of 2.2 GB for the 8-minute
  film (a fixed QP per frame; QP 20 closes half the gap but falls below today's quality). The
  33 s film came out the same size. Viewers get the 5 Mbps web copy either way.
- **Found on the way:** today's renders are BT.601 and untagged, and a browser assumes BT.709
  for untagged HD, so they probably play slightly dark in green (5.6 levels of 255). The
  browser path tags its output; the pipe path is unchanged.

### The blind test, 2026-09-28

Three customer films (Clamly 30 s, the hand-painted science film 30 s, the owl bedtime film
20 s), each rendered both ways twice, alternating which went first, then web copies made with
the studio's own settings, then 10 true frames a film scored as Edge shows them. The laptop had
other sessions running, so single timings swing ~2x; the ranges are what was seen.

| | render time | master size | web copy SSIM (what viewers stream) | master SSIM | colour error (green, of 255) |
|---|---|---|---|---|---|
| Clamly, today / browser | 64-113 s / 32-47 s | 108 / 110 MB | 0.957 / 0.958 | 0.967 / 0.960 | -5.7 / -1.5 |
| science, today / browser | 117-162 s / 34-66 s | 98 / 123 MB | 0.967 / 0.968 | 0.983 / 0.980 | -2.5 / -1.5 |
| owl, today / browser | 118-153 s / 52-58 s | 101 / 168 MB | 0.854 / 0.855 | 0.949 / 0.961 | -1.5 / -1.4 |

- The web copy, which is what every page plays, comes out the same sharpness either way.
- The master scores a hair lower on two films and higher on one. The differences (<0.01 SSIM)
  were not visible in 2x crops.
- **Colour is the visible difference.** Edge was screenshotted playing each file: its pixels
  match the file decoded as BT.709 for both (mean error 1.2 vs 2.1 decoded as BT.601), so
  today's untagged BT.601 renders really do play shifted. On Clamly the clam turns orange and
  the water bluer. The browser path matches the drawn frame. The pipe path could be fixed on
  its own (convert and tag BT.709) without switching encoders.
- The web copy of a pipe render stays untagged too; the browser path's web copy keeps its
  BT.709 tags.

## Stills

Per still, 120 of them, one browser: PNG 123 ms, JPEG 54 ms (the file 12x smaller, SSIM 0.975
against the PNG), WebP 214 ms, raw pixels 108 ms, a 192x108 copy 58 ms. About 45 ms of every
still is drawing, which no format removes. A 12-still review sheet also pays ~3 s of fixed
browser and Python start-up.

## A CPU-only machine: the Azure VM (2026-09-28)

The studio moved off the laptop to an Azure VM with no GPU (`studio/deploy/README.md` has the
full tables and the method). On the 8-minute film's frames, quality as VMAF against a lossless
render of the same frames:

- **The render:** the browser's *software* H.264 (OpenH264) in the page, 12 Mbps: 35 fps on
  D8ads_v5 (8 vCPU), 45.5 on F16s_v2 (16), VMAF 99.99 (99.1 on a painted film). The pipe on the
  same machines: 19-25 fps, VMAF 94.6-95.5, up to 3x the memory. The laptop's NVENC path: 54 fps.
  The software encoder refuses "quantizer", so it runs at a bitrate; 5 Mbps scored 91.6 on the
  painted film.
- **Everything else is faster than the laptop:** Whisper word timing for 8 minutes of narration
  46 s (laptop 2.5-4 min), the soundtrack master 35 s (66 s), a motion-check still 0.22 s (~0.4).
- **The new cost is the web copy,** libx264 on the CPU: ~2.7 min for 8 minutes at `veryfast`,
  which scored the same as `medium` (VMAF 99.99) in 40 % of the time.
- Found on the way: the pipe's colour is fixed on its own (converted to BT.709 and tagged); a
  lossless pipe render and the browser's software encode now score 99.99 against each other.

## Open decisions

1. ~~Switch the studio to parallel narration~~ -- done 2026-09-28, 8 at once.
2. ~~Switch the studio to encoding in the browser~~ -- done 2026-09-28: no visible difference but colour, which the browser path gets right; masters up to 1.7x bigger.
3. Build JPEG stills and the parallel motion check (#6)?
4. ~~Whisper on the GPU (#2) waits on the dedicated render machine~~ -- replaced, 2026-09-29:
   the takes are scored by a transcription service (below). The 46 s above was an 8-vCPU test
   machine; production on the 4-vCPU VM, beside other films, measured 180-265 s a recording.

## Scoring the narration off the machine (2026-09-29)

The bike film (`studio-20260929-103129-i4d52n`, 8 minutes, 78 lines) recorded its narration
7 times: **23 minutes, of which Gemini's voice was ~5 and Whisper's word timing ~18.** Gemini
was never rate-limited (78 lines in 10-89 s, 8 at once); the time was `score`, one take after
another through Whisper small.en on the VM's 4 vCPUs (~3.4 s a line).

Two fixes, both in `scripts/sketch-vo.py`:

- **A take's score is remembered** (`<take>.score.json`, keyed on the audio's bytes, the line,
  the hotwords, the language and the scorer). Four of the film's recordings re-scored all 78
  lines for 180-225 s when only a few had changed; now they score only those.
- **The studio scores on a service** (`SKETCH_SCORER`, set by `studio/procs.py` `SCORER`;
  `STUDIO_SCORER=local` puts Whisper back): **Whisper large-v3 on Groq, through OpenRouter.**
  A failed call scores that take locally, so the service being down costs time, not the film.

How it was chosen, with `scripts/vo-scorer-bench.py`. Agreeing with small.en proves nothing
about quality, so every candidate is held to a **referee**: Whisper large-v3, run locally on the
same takes. Two things decide quality. *Missed* counts takes the referee calls bad (accuracy
under 0.9) that the candidate passes, which means a garbled line ships. *|dt|* measures word
starts against the referee's, which is where the cues land. *Onset* is the first word minus
where the sound actually begins, the one timing the audio vouches for itself.

The bike film, English, 78 lines, referee large-v3 (20 bad takes):

| scorer | wall | missed | extra | \|dt\| median / p95 / >0.2 s | onset |
|---|---|---|---|---|---|
| small.en on the VM (what the film had) | 265 s | 1 | 5 | 0.10 / 0.36 / 17 % | -0.08 |
| **openai/whisper-large-v3 (Groq)** | **17 s** | **1** | **2** | 0.12 / 0.38 / 22 % | 0.00 |
| openai/whisper-large-v3-turbo (Groq) | 16 s | 2 | 4 | 0.08 / 0.28 / 10 % | -0.01 |
| microsoft/mai-transcribe-2 | 22 s | 3 | 4 | 0.26 / 0.50 / 72 % | +0.11 |
| x-ai/grok-stt-1.0 | 14 s | 3 | 3 | 0.21 / 0.44 / 57 % | +0.05 |
| openai/whisper-1 | 27 s | 3 | 2 | 0.20 / 0.48 / 52 % | -0.08 |
| google/gemini-3.5-transcribe | 33 s | 3 | 5 | 0.18 / 0.38 / 39 % | +0.04 |
| assemblyai/universal-3-5-pro | 14 s | 6 | 5 | 0.23 / 0.47 / 60 % | +0.05 |
| mistralai/voxtral-mini-transcribe | 19 s | 0 | 5 | 0.20 / 0.40 / 48 % | +0.04 |
| deepgram/nova-3 | 15 s | 17 | 3 | 0.20 / 0.39 / 52 % | -0.05 |

The freelancers film, Ukrainian, 30 lines, referee large-v3, which is also what the film was
made with (4 bad takes): whisper-large-v3 missed 0, extra 0, |dt| 0.08 s; turbo 0 / 1 / 0.08 s;
MAI-Transcribe 2 1 / 5 / 0.24 s.

**MAI-Transcribe 2 was live for a few hours first (34c96b9) and was the wrong pick.** Measured
against small.en it looked as good. Against the referee, its word starts run a quarter-second
late, and it passes more bad takes. Groq's large-v3 is the only service that matches the old
local setup on both counts, in about 1/15 of the time, at $0.003 an 8-minute film.

Not measurable here: meta/muse-voice-transcribe-1.0, openai/gpt-transcribe, google/chirp-3 and
voxtral-small give text but no word times (`verbose_json` refused). The kitcut OpenRouter account
allows only listed providers (settings/privacy); DeepInfra (Qwen3-ASR, Parakeet) is not on it.
OpenRouter drops a transcription prompt, so the films' hotwords no longer bias the scorer; only
Azure's MAI takes them, as a phrase list.

## What Claude's own time goes to, and the kit (2026-10-01)

`studio/harvest.py` over the 172 films of 2026-09-28..30 (234 Claude sessions), timing Claude by
*reply* -- from the answer it replies to until its last call: **27.1 h of Claude composing against
13.7 h of tools running.** Of Claude's time:

| reply | share |
|---|---|
| writing a film's picture the first time | 47% |
| fixing the picture after stills | 15% |
| reading (most of it deciding the next scene) | 12% |
| narration: the script and its retakes | 12% |
| music and sound effects | 7% |
| looking at stills, pictures, closing words | 8% |

Only ~10% of Claude's output tokens are code; the rest is working the design out -- a 30 s film's
first film.js is one reply of ~7 minutes, ~85% of it thought. Template remakes take a median 5.6
minutes of Claude against 13.7 for a 30 s film from scratch: a starting point more than halves it.
Seven agents read the code of 69 films and listed 1,476 hand-built components; what recurs across
unrelated films became `sketch/kit.js` (the reference, "The kit"). Its effect, measured by
`studio/bakeoff.py --set kit`, is below.

**Narration.** Two causes of retakes, both fixed:

- *The word budget.* The first message asked for 2.2 words a second; real narration takes 1.78 a
  second of film (lead, gaps and pauses in), 1.80 Ukrainian, 1.93 Spanish (first full takes of 71
  films). Claude writes to the budget (words / budget 1.00 at the median), so **53 of 71 first
  takes ran past the film's end** and were recorded again. `agent.WORDS_PER_S` is now 1.7: about
  57% of first takes fit as recorded, against 25%. A refusal before recording was tried on the same
  71 and rejected: the pace varies by ±20% (voice, direction, the take), so it would have refused 14
  of the 18 that fit.
- *The scorer.* Numbers heard as digits and names in another spelling scored as misreads: 33 of the
  78 lines under 0.9 among 646 takes. `sketch-vo.accuracy()` credits exactly those (above).

Each voice's measured pace is `studio/harvest.py --pace` (speech only: English 2.26 words a second,
Ukrainian 1.85; Vindemiatrix the slowest English voice at 1.85, Aoede and Kore the fastest at 2.42).

**Still open, measured and not built:** the music-too-loud loop (the sound step pulls the music
under the voice itself, then asks Claude to lower the score anyway: 10 of 19 narrated films, ~20
extra sound runs per 25 films -- whether the automatic duck is good enough is a listening decision);
a default camera breath on holds (`SK.breath` exists; the motion check's 4 s rule drew hand-written
drift in 10-14 of 30 films); scene passes that cannot share helpers (10 of the 8-minute bike film's
12 scene sessions pasted the same 1.7 KB renderer); a series pack (episodes re-read the last
episode's film.js in 8-10 films); stills over 12 times refused (3-5 films).
