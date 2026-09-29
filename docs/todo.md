# TODO

Open work, newest first. An entry earns its place by being something a future
session would otherwise have to rediscover or re-argue. Close one by deleting it
and saying where the work landed (skill, script, README section).

Traps that already bit us live in `docs/known-issues.md`; this file is for work
that has not happened yet.

---

## 7. Studio films past ~15 minutes: scenes as the unit of work

Measured on the 8-minute film llwtme (docs/known-issues.md KI-034): the film is one `film.js`,
written by one Claude conversation that grows with it -- 73k tokens at the start, 371k at the end,
the picture's first draft one reply of 57k tokens. Opus 5.5 allows 128K per reply and 1M per
conversation, so the picture cannot be written in one reply past ~18 minutes of film, and the
conversation outgrows the window past ~25; well before that each reply re-reads everything, so
cost grows faster than length, and one stall puts the whole film at risk. The Phase 1 fixes
(write in parts, the stall watchdog, lean narration results) push the limits out; they do not
remove them.

The redesign, agreed 2026-09-29, to build behind a switch for films over ~5 minutes (the
step-by-step implementation plan, files and tests: docs/studio-scenes-plan.md):

1. **Engine.** `SK.scene({lines: [a, b], draw(t, local)})` registered by `scenes/NN-*.js` files
   loaded after `cast/`; the film's own draw composes the scenes covering t. A film is then a
   shared look (`film.js`: palette, helpers, camera) plus a file per scene. Single-file films keep
   working. "Every frame is a pure function of t" still holds, which is what lets a scene be
   re-rendered alone.
2. **Studio, three passes.** A director conversation writes the script, records the narration and
   plans the scenes (line ranges, what each shows). Each scene is written and reviewed in a fresh
   conversation carrying only the style guide, the shared look, its own lines and its neighbours'
   last and first frames -- bounded whatever the film's length, and two or three can run at once.
   An editor pass looks at the whole film's contact sheet for continuity.
3. **Checkpoints.** A scene is done when its stills pass; a crash, stall or restart costs one scene,
   and a resume continues from the next unfinished one -- no giant session to replay.
4. **Render per scene,** cached, so a changed scene re-renders alone (the renderer already works in
   parallel chunks).
5. **Prove it first:** a stubbed-Claude ladder at 8, 16 and 30 minutes asserting every conversation
   stays bounded and a killed scene recovers on its own; then real 2-, 8- and 16-minute films on
   the VM's login against today's pipeline, for quality, cost and time. Adopt where it wins.

---

## 1. Take an edit BACK from DaVinci Resolve

**Half of this landed 2026-09-08.** `resolve-export.py` writes the cut as
`.otio` / `.edl` / FCP7 `.xml` / `.srt` with the decisions as markers,
`check-resolve.py` pins it (56 checks, no Resolve, no media), and
`config/resolve/export.json` carries the defaults. The research is
`docs/davinci-resolve.md`; the reference section is "Handing an edit to DaVinci
Resolve"; the skill is `video-resolve`.

What is still open, and it is the more valuable direction:

- **`resolve-import.py`** — a human fine-trims in Resolve (free), exports
  `.otio`, and we render it here with NVENC, the captions, the labels, the
  redaction and the project record. Resolve becomes the front end for what a
  person is better at, and the finishing stays where it is gated and recorded.
  Start with `.otio` only (plain JSON, exact) and refuse EDL by name: an EDL
  carries no media paths, so a keep-list built from one is a guess.
