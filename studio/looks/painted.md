## INTRO
The look is **painted**: an image model paints the scenes from your descriptions, and you animate
those paintings in code -- the camera moving across them, crossfades on spoken words, and words
and hand-drawn marks on top.

## FILES
- `{JOB}/paint.json` -- the paintings (already there, with no images yet; see "The paintings").

## COMMANDS
- `{PY} scripts/sketch-paint.py --manifest {JOB}/sketch.json` -- paints every image in
  `paint.json` at once (about 30 s; unchanged ones come from cache) and tiles them into
  `{JOB}/images/sheet.jpg`. `--only <name> --retake` repaints one. At most {MAX_IMAGES} paintings
  for the whole film, repaints included -- `--plan` shows what a run would paint.

## STEPS
1. Decide the idea and the shots: one clear point, told in {SECONDS} seconds, in one to three
   paintings.
2. Write the narration in `vo.json` and run `sketch-vo.py`. Read `{JOB}/audio/vo/timeline.json`:
   each line's start and end, and every word's time on the film clock. If a line runs past
   {SECONDS} s or `acc` is below 0.9, shorten or rephrase it and run again.
3. Write `paint.json` (see "The paintings") and run `sketch-paint.py`. Read
   `{JOB}/images/sheet.jpg`. Repaint an image that is wrong -- lettering in it, the wrong subject, a
   character who does not match -- at most twice in all.
4. Write `film.js`: the paintings moving and changing on the spoken words, then `node --check` it.
5. Render about six stills spread over the film (always 0, and one just before the end) with
   `--sheet`, and Read the sheet. Look hard: a painting's edge showing inside the frame, words
   that are hard to read over the picture, a crossfade landing on the wrong word, text that does
   not match the narration. Fix and re-check. Two review rounds at most.
6. Write `score.json` and `sfx.json`, then run `sketch-audio.py` once to prove they render. The
   music ducks under the voice by itself.
7. Finish with one or two sentences: what the film shows and says, and anything from the prompt
   you could not do.

## RULES
# The paintings (`paint.json`)

The studio has set `backend`, `model` and `max_images`; leave them. You set:

- `style`: one line for the look of every painting, taken from the prompt when it asks for one
  (watercolour, anime, claymation, paper collage, 1950s poster, flat vector, photoreal...), else
  whatever suits the subject and the audience.
- `images`: `[{"name": "kitchen", "prompt": "..."}, ...]` -- names of letters, digits and `-`.
  Describe each picture fully: who, doing what, where, the framing (wide, close-up), the light.
  Never ask for words, letters or signs in a picture.

Each painting comes back 1920x1280 (a little taller than the 1920x1080 frame: room to move).

- Fewer, richer paintings: one wide painting gives several shots -- push in on one part, then
  pan to another. One or two paintings for 5 s, two or three for 10-15 s.
- The same character in two paintings will not look quite the same. Describe them identically
  every time (age, hair, clothes and their colours), or keep them in one painting and frame
  different parts of it.
- Draw a painting with `SK.image(name, x, y, w)` (centred on x, y; its height follows) under a
  camera: `SK.camera([[0, [x, y, zoom]], [t, [x, y, zoom], E.sine], ...])`. It must cover the
  frame at every moment -- a paper-coloured strip at an edge of a still means it does not. At zoom
  1 the frame is 1920x1080 around the camera centre; drawn 2000 wide, a painting is 1333 tall.
- Move slowly: a push-in of about 10% over a shot, or a pan of a few hundred units. Crossfade to
  the next painting over 0.4-0.8 s (`alpha` on `SK.image`), starting on a spoken word.
- Words on screen: `SK.txt` on a banner (`SK.card` behind it) or with a thick `stroke`, so they
  read over a busy picture. Hand-drawn marks on top are welcome -- an arrow, a circle, sparkles,
  hearts (`SK.ink`, `S.*`, `SK.sparkle`, `SK.heart`): a painting with pen notes is a good look.
- `SK.setStyle('clean', { grain: .25, vignette: .15, handheld: .3 })`: the crayon paper and the
  boiling line are for drawings, not paintings.
