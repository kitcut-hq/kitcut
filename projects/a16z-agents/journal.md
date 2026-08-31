# a16z-agents -- edit journal
AI notes for future sessions. Scripts append the `- HH:MM` event lines;
after each editing session, append a short prose note: what was asked,
which knob changed, why, and anything the next session should not rediscover.

## 2026-08-27
- 19:05 project created
- 19:05 conform scripts/split-cameras.py (--manifest projects/a16z-agents/multicam-sim.json --conform-only) -- CFR 24000/1001 programme from projects/a16z-agents/sources/original.mp4
- 19:08 shot-detect scripts/shot-detect.py (--src projects/a16z-agents/temp/program.mp4) -- 5 shots, 2 angles, 4 cuts from projects/a16z-agents/temp/program.mp4
- 19:08 sim-raw scripts/split-cameras.py -> projects/a16z-agents/raws/cam1.mp4 (--manifest projects/a16z-agents/multicam-sim.json)
- 19:08 sim-raw scripts/split-cameras.py -> projects/a16z-agents/raws/cam2.mp4 (--manifest projects/a16z-agents/multicam-sim.json)
- 19:09 sync-audio scripts/sync-audio.py (--manifest projects/a16z-agents/anglecut.json) -- 2 tapes aligned on cam1, worst confidence 453.6, worst three-way residual 0.000 ms
- 19:11 anglecut scripts/angle-cut.py -> projects/a16z-agents/outputs/a16z-agents-anglecut.mp4 (--manifest projects/a16z-agents/anglecut.json)
- 19:12 compare scripts/compare-videos.py (--rendered projects/a16z-agents/outputs/a16z-agents-anglecut.mp4 --reference projects/a16z-agents/temp/program.mp4) -- PASS: projects/a16z-agents/outputs/a16z-agents-anglecut.mp4 vs projects/a16z-agents/temp/program.mp4, median ssim 0.9993, 0 shifted frames
- 19:17 auto-switch scripts/auto-switch.py (--manifest projects/a16z-agents/anglecut-auto.json --score projects/a16z-agents/a16z-agents.shots.json) -- 3 shots from the sound alone, 85.5% agreement with the human edit
- 19:30 auto-switch scripts/auto-switch.py (--manifest projects/a16z-agents/anglecut-auto.json --score projects/a16z-agents/a16z-agents.shots.json) -- 3 shots from the sound alone, 86.9% agreement with the human edit
- 19:30 anglecut scripts/angle-cut.py -> projects/a16z-agents/outputs/a16z-agents-autocut.mp4 (--manifest projects/a16z-agents/anglecut-auto.json --out projects/a16z-agents/outputs/a16z-agents-autocut.mp4 --force)
- 19:33 sync-audio scripts/sync-audio.py (--manifest projects/a16z-agents/anglecut.json) -- 2 tapes aligned on cam1, worst confidence 453.6, worst three-way residual 0.000 ms
- 19:33 auto-switch scripts/auto-switch.py (--manifest projects/a16z-agents/anglecut-auto.json) -- 3 shots from the sound alone
- 19:34 anglecut scripts/angle-cut.py -> projects/a16z-agents/outputs/a16z-agents-autocut.mp4 (--manifest projects/a16z-agents/anglecut-auto.json --out projects/a16z-agents/outputs/a16z-agents-autocut.mp4 --force)
- 19:35 compare scripts/compare-videos.py (--rendered projects/a16z-agents/outputs/a16z-agents-anglecut.mp4 --reference projects/a16z-agents/temp/program.mp4) -- PASS: projects/a16z-agents/outputs/a16z-agents-anglecut.mp4 vs projects/a16z-agents/temp/program.mp4, median ssim 0.9993, 0 shifted frames
- 19:36 compare scripts/compare-videos.py (--rendered projects/a16z-agents/outputs/a16z-agents-autocut.mp4 --reference projects/a16z-agents/temp/program.mp4 --out projects/a16z-agents/a16z-agents.autocompare.json) -- FAIL: projects/a16z-agents/outputs/a16z-agents-autocut.mp4 vs projects/a16z-agents/temp/program.mp4, median ssim 0.9992, 4 shifted frames

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
- 20:49 shot-detect scripts/shot-detect.py (--src projects/a16z-agents/temp/program.mp4 --out temp/regress/a16z-agents.shots.json) -- 5 shots, 2 angles, 4 cuts from projects/a16z-agents/temp/program.mp4

## 2026-08-31
- 04:48 publish scripts/yt-upload.py -> projects/a16z-agents/outputs/a16z-agents-anglecut.mp4 (projects/a16z-agents/outputs/a16z-agents-anglecut.mp4 --title Benchmark: 2-camera replay, frame-exact (stage 1) --description-file temp/ytdesc/a16z-stage1.txt --channel @instafill_ai --privacy unliste) https://youtu.be/w5EL_tisbsA -- uploaded Benchmark: 2-camera replay, frame-exact (stage 1)
- 04:48 publish scripts/yt-upload.py -> projects/a16z-agents/outputs/a16z-agents-autocut.mp4 (projects/a16z-agents/outputs/a16z-agents-autocut.mp4 --title Benchmark: 2-camera AI auto-switch (stage 2) --description-file temp/ytdesc/a16z-stage2.txt --channel @instafill_ai --privacy unlisted) https://youtu.be/eRH7nODTBpw -- uploaded Benchmark: 2-camera AI auto-switch (stage 2)

## 2026-08-30

Uploaded the finished render(s) to the @instafill_ai channel as **unlisted**, with a short
description in each saying what the AI did and which capabilities the film demonstrates.
Description sources are in `temp/ytdesc/`; the video ids are in the `.youtube.json`
sidecars beside each render.
