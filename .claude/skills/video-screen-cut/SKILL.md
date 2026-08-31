---
name: video-screen-cut
description: Edit one or more screen recordings that carry NO usable audio into a single film — drop the dead air, fast-forward the stretches where only an AI side panel is streaming, and blur card numbers, CVVs, IBANs, phone numbers, emails and delivery addresses before anything is published. Use when asked to edit a screen recording or screencast that has no narration, to cut the pauses or boring parts out of a demo/desktop capture, to speed up or fast-forward parts of a screen recording, to hide or blur sensitive data (bank card, CVV, phone number, address, balance) in a video, or to turn a session of raw desktop captures into one watchable video with a voice-over added later.
---

# A film out of silent screen recordings

**Wrong skill?** If the screen recording is paired with a **camera take that
carries the sound**, use `video-multicam` (`sync-tracks.py` +
`screencast-cut.py`) — it cuts on speech and composites the two. This skill is
for recordings with **no usable audio at all**, where the picture is the only
signal and the voice-over is added afterwards.

```powershell
# from the repo root
python scripts/screen-activity.py --src projects/<id>/sources/<f>.mp4 --list --probe-motion
python scripts/scan-pii.py        --src projects/<id>/sources/<f>.mp4 --report --emit
python scripts/screen-cut.py      --manifest projects/<id>/screen.json --list --sweep
python scripts/screen-cut.py      --manifest projects/<id>/screen.json --target 8:00 --sheet projects/<id>/temp/sheet
python scripts/screen-cut.py      --manifest projects/<id>/screen.json --target 8:00
```

The worked example is `projects/books-giveaway/screen.json`. README has the
reference under "A screencast with no soundtrack at all".

## The project folder comes first

Every video lives in `projects/<id>/` — its manifests, its content dirs, and two
committed metadata files. Before doing anything, read
`projects/<id>/project.json` (create the folder with
`python scripts/project-scan.py --init <id>` if this is new) and skim
`projects/<id>/journal.md` if the ask touches past decisions. `screen-cut.py`
records its own renders; anything you run by hand you record yourself. End the
session with a prose note in `journal.md` for the next one.

## Check the audio before you plan anything

This whole pipeline exists because of one measurement. Run it first:

```powershell
ffmpeg -hide_banner -nostats -i <src> -af volumedetect -f null - 2>&1 | Select-String "mean_vol|max_vol"
```

`mean_volume: -91.0 dB` **and** `max_volume: -91.0 dB` is digital silence — not
room tone, literally zero samples. Windows' Game Bar window capture does this
when no microphone is selected. If you see that, `screencast-cut.py` cannot
help: every silence threshold it has resolves to "cut everything".

Do not skip to transcription to check. On this footage one recording had a
*little* ambient noise (-56 dB mean) and looked promising; faster-whisper
returned **0 words** from four minutes of it. Measure, don't hope.

## Order the sources by when they were shot, not by filename

Windows names a capture for the moment it *stopped*; Android names a screen
recording for when it *started*; a phone camera file is stamped in **UTC** while
the desktop files are local. Sorting a mixed set by name silently interleaves
them wrong.

- `PXL_YYYYMMDD_HHMMSS.mp4` — UTC, from the camera roll (`DCIM/Camera`)
- `screen-YYYYMMDD-HHMMSS-*.mp4` — local, an Android **screen recording**, and
  it lives in `Movies/`, **not** `DCIM/Camera`. Look there before concluding
  there is no screen recording on the phone.
- `Recording YYYY-MM-DD HHMMSS.mp4` — local, Windows Game Bar

