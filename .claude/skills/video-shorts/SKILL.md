---
name: video-shorts
description: Extract shorts/episodes from a long video, optionally reframed to vertical 9:16, and stamp them with an animated Instagram-handle badge. Reads the word-level transcript to pick self-contained episodes, resolves cut boundaries by quoting what is said (not by timecodes), face-tracks the crop window so the subject stays in frame, re-renders captions at vertical size, and burns everything in one NVENC pass. Use when asked to make shorts, extract clips or episodes from a video, to make a video vertical for Reels/Shorts/TikTok, or to add a social-handle watermark to clips.
---

# Shorts out of a long video, with a handle badge

The whole workflow, once a manifest exists:

```powershell
# from the repo root
python scripts/cut-clips.py --manifest projects/<id>/clips.json --list   # plan only
python scripts/cut-clips.py --manifest projects/<id>/clips.json          # cut
```

Clips land in the manifest's `outdir` — `projects/<id>/outputs/shorts/` for
landscape, `projects/<id>/outputs/shorts-vertical/` for the 9:16 manifests — as
`<prefix>-<clipid>.mp4`, each with a `.json`
sidecar recording exact boundaries and encoder settings. Cutting runs ~3x
realtime on this machine (five ~75s clips ≈ 2 minutes). Existing outputs are
skipped, so editing one manifest entry and re-running rebuilds only that entry;
`--only <ids>` / `--force` narrow it further.

**Prerequisite:** a word-level transcript at
`projects/<id>/transcripts/<id>.words.json`. If there isn't one, run the
captions pipeline first (see the `video-captions` skill) or just its transcribe
stage — everything below keys off that file. Prefer cutting from the
**captioned master** in `projects/<id>/outputs/` so the shorts carry the
burned-in subtitles.

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
README; the re-edit entry point is the `video-project` skill.

## Step 0 — derive the channel's own style

**Never cut for a channel we have not cut for before without first measuring
their look and committing a preset named for them.** Reaching for `red-card` on
somebody else's footage is what makes a sample reel read as "here is some
software" instead of "this is your show". It costs about twenty minutes and it
is the highest-leverage thing in the whole job.

Where the style is depends on what they publish:

- **They already post shorts** → measure those. `.venv/Scripts/python.exe -m yt_dlp`
  their channel's `/shorts` tab, pull three, and measure at **native 1080x1920**.
- **They only post long-form, but it is broadcast** → measure their own on-air
  lower third off a native 1920x1080 frame. In the 9:16 cut their banner is
  outside the crop, so **our caption card becomes their banner** — which is only
  true if it is actually theirs.

What to measure, and the trap in each:

| | how, and what bites |
|---|---|
| card colour + **opacity** | Compare brightness inside the box against just outside it, **over a bright part of the picture**. Lenny's read 65/140 and 62/138 → ~55% black → `card.alpha` 115. Sampling over dark hair or a black jumper tells you nothing, and a single frame cannot tell a caption box from clothing. |
| box top/bottom | Step-detect down a column that crosses a bright region. Their box: y 1210→1318, 109 px. |
| cap height | A line with **no descenders** — a `g` or `y` inflates it by ~10 px. |
| pads | `pad_y = (box height − cap height) / 2`. |
| case | Look. Sentence case vs uppercase is the single biggest tell, and uppercase runs ~15% wider, which changes `grouping.max_words`. |
| bottom margin | Distance from the frame bottom to the bottom of the box. |
| brand accent | Sample their logo bug **where it sits on a bright background** — over their own beige wall the wall wins the histogram. |

Then divide every 1080x1920 measurement by **1.7778** before writing it into the
preset, because presets are authored on a 1920x1080 canvas and scaled by the
height ratio. Put the raw numbers in a `_measured` block: that block is the
difference between a style and a guess, and it is what the next session reads
instead of measuring again. `config/presets/lennys-podcast-vertical.json` and
`bloomberg-tech.json` are the two worked examples.

**Two rules that are not negotiable:**

- **Shorts safe area.** Park the caption box ~600 px above the frame bottom
  (339 on the authoring canvas). The Shorts UI draws its title and CTA over the
  bottom ~380 px and the action rail over the right ~200 px. Lenny's sits at
  602 px, which is how we know it is a real constraint and not a preference.
  `red-card-vertical`'s 170 → 302 px is inside that zone.
- **Copy the look, then change exactly one thing** — and be able to say what it
  is. Here it was the per-word spotlight, in a colour sampled from their own
  logo. If you cannot name the single difference, you have either cloned them
  (why would they pay) or redesigned them (why would they agree).

## Step 0b — when the job is a pitch, write their numbers down FIRST

If the channel already publishes shorts, "better than theirs" is a claim, and a
claim recorded after the fact is unfalsifiable. Before cutting, put into the
manifest and the journal: their shorts' **length range, view range, caption
treatment, framing method, and what they do NOT do**. See
a `_their_shorts_from_this_episode` block in the clips manifest, holding one
line per short they already published: id, title, duration, views. Project
folders are local (see `.gitignore`), so copy the shape rather than expecting
to find that file in a fresh clone:

