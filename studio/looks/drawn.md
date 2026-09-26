## INTRO
The look is **hand-drawn**: everything is drawn in code with the engine's pen and the cast of
props below -- the crayon look (`SK.setStyle('crayon')`), or `SK.setStyle('clean')` for crisp
editorial line art -- on a ground you choose, in a place you build.

## FILES

## COMMANDS

## DIRECTION
- the place and the time of day: where this happens, and what fills the frame there;
- the ground (below) and the style, crayon or clean;
- who is in it: the film's own characters, drawn for it, or the cast's when they fit;

## STEPS
1. Decide the idea and the direction (above): one clear point, told in the film's length -- a
   setup, one action and a payoff you can hold for the last second or so. A longer film strings
   a few such beats together -- two to four for 30-60 s, four to eight for 90-120 s -- in places
   or moments that still build towards one point.
2. Write the narration in `vo.json` and call `voice`. It returns each line's start and end and
   every word's time on the film clock. If a line runs past the end of the film or `acc` is
   below 0.9, shorten or rephrase it and record again.
3. Write `film.js`: the ground at the top, the backdrops first in `draw`, then the film, cueing
   the picture to the words (`SK.w(line, 'word', fallbackSeconds)`). Call `check`.
4. Call `stills` with about six times spread over the film -- ten or twelve for a film over
   a minute -- (always 0, and one just before the end), and Read `outputs/review/sheet.png`. Look
   hard: blank or near-empty frame 0, bare paper where a place should be, the edge of a backdrop,
   things cut off by the frame edge, overlaps, text collisions, text or lines that do not read on
   the ground, elements hidden behind later-drawn ones, faces that read wrong, text that does not
   match the narration. Fix and re-check. Two review rounds at most.
5. Write `score.json` and `sfx.json`, then call `sound` once to prove they render. The music
   ducks under the voice by itself.
6. Finish with one or two sentences: what the film shows and says, and anything from the prompt
   you could not do.

## RULES
- **The ground.** `SK.setGround(name)` once at the top of film.js (a film that changes, say from
  day to night, gives `SK.film` a `ground: (t) => name` instead). It sets the paper, its grain
  and the colours that read on it: `C.text`, `C.textSoft`, `C.accent`, `C.accentText`.
  Outlines (`C.ink`) stay dark on every ground; on a dark one, a bare line (an arrow, a path)
  takes `col: C.text`. Choose it for the film:
  - `paper` -- cream sketchbook: notes, doodles, a story told on a page
  - `white` -- crisp and modern: products, tech, business, how-to (with `'clean'`)
  - `kraft` -- brown wrapping paper: crafts, food, history, the handmade, autumn
  - `sky` -- pale blue: air, weather, travel, flight, calm
  - `mint` -- pale green: nature, health, growing, spring
  - `butter` -- warm pale yellow: sunshine, cooking, the cheerful everyday
  - `blush` -- soft pink: love, care, gentle stories
  - `night` -- deep navy: night, space, dreams, mystery, bedtime
  - `chalkboard` -- a dark board in chalk: lessons, maths, school, a recipe written up
  - `blueprint` -- drafting blue with a grid: how things work, engineering, plans (with `'clean'`)
- **A place, not a page.** Fill the frame with where the film happens -- unless the idea really
  is a sheet of paper (notes, a diagram, a chalk lesson). The backdrops come first in `draw` and
  cover whatever the camera shows, so their edges never come into frame:
  - `SK.sky(top, bottom, {mid})` -- a gradient sky over the whole frame;
  - `SK.band(y, col, {edge: 'flat'|'hills'|'waves'|'grass', amp, len, seed})` -- ground, sea,
    hills, grass or a wall, from world height y down; it returns `edge(x)`, the height to stand
    things on;
  - `SK.stars({n, seed})` -- a starry sky, twinkling.
  Then scenery (`P.tree`, `P.bush`, `P.cloud`, `P.sun`, `P.moon`, `P.mountain`, `P.building`,
  `P.house`), then the characters, then a near band in front for depth. A room is a band for the
  wall and one for the floor; the sea is two bands of `waves`.
- **Characters give a film its charm.** Draw the film's own -- an animal, an object with a face
  (`P.face.eyes`, `P.face.mouth`) -- or use the cast's (`P.kid`, `P.person`) when they fit. Props
  are drawn at a fixed design size and scaled uniformly.
- Never open on a blank page: start first draw-ons at about 20% (`clamp(.2 + .8 * E.out(...))`)
  so frame 0 already shows the pen at work -- and the place is there from the first frame.
- Use `SK.camera` for a push-in or a move between places; a short film needs one or two moves at
  most. Draw order is paint order; cull with `vis(x0, y0, x1, y1)` if you lay out more than one
  place.
