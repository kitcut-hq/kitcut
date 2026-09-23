---
name: video-name-label
description: Add a broadcast lower-third name label to a video — a dark rounded card carrying a person's name over their title and company, with a coloured accent sliver, that fades up, holds a few seconds and fades out. Use when asked to add a name label, a lower third, a chyron, a name tag or a speaker/title caption to a video, to identify who is on screen, or to restyle an existing name label.
---

# A lower-third name label

```powershell
# from the repo root

# 1. eyeball the card on its own
python scripts/name-label.py --card-only --name "Jane Doe" --title "CEO, Example"

# 2. prove where it lands on THIS footage -- one still, no encode
python scripts/name-label.py --video projects/<id>/outputs/film.mp4 --frame 4.0 `
    --name "Jane Doe" --title "CEO, Example"

# 3. burn it in
python scripts/name-label.py --video projects/<id>/outputs/film.mp4 `
    --name "Jane Doe" --title "CEO, Example" --at 2.0 --dur 5.5
```

The worked example is the `name_labels` block in
`projects/claude-demo/screencast.json`. Style lives in
`config/labels/lower-third.json`; `docs/reference.md` has the reference under
"A lower-third name label".

## The project folder comes first

Every video lives in `projects/<id>/` — its manifests, its content dirs, and
two committed metadata files. Before doing anything, read
`projects/<id>/project.json` (create the folder with
`python scripts/project-scan.py --init <id>` if this is a new video) and skim
`projects/<id>/journal.md` if the ask touches past decisions. When the work
lands: the finishing scripts record renders and uploads into the project file
themselves; if you ran ffmpeg by hand or a script printed
"PROJECT FILE NOT UPDATED", record the deliverable and journal line yourself.
End an editing session by appending a short prose note to `journal.md`
addressed to the next session: what was asked, which knob changed, why, and
anything it should not have to rediscover. Details: `## Projects` in the
`docs/reference.md`; the re-edit entry point is the `video-project` skill.

## Do not re-encode a finished film to label it

The label composes. `screencast-cut.py` reads `name_labels` from the manifest
and overlays the card **after its concat**, inside the film's existing single
encode pass:

```json
"name_labels": [
  {"name": "Oleksandr Gamaniuk", "title": "CEO, Instafill.ai", "at": 2.0, "dur": 5.5}
]
```

```powershell
python scripts/screencast-cut.py --manifest projects/<id>/screencast.json --list
python scripts/screencast-cut.py --manifest projects/<id>/screencast.json
```

So when the film is being cut anyway, put the label in the manifest and render
once. Reach for `--video` only when the source is gone and all you have is the
finished file — that costs a second generation.

`--at` is **film time**, the time on the finished scrubber, not camera time.
The overlay is applied after the cut, so the pauses the cut removed are already
gone from the clock.

## Order of work

1. **Pick the window before the style.** Watch the opening and find a stretch
   where the person is on screen, talking, and no cutaway interrupts. A card
   that spans a cut looks like a mistake even when it is centred perfectly.
   `screencast-cut.py --list` prints the acts and the b-roll, which is where
   the safe window is read off.
2. **`--frame T`** — composites the card onto the real frame at T and writes a
   PNG. This is the check that costs nothing, and it is the one that catches a
   card over a face, a card over a busy background, or a name too long for the
   frame.
3. **Render**, then sample the fade at `at-0.2`, `at+0.5`, `at+dur-0.3` and
   `at+dur+0.2` to confirm it arrives and leaves when it should.

## Shared code

Drawing and filter helpers live in `scripts/_overlay.py` — `hex_rgba`,
`font_for_cap_height`, `draw_text_tracked`, `text_width_tracked`, `esc`,
`probe`. `handle-overlay.py` uses the same ones. A new burned-in graphic should
import from there rather than grow a third copy of each, and follow the same shape:
Pillow draws a PNG, ffmpeg animates it with expressions in `t`, and `prepare()`
returns `(pngs, filter_complex, out_label)` so a caller can splice it onto its
own chain and keep the render to one encode.

## Style

Everything visual is in the preset — nothing is in the script.

| key | |
|---|---|
| `card.colour` / `alpha` | the slab behind the type; `alpha` 0.95 lets a hint of the shot through |
| `accent.colour` | the sliver. **The one key to change to rebrand the label** |
| `accent.offset_x_px` / `offset_y_px` | how far the accent rectangle sits down-right of the card, which is how much of it shows |
| `lines.name` / `lines.title` | font file and cap height per line |
| `card.pad_*` / `line_gap_px` | the card's air |
| `layout.corner` | `bottom-left`, `bottom-right`, `top-left`, `top-right`, or anything else for centred |
| `layout.max_width_px` | a longer name shrinks to fit, and says so on stderr |
| `animation.*` | fade up, hold, fade out, in seconds |

Sizes are authored on the preset's `canvas` and scaled to whatever frame they
land on, so one preset serves 1080p, 720p and vertical.

Type is sized by **cap height**, not nominal size, because nominal size
includes ascent and descent and those differ between weights — sizing by it
would put the two lines at a ratio nobody chose.

## Gotchas

- **A label past the end of the film is silent.** `enable` simply never turns
  true; ffmpeg reports nothing and the render succeeds without a card in it.
  `screencast-cut.py` checks `at` against the cut runtime for this reason. Keep
  that check.
- **`shortest=1` is mandatory on the overlay.** The card is a `-loop 1` image
  input and therefore infinite. Without it the render never ends and leaves a
  growing file with no `moov` atom — the same trap the PiP mask has.
- **`--frame` composites flat, with no fade.** A still grabbed at T restarts the
  image input's clock at zero, so the fades would land somewhere else entirely.
  That mode answers *where*, never *when*.
- **Don't seek before the input when trimming.** `-ss` after `-i` keeps the
  original timeline, so the fade start times still mean what they say. Seeking
  first rebases `t` and the card arrives at the wrong moment.
