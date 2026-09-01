# Retro: books-giveaway stage 1 — six hours for a thirty-five-minute job

Stage 1 of the first Ukrainian video (ten silent screen recordings → one
eight-minute film with the sensitive fields blurred) took **5 h 40 min of
machine time** plus an hour of discovery. Its honest size is about 35 minutes
of compute. This is where the rest went, ranked by cost, with the rule that
now prevents each one. The tooling those rules became is in
`scripts/screencast-pipeline.py` and the scripts it drives; the skill is
`video-screen-cut`.

| # | cost | what happened | root cause | rule now |
|---|---|---|---|---|
| 1 | ~1.5 h | The full film was rendered five times with a redaction look the user had not seen: black boxes, pixelated whole panels, two sources dropped, then uploaded *private* | The AI decided the look; the user asked for **blur** and meant it | **Review gate.** `redaction-review.py` writes a before/after sheet of every redaction and nothing encodes until it is approved |
| 2 | ~1.5 h | Time-windowed rects → widened → row-merged → per-hit → blankets; four patch rounds before switching to tracking | Wrong primitive for scrolling content; the user diagnosed it ("we start from nothing each frame") | Tracked redaction (`track-blur.py`) is the default, not the escalation |
| 3 | ~1 h | The tracker was rendered with three times **without measuring its recall**; the final gate found 183 leaks | The house rule "measure a proposal before adopting it" was skipped — the OCR hits *are* a free ground truth | `track-blur.py --recall` runs in seconds and blocks the render below 98 % |
| 4 | ~1 h | Full OCR of 47 minutes of footage **three times** (~30 min each) because the rules changed after scanning | Only the *hits* were persisted, so a rule tweak forced a re-OCR | `scan-pii.py` caches raw OCR per frame once; `--from-cache` re-applies rules in seconds |
| 5 | ~1 h | Seven ffmpeg landmines found by launching full renders (see Gotchas: 87 KB graph, ten-input concat, pixelate cost, per-rect chains, boxblur chroma, fontconfig, `-progress`) | Each discovered at full-film scale after a 5–10 minute wait | `screen-cut.py --smoke` renders 30 s of the busiest source through the full graph before every full render |
| 6 | ~40 min | A sparse OCR gate read "clean"; a dense one later found the card number in a Notepad **window title**. Then four dense gates at 10–25 min each | Sampling used as a safety check; OCR as the only gate | `render-gate.py`: template NCC on the render (exact, minutes) + cheap OCR, and it maps hits back to source rects and patches the manifest itself |
| 7 | ~30 min | 4K decoded again and again; contact sheets timed out; OCR read the originals | Proxies came late (the user's idea) | Proxies are stage 1; everything after reads them. The claim that OCR needs the originals was wrong — it ran at 1600 px, below proxy width |
| 8 | ~25 min | Seven helpers lived in scratch; the manifest was edited by ~10 ad-hoc heredocs | Convenience over "leave tooling behind" | The manifest is written only by repo scripts |
| 9 | ~20 min | MTP walk timed out; looked in `DCIM/Camera` first (screen recordings live in `Movies/`); string-sorted dates; byte-identical duplicates in two folders | No import tool for this shape of session | `import-footage.py` |
| 10 | ~20 min | ~40 hand-typed commands, ten-minute foreground timeouts, buffered output hiding progress | No orchestrator | One checkpointed command |

Two things that were right and are kept exactly: the proxy step (12 GB →
332 MB at SSIM 0.9999) and the content-addressed piece cache (one changed
source re-renders in 46 s instead of 1142 s).

## What the rerun looks like

| stage | before | after |
|---|---|---|
| import, order, audio check | ~60 min | 3 min |
| proxies | 12 min | 5 min |
| activity + panel edge | 24 min | 2 min |
| OCR | 3 × 30 min | 12 min once, then seconds |
| tracking + recall | 3 × 8 min, unmeasured | 6 min + 30 s |
| review | skipped | 1 min, then STOP for approval |
| smoke + render | ~12 renders | 1 min + 4 min |
| gate + auto-patch | 4 × 20 min | 3 min, loops to clean |
| **total** | **~6 h** | **~35 min wall, ~5 min attended** |

## The one sentence to remember

A safety check that samples is not a safety check, and a tool whose recall
you have not measured has not been adopted — it has been hoped for.
