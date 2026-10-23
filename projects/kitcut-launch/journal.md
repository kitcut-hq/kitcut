# kitcut-launch -- edit journal
AI notes for future sessions. Scripts append the `- HH:MM` event lines;
after each editing session, append a short prose note: what was asked,
which knob changed, why, and anything the next session should not rediscover.

## 2026-10-23
- 04:39 project created
- 05:12 showreel drive raw cut rendered (0:32.00, 8 acts, 120 bpm) scripts/showreel.py -> projects/kitcut-launch/outputs/kitcut-launch-drive-raw.mp4 (--manifest projects/kitcut-launch/showreel.json --option drive --raw -j 6) -- option drive: music config/showreel/music/drive.json, solo transitions cut
- 05:15 showreel pop raw cut rendered (0:30.97, 8 acts, 124 bpm) scripts/showreel.py -> projects/kitcut-launch/outputs/kitcut-launch-pop-raw.mp4 (--manifest projects/kitcut-launch/showreel.json --option pop --raw -j 6) -- option pop: music config/showreel/music/pop.json, solo transitions whip
- 05:18 showreel cinema raw cut rendered (0:38.40, 8 acts, 100 bpm) scripts/showreel.py -> projects/kitcut-launch/outputs/kitcut-launch-cinema-raw.mp4 (--manifest projects/kitcut-launch/showreel.json --option cinema --raw -j 6) -- option cinema: music config/showreel/music/cinema.json, solo transitions zoom
- 05:20 showreel drive raw cut rendered (0:32.00, 8 acts, 120 bpm) scripts/showreel.py -> projects/kitcut-launch/outputs/kitcut-launch-drive-raw.mp4 (--manifest projects/kitcut-launch/showreel.json --option drive --raw) -- option drive: music config/showreel/music/drive.json, solo transitions cut
- 05:21 showreel drive raw cut rendered (0:32.00, 8 acts, 120 bpm) scripts/showreel.py -> projects/kitcut-launch/outputs/kitcut-launch-drive-raw.mp4 (--manifest projects/kitcut-launch/showreel.json --option drive --raw) -- option drive: music config/showreel/music/drive.json, solo transitions cut
- 05:22 showreel pop raw cut rendered (0:30.97, 8 acts, 124 bpm) scripts/showreel.py -> projects/kitcut-launch/outputs/kitcut-launch-pop-raw.mp4 (--manifest projects/kitcut-launch/showreel.json --option pop --raw) -- option pop: music config/showreel/music/pop.json, solo transitions whip
- 05:23 showreel cinema raw cut rendered (0:38.40, 8 acts, 100 bpm) scripts/showreel.py -> projects/kitcut-launch/outputs/kitcut-launch-cinema-raw.mp4 (--manifest projects/kitcut-launch/showreel.json --option cinema --raw) -- option cinema: music config/showreel/music/cinema.json, solo transitions zoom
- 05:25 showreel drive raw cut rendered (0:32.00, 8 acts, 120 bpm) scripts/showreel.py -> projects/kitcut-launch/outputs/kitcut-launch-drive-raw.mp4 (--manifest projects/kitcut-launch/showreel.json --option drive --raw) -- option drive: music config/showreel/music/drive.json, solo transitions cut
- 05:26 showreel pop raw cut rendered (0:30.97, 8 acts, 124 bpm) scripts/showreel.py -> projects/kitcut-launch/outputs/kitcut-launch-pop-raw.mp4 (--manifest projects/kitcut-launch/showreel.json --option pop --raw) -- option pop: music config/showreel/music/pop.json, solo transitions whip
- 05:27 showreel cinema raw cut rendered (0:38.40, 8 acts, 100 bpm) scripts/showreel.py -> projects/kitcut-launch/outputs/kitcut-launch-cinema-raw.mp4 (--manifest projects/kitcut-launch/showreel.json --option cinema --raw) -- option cinema: music config/showreel/music/cinema.json, solo transitions zoom
- 05:28 showreel drive raw cut rendered (0:32.00, 8 acts, 120 bpm) scripts/showreel.py -> projects/kitcut-launch/outputs/kitcut-launch-drive-raw.mp4 (--manifest projects/kitcut-launch/showreel.json --option drive --raw) -- option drive: music config/showreel/music/drive.json, solo transitions cut
- 05:29 showreel pop raw cut rendered (0:30.97, 8 acts, 124 bpm) scripts/showreel.py -> projects/kitcut-launch/outputs/kitcut-launch-pop-raw.mp4 (--manifest projects/kitcut-launch/showreel.json --option pop --raw) -- option pop: music config/showreel/music/pop.json, solo transitions whip
- 05:30 showreel cinema raw cut rendered (0:38.40, 8 acts, 100 bpm) scripts/showreel.py -> projects/kitcut-launch/outputs/kitcut-launch-cinema-raw.mp4 (--manifest projects/kitcut-launch/showreel.json --option cinema --raw) -- option cinema: music config/showreel/music/cinema.json, solo transitions zoom

