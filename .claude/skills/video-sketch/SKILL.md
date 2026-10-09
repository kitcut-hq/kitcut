---
name: video-sketch
description: Make an animated explainer film with no footage — a hand-drawn/whimsical, a clean editorial, or a mixed-media paper-collage animation (cut-out pictures from an image model animated with type, tape labels, rubber stamps and torn paper, the "newspaper cutout" motion-design look) written as JavaScript, with an AI voice-over, an original score on sampled instruments and synthesised sound effects, rendered to MP4 and to a self-contained HTML player. It also makes real people talk from their photos -- bobble-heads, puppet cut-outs, a newspaper photo or a painting where only the mouth moves -- each with their own voice. Use when asked for an animation, an animated explainer or promo, a motion-graphics or motion-design video, a "whimsical hand-drawn" video, a collage / mixed-media / cut-out / scrapbook / newspaper-style video, a product or feature explainer, a 30-60 second ad, talking heads or bobble-heads made from photos, or anything that should be illustrated rather than filmed. Also for a square or vertical social promo in 3D motion-design style with real people in it -- a conference speaker announcement, a line-up, an event teaser with a speaker carousel, a ticket and a poster, music only, no narration.
---

# A sketch film: an explainer written as code

```powershell
# from the repo root, after copying config/sketch/example/ to projects/<id>/
python scripts/sketch-vo.py     --manifest projects/<id>/sketch.json --plan
python scripts/sketch-vo.py     --manifest projects/<id>/sketch.json
python scripts/sketch-render.py --manifest projects/<id>/sketch.json --stills 2,9,17,31 --sheet
python scripts/sketch-render.py --manifest projects/<id>/sketch.json --preview   # play it, narration + captions, before any music or render
python scripts/sketch-audio.py  --manifest projects/<id>/sketch.json --levels
python scripts/sketch-render.py --manifest projects/<id>/sketch.json
python scripts/sketch-render.py --manifest projects/<id>/sketch.json --timings
```

`docs/reference.md` has the reference under "Sketch films". The engine is `sketch/engine.js`,
the cast `sketch/props.js`, the kit `sketch/kit.js` (text, charts, screens, logos, end
cards, page transitions, cues -- every look; its header is the API, `config/sketch/kit-example/`
shows every piece), the collage pieces `sketch/collage.js`, the page
`sketch/player.html`. Finished examples: the committed `config/sketch/example/` (crayon), a
real brand film (clean, 60 s, real estate) described in the reference, and the committed
`config/sketch/collage-example/` (collage, 66 s: 17 cut-outs, ten sheets, stamps, a timeline
ruler, `score.py` and `sfx.py` beside it). Copy an example into `projects/<id>/` to start.

## The project folder comes first

`python scripts/project-scan.py --init <id>`, then copy `config/sketch/example/*` in and
edit. Read `projects/<id>/journal.md` before re-deciding anything; end with a note in it.

## Order of work

1. **Facts before words.** A promo makes claims. Find each claim's source (the product's own
   pages, its docs, its videos) and keep them in the manifest's `_sources`. Check the brand's
   own rules (a `PRODUCT.md`/`DESIGN.md` in its repo): named customers, certifications and
   benchmarks are the usual things a brand forbids unless approved. Leave out anything you
   cannot source; say so in the report.
2. **Brand before design.** Use the brand's real logo file (`"images": {"logo": ...}` →
   `SK.image('logo', ...)`), its colours and its typefaces (woff2 in `fonts/`). Pick the look
   for the audience: `crayon` is whimsical; `clean` is editorial (agents, finance, B2B);
   `collage` is mixed media -- real pictures cut out of paper and animated as motion design
   (history, explainers, anything with things to show). See "A collage film" below.
3. **Script.** About 1.7 words per second of film (lead, gaps and pauses included): 30 s is ~50
   words, 60 s ~100. That is measured: at the old 2.2 a second, 53 of 71 studio first takes ran
   past the film's end (studio/harvest.py, 2026-10-01). One idea per line.
   `sketch-vo.py --plan` prints the layout and the credit cost; nothing is spent.