- **Verify the export against a real Resolve.** Nothing here has opened one.
  Five questions in `docs/davinci-resolve.md` §7 need a machine with Resolve
  on it — chiefly whether OTIO import honours markers, relinks by path, and
  what it does with a `LinearTimeWarp` (which is what decides whether
  `screen-cut.py`'s speed ramps can travel at all).
- **Speed ramps.** `screen-cut.py` produces 6x segments and the exporter does
  not write them yet; the shape is a `LinearTimeWarp` on the clip, and it is
  worth writing only once the question above is answered.

## 2. Make shorts predictable: the roadmap

**The diagnosis, from the 2026-09-03 session** (four shorts, two channels,
every defect the user or a late check caught): each failure was either a
hand-chosen number validated *after* the encode (caption margin, crop zoom —
three re-renders of one clip), or a judgement step living in skill prose
(frame review missed a card across a mouth twice). The one pre-existing guard
that lived in the render path as code — the hook gate — caught its error before
anything was spent. The fix is therefore structural, and both halves of it are
already proven elsewhere in this repo: `screencast-pipeline.py` (one command,
cached stages, explicit review stops, gates that read the render) and the
multicam round-trip corpus (the only thing that tells a result from a fit).
Shorts has neither. In leverage order:

**1a. `shorts-pipeline.py` — one command owns the sequence.** Stages: fetch →
transcribe → derive channel style (1b, skipped when the preset exists) → pick
episodes (propose boundaries + hooks + rejected-alternative notes, **stop for
review**) → reframe → solve placement (1c) → render with gates inside →
review sheet (1d, **stop**) → record + journal. Cached and checkpointed like
the screencast pipeline, prints the known-issues entries for its stages.
Removes: forgotten steps, order drift, and review-by-whenever-I-think-to-look.

**1b. `channel-style.py` — style measuring in code** (absorbed from the old
item 1). Takes a channel URL or reference short; finds the caption band by
temporal median across frames (a single frame cannot tell a caption box from a
black turtleneck — this is what cost time by hand); measures card colour,
opacity, radius, cap height, pads, margin, case, words/card; samples the brand
accent from the logo bug where it sits on a bright background; emits a preset
stub with everything in `_measured` and a `--list` mode. ~20 min of hand
pixel-poking per channel becomes a minute.

**1c. Placement becomes a solver, not a setting.** The decision tree now in
skill Step 0c is an algorithm written as prose; make it code. Run
`check-caption-space`'s geometry on the PLAN: sample faces through the intended
crop before encoding, intersect with the forbidden zones (the source-graphics
map from the channel measurement, the Shorts UI band), and output per clip:
a margin, or above-the-head, or letterbox. The preset keeps the style; the
position is computed per framing. Kills the whole class "margin measured on
another framing" — the three Bloomberg re-renders become zero. The post-render
check stays as the backstop, because the solver and the render can still
disagree (that is what backstops are for).

**1d. A review sheet as the stop.** One HTML per run — first frame, worst-
clearance frame, caption-band strip, hook timing per clip — on the
`redaction-review.py` pattern: nothing publishes unapproved, and approval is
recorded in the manifest. One look at one page instead of scrubbing N files,
which is the sampling-luck failure that shipped the mouth card.

**1e. `check-shorts.py` — DONE 2026-09-03.** Landed as
`scripts/check-shorts.py` (33 checks: hook gate, `resolve()` padding, crop
windows, grouping typography end to end through real font metrics on the real
orphan-producing word span, caption-space geometry, `clip_style` overrides,
`capitalize_i`), wired into CLAUDE.md pipeline 2, the README script table and
the `video-shorts` skill. Proven in both directions: passes clean, and
re-injecting the two historical guard bugs (0.7 floor, below-only gap metric)
is detected. The one gap it does not close: nothing *forces* it to run after
an edit — that is `check-script.py --changed`'s reminder at best. 1a's
pipeline should run it as stage zero.

**1f. The two finished projects become the golden corpus.** After any tooling
change, re-run the *plan* stages (no encodes — seconds) on the committed
manifests + transcripts of `g-YDNJcyuck` and `zMvBMfj4cSQ` and diff the
decisions: boundaries, groups, placements, gate verdicts. The multicam
round-trip, at the plan layer. New projects join the corpus by existing.

**1g. Refuse unmeasured defaults on a new channel.** `cut-clips.py` warns (or
refuses without an override flag) when the caption style carries no
`_measured` block — Step 0 becomes enforced instead of advised, which is the
difference between a standard and a hope.

**1h. Hand-edits survive regeneration — DONE 2026-09-03.** `merge_sidecar()`
in `auto-reframe.py`: entries carrying `_`-prefixed markers are kept (a
file-level `_comment` protects every existing entry, new clips still land),
`--force-regen` overrides, refusals name the marker they honoured. Proven live
against `g-YDNJcyuck`'s hand-edited sidecar (semantically identical after a
real regen) and covered by 8 checks in `check-shorts.py`. Unmarked edits still
only WARN — marking them is the contract, taught in the `video-shorts` skill.

Sequencing: 1e first (it protects everything else while it is built), then
1c (biggest error-class kill), then 1a wrapping it all, 1b/1d inside 1a,
1f/1g/1h as they land. Each obeys the house rules: free mode, README section,
skill update, `check-script.py --changed` clean.

## 3. Vertical presets sit inside the YouTube Shorts UI

