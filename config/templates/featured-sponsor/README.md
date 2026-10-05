# Featured sponsor -- the template's code

kitcut.ai's featured-sponsor template (studio/templates.py; its spec and brief:
`../featured-sponsor.json`).

- `film.js` -- the film, 26 s, music only: a coin press whose die carries the sponsor's logo
  creeps down over a blank, draws back and strikes on the music's hit (a flash, a ring, sparks);
  the logo stands in relief in the tier's metal; the coin is tossed, spins in 3D and lands on the
  event's logo; it stands large and turns beside the sponsor's name, one line about them and where
  to find them; then it rolls along a tray of blank slots and drops into the first, over the
  event's logo, dates, city and link. The coin is one drawn component (two faces, a reeded edge
  with thickness, a metal), reused small in the tray. Every word, colour, logo and metal comes
  from `SK.DATA.content`; its music and cues are worked out from its own clock
  (`SK.film({sound})`, `sketch-render.py --sound-data`). It holds in 1:1 (the main frame), 16:9
  (the coin left, the words right; the tray left, the sign-off right) and 9:16.

The sample is a real sponsor of a real event, with both logos, and this repo is public: the
sample's content and pictures live only with the working project, `projects/featured-sponsor/`
(local), whose `film.js` this is a copy of. A version is made from that project:

    python studio/template_from_film.py make --slug featured-sponsor --push --publish

v1 (2026-10-05): from kitcut.ai film studio-20261005-122631-gzityz, itself a remake of the
Conference speaker promo with every scene replaced; proven pixel-identical to it, then polished:
the press is whole in the frame with a yoke that rides the columns, the die creeps down and draws
back before the blow, the blow flashes and kicks the camera, the coin is thicker, the
who-they-are scene is laid out from the type it has to carry (a large coin, the name and line as
large as the frame allows, evened lines), the words leave before the tray comes, the tray has six
large slots, a long address is cut back to what can be read, a face with no logo file carries the
name in type, and other scripts fall back to a face that has them.
