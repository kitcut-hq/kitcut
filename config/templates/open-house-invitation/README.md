# Open house invitation -- the template's code

kitcut.ai's open-house-invitation template (studio/templates.py; its spec and brief:
`../open-house-invitation.json`).

- `film.js` -- the film, 30 s, narrated, in the host's own look: a yard sign swinging in with the
  logo, the day and the hours, beside the home's name; then one large card (the picture over a
  caption strip) that carries the rest: the home's photo with the day on it and the address under
  it; bedrooms, bathrooms, square feet and price ticking in, each in its own place in the strip; two
  or three more photos, each with its room's name; the card shrinking onto the real street map of the
  place (the map tool: `SK.DATA.place`, drawn with the kit's `SK.map` and `SK.mapPin`) as the pin
  drops, the home's own street lit and named; and an end card with the day, the hours, the address
  and who to call. Six narration
  lines, one scene each, every cue hung on a word of its line (`SK.cues` at the top). Every fact and
  picture comes from `SK.DATA.content`, every layout from the frame: it holds in 16:9, 1:1 and 9:16,
  and with no day, no venue, no facts, no rooms or no photo at all (`content.alt.json` and
  `content.alt2.json` in the project are the stress sets), and with no map (`sketch.nomap.json`: a
  place the map tool could not find leaves `place.json` saying so, and the card then stays large
  with the address under the picture).

The sample is a real listing (2601 NE 29th Street, Fort Lauderdale; Coldwell Banker Realty, open house
Sunday October 18 2026), with the brokerage's logo and the listing's photos, and this repo is public: the sample's content, narration, sound
and pictures live only with the working project, `projects/open-house-invitation/` (local), whose
`film.js` this is a copy of. A version is made from that project:

    python studio/template_from_film.py make --slug open-house-invitation --push --publish

v7 (2026-10-07): in the vertical frame the agent's photo stands over the name on the end card (side by side, the
name ran under the buttons Reels and TikTok lay over the right edge). v6 (2026-10-07): the agent is in it, because people buy from people. `content.agent` {name, role, phone,
photo {img, fx, fy, zoom}}: a rider hangs under the yard sign with the photo, the name and the number,
and the end card sets the photo beside the name, what they are and the number to call, in place of the
plain contact pill. The photo is the agent's own headshot (an attachment, or the one the listing's own
page shows for that agent), cropped to a circle by `face()`. With no photo the name stands alone; with
no agent the film is as it was (`contact`). The sample's is the listing team's leader, from the
brokerage's page. The three showcase films were made again on the studio VM from the changed files
(`ops.sh resume <id> --finish --patched`), not on a laptop. v5: the street's name beside the pin when
its street leaves no clear spot.

v4 (2026-10-06): the map is real. v3 drew a ruled grid with two green ovals and lit one of its lines
as "the host's street"; nothing on it existed. Now the map tool makes the street map of the address
from OpenStreetMap and the film draws that: the sample's shows Coral Ridge's own streets, its houses,
the Middle River and the canals. The sample changed with it, to a real listing whose street is on the
map (the Lennar sample's street, in a subdivision still being built, is on no map yet -- the tool
refuses such an address, and the film then shows it in type). The narration was recorded again and
its cues moved with it.

v3 (2026-10-05): redesigned after watching v2 frame by frame. The photos were 70% of the width with
an empty band under them, the facts re-centred as each arrived, and the square frame overlapped; now
the photos fill the frame, the facts have fixed places, and all three frames are offered. v3 is no
longer pixel-identical to the studio film it began as (studio-20261003-220824-nkmkf2); the narration
and its timing are unchanged. v2 was that film as pulled; v1 the overnight draft.
Known weak spots: the sample's exterior is 1538 px wide (the largest the listing serves), so it is a
little soft in the vertical frame; a house number OpenStreetMap does not have is placed along its
street from the address range, so the pin stands on the street, right to a house or two; a remake from a builder's name alone can find a past event or no
date at all (the brief asks for an upcoming date with the calendar's weekday, or none).