```json
"_their_shorts_from_this_episode": {
  "_note": "Recorded BEFORE cutting, so 'better' stays falsifiable.",
  "range": "33-61s, 1080x1920, 194-3741 views, posted 1-4 days after",
  "already_mined": ["<id> '<title>' <dur> <views>", "..."],
  "what_they_do_not_do": "flat caption block, no per-word highlight, ..."
}
```

Then cut **one of each kind**: one short from a passage they *already published*
(so the comparison is direct and nothing hides behind a different pick) and one
from a moment they missed. The first argues craft, the second argues judgement.

## Step 0c — the caption placement is checked for you; read its verdict right

**A caption position is only safe relative to a framing.** The preset's
`bottom_margin_px` was measured against one framing; a crop change silently
invalidates it. On `g-YDNJcyuck` clearing the broadcast lower third pushed
`crop_zoom` up, magnified the face, and put the card across two speakers'
mouths — through 24/24 caption-sync probes, a passing hook gate and two rounds
of eyeballed frames.

`cut-clips.py` runs `check-caption-space.py` **automatically** after rendering
any vertical captioned manifest and fails the run if a card sits on a face, so
you do not have to remember it — you have to know what to do when it fires.
Run it standalone only to re-check without an encode, or on a machine that had
no face model at render time (the render prints a loud skip in that case —
never publish past one):

```powershell
python scripts/check-caption-space.py --manifest projects/<id>/clips-vertical.json
python scripts/check-caption-space.py --manifest ... --list   # every frame, exit 0
```

Read the verdict as a decision tree, not a pass/fail:

1. **Clean** → done.
2. **Card on the face, room below the chin** → lower `bottom_margin_px`.
3. **No room below** (the card cannot clear the face box *and* stay above the
   Shorts UI at y≈1540 — a two-line card is ~174 px and often will not fit)
   → put it **above the head** with a large `bottom_margin_px`.
4. **No room anywhere** — the subject fills the frame top to bottom → the
   *framing* is wrong, not the caption. Letterbox the clip (`pad` in the
   `.reframe.json` sidecar, which **overrides** the manifest's `crop_pad`): the
   whole source frame over a blurred fill keeps the channel's own graphics
   intact and unsliced and opens clear space under the band for the card.

Clips in one manifest can need different answers. A clip may carry its own
`captions` block overriding `bottom_margin_px` / `max_lines` /
`max_line_width_px`; only `layout` keys are overridable.

And sweep the grouping — `grouping.max_words` against
`layout.max_line_width_px` — using the wrap/orphan counters
`build-captions-ass.py` prints. A group one word too wide wraps and orphans that
word onto its own line ("the models are going / **to**"), which no structural
check can see. Both channel presets shipped on the worst cell of their own
sweep; uppercase runs ~15% wider, so caps take one word fewer per card.

After changing any of the machinery itself — `cut-clips.py`,
`build-captions-ass.py`, `check-caption-space.py` — run
`python scripts/check-shorts.py` before trusting a render: it pins the hook
gate, pad resolution, crop windows, grouping typography and caption-space
geometry against real-footage fixtures, in seconds, with no encode.

## Step 1 — analyze: pick the episodes

Dump the transcript as timestamped lines and read it end to end:

```powershell
python scripts/transcript-outline.py projects/<id>/transcripts/<id>.words.json --outline
```

What makes a good as-is short (no editing pass to save it later):

- **Open on the HOOK, not on the start of the thought.** The first spoken words
  must be a concrete, self-contained claim — a number, a name, a surprising
  statement. Setup, wind-up and back-reference to earlier context are dead air:
  a short has ~2 s to earn the watch, and "the start of the thought" is usually
  several sentences of it. Closes on a payoff or punchline. Never open
  mid-sentence.
- **60–90 s** for talking-head content; under 60 s for a single gag/story.
- Prefer segments with emotion, concrete numbers, a strong visual, or a
  controversial thesis — those carry a clip with zero extra editing.
- **Skip the video's intro** (it never stands alone) and **skip sponsor reads**;
  check that a chosen segment doesn't start right inside one.

Verify each candidate boundary before writing the manifest:

```powershell
python scripts/transcript-outline.py projects/<id>/transcripts/<id>.words.json --find "exact phrase"
```

### Step 1b — the selection is a STAGE, not a moment of taste

Do not go from the outline straight to a manifest. Write
`projects/<id>/shortlist.json` first — every candidate seriously considered,
each with its quotes, its hook, answers to the four hook tests, a picture
note, and a verdict (`pick`/`backup`/`reject`) with reasoning — then run:

```powershell
python scripts/shortlist-moments.py --shortlist projects/<id>/shortlist.json
```

It resolves every phrase, prices every hook against the gate, and refuses a
shortlist with fewer than 5 candidates or fewer than 2 documented rejects —
if nothing lost, nothing was compared. Only candidates marked `pick` go into
the manifest; `backup`s are the bench for when a pick dies on review.

Why mandatory: on one Bloomberg episode the pick-inside-the-flow approach
shipped two rejected shorts in a row (an anchor posing a question; a Treasury
Secretary saying nothing falsifiable), while the candidate that survived had
been the top of the payoff table all along. Both bad picks fail the four
tests ON PAPER — the stage makes writing that paper mandatory, and the
comparison run that proved it also caught, in one afternoon: a hook quoted
from a short's TITLE instead of the transcript, two "already mined" shorts
that belonged to a different episode entirely, and two spans silently
anchored to the cold-open trailer's copy of the quote (a first-match phrase
resolver takes the trailer, and the same trap applies to `resolve()` in
cut-clips — anchor on words unique to the body instance).

