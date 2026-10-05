# Featured sponsor -- the template's code

kitcut.ai's featured-sponsor template (studio/templates.py; its spec and brief:
`../featured-sponsor.json`).

- `film.js` -- the film, 26 s, music only, in the EVENT's own look: its ground colour, its type,
  its buttons and its key art along the bottom, with its logo top right as on its own social card.
  "THANK YOU TO OUR" and the tier, large; on the music's hit the art drops away, a line opens into
  a white rounded panel and the sponsor's logo is there, flat and still; the panel settles and the
  tier over a rule, one line about the sponsor and where to find them come beside it; the panel
  grows into a sponsor wall (the tier in light tracked capitals over its rule, the logo large);
  the wall drops away to the dates and the city in bold capitals over the art in full colour, the
  venue and the link. Every word, colour, logo and picture comes from `SK.DATA.content`; its music
  and cues are worked out from its own clock (`SK.film({sound})`, `sketch-render.py --sound-data`).
  It holds in 1:1 (the main frame), 16:9 (the panel left, the words right) and 9:16.

**The logo rule the code keeps.** A sponsor's logo is drawn as its file draws it, flat and whole,
on a solid panel (white under dark ink, the sponsor's own colour under a white logo) with clear
space of at least a quarter of its height on every side. It fades in and it moves with its panel,
one size and one move together; it is never turned, squashed, recoloured, shaded, lit, cropped
inside the frame or laid on the art. The film has no grain or vignette for the same reason: nothing
is laid over a logo. The key art is one picture, whole, panned slowly; nothing of it is redrawn.

The sample is a real sponsor of a real event, with both logos and the event's own key art, and
this repo is public: the sample's content, pictures and font files live only with the working
project, `projects/featured-sponsor/` (local), whose `film.js` this is a copy of. A version is
made from that project:

    python studio/template_from_film.py make --slug featured-sponsor --push --publish

v3 (2026-10-05): written again from nothing. v1 and v2 struck the sponsor's logo into a coin of
the tier's metal in a press (a remake of the Conference speaker promo, kitcut.ai film
studio-20261005-122631-gzityz). The owner's verdict on seeing it: cringe, and it follows neither
style book. Both were right. A coin press is a costume that belongs to neither brand; the magenta
label and yellow button were guessed, not read off the event's pages; and a logo embossed in a
metal gradient, tilted in 3D with a shine across it breaks the first rules of every logo standard
(no gradients or shadows on or behind it, never distorted, clear space, never on a cluttered
ground). v3 starts from the two style books instead: the event's own social card and sponsor page
(a flat ground, bold capitals in its own face, its key art, tier headings in light tracked
capitals over a thin rule, every sponsor's logo flat on white), and the sponsor's logo standards.
The coin's code is kept beside the project (`temp/film.v2-coin.js`) and nowhere else. v3 is not a
pull of a studio film, so `template_from_film.py prove` has nothing to compare it with; `check`,
`alt`, `make` and `test` work as for any template.
