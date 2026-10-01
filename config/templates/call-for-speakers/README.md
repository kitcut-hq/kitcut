# Call for speakers -- the template's code

kitcut.ai's call-for-speakers template (studio/templates.py; its spec and brief: `../call-for-speakers.json`).

- `film.js` -- the film, 90 s at 120 bpm: every word, date, colour and logo comes from `SK.DATA.content`;
  its music and cues are worked out from its own clock and content (`SK.film({sound})`,
  `sketch-render.py --sound-data`). It needs the `space` module (`SK.fx`, for the whip pans).
- `content.sample.json` -- the sample it was made with: KubeCon + CloudNativeCon Europe 2027's call for
  proposals (Barcelona, 15-18 March 2027; closes 11 October 2026), every fact from the event's CFP page
  and its Sessionize call (the sources are in the project's `sketch.json` `_sources`).

The sample's logo is the Linux Foundation's and stays out of the repo; it lives with the working project,
`projects/call-for-speakers/` (local), whose `film.js` and `content.json` these are copies of. A version is
made from that project:

    python studio/templates.py make --folder projects/call-for-speakers --id t-call-for-speakers --spec config/templates/call-for-speakers.json

What the content may hold, and where it is tight, is in the spec's brief. The layouts were drawn with the
sample (13 topics, 4 formats, 1 perk, 5 dates), a made-up Ukrainian event (3 topics, a format in days, no
perks, no logo, 80 days left) and a made-up English one (8 topics, 5 formats, 5 perks, 6 dates, 3 days
left), and with no `as_of` (the deadline shown in place of a count).

v1 (2026-10-01): the KubeCon + CloudNativeCon Europe 2027 sample.