`config/presets/red-card-vertical.json` uses `bottom_margin_px: 170`, which
scales to **302 px** from the bottom of a 1080x1920 frame. The Shorts UI (title,
channel line, CTA) occupies roughly the bottom 380 px.

Measured against a channel that does this correctly: Lenny's Podcast parks its
caption box 602 px above the frame bottom. The three presets written in this
session use 339 on the authoring canvas = 602 px for that reason.

**Open:** whether `red-card-vertical` should move too. It cannot be changed
silently — every already-rendered short that used it goes STALE — so this wants
a deliberate pass with `project-scan.py --all --check` and a journal note per
project, not a one-line edit.

## 4. `_gpulock` reports the wrong hold time

`acquire()` builds the lock record — including `started_epoch` — **before** the
retry loop, so a run that queued for 20 minutes and then took the card reports
itself as having held it for 20 minutes longer than it has. Seen live this
session: the second transcribe printed `since 16:50:05Z, 24m58s` when it had
actually held the lock for about 7.

Harmless for the 6 h `MAX_AGE_S` staleness backstop, but `gpu-lock.py` is the
thing you read when a run is wedged, and it is currently lying to you in exactly
that situation. Fix: stamp `started_epoch` at the moment `_write_new` succeeds.

## 5. Carry the channel's own logo bug into the cut

Lenny's shorts carry their campfire logo top-left and the sponsor bug top-right,
both burned into the 1920x1080 source at x 25..145 and x 1750..1900. No 9:16
window contains either, so our cuts drop both. For a pitch that is a visible
gap — the first thing the owner looks for is their own logo.

`cut-clips.py` already reads `image_overlays`, so the burn is free; the missing
piece is getting a clean transparent PNG of the bug out of footage that only
ever shows it composited. Worth doing properly (key it where it sits on the flat
grey column, verify the alpha the way `html-to-image.py` does) rather than
shipping a grey box behind a logo.

## 6. The Resolve live API: decided against, and what to keep if that changes

Two sessions built toward the same thing at once. **Resolved in favour of
interchange** -- `resolve-export.py` and `docs/davinci-resolve.md` above: OTIO
leads, EDL is the universal fallback, FCP7 XML carries paths, SRT carries the
words, and all of it works in the **free** edition.

The other answer drove the running application through `fusionscript`. It is not
merged and its branch is gone; the commit is kept as the tag
**`archive/resolve-live-api`** (`git show archive/resolve-live-api`) so nothing
was destroyed, but treat it as a reference, not a starting point -- Resolve's API
moves, and the facts below are the expensive part, not the code.

**Why it was rejected, measured rather than argued:** external scripting is
**Studio-only**. Resolve 21.1's notes say "Advanced scripting now requires
DaVinci Resolve Studio", and on the free 21.1 `scriptapp("Resolve")` returns
`None` from both this repo's venv and Blackmagic's own bundled `ResolvePython`.
A live mode nobody on the free edition can reach is a maintenance cost with no
user, and the 21.1 MCP server sits behind the same licence. **Never tell a
free-edition operator to switch external scripting on** -- their build has no
such preference, and sending them to look for it costs their trust in whatever
you say next. That mistake was made in the session that wrote this.

**If a Studio machine ever justifies the live API, three things are worth
rebuilding rather than rediscovering:**

