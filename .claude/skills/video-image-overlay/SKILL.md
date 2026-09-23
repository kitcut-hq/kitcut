---
name: video-image-overlay
description: Burn an image onto a video — an end card, an outro, a logo, a chart, a screenshot or a product shot — with an entrance animation (wipe, fade or slide), real transparency, and optionally a treatment on the footage underneath (black and white, blurred, dimmed) while it keeps playing. The picture may be a file the user supplies, a card spec designed by make-card.py, or a hand-written HTML page. Use when asked to add an end card or outro to a video, overlay an image or logo on footage, put a picture or chart over a video, stamp or watermark a video with a graphic, or move/restyle an existing image overlay. To design the graphic itself, use video-card-design first.
---

# An image overlay, and end cards

This skill **burns** a picture onto a film. If the picture does not exist yet
and has to be designed, that is the `video-card-design` skill — come back here
once there is a spec, a page or a PNG.

The source is one of three, and nothing downstream can tell which:
`image` (a file), `card` (a spec designed by `make-card.py`), or `html` (a
hand-written page).

```powershell
# from the repo root

# 0. can this machine render HTML at all?
python scripts/html-to-image.py --check

# 1. the artwork on its own
python scripts/html-to-image.py --html projects/<id>/assets/end-card.html `
    --out projects/<id>/temp/end-card.png

# 2. prove where it lands on THIS footage -- one still, no encode
python scripts/image-overlay.py --video projects/<id>/outputs/film.mp4 `
    --html projects/<id>/assets/end-card.html --at -11 --background --frame 440

# 3. put it in the manifest and render the film once (see below)
```

The worked example is the `image_overlays` block in
`projects/claude-demo/screencast.json` with its page at
`projects/claude-demo/assets/end-card.html`. Animation, layout and treatment
defaults live in `config/overlays/end-card.json`; `docs/reference.md` section is
"An image overlay, and end cards".

## The project folder comes first

Every video lives in `projects/<id>/` — its manifests, its content dirs, and
two committed metadata files. Before doing anything, read
`projects/<id>/project.json` (create the folder with
`python scripts/project-scan.py --init <id>` if this is a new video) and skim
`projects/<id>/journal.md` if the ask touches past decisions. When the work
lands: the finishing scripts record renders themselves; if you ran ffmpeg by
hand or a script printed "PROJECT FILE NOT UPDATED", record the deliverable and
journal line yourself. End an editing session by appending a short prose note to
`journal.md` addressed to the next session. Details: `## Projects` in the
`docs/reference.md`; the re-edit entry point is the `video-project` skill.

## Do not re-encode a finished film to put a card on it

The overlay composes. `screencast-cut.py` and `cut-clips.py` both read
`image_overlays` and apply it inside the render's existing single encode pass:

```json
"overlay_preset": "config/overlays/end-card.json",
"image_overlays": [
  {
    "card": "projects/<id>/cards/outro.json",
    "at": -11.0,
    "layout": {"corner": "centre", "width_frac": 0.56},
    "in": {"type": "wipe", "dur": 1.1, "direction": "left", "feather_px": 18},
    "out": {"type": "none"},
    "background": {}
  }
]
```

```powershell
python scripts/screencast-cut.py --manifest projects/<id>/screencast.json --list
python scripts/screencast-cut.py --manifest projects/<id>/screencast.json
```

Reach for `image-overlay.py --video` only when the source is gone and all you
have is the finished file — that costs a second generation. `--clip` restricts
that encode to the overlay's own window, which is the cheap way to scrub timing.

**Write `at` negative for an end card.** It means "this many seconds before the
end", so re-cutting the film moves the card with it instead of stranding it at a
timecode that no longer exists. In a clips manifest the same number counts back
from each clip's own end, so one end card rides a whole batch of shorts.

## Choosing the animation

| | |
|---|---|
| `wipe` | the end-card move: reveals the image behind a travelling edge. Wants artwork made of solid blocks — the edge crossing type *and* its background is what sells it |
| `fade` | anything photographic, and any mid-video insert that should not draw attention to its own arrival |
| `slide` | a card that enters from an edge; pairs well with a corner `layout` |
| `none` | for `out`, when the film ends under the card |

