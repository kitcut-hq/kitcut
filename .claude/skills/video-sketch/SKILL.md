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
python scripts/sketch-audio.py  --manifest projects/<id>/sketch.json --levels
python scripts/sketch-render.py --manifest projects/<id>/sketch.json
python scripts/sketch-render.py --manifest projects/<id>/sketch.json --timings
```

`docs/reference.md` has the reference under "Sketch films". The engine is `sketch/engine.js`,
the cast `sketch/props.js`, the collage pieces `sketch/collage.js`, the page
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
3. **Script.** About 2.6 words a second: 60 s is ~130 words, 40 s ~90. One idea per line.
   `sketch-vo.py --plan` prints the layout and the credit cost; nothing is spent.
4. **Voice.** `sketch-vo.py`. Read the take table it prints: accuracy under ~0.8 is usually
   numbers ("45" vs "forty-five"), not a bad take; `HARD-CUT` means no silence was found before
   the tail word — pick another take with `"pick"` on the line. Put brand names in `hotwords`.
   A long script: `--jobs 8` records eight takes at once (70 Gemini lines: 341 s -> 52 s).
5. **Picture.** Write `film.js` scene by scene, every cue on a word: `SK.w(line, "word")`. A long
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
   wrong way reads as angry).
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
   thumbnail, make four from the film's own frames: `python studio/ytdraft.py --film <folder>
   --thumbs` (Claude picks the moments and words, the first the video's main message; ~$0.06) or
   `python scripts/thumb-options.py --film <folder> --concepts c.json [--logo all|none]` (your
   own), then look at `feed.jpg` -- the options at YouTube's feed sizes -- and pass the one you
   pick to `yt-upload.py --thumbnail`. They are made the way YouTube thumbnails are: the film's
   own titles and labels left out of the frame, its subject pushed in on one side, the message
   large on the other in the film's title type and outline, its logo on options 1 and 3. Every
   option has passed the checks (legible at 168 px, contrast, clear of the duration stamp). So
   give the film's titles to `SK.txt` / `SK.headline` (an outline on them carries into the
   thumbnail), its labels to `SK.tape`, its pictures to `SK.image` / `SK.cutout` (their boxes
   are the subject), and its logo a name with `logo` in it -- the thumbnail finds them all.
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
4. **The frame**: `"frame": [1080, 1080]`; lay everything out in `SK.W`/`SK.H` and put the 2D
   camera on the frame's middle so world units are pixels.
5. **3D**: `"modules": ["space"]`. `SK.view3` then `SK.face3`/`SK.box3`/`SK.poly3`; give a low
   piece its own view with `sx`/`sy` so the camera looks at it level; `SK.fx` for blur and whips.
6. **Sound without a voice**: leave out `vo`; write `score.py` (a chord chart; hits on the beats the
   picture lands on) and `sfx.py` (every visual event, times copied from film.js by name). Compare
   the mix's band balance with the reference's soundtrack; keep the noise drums (snare, clap,
   hats) well back and put `sub_bass` under the bass.
7. **Render** `--encode browser --web`: the master and a ~8 Mbps copy to post.

Check the whip, the turns and every transition frame by frame from a `--draft` render
(`ffmpeg ... -vf "fps=30,scale=216:216,tile=6x5"`), not only from stills: an empty frame between two
scenes only shows in motion.

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
