---
name: video-resolve
description: Hand an edit made here to DaVinci Resolve (or any NLE) as an editable timeline — an OpenTimelineIO/EDL/FCP7 XML file plus an SRT — so somebody can keep cutting it in Resolve's free edition instead of receiving a flat render. Use when asked to export a timeline, an XML, an EDL, an OTIO or a project for Resolve/Premiere/Final Cut, to give a client or editor "the project file" or "the edit, not the video", to send subtitles as SRT, or to answer whether this repo can work with DaVinci Resolve and modify its files.
---

# Handing an edit to DaVinci Resolve

```powershell
# from the repo root

# 1. price it: what the timeline is, what rides along, what each format drops
python scripts/resolve-export.py --manifest projects/<id>/tighten.json --list

# 2. write it
python scripts/resolve-export.py --manifest projects/<id>/tighten.json --format all

# 3. one format, elsewhere
python scripts/resolve-export.py --manifest projects/<id>/screencast.json `
    --format otio --outdir projects/<id>/handover
```

In Resolve: Media Pool right-click → Timelines → Import → OpenTimelineIO (or
AAF/EDL/XML); File → Import → Subtitle for the `.srt`. Both work in the **free
edition** — no licence, no scripting permission.

Reference: "Handing an edit to DaVinci Resolve" in `docs/reference.md`. The
research behind every claim here — including why we do NOT write `.drp` files —
is `docs/davinci-resolve.md`.

## The project folder comes first

Every video lives in `projects/<id>/` — its manifests, its content dirs, and two
committed metadata files. Before exporting, read `projects/<id>/project.json`
(which render is current, what is burned onto it) and skim `journal.md` if the
ask touches past decisions. The exporter records the handover itself; end the
session with a prose note in `journal.md` saying who the timeline went to and
what they were told it does not carry.

## Step 1 — there must be a keep-list

The exporter reads the keep-list the cutter writes, not the render:

- `tighten-cut.py --manifest <m> --plan` → `<manifest>.cuts.json`
- `screencast-cut.py --manifest <m> --plan` → `<id>.cuts.json`

If neither exists the exporter refuses and prints the command to make one. Both
dialects are read automatically.

## Step 2 — run `--list` and read the two things it prints

**The tracks.** V1 is the picture (screen where the cut says `pip`, camera where
it says `full`), V2 is what sits over it (the PiP, or a bookend's b-roll), A1 is
the sound. V1 alone should already be a watchable rough cut.

**The drops.** This is the honesty report, and it is the thing to paste to
whoever asked. Cut decisions travel; pixels do not — the PiP transform, crop
windows, the caption card, redaction blurs and the loudnorm stay in the render.
Never promise "the same video, editable": promise the cut.

## Step 3 — pick the format for the receiver

| | |
|---|---|
| `otio` | default and best. Paths, both video tracks, the audio track, markers with notes |
| `edl` | when the receiver's tool is old. One video track, no paths, no markers, and the frame rate must be typed into their import dialog |
| `fcpxml` | FCP7 XML, when they asked for "an XML". Needs every source's duration, so the media must be readable — it refuses by name otherwise |
| `srt` | the words. Resolve draws its own subtitle: our caption look does not travel, and saying so up front avoids the "why do they look wrong" round trip |

`--format all` writes the preset's list (`config/resolve/export.json`).

## The traps

- **A keep-list is not the film.** Bookends live in the manifest, so a keep-list
  can under-run the render — 22.5s on `claude-demo`. The exporter builds
  bookends as clips and refuses when the totals still disagree. Do not reach for
  `--skip-bookends` to make a refusal go away: it exports the body alone, and
  the timeline really will be short.
- **A bookend bounded by a quote** (`start_text`) is refused rather than guessed
  at — resolve it to seconds with `screencast-cut.py --list` first.
- **29.97 and 59.94 need drop-frame timecode**, which the EDL writer handles;
  the receiver still has to be told the rate, because an EDL does not state it.
- **Reel names truncate to 8 characters** in an EDL. That is the format. It is
  why `otio` leads.

## Never

- **Never write, patch or "fix" a `.drp`, a `.drt` or Resolve's disk database**
  as part of an export. They are a closed format whose effect payloads are
  hex-wrapped structures with no schema; the supported door is interchange.
  (Repairing a crashing project someone hands us is a different job — see
  `docs/davinci-resolve.md` §2 — and it is a separate script, not this one.)
- **Never add `opentimelineio` to `requirements.txt`** for this. The `.otio` is
  hand-written JSON on purpose; the library is only ever a check.
- **Never change a writer without running** `python scripts/check-resolve.py`
  (56 checks, no Resolve, no media, ~1s), then
  `python scripts/check-script.py --changed`.
