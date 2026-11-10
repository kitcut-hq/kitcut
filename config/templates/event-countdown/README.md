# Event countdown -- the template's code

kitcut.ai's event-countdown template (studio/templates.py; its spec and brief:
`../event-countdown.json`).

- `film.js` -- the film, 26 s, music only: a tear-off wall calendar in the event's colours drops
  onto its nail with today's page; its pages rip off and fly past the camera, counting down to a
  huge number with DAYS TO GO (or a word such as TOMORROW, or a deadline, fitted on up to three
  lines); the count page tears off at the camera and leaves up to three published facts pinned as
  torn pages; a ticket turns in and its price tag flips from today's price to the next one; and
  the month's grid circles the event's first day over the logo, the dates, the city, a button and
  the link. Every word, colour and the logo come from `SK.DATA.content`; the month grid and its
  weekdays are worked out from the event's ISO dates; its music and cues are worked out from its
  own clock and content (`SK.film({sound})`, `sketch-render.py --sound-data`). It holds in 1:1
  (the main frame), 16:9 and 9:16.

What closes up when a fact is missing: no facts (the count holds to bar 7 and says the dates, the
ticket has the rest), one or two facts, no price (no tag), one price (no flip), no deadline, no
venue, no link, no button, no today's page, a long lockup (two lines beside a taller logo).

The sample is a real event with its own logo, numbers and prices, and this repo is public: the
sample's content and logo live only with the working project, `projects/event-countdown/` (local),
whose `film.js` this is a copy of. A version is made from that project:

    python studio/template_from_film.py make --slug event-countdown --push --publish

v1 (2026-10-05): from kitcut.ai film studio-20261005-122635-bjqeeq, itself a remake of the
Conference speaker promo with every scene replaced; proven pixel-identical to it, then polished:
the cut out of the count is a torn page flying off (it was a quarter second of flat colour), the
facts are large (a column of wide pages in a square frame), the tag is larger and the flip pushes
in, the month is larger, a long lockup sets on two lines, the count can be a word or a deadline
and the torn pages count down to it (`count.days`), labels in scripts the event's face lacks fall
back to Sofia Sans, and the button's glint is a soft band (a hard one read as a stray "7").
