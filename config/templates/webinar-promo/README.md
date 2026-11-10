# Webinar promo -- the template's code

kitcut.ai's webinar-promo template (studio/templates.py; its spec and brief: `../webinar-promo.json`).

- `film.js` -- the film, 30 s, narrated, in the host's own colours: the host's logo with a LIVE
  WEBINAR tag and the date; the title set large in even lines (`setType` picks the breaks), each
  lighting as it is said; one to three speakers, each with a photo in a ring or their initials on
  the host's colour, with name, role and organisation; up to three things people will learn, each on
  its own card; one centred card of the date, the time with its time zone, the length and whether it
  is free; and a Register end card with the date, the time and the link. Six narration lines, one
  scene each, every cue hung on a word of its line (`SK.cues` at the top). Every fact comes from
  `SK.DATA.content`, every scene is centred in the space under the header, and it holds in 16:9, 1:1
  and 9:16.

The sample is a real webinar (the National Board of Public Health Examiners' Webinar Wednesday of
November 18, 2026), with the host's logo, and this repo is public: the sample's content, narration,
sound and logo live only with the working project, `projects/webinar-promo/` (local), whose
`film.js` this is a copy of. A version is made from that project:

    python studio/template_from_film.py make --slug webinar-promo --push --publish

v2 (2026-10-05): from studio film studio-20261003-220824-tklmoy, made on the VM overnight
(`studio/overnight_templates.py`) and proven pixel-identical to it. v1 was that night's rough draft.

v3 (2026-10-05): redrawn after watching v2 frame by frame: scenes were top-anchored with the foot of
the frame empty, the title broke raggedly, a speaker without a photo was a bare name, the date scene
was half left-aligned, the end card had no date, and the header was cut in the square and vertical
frames. The sample's link is now the host's own short page (nbphe.org/webinar-wednesday) instead of
a Zoom address nobody could type. Stress contents: `content.alt*.json` in the project.
