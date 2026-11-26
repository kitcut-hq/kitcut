---
name: launch-kit
description: Make a product's launch assets from a real recorded run of the product -- a 9:16 phone reel (~40-60 s), a 16:9 desk demo (~55 s: the phone on the left, the filled document flying out into a large toured sheet) and a Product Hunt gallery (five 2540x1520 images + a 240x240 thumbnail) -- in the Mister Blocks grammar (2-6 word step cards, an underlined tagline at the end), in the product's own fonts and colours, with no mockups. Use when asked for a Product Hunt (or any launch) video, reel, desk demo, gallery, screenshots or thumbnail, to turn a phone screen recording of a product into a short demo, to show a filled form or PDF readably in a video, or to restyle captions "like Mister Blocks".
---

# A launch kit from one real run

Built for the Instafill Product Hunt launch (2026-11, `projects/instafill-ph-launch/`,
local only): a letter photographed on a desk, the Instafill Agent finds the
ACORD 25, fills it from the client's policies, the filled PDF opens on the
phone. Four review rounds with the owner shaped every rule below; each has the
reason, so you can tell when one does not apply.

## What you make

| deliverable | how |
|---|---|
| 9:16 phone reel | `edl-cut.py`: camera shots of the desk + the phone's screen recording + `page-tour.py` over the filled page, step cards from `step-captions.py` as `image_overlays`, an end card |
| 16:9 desk demo | the same camera opening and close; the middle is `phone-sheet.py` (phone left, captions right; the page flies out of the phone into a sheet toured by `page-tour.py`) |
| gallery 2540x1520 x5 + 1270x760 copies + 240x240 thumbnail | Pillow, one script per project; reference: `examples/ph_gallery.py` |
| end card 1080x1920 and 1920x1080 | reference: `examples/end_card.py` |
| tagline < 60 chars | the end card's words ("An AI agent that fills your forms.", 34) |

Copy the three examples in `config/launch-kit/` into `projects/<id>/` and edit them.

## The shoot

