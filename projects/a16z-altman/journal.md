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
- 18:11 auto-switch scripts/auto-switch.py (--manifest projects/a16z-altman/anglecut-auto.json --score projects/a16z-altman/a16z-altman.shots.json) -- 8 shots from the sound alone, 77.7% agreement with the human edit
- 18:11 anglecut scripts/angle-cut.py -> projects/a16z-altman/outputs/a16z-altman-autocut.mp4 (--manifest projects/a16z-altman/anglecut-auto.json --out projects/a16z-altman/outputs/a16z-altman-autocut.mp4 --force)

Stage 2 is now done too, and scores **77.68%** of the timeline on the same
camera as the human editor, from the soundtrack alone. Two things about that
number before anyone quotes it.

The ceiling is about 85.8%, not 100%. The wide is nobody's close-up, so a
speaker-following rule cannot predict a cut to it, and it is 14.2% of this film.
Per camera we get 100% on the interviewer (501 of 501 frames), 90.4%, 83.6% and
0% on the wide. So 77.68% is roughly 90% of what this grammar can reach, and the
rest is the editor holding on a listener rather than the talker.

And the grammar knobs were swept against this film, so the number is optimistic
by construction. The honest one comes from the next video, which is the whole
reason the framework is manifest-driven. Do not report 77.68% as "how well we
edit" -- report it as "how well we edit the film we tuned on".

Worth keeping: the sweep killed a plausible idea. "Break a long monologue with a
wide cutaway" sounds obviously right and measures worse -- 64.6% against 77.7%
-- while placing MORE cuts near the human's (8 of 15 within a second, against
4). It cuts at the right times to the wrong camera. min_shot did nothing at all
here because the speaker runs are all longer than three seconds.

Also worth keeping: sherpa-onnx's built-in clustering merged two of the three
speakers into one 33-second block, and it was not the model's fault -- measured
cosine distance is 0.59 within a speaker against 0.82 between, which separates
fine. auto-switch.py does its own average-linkage clustering for that reason.
Suspect the clustering before the embeddings.

The two agreement numbers (auto-switch --score off the shot list, compare-videos
off the rendered pixels) agree to the second decimal by completely different
routes. If they ever diverge, one of them is broken.
- 18:14 compare scripts/compare-videos.py (--rendered projects/a16z-altman/outputs/a16z-altman-autocut.mp4 --reference projects/a16z-altman/temp/program.mp4 --out projects/a16z-altman/a16z-altman.autocompare.json) -- FAIL: projects/a16z-altman/outputs/a16z-altman-autocut.mp4 vs projects/a16z-altman/temp/program.mp4, median ssim 0.9992, 490 shifted frames
- 18:29 auto-switch scripts/auto-switch.py (--manifest projects/a16z-altman/anglecut-auto.json) -- 8 shots from the sound alone
- 18:29 anglecut scripts/angle-cut.py -> projects/a16z-altman/outputs/a16z-altman-autocut-debug.mp4 (--manifest projects/a16z-altman/anglecut-auto.json --debug --out projects/a16z-altman/outputs/a16z-altman-autocut-debug.mp4 --force)
- 18:43 auto-switch scripts/auto-switch.py (--manifest projects/a16z-altman/anglecut-auto.json --score projects/a16z-altman/a16z-altman.shots.json) -- 8 shots from the sound alone, 77.7% agreement with the human edit
- 18:43 anglecut scripts/angle-cut.py -> projects/a16z-altman/outputs/a16z-altman-anglecut-debug.mp4 (--manifest projects/a16z-altman/anglecut.json --debug --force)
- 18:45 anglecut scripts/angle-cut.py -> projects/a16z-altman/outputs/a16z-altman-anglecut-debug.mp4 (--manifest projects/a16z-altman/anglecut.json --debug --force)
- 18:45 anglecut scripts/angle-cut.py -> projects/a16z-altman/outputs/a16z-altman-autocut-debug.mp4 (--manifest projects/a16z-altman/anglecut-auto.json --debug --out projects/a16z-altman/outputs/a16z-altman-autocut-debug.mp4 --force)
- 18:46 compare scripts/compare-videos.py (--rendered projects/a16z-altman/outputs/a16z-altman-anglecut.mp4 --reference projects/a16z-altman/temp/program.mp4) -- FAIL: projects/a16z-altman/outputs/a16z-altman-anglecut.mp4 vs projects/a16z-altman/temp/program.mp4, median ssim 0.9993, 0 shifted frames
- 18:46 compare scripts/compare-videos.py (--rendered projects/a16z-altman/outputs/a16z-altman-autocut.mp4 --reference projects/a16z-altman/temp/program.mp4 --out projects/a16z-altman/a16z-altman.autocompare.json) -- FAIL: projects/a16z-altman/outputs/a16z-altman-autocut.mp4 vs projects/a16z-altman/temp/program.mp4, median ssim 0.9992, 490 shifted frames
- 18:48 compare scripts/compare-videos.py (--rendered projects/a16z-altman/outputs/a16z-altman-anglecut.mp4 --reference projects/a16z-altman/temp/program.mp4) -- PASS: projects/a16z-altman/outputs/a16z-altman-anglecut.mp4 vs projects/a16z-altman/temp/program.mp4, median ssim 0.9993, 0 shifted frames
- 18:48 compare scripts/compare-videos.py (--rendered projects/a16z-altman/outputs/a16z-altman-autocut.mp4 --reference projects/a16z-altman/temp/program.mp4 --out projects/a16z-altman/a16z-altman.autocompare.json) -- FAIL: projects/a16z-altman/outputs/a16z-altman-autocut.mp4 vs projects/a16z-altman/temp/program.mp4, median ssim 0.9992, 490 shifted frames

