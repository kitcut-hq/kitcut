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

## Open decisions

1. ~~Switch the studio to parallel narration~~ -- done 2026-09-28, 8 at once.
2. ~~Switch the studio to encoding in the browser~~ -- done 2026-09-28: no visible difference but colour, which the browser path gets right; masters up to 1.7x bigger.
3. Build JPEG stills and the parallel motion check (#6)?
4. Whisper on the GPU (#2) waits on the dedicated render machine.
