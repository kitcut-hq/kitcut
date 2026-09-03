# TODO

Open work, newest first. An entry earns its place by being something a future
session would otherwise have to rediscover or re-argue. Close one by deleting it
and saying where the work landed (skill, script, README section).

Traps that already bit us live in `docs/known-issues.md`; this file is for work
that has not happened yet.

---

## 1. Make shorts predictable: the roadmap

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

## 2. Vertical presets sit inside the YouTube Shorts UI

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

## 3. `_gpulock` reports the wrong hold time

`acquire()` builds the lock record — including `started_epoch` — **before** the
retry loop, so a run that queued for 20 minutes and then took the card reports
itself as having held it for 20 minutes longer than it has. Seen live this
session: the second transcribe printed `since 16:50:05Z, 24m58s` when it had
actually held the lock for about 7.

Harmless for the 6 h `MAX_AGE_S` staleness backstop, but `gpu-lock.py` is the
thing you read when a run is wedged, and it is currently lying to you in exactly
that situation. Fix: stamp `started_epoch` at the moment `_write_new` succeeds.

## 4. Carry the channel's own logo bug into the cut

Lenny's shorts carry their campfire logo top-left and the sponsor bug top-right,
both burned into the 1920x1080 source at x 25..145 and x 1750..1900. No 9:16
window contains either, so our cuts drop both. For a pitch that is a visible
gap — the first thing the owner looks for is their own logo.

`cut-clips.py` already reads `image_overlays`, so the burn is free; the missing
piece is getting a clean transparent PNG of the bug out of footage that only
ever shows it composited. Worth doing properly (key it where it sits on the flat
grey column, verify the alpha the way `html-to-image.py` does) rather than
shipping a grey box behind a logo.
