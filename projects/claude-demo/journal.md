# claude-demo -- edit journal
AI notes for future sessions. Scripts append the `- HH:MM` event lines;
after each editing session, append a short prose note: what was asked,
which knob changed, why, and anything the next session should not rediscover.

## 2026-08-26
- 22:34 render scripts/screencast-cut.py -> outputs/claude-demo.mp4 (reconstructed from file times)
- 22:36 publish -> https://youtu.be/7FBUWAmJfu4 (unlisted)

Film assembled by the multicam pipeline: camera is the master clock, offset
19.165s measured by phrase anchors (see claude-demo.sync.json -- the
correlation method was refused at z=2.3 because the screen streams silently).
Cut swept with --list before rendering: min_silence 0.7 won over 1.5 (49s of
pauses removed vs 27s). camera_when_frozen_over=100 deliberately catches the
167s dead stretch but NOT the 92s empty prompt at the start -- that would be a
bigger editorial change; see the manifest _comment before "fixing" it.

## 2026-08-27
- 04:40 render scripts/name-label.py --video -> outputs/claude-demo-labelled.mp4 (reconstructed)
- 04:43 publish -> https://youtu.be/al_qdMlck9I (unlisted) -- this is the version people have

Lower-third added as a SECOND encode of the finished film because name_labels
did not exist in the manifest yet. Afterwards the label was integrated into
screencast-cut.py's single pass and `name_labels` was added to screencast.json
(at: 2.0 -- film time, after the pause cut). Consequence the doctor still
flags as STALE: the manifest now describes a render that has not been made.
The next `screencast-cut.py` run produces claude-demo.mp4 WITH the label in
one generation and supersedes the -labelled file; re-upload decision is open.

Project migrated into projects/claude-demo/ (manifest renamed to
screencast.json, paths rewritten); cut plan verified identical before/after
the move. IMG_2691/2692/2694 are unused takes from the same shoot.
- 06:07 render scripts/screencast-cut.py -> C:/Users/alex/AppData/Local/Temp/claude/C--instafill-video-editing/3b4ea4b3-a90c-4854-bc2e-3332f6d80981/scratchpad/preview-endcard.mp4 (--manifest projects/claude-demo/screencast.json --preview 40 --out C:/Users/alex/AppData/Local/Temp/claude/C--instafill-video-editing/3b4ea4b3-a90c-4854-bc2e-3332f6d80981/scratchpad/preview-endcard.mp)
- 06:22 render scripts/screencast-cut.py -> projects/claude-demo/outputs/claude-demo.mp4 (--manifest projects/claude-demo/screencast.json --force)

The 06:22 render is the first one-generation film: pause cut, camera PiP,
opening bookend, the lower third AND a new Instafill end card, all in a single
NVENC pass. It supersedes claude-demo-labelled.mp4, which was the
second-generation label burn. **The published uploads are both older than this
file** -- al_qdMlck9I is the labelled second-generation encode and 7FBUWAmJfu4
predates the label. Re-upload is still an open decision, deliberately not taken
here.

The end card is the first use of the new image-overlay pipeline. It is written
as `image_overlays` in screencast.json with `at: -11.0` -- negative meaning
"eleven seconds before the end", which is the point: re-cutting the film moves
the card with it instead of stranding it at a timecode the new cut no longer
has. It wipes on left-to-right over a B&W/blur/dim treatment of the footage,
which keeps playing underneath (he is still talking to camera there, which is
why the treatment is worth having -- it puts him behind the type without
freezing or cutting him off). The 06:07 preview render was a throwaway graph
test into the scratchpad; its deliverable entry has been removed from
project.json.

Artwork lives two ways now and both are committed: assets/end-card.html is a
hand-written page (the original, still the one the manifest points at), and
cards/outro.json is the same idea as a *spec* -- template + brand + words --
which make-card.py designs. Prefer the spec route for anything new; the page is
kept as the worked example of the hand-written escape hatch.

## 2026-08-31
- 04:40 publish scripts/yt-upload.py -> projects/claude-demo/outputs/claude-demo-labelled.mp4 (projects/claude-demo/outputs/claude-demo-labelled.mp4 --title Claude Code demo — AI-edited screencast + camera --description-file temp/ytdesc/claude-demo.txt --channel @instafill_ai --privacy unlisted) https://youtu.be/_3n076Zfzj0 -- uploaded Claude Code demo — AI-edited screencast + camera

## 2026-08-30

Uploaded the finished render(s) to the @instafill_ai channel as **unlisted**, with a short
description in each saying what the AI did and which capabilities the film demonstrates.
Description sources are in `temp/ytdesc/`; the video ids are in the `.youtube.json`
sidecars beside each render.

## 2026-09-02
Marked `outputs/claude-demo.mp4` superseded in project.json -- the labelled render is
the published one; the unlabelled file stays on disk as the pre-label master. This
clears the doctor's AMBIGUOUS (two current screencast renders).