- **Real product only.** The email said "no mockups": every pixel of UI is a
  frame of the real recording. What may be drawn on top: captions, the tour's
  highlights, a corrected page laid exactly into the viewer's own page box
  (the tour starts on the recording's own framing, so it cuts in invisibly).
- **The camera walks in.** One continuous shot: the paper on the desk with air
  around it, then the phone comes in and frames it. A cut between "paper" and
  "phone over paper" made the phone pop in -- rejected twice (reel and 16:9).
- **No Chrome splash.** Start the screen track on the product's own page, already
  loaded. The browser's launch icon frame read as filler.
- **Android pickers draw a black frame first** (31.6-31.8 s in our recording):
  start the picker segment on its first drawn frame, and end before it closes
  (the closing redraw is a black bar).
- **Fictional data that looks real** (docs/reference.md, make-doc): ordinary
  names, 555-01xx numbers, domains checked not to resolve, policy dates that
  cover the shoot day. No customer data, ever.

## Words: the Mister Blocks grammar

Measured off Mister Blocks' own launch reel; the owner asked for it after the
first draft's sentences were too long.

- **2-6 words a card, two even lines**, a STEP kicker above ("- STEP 2"), the
  words that matter in the accent colour. `step-captions.py` balances the
  split; `|` forces it where the sense is ("Flat PDF?|It makes it *fillable.*").
- **Open on the viewer's problem, not on your example.** "Need an ACORD 25
  filled?" made the film look like it was only for ACORD 25 users. What
  shipped: "A letter full of *details?*" -> "And a form *to fill?*" -> "Just
  snap the *request.*" The specific form comes later, as the example.
- **Name the thing that does the work.** "Open Instafill" was wrong: only the
  *Agent* finds forms and makes flat PDFs fillable. Say "Open the *Instafill Agent.*"
- **Describe the real process**, step by step, in the order it happens: snap
  the request; the other documents already exist; ask for the form; it finds
  the blank form; flat? it makes it fillable; then fills it from your files.
- **No "No scanner. Just snap a photo."** -- the owner disliked selling against
  something nobody mentioned.
- **A fast-forward is labelled** with a badge, "8x . REAL WAIT 50 SEC", so a
  speed-up is never a lie.
- **The claim must match the run** or be a general product truth you flag to
  the owner: "Flat PDF? It makes it fillable" was a product claim; the run's
  form was already fillable. Say so when you deliver.

## Look

- **No white panels.** The end card is the frame itself in the brand's ink with
  a soft accent glow, the logo with its dark wordmark recoloured white, the
  tagline with the accent phrase underlined, the address as a mono pill.
  **"instafill.ai", never "https://..."**. A white end block was rejected as
  not fitting the colours.
- **Bars beside a phone screen** on a 9:16 film: `"bg": "blur"` on the edl-cut
  source (the picture itself, cover-scaled, blurred, dimmed), never a flat colour.
- **The 16:9 right half** is for big captions while the work happens, then for
  the page flying out of the phone (`phone-sheet.py`). A magnifier card beside
  the phone (same UI, bigger, with a beam) was rejected: two objects showing
  the same thing.
- **A readable page in a video**: `page-tour.py`, stops at >= 2000 page px wide
  (7.5-pt type at ~20 px with its block in view). At 42 px type the labels and
  the context were lost. Labels say where a value came from ("From the
  letter", "Every limit"), not the field's name.

## The gallery

What shipped (`examples/ph_gallery.py`), and what each round taught:

1. **Hero**: logo, kicker, "An AI agent that / fills your *forms.*", three short
   lines, the URL pill; a phone with the real viewer frame and the filled page
   **with every filled field tinted blue** (`pdf-fields.py`). Amber boxes with
   labels on the page read as "an unclear orange piece" -- blue is how PDF
   viewers show fields, so it says "fillable, and filled" with no label.
2. **Steps 2x2**: every tile a whole thing, never cut mid-word or mid-page:
   the whole letter on the desk; the full prompt from a clean frame (not the
   reel's frame with a baked pill/underline); the agent's closing message with
   its Open PDF / Download buttons, fitted uncropped on the app's own
   background; the coverage block in blue fields.
3. **Before -> after**: the request letter and the filled form, straight, same
   size. Draw both from the PDF at 3400 px, downscale, light unsharp mask
   (radius 1, 90 %); a 1700 px render looked soft when zoomed.
4. **Sources**: the three real inputs on the left (thumbnail, file name, what
   came from it), the whole filled form on the right, an S-curve from each
   input to a bracket over the band of the form it filled -- bands from the
   PDF's widget rects, so the claim is exact. Name what is not traced to an
   input (certificate number, date, signature) when you deliver.
5. **Call to action**: the end card's words, a line of what it fills ("ACORD 25
   . W-9 . any PDF, fillable or flat" -- a product claim: flag it), the URL pill.
   A "the ask" slide with a phone and a same-size "zoom" of its screen beside
   it was rejected as meaningless.

- **The backdrop covers the canvas.** A 16:9 still scaled to 2540 wide is
  1429 tall; fitting it left black bands top and bottom on every image.
  Scale by `max(W/w, H/h)` and centre-crop.
- **Upload the 2540x1520 files**, not the 1270x760 copies: Product Hunt shows
  them zoomed, and small type survives only at 2x.
- **Thumbnail 240x240** from the site's own share image, centre-cropped.

## Procedure

1. `projects/<id>/` + `journal.md` first. Read the brief (an email: list every
   ask and check each one off at delivery: lengths, fonts, music, "address at
   the end", where to render, sizes, tagline length, "no customer data").
2. Cut the 9:16 reel first; the owner approves it before anything else (the
   16:9 and the gallery reuse its words and frames).
3. Captions: `python scripts/step-captions.py --spec projects/<id>/captions.json --list`,
   then without `--list`; place them in the manifest at times derived from the
   EDL's segment bounds (`examples/mk16a.py` does this for the 16:9), never by
   hand-typed seconds that drift when a segment changes.
4. Check frames at each caption's time (`edl-cut.py --frame`) before encoding:
   a card over a real UI sheet ("Choose an action") hid the action.
5. The 16:9: phone track (edl-cut), sheet (page-tour), then `phone-sheet.py
   --plan`, `--still T` at the fly and after it, then the section, then the film.
   Read the phone track's real duration with ffprobe: edl-cut frame-rounds
   each segment (44.70 s rendered vs 44.82 s summed).
6. Gallery, then copy the deliverables to the owner's folder, keeping each
   superseded final renamed (`*-FINAL-old-<what changed>.mp4`), never deleted.
7. Never render a look the owner has not seen: propose words and layouts in
   text first (a table: was / becomes), render after "yes".

## Traps

- **PowerShell `Get-Content`/`Set-Content` round trips break UTF-8** (a "->"
  arrow became "a+'"). Edit with the Edit tool or Python, never Set-Content.
- **`phone-sheet.py --still`** reads one frame with a select filter; the old
  generator form printed "Broken pipe" from ffmpeg -- harmless, now gone.
- **The composed middle's first 4 frames decode blank**: start its EDL entry at 0.15 s.
- Run Python through `.venv\Scripts\python.exe` from PowerShell on the laptop:
  Git Bash's `python` segfaults (exit 139) there.