Also: Windows writes the same capture to `Videos\` **and**
`Videos\Screen Recordings\` with timestamps a few seconds apart. They are byte
identical — check with `head -c 5000000 | sha1sum` before treating them as two
takes.

`Shell.Application` sorts MTP listings as **strings**, so `9/9/2025` sorts above
`8/31/2026`. Sort by the date embedded in the filename instead. Getting footage
off the phone: see the MTP section of the `video-multicam` skill.

## Transcode once, before anything else

```powershell
python scripts/make-proxies.py --manifest projects/<id>/screen.json --verify
```

Every other pass decodes the source and throws most of it away in its first
filter, and that decode is the dominant cost of the pipeline. One transcode to
the canvas fit size, recorded on each source, and `screen-cut.py` picks it up
automatically (`--no-proxy` opts out). Here: 4.5 GB -> 38 MB.

This is not a quality trade, because **every rectangle in this pipeline is a
fraction of the frame, never a pixel box** — proxy and original are
interchangeable, so there is no "apply the decisions to the big one" step. The
scale to 1080p has to happen anyway; doing it once is less resampling, and
`screen-cut.py` skips the scale filter when the input already matches.

**Do not proxy for `scan-pii.py`.** OCR is resolution-bound, so shrinking costs
recall on the most expensive step. Scan the originals; use `--skip-static` to
cut the frame count instead.

## Measure the picture, per region

`screen-activity.py` counts the fraction of pixels that changed by more than a
noise floor, per sampled frame. Give it **named regions** — without them there
is nothing to fast-forward *with*, because whole-frame activity cannot tell the
human working from an AI streaming text.

```json
"regions": { "main": [0, 0, 0.748, 0.98], "panel": [0.748, 0, 0.252, 0.98] }
```

| what is moving | what the cut does |
|---|---|
| `main` | keep at `keep_speed` |
| only `panel` | run at `speed` |
| nothing | drop |

**Find the divider, do not assume it.** `--probe-motion` reports which
eighth-of-the-frame cells move during otherwise-still stretches; a side panel
shows up as one column on every recording. Confirm it by taking the strongest
long vertical edge in the right half of a frame at several timestamps and using
the mode — on this footage that gave `x = 0.748` on all five recordings that had
the Edge panel open, while a single timestamp gave three different answers
because a dialog was on screen.

**Ignore the spinners.** A thinking animation, a caret, a clock or the
recorder's own timer keeps a dead screen above any threshold forever. `ignore`
rectangles are frame **fractions** so they survive a resolution change. Phone
screen recordings want `0,0,1,0.04` for the status bar.

## Blur before you cut, and find it by reading, not scrubbing

Run `scan-pii.py` on **every** source before planning the edit. It samples,
OCRs, and matches the *shape* of a secret — Luhn-valid 13–19 digits, three
digits next to "CVV", `+380` and nine more, `UA` and 27. `--emit` prints `blur`
entries ready to paste into the manifest.

Three things that decide whether it works:

- **Luhn is what makes the card rule usable.** An order number like
  `#1806413786` is ten digits in a row; without the checksum every confirmation
  page is a false positive.
- **Match the mask's shape, not its glyph.** The bank draws a bullet, one OCR
  model returns `----`, another `****`. Requiring a full 27-character IBAN found
  *nothing*, because the field is always drawn part-masked.
- **`--skip-static` is what makes it finish.** OCR is the entire cost and a
  screencast holds still. A frame close to the last one *read* is skipped and
  the previous reading is re-stamped at the current time, so windows stay
  accurate while the call count drops with the stillness, not the length.

Blur runs **in source time, upstream of the trim** — same trap as the name
label's film-time `at`. A window verified against a source frame stays verified
after the cut moves everything. Default `mode` is `pixelate`, not blur: a soft
blur reads as a focus artefact and invites someone to try to sharpen it back.

- **The country code is optional.** Requiring `+38` let a panel summary reading
  `(Київ, відділення 57, 0939589090, Стрельченко Марія …)` straight through —
  city, branch, phone and full name, in the national `0XX` form.

**It is a net, not a clearance.** OCR misses rotated, low-contrast and
partly-scrolled text, and cannot know that a first name plus a delivery branch
identifies a real person. Look at the `--sheet` frames before you encode, and
**ask the person whose footage it is** what to hide — the answer is routinely
wider than the request. Asked here for "phone number, card and CVV", the footage
also held recipients' names, phones and home addresses, plus a bank balance; the
answer was "everything, but keep the city name".

Then **scan the render itself** — it is short and 1080p, so it costs minutes,
and it checks the thing you are about to publish:

```powershell
python scripts/scan-pii.py --src projects/<id>/outputs/<id>.mp4 --report --fps 0.25
```

Anything that comes back is a rect that did not land. Fix the manifest and
re-render; never trim the film to hide it.

Keep hand-written rects in a `blur_extra` list on the source, so regenerating
the scanned ones cannot silently drop the rects that exist *because* the OCR
missed something.

A handheld shot of a screen needs **one generous rect per field**, not the
per-frame boxes the scanner reports — the camera moves, so union them.

## Hold, or the film strobes

Thresholding raw activity gave **1094 segments** and a film flickering between
1x and 6x several times a second. `hold` dilates each region's boolean track
forward and back ("it moved within the last second, so it is still moving");
`panel_hold` is longer because streaming text is burstier than a mouse. Same
footage: **579 segments**.

Short runs are then absorbed into the **longer neighbour**, not promoted back to
keep — half a second of panel flicker inside a two-minute wait belongs to the
wait, and promoting it put a hitch in the middle of every fast-forward. `air` is
handed back at **1x**; handing it back sped is a lurch either side of every join.

## Price the length before you encode

`--list` shows where the runtime goes, and it is usually not where you'd guess:
on this footage only 3:17 of 47 minutes was truly dead, because the spinner means
something is nearly always moving. Raising `speed` 6x→12x moved the film 25:27 →
23:36 and no further, because **21:45 was held at 1x**. That is what
`keep_speed` is for.

`--target M:SS` solves for both speeds together, keeping the manifest's
panel:work ratio. `hold_1x` windows are forced to 1x and do **not** scale — use
them for the things the film exists to show, because no motion metric knows
which page matters. The solver reports the floor they impose.

`--sweep` prices a grid; `--sheet` writes a frame per kept segment and per blur
rect. Both encode nothing.

## Render with no audio

`-an`, deliberately. The sources are silent and the voice-over is recorded
against the finished cut; muxing a silent track invites a later pass to mix onto
it and produce nothing. The render asserts its own duration against the plan
before it reports success.
