# Open house invitation -- the template's code

kitcut.ai's open-house-invitation template (studio/templates.py; its spec and brief:
`../open-house-invitation.json`).

- `film.js` -- the film, 30 s, narrated, in the host's own look: a yard sign swinging in with the
  logo, the day and the hours, beside the home's name; then one large card (the picture over a
  caption strip) that carries the rest: the home's photo with the day on it and the address under
  it; bedrooms, bathrooms, square feet and price ticking in, each in its own place in the strip; two
  or three more photos, each with its room's name; the card shrinking onto a drawn street map as the
  pin drops; and an end card with the day, the hours, the address and who to call. Six narration
  lines, one scene each, every cue hung on a word of its line (`SK.cues` at the top). Every fact and
  picture comes from `SK.DATA.content`, every layout from the frame: it holds in 16:9, 1:1 and 9:16,
  and with no day, no venue, no facts, no rooms or no photo at all (`content.alt.json` and
  `content.alt2.json` in the project are the stress sets).

The sample is a real builder's event (Lennar's Driftwood model grand opening at Pepperwood, Stuart,
Florida), with its logo and photos, and this repo is public: the sample's content, narration, sound
and pictures live only with the working project, `projects/open-house-invitation/` (local), whose
`film.js` this is a copy of. A version is made from that project:

    python studio/template_from_film.py make --slug open-house-invitation --push --publish

v3 (2026-10-05): redesigned after watching v2 frame by frame. The photos were 70% of the width with
an empty band under them, the facts re-centred as each arrived, and the square frame overlapped; now
the photos fill the frame, the facts have fixed places, and all three frames are offered. v3 is no
longer pixel-identical to the studio film it began as (studio-20261003-220824-nkmkf2); the narration
and its timing are unchanged. v2 was that film as pulled; v1 the overnight draft.
Known weak spots: the sample's exterior is a 1760 x 398 banner off the event page, so it is soft
when it fills the vertical frame; a remake from a builder's name alone can find a past event or no
date at all (the brief asks for an upcoming date with the calendar's weekday, or none).
