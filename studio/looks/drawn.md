## INTRO
The look is **hand-drawn**: everything is drawn in code with the engine's pen and the props
below -- the crayon look (`SK.setStyle('crayon')`), or `SK.setStyle('clean')` for crisp
editorial line art -- on a ground you choose.

## FILES

## COMMANDS

## DIRECTION
- what fills the frame, scene by scene;
- the ground (below) and the style, crayon or clean;
- who or what is on screen: the person's own cast (cast/) when this continues their films, else
  whatever this film needs;

## STEPS
1. Decide the idea and the direction (above): one clear point, told in the film's length -- a
   setup, one action and a payoff you can hold for the last second or so. A longer film strings
   a few such beats together -- two to four for 30-60 s, four to eight for 90-120 s -- in places
   or moments that still build towards one point.
2. Write the narration in `vo.json` and call `voice`. It returns each line's start and end and
   every word's time on the film clock. If a line runs past the end of the film or `acc` is
   below 0.9, shorten or rephrase it and record again.
3. Write `film.js`: first the `// For:` line (see "Direction"), then the ground, then `draw` --
   any backdrop first, then the film, a small function per scene -- cueing the picture to the
   words (`SK.w(line, 'word', fallbackSeconds)`). Call `check`.
4. Call `stills` with about six times spread over the film -- ten or twelve for a film
   over a minute -- (always 0, and one just before the end), Read `outputs/review/sheet.png`,
   and call `motion` once and Read `outputs/review/motion.png`. Look first at the sheet as a
   whole, against film.js's `// For:` line: would that audience take this film seriously, and
   does it look professionally made for them? If not, fix that before anything else. Then look
   hard at the details: blank or near-empty frame 0, a frame that looks unfinished, the edge of
   a backdrop, things cut off by the frame edge, overlaps, text collisions, text or lines that
   do not read on the ground, elements hidden behind later-drawn ones, faces that read wrong,
   text that does not match the narration; and from `motion`, any stretch where nothing moves
   and any cut where nothing carries over or the new scene waits empty for its subject. Fix and
   re-check. Two review rounds at most.
5. Write `score.json` and `sfx.json`, then call `sound` once to prove they render. The music
   ducks under the voice by itself.
6. Finish with one or two sentences: what the film shows and says, and anything from the prompt
   you could not do.

## RULES
- **The ground.** `SK.setGround(name)` once at the top of film.js (a film that changes, say from
  day to night, gives `SK.film` a `ground: (t) => name` instead). It sets the paper, its grain
  and the colours that read on it: `C.text`, `C.textSoft`, `C.accent`, `C.accentText`.
  Outlines (`C.ink`) stay dark on every ground; on a dark one, a bare line (an arrow, a path)
  takes `col: C.text`. The grounds:
  - `paper` -- cream sketchbook paper
  - `white` -- a crisp editorial page
  - `kraft` -- brown wrapping paper
  - `sky` -- pale blue
  - `mint` -- pale green
  - `butter` -- warm pale yellow
  - `blush` -- soft pink
  - `night` -- deep navy
  - `chalkboard` -- a green-black board, drawn on in chalk
  - `blueprint` -- drafting blue with a white grid
- **Backdrops.** A backdrop is drawn first in `draw` and covers whatever the camera shows, so its
  edges never come into frame:
  - `SK.sky(top, bottom, {mid})` -- a gradient over the whole frame;
  - `SK.band(y, col, {edge: 'flat'|'hills'|'waves'|'grass', amp, len, seed})` -- a band from
    world height y down (ground, sea, hills, grass, a wall or a floor); it returns `edge(x)`, the
    height to stand things on;
  - `SK.stars({n, seed})` -- a starry sky, twinkling.
  Scenery props: `P.tree`, `P.bush`, `P.cloud`, `P.sun`, `P.moon`, `P.mountain`, `P.building`,
  `P.house`.
- **One film, not a slideshow.** Scenes follow on from each other: carry something across every
  change -- the same character, an object that travels, one camera move through a single wide
  world, a match on a shape or a colour. A new scene opens with its subject already in frame,
  never an empty stage waiting for it. Nothing holds still for more than about 3 s: keep a slow
  camera drift or push, a small action, something drawing on.
- Props are drawn at a fixed design size and scaled uniformly.
- Never open on a blank frame: when things draw on, start the first ones at about 20%
  (`clamp(.2 + .8 * E.out(...))`) so frame 0 already shows something.
- Use `SK.camera` for a push-in or a move between places; keep the moves few enough that the
  frame always reads. Draw order is paint order; cull with `vis(x0, y0, x1, y1)` if you lay out
  more than one place.
