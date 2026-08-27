# a16z-sinofsky -- edit journal
AI notes for future sessions. Scripts append the `- HH:MM` event lines;
after each editing session, append a short prose note: what was asked,
which knob changed, why, and anything the next session should not rediscover.

## 2026-08-27
- 19:05 project created
- 19:05 conform scripts/split-cameras.py (--manifest projects/a16z-sinofsky/multicam-sim.json --conform-only) -- CFR 24000/1001 programme from projects/a16z-sinofsky/sources/original.mp4
- 19:08 shot-detect scripts/shot-detect.py (--src projects/a16z-sinofsky/temp/program.mp4) -- 7 shots, 2 angles, 6 cuts from projects/a16z-sinofsky/temp/program.mp4
- 19:09 sim-raw scripts/split-cameras.py -> projects/a16z-sinofsky/raws/cam1.mp4 (--manifest projects/a16z-sinofsky/multicam-sim.json)
- 19:09 sim-raw scripts/split-cameras.py -> projects/a16z-sinofsky/raws/cam2.mp4 (--manifest projects/a16z-sinofsky/multicam-sim.json)
- 19:09 sync-audio scripts/sync-audio.py (--manifest projects/a16z-sinofsky/anglecut.json) -- 2 tapes aligned on cam1, worst confidence 540.8, worst three-way residual 0.000 ms
- 19:12 anglecut scripts/angle-cut.py -> projects/a16z-sinofsky/outputs/a16z-sinofsky-anglecut.mp4 (--manifest projects/a16z-sinofsky/anglecut.json)
- 19:12 compare scripts/compare-videos.py (--rendered projects/a16z-sinofsky/outputs/a16z-sinofsky-anglecut.mp4 --reference projects/a16z-sinofsky/temp/program.mp4) -- FAIL: projects/a16z-sinofsky/outputs/a16z-sinofsky-anglecut.mp4 vs projects/a16z-sinofsky/temp/program.mp4, median ssim 0.9992, 1 shifted frames
- 19:12 compare scripts/compare-videos.py (--rendered projects/a16z-sinofsky/outputs/a16z-sinofsky-anglecut.mp4 --reference projects/a16z-sinofsky/temp/program.mp4) -- FAIL: projects/a16z-sinofsky/outputs/a16z-sinofsky-anglecut.mp4 vs projects/a16z-sinofsky/temp/program.mp4, median ssim 0.9992, 1 shifted frames
- 19:14 anglecut scripts/angle-cut.py -> temp/negctl2/offbyone.mp4 (--manifest temp/negctl2.json --out temp/negctl2/offbyone.mp4 --force)
- 19:14 compare scripts/compare-videos.py (--rendered projects/a16z-sinofsky/outputs/a16z-sinofsky-anglecut.mp4 --reference projects/a16z-sinofsky/temp/program.mp4) -- PASS: projects/a16z-sinofsky/outputs/a16z-sinofsky-anglecut.mp4 vs projects/a16z-sinofsky/temp/program.mp4, median ssim 0.9992, 0 shifted frames
- 19:18 auto-switch scripts/auto-switch.py (--manifest projects/a16z-sinofsky/anglecut-auto.json --score projects/a16z-sinofsky/a16z-sinofsky.shots.json) -- 1 shots from the sound alone, 73.3% agreement with the human edit
- 19:31 auto-switch scripts/auto-switch.py (--manifest projects/a16z-sinofsky/anglecut-auto.json --score projects/a16z-sinofsky/a16z-sinofsky.shots.json) -- 1 shots from the sound alone, 73.3% agreement with the human edit
- 19:31 anglecut scripts/angle-cut.py -> projects/a16z-sinofsky/outputs/a16z-sinofsky-autocut.mp4 (--manifest projects/a16z-sinofsky/anglecut-auto.json --out projects/a16z-sinofsky/outputs/a16z-sinofsky-autocut.mp4 --force)
- 19:34 sync-audio scripts/sync-audio.py (--manifest projects/a16z-sinofsky/anglecut.json) -- 2 tapes aligned on cam1, worst confidence 540.8, worst three-way residual 0.000 ms
- 19:34 auto-switch scripts/auto-switch.py (--manifest projects/a16z-sinofsky/anglecut-auto.json) -- 1 shots from the sound alone
- 19:35 anglecut scripts/angle-cut.py -> projects/a16z-sinofsky/outputs/a16z-sinofsky-autocut.mp4 (--manifest projects/a16z-sinofsky/anglecut-auto.json --out projects/a16z-sinofsky/outputs/a16z-sinofsky-autocut.mp4 --force)
- 19:36 compare scripts/compare-videos.py (--rendered projects/a16z-sinofsky/outputs/a16z-sinofsky-anglecut.mp4 --reference projects/a16z-sinofsky/temp/program.mp4) -- PASS: projects/a16z-sinofsky/outputs/a16z-sinofsky-anglecut.mp4 vs projects/a16z-sinofsky/temp/program.mp4, median ssim 0.9992, 0 shifted frames
- 19:36 compare scripts/compare-videos.py (--rendered projects/a16z-sinofsky/outputs/a16z-sinofsky-autocut.mp4 --reference projects/a16z-sinofsky/temp/program.mp4 --out projects/a16z-sinofsky/a16z-sinofsky.autocompare.json) -- FAIL: projects/a16z-sinofsky/outputs/a16z-sinofsky-autocut.mp4 vs projects/a16z-sinofsky/temp/program.mp4, median ssim 0.9992, 25 shifted frames

Round-trip fixture added in the same session as a16z-altman's, as one of three
films the framework had never seen. Stage 1 passes exactly: frame-for-frame,
zero shifted frames, zero frozen filler, every cut at offset 0.

Three harness bugs surfaced here that a single film could never have shown, all
now fixed in the scripts: a wide angle cannot self-anchor from its picture (its
people are small and it barely moves, so a fixed motion threshold finds its
first live frame late -- +2, +30 and +6 frames on the three films), so ONE tape
anchors by picture and the sound places the rest; a single near-still frame can
tie against its neighbour and was failing an otherwise exact round trip, so a
neighbour must now win by more than encode noise; and a film with an unframed
speaker needs `off_camera_speakers` or that voice pollutes a framed speaker's
cluster.

Editing this film -- sync, decide, render, from raw tapes -- takes about half
its runtime. The decide step is ~85% of that and is CPU-bound speaker
embedding; the NVENC render is roughly fifteen times faster than realtime.
