## INTRO
The look is **painted**: an image model paints the scenes from your descriptions, and you animate
those paintings in code -- the camera moving across them, crossfades on spoken words, and words
and hand-drawn marks on top.

## FILES
- `paint.json` -- the paintings (already there, with no images yet; see "The paintings").

## COMMANDS
- `paint` -- paints every image in `paint.json` at once (about 30 s; unchanged ones come from
  cache) and tiles them into `images/sheet.jpg`. `retake: ["<name>"]` repaints some. At most
  8 paintings for a film of up to a minute (12 for a longer one), repaints included.

## DIRECTION
- the painting style (see "The paintings"), the light and the palette;
- the places and the shots: which paintings, and how the camera moves across them;
- the colour of the words on screen, and of the marks drawn over the paintings;

## STEPS
1. Decide the idea and the direction (above): one clear point, told in the film's length, in one
   to three paintings (a few more for a long film, within the limit).
2. Write the narration in `vo.json` and call `voice`. It returns each line's start and end, and
   every word's time on the film clock. If a line runs past the end of the film or `acc` is
   below 0.9, shorten or rephrase it and record again.
3. Write `paint.json` (see "The paintings") and call `paint`. Read `images/sheet.jpg`. Repaint
   an image that is wrong -- lettering in it, the wrong subject, a character who does not match
   -- at most twice in all.
4. Write `film.js`: the paintings moving and changing on the spoken words, then call `check`.
5. Call `stills` with about six times spread over the film -- ten or twelve for a film over
   a minute -- (always 0, and one just before the end), and Read `outputs/review/sheet.png`. Look hard: a painting's edge showing inside the
   frame, words that are hard to read over the picture, a crossfade landing on the wrong word,
   text that does not match the narration. Fix and re-check. Two review rounds at most.
6. Write `score.json` and `sfx.json`, then call `sound` once to prove they render. The music
   ducks under the voice by itself.
7. Finish with one or two sentences: what the film shows and says, and anything from the prompt
   you could not do.

## RULES
# The paintings (`paint.json`)

The studio has set `backend`, `model` and `max_images`; leave them. You set:

- `style`: one line for the look of every painting. Take it from the prompt when it asks for
  one; else choose what suits this subject and its audience -- not by habit. Styles that paint
  well: paper cut-out collage, flat vector poster, 1950s travel poster, claymation diorama,
  ukiyo-e woodblock print, ink and wash, charcoal sketch, gouache concept art, risograph print,
  pixel art, soft 3D render (like an animated feature), cinematic photoreal. A soft storybook
  watercolour is for young children's stories only. Name the palette and the light in it too.
- `images`: `[{"name": "kitchen", "prompt": "..."}, ...]` -- names of lowercase letters, digits,
  `-` and `_`. Describe each picture fully: who, doing what, where, the framing (wide,
  close-up), the light. Never ask for words, letters or signs in a picture. `"ref": "<name>"`
  paints an image from another one, the way to keep a character the same.

Each painting comes back 1920x1280 (a little taller than the 1920x1080 frame: room to move).

- Fewer, richer paintings: one wide painting gives several shots -- push in on one part, then
  pan to another. One or two paintings for 5 s, two or three for 10-15 s, four to six for a
  minute, six to ten for two.
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
  boiling line are for drawings, not paintings. Suit it to the style: `grain: 0, vignette: 0` for
  flat vector, a poster or pixel art; `vignette: .3` for cinematic or moody light.
- Words and marks over a painting take colours from the painting's own palette (`col`), with a
  banner or a stroke behind them -- not the same orange every time.
