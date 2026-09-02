# neaCnEawvbk -- edit journal
AI notes for future sessions. Scripts append the `- HH:MM` event lines;
after each editing session, append a short prose note: what was asked,
which knob changed, why, and anything the next session should not rediscover.

## 2026-09-01
- 22:37 project created
- 22:54 render scripts/cut-clips.py -> projects/neaCnEawvbk/outputs/shorts-vertical/neaCnEawvbk-v-01-500-fields.mp4 (--manifest projects/neaCnEawvbk/clips-vertical.json)
- 22:57 render scripts/cut-clips.py -> projects/neaCnEawvbk/outputs/shorts-vertical/neaCnEawvbk-v-02-45-minutes-to-two.mp4 (--manifest projects/neaCnEawvbk/clips-vertical.json)
- 22:59 render scripts/cut-clips.py -> projects/neaCnEawvbk/outputs/shorts-vertical/neaCnEawvbk-v-03-manual-bpo-risk.mp4 (--manifest projects/neaCnEawvbk/clips-vertical.json)
- 23:08 render scripts/cut-clips.py -> projects/neaCnEawvbk/outputs/shorts-vertical/neaCnEawvbk-v-01-500-fields.mp4 (--manifest projects/neaCnEawvbk/clips-vertical.json --force)
- 23:11 render scripts/cut-clips.py -> projects/neaCnEawvbk/outputs/shorts-vertical/neaCnEawvbk-v-02-45-minutes-to-two.mp4 (--manifest projects/neaCnEawvbk/clips-vertical.json --force)
- 23:15 render scripts/cut-clips.py -> projects/neaCnEawvbk/outputs/shorts-vertical/neaCnEawvbk-v-03-manual-bpo-risk.mp4 (--manifest projects/neaCnEawvbk/clips-vertical.json --force)

Created three 1080x1920 shorts from the BPO walkthrough: the 500+ field scope,
the under-two-minute fill claim, and the manual-entry error risk. Because the
source is a screencast, the vertical manifest uses a fixed 1600x880 content crop
starting at x=320 rather than face tracking; this cleanly excludes the webcam
bubble and taskbar. The first QA render used a delogo mask, but it left a visible
lower-left smear, so all three were reframed and re-rendered without a mask.
Two end boundaries are numeric by 1 ms because adjacent transcript words share
the exact same timestamp; this prevents the next sentence from leaking onto the
last caption card. Obvious ASR errors in the selected ranges were corrected.
Final beginning/middle/end frame review was clean, every clip passed 24/24
caption-sync probes, and project-scan reported ok.