## Step 2 — the manifest

`projects/<id>/clips.json`. Boundaries are **quoted speech**, not timecodes, so
the manifest reads like the edit decisions that were made:

```json
{
  "source": "projects/<id>/outputs/<id>-captioned-1080p60.mp4",
  "words": "projects/<id>/transcripts/<id>.words.json",
  "outdir": "projects/<id>/outputs/shorts",
  "prefix": "<id>",
  "pad": { "head": 0.15, "tail": 0.35 },
  "handle": { "text": "@kris_zahrebelna", "preset": "config/handles/default.json" },
  "clips": [
    { "id": "01-slug", "title": "…",
      "start_text": "ну що, тільки що кур'єр",
      "end_before_text": "наступне, друге" }
  ]
}
```

- `start_text` starts where that phrase begins; `end_text` ends where that
  phrase ends; `end_before_text` ends just before that phrase begins (use it to
  cut right before the next thought). Matching ignores case, punctuation and
  spacing, so a phrase pasted from the outline and one typed by hand both hit. Plain `start`/`end`/`duration` seconds also work.
- Pads never eat a neighbouring word — when the transcript says speech continues
  inside the pad, the boundary meets it halfway. So don't hand-tune pads per
  clip; the defaults are right.
- No NVIDIA card → `--encoder libx264` encodes on CPU (the manifest's NVENC
  render block is translated, cq→crf, not passed through).
- Cuts re-encode (NVENC) and are frame-accurate. `--copy` stream-copies —
  instant but keyframe-snapped, and it cannot burn in the handle.

## Step 3 — the handle badge

Declared in the manifest (`handle` key, above) and applied **during the cut** —
one encode, no second generation loss. CLI overrides: `--handle "@name"`,
`--handle-preset <path>`, `--no-handle`.

The badge is a camera glyph above the @handle that hops between anchor points
every `move_every_s` and alternates flat-white/gradient every `colour_every_s`
(two independent cycles — the combination doesn't repeat quickly, which is the
anti-crop point). All styling and motion lives in `config/handles/*.json`,
authored on 1920x1080 and scaled to the real video. Keep `motion.positions`
(badge centres) clear of the caption card at the bottom.

Standalone use on any existing file:

```powershell
python scripts/handle-overlay.py --badges-only --handle "@name"      # preview PNGs
python scripts/handle-overlay.py --video in.mp4 --handle "@name"     # burn in
```

Architecture, if editing it: Pillow draws the badge once per colour variant into
a PNG (fonts, gradients, outlines are easy there); ffmpeg animates it with
`overlay` using `x`/`y`/`enable` expressions in `t`. One filter pass, no
per-frame Python. Don't try to move this into ASS — libass has no gradients.

## Vertical 9:16

Do **not** crop the captioned master — its caption cards are up to ~1180 px wide
on a 1920 canvas and a 9:16 window is only 607 px, so the crop slices the
subtitles. Cut from the **clean source** and re-render captions after the crop.
Use a second manifest for it (`projects/<id>/clips-vertical.json`) so the
landscape build stays intact:

```json
"source": "projects/<id>/sources/<id>-1080p60.mp4",
"vertical": { "width": 1080, "height": 1920 },
"captions": { "style": "config/presets/red-card-vertical.json", "samples": 24 },
"handle":   { "text": "@name", "preset": "config/handles/vertical.json" }
```

Order inside the single encode is crop → scale → captions → badge, so captions
and badge are both sized for the frame the viewer sees.

**Reframe first.** A fixed centre crop is a bet that the subject is centred;
over a real video they are not.

```powershell
python scripts/auto-reframe.py --manifest projects/<id>/clips-vertical.json
```

It writes `projects/<id>/clips-vertical.reframe.json`, which `cut-clips.py` picks
up automatically. The default `--mode hybrid` splits each clip at its shot
boundaries and decides every shot on its own:

| | when | result |
|---|---|---|
| `static` | face barely moves in the shot | window frozen |
| `pan` | face moves | window tracks it |
| `pad` | no face found | **not cropped** — whole frame letterboxed over a blurred fill |

`pad` is what saves full-width burned-in graphics and b-roll, which no 607 px
window can contain. It is switched by `enable` on an overlay, so it still costs
one encode, and captions and badge composite on top of it.

Report the detection rate and the per-shot plan it prints. Two things to check
by eye every time:

