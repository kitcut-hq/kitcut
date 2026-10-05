# Open house invitation -- the template's code

kitcut.ai's open-house-invitation template (studio/templates.py; its spec and brief:
`../open-house-invitation.json`).

- `film.js` -- the film, 30 s, narrated, in the host's own look: a yard sign swinging in with the
  logo, the day and the hours; the home's photo with its address; bedrooms, bathrooms, square feet
  and price ticking in; two or three more photos, each with its room's name; a pin dropping on a
  drawn street map; and an end card with the day, the hours, the address and who to call. Six
  narration lines, one scene each, every cue hung on a word of its line (`SK.cues` at the top). Every
  fact and picture comes from `SK.DATA.content`. It holds in 16:9 and 9:16; in 1:1 the yard sign and
  the end card overlap, so the square frame is not offered yet.

The sample is a real builder's event (Lennar's Driftwood model grand opening at Pepperwood, Stuart,
Florida), with its logo and photos, and this repo is public: the sample's content, narration, sound
and pictures live only with the working project, `projects/open-house-invitation/` (local), whose
`film.js` this is a copy of. A version is made from that project:

    python studio/template_from_film.py make --slug open-house-invitation --push --publish

v2 (2026-10-05): from studio film studio-20261003-220824-nkmkf2, made on the VM overnight
(`studio/overnight_templates.py`) and proven pixel-identical to it. v1 was that night's rough draft.
Known weak spot: a remake from a builder's name alone can find a past event or no date at all; the
brief now asks for an upcoming date with the calendar's weekday, or none.
