# Conference speaker promo -- the template's code

kitcut.ai's first template (studio/templates.py; its form and brief: `../conference-speakers.json`).

- `film.js` -- the film: every word, colour, logo and person comes from `SK.DATA.content`; its music and
  cues are worked out from its own clock and content (`SK.film({sound})`, `sketch-render.py --sound-data`).
- `content.sample.json` -- the sample it was made with: Web Summit 2026 and its speakers.

The sample's pictures (Web Summit's logo, the speakers' cut-outs) are third-party and stay out of
the repo; they live with the working project, `projects/websummit-speakers/` (local), whose
`film.js` this is a copy of. A version is made from that project:

    python studio/templates.py make --folder projects/websummit-speakers --id t-conference-speakers --spec config/templates/conference-speakers.json

v1 (2026-09-30): the template-ready Web Summit film. v2: with no measured logo symbol the opening
card turns the accent as the logo fades and the camera dives into it -- the v1 fallback, a disc of the
accent opening over the logo, read as a stray blot in all three bake-off films.