- **A `pad` decision only ever means "no face found here."** Usually b-roll, but
  a shot where the subject looks down or away reads identically — one clip here
  letterboxed a shot she is actually in, because she was holding something up
  and her head was above the source frame.
  **"No face" is not "nothing to crop to."** Letterboxing shrank a perfectly
  good subject to a third of the screen; cropping to what she was holding looked
  far better. Review every `pad` on screen, and when one is wrong, override it in
  the `.reframe.json` sidecar — that file exists to be edited: clear the `pad`
  entry and add `keys` across the span.
- Below ~60% detection means it mostly held a guess.

Only `crop_keys` (inline `[[t, x], ...]`) overrides the sidecar. `crop_x` and
`crop_pad` do **not** — where a sidecar entry exists it wins, and `cut-clips.py`
prints a note if a clip sets one anyway. Override by editing the sidecar
itself, as above.

**Mark every hand edit, and a re-run of `auto-reframe.py` will refuse to
destroy it.** Put a `_`-prefixed prose key in the entry (`"_pad_why": "..."`)
or at the top of the file (`"_comment": "HAND-EDITED ..."`) — the regen keeps
marked entries (file-level marks protect every existing entry, new clips still
land) and says what it kept and why. `--force-regen` overwrites, which is the
right move after a clip's boundary changes: sidecar times are in CLIP time, so
a moved start makes every hand-tuned time mean something else — regenerate,
then re-apply the edit recomputed against the new start. An UNMARKED edit is
still overwritten with only a WARNING, which is how one film lost the same
letterbox override three times in a session — so mark them; the marker doubles
as the note the next session needs anyway.

The other reason to letterbox besides "no face": a **full-width graphic
insert** — the host steps aside and a news card takes half the frame. The
tracker follows the face correctly, which is exactly wrong: measure the card
(it was 641 px here, wider than the 607 px window), letterbox the span with a
`pad` entry, and neutralise the runaway x keys inside it so a frame-off pad
edge still shows the host.

`--mode compare` needs scenedetect; without it the comparison refuses rather
than printing a table (it used to print one full of zeros and exit 0).

**Do not swap the default on a hunch — measure.** `--mode compare` scores every
strategy on off-centre distance and window motion, writing nothing:

```powershell
python scripts/auto-reframe.py --manifest ... --mode compare
```

That is how `hybrid` was chosen: `pan` 27.9 px mean / 77 p95 / 10.5 px/s,
`shot` 32.0 / 102 / 4.0, `hybrid` 24.8 / 73 / 8.4 — hybrid beat both on every
clip. Note the off-centre metric is scored against detected faces, so it
structurally favours a face-following track; the near-edge and out-of-frame
columns are the ones describing real damage. `--mode pan` is the older behaviour
and is the automatic fallback when `scenedetect` is not installed.

### How the tracking actually works, and where it breaks

Deliberately the cheapest thing that worked, so know what you are trusting:

- **The subject is whichever face has the largest box** — no identity
  association across frames. It holds because a talking head dwarfs the people
  behind her. If a nearer background face ever measured larger, the window would
  jump to them, and nothing in the design prevents that.
- **Detection is Haar** (2001-era, frontal + profile) at 3 fps on 480 px
  greyscale. The quality comes from the smoothing, not the detector: median over
  1.2 s, then EMA, with jumps over 280 px snapping as scene cuts. A genuinely
  fast movement is therefore tracked late.
- **Misses hold the last position** rather than predicting, so a long faceless
  stretch parks the window wherever the last face was.
- **Only `x` is driven.** `y` sits at frame centre — headroom and eyeline are
  not controlled at all.

If better framing is asked for, the worked-out upgrade path, best value first —
all of these install cleanly on this machine's Python 3.13:

1. ~~`scenedetect` per-shot framing + blur-pad fallback~~ — **done**, this is
   `--mode hybrid`. Worth knowing what the measurement showed: per-shot framing
   *alone* was a regression (steadier, but it loses the subject), and scene
   detection alone did **not** fix the b-roll — the pad fallback did. Both
   halves were needed; the first half shipped alone would have looked like a
   failed idea.
2. **YuNet** (`cv2.FaceDetectorYN`, already in the installed cv2 — needs one
   ~350 KB ONNX from opencv_zoo) to replace Haar. Its 5 landmarks let you place
   the eyeline on the upper third, i.e. finally drive `y`. It would also cut the
   false `pad` decisions, which are purely detection misses.
3. **Kalman / constant-velocity filter** over detections, replacing hold-last.
4. Person detection (`ultralytics`) only if faces genuinely are not the subject.

`cv2.saliency` is NOT available: that lives in `opencv-contrib-python`, not
`opencv-python`.

Both presets need a vertical variant, because both are authored on a landscape
canvas:

- **Captions** scale by the HEIGHT ratio, so vertical enlarges text ×1.78 while
  the frame gets narrower. `red-card-vertical.json` cuts words-per-group so the
  cards don't turn into tall multi-line blocks.
- **The badge** scales by the WIDTH ratio, so a landscape preset comes out tiny.
  `handles/vertical.json` is authored on 1080x1920 with anchors that stay clear
  of the caption card (below y≈1450).

## A short out of a SCREEN RECORDING — do not face-track it