4. **Voice.** `sketch-vo.py`. Read the take table it prints. Accuracy already forgives numbers
   heard as digits ("1986" for "nineteen eighty-six") and names in another spelling (`accuracy()`:
   33 of 78 studio lines it used to flag were those); what still scores low is a real misread,
   words the voice added, or its direction read aloud; `HARD-CUT` means no silence was found before
   the tail word — pick another take with `"pick"` on the line. Put brand names in `hotwords`.
   A long script: `--jobs 8` records eight takes at once (70 Gemini lines: 341 s -> 52 s).
5. **Picture.** Write `film.js` scene by scene, every cue on a word -- all of them at the top with
   `const T = SK.cues({snap: [2, 'snap'], end: [5, null, 'e']})` (a miss warns instead of hiding
   behind a fallback second). Reach for the kit before drawing text furniture, a chart, a screen,
   a logo or an end card; draw by hand only what is the film's own. A long
   film can be a file per scene instead -- `"scenes": "scenes"` in the manifest, film.js the
   shared look with no `draw`, `scenes/NN-slug.js` each an `SK.scene({id, lines, draw})`
   (docs/reference.md, "A film in scenes").
   Lay scenes out in world space and move the camera between them (`SK.camera` keys with
   easing); keep each scene's content inside ±900 x ±500 of its centre at zoom 1.
   For a painted film, `sketch-paint.py` makes the pictures from the manifest's `paint` block
   (one style line, one prompt per scene, `ref` to keep a character across scenes on a model
   that takes references). Look at `images/sheet.jpg` before animating. To choose or change
   the image model, run `paint-compare.py` on a few real scenes and judge the sheets. Its
   `--plan` prices the run, but it cannot see an OpenRouter account's allowed-providers
   setting, so paint one scene per model first.
6. **Review with stills, not guesses.** `--stills` at the moments that matter (each cue, each
   transition midpoint) with `--sheet`, then look at the sheet. Fix, re-still, repeat. A round
   of 18 stills costs ~9 s. Check text overlaps, off-frame content, elements hidden behind
   later-drawn ones (draw order is paint order), and emotional reads (a "sad" brow drawn the
   wrong way reads as angry). **Stills at chosen moments miss what breaks inside a second**
   (a character through a wall, flipped through a sliver, in two places at once): before a
   film is called done, `python studio/review.py --folder projects/<id>` lays the whole of
   it out a frame a second (`outputs/review/film-NN.jpg`), reads the drawing code for those
   moments and has a fresh Claude read both; `--machine` is the free half. A body goes into
   a thing through its opening, whole; it turns with a hop or a pose change, never by
   scaling through flat.
7. **Sound.** Write `score.json` (tempo chosen so bar lines land on the story beats — compute
   `bar = 240 / bpm` and line the scene changes up) and `sfx.json` (a cue on every visual hit).
   `sketch-audio.py --levels`: the voice should sit 8-12 dB over the heard music. Every volume
   in a score (`vel`, `v0`/`v1`, `drum_gain`, `"swell": [g0, g1]`) is a gain from 0 to 1.5,
   never a time -- a swell written as beats, `[24, 30]`, played the strings 28 dB too loud and
   is now refused. The voice gate holds the music 8 dB under the voice anyway; if the run says
   it pulled the music down, lower the score there instead of relying on it.
8. **Render**, then check the MP4 itself: duration, loudness (-14 LUFS), a few decoded frames.
   The render draws `--jobs` chunks at once (default: a quarter of the logical cores), 3x the
   old serial speed on a 60 s film. On a machine other sessions are loading, lower `--jobs`
   rather than let every browser crawl; `--jobs 1` is the old serial path.
   `--encode browser` has each page encode its own frames on the GPU instead of posting raw
   pixels to ffmpeg: 4x on the 8-minute studio film (2,218 s -> 536 s of frames), quality at
   least as good at the same `cq`, but a bigger master on grainy films. The studio renders
   this way; the script's default is still the pipe. It falls back to ffmpeg by itself where the browser cannot encode.
