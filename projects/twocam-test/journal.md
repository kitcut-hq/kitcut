# twocam-test -- edit journal
AI notes for future sessions. Scripts append the `- HH:MM` event lines;
after each editing session, append a short prose note: what was asked,
which knob changed, why, and anything the next session should not rediscover.

## 2026-08-31
- 13:41 project created
- 13:43 conform scripts/conform-tapes.py (--tapes sources/2026-08-31 15-30-38.mkv sources/video_2026-08-31_15-33-02.mp4 --outdir projects/twocam-test/tapes --id twocam-test) -- conformed 2 tapes to 1920x1080 @ 30 fps
- 13:46 sync-audio scripts/sync-audio.py (--manifest projects/twocam-test/anglecut.json --verify 3) -- 2 tapes aligned on webcam, worst confidence 137.9, worst three-way residual 0.000 ms
- 13:47 sync-audio scripts/sync-audio.py (--manifest projects/twocam-test/anglecut.json) -- 2 tapes aligned on webcam, worst confidence 137.9, worst three-way residual 0.000 ms
- 14:10 anglecut scripts/angle-cut.py -> projects/twocam-test/outputs/twocam-test-anglecut.mp4 (--manifest projects/twocam-test/anglecut.json)
- 14:13 dub scripts/dub-clips.py -> projects/twocam-test/outputs/dub/twocam-test-full.en.wav (--manifest projects/twocam-test/clips.json --only full --outdir projects/twocam-test/outputs/dub) -- sync 94.8%, edge/en-US-AvaMultilingualNeural
- 14:14 render scripts/cut-clips.py -> projects/twocam-test/outputs/twocam-test-full-en.mp4 (--manifest projects/twocam-test/clips.json --only full --dub projects/twocam-test/outputs/dub)

## 2026-08-31

First real render on this machine and the first live exercise of the AMF encoder
path. The whole chain ran on the AMD GPU: two conforms, the angle cut and the
captioned dub render, no NVENC anywhere. The caption preset still names
`h264_nvenc`, and `_encode.resolve()` substituted `h264_amf` with a note rather
than failing -- which is the behaviour that path was built for, confirmed in
anger rather than in a test.

Two defects surfaced and were fixed before they could produce a wrong film,
neither of them in the encoder:

- `angle-cut.py` never checked that the tapes share a frame rate and size. It
  read both off the reference tape. A 60 fps 1080p webcam beside a 30.03 fps
  720p phone would have been addressed at the wrong speed on one of the two and
  handed `concat` mismatched sizes. It refuses a mismatched set now, and
  `conform-tapes.py` is the new tool that puts real recordings on one grid.
- `sync-audio.py` refused a correct sync. Its onset cross-check assumes every
  tape carries one soundtrack from one recorder; two cameras with their own
  microphones in a live room are audible from their first sample, so both
  onsets are ~0 and the reported "disagreement" equals the offset itself. It
  now detects a rolling start and reports the second opinion as unavailable.
  The offset (+1.6818 s, z=137.9) was confirmed independently by envelope
  correlation at +1.700 s, r=0.984, and by the bracket arithmetic: 1.68 s of
  phone before the webcam and 1.82 s after, both positive, as the shoot was
  described.

The phone angle is a silhouette throughout -- it lay low pointing into a window.
Kept at 25% of the film as three short cutaways because two-camera switching is
what this test exists to prove. Do not use it as a real B camera until it is
re-shot facing the light.

Transcribed with whisper `small` on CPU (15 s for 17 s of audio). It mis-hears
"два пристрої" as "до пристроїв" and "Розмовляю" as "Размовляю"; the translator
recovered the meaning anyway. `medium` or `large-v3` would fix the source text
if the transcript itself ever matters.

Dub: edge-tts, sync 94.8%, mean slot error 0.18 s, one line tightened and one
squeezed 9%. Caption sync verified 20/20 before the encode.
- 15:13 anglecut scripts/angle-cut.py -> projects/twocam-test/outputs/twocam-test-anglecut.mp4 (--manifest projects/twocam-test/anglecut.json --force)
- 15:14 render scripts/cut-clips.py -> projects/twocam-test/outputs/twocam-test-full-en.mp4 (--manifest projects/twocam-test/clips.json --only full --dub projects/twocam-test/outputs/dub --force)

Re-rendered both stages after finding that AMF's quality scale is inverted
(see README ## Gotchas). The first delivery went out at qvbr level 20 where it
should have been 31 -- VMAF ~88 instead of ~92. Output grew 1.3 MB -> 2.1 MB at
the same settings, which is what the fix looks like from outside.
