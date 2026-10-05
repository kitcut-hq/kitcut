# Trade show booth invitation -- the template's code

kitcut.ai's trade-show-booth-invite template (studio/templates.py; its spec and brief:
`../trade-show-booth-invite.json`).

- `film.js` -- the film, 30 s, narrated, in the exhibitor's own look: the show's name, dates and city
  with the exhibitor's logo; a drawn hall of stands the camera flies over until one lights up with
  its hall and booth number; the stand rising with the logo and up to three things to see there; the
  exhibit hours day by day; and an end card with the booth number large. Five narration lines, one
  scene each, every cue hung on a word of its line (`SK.cues` at the top). Every fact comes from
  `SK.DATA.content`, and the layout is worked out from the frame, so it holds in 16:9, 1:1 and 9:16.

The sample is a real exhibitor at a real show (Radiology Partners and Mosaic Clinical Technologies
at RSNA 2026), with their logos, and this repo is public: the sample's content, narration, sound
and logos live only with the working project, `projects/trade-show-booth-invite/` (local), whose
`film.js` this is a copy of. A version is made from that project:

    python studio/template_from_film.py make --slug trade-show-booth-invite --push --publish

v2 (2026-10-05): from kitcut.ai film studio-20261003-215229-l6j4hi, made on the VM overnight
(`studio/overnight_templates.py`) and proven pixel-identical to it. v1 was that night's rough draft.
