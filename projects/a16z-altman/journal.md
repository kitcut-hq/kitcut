# a16z-altman -- edit journal
AI notes for future sessions. Scripts append the `- HH:MM` event lines;
after each editing session, append a short prose note: what was asked,
which knob changed, why, and anything the next session should not rediscover.

## 2026-08-27
- 17:13 project created
- 17:33 conform scripts/split-cameras.py (--manifest projects/a16z-altman/multicam-sim.json --conform-only) -- CFR 24000/1001 programme from projects/a16z-altman/sources/original.mp4
- 17:33 shot-detect scripts/shot-detect.py (--src projects/a16z-altman/temp/program.mp4) -- 16 shots, 4 angles, 15 cuts from projects/a16z-altman/temp/program.mp4
- 17:38 sim-raw scripts/split-cameras.py -> projects/a16z-altman/raws/cam1.mp4 (--manifest projects/a16z-altman/multicam-sim.json --force)
- 17:38 sim-raw scripts/split-cameras.py -> projects/a16z-altman/raws/cam2.mp4 (--manifest projects/a16z-altman/multicam-sim.json --force)
- 17:38 sim-raw scripts/split-cameras.py -> projects/a16z-altman/raws/cam3.mp4 (--manifest projects/a16z-altman/multicam-sim.json --force)
- 17:38 sim-raw scripts/split-cameras.py -> projects/a16z-altman/raws/cam4.mp4 (--manifest projects/a16z-altman/multicam-sim.json --force)
- 17:40 sync-audio scripts/sync-audio.py (--manifest projects/a16z-altman/anglecut.json) -- 4 tapes aligned on cam1, worst confidence 604.5, worst three-way residual 0.125 ms
- 17:44 sync-audio scripts/sync-audio.py (--manifest projects/a16z-altman/anglecut.json) -- 4 tapes aligned on cam1, worst confidence 604.5, worst three-way residual 0.125 ms
- 17:47 anglecut scripts/angle-cut.py -> projects/a16z-altman/outputs/a16z-altman-anglecut.mp4 (--manifest projects/a16z-altman/anglecut.json)
- 17:49 compare scripts/compare-videos.py (--rendered projects/a16z-altman/outputs/a16z-altman-anglecut.mp4 --reference projects/a16z-altman/temp/program.mp4) -- PASS: projects/a16z-altman/outputs/a16z-altman-anglecut.mp4 vs projects/a16z-altman/temp/program.mp4, median ssim 0.9993, 0 shifted frames
- 17:49 anglecut scripts/angle-cut.py -> temp/negctl/offbyone.mp4 (--manifest temp/negctl-anglecut.json --out temp/negctl/offbyone.mp4 --force) -- negative control: cam4 anchored one frame wrong on purpose. Deleted after the comparator failed it as intended; not a deliverable.

This project is a **test fixture**, not a video anyone publishes. It exists to
answer one question: can this repo's scripts reproduce an edit a professional
editor made? The a16z clip was chosen because it is short, cleanly cut, and shot
on locked-off cameras with very different backgrounds -- which is what makes the
angles separable by fingerprint at all. Do not "improve" the render settings
here without re-running the comparison; the whole file is a measuring
instrument.

Stage 1 (the machinery) passes exactly: 2796 of 2796 frames, all 15 cuts at
offset 0, zero shifted frames, audio at 0.000 ms, 100% angle agreement. The
tapes' staggers were recovered by audio correlation to the exact frame, and
independently by picture anchor, and the two agreed to zero frames on all four.

Four things cost real time and are now written down in the README gotchas, so
nobody has to find them twice:

- `freezedetect` is useless on synthetic footage. NVENC re-encodes cloned frames
  independently, so a held frame differs from itself by up to 3/255 and the
  detector finds nothing in a 95-second freeze at -60 dB. Its span count is not
  even monotonic in the threshold. Tapes are verified by fingerprinting every
  sampled frame against the programme frame it should be showing instead --
  which is a stronger check anyway, because it proves placement, not stillness.
- Average SSIM cannot see the error this test is for. A render with one camera
  one frame out scored median 0.9992 against 0.9993 for the correct one. The
  shift probe (score each frame against the reference frame before, at and
  after) flagged 665 frames starting exactly at that camera's first live frame.
  That negative control is worth re-running whenever the comparator changes.
- The anchor has an off-by-one that is easy to get wrong and was: a tape's held
  opening frame IS its first live frame repeated, so the first frame that
  *differs* is the second live one. The audio-vs-picture cross-check caught it
  before any conclusion was drawn from a bad render.
- Onset detection is not a frame anchor. It finds where a mix becomes audible,
  which on this programme is 41 ms after it starts, identically on every tape.
  Fine as a second opinion, useless for placing a film.

Stage 2 is the real question and is next: `auto-switch.py` gets the tapes and
nothing else -- no truth, no shot list, no picture -- and has to decide from the
sound alone who is speaking and which camera to be on. The frozen filler makes
the answer visible to any motion detector, so reading the picture there is
cheating and the skill says so.
