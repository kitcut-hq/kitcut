# Webinar promo -- the template's code

kitcut.ai's webinar-promo template (studio/templates.py; its spec and brief: `../webinar-promo.json`).

- `film.js` -- the film, 30 s, narrated, in the host's own colours: the host's logo with a LIVE
  WEBINAR tag and the date; the title set large, arriving phrase by phrase; one to three speakers
  with their photos, names, roles and organisations; up to three things people will learn; the date,
  the time with its time zone, the length and whether it is free; and a Register end card with the
  link. Six narration lines, one scene each, every cue hung on a word of its line (`SK.cues` at the
  top). Every fact comes from `SK.DATA.content`. Wide (16:9) only: in the square and vertical frames
  the header's logo is cut by the top edge.

The sample is a real webinar (the National Board of Public Health Examiners' Webinar Wednesday of
November 18, 2026), with the host's logo, and this repo is public: the sample's content, narration,
sound and logo live only with the working project, `projects/webinar-promo/` (local), whose
`film.js` this is a copy of. A version is made from that project:

    python studio/template_from_film.py make --slug webinar-promo --push --publish

v2 (2026-10-05): from studio film studio-20261003-220824-tklmoy, made on the VM overnight
(`studio/overnight_templates.py`) and proven pixel-identical to it. v1 was that night's rough draft.
