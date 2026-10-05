# Trade show booth invitation -- the template's code

kitcut.ai's trade-show-booth-invite template (studio/templates.py; its spec and brief:
`../trade-show-booth-invite.json`).

- `film.js` -- the film, 30 s, narrated, in the exhibitor's own look: the exhibitor's logos, large,
  then the show's name, dates and city under them; a drawn hall of numbered stands (numbered by
  counting out from the stand's own number: never a real plan) with an entrance and a dotted route
  the camera follows to one stand, which lights up with its hall and booth number; the stand rising
  as a real stand (logos on the back wall, a counter, a screen, a plant, two plain figures) with up
  to three things to see there; the exhibit hours, one to five days; and an end card with the booth
  number large. Five narration lines, one scene each, every cue hung on a word of its line
  (`SK.cues` at the top). Every fact comes from `SK.DATA.content`; every column is stacked and
  centred from what is there, so a missing hall, area, booth number, link or list leaves no hole,
  and it holds in 16:9, 1:1 and 9:16.

The sample is a real exhibitor at a real show (Radiology Partners and Mosaic Clinical Technologies
at RSNA 2026), with their logos, and this repo is public: the sample's content, narration, sound
and logos live only with the working project, `projects/trade-show-booth-invite/` (local), whose
`film.js` this is a copy of. A version is made from that project:

    python studio/template_from_film.py make --slug trade-show-booth-invite --push --publish

v2 (2026-10-05): from kitcut.ai film studio-20261003-215229-l6j4hi, made on the VM overnight
(`studio/overnight_templates.py`) and proven pixel-identical to it. v1 was that night's rough draft.
v3 (2026-10-05): redrawn after watching v2 frame by frame (a five-second still opening with a hole
in it, three seconds of bare grey plan, a stand that was a blue block). No longer the film it was
pulled from, so `prove` no longer applies; stress contents are `content.alt.json` (no booth number,
a long show name, nothing to see, one day) and `content.alt2.json` (stand A18, five days) in the project.
