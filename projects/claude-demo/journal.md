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