9. **Publish** with `yt-upload.py --channel <handle>` — unlisted unless told otherwise. For a
   thumbnail, make four from the film itself: `python studio/ytdraft.py --film <folder>
   --thumbs` (Claude picks the moments, the words and -- for a film with pictures -- which of
   them each is built on, the first the video's main message; ~$0.06) or
   `python scripts/thumb-options.py --film <folder> --concepts c.json [--logo all|none]` (add `--title "..." --title-box all` for the video's title in a box on a whole frame, the look kitcut.ai offers as options 1 and 2) (your
   own), then look at `feed.jpg` -- the options at YouTube's feed sizes -- and pass the one you
   pick to `yt-upload.py --thumbnail`. A film with pictures (cut-outs, photographs) gets posters
   composed from them: one large on the film's own page (somebody from the waist up, an object
   whole), another tucked behind it, the message beside or above in the film's title type and
   outline or on its label strips, the template varied by the film and the option. A film that
   draws everything itself gets frames of it: its own titles and labels left out, its subject
   pushed in on one side, the message large on the other. Its logo on options 1 and 3. Every
   option has passed the checks (legible at 168 px, contrast, clear of the duration stamp). So
   give the film's titles to `SK.txt` / `SK.headline` (an outline on them carries into the
   thumbnail), its labels to `SK.tape`, its pictures to `SK.image` / `SK.cutout` (they are what
   a poster is made of, so paint a character as "full figure, standing" and it is shown from
   the waist up; lay a page down with `SK.sheet` and the poster stands on it), and its logo a
   name with `logo` in it -- the thumbnail finds them all.
10. **Report the timings** (`--timings`) with the deliverables.

## A collage film (mixed media, paper cut-out, "newspaper" motion design)

The look of the Runway + Opus 5.5 demos: every picture is one object cut out of paper (an
engraving, a product photo), pinned onto coloured sheets with torn edges, and the motion design
is everything around it -- display type, tape labels, rubber stamps, marker arrows, ransom
letters, halftone dots, a running timeline. `SK.setStyle('collage')` plus `sketch/collage.js`,
an engine module the manifest opts into with `"modules": ["collage"]`:

