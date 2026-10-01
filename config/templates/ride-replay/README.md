# Ride replay -- the template's code

kitcut.ai's ride-replay template (studio/templates.py; its spec and brief: `../ride-replay.json`).

- `film.js` -- the film, 45 s on a 120 bpm clock: every word, colour and picture comes from
  `SK.DATA.content`, and the route and its map from `SK.DATA.route` (route.json, written by the studio's
  route tool: `scripts/route-map.py --film`). Its music and cues are its own (`SK.film({sound})`). The
  replay's camera is worked out from the route's size, so a 3 km run and a 60 km loop play the same 45 s.
- `content.sample.json` -- the sample it was made with: Pedal & Network, Instafill.ai's LA Tech Week
  gravel ride, Sunday 18 October 2026, from Santa Monica Pier up Sullivan Fire Road to Dirt Mulholland and
  back (23.5 mi, 2,590 ft), the route a recorded ride cut to start and finish at the Pier.

The template is the first with **data beside its content** and **assets**: route.json is seeded as the
film's own (`"data": {"route": ...}` in the manifest; a version keeps it as `route.sample.json`), and the
generic cut-outs every ride keeps -- riders, bike, jersey, bibs, gels, bar, bottles -- are `assets` in the
spec: copied apart, seeded as `template/assets/`, never a leftover. The sample's own pictures (the pier, the
palm, the photograph of the route, the map, the logos, the QR code) are leftovers until a film replaces them.

The sample's logos (Tech Week's cover, Instafill's wordmark) and the recorded ride are third-party and stay
out of the repo; they live with the working project, `projects/ride-replay/` (local), whose `film.js` and
`content.json` these are copies of. A version is made from that project:

    python studio/templates.py make --folder projects/ride-replay --id t-ride-replay --spec config/templates/ride-replay.json

v1 (2026-10-01): the Pedal & Network film (kitcut.ai film studio-20261001-132538-dnqtvr), its clock fixed
from that film's narration and its score and cues kept. Checked with two routes made from place names: a
bike loop from the Golden Gate Bridge to Hawk Hill (imperial) and a run in Lviv (metric, no climb to speak
of), each with its own content.