## 2026-10-22 — the launch reel, three raw options

Asked: a launch video for Product Hunt, X and Reddit showing the kinds of films KitCut makes —
four films one at a time with a short comment each (three.js among them), then grids of 4, 8,
16 all playing, about a minute, professional cuts, music on the rhythm, a few options as short
raw cuts.

Picked 16 of the owner's 864 finished films (48 surveyed by contact sheet) for range of look
and use: padel lesson in three.js (opens the reel), Leo kids' series (crayon), Apollo 13
(painted documentary), Web Summit speaker promo; then The Box (collage history), Cloudflare
(charts), the wooden-toy heist (vertical drama, shown whole on a blurred bed), the open house
on a real map; then Stripe/OpenRouter (collage research), Ocheretyne economics (Ukrainian),
the dragon bedtime story, Duchess, the PGConf metro-map agenda, masala chai (Hindi), Marisol
(painted restaurant promo), the Pedal & Network ride map. Ids are in `showreel.json`.

Built `scripts/showreel.py` for it (tooling, generic): beats-based acts, the music arranged
from the same acts. Three options, each a 31-38 s raw cut at 960x540: drive (electronic,
hard cuts with a punch-in), pop (marimba/glockenspiel, whip pans), cinema (orchestral, zoom
dissolves). The full cut (~58 s drive, ~56 s pop, ~70 s cinema at 1080p) waits for the
owner's pick. Captions are mine: change any line in `clips.<key>.caption`.
- 05:34 showreel drive raw cut rendered (0:32.00, 8 acts, 120 bpm) scripts/showreel.py -> projects/kitcut-launch/outputs/kitcut-launch-drive-raw.mp4 (--manifest projects/kitcut-launch/showreel.json --option drive --raw -j 6) -- option drive: music config/showreel/music/drive.json, solo transitions cut
- 05:35 showreel pop raw cut rendered (0:30.97, 8 acts, 124 bpm) scripts/showreel.py -> projects/kitcut-launch/outputs/kitcut-launch-pop-raw.mp4 (--manifest projects/kitcut-launch/showreel.json --option pop --raw -j 6) -- option pop: music config/showreel/music/pop.json, solo transitions whip
- 05:36 showreel cinema raw cut rendered (0:38.40, 8 acts, 100 bpm) scripts/showreel.py -> projects/kitcut-launch/outputs/kitcut-launch-cinema-raw.mp4 (--manifest projects/kitcut-launch/showreel.json --option cinema --raw -j 6) -- option cinema: music config/showreel/music/cinema.json, solo transitions zoom
- 05:37 showreel drive raw cut rendered (0:32.00, 8 acts, 120 bpm) scripts/showreel.py -> projects/kitcut-launch/outputs/kitcut-launch-drive-raw.mp4 (--manifest projects/kitcut-launch/showreel.json --option drive --raw) -- option drive: music config/showreel/music/drive.json, solo transitions cut
- 05:38 showreel pop raw cut rendered (0:30.97, 8 acts, 124 bpm) scripts/showreel.py -> projects/kitcut-launch/outputs/kitcut-launch-pop-raw.mp4 (--manifest projects/kitcut-launch/showreel.json --option pop --raw) -- option pop: music config/showreel/music/pop.json, solo transitions whip
- 05:39 showreel cinema raw cut rendered (0:38.40, 8 acts, 100 bpm) scripts/showreel.py -> projects/kitcut-launch/outputs/kitcut-launch-cinema-raw.mp4 (--manifest projects/kitcut-launch/showreel.json --option cinema --raw) -- option cinema: music config/showreel/music/cinema.json, solo transitions zoom
- 05:41 showreel drive raw cut rendered (0:32.00, 8 acts, 120 bpm) scripts/showreel.py -> projects/kitcut-launch/outputs/kitcut-launch-drive-raw.mp4 (--manifest projects/kitcut-launch/showreel.json --option drive --raw) -- option drive: music config/showreel/music/drive.json, solo transitions cut
- 05:42 showreel pop raw cut rendered (0:30.97, 8 acts, 124 bpm) scripts/showreel.py -> projects/kitcut-launch/outputs/kitcut-launch-pop-raw.mp4 (--manifest projects/kitcut-launch/showreel.json --option pop --raw) -- option pop: music config/showreel/music/pop.json, solo transitions whip
- 05:43 showreel cinema raw cut rendered (0:38.40, 8 acts, 100 bpm) scripts/showreel.py -> projects/kitcut-launch/outputs/kitcut-launch-cinema-raw.mp4 (--manifest projects/kitcut-launch/showreel.json --option cinema --raw) -- option cinema: music config/showreel/music/cinema.json, solo transitions zoom