`feather_px` is the softness of the wipe's leading edge: 1 is the hard edge of
the reference, ~20 suits a photograph. `direction` is the edge the reveal starts
**from** (for a slide, the edge it travels in from).

## The background treatment

`background` is **opt-in per overlay** — absent means the film is untouched, so
a mid-video logo can never dim the picture by surprise. `{}` takes the preset's
defaults; override individual keys (`desaturate`, `blur_sigma`, `dim`,
`vignette`, `in_s`, `out_s`) on the entry.

It is what makes an end card look expensive: the footage never freezes and never
cuts, it just recedes. Check it against the actual footage with `--frame` —
defaults measured on a bright studio wide shot will crush an already-dark screen
recording to near-black.

## Writing the page by hand

Prefer a `card` spec (the `video-card-design` skill) — a hand-written page is
for a design no template covers. The browser shoots it either way, and two
rules are enforced:

- **Nothing paints a background.** `html`/`body` stay transparent, or the shot
  comes back opaque and `html-to-image.py` refuses it by name. Only the artwork
  carries a fill.
- **The artwork is the only ink.** The PNG is cropped to its own alpha bbox, and
  that crop is what `corner` and `width_frac` size and place. Padding inside the
  page is fine; it is cropped away.

Load the repo's own fonts with a relative `@font-face` src
(`url("../../../fonts/Montserrat-Bold.ttf")`) so a card reads as the same
channel as the captions, the badge and the lower third. Montserrat covers
Cyrillic, which matters for this channel.

The page goes in `projects/<id>/assets/` — **committed**, because it is the
editable control; change the card by editing the page and re-rendering. The PNG
goes to `projects/<id>/temp/`, gitignored, regenerated whenever the page is
newer.

## Order of work

1. **Pick the moment before the artwork.** For an end card, read what the film
   actually does at the end — `screencast-cut.py --list` prints the acts. A card
   over a speaker still talking to camera is the reference's move and works;
   a card over a cut looks like a mistake.
2. **`--frame T`** — composites onto the real frame at T, treatment included, and
   writes a PNG. Free, and it is what catches an unreadable card, a bad size, or
   a treatment that kills the shot.
3. **`--list`** prices the plan and resolves the negative `at` against the real
   runtime, so you see the timecode before spending anything.
4. **Render**, then sample across the entrance to confirm the reveal reads.

## Shared code

`scripts/_overlay.py` carries what every burned-in graphic uses — `hex_rgba`,
`font_for_cap_height`, `draw_text_tracked`, `text_width_tracked`, `esc`,
`probe`, `anchor_xy`. Follow the same shape as the name label and the badge:
something draws a PNG once, ffmpeg animates it with expressions in `t`, and
`prepare()` returns `(pngs, filter_complex, out_label)` so a caller splices it
onto its own chain and the render stays one encode. Give any new one
`first_input=` — the badge's absence of it is why `cut-clips.py` needs a
defensive assert about input order.

## Gotchas

- **An overlay past the end of the film is silent.** `enable` never turns true;
  ffmpeg reports nothing and the render succeeds without it. Both pipelines
  check `at` against the runtime — which is also where a negative `at` is
  resolved. Keep that check.
- **`crop` cannot wipe anything.** Its `w`/`h` are evaluated once at filter
  configuration; only `x`/`y` re-evaluate per frame. The wipe is a `geq` on the
  image's alpha instead, `enable`-gated to its own window because a per-pixel
  interpreter left running is not free.
- **`shortest=1` is mandatory on the overlay.** The image is a `-loop 1` input
  and therefore infinite; without it the render never ends and leaves a file
  with no `moov` atom.
- **`--frame` composites flat.** A still grabbed at T restarts the image input's
  clock at zero, so every fade, wipe and `enable` would land elsewhere. That
  mode answers *where* and *how it reads*, never *when*.
- **`msedge --version` opens a browser window** instead of printing a version
  (Chrome's hangs). Versions are read off the install directory so `--check`
  stays free.
- **The preset's HTML block is `html_render`, not `html`** — on an overlay entry
  `html` is the page's path, and one name for two shapes merges a dict with a
  string.
