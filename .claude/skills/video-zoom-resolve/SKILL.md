---
name: video-zoom-resolve
description: Turn a Zoom local recording — including a talk the host stopped and restarted, so it arrived as several folders — into one edited film, and hand the edit to DaVinci Resolve as a real project with the cuts and a subtitle track. Covers importing from ~/Documents/Zoom, joining parts onto one clock, cutting the thinking pauses, and building the Resolve timeline live or as an FCPXML handoff. Use when asked to edit a Zoom recording or meeting, to cut pauses out of a talking-head recording, to edit something "in DaVinci Resolve" or "in Resolve", to open an edit in Resolve, to import Zoom footage, or when a recording arrives as two or more parts that belong to one video.
---

# A Zoom recording, edited, and handed to Resolve

> **Branch only. Read `docs/todo.md` #5 before using or extending this.** The
> Zoom half of this skill shipped to main as `video-zoom`; use that. The Resolve
> half here is one of two parallel answers, and its LIVE mode is measured to be
> unreachable on the free edition — external scripting is Studio-only. The other
> answer (`resolve-export.py`, OTIO-first) is the better foundation.

Two scripts you will not find in the other skills: `zoom-import.py` brings the
recording in, `resolve-edit.py` hands the finished cut to Resolve. Everything
between them is the ordinary tighten + captions path.

```powershell
python scripts/zoom-import.py --since 2026-09-01                    # survey; copies nothing
python scripts/zoom-import.py --project <id> --join --meeting "<a>" --meeting "<b>"
python scripts/tighten-cut.py --manifest projects/<id>/tighten.json --list
python scripts/tighten-cut.py --manifest projects/<id>/tighten.json --plan
python scripts/run-captions.py --input projects/<id>/outputs/<id>-tight.mp4 \
    --project <id> --id <id>-tight --style config/presets/<preset>.json \
    --emphasis-file projects/<id>/emphasis.txt --lang <xx> --height <H>
python scripts/resolve-edit.py --manifest projects/<id>/tighten.json
```

`docs/reference.md` has the reference under "A Zoom recording, and a talk
recorded in parts" and "Handing an edit to DaVinci Resolve".

There is no committed worked example for this path, and there will not be:
project folders created after the blanket `projects/` ignore stay on the machine
that cut them, and the recordings that go through here are internal ones whose
manifests carry people's and clients' names. `check-zoom-resolve.py` is the
portable statement of the same rules — read that instead.

## Step 1 — import, and let the importer refuse

A Zoom recording is a **folder**. Run `zoom-import.py` and read what it prints
before doing anything else; it knows four things you do not want to rediscover.

- **`recording.conf` is the authority.** `process` below 100 means Zoom has not
  finished converting, and the `video*.mp4.tmp` in that folder **probes clean as
  a short valid mp4**. The importer refuses; do not work around it by globbing.
  Tell the user to open the recording in Zoom and let it convert.
- **The sidecar `audio*.m4a` is the same mix as the mp4's own audio.** Never mux
  it in — it doubles the voice. (Measured: identical MD5 at 16 kHz mono.)
- **Order parts by the folder NAME, never by `creation_time`** — that stamp is
  when Zoom finished *converting*, so it orders parts by encode speed.
- **`--join` when there is more than one part.** Stream-copied, duration
  asserted against the sum. This is what gives the cut, the transcript, the
  captions and the Resolve timeline one clock.

## Step 2 — the transcript, before anything reads it

Talking-head Zoom is unrehearsed speech, so ASR gets names wrong, and a wrong
name is what a viewer notices. **Put brand and proper names in a hotword file
BEFORE transcribing** — patching afterwards leaves timings attached to words
that were never decoded:

```powershell
python scripts/transcribe-words.py <film> --out <words.json> \
    --language <xx> --hotwords-file config/vocab/<list>.txt
```

Read the transcript. Anything still wrong goes in the manifest's `corrections`
block, quoted with a `why` — those survive a re-transcription; a hand-edited
transcript does not. Keep the hotword list short: every entry nudges the decoder
on every window.

## Step 3 — cut the thinking pauses, from the sweep

`--list` prints a `min_silence × keep_pause` table. **Read it, do not pick by
eye.** On a talking head the trade is not runtime, it is jump cuts: the face is
static, so every cut is visible, and the aggressive cell of the sweep buys
another half-minute at roughly twice the cuts. Quote both numbers to the user.

A pause is **shortened, not deleted** — a briefing with every breath removed
sounds like a hostage tape, and the pauses between points are how a listener
hears that a new point started.

## Step 4 — captions, and the main points

If the ask mentions highlighting key points, that is `--emphasis-file`, not a
hand-made overlay: named phrases hold `states.emphasis` for the whole card while
the spotlight still sweeps. A phrase that matches nothing **fails the build** on
purpose. See `video-captions` for the styling rules; the two that bite here:

- Sweep `grouping.max_words × layout.max_line_width_px` before rendering.
  A language with longer words than the preset was measured on will wrap and
  orphan; widening the line usually beats carrying fewer words. Commit the
  result as its own preset with a `_measured` block rather than editing the
  parent, which would restyle every existing render.
- Emphasis must not reuse the spotlight colour, or the two signals collapse.

## Step 5 — hand it to Resolve

```powershell
python scripts/resolve-edit.py --manifest projects/<id>/tighten.json --list
```

The `--list` line tells you which mode you are in.

**If it says HANDOFF, that is the normal case, not a failure.** External
scripting is a **Studio** feature — 21.1's notes say "Advanced scripting now
requires DaVinci Resolve Studio", and on the free edition `scriptapp()` returns
`None` no matter what. `scriptapp()` returns that same `None` for "not running"
and "still starting" too, which is why the script says which.

**Do not tell a free-edition user to flip a Preferences toggle.** They do not
have one. HANDOFF still writes the FCPXML and SRT, so the edit is delivered
either way — say that instead.

**Never set `PYTHONPATH` to reach the Resolve API**, whatever Blackmagic's
README says — see CLAUDE.md for what that variable costs in this repo.
`_resolve.py` loads the extension by path instead.

## What Resolve does and does not render

Per-word caption highlighting is an ASS capability; a Resolve subtitle track
cannot express it. So the **deliverable is normally the `run-captions.py`
render**, and the Resolve project carries the same cut plus a plain SRT for
editing. Say this to the user rather than letting them assume the mp4 came out
of Resolve. If you do render from Resolve, give it its own output name — it is a
different encode of the same edit.

## Before you call it done

- `python scripts/check-zoom-resolve.py` — the folder rules, the
  inclusive-endFrame arithmetic, the FCPXML offsets and the emphasis
  matcher. No GPU, no Resolve, seconds.
- `python scripts/check-script.py --changed` — clean.
- `python scripts/project-scan.py --id <id> --check` — clean. A `STALE` from a
  manifest edit that did not affect that render is acknowledged with
  `checked_utc` **and a note saying which key changed**, never by re-rendering.
- Look at real frames: the opening frame, and one where an emphasised word is
  *not* the current word, to confirm both colours read.
- A prose note in `projects/<id>/journal.md`: what was asked, which knob moved,
  what the sweep said, and what the next session must not re-derive.
