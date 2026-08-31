# yt2-fpv33-val -- edit journal
AI notes for future sessions. Scripts append the `- HH:MM` event lines;
after each editing session, append a short prose note: what was asked,
which knob changed, why, and anything the next session should not rediscover.

## 2026-08-31
- 06:20 project created
- 06:24 shot-detect scripts/shot-detect.py (--src projects/yt2-fpv33-val/sources/original.mp4 --sheets --angle-by auto) -- 72 shots, 5 angles, 71 cuts from projects/yt2-fpv33-val/sources/original.mp4

The control. Chapters 8-10 of the same film, never swept against, and it exists
because the alternating grammar looked like a 14-point win on the fitted
segment. It is not: 35.8% here against 49.5% for plain speaker-following and
44.8% for never cutting away from the wide.

Cheap by construction -- no tapes, no render. Three camera entries all point at
the segment's own file, the anchors are 0, the sync sidecar carries nothing but
fps, and --score reads the shot list detected off this segment. Fifteen minutes
end to end, and it is the difference between a result and a fit. Do this for
every new film before quoting a stage-2 number.

Two things this segment shows that the fitted one did not. It detects FIVE
angles rather than three, because the studio wide and the frontal two-shot
separated here where person identity merged them there -- they are one
editorial choice, so the scoring reference merges them back into camW. And the
first speaker hint, taken from a long close-up of the young host, resolved to
the wrong voice: this channel cuts to listening faces, so a close-up is not
evidence that its subject is talking.
