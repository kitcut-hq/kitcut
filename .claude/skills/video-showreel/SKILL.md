---
name: video-showreel
description: Make a showreel (sizzle reel, montage, launch video, "what we made" video) out of finished films - films one at a time with a short caption each, then grids of 4, 8 and 16 playing at once, then a logo card, every cut on the beat of music arranged from the same timeline. Use when asked for a launch video, a showreel, a sizzle reel, a montage or grid of many videos, a "what you can make" or capabilities video, or a Product Hunt / X / Reddit video built from existing films.
---

# A showreel out of finished films

`scripts/showreel.py` + a manifest `projects/<id>/showreel.json`. Reference: `docs/reference.md`,
"A showreel out of finished films". Example: `projects/kitcut-launch/showreel.json`.

## Order of work

1. **Find the films first.** List the candidates (`node C:/instafill/sketch-studio/scripts/prod.mjs`
   for kitcut.ai films: `aggregate studio_runs` with `media.video`, `look`, `frame`, `share.title`).
   Pick for range on two axes at once: the LOOK (crayon, clean, collage, painted, 3D/three.js,
   real maps, real people's photos, tall 9:16) and the USE (a kids' series, a lesson, a
   documentary, an event promo, research with charts, a drama, an invitation, a brand, other
   languages). Prefer the owner's own films; someone else's public film needs their yes.
2. **Choose each moment by looking**: a 24-frame sheet per film, then a 4 fps strip of the
   window you like. The first shot opens the reel: it must move from frame 0.
3. **Write the manifest**: clips (`src`, `in`, `caption` [kicker, line] for the solo shots,
   `jump` per act, `fit: contain` for tall films), acts in beats, options (music style +
   solo transition), `raw` lengths. `--list` prices it: act times, the film windows played,
   wraps (add a `jump`), pieces to cut.
4. `--fetch`, then `--frame T` at each act before any encode.
5. **Options as raw cuts first** (`--raw`: short holds, 960x540, its own music) - one per
   option, sent together; the full 1080p cut waits for the owner's pick.
6. Look at every raw cut at 2 fps, measure the music's level per 2 s (it should build into
   the grids), check the decoded AAC for clipping, and have a fresh agent review it
   (`video-review`). Then send the full paths.

## Things that bit

- loudnorm flattens the build (its dynamic mode); the script masters with a gain and a
  look-ahead limiter. A soft clipper clips after AAC.
- The variable Inter needs its `Weight` axis set by name; the first axis is optical size.
- Captions sit 104 px up: many films carry their own source line or subtitle along the bottom.
- A GM sample is 3.1 s long: hold a closing chord with `repeat`, not a long duration, and
  measure the last seconds of the sound. Fix the sound alone with `--remux`.
- Render the full cuts on kc-local (`ssh` + `systemd-run` with `MemoryMax`, as ops.sh does):
  a copy of `scripts/`, `config/showreel/`, the logo, the font and the manifest, with `.venv`
  and `models` linked to `/srv/kitcut/repo`. Three 1-minute cuts took about 12 minutes there.
- Fresh reviewers caught, on every option: a black first frame, a small end line, captions on
  a film's own name plate, tall films as empty-looking strips in cells, and the product only
  named at the end. All are manifest/look keys now (see the reference); check them first.
