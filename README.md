# KitCut

**Raw footage in. Finished video out. On your own machine.**

- You say what you want in plain words. Claude does the editing.
- Nothing is uploaded until you say "publish."
- Every decision is remembered, so any video can be changed later in one sentence.

## Start

1. Install [Claude Code](https://claude.com/claude-code).
2. Open this folder in it. Say **"Set this up."** Claude installs what's missing and renders a test video to prove it works.
3. Record something. Say **"Import today's recordings."**

No dragging files. KitCut finds the session's recordings on your PC and on a connected phone, drops duplicate copies, orders them by when they were actually shot, and knows which ones have sound. Then say what you want made.

## Capabilities

Every choice is priced before anything renders, and every render is checked
afterwards against what was asked for. That applies to all of it.

### Captions
- **Word-synced captions** burned in, the spoken word highlighted.
- **Any channel's style**, measured off their own frames rather than guessed.
- **Never lands on a face** or across the video's own lower third.

### Shorts
- **Finds the moments** in a long video, shortlisted with reasons before a cut.
- **Opens on the hook** — a clip whose point arrives late is refused, not rendered.
- **Vertical 9:16 with face tracking**, or a fixed region for a screen recording.
- **Animated social-handle badge.**

### Dubbing
- **Another language, same rhythm**: speech starts and stops with the mouth.
- **Every line measured**, and re-tuned where it does not fit its slot.
- **Free or premium voice**, captions timed from the dub itself.
- **Or replace the narration** with a written script, timed to the picture.

### Tightening one recording
- **For footage that arrives already finished** — screen, webcam and narration
  burned together, nothing to sync.
- **Shortens pauses rather than deleting them**, so nothing sounds spliced,
  and swallows the "um"s that lean on them.
- **Removes a passage you name by quoting it.**

### Screen recording + camera
- **Syncs two recordings that never were**, proven with paired frames.
- **Cuts only where the speaker is silent and the screen is still.**
- **Camera picture-in-picture**, full-frame where the screen has nothing to show.
- **Intro and outro shot separately**, with cutaway footage over them.

### Multi-camera events
- **Lines up any number of cameras** from their sound alone, to the frame.
- **Cuts between angles following the voice**; tells cameras apart by
  background or by who is in shot.
- **Scores itself** against professionally edited videos, frame by frame — and
  will tell you whether it can reproduce a given channel's style.

### Silent screen recordings
- **One film from a session of silent captures**, voice-over added later.
- **Drops dead air**, fast-forwards where only an AI panel is streaming, and
  hits a target length.
- **Finds and blurs** card numbers, CVVs, IBANs, phones, emails and addresses,
  following each one as it scrolls.
- **Two stops before publishing**: a before/after sheet, then a draft of the
  riskiest minute.
- **The last check reads the finished render**, not the plan.

### Graphics
- **Lower-third name labels**, image overlays and end cards, with entrance
  animation and the footage beneath blurred, dimmed or black-and-white.
- **Card designer**: template x brand x words.
- **Burned inside the render**, never a second encode.

### Publishing
- **YouTube upload**, confirmed on the right channel, unlisted by default.
- **Chapters from the transcript**, plus an audit of which videos lack them.

### Memory
- **Every render has a record**: what is on it, which setting controls it,
  where it went, and a journal of why.
- **Change one thing later in one sentence** — only that re-renders.
- **Stale renders flagged** when a decision changed after them.

## Requirements

| | |
|---|---|
| OS | Windows |
| GPU | Optional. KitCut finds the fastest encoder your machine has — NVIDIA, AMD or Intel — and falls back to software, which is slower but works everywhere. |
| Accounts | None. YouTube publishing and the premium dub voice are the only exceptions. |

## Not yet

Colour grading. Mac.

## Technical reference

Every command, setting and trap: [`docs/reference.md`](docs/reference.md).

## Update history

What changed and which capability it touched. Fixes that only a maintainer
would care about are left to `git log`.

```
2026-09-03
  shorts     Picking the moments became its own stage: candidates shortlisted
             with reasoning, quotes resolved and hook timing priced BEFORE
             anything is cut. Two rejected picks would have died on paper.
  shorts     A caption card sitting on the speaker's face is refused. The
             guard reads the render and runs after every vertical cut.
  captions   Whisper's split punctuation glued at the shared word loader --
             "60 ,000" reads "60,000" in captions, dub units and phrase
             anchors alike. It had been shipping on every captioned video.
  captions   grouping.wrap: a channel's own wrapping policy ends cards that
             strand a single word on a line of their own.
  shorts     Caption position measured off the channel's published shorts
             instead of eyeballed -- a still frame cannot tell a caption box
             from a black turtleneck.
  shorts     check-shorts.py, the self-test this path never had. No GPU.

2026-09-02
  platform   Setup is something Claude performs, not something the user is
             told to run.

2026-09-01
  captions   CPU encoder fallback -- captions and shorts render on a machine
             with no NVENC.
  shorts     Hook gate: a clip whose hook arrives late is refused rather than
             rendered. It had shipped twice.
  screen     film-redact -- when the secrets ARE the film, redact the finished
             cut instead of mapping back through it.
  publish    One OAuth grant per channel, so authorising a second never burns
             the first.
  platform   make-tester-repo -- the copy of this repo a stranger can be given.

2026-08-31
  screen     New pipeline: a film out of screen recordings carrying no sound
             at all -- sensitive fields tracked and blurred, voice-over added
             later, twelve stages behind one command, two review stops.
  multicam   Count the PEOPLE at the shoot, not the clusters: held-out score
             49.5% -> 63.9%, and it needed no tuning.

2026-08-30
  platform   Tooling and the user's work split behind one resolver, with the
             platform boundary enforced by the checker rather than by habit.

2026-08-27
  multicam   New pipeline: cut between cameras that shot one event, tested by
             rebuilding somebody else's finished film and scoring the re-cut
             frame by frame. Six films, stage 1 exact on all six.
  multicam   Stage 2 chooses the cut from the soundtrack alone -- 73-87% of
             the timeline on the same camera as the human editor.
  multicam   Angles identified by WHO is in frame, for the studio case where
             every camera shares one backdrop.

2026-08-26
  screencast New pipeline: one film out of a screen recording plus the camera
             take beside it -- offset measured and proved, dead air dropped,
             camera composited as a PiP.
  projects   Every video gets a folder that remembers what was done to it:
             project.json for current state, journal.md for history.
  graphics   Name labels, image overlays and designed cards, each burned
             inside the pass that was already happening.
  publish    Chapter markers written and audited from what a video says.
  platform   check-script.py, the status line, and a render progress reader.

2026-08-25
  captions   The beginning: word-synced burned-in captions, with sync proven
             on sampled frames before an encode is spent.
  shorts     Shorts cut by quoting what is said rather than by timecode;
             vertical 9:16 with a face-tracked crop; animated handle badge.
  dub        New pipeline: translate a clip and keep its cadence -- segment at
             real pauses, fit each line to its slot, retune what will not fit.
  platform   A user-level PYTHONPATH was loading another Python's packages;
             every script now re-execs into .venv with a clean environment.
```
