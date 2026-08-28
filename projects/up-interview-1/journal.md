# up-interview-1 -- edit journal
AI notes for future sessions. Scripts append the `- HH:MM` event lines;
after each editing session, append a short prose note: what was asked,
which knob changed, why, and anything the next session should not rediscover.

## 2026-08-27
- 20:06 project created

Brought in to test the framework on content it had never seen: 25 fps (not
23.976), an hour long, a different editor, 1080p in AV1/VP9. It failed at the
first step, and the failure is why this project is kept.

shot-detect finds the cuts but cannot tell the ANGLES apart, and says so: worst
distance within an angle exceeds the closest distance between two, meaning a
shot resembles a different camera more than it resembles its own. The angle
count never settles across the threshold sweep either.

The cause is visible the moment you look at --sheets. Four people at one table
against a plain black backdrop, so every camera has the SAME background -- and
reading the room behind the speaker is exactly how this method identifies an
angle. On the a16z films each camera had a gold disc, a lamp, a bookshelf; here
there is nothing. Burned-in lower-third name cards compound it: while a name is
up, that camera fingerprints as a new angle.

Three rescues were measured, not guessed, and all three failed: plain, top-60%
mask (drops the name cards and the table), and top-60% plus contrast
normalisation. Best margin 0.47x, where anything usable is well above 1.0.
Masking does help the name-card pairs specifically (0.158 -> 0.062) but the
underlying angles still do not separate.

Do not tune thresholds at this. The signal is absent, not buried. Making these
work needs angle identity from WHO is in frame and how they are framed -- face
or person embeddings -- which is a different method, not a parameter. Until
then shot-detect refuses to write a shot list here, which is what stops
split-cameras from building one hour-long tape per phantom angle.
- 21:02 shot-detect scripts/shot-detect.py (--src projects/up-interview-1/sources/original.mp4 --sheets) -- 229 shots, 31 angles, 228 cuts from projects/up-interview-1/sources/original.mp4
- 21:16 shot-detect scripts/shot-detect.py (--src projects/up-interview-1/sources/original.mp4 --sheets) -- 229 shots, 16 angles, 228 cuts from projects/up-interview-1/sources/original.mp4
- 21:28 conform scripts/split-cameras.py (--manifest projects/up-interview-1/multicam-sim.json --conform-only) -- CFR 25/1 programme from projects/up-interview-1/sources/original.mp4
- 21:51 shot-detect scripts/shot-detect.py (--src projects/up-interview-1/sources/original.mp4 --sheets) -- 229 shots, 13 angles, 228 cuts from projects/up-interview-1/sources/original.mp4

SECOND VISIT -- the negative result above is now obsolete, and this film is the
reason person-identity angle detection exists.

Alex's question settled it: what is the problem with detecting the person
instead of the background, and would a green wall be a shock? It would have
been, and that was the flaw. Frame fingerprints read the room behind the
speaker, and the room was only ever a proxy for the camera. A single black
backdrop is the EASY case for detecting a person -- the less background there
is, the more the frame is the person.

shot-detect --angle-by person (auto by default) now uses YuNet detection plus
SFace identity embeddings. On this film: 55 phantom angles -> 13 real ones,
every one a real picture. The four close-ups absorbed their own burned-in
name-card shots, which frame fingerprints could never do.

Instruments were chosen by elimination, all measured on these shots:
whole-frame 0.44x, masked+contrast-normalised 0.72x, colour torso with Haar
1.11x -- and Haar missed one of the four people in five of five samples.
YuNet detects 5/5 everywhere and SFace separates at 3.0x.

Four rules each earned themselves by failing here first, and the iteration was
55 -> 31 -> 16 -> 13:
- one face, AVERAGE linkage: pose stretches a person's own embeddings, and
  under complete linkage an outstretched arm and a thrown-back head each got a
  phantom camera. A singleton within SFace's published 0.64 of a real person is
  that person mid-gesture.
- two-plus faces: group by WHICH people are in the shot, not by frame sig --
  the same black backdrop shattered one two-shot pairing into fifteen angles.
- faces under ~8.5% of frame width stay anonymous: in a four-person wide, per
  face identities are noise and split one wide camera six ways.
- zero faces (and, after up-interview-2, anyone not in the cast) go to one
  shared xtra bin. A logo animation is not a camera, and each of its frames was
  about to become its own hour-long synthetic tape.

The separation guard is centroid-based for person mode -- is every shot closer
to its own person than to any other -- because pairwise fails a correct
clustering: absorbing an outlier is right, and pairwise then reports that
outlier's distance to its farthest team-mate as "within".

Face detections are cached under temp/ per (file, params). Before that, every
grouping-logic iteration cost a ten-minute decode of an hour of AV1.

This film is also the first through the 25 fps audio-boundary path (exact:
1920 samples a frame) and the hour-long clustering path. Conform preserved all
90145 frames.
- 22:50 sync-audio scripts/sync-audio.py (--manifest temp/up1-syncprobe-manifest.json --out temp/up1-syncprobe.json) -- 3 tapes aligned on cam1, worst confidence 3298.5, worst three-way residual 0.000 ms