If the source is a screencast, stop before `auto-reframe.py`: there is no
subject to track, and the 9:16 window it would crop to is 607 px of a 1280 px
browser, which nobody can read. Name the **rectangle to keep** instead.

```json
"crop_rect": [215, 72, 900, 535],
"place": {
  "y": 544,
  "background": "#0B0D10",
  "mask": [ { "rect": [12, 488, 190, 186], "mode": "delogo" } ]
}
```

`crop_rect` is `[x, y, w, h]` on the source; it beats `crop_x`/`crop_keys` and
the reframe sidecar, which is not even loaded when the manifest sets one. The
rect is scaled to the canvas width and placed at `place.y` (omit to centre).
`place.pan` — `[[t, [x, y]], ...]` — moves the window, but it keeps ONE size:
`crop` evaluates `w`/`h` once, only `x`/`y` per frame.

**Work in this order, and none of it costs an encode:**

1. **Find what must leave the frame.** A screen recording made for YouTube
   usually carries a webcam PiP, burned-in captions and a taskbar. All three
   are wrong in a short, and *fatal* if the sound is being replaced: the old
   captions contradict the new voice and the PiP's lips disagree with it.
2. **Drop what sits outside the readable region, mask what sits inside it.**
   The caption card and the taskbar are below the content, so the rect's height
   drops them. The webcam is bottom-left, in the same band as the buttons the
   demo is about — cropping around it costs you the demo, so mask it. Masking
   first is what frees the rect to be chosen for readability alone.
3. **Use `delogo`** (the default). Measured on real frames: it interpolates the
   rectangle from its own borders, so over a flat page background it *is* that
   background. `blur` made a dark webcam a grey smudge; copying a neighbouring
   strip duplicated the buttons next to it.
4. **Give it a flat dark ground, not `blur`.** A white browser page blurs to a
   white void and the picture has no edge against it.
5. **Centre the window on the page's own centre**, not on the action — a web
   page re-centres its content between beats, and a window centred anywhere
   else reads as a mis-framing on half of them. Then check the widest beat: if
   a headline or a file name is clipped at the frame edge, either widen the
   window or start the clip after that beat.
6. **Price it with `--list`**, which prints rect, output size, placement, zoom
   factor, pan keys and mask count.

**Two things a screencast short gets wrong that a talking head does not:**

- **A progress bar is dead air.** One of these shorts had 30 seconds of an
  "Adding fields" status that went from 1% to done without visibly moving.
  Find the moment the state actually changes and start there — track the chip's
  hue across sampled frames rather than guessing, then let the voice-over carry
  the setup you cut.
- **The picture keeps moving after the point is made.** Sample the last few
  seconds: a clip that runs two seconds long lands on an unrelated page.

**Verify the removals on the RENDER, with a detector.** A stray talking head in
a re-voiced short is the one failure nobody forgives, and an eyeball on four
frames does not cover a 26-second clip. Sweep with the YuNet under
`models/face/` — and sweep the SOURCE with the same settings too, because a
detector that finds nothing everywhere has proved nothing. Here: 30/30 sampled
source frames had the webcam, 0/80 across the two finished shorts.

## Step 4 — verify before declaring done

The cutter already asserts output duration against the plan. Additionally:

1. `--list` first, and sanity-check the resolved times and lengths.
2. Pull 4–5 frames per clip across the badge's cycle and LOOK at them —
   position hops, colour alternation, captions intact, badge not overlapping
   the caption card:
   ```powershell
   ffmpeg -v error -ss 6 -i projects/<id>/outputs/shorts/<clip>.mp4 -frames:v 1 -vf scale=760:-1 -y temp/chk.png
   ```
3. Check both ends of one clip for clipped words (frame at t=0.2 and t=dur-0.2).

### The opening is a HOOK problem first, a frame problem second

**Never buy a settled opening frame with dead air.** A short has about two
seconds to earn the watch; nobody waits through a wind-up for the point. This
ordering is not optional, and it is easy to get backwards — on `dHYrpun-XTs` the
opening frame was fixed by moving the start back one sentence, which bought a
closed mouth at the cost of ~7 s of back-reference to a calculation made *before
the clip*. The frame was perfect and the short was worse. It had to be re-cut a
third time.

The order to work in:

1. **Find where the hook is** — the first concrete, self-contained claim. Cut
   there. Everything before it that only makes sense with earlier context is
   dead air, however fluent it sounds.
2. **Then** place the exact frame, within the couple of frames around that word.
3. Only if no acceptable frame exists near the hook, consider moving — and if
   moving costs a hook, keep the hook.

**Check the render's CAPTION, not just its picture.** A head that lands inside
the previous word shows up in the first caption card as a word the viewer never
properly hears — that is how a cut 0.06 s inside `кажуть,` was caught here,
after the picture alone had looked fine. `--sheet` writes the render's first
eight frames with captions burned in for exactly this.

Word boundaries are in the transcript, so use them: land in the gap *between*
words (`кажуть,` ends 371.56, `людина` starts 371.58 → start at 371.57). A
numeric `"start"` is the right tool, because `resolve()` skips the pad block
entirely when there is no `start_text` anchor, so the value lands frame-exact.

### Always check the opening — picture AND sound

