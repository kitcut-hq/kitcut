## INTRO
The look is **hand-drawn**: everything is drawn in code with the engine's pen and the cast of
props below -- the crayon look by default, or `SK.setStyle('clean')` for crisp editorial line art
when the prompt calls for it.

## FILES

## COMMANDS

## STEPS
1. Decide the idea: one clear point, told in the film's length -- a setup, one action and a
   payoff you can hold for the last second or so. A longer film (30 s and up) strings a few
   such beats together, in two to four places or moments, still towards one point.
2. Write the narration in `vo.json` and call `voice`. It returns each line's start and end and
   every word's time on the film clock. If a line runs past the end of the film or `acc` is
   below 0.9, shorten or rephrase it and record again.
3. Write `film.js`, cueing the picture to the words (`SK.w(line, 'word', fallbackSeconds)`), then
   call `check`.
4. Call `stills` with about six times spread over the film (always 0, and one just before the
   end), and Read `outputs/review/sheet.png`. Look hard: blank or near-empty frame 0, things cut
   off by the frame edge, overlaps, text collisions, elements hidden behind later-drawn ones,
   faces that read wrong, text that does not match the narration. Fix and re-check. Two review
   rounds at most.
5. Write `score.json` and `sfx.json`, then call `sound` once to prove they render. The music
   ducks under the voice by itself.
6. Finish with one or two sentences: what the film shows and says, and anything from the prompt
   you could not do.

## RULES
- Never open on a blank page: start first draw-ons at about 20% (`clamp(.2 + .8 * E.out(...))`)
  so frame 0 already shows the pen at work.
- Use the props in `SK.P` generously: they are drawn at a fixed design size and scaled uniformly.
  Characters (`P.person`, `P.kid`, `P.ticket` with a face) give a film its charm.
- Use `SK.camera` for a push-in or a move between places; a film this short needs one or two
  moves at most. Draw order is paint order; cull with `vis(x0, y0, x1, y1)` if you lay out more
  than one place.