1. **Reach the API without setting `PYTHONPATH`.** Blackmagic's README tells you
   to export `RESOLVE_SCRIPT_API`, `RESOLVE_SCRIPT_LIB` and `PYTHONPATH`. Do not
   export the third -- CLAUDE.md documents the day that variable cost this repo,
   and `_env.py` exists to undo it. The `Modules/DaVinciResolveScript.py` shim it
   wants on the path does nothing but load the `fusionscript` extension from a
   known file, so load it directly instead:
   `importlib.machinery.ExtensionFileLoader("fusionscript", <path to
   fusionscript.dll/.so>)`, then `spec_from_loader` / `module_from_spec` /
   `exec_module`, then `mod.scriptapp("Resolve")`. Probe the per-OS install
   paths with `os.path.exists()` and let `$RESOLVE_SCRIPT_LIB` override. The
   extension loads fine into the project venv, so the bundled interpreter (which
   has no pip, and so cannot see this repo's dependencies) is not needed.
2. **Diagnose a failed connection three ways.** `scriptapp()` returns the same
   `None` whether Resolve is absent, still starting, or refusing -- so check for
   the library, then for the process, and only then report a refusal, naming the
   edition. One `None` and three causes is otherwise an unanswerable support
   question.
3. **Resolve's `endFrame` is INCLUSIVE.** A half-open `[start, end)` range in
   seconds becomes `endFrame = last frame`, not one past it. Getting it wrong
   lengthens every segment by a frame, and on a 68-segment timeline that is
   nearly three seconds of drift that surfaces only as late audio ten minutes
   in. Convert in exactly one function and pin it with a fake media pool, the
   way `check-resolve.py` pins the interchange arithmetic.

Do not open a third implementation.

## 7. Ship the collage look on kitcut.ai

**Built 2026-09-28 on branch `sketch-collage`, not released.** A third studio look, `collage`:
an image model paints single objects cut out of paper (`sketch-paint.py` `"cutout": true`,
openai/gpt-image-2.5-flare with real alpha, ~$0.012 each) and Claude builds pages round them
with `sketch/collage.js` (sheets, tape labels, stamps, type, marker lines, ransom letters, the
stop-motion nudge). Brief: `studio/looks/collage.md`; example: `config/sketch/collage-example/`;
reference: "Collage films" in `docs/reference.md`. It answers a Runway + Opus 5.5 demo
(@notiansans, 2026-09-28): the studio, given that post's own prompt (60 s, history of ice cream,
"newspaper cutout / mixed media"), made a film at its level with no human edits in 21 minutes --
17 cut-outs $0.20, voice $0.11, Claude $4.43 at API prices, 43 turns.

**Decided 2026-09-29 (the owner approved):** a third *look* people pick -- Hand-drawn, Painted,
Collage -- not capability checkboxes: people choose by the picture they want, only tested
combinations can be promised, a ticked box becomes an order Claude must obey, and every
capability is prompt Claude re-reads each turn at one flat price per second. Underneath, a look
is a recipe of capabilities (`film.CAPS`, `RECIPES`), so parts can later move between looks
(cut-outs in Painted, collage pieces in Drawn), each after its own bake-off. Checkboxes fit only
delivery switches (no music, burned captions, 9:16), later. The plan: the owner's
`concurrent-purring-biscuit` plan file, 2026-09-29.

**Done 2026-09-29:** rebased onto studio-poc; looks as recipes of capabilities, prompts and new
films byte-identical for all three looks; collage.js an opt-in engine module (the jelly
branch's mechanism); the labels ("painting the cut-outs"), `/api/limits` cut-outs, the check
tool covering `engine/collage.js`, a drawn film refused it; Cyrillic stand-in faces (IBM Plex
Mono added); the stop-motion clock dividing 30 fps; the studio's copy of the example without
its newspaper (196 -> 189 KB); collage direction and recent-films rows; `bakeoff.py --look`,
`grade_extra` and the `collage` set (9 prompts).

Open, in order:
- **Run the bake-off** (`studio/README.md`, "Two looks from one tree"): collage and painted on
  all nine, drawn on three; the owner watches the collage films and says go. The bar: all
  made with no human edits; professional within 0.25 of painted; fits the subject 4+ on 7 of
  9; childish at most 0.3 on the serious ones, the bedtime control still fits; a newspaper on
  at most 1 of the 4 prompts where one is wrong; no missing Cyrillic; Claude's cost at most
  1.3x painted's; if suez (120 s) fails, launch collage capped at 60 s.
- **The site** (sketch-studio, a worktree from `origin/main`): three preview tiles for the
  picker, the MCP enum and its descriptions ("when the idea names a style, pick the look that
  matches"), projects, the gallery and film-page labels, pricing and privacy copy, the docs
  (looks.md: painted's "collage" style becomes "paper-cut illustration"), the page mirror.
- **VM pre-flight** before the ship: `import cv2` and WebP in the VM's venv, OpenRouter allows
  `openai/gpt-image-2.5-flare`.
- **Narration length, every look**: the first message asks for 2.2 words a second; Gemini reads
  nearer 1.9 (the collage run re-recorded four times to fit 60 s; by hand, 140 words ran 72 s
  against a 58 s plan). Measure over recent films and lower it -- a brief change, so bake-off.
- **Cost**: the collage prompt is ~189 KB against ~133 KB. The studio's collage film called
  nothing in props.js (59 KB of every prompt): leaving it out of collage films is a cost test
  of its own. Separately, `lib/plans.js` `filmCost` is below measured cost in every look
  (filmCost(60) $2.73; the 60 s collage film $4.74 at API prices).
- **Release** with the studio-vm skill, after the user approves; then merge `sketch-collage`
  into `studio-poc` (`--ff-only` after a rebase).