Debug notes added, and a good question from Alex settled two things.

`angle-cut.py --debug` now burns a bottom-left commentary -- shot, tape frames,
anchor, sync, why this camera, and a warning where the tape is held. It is an
ASS track spliced after the concat, so it costs one filter and rides in the
existing pass. It writes a `-debug.mp4` and never replaces the clean render:
burning text changes pixels, and a debug copy of the stage-1 cut would no longer
be frame-identical to the programme and would fail its own comparison. The clean
anglecut/autocut pair is the control-and-experiment; keep all four files.

Alex spotted the picture freezing at 0:27 of the autocut and asked whether it
was a bug. It is not: our switcher chose cam2 there, cam2's tape has real
footage only up to frame 632, and the editor was on the wide from 632-848 -- so
we asked for footage that does not exist and got a held frame for 9 seconds.
That is inherent to the fixture and unavoidable, and it is the VISIBLE form of
the disagreement. Worth knowing that the three numbers coincide exactly: 22.32%
of the timeline on a different camera, 624 frames below 0.90 SSIM, 624 frames of
frozen filler. Stage-2 renders are diagnostics, not films; say so when reporting.

My reporting had been wrong, not the measurement. I quoted the autocut's median
SSIM (0.9992) which is blind to a 22% tail while p5 was 0.2318 -- the exact
mistake the negative control was written to warn about. compare-videos.py now
prints a loud line when frames fall below 0.90, and fails on p5 as well as the
median.

Then Alex asked whether the editor cut to the wide BECAUSE several people spoke
at once. Half right, and the half that is right is measured: the two wide shots
are the two densest patches of crosstalk in the film (11.7% and 18.0% of their
length with two voices active) against a median of 0.0% across every close-up
longer than three seconds, and six of nine short interjections land within 0.31s
of a human cut. Windowed embeddings CANNOT see this -- a window holding a
speaker plus a "yeah" embeds as the speaker, and churn inside the wides measured
identical to outside. The segmentation model can, because it is multi-label.

But acting on it barely helps. `wide_overlap_pct` is implemented and OFF:
crosstalk is 4.5% of the film and the wide is 14.2%, so overlap is close to
necessary and nowhere near sufficient. Best of 30 swept settings was 78.79%
against 77.68% -- one point, fitted to a film with two wide shots. One setting
matched far more cut TIMING (10 of 15 within a second vs 4) but made 22 cuts
against the human's 15, and cuts_within_1s does not penalise a spurious cut, so
that metric wants fixing before it is trusted. Next film decides.

Method worth reusing: calibrate detectors against stage 1. Its plan is the
human's own edit so every frame provably has real footage, and any frozen run
reported there is a false positive. That is how both freeze thresholds were set
-- 0.0015 over half a second called 12.8% of a pixel-identical render frozen,
0.0005 over a second calls 0.0% while still catching all 624 in stage 2.
- 19:31 sync-audio scripts/sync-audio.py (--manifest projects/a16z-altman/anglecut.json) -- 4 tapes aligned on cam1, worst confidence 604.5, worst three-way residual 0.125 ms
- 19:32 auto-switch scripts/auto-switch.py (--manifest projects/a16z-altman/anglecut-auto.json) -- 8 shots from the sound alone
- 19:32 anglecut scripts/angle-cut.py -> projects/a16z-altman/outputs/a16z-altman-autocut.mp4 (--manifest projects/a16z-altman/anglecut-auto.json --out projects/a16z-altman/outputs/a16z-altman-autocut.mp4 --force)
- 19:35 compare scripts/compare-videos.py (--rendered projects/a16z-altman/outputs/a16z-altman-anglecut.mp4 --reference projects/a16z-altman/temp/program.mp4) -- PASS: projects/a16z-altman/outputs/a16z-altman-anglecut.mp4 vs projects/a16z-altman/temp/program.mp4, median ssim 0.9993, 0 shifted frames
- 19:37 anglecut scripts/angle-cut.py -> projects/a16z-altman/outputs/a16z-altman-autocut-debug.mp4 (--manifest projects/a16z-altman/anglecut-auto.json --debug --out projects/a16z-altman/outputs/a16z-altman-autocut-debug.mp4 --force)

