---
name: video-tighten
description: Tighten a single already-composited recording — a screen capture that already has the webcam bubble and the narration burned into it, one file, nothing to sync. Shortens every long pause, swallows the "um"s that lean on them, removes spans named by quoting what is said in them, ramps the joins so they do not click, and remaps the word transcript so the result can be captioned for free. Use when asked to cut the dead air, silences, pauses or filler out of a screencast or demo recording, to remove a specific thing somebody said ("cut the bit where I say I'll pause the video"), to make a raw recording tighter, shorter or more professional, or to prepare a one-file recording for YouTube.
---

# Tightening one recording that is already composited

**Wrong skill?** This one takes **one** file with everything already in it. If
you have a screen capture and a *separate* camera/phone take that need syncing
and compositing, use `video-multicam` (`screencast-cut.py`). If the ask is to
pull short clips *out* of a long video, use `video-shorts` (`cut-clips.py`).

```powershell
# from the repo root
python scripts/tighten-cut.py --manifest projects/<id>/tighten.json --list
python scripts/tighten-cut.py --manifest projects/<id>/tighten.json
```

The worked example is `projects/flatten-pdf/tighten.json`. README has the
reference under "Tightening one recording that is already composited".

## The project folder comes first

Every video lives in `projects/<id>/` — its manifests, its content dirs, and
two committed metadata files. Before doing anything, read
`projects/<id>/project.json` (create the folder with
`python scripts/project-scan.py --init <id>` if this is a new video) and skim
`projects/<id>/journal.md` if the ask touches past decisions. `tighten-cut.py`
records its own render; anything you run by hand you record yourself. End the
session with a prose note in `journal.md`.

## Order of work

1. **Copy the raw file in** as `projects/<id>/sources/<id>-raw.mp4`. Never edit
   in place and never overwrite what the recorder produced.
2. **Transcribe with the vocabulary first.** Extract 16k mono WAV, then:

   ```powershell
   python scripts/transcribe-words.py projects/<id>/audio/<id>.wav `
       --out projects/<id>/transcripts/<id>.words.json `
       --model large-v3 --device cpu --compute-type int8 --language en `
       --hotwords-file config/vocab/instafill.txt
   ```

   **Do this before anything else that reads the transcript.** A product name
   the model has never heard comes back as three different words in one file,
   and burned captions make that everybody's problem. Add missing terms to the
   vocab file; keep it to words the model actually gets wrong.
3. **Read the transcript grouped by its pauses** before choosing anything. That
   is what shows you the stumble at 0:47, the 10-second wait at 3:53, and the
   aside that has to be named in `remove`.
4. **`--list` and read the sweep.** Pick `min_silence` / `keep_pause` off the
   table, not by eye.
5. Render, then caption (below), then write the description and chapters.

## The manifest

```json
{
  "id": "<id>",
  "src": "projects/<id>/sources/<id>-raw.mp4",
  "words": "projects/<id>/transcripts/<id>.words.json",
  "outdir": "projects/<id>/outputs",
  "cut": {"min_silence": 0.7, "keep_pause": 0.35, "silence_db": -34,
          "min_drop": 0.30, "join_fade_ms": 12},
  "fillers": {"enabled": true, "reach": 0.45},
  "remove": [
    {"from_text": "let's wait a few seconds", "to_text": "it's almost done",
     "why": "dead wait plus the aside about pausing the video"}
  ],
  "audio": {"loudnorm": "I=-16:TP=-1.5:LRA=11"},
  "render": {"cq": 20, "speed": 5}
}
```

| key | |
|---|---|
| `cut.min_silence` | a silence must be at least this long to be touched |
| `cut.keep_pause` | how much of it **survives**, split across the join |
| `cut.min_drop` | do not bother with a cut smaller than this |
| `cut.join_fade_ms` | audio ramp at each seam; 12 ms kills the click |
| `fillers.reach` | how close to a dropped span an "um" must be to go with it |
| `remove[]` | `from_text` / `to_text` (or numeric `from`/`to`), plus `why` |
| `film.start_text` / `end_text` | where the film begins and ends, quoted |

`name_labels` and `image_overlays` work exactly as in `screencast-cut.py` —
same keys, same presets, applied after the concat so `at` is **film time**, and
inside the same encode. A negative `at` on an overlay counts back from the end.

## What to think about, not just what to type

- **A pause is shortened, not deleted.** Removing every silence outright
  produces a film that sounds like a ransom note. `keep_pause` is the knob, and
  it is what survives, not what goes.
- **Read the segment line in `--list`, not just the runtime.** A cut is a jump
  for whatever is moving in the frame — on a screencast that is the webcam
  bubble and nothing else. "a cut every 3.6s" and "shortest 0.40s" are what
  tell you whether the result will feel edited or frantic. Runtime cannot.
- **Fillers only go where a pause already is.** Cutting an "um" mid-phrase
  costs an audible seam and buys a third of a second. The default leaves them.
- **The thing the user actually wants cut is usually fluent speech.** "Let me
  pause the video while this runs", a false start, a sentence said better the
  second time — no detector finds those. Ask what should go, then name it by
  **quoting** it so the manifest survives a re-transcription.
- **Look at the picture across a removal, not just the transcript.** A cut over
  a screen that changes state (a job finishing, a page navigating) reads as
  "time passed" and is fine. A cut mid-mouse-drag does not.

## Captioning the result costs no ASR

The render writes `<out>.words.json`, the word transcript remapped through the
keep-list. The remap is exact — a cut only deletes — so put it where
`run-captions.py` looks and its transcribe stage is already satisfied:

```powershell
copy projects/<id>/outputs/<id>-tight.words.json projects/<id>/transcripts/<id>-tight.words.json
python scripts/run-captions.py --input projects/<id>/outputs/<id>-tight.mp4 `
    --id <id>-tight --project <id> --style config/presets/instafill.json
```

**Use `config/presets/instafill.json`, not `red-card`, on a screen recording.**
`red-card` was measured off a news channel — a saturated slab in uppercase,
built to be read over a talking head. On a screencast it competes with the very
UI the video is pointing at. The `instafill` preset recedes instead: near-black
at 12% transparency, sentence case, mint spotlight, narrower lines, and its
`_geometry` block records the webcam bubble and taskbar the placement was fitted
around. See `## Styling` in the README before widening a line.

## Checks it makes for you

Duration against the keep-list, audio not silent, and every label and overlay
proved to start before the film ends — the failure that is otherwise completely
silent, because `enable` never turns true and the card simply never appears.

## After any change to the script

```powershell
python scripts/check-script.py --changed
```