**Never ship a short that opens mid-word with a half-open mouth.** It is the
first thing a viewer sees, it reads as a botched cut, and *nothing else in the
pipeline catches it*: caption-sync probes and the duration assert both pass on
such a clip, because nothing about it is out of sync or the wrong length.

```powershell
python scripts/check-openings.py --manifest projects/<id>/clips-vertical.json
python scripts/check-openings.py --manifest ... --sheet     # then LOOK at the png
```

It flags a **boundary inside a word** unconditionally — a cut 0.06 s into a
word shipped from here before that check existed; the picture looked fine and
only the render's first caption card, carrying a word from the previous
sentence, gave it away. No `open_ok` excuses this one: unlike a short lead-in
there is no judgement call to make. (A deliberate stop-1-ms-early end, used
when two transcript words share a timestamp, is inside the check's epsilon and
does not flag.)

It also measures the **lead-in silence** (the gap between the previous word's
end and the cut) and flags anything under 0.20 s. Remember `resolve()` pads
meet speech halfway, so a 0.24 s transcript gap yields only ~0.12 s of lead-in.

**Silence is not proof, and the numbers often cannot decide it.** A mouth stays
open across a short gap, and some speakers never pause at all — on `dHYrpun-XTs`
the largest gap in the 37 s around one clip was 0.28 s, so no boundary there was
clean on silence and every candidate had to be looked at. `--sheet` contact-
sheets every frame inside the nearby pauses plus the first 8 frames of the
render as shipped; pick a frame with the mouth closed, face toward camera and
the gesture settled, then set that clip's `pad.head` to land on it.

That is exactly how one clip here was fixed: opening on the phrase that carried
the idea put frame 0 mid-word — mouth open, eyes down, hand frozen mid-gesture —
while every frame of an earlier 0.28 s gap was settled. The start moved back one
sentence **for the picture, not for the words**.

A short lead-in you have looked at and accepted goes in the manifest as
`"open_ok": "<why>"`, so the check keeps its teeth and stops crying wolf:

```json
{ "id": "01-…", "start_text": "…",
  "pad": { "head": 0.2, "tail": 0.35 },
  "open_ok": "0.14 s lead-in, but no pause >0.28 s anywhere near; frame 0 checked by eye" }
```

**A mouth-openness detector was tried and rejected**, and is worth not
re-attempting blind. YuNet's 5 landmarks give mouth *corners* but no lip
contour, so openness has to be inferred from darkness. Scored against eight
frames already judged by eye it separated them cleanly and **backwards** —
closed mouths read darker than open ones, because the speaker was looking down
in the open ones and the score was reading head pose, not lips. Eight frames
from one shot separating for the wrong reason will not survive the next video.
Doing it properly needs a lip-contour model and a labelled set across films.

## The hook gate — mandatory, and it blocks the render

**Every clip must declare `hook`: the exact phrase that makes a viewer stay.**
`cut-clips.py` resolves it in the transcript and refuses to encode if it lands
more than 3.0 s after the first frame. There is no way to skip it; a stated
reason in `hook_ok` downgrades the timing failure to a warning, and nothing
downgrades a missing hook.

```json
{ "id": "01-...", "hook": "дуже полюють за нашими інженерами", ... }
```

This exists because the same mistake shipped **twice in a row**, and every other
check passed both times — settled frame, silent lead-in, no mid-word cut, and a
clip nobody would watch:

| shipped opening | hook landed | what the viewer got first |
|---|---|---|
| `Можна так зробити…` | **32.6 s** | a back-reference to a calculation that was cut away |
| `Якщо ми говоримо конкретно про ту ситуацію, яку зараз ми проговорюємо…` | **6.7 s** | a pronoun pointing at a question the viewer never heard |

Both now FAIL the gate, and both trip the filler-opener warning by name. Naming
the hook is most of the value: **a clip whose hook cannot be written down as a
phrase does not have one**, and the boundaries are wrong.

**A hook is a CLAIM somebody makes, not a question an anchor poses.** The gate
measures *when* the hook lands; it cannot tell you the hook is worthless. A news
panel is the trap, because its wind-up is grammatical, confident and completely
empty. Bloomberg Tech's headline segment opened

> "But really the question here is what happens to Hugging Face if Nvidia owns it"

which passes every structural check and is not a hook: it is hedged (*really the
question here is*), it is meta — a question ABOUT the story rather than a
statement of it — and there is nothing in it for a scroller to agree or disagree
with. Its one real claim, "arguably Hugging Face's greatest value is that
everybody uses it", sat at 0:12. Three tests, all free:

- **Could a viewer disagree with the first sentence?** If not, it is set-up.
- **Is the speaker addressing an audience, or the person next to them?**
  Studio cross-talk is not a short. "So Rachel, real quick, is this imminent"
  ran through the middle of that same clip; a handoff mid-clip is a dead 3 s.
- **Does it end on the claim or trail off?** That one closed on "it sounds
  like, like, it is pretty imminent" — a hedge on a hedge.
