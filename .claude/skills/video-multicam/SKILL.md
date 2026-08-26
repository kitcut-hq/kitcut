---
name: video-multicam
description: Cut a film out of a screen recording plus a separate camera take of the person narrating, when the two are unsynchronised and the screen recording has no usable audio. Measures the offset between the recordings and proves it with paired frames, drops the pauses where the speaker is silent AND the screen is static, and composites the camera as a square picture-in-picture over the screen in one NVENC pass, opening and closing full-frame on the camera where the screen was not yet rolling. Use when asked to sync a screen recording with a phone/camera recording, to cut the dead air or long pauses out of a screencast, to put a webcam or talking head in the corner of a screen capture, or to turn a demo recording into an edited video.
---

# A film out of a screen recording and a camera take

```powershell
cd C:\instafill\video-editing
python scripts/sync-tracks.py    --manifest config/screencast/<id>.json --verify
python scripts/screencast-cut.py --manifest config/screencast/<id>.json --list
python scripts/screencast-cut.py --manifest config/screencast/<id>.json
```

The worked example is `config/screencast/claude-demo.json`. README has the
reference under "A screencast out of two recordings".

## Get the footage off the phone first

A phone is an MTP device with no drive letter, so `Copy-Item` cannot see it:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/import-iphone.ps1 -Days 1 -List
powershell -ExecutionPolicy Bypass -File scripts/import-iphone.ps1 -Days 1
powershell -ExecutionPolicy Bypass -File scripts/import-iphone.ps1 -DeviceName 'Pixel 5' -Days 60
```

Zero items listed means the phone is **locked or untrusted**, not broken. A
device missing from `This PC` entirely means it is unplugged.

## Order of work

1. **Import**, then `ffprobe` for real. Sizes and MTP timestamps are estimates;
   duration, fps and rotation are not known until the file is local.
2. **Transcribe the camera audio** — `transcribe-words.py` onto the extracted
   `.m4a`. Everything downstream keys off it: the film's in and out points, the
   sync anchors, and the `--list` column showing what is said in each segment.
3. **Sync**, and read the residuals.
4. **`--list`**, and read the timeline.
5. **Render**, then watch it.

## The part that needs judgement

**Which recording is the master.** The camera, nearly always. It has the sound
and it brackets the screen recording at both ends. Cutting the film to the
screen recording's span throws away the opening sentence and the sign-off.

**Whether the rotation tag is true.** Extract one frame and look. A phone lying
flat writes a rotation the footage does not have; a phone held upright writes
one it does. Both directions have shipped a broken render out of this repo. Set
`camera_rotate` to `none` or an angle once you have looked.

**Which anchors are worth having.** An anchor is only evidence if its screen
time can be read off the screen ALONE. A one-second visual event that the
narration names as it happens is worth ten vague ones. Do not anchor on a phrase
that follows an action by an unknown pause — it dates the pause, not the event.

**Where the pauses really are.** `silence_db` is the whole cut. Sweep it before
committing: on a quiet room the floor sat between -38 dB (found nothing at all)
and -34 dB (found 43.5 s), and -30 dB found 79.5 s by eating soft speech.

## Footage shot separately

An intro recorded after the fact, or a silent shot of the rig, goes in
`bookends.open` / `bookends.close` — a clip from its own source, rendered to the
same canvas and concatenated as another act.

A clip with **no speech in it cannot be an act of its own**; it is dead air.
Transcribe every extra clip before deciding what it is for. One that comes back
with zero words is picture, not a scene: put it in a bookend's `broll` list, so
the bookend's sound keeps running while only the picture cuts away. Choose the
moment from the narration — the cutaway should show what is being said.

Read what the extra clips actually say before placing them. On this shoot one of
them turned out to be a purpose-recorded intro that states where it goes ("на
початку відео я ставлю цей фрагмент"), which settled the question outright.

## What is already handled

- The offset seed, the correlation attempt and its **rejection** when the peak
  is mush, and the anchor fit — all recorded in `<id>.sync.json` with residuals.
- Act splitting at the screen-coverage edges, so no segment has two layouts.
- The `min(iw,ih)` square, immune to whichever way the source turns out.
- Duration, dimensions, rotation and **non-silent audio** asserted before the
  output is moved into place.

## Do not

- **Do not use `select`/`aselect` to drop spans.** `aselect` passes every audio
  frame on this ffmpeg. See the gotcha in README.
- **Do not cut on silence alone.** The long wait while output streams is the one
  silence the viewer needs. `require_frozen` is why the rule works.
- **Do not trust a rendered duration you did not assert.** The bug that made a
  40 s preview come out 1036.80 s was invisible in every log line ffmpeg wrote.
