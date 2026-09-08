---
name: video-zoom
description: Turn a Zoom local recording — including a talk the host stopped and restarted, so it arrived as several folders — into one edited film with the thinking pauses cut and captions that highlight the main points. Covers importing from the Zoom recordings folder, joining parts onto one clock, keeping people's names out of the committed ASR vocabulary, and the caption emphasis pass. Use when asked to edit a Zoom recording or meeting, to cut pauses out of a talking-head recording, to import Zoom footage, when a recording arrives as two or more parts that belong to one video, or when captions should highlight key points or takeaways.
---

# A Zoom recording, edited

`zoom-import.py` is the one script here you will not find in the other skills.
Everything after it is the ordinary tighten + captions path.

```powershell
python scripts/zoom-import.py --since 2026-09-01                    # survey; copies nothing
python scripts/zoom-import.py --project <id> --join --meeting "<a>" --meeting "<b>"
python scripts/tighten-cut.py --manifest projects/<id>/tighten.json --list
python scripts/tighten-cut.py --manifest projects/<id>/tighten.json --plan
python scripts/run-captions.py --input projects/<id>/outputs/<id>-tight.mp4 \
    --project <id> --id <id>-tight --style config/presets/<preset>.json \
    --emphasis-file projects/<id>/emphasis.txt --lang <xx> --height <H>
```

`docs/reference.md` has the reference under "A Zoom recording, and a talk
recorded in parts". `check-zoom.py` is the portable statement of the rules
below — read it rather than looking for a committed worked example, because
project folders created after the blanket `projects/` ignore stay on the machine
that cut them, and these recordings are internal ones whose manifests carry
people's and clients' names.

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
  asserted against the sum. This is what gives the cut, the transcript and the
  captions one clock.

## Step 2 — the transcript, before anything reads it

Talking-head Zoom is unrehearsed speech, so ASR gets names wrong, and a wrong
name is what a viewer notices. **Put brand and proper names in a hotword file
BEFORE transcribing** — patching afterwards leaves timings attached to words
that were never decoded.

`--hotwords-file` is **repeatable**, and that is the point: the committed
vocabulary in `config/vocab/` is shared with everyone who uses these scripts,
and the people in your recordings are not theirs to have.

```powershell
python scripts/transcribe-words.py <film> --out <words.json> --language <xx> \
    --hotwords-file config/vocab/<domain>.txt \
    --hotwords-file config/vocab/names.local.txt
```

**Never add a person's or a client's name to a committed list.** `*.local.txt`
under `config/vocab/` is gitignored for exactly this. If you find one in a
committed file, move it.

Read the transcript afterwards. Anything still wrong goes in the manifest's
`corrections` block, quoted with a `why` — those survive a re-transcription; a
hand-edited transcript does not. Keep hotword lists short: every entry nudges
the decoder on every window.

## Step 3 — cut the thinking pauses, from the sweep

`--list` prints a `min_silence × keep_pause` table. **Read it, do not pick by
eye.** On a talking head the trade is not runtime, it is jump cuts: the face is
static, so every cut is visible, and the aggressive cell of the sweep typically
buys another half-minute at roughly twice the cuts. Quote both numbers.

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

## If they ask for it in DaVinci Resolve

Say what is true rather than promising the app. Two facts decide every answer:

- **External scripting is Studio-only.** Resolve 21.1's notes say "Advanced
  scripting now requires DaVinci Resolve Studio", and on the free edition
  `scriptapp("Resolve")` returns `None` from any external interpreter. Do not
  send somebody hunting for a Preferences toggle that their edition does not
  have.
- **The caption look does not travel.** Resolve imports SRT, VTT, TTML and XML
  subtitles, but not ASS — and ASS is what carries the per-word spotlight and
  the emphasis colour. Resolve draws its own subtitle in its own style.

Handing the cut over as an editable timeline (OTIO/EDL/FCP7 XML + SRT) is real,
works in the free edition, and already exists: `resolve-export.py`, with the
`video-resolve` skill. Use that — do not write a second exporter.

## Before you call it done

- `python scripts/check-zoom.py` — the folder rules, the part ordering and the
  emphasis matcher. No GPU, seconds.
- `python scripts/check-script.py --changed`, then
  `python -m ruff check <files>` and `python -m ruff format <files>`.
- `python scripts/project-scan.py --id <id> --check` — clean. A `STALE` from a
  manifest edit that did not affect that render is acknowledged with
  `checked_utc` **and a note saying which key changed**, never by re-rendering.
- Look at real frames: the opening frame, and one where an emphasised word is
  *not* the current word, to confirm both colours read.
- A prose note in `projects/<id>/journal.md`: what was asked, which knob moved,
  what the sweep said, and what the next session must not re-derive.