- **Does the first sentence contain something falsifiable — a number, a name,
  an event?** This is the test that matters, and it was learned the expensive
  way: the first replacement for that clip was a Treasury Secretary telling a
  room the AI industry has "done a horrendous job, horrendous job of
  explaining themselves" and needs "a big reset" — which passes all three
  tests above and was rejected on review as "blabla nothing specific",
  correctly. It contains no number, no name, no event; it is a complaint
  about *messaging*, meta all the way down. A politician can deliver empty
  content with perfect form. "Dell was considered dead, or almost a dinosaur"
  passes: a named company, a dated reversal, and the numbers follow.

The clip that finally shipped is the same episode's Dell answer — falsifiable
from its first sentence, revenue up 110 % inside it, one held shot.

**Rank the alternatives by where their payoff lands before you argue about
them.** It costs nothing and it turns taste into a table: write the
candidates into the manifest and run `cut-clips.py --list` — it prints
`hook +X.Xs` for every passing clip, not just gate failures. For that
episode: Dell "considered dead" +1.8 s, Uber micro-teams +5.0 s, Bessent
+7.5 s, Ian King "wants more customers" +12.7 s. Then apply the
falsifiability test BEFORE re-anchoring anything — it would have eliminated
Bessent at the table stage, before a render was spent. Typography prices the
same way: `build-captions-ass.py --sweep` prints the max_words × width table
for the words that will actually render.

**Re-anchoring usually beats rejecting.** A soundbite whose payoff is buried
behind parallel clauses can often be entered mid-sentence at a point that still
reads as a whole sentence — "the labs themselves have done a horrendous job"
moved +7.5 s to +2.9 s and changed not one word of his. What you may NOT do is
redeclare the hook as a longer phrase that starts earlier: that scores +1.4 s by
moving the goalposts rather than the cut, and the gate is then measuring
nothing. **Then let the picture decide.** Of the four candidates above, the
SpaceX/Cognition exchange died on a two-box and the Hugging Face segment had
already died on one.

**When a fast hook and a settled frame are incompatible, change the material,
not the rule.** They are separate constraints and both are real — an opening
mouth-open on a vowel is never acceptable, and neither is 6 s of run-up. On
`SKv9fUHeckE` those two were 5 s apart in one segment, so that segment was
dropped for the next answer, where a genuine 0.68 s silence and a 2.2 s hook
coincide. Find the segments where they coincide by scanning the audio for real
silences and reading what follows each one; do not negotiate between the rules.

## Reading somebody else's source before you cut it

Three properties of a third-party video decide what you are allowed to pick, and
all three are cheap to measure. Do it before choosing episodes, not after.

- **Burned-in subtitles.** Many channels burn captions on part of their footage.
  A 9:16 window is 607 px of a 1920 px frame, so full-width burned-in text is
  sliced into fragments AND your own caption card lands on top of it. Measure the
  fraction of near-white pixels in the caption band across sampled frames rather
  than eyeballing four of them. On DOU `SKv9fUHeckE` only the host's off-camera
  questions are subtitled: the band reads 0.0280 under a question and exactly
  0.0000 during every guest answer. That made "guest-only" a hard constraint on
  episode choice and killed two otherwise-excellent clips whose hook lived in the
  host's question. **A clip built on an unsubtitled off-camera question also
  fails for a second reason:** the guest answers in pronouns, so the short is a
  minute about an unnamed "they".
- **How many cameras.** `scene>0.25` finds nothing when two cameras shoot the
  same person in the same room — it missed all seven cuts in a 68 s clip. Frame
  differencing finds them instantly (median 0.36, cuts >12).
- **Then judge the reframe plan against those cuts, not by its jumps.** A
  ±140 px window snap looks like a defect and is not one if it lands on a camera
  cut, because the whole picture changes at that instant. All eleven jumps across
  two clips landed within 0.01 s of a real cut. Check alignment; do not "fix"
  the jumps.

## The transcript is not evidence of silence

faster-whisper truncates word **ends**. A "gap" between one word's end and the
next word's start therefore routinely contains speech, and a head pad placed by
that number opens mid-phrase while every transcript-based check reports a
comfortable "ok". Measured: the transcript claimed 0.48 s of lead-in before a
hook word while the waveform ran at -12 dB RMS straight through it. Word
*starts* line up with the audio well; it is the ends that drift.

`check-openings.py` now measures the waveform as well and flags the
disagreement. When there is genuinely no silence to cut into — a speaker who
runs a sentence into the next — place the head pad on the **RMS minimum** and
record it in `open_ok`:

```powershell
python scripts/check-openings.py --manifest projects/<id>/clips-vertical.json
#   audio  frame 0 is SILENT, 0.54s of air before the first word
#   audio  frame 0 lands in SPEECH -- reviewed and accepted: <why>
```

Decode raw PCM to measure this. `volumedetect` after an `-ss` seek on a
compressed source returns decoder-priming garbage — it reported -1.2 dB peaks
inside a pause that is really at -40 dB.

## Traps (all hit for real)

- **A per-clip `pad` is honoured by the renderer, the reframer and the
  checker — but was silently ignored by the first two until 2026-09.** If you
  are reading an older manifest, a clip's `pad.head` may not be what actually
  shipped; `--list` prints the resolved start, so trust that over the manifest.