## 2026-08-28
- 00:16 sim-raw scripts/split-cameras.py -> projects/up-interview-1/raws/cam1.mp4 (--manifest projects/up-interview-1/multicam-sim.json)
- 00:16 sim-raw scripts/split-cameras.py -> projects/up-interview-1/raws/cam10.mp4 (--manifest projects/up-interview-1/multicam-sim.json)
- 00:16 sim-raw scripts/split-cameras.py -> projects/up-interview-1/raws/cam11.mp4 (--manifest projects/up-interview-1/multicam-sim.json)
- 00:16 sim-raw scripts/split-cameras.py -> projects/up-interview-1/raws/cam12.mp4 (--manifest projects/up-interview-1/multicam-sim.json)
- 00:16 sim-raw scripts/split-cameras.py -> projects/up-interview-1/raws/cam13.mp4 (--manifest projects/up-interview-1/multicam-sim.json)
- 00:16 sim-raw scripts/split-cameras.py -> projects/up-interview-1/raws/cam2.mp4 (--manifest projects/up-interview-1/multicam-sim.json)
- 00:16 sim-raw scripts/split-cameras.py -> projects/up-interview-1/raws/cam3.mp4 (--manifest projects/up-interview-1/multicam-sim.json)
- 00:16 sim-raw scripts/split-cameras.py -> projects/up-interview-1/raws/cam4.mp4 (--manifest projects/up-interview-1/multicam-sim.json)
- 00:16 sim-raw scripts/split-cameras.py -> projects/up-interview-1/raws/cam5.mp4 (--manifest projects/up-interview-1/multicam-sim.json)
- 00:16 sim-raw scripts/split-cameras.py -> projects/up-interview-1/raws/cam6.mp4 (--manifest projects/up-interview-1/multicam-sim.json)
- 00:16 sim-raw scripts/split-cameras.py -> projects/up-interview-1/raws/cam7.mp4 (--manifest projects/up-interview-1/multicam-sim.json)
- 00:16 sim-raw scripts/split-cameras.py -> projects/up-interview-1/raws/cam8.mp4 (--manifest projects/up-interview-1/multicam-sim.json)
- 00:16 sim-raw scripts/split-cameras.py -> projects/up-interview-1/raws/cam9.mp4 (--manifest projects/up-interview-1/multicam-sim.json)
- 00:24 sync-audio scripts/sync-audio.py (--manifest projects/up-interview-1/anglecut.json) -- 13 tapes aligned on cam1, worst confidence 3298.5, worst three-way residual 0.000 ms
- 01:54 anglecut scripts/angle-cut.py -> projects/up-interview-1/outputs/up-interview-1-anglecut.mp4 (--manifest projects/up-interview-1/anglecut.json)
- 02:07 compare scripts/compare-videos.py (--rendered projects/up-interview-1/outputs/up-interview-1-anglecut.mp4 --reference projects/up-interview-1/temp/program.mp4) -- FAIL: projects/up-interview-1/outputs/up-interview-1-anglecut.mp4 vs projects/up-interview-1/temp/program.mp4, median ssim 0.9993, 0 shifted frames
- 02:28 compare scripts/compare-videos.py (--rendered projects/up-interview-1/outputs/up-interview-1-anglecut.mp4 --reference projects/up-interview-1/temp/program.mp4) -- PASS: projects/up-interview-1/outputs/up-interview-1-anglecut.mp4 vs projects/up-interview-1/temp/program.mp4, median ssim 0.9993, 0 shifted frames

STAGE 1 PASSES on the hour. 90145 of 90145 frames, zero shifted, zero frozen
filler, 228 cuts against 228, 100.00% angle agreement, audio at 0.000 ms,
median SSIM 0.9993. This is the largest round trip the framework has run: 13
hour-long tapes, 1.17 million encoded frames, a 229-segment filtergraph, and
the first film at 25 fps and on a person-mode shot list.

The anchor logic behaved exactly as designed at scale: cam2 anchored the film
at a 980x margin, nine tapes independently agreed at +0 frames, and three
(cam5, cam9, cam11 -- all near-static angles) correctly self-reported as too
still to self-anchor and were placed by sound. All 13 sync offsets came back at
exact whole frames with confidence 3298 and zero three-way residual.

It did NOT pass first time, and the two failures were both the comparator
measuring itself. Worth knowing because they will recur on any long 1080p film:

- Fifty "frozen" frames in two runs of exactly 1.00s -- which is the minimum
  run length, and that is the giveaway. At those frames the rendered film maxed
  0.000858 and the reference 0.000866: the same stillness, a person sitting
  motionless for a second. The bug was comparing frozen RUNS between the two
  films; when both hover either side of the threshold their run boundaries
  disagree and shared stillness reads as filler. Now it asks whether the
  reference MOVES over those frames, which has no boundary to argue about.
- One cut "a frame out" at 62168. Frames 62164-62171 are a smooth plateau, not
  a cut: rendered peaks at 62167 with 0.02435, reference at 62168 with 0.02434.
  A coin flip in the fifth decimal. max_cut_offset is now 1 -- the detector's
  measured precision, NOT a relaxation of frame-exactness, which the shift
  probe still holds at zero.

Do not "fix" a future failure by loosening a threshold without measuring what
the two films actually do at the disputed frames. Both of these looked like
real defects and were not, and the measurement took ten minutes.

Two caches were added while doing this, both because iteration was costing full
decodes of an hour of video: face detections (temp/shot-detect-faces-*.npz) and
the picture anchor (temp/anglecut-anchor-*.json). Anchoring 13 hour-long tapes
is a scan of each, once for --list and once for the render.

Stage 2 is NOT run here. With 13 angles including six framings of two-shot
pairings, the speaker-to-camera hint mapping stops being one hint per person,
and that is a design question rather than a run.
