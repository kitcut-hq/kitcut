---
name: video-sketch
description: Make an animated explainer film with no footage — a hand-drawn/whimsical or clean editorial animation written as JavaScript, with an AI voice-over, an original score on sampled instruments and synthesised sound effects, rendered to MP4 and to a self-contained HTML player. Use when asked for an animation, an animated explainer or promo, a motion-graphics video, a "whimsical hand-drawn" video, a product or feature explainer, a 30-60 second ad, or anything that should be illustrated rather than filmed.
---

# A sketch film: an explainer written as code

```powershell
# from the repo root, after copying config/sketch/example/ to projects/<id>/
python scripts/sketch-vo.py     --manifest projects/<id>/sketch.json --plan
python scripts/sketch-vo.py     --manifest projects/<id>/sketch.json
python scripts/sketch-render.py --manifest projects/<id>/sketch.json --stills 2,9,17,31 --sheet
python scripts/sketch-audio.py  --manifest projects/<id>/sketch.json --levels
python scripts/sketch-render.py --manifest projects/<id>/sketch.json
python scripts/sketch-render.py --manifest projects/<id>/sketch.json --timings
```

`docs/reference.md` has the reference under "Sketch films". The engine is `sketch/engine.js`,
the cast `sketch/props.js`, the page `sketch/player.html`. A finished example with both
looks' conventions: the committed `config/sketch/example/` (crayon), and a real brand film
built the same way (clean, 60 s, real estate) is described in the reference.

## The project folder comes first

`python scripts/project-scan.py --init <id>`, then copy `config/sketch/example/*` in and
edit. Read `projects/<id>/journal.md` before re-deciding anything; end with a note in it.

## Order of work

1. **Facts before words.** A promo makes claims. Find each claim's source (the product's own
   pages, its docs, its videos) and keep them in the manifest's `_sources`. Check the brand's
   own rules (a `PRODUCT.md`/`DESIGN.md` in its repo): named customers, certifications and
   benchmarks are the usual things a brand forbids unless approved. Leave out anything you
   cannot source; say so in the report.
2. **Brand before design.** Use the brand's real logo file (`"images": {"logo": ...}` →
   `SK.image('logo', ...)`), its colours and its typefaces (woff2 in `fonts/`). Pick the look
   for the audience: `crayon` is whimsical; `clean` is editorial (agents, finance, B2B).
3. **Script.** About 2.6 words a second: 60 s is ~130 words, 40 s ~90. One idea per line.
   `sketch-vo.py --plan` prints the layout and the credit cost; nothing is spent.
4. **Voice.** `sketch-vo.py`. Read the take table it prints: accuracy under ~0.8 is usually
   numbers ("45" vs "forty-five"), not a bad take; `HARD-CUT` means no silence was found before
   the tail word — pick another take with `"pick"` on the line. Put brand names in `hotwords`.
5. **Picture.** Write `film.js` scene by scene, every cue on a word: `SK.w(line, "word")`.
   Lay scenes out in world space and move the camera between them (`SK.camera` keys with
   easing); keep each scene's content inside ±900 x ±500 of its centre at zoom 1.
6. **Review with stills, not guesses.** `--stills` at the moments that matter (each cue, each
   transition midpoint) with `--sheet`, then look at the sheet. Fix, re-still, repeat. A round
   of 18 stills costs ~9 s. Check text overlaps, off-frame content, elements hidden behind
   later-drawn ones (draw order is paint order), and emotional reads (a "sad" brow drawn the
   wrong way reads as angry).
7. **Sound.** Write `score.json` (tempo chosen so bar lines land on the story beats — compute
   `bar = 240 / bpm` and line the scene changes up) and `sfx.json` (a cue on every visual hit).
   `sketch-audio.py --levels`: the voice should sit 6-12 dB over the ducked music.
8. **Render**, then check the MP4 itself: duration, loudness (-14 LUFS), a few decoded frames.
9. **Publish** with `yt-upload.py --channel <handle>` — unlisted unless told otherwise.
10. **Report the timings** (`--timings`) with the deliverables.

## Traps already paid for

- `-shortest` with a subtitle track shortens the film to the last caption. `sketch-render.py`
  muxes with `-t`; do the same in any hand-run mux.
- `eleven_v3` clips final syllables: always go through `sketch-vo.py` (tail word + cut).
- The props draw at a fixed design size and scale uniformly (`P.house` at `w` = 104 is a
  thumbnail of the same house); if a new prop has hard-coded sizes inside, give it the same
  scale treatment before using it small.
- Every frame must be a pure function of `t`; any state kept between frames breaks the
  exported video while looking fine in the browser.
