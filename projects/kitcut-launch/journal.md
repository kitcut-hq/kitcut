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
- 06:10 showreel drive raw cut rendered (0:32.00, 8 acts, 120 bpm) scripts/showreel.py -> projects/kitcut-launch/outputs/kitcut-launch-drive-raw.mp4 (--manifest projects/kitcut-launch/showreel.json --option drive --raw -j 6) -- option drive: music config/showreel/music/drive.json, solo transitions cut
- 06:11 showreel pop raw cut rendered (0:30.97, 8 acts, 124 bpm) scripts/showreel.py -> projects/kitcut-launch/outputs/kitcut-launch-pop-raw.mp4 (--manifest projects/kitcut-launch/showreel.json --option pop --raw -j 6) -- option pop: music config/showreel/music/pop.json, solo transitions whip
- 06:13 showreel cinema raw cut rendered (0:38.40, 8 acts, 100 bpm) scripts/showreel.py -> projects/kitcut-launch/outputs/kitcut-launch-cinema-raw.mp4 (--manifest projects/kitcut-launch/showreel.json --option cinema --raw -j 6) -- option cinema: music config/showreel/music/cinema.json, solo transitions zoom
- 06:16 showreel drive raw cut rendered (0:32.00, 8 acts, 120 bpm) scripts/showreel.py -> projects/kitcut-launch/outputs/kitcut-launch-drive-raw.mp4 (--manifest projects/kitcut-launch/showreel.json --option drive --raw) -- option drive: music config/showreel/music/drive.json, solo transitions cut
- 06:18 showreel pop raw cut rendered (0:30.97, 8 acts, 124 bpm) scripts/showreel.py -> projects/kitcut-launch/outputs/kitcut-launch-pop-raw.mp4 (--manifest projects/kitcut-launch/showreel.json --option pop --raw) -- option pop: music config/showreel/music/pop.json, solo transitions whip
- 06:19 showreel cinema raw cut rendered (0:38.40, 8 acts, 100 bpm) scripts/showreel.py -> projects/kitcut-launch/outputs/kitcut-launch-cinema-raw.mp4 (--manifest projects/kitcut-launch/showreel.json --option cinema --raw) -- option cinema: music config/showreel/music/cinema.json, solo transitions zoom

Owner's changes the same evening: no Marisol, a micro drama instead (Gate 23, watercolour, beside
the toy heist); no dragon, the "Peppa Pig" one instead (no Peppa film exists: used the pink-pig
toddler rhyme "Hop, Plop, Splash!", studio-20261021-014254-bmgktx, made by a CUSTOMER account,
public: confirm before launch); add the Yandex film with the X posts (from 1:23); more
Ocheretyne collage (the Pokemon booster mountain). 18 films: two 4x4 tiles now switch films on
a bar line halfway (showreel.py: a grid cell may be a list of clips).

The owner then said "skip Peppa": the rhyme (a customer's film) is out, the donuts maths film (studio-20261003-161908-i3lfpc, from 0:06) in. Full 1080p renders of all three options started on kc-local, no option picked yet.

Owner, later: the toy heist read as a kids' cartoon ("bad choice for drama ... not kids animation"), go easy on kids' cartoons, remove the donuts. Now: noir drama "Which Hand" (6cubej, from 0:34) for the heist; the XC bikes collage (i4d52n, 0:50) for the donuts; the Anthropic IPO Short (2xqki7, 0:41, tall) for Duchess. Kids' films left: Leo (solo), the two Ocheretyne economics tiles, masala chai. Re-rendered on kc-local.
- 16:50 showreel drive: music replaced under the same picture scripts/showreel.py -> projects/kitcut-launch/outputs/kitcut-launch-drive.mp4 (--manifest projects/kitcut-launch/showreel.json --option drive --remux)
- 16:50 showreel pop: music replaced under the same picture scripts/showreel.py -> projects/kitcut-launch/outputs/kitcut-launch-pop.mp4 (--manifest projects/kitcut-launch/showreel.json --option pop --remux)
- 16:51 showreel cinema: music replaced under the same picture scripts/showreel.py -> projects/kitcut-launch/outputs/kitcut-launch-cinema.mp4 (--manifest projects/kitcut-launch/showreel.json --option cinema --remux)
- 16:51 showreel drive: music replaced under the same picture scripts/showreel.py -> projects/kitcut-launch/outputs/kitcut-launch-drive.mp4 (--manifest projects/kitcut-launch/showreel.json --option drive --remux)

2026-10-23: the three full cuts came back from kc-local (drive 0:58, pop 0:56, cinema 1:10). Checked at 2 fps: picture fine. Sound: each closing chord stopped ~2.5 s before the end (3.1 s samples); fixed with re-struck chords and put under the same picture with --remux. Peaks after AAC: 0.77 / 0.83 / 0.90, nothing clipped.

2026-10-23, after three fresh reviews of the full cuts (drive SHOW IT, pop SHOW IT, cinema NOT YET) - fixed in all three: no black opening frames; end card 4 s with "One prompt in. A finished film out." large; first caption says Claude wrote it; Web Summit caption moved off its name plate; the noir drama is solo 2 (Leo becomes a tile: kids' cartoon no longer a headline); tall films fill their grid tiles (grid_fit cover) and sit right of centre in their solo (place_x). Piece cache key now includes the piece size.

Second review round (one fresh reviewer, all three): drive SHOW IT (would post it), pop SHOW IT, cinema NOT YET (grids too long). Fixed: Web Summit solo now starts on its speakers scene (caption top-left, clear of the name plate); the 3x3 logo tile says "One prompt in. / A finished film out."; cinema holds its grids 12 s and 17 s (option beats), now 1:00. Final renders on kc-local.