- **A caption-sync probe cannot judge a word shorter than two frames.** At
  25 fps a 40 ms word is exactly one frame, and cs-quantised ASS plus a 70 ms
  fade can put the highlight on either side of it. Such words are skipped and
  the count is printed. Raising `min_active_ms` does NOT fix it when the word is
  the last of its caption group — the group end clamps the highlight regardless.
- **`crop` has no `eval` option** — that is `scale`/`overlay`/`drawtext`. Its
  `x`/`y` are flagged runtime-tunable and already re-evaluated every frame,
  which is what makes the pan work. Passing `eval=frame` is a hard error.
- **Never pass a Windows path to the `ass` filter with backslashes.** libass
  reads `temp\05-x.ass` as an escape and silently looks for `temp05-x.ass`.
  Forward slashes everywhere.
- **`SELFCHECK: group N overlaps group N-1` is a real defect, not noise.** A
  group's per-word `min_active_ms` cascade ran past the next group's start, so
  the card would outlive its slot. It depends on where the group seam falls, so
  it appears and disappears as `grouping.max_words` changes — and `max_words`
  and `min_active_ms` interact. Tune them **as a pair and re-test every clip**
  (build the ASS alone, no encode, it takes seconds). Never edit the builder to
  silence it.
- **Haar cascades need `opencv-python<5`.** OpenCV 5 ships none, and its
  `FaceDetectorYN` wants a model downloaded from an external host.
- **An ffmpeg option before an `-i` binds to THAT input.** Adding badge PNG
  inputs turned a `-t` next to the source into the PNG's duration and the clip
  silently ran to the end of the source. `-ss` before the source input, `-t`
  after all inputs. The duration assert is what catches this class of bug.
- **`-b:v 0` is required with `-cq`** or NVENC ignores the quality target.
- **The environment is fixed; run scripts as plain `python scripts/<name>.py`.** A machine-wide `PYTHONPATH` used to point at another Python install and break `import faster_whisper` -- and a venv did not help, because `PYTHONPATH` is prepended inside one too. It has been removed, and every script now imports `scripts/_env.py` first, which re-execs into `.venv` with a clean environment and forces UTF-8 stdio on this cp1252 console. Run `python scripts/check-env.py` if an import ever breaks again.
- **Bare `yt-dlp` prints nothing under Git Bash** on this machine; always
  `.venv/Scripts/python.exe -m yt_dlp`.
- **Threads.com links can't be downloaded** — yt-dlp has no Threads extractor
  and the page is a logged-out JS shell with no og:video. Ask the user for the
  file or a DevTools-captured CDN URL.
- The badge animates on the **output** clock (t=0 at clip start), so every clip
  starts its cycle at the same place — that's intended, don't "fix" it.
- `scripts/transcript-outline.py` and `scripts/cut-clips.py` have hyphens in
  their names: import via `importlib.import_module("transcript-outline")`, and
  keep it that way for CLI ergonomics.

## Where to put the handle badge

Anchors live in `config/handles/<preset>.json` as centres on the output canvas.
Two constraints bound them: the caption card's top edge (near y=1412 on a
1080x1920 frame) caps how low the bottom pair can sit, and the badge's own
height caps how high the top pair can go. y=150 / y=1350 are the practical
extremes for a 357x111 badge.

Be honest about the limit: **in a tight close-up the face fills the whole frame
and no anchor clears it.** At the extremes the badge sits on hair rather than on
features, which is the best available rather than a fix. If that is not enough,
the real options are shrinking the badge or dropping the 4-position cycle for a
single fixed corner.

## Files

| Path | |
|---|---|
| `scripts/transcript-outline.py` | transcript → skimmable outline; `--find` a phrase's time |
| `scripts/cut-clips.py` | manifest → clips; crop, captions and badge in one encode |
| `scripts/handle-overlay.py` | badge rendering + ffmpeg animation graph |
| `scripts/auto-reframe.py` | per-shot framing decisions; `--mode compare` measures them |
| `projects/<id>/clips.json` | one manifest per source video |
| `config/handles/default.json` / `vertical.json` | badge style + motion, per orientation |
| `config/presets/red-card-vertical.json` | caption preset for a 9:16 frame |
| `projects/egr4Y4oZgLM/clips.json` | working example (5 episodes, handle, Ukrainian phrases) |
| `projects/egr4Y4oZgLM/clips-vertical.json` | the same five, vertical + auto-reframed |

Requires `opencv-python<5` and `scenedetect` for auto-reframe (without
scenedetect it falls back to `--mode pan`); everything else is the captions
pipeline's existing dependency set.

## Dubbing one of these into another language

Use the **video-dub** skill. It reuses this manifest and this clip's
boundaries, then renders a `…-en.mp4` alongside the original:

```powershell
python scripts/dub-clips.py --manifest projects/<id>/clips-vertical.json --only <clip-id> --outdir projects/<id>/outputs/dub
python scripts/cut-clips.py --manifest projects/<id>/clips-vertical.json --only <clip-id> --dub projects/<id>/outputs/dub
```
