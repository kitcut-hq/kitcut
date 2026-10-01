# The conference in numbers -- the template's code

A kitcut.ai template (studio/templates.py; its spec and brief: `../conference-numbers.json`).

- `film.js` -- the film: every word, number, colour, logo and place comes from `SK.DATA.content`;
  its music and cues are worked out from its own clock and content (`SK.film({sound})`,
  `sketch-render.py --sound-data`). It carries its own dot map of the world (Natural Earth 1:110m
  land, public domain, rasterised at 1.5 degrees into a base64 bitset).
- `content.sample.json` -- the sample it was made with: Web Summit 2026 (Lisbon, Nov 9-12), told
  in the 2025 edition's published numbers.

88 s, 1920 x 1080, 60 fps, music only. The story on a 120 bpm clock: the logo assembles out of
digits (0-8 s), a calendar marks the dates (8-12), a pin drops on the venue (12-16), one chapter
per number (3 to 7 share 16-64 s), each rolling up like an odometer over a picture chosen by its
`kind` -- people, countries, companies, network, speakers, sessions, years, media, type -- the
topics as a wall of words with an optional quote (64-76), and the poster (76-88).

The sample's logo is third-party and stays out of the repo; it lives with the working project,
`projects/conference-numbers/` (local), whose `film.js` this is a copy of. A version is made from
that project:

    python studio/templates.py make --folder projects/conference-numbers --id t-conference-numbers --spec config/templates/conference-numbers.json

v1 (2026-09-30): the Web Summit film, checked with two made-up events besides the sample (three
numbers in Ukrainian with no logo, a long venue and dates across two months; seven numbers on a
green-and-orange palette with a three-line quote).