1. **Cut-outs** come from the manifest's `paint` block with `"cutout": true` on each image
   (`"aspect": "2:3"` for a tall one). The block's `"cutouts": {"model", "quality", "border",
   "cut"}` default to `openai/gpt-image-2.5-flare`, which paints on a real transparent
   background (~$0.011-0.014, ~15 s, 4 at once); a model with no alpha is asked for a white
   ground and keyed off it. Each becomes `images/<name>.webp` with a white scissor-cut paper
   border; the sheet shows them on blue so a bad edge shows. Write each prompt as the medium
   plus the thing: "A 19th-century steel engraving of ..." or "Studio product photograph of
   ...". A model sometimes paints a paper shape behind an engraving (the barley did): repaint
   with "drawn alone with nothing behind it".
2. **Fonts** are the print faces in `fonts/` (see `fonts/SOURCES.md`): Abril Fatface
   (headlines), UnifrakturMaguntia (mastheads), Oswald (labels), Old Standard TT (body,
   datelines), Playfair Display (italic kickers), Courier Prime (typewriter), Anton, Caveat
   (handwriting). Only Oswald, Old Standard TT and Playfair Display carry Cyrillic.
3. **Pieces**: `SK.sheet` (a page; torn `edges`), `SK.cutout`, `SK.tape` (labels, banners, a
   big title on a strip), `SK.headline` (`distress` for letterpress), `SK.stamp` (`t:` its
   hit), `SK.burst`/`SK.disc`, `SK.halftone`, `SK.ransom`, `SK.mark`/`SK.arrow` (drawn on),
   `SK.maskingTape`, `SK.newsprint` (call first), `SK.rules`. Every piece takes `in`/`out`
   specs `{t, type, d, from}`: pop, grow, drop, slap, thump, slide, wipe, rise, fade.
4. **One scene = one sheet** inside `SK.layer({in: {t, type: 'slide', from}, steps: 0})`, so
   the sheet and everything on it slide in together, over the scene before. A card with words
   on it is its own `SK.layer({nudge: 1})` with `nudge: 0` on what is written on it.
5. **Pages arrive composed**: the chapter label, title and main picture ride in on the sheet;
   only the details land later, each on the word that names it. Start a sheet 0.15 s before
   its line; a payoff on the line's last word then still has ~0.8 s before the next sheet.
6. **The stop-motion feel is automatic**: the style nudges every piece a pixel or so 12 times
   a second, steps entrances on twos and grains the frame at 12 fps. Render at 24 fps.
7. Cue the sound from the timeline with `sfx.py` beside the manifest (a whoosh and a paper
   landing per sheet, a thunk per stamp, a pop per pop, keys for typing, a scribble per marker
   line) and write the score from a chord chart with `score.py`; see `config/sketch/collage-example/`.

## Talking heads: people from their photos

When the film should show real people speaking -- founders, a team, a customer, a historical
figure -- and you have their photos, make them talk instead of drawing stand-ins
(`docs/reference.md`, "Talking heads"). Start from `config/sketch/heads-example/`.

1. Put each photo in `sources/` and name it in the manifest: `"heads": {"alex": {"photo":
   "sources/alex.jpg"}}`. `head-rig.py --manifest ... --sheet` builds the rigs; look at each
   `rigs/<name>/sheet.png` (the cut-out on a check board, the jaw pieces, the mesh) before using
   one. A photo with the top of the head cropped off makes a flat-topped cut-out: use it as a
   `photo`, not a `cutout` or `bobble`.
2. Give each speaker a voice in `vo.cast` and each line its `who`; a line without one is the
   narrator. Pick voices that are told apart at once (one low, one high).
   **Drawn characters are the default choice** (the owner found a photo that talks, and every
   photoreal model, cringe): add `"look": "brick" | "blocky" | "newspaper" | "caricature" |
   "clay"` to a head and the person is redrawn in that look from their photo, with their own
   mouth shapes and a blink (~$0.11 a person, cached; `head-rig.py --list` prices it; the photo
   goes to the image model). If the model refuses a photo, try another look or photo.
3. In film.js, `SK.head(name, x, y, h, {style, mouth, tone})`: `photo` + `warp` for "only the
   mouth moves" (a newspaper photo with `tone: 'news'`, a portrait in a frame); `cutout` or
   `bobble` + `chin`/`dummy`/`flap` for the puppet looks. Lay heads out with `SK.headBox`; a
   head's mouth moves only on its own lines (`who`), so two heads can share a frame.
4. Review stills at mid-word moments of each speaker, and zoom on a mouth: the teeth, the jaw
   piece's edges, the halftone. Check frame 0 as always.

Whose face it is, and whether they agreed to be animated saying these words, is the user's
call: ask before putting words in a real person's mouth unless the user is that person or
has said so.

## A motion-design promo (square, 3D pieces, real people, music only)

The worked example is `projects/websummit-speakers/` (local; docs/reference.md "Motion-design
films"): a 26 s 1080x1080 speaker promo for a conference, rebuilt from another designer's After
Effects piece in the conference's own look. What it takes:

1. **Measure the reference, then leave it.** Download it (X: `api.fxtwitter.com/<user>/status/<id>`
   gives the MP4 URLs; `/2/conversation/<id>` the replies, where authors post their prompts), tile
   its frames at 2-4 fps, and write down its beats and their timings. Keep the beats; take nothing
   of its artwork, colours, type or people. Find an idea of your own for the same beats (Lisbon ->
   a trip: tiles, a departures board, a paper plane, a boarding pass).
2. **The event's own facts and look.** Speakers, titles, dates, venue, tagline and button copy from
   the event's pages (quote them in `_sources`), its logo file, its colours measured off the logo,
   and its typeface -- or the nearest open one when it is licensed (`fonts/SOURCES.md`).
3. **People**: `scripts/portrait-cutout.py --frame --tone mono` (local BiRefNet; `--plan` first),
   then `"images": {"sp-<id>": "images/speakers/<id>.webp"}`, drawn inside a circle clip.
4. **The frame**: `"frame": [1920, 1080]` for YouTube (the default the user wants), `[1080, 1080]` for
   a feed. Lay everything out from `SK.W`/`SK.H` (`CX`, a `WIDE` flag for layouts that differ) so one
   film renders both, and put the 2D camera on the frame's middle so world units are pixels.
   Pick people by checking who they are: never feature Russian public figures, even when the
   event's own line-up does.
5. **3D**: `"modules": ["space"]`. `SK.view3` then `SK.face3`/`SK.box3`/`SK.poly3`; give a low
   piece its own view with `sx`/`sy` so the camera looks at it level; `SK.fx` for blur and whips.
6. **Sound without a voice, written by the film**: leave out `vo`; give `SK.film` a
   `sound: {score(), sfx()}` that works the score (a chord chart; hits on the beats the picture lands
   on) and every cue out of the film's own clock and content, then `sketch-render.py --sound-data`
   writes score.json and sfx.json. Never copy timings into a script beside the film: they drift. A
   sound that repeats at one level and pan is one cue with `times` (the studio allows 200 cues).
   Compare the mix's band balance with the reference's soundtrack; keep the noise drums (snare,
   clap, hats) well back and put `sub_bass` under the bass.
7. **Content in data, when the film could be a template**: `"data": {"content": "content.json"}`
   makes the file `SK.DATA.content`; keep every word, colour, logo and person there and none in the
   code, work shades out of three brand colours, and never let the content move the clock (a fixed
   number of carousel stops; repeat people when there are few). Prove it: stills at 60 moments
   before and after must match, and a made-up event must render without a broken frame.
8. **Render** `--encode browser --web`: the master and a ~8 Mbps copy to post.

Check the whip, the turns and every transition frame by frame from a `--draft` render
(`ffmpeg ... -vf "fps=30,scale=216:216,tile=6x5"`), not only from stills: an empty frame between two
scenes only shows in motion.

## A YouTube Short (9:16, the words in the picture)

A narrated film for a phone feed: `"frame": [1080, 1920]`, `"fps": 30` and `"modules": [...,
"captions"]` in the manifest. `sketch/captions.js` draws the narration a card at a time from the
voice timeline -- white on a dark card, the word being said in yellow -- so the words are in the
pixels: YouTube shows no subtitle track on a Short. On kitcut.ai it is one flag, `npm run film --
make ... --short` (the studio's `"frame": "9:16", "captions": true`), and the film's first message
tells its writer the canvas and what is taken.

**`docs/shorts-guidebook.md` is the rulebook: read it before writing a Short's prompt and hold the
finished file to it.** Thirty-three rules, each checkable, each with what it rests on (YouTube's own
statements, 25 high-view Shorts measured, and the owner's calls). The ones that cost a day when
they were missed:

- **The news is the first frame and the first sentence.** A headline of eight words or fewer on
  frame 0, the voice inside 0.3 s, the first sentence saying who did what. Never a clue first.
- **A news Short is a bulletin** (strap, headline, a lower band naming the source on screen), with
  **real screenshots of the source sites' own headlines**, masthead to date, one page at a time.
- **No music** (`--no-music`), and a narrator who is fast and confident but steady: neither a flat
  anchor nor an alarmed one. The owner picks the voice by ear from an audition page.
- **A 20-second pilot before a batch** in a new format; the batch after the owner's yes.
- **Nothing stands still.** A diagram a wide film would hold is moved in a Short: the camera
  follows the action, a picture is studied part by part on the narrator's words, a number counts
  up. Run `python scripts/short-stillness.py <mp4> --check` on the finished file before showing
  it: over 5% of the time frozen, or a drift longer than 3 s with nothing moving, fails. A Short
  cut from a wide film fails it by default (49 to 65% frozen on the first five), so each scene is
  laid out again for the tall frame, not scaled into it.

The studio does its part for a 9:16 film: the first word 0.1 s in, and the film's own frame 0 as
the video's first frame (`"cover": false`). By hand, set both: `"lead": 0.1` in `vo.json` and
`"cover": false` in the manifest; for no music, `"audio": {"music": false}`.

- **Compose for the tall frame**, never a wide layout shrunk into it: stacked top to bottom, one
  idea on screen at a time, a headline of 90 px or more, nothing to be read under 44.
- **Three things lie over the film.** The caption band (`SK.captionBox()`: about y 1330-1530 of
  1920); below it the phone's title and channel name (the bottom fifth); and the like/comment/share
  column down the right of the lower half. The picture runs under all three; nothing that must be
  read goes there. A thing that moves (a hand that presses a button low in the frame) wanders in:
  bring it in from the side.
- **The first frame is the hook**, on screen at 0.0 s. A feed shows that frame before anything
  plays.
- **No thumbnail.** The thumbnail options are 1280x720 posters and come out cropped on a tall
  film, so the studio makes none (`thumbs.wide`); YouTube shows a Short by a frame of its own.
  The film's cover on kitcut.ai is a frame of it: `ops.sh share <id> --frame 0.3`.
- **Check the words against the source, not against the prompt.** Two of the first five Shorts
  (2026-10-08) said what the prompt had invented: a list item the policy never names, and "the
  reason" for a rule whose announcement gives none. Open the primary source once more with the
  finished narration beside it; a line that is wrong is re-recorded by itself (studio-vm skill,
  "Reworking a finished film by hand").

## A pin, an address, "find us here": the real map

A film that shows where a real place is draws the real map of it -- never a made-up street plan.

1. Price it: `python scripts/place-map.py --at "<the address as written, with its town>" --list` says
   what it matched and **how exactly** (`house`, `block`, `street`, `place`), and what is there. When
   only the street is known the pin marks the street: letter it, point at no house, and say "on
   <street>" in the narration. A street on no map is refused (`no map:`): show the address in type.
2. Make it into the film: `--film spec.json --out-image <film>/images/place_map.jpg --out-data
   <film>/place.json` (spec: `at`, and `tint` = the film's main colour, or `tone: "dark"`), then add
   `"place_map": "images/place_map.jpg"` to the manifest's `images` and `"place": "place.json"` to its
   `data`. On kitcut.ai the studio's `map` tool does both.
3. Draw it with the kit: `const m = SK.map(x, y, {s, own: {col, p}, names, clear: [[card box]]})`
   puts the address at (x, y) and letters the real street names; `SK.mapPin(x, y, {t})` drops the
   pin. Keep `s >= m.cover` or the map's edge shows. `© OpenStreetMap` must show (SK.map letters it).
4. Look at a still of every frame the film is made in: the pin off-centre plus a card over the map
   is the usual layout, and a name half under the card is why `clear` exists.

`docs/reference.md`, "A real map of a real address". The open house template
(`config/templates/open-house-invitation/`) is the worked example, with its no-map fallback.

## A ride or a route on a real map (a cycling-app replay)

The studio's Claude cannot fetch a map or a route, so make both here and attach them:

1. Get the route as data, best a GPX of a real ride (it carries elevation and a clock); else OSM
   way ids in order, or a bike-router leg. Trim a GPX to where the event really starts and ends
   (`from_near`/`to_near` + `start_at`/`end_at` pins): a recording usually starts at someone's door.
2. Write `projects/<id>/route-map.json` (ONE map at a fractional zoom under 40 MP -- two maps of
   different zooms showed a seam in the film; `uploads` naming which `uploadN` it will be, `marks` for the gates and summits, `places` to label), price it with
   `--list` (keep rows under ~12k characters: the film copies them), render, and **look at
   `preview.jpg`** -- the line must sit on the roads and the sea must be sea.
3. Attach the map first (so it is `upload1`), logos and a QR after, then `route.md`
   and a facts sheet; the prompt says to copy the rows and never redraw the line, to keep the camera inside the map
   while it follows the dot, to keep the map, line, dot and numbers crisp (no collage nudge), to drive the dot by the ride's own clock, and to
   credit OSM. `docs/reference.md` "A real map and a real route" has the details.

## Harvest: turn what films keep re-inventing into kit pieces

Every few days of studio films, read them back -- this is how `sketch/kit.js` was found, and the
step that had stopped happening:

1. `python studio/harvest.py --pull --since <date>` then `--report temp/harvest/<date>`: where
   Claude's time went (by reply: first write of the picture, fixes, narration, sound...), the
   tools' errors grouped, helpers re-written across unrelated prompts, and how much the kit is used.
2. `--timelines` and `--pace --write` (each voice's real words a second, for the word budget).
3. The reading pass: split the films (one per distinct prompt) into batches of ~250k characters
   and give each to an agent with `studio/harvest/inventory.md`; the timelines, in three batches,
   with `studio/harvest/process.md`. Merge their JSON; rank components by how many unrelated films
   built one.
4. Add the top ones to `sketch/kit.js` (header first: it is the API Claude reads), show each in
   `config/sketch/kit-example/film.js`, run `python scripts/check-kit.py --sheet` and look at the
   sheet in both looks.
5. Prove it before it ships: `studio/bakeoff.py` with `studio/bakeoff/kit.json` (or a new set),
   one arm at the released commit and one at the change; compare Claude's time, recordings and the
   blind grade (`--grade`, `--compare`). Then release.

## Traps already paid for

- **A 3D face drawn as clipped triangles shows its seams** -- a hatch of hairlines on every flat
  colour. space.js draws overlapping unclipped cells instead; keep it that way.
- **A face seen at a slant squashes its type**: a name block's side at ~30 degrees halves its
  width. Draw that face's words wide (`c.scale(1.55, 1)`) so they read as normal.
- **Magenta on magenta**: a mascot in the brand colour disappears on a ground of the same colour --
  the first paper plane did. Paper is paper-coloured.
- **An effect level set by RMS alone lies**: set each cue by its level over the music at its moment
  (the stems: `sketch-audio.py --stems`), impacts at or above the music, secondary cues a few dB
  under.
- **Never open on a blank page.** A fade in from paper, or a draw-on that starts at zero,
  reads as empty frames at the head of the film. The engine no longer fades in by default;
  start the first draw-ons around 20% (`clamp(.2 + .8 * E.out(...))`) so frame 0 already
  shows the pen at work. Check frame 0 in the stills every time. (The video file's own frame 0
  is the film's cover -- the poster, or a livelier moment -- because X and a phone show it
  before play; `sketch-render.py` draws it, manifest `cover` overrides. That does not excuse
  a blank opening: frame 1 is what plays.)
- `-shortest` with a subtitle track shortens the film to the last caption. `sketch-render.py`
  muxes with `-t`; do the same in any hand-run mux.
- `eleven_v3` clips final syllables: always go through `sketch-vo.py` (tail word + cut).
- **A studio film may have its narrator chosen for it** (kitcut.ai's voice picker): `vo.json`'s
  voice is then pinned (`Film.vo_pins()`, put back by `guard.pin_vo` after every edit), and only
  `style` and `language` are Claude's. In a person's own ElevenLabs voice, every line goes through
  the site's relay (`ELEVENLABS_RELAY` + the film's grant), is paid from their characters, and a
  refusal from their account ends `sketch-vo.py` with `VOICE-BLOCKED` and exit 75: the film waits
  for them rather than failing (`docs/reference.md`, "Workspaces, and the narrator a person
  picks"). By hand, with no relay set, `sketch-vo.py` works as before.
- The props draw at a fixed design size and scale uniformly (`P.house` at `w` = 104 is a
  thumbnail of the same house); if a new prop has hard-coded sizes inside, give it the same
  scale treatment before using it small.
- Every frame must be a pure function of `t`; any state kept between frames breaks the
  exported video while looking fine in the browser.
- **A film in another language** needs four things, or it fails silently: `vo.language`
  (e.g. `"uk"`), a `tail` in that language (`"Добре."`), fonts that carry the script (the
  committed woff2 files are Latin subsets -- use the full `.ttf` in `fonts/`), and cue words
  written exactly as spoken (`SK.w(3, "збиті")`). Pick the voice by measurement: one test line
  per candidate, Whisper large-v3 with no language forced, highest language confidence wins
  (Ukrainian: `lily`). Budget ~1.8 words/s, not 2.6 -- `--plan` overestimates a Ukrainian
  line's speed.
- **A line Gemini refuses** (its content filter: a name, a wine) is read by the backup
  voice when `vo.backup` is set -- ElevenLabs, a low or high voice chosen by the film's own
  measured pitch -- and the timeline marks it `backup_voice`. It sounds a little different;
  rewording the line and recording again brings it back to Gemini. Without `vo.backup` the
  run stops and asks for a rephrase, as before.
- **Films for children** (the air-raid-kids film): no explosions, fire or injury on screen --
  a shoot-down is a puff, danger is a grey silhouette -- and every scene ends on the child
  doing the safe thing. Use the official wording of the safety authority verbatim where it
  exists (ДСНС: «Стій! Не чіпай! Телефонуй 101!») and list what was left out in `_sources`.
- Cue sound effects from the voice timeline with a small `sfx_gen.py` beside the manifest
  (see `projects/air-raid-kids/`), not with hand-copied seconds: a retake moves them too.
- **Gemini reads slower than `--plan` thinks.** The collage film's 140-word script planned at
  58 s and came back at 72 s (Charon, a documentary direction); "brisk" in the style barely
  moved it. Budget ~1.9 words a second for Gemini narration and cut words, not the pace note.
- **A sheet that overshoots bares the page under it.** Slides land with no bounce; keep the
  overshoot for things that drop onto a page.
- **A payoff on a line's last word gets covered** by the next sheet unless the next sheet waits
  (see 5 above); move the big reveal to an earlier word ("one form into three": fan on "one").
- **A `//` comment inside a one-line object** swallows its closing brackets; the render then
  fails in every chunk with "Unexpected end of input". `node --check film.js` catches it in a
  second.
