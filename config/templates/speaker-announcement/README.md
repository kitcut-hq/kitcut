# Speaker announcement card -- the template's code

kitcut.ai's speaker-announcement template (studio/templates.py; its spec and brief:
`../speaker-announcement.json`).

- `film.js` -- the film, 26 s, music only: a foil pack in the event's colours tears open, a card
  flips out in 3D and lands face up under a holographic shine, the card is read (cut-out photo,
  name, role and company, the talk, the track, day, time and stage), it tilts with sparks, and it
  drops into a binder page of face-down cards over the event's logo, dates and link. Every word,
  colour, logo and person comes from `SK.DATA.content`; its music and cues are worked out from its
  own clock (`SK.film({sound})`, `sketch-render.py --sound-data`). It holds in 1:1 (the main
  frame), 16:9 (the card left, the talk set large on the right) and 9:16.

The sample is a real speaker at a real event, with his photo and two companies' logos, and this
repo is public: the sample's content and pictures live only with the working project,
`projects/speaker-announcement/` (local), whose `film.js` this is a copy of. A version is made from
that project:

    python studio/template_from_film.py make --slug speaker-announcement --push --publish

v1 (2026-10-05): from kitcut.ai film studio-20261003-215221-mikimq, itself a remake of the
Conference speaker promo with every scene replaced; proven pixel-identical to it, then polished:
the wide frame's camera no longer pulls the card under the talk's details, the card, pack, reading
stops, binder and end card fit a vertical frame, a long role wraps to two lines, a speaker with no
photo gets their initials, and labels in scripts the UI face lacks fall back to the wide face.

v2 (2026-10-05): the binder shows the speakers already announced (`announced` in the content, 0 to
8): each sits open in a slot as a small card with their photo or initials and their name, the new
card lands in the middle with a halo, and the rest stay face down. With none it is v1's film.
