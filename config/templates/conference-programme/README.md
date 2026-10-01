# The programme -- the template's code

kitcut.ai's programme template (studio/templates.py; its spec and brief: `../conference-programme.json`):
a conference's agenda in 90 seconds as a metro map, music only.

- `film.js` -- the film: every word, time, colour, logo and person comes from `SK.DATA.content`. Its
  clock (112 bpm) is worked out from the content -- how many stops and days -- always inside the same
  bars, so any programme within the limits keeps the 90 s; its music and cues are worked out from that
  clock (`SK.film({sound})`, `sketch-render.py --sound-data`).
- `content.sample.json` -- the sample it was made with: PGConf.EU 2026 (Valencia, 20-23 October),
  nine highlights over four days on its four tracks, in the colours its own schedule gives them.

The sample's logo is PGConf.EU's and stays out of the repo; it lives with the working project,
`projects/conference-programme/` (local), whose `film.js` this is a copy of, with the schedule it
was taken from (`sources/`) and three stress contents (`tests/`: Ukrainian on one day, six tracks
over four days with twelve stops and a keynote picture, two tracks over two days). A version is made
from that project:

    python studio/templates.py make --folder projects/conference-programme --id t-conference-programme --spec config/templates/conference-programme.json

What the code does for any content:

- **A snake of rows.** Each day is a row of the map, left to right then right to left, joined by
  half-circle bends; the bundle of lines keeps a fixed lateral offset per line, so the bends come out
  concentric. A one-day event is drawn as two rows (morning, afternoon). Line spacing and width follow
  the row height, and the ride's zoom follows the spacing, so the lines are the same width on screen
  for one day or six.
- **Stations by time.** Each day's stops sit along its row by their start time, kept a minimum gap
  apart; a keynote (or a stop on no line) is an interchange: the bundle pinches and a capsule crosses
  every line.
- **The clock from the content.** The ride runs from beat 24 to 136 whatever the content: a change of
  day takes 8 beats, the rest is shared evenly between the stops (4 to 16 beats each), and what is
  left is the run to the end of the line. Every arrival, sign and board lands on a beat.
- **Labels that do not collide.** The overview's day names and station labels are placed once,
  greedily, off the lines and the bends and off each other: own side, the other side, a step further
  out with a hairline, the time alone, or none.
- **Cyrillic.** Sofia Sans draws Bulgarian letterforms by default; for Cyrillic in any other language
  (`content.lang` not `bg`) the canvas is tagged so its standard forms are used.

v1 (2026-09-30): the PGConf.EU sample.
