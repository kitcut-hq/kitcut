# a16z-bornstein -- edit journal
AI notes for future sessions. Scripts append the `- HH:MM` event lines;
after each editing session, append a short prose note: what was asked,
which knob changed, why, and anything the next session should not rediscover.

## 2026-08-27
- 19:05 project created
- 19:05 conform scripts/split-cameras.py (--manifest projects/a16z-bornstein/multicam-sim.json --conform-only) -- CFR 24000/1001 programme from projects/a16z-bornstein/sources/original.mp4
- 19:08 shot-detect scripts/shot-detect.py (--src projects/a16z-bornstein/temp/program.mp4 --alike 0.13) -- 6 shots, 3 angles, 5 cuts from projects/a16z-bornstein/temp/program.mp4
- 19:08 sim-raw scripts/split-cameras.py -> projects/a16z-bornstein/raws/cam1.mp4 (--manifest projects/a16z-bornstein/multicam-sim.json)
- 19:08 sim-raw scripts/split-cameras.py -> projects/a16z-bornstein/raws/cam2.mp4 (--manifest projects/a16z-bornstein/multicam-sim.json)
- 19:08 sim-raw scripts/split-cameras.py -> projects/a16z-bornstein/raws/cam3.mp4 (--manifest projects/a16z-bornstein/multicam-sim.json)
- 19:09 sync-audio scripts/sync-audio.py (--manifest projects/a16z-bornstein/anglecut.json) -- 3 tapes aligned on cam1, worst confidence 511.9, worst three-way residual 0.000 ms
- 19:11 anglecut scripts/angle-cut.py -> projects/a16z-bornstein/outputs/a16z-bornstein-anglecut.mp4 (--manifest projects/a16z-bornstein/anglecut.json)
- 19:12 compare scripts/compare-videos.py (--rendered projects/a16z-bornstein/outputs/a16z-bornstein-anglecut.mp4 --reference projects/a16z-bornstein/temp/program.mp4) -- PASS: projects/a16z-bornstein/outputs/a16z-bornstein-anglecut.mp4 vs projects/a16z-bornstein/temp/program.mp4, median ssim 0.9995, 0 shifted frames
- 19:17 auto-switch scripts/auto-switch.py (--manifest projects/a16z-bornstein/anglecut-auto.json --score projects/a16z-bornstein/a16z-bornstein.shots.json) -- 2 shots from the sound alone, 74.0% agreement with the human edit
- 19:29 auto-switch scripts/auto-switch.py (--manifest projects/a16z-bornstein/anglecut-auto.json --score projects/a16z-bornstein/a16z-bornstein.shots.json) -- 4 shots from the sound alone, 78.8% agreement with the human edit
- 19:29 anglecut scripts/angle-cut.py -> projects/a16z-bornstein/outputs/a16z-bornstein-autocut.mp4 (--manifest projects/a16z-bornstein/anglecut-auto.json --out projects/a16z-bornstein/outputs/a16z-bornstein-autocut.mp4 --force)
- 19:32 sync-audio scripts/sync-audio.py (--manifest projects/a16z-bornstein/anglecut.json) -- 3 tapes aligned on cam1, worst confidence 511.9, worst three-way residual 0.000 ms
- 19:33 auto-switch scripts/auto-switch.py (--manifest projects/a16z-bornstein/anglecut-auto.json) -- 4 shots from the sound alone
- 19:33 anglecut scripts/angle-cut.py -> projects/a16z-bornstein/outputs/a16z-bornstein-autocut.mp4 (--manifest projects/a16z-bornstein/anglecut-auto.json --out projects/a16z-bornstein/outputs/a16z-bornstein-autocut.mp4 --force)
- 19:35 compare scripts/compare-videos.py (--rendered projects/a16z-bornstein/outputs/a16z-bornstein-anglecut.mp4 --reference projects/a16z-bornstein/temp/program.mp4) -- PASS: projects/a16z-bornstein/outputs/a16z-bornstein-anglecut.mp4 vs projects/a16z-bornstein/temp/program.mp4, median ssim 0.9995, 0 shifted frames
- 19:36 compare scripts/compare-videos.py (--rendered projects/a16z-bornstein/outputs/a16z-bornstein-autocut.mp4 --reference projects/a16z-bornstein/temp/program.mp4 --out projects/a16z-bornstein/a16z-bornstein.autocompare.json) -- FAIL: projects/a16z-bornstein/outputs/a16z-bornstein-autocut.mp4 vs projects/a16z-bornstein/temp/program.mp4, median ssim 0.9994, 59 shifted frames

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
