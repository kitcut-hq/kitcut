# yt2-fpv33-seg -- edit journal
AI notes for future sessions. Scripts append the `- HH:MM` event lines;
after each editing session, append a short prose note: what was asked,
which knob changed, why, and anything the next session should not rediscover.

## 2026-08-31
- 04:56 project created
- 05:06 shot-detect scripts/shot-detect.py (--src projects/yt2-fpv33-seg/sources/original.mp4 --angle-by auto) -- 101 shots, 3 angles, 100 cuts from projects/yt2-fpv33-seg/sources/original.mp4
- 05:12 conform scripts/split-cameras.py (--manifest projects/yt2-fpv33-seg/multicam-sim.json --conform-only) -- CFR 25/1 programme from projects/yt2-fpv33-seg/sources/original.mp4
- 05:23 sim-raw scripts/split-cameras.py -> projects/yt2-fpv33-seg/raws/cam1.mp4 (--manifest projects/yt2-fpv33-seg/multicam-sim.json)
- 05:23 sim-raw scripts/split-cameras.py -> projects/yt2-fpv33-seg/raws/cam2.mp4 (--manifest projects/yt2-fpv33-seg/multicam-sim.json)
- 05:23 sim-raw scripts/split-cameras.py -> projects/yt2-fpv33-seg/raws/cam3.mp4 (--manifest projects/yt2-fpv33-seg/multicam-sim.json)
- 05:24 sync-audio scripts/sync-audio.py (--manifest projects/yt2-fpv33-seg/anglecut.json) -- 3 tapes aligned on cam1, worst confidence 2062.9, worst three-way residual 0.000 ms
- 05:29 anglecut scripts/angle-cut.py -> projects/yt2-fpv33-seg/outputs/yt2-fpv33-seg-anglecut.mp4 (--manifest projects/yt2-fpv33-seg/anglecut.json)
- 05:33 compare scripts/compare-videos.py (--rendered projects/yt2-fpv33-seg/outputs/yt2-fpv33-seg-anglecut.mp4 --reference projects/yt2-fpv33-seg/temp/program.mp4) -- PASS: projects/yt2-fpv33-seg/outputs/yt2-fpv33-seg-anglecut.mp4 vs projects/yt2-fpv33-seg/temp/program.mp4, median ssim 0.9986, 0 shifted frames
- 06:19 auto-switch scripts/auto-switch.py (--manifest projects/yt2-fpv33-seg/anglecut-auto.json) -- 98 shots from the sound alone
- 06:24 anglecut scripts/angle-cut.py -> projects/yt2-fpv33-seg/outputs/yt2-fpv33-seg-autocut.mp4 (--manifest projects/yt2-fpv33-seg/anglecut-auto.json --out projects/yt2-fpv33-seg/outputs/yt2-fpv33-seg-autocut.mp4)
- 06:47 anglecut scripts/angle-cut.py -> projects/yt2-fpv33-seg/outputs/yt2-fpv33-seg-autocut-debug.mp4 (--manifest projects/yt2-fpv33-seg/anglecut-auto.json --debug --out projects/yt2-fpv33-seg/outputs/yt2-fpv33-seg-autocut-debug.mp4)
- 06:54 anglecut scripts/angle-cut.py -> projects/yt2-fpv33-seg/outputs/yt2-fpv33-seg-finished.mp4 (--manifest projects/yt2-fpv33-seg/anglecut-finished.json --out projects/yt2-fpv33-seg/outputs/yt2-fpv33-seg-finished.mp4)

Brought in to answer a business question, not a technical one: УТ-2 (@yt-2,
44.8k subs) is a channel we may invite to edit with this repo, and before that
we needed to know whether we can actually reproduce how they cut. This is
chapters 2-4 of their 110-minute 'fpv #33'; chapters 8-10 are held out in
yt2-fpv33-val.

WHAT WORKS, PROVEN. Frame fingerprints could not tell their cameras apart
(within 0.049 >= between 0.016) -- the studio-film failure, same as
up-interview-1. Face identity separated three angles at 0.068 vs 0.671, a 9.9x
margin, the cleanest the repo has measured. Stage 1 then passed FIRST TIME:
29250 of 29250 frames, zero shifted, zero frozen filler, 100 cuts against 100
with a worst offset of 0, 100.00% angle agreement, audio at 0.000 ms, median
SSIM 0.9986. Their cut can be rebuilt from tapes and replayed exactly.

WHAT DOES NOT, AND WHY IT IS THE INTERESTING PART. This channel does not cut on
the speaker. Read their transition matrix and there is nothing ambiguous about
it: a close-up is followed by the wide 97% and 92% of the time and by the other
close-up 3%; every shot runs 11.6 s on average (median 11.0); the wide holds
52.4% of the runtime. The room is their default state and the faces are the
accents -- the inverse of what auto-switch.py assumes. Plain speaker-following
scored 45.0%, which is BELOW the 52.4% you get by never cutting at all.

So a metronome grammar was written for it (alternating(), wide_between +
wide_after_s + wide_dur_s, snapping each beat to a gap between speech segments
via snap_s). Swept here it reached 59.1% at 10 s of face and 14 s of room, with
98 cuts against their 100 -- structurally right. Then the held-out segment took
it to 35.8% while plain speaker-following held 49.5%. It was fitted. It ships
OFF, like wide_overlap_pct, with its numbers written down. Do not turn it on
for a new film without a second segment saying it earns its place.

TWO TRAPS THIS FILM FOUND, both now fixed and tested:
- TitaNet's ONNX export dies above 122.88 s in one embedding (12288 feature
  frames) with a broadcast error from inside the encoder. An answer here ran
  132 s with no pause the segmentation model would split on, and the run died.
  embed_span() now chunks at 60 s and averages; check-multicam.py holds it.
- A speaker hint taken from a long close-up resolved to the wrong voice,
  because they cut to LISTENING faces. On a speaker-following channel that is a
  safe way to pick a hint; here it is not. Take hints from --list's voice track.

FINISHING. angle-cut.py could not carry a lower third or an end card -- those
lived in screencast-cut.py only -- so it now reads name_labels and
image_overlays and composites them inside its own NVENC pass, labels then
overlays then the --debug commentary. -finished.mp4 is the stage-1 cut with
both burned in. The end card is designed, not hand-written: template
stacked-blocks, brand config/cards/brands/yt2.json, whose accent #4F2D7F is
their studio wall measured off 164k saturated pixels of a close-up.

NOT LABELLED WITH NAMES ON PURPOSE. Their own intro carries no name cards, so
which host is Олексій Бабенко and which is Володимир Несторак cannot be read
off the footage. Putting a real person's name on the wrong face is not a demo.
The label names the show; name_labels takes people the moment they confirm who
is who.

FOR THE NEXT SESSION, if this becomes a pitch: the honest sentence is that we
can rebuild and finish their film exactly, and that the editorial choice --
when to punch in and when to sit wide -- is theirs, not ours, at 45-50%
agreement against a 44.8-52.4% do-nothing baseline. Agreement with one human's
edit is a harsh yardstick and two editors would not agree either, but it is not
yet a claim that we can make their taste.
- 07:07 render scripts/run-captions.py -> projects/yt2-fpv33-seg/outputs/yt2-fpv33-seg-captioned-captioned.mp4 (--input projects/yt2-fpv33-seg/outputs/yt2-fpv33-seg-finished.mp4 --project yt2-fpv33-seg --id yt2-fpv33-seg-captioned --style config/presets/eu-navy.json --lang uk)
