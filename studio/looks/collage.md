## INTRO
The look is **collage**: an image model paints single objects and figures, each one alone and
cut out of its background, and you build the film around them in code -- pages of paper,
printed words, labels, stamps and marks -- every piece entering and moving on the spoken words.

## FILES
- `paint.json` -- the cut-outs (already there, with no images yet; see "The cut-outs").

## COMMANDS
- `paint` -- paints every image in `paint.json` at once (about a minute for twenty; unchanged
  ones come from cache) and tiles them into `images/sheet.jpg`, each on a mid blue so its edge
  shows. `retake: ["<name>"]` repaints some. `max_images` in paint.json is the cap, repaints
  included.

## DIRECTION
- the pictures: what each is made as (the medium) and what it shows;
- the pages: their papers and colours, what each page holds, and how one gives way to the next;
- the words: which typeface does which job, and the colours of words, labels, stamps and marks;

## STEPS
1. Decide the idea and the direction (above): one clear point, told in the film's length, as a
   run of pages -- one for each beat of the narration, most of them 4-8 s on screen.
2. Write the narration in `vo.json` and call `voice`. It returns each line's start and end, and
   every word's time on the film clock. If a line runs past the end of the film or `acc` is
   below 0.9, shorten or rephrase it and record again (a number read as words and written as
   digits scores low without being wrong).
3. Write `paint.json` (see "The cut-outs") and call `paint`. Read `images/sheet.jpg`. Repaint an
   image that is wrong -- lettering in it, the wrong subject, a background or paper shape left
   behind it, the border biting into the subject -- at most twice in all.
4. Write `film.js`: the pages and what is on them, each piece entering on the word that names it
   ({CUE_SHORT}).{KIT_STEP} Then call `check`.
5. Call `stills` with about six times spread over the film -- ten or twelve for a film over a
   minute -- (always 0, one just after each page arrives, and one just before the end), and Read
   `outputs/review/sheet.png`; then call `motion` once and Read `outputs/review/motion.png`. Look
   first at the sheet as a whole, against film.js's `// For:` line (see "Direction"): would that
   audience take this film seriously, and does it look professionally made for them? If not, fix
   that before anything else. Then look hard at the details: a page that stays bare for long
   after it arrives, a piece covering words or another piece's point, text too small or hard to
   read, a piece cut off by the frame, a reveal the next page covers before it has been seen;
   and from `motion`, any stretch where nothing moves. Fix and re-check. Two review rounds at
   most.
6. Write `score.json` and `sfx.json`, then call `sound` once to prove they render. The music
   ducks under the voice by itself.
7. Finish with one or two sentences: what the film shows and says, and anything from the prompt
   you could not do.

## RULES
# The cut-outs (`paint.json`)

The studio has set `backend`, `model`, `max_images` and `cutouts`; leave them. You set:

- `style`: one line put in front of every prompt, or `""` when each prompt carries its own.
- `images`: `[{"name": "press", "prompt": "...", "cutout": true, "aspect": "1:1"}, ...]` --
  names of lowercase letters, digits, `-` and `_`.
  - A cut-out (`"cutout": true`) is one object or figure, whole, painted alone on a transparent
    background, trimmed to it, with a white paper border cut round it in straight snips.
    `{"border": 0}` leaves it bare; `{"cut": "round"}` follows its outline instead; `border` is
    in pixels at 1024 on the long side (12 by default).
  - `aspect` is the shape of the canvas it is painted on: `"2:3"` for a tall thing, `"3:2"` for
    a wide one, `"1:1"` otherwise.
  - Describe each fully: what it is made as (an engraving, a photograph, a woodcut, a gouache, a
    clay model...), the object and its details, the angle. Never ask for words, letters or signs
    in a picture: words go on screen in code, where they are sharp and can move.
  - It comes back as `images/<name>.webp`, up to 1024 px on its long side. An image without
    `cutout` is a whole scene (1920x1280), drawn with `SK.image`.
  - The painter works from the words alone; `ref` changes nothing.

# Pages and pieces (`engine/collage.js`)

- Call `SK.setStyle('collage')` first. Under it every piece shakes by a pixel or so twelve
  times a second (ten in a film rendered at 30 fps), entrances move on the same clock, and the
  grain changes about as often: paper animated under a camera. `SK.setGround(...)` names the
  table under the pages.
- The pieces, each centred on its x, y (the source is below): `SK.sheet` (a page: `col`,
  `edges` -- which sides are torn, `''` for a cut sheet), `SK.cutout(name, x, y, w)`,
  `SK.tape` (words on a strip; returns its size), `SK.headline` (display type; `distress` inks
  it unevenly), `SK.stamp` (a ring or box of words printed in ink, `t` its hit), `SK.burst` and
  `SK.disc` (a starburst, a paper circle), `SK.halftone` (printed dots), `SK.ransom` (letters
  cut from different pages), `SK.mark` and `SK.arrow` (a marker line drawn on),
  `SK.maskingTape`, `SK.newsprint` (a page of small newspaper type behind everything),
  `SK.rules`, and `SK.txt` from the engine (per-letter write-on, `mode: 'type'` for typing).
- Every piece takes `in` and `out`: `{t, type, d, from}`, type one of `pop`, `grow`, `drop`,
  `slap`, `thump`, `slide`, `wipe`, `rise`, `fade`, `none`; before `in.t` it is not drawn.
- A page and what is on it move together: draw them inside `SK.layer({in: {t, type: 'slide',
  from: 'l'}, steps: 0}, () => {...})` (`steps: 0`: a sliding page moves smoothly, not on the
  12-a-second clock). Draw older pages first; stop drawing one once the next covers it.
- A card with words on it is its own `SK.layer({x, y, nudge: 1, ...})` with `nudge: 0` on the
  words, so they stay on the paper as it shakes.
- One film, not a slideshow: pages follow on from each other -- carry something across every
  change (a strip that stays on screen, a picture that travels to the next page, a match on a
  shape or a colour), and keep something moving on every page while it is up. A page that
  arrives bare and waits for its words reads as a gap: let its title and main picture arrive
  with it, and land the details on the words that name them. Start a page a little before its
  line; a reveal on a line's last word is covered by the next page unless that page waits.
- Typefaces in this film, besides the engine's (Caveat, Patrick Hand, Balsamiq Sans):
  `'Abril Fatface'`, `'UnifrakturMaguntia'`, `'Oswald'` (200-700), `'Old Standard TT'` (400, 700,
  italic), `'Playfair Display'` (400-900, italic), `'Courier Prime'` (400, 700), `'Anton'`,
  `'IBM Plex Mono'` (400, 700). Oswald, Old Standard TT, Playfair Display and IBM Plex Mono (and
  Caveat, Balsamiq Sans) carry Cyrillic. The pieces set a line with Cyrillic letters in a face
  that has them (`SK.face`): Abril Fatface as Playfair Display 900, Anton as Oswald 700,
  UnifrakturMaguntia as Old Standard TT 700, Courier Prime as IBM Plex Mono. `SK.txt` and your
  own canvas text do not: give them a face that carries the letters.
- Words take any colour; check that each reads on what it sits on.

# Reference: the collage pieces (`engine/collage.js`)

```js
{COLLAGE}
```

# Reference: an example collage film (technique, not a look to reuse)

"A Brief History of Paperwork" (66 s): pages that slide over one another, cut-outs, labels,
stamps and a timeline, every piece on a word (some of its ten pages are left out of this copy).
Its papers, faces and palette were chosen for its subject; choose this film's own.

```js
{EXAMPLE_COLLAGE}
```