Three more films went through the framework in the same session -- bornstein,
agents, sinofsky -- and they earned their keep immediately by breaking three
things one film could never have shown. All fixed; see their journals too.

The one that matters most here: a16z-altman is now the COUNTER-EXAMPLE for
segment painting. Painting the segmentation model's exact boundaries over the
window track is the shipped default because it won on both unseen films (+4.8
bornstein, +1.4 agents), but on this film it LOSES 4.2 points (77.68 -> 73.50).
Two of the men here sound alike enough that a whole-segment embedding lands on
the wrong one for a few long segments, while many independent window votes
average it out. anglecut-auto.json pins paint:false with that reason written
in. Do not "fix" this by flipping the default back; a default that wins twice
and loses once is worth keeping WITH its counter-example committed next to it.

Cross-film numbers, for anyone tempted to quote 77.68% as "how well we edit":
altman 77.68, bornstein 78.77, agents 86.90, sinofsky 73.27. The spread is the
answer, and both ends have causes. agents is easiest because one framed speaker
plus an off-camera interjector is exactly what a speaker-follower is good at.
sinofsky is hardest because it is a single 106-second monologue: the editor cut
six times for rhythm alone, our switcher cut zero, and no audio feature could
have known. That is the floor of the method, not a defect.

Stage 1 is exact on all four films. That is the result worth repeating -- the
machinery is not the uncertain part.

Editing time, measured end to end from raw tapes: 0.46x to 0.57x of the film's
runtime. The decide step (speaker embeddings on CPU) is ~85% of it; the NVENC
render is ~15x faster than realtime. If that ever needs to be faster, the
embeddings are the only thing worth optimising.
- 20:26 shot-detect scripts/shot-detect.py (--src projects/a16z-altman/temp/program.mp4) -- 16 shots, 4 angles, 15 cuts from projects/a16z-altman/temp/program.mp4
- 20:48 shot-detect scripts/shot-detect.py (--src projects/a16z-altman/temp/program.mp4 --angle-by person --out temp/altman-person.shots.json) -- 16 shots, 4 angles, 15 cuts from projects/a16z-altman/temp/program.mp4
- 20:49 shot-detect scripts/shot-detect.py (--src projects/a16z-altman/temp/program.mp4 --out temp/regress/a16z-altman.shots.json) -- 16 shots, 4 angles, 15 cuts from projects/a16z-altman/temp/program.mp4
- 21:19 shot-detect scripts/shot-detect.py (--src projects/a16z-altman/temp/program.mp4 --angle-by person --out temp/altman-person.shots.json) -- 16 shots, 4 angles, 15 cuts from projects/a16z-altman/temp/program.mp4
- 22:08 shot-detect scripts/shot-detect.py (--src projects/a16z-altman/temp/program.mp4 --angle-by person --out temp/altman-p2.json) -- 16 shots, 4 angles, 15 cuts from projects/a16z-altman/temp/program.mp4

## 2026-08-28
- 02:16 compare scripts/compare-videos.py (--rendered projects/a16z-altman/outputs/a16z-altman-anglecut.mp4 --reference projects/a16z-altman/temp/program.mp4) -- PASS: projects/a16z-altman/outputs/a16z-altman-anglecut.mp4 vs projects/a16z-altman/temp/program.mp4, median ssim 0.9993, 0 shifted frames
- 02:16 compare scripts/compare-videos.py (--rendered projects/a16z-altman/outputs/a16z-altman-autocut.mp4 --reference projects/a16z-altman/temp/program.mp4 --out temp/a2.json) -- FAIL: projects/a16z-altman/outputs/a16z-altman-autocut.mp4 vs projects/a16z-altman/temp/program.mp4, median ssim 0.9992, 92 shifted frames
- 02:29 compare scripts/compare-videos.py (--rendered projects/a16z-altman/outputs/a16z-altman-autocut.mp4 --reference projects/a16z-altman/temp/program.mp4 --out projects/a16z-altman/a16z-altman.autocompare.json) -- FAIL: projects/a16z-altman/outputs/a16z-altman-autocut.mp4 vs projects/a16z-altman/temp/program.mp4, median ssim 0.9992, 92 shifted frames
