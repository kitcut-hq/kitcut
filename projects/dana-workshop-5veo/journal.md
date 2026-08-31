# dana-workshop-5veo -- edit journal
AI notes for future sessions. Scripts append the `- HH:MM` event lines;
after each editing session, append a short prose note: what was asked,
which knob changed, why, and anything the next session should not rediscover.

## 2026-08-31
- 16:03 project created
- 16:07 acquire yt_dlp -> projects/dana-workshop-5veo/sources/original.mp4 (bestvideo[height<=1080]+bestaudio, https://youtu.be/5VeOzyEd1VQ) -- 50:57.68, 1920x1080, 25/1 CFR, 76442 frames, AV1 + opus, 122 MB
- 16:16 audio ffmpeg -> projects/dana-workshop-5veo/audio/original.wav (mono 16 kHz pcm_s16le, for the pause and level measurements)
- 16:20 pause-price ffmpeg silencedetect sweep + 50 ms RMS envelope -- 27 s of gaps >= 0.7 s in 3057.7 s; nothing to cut
- 16:28 slide-scan ffmpeg fps=2,scale=160:90,gray + numpy diff with the PiP tile masked -- 30 slide changes, plateau flat from threshold 2 to 10
- 16:35 shot-detect scripts/shot-detect.py (--src projects/dana-workshop-5veo/sources/original.mp4 --list) -- 26 cuts / 27 shots / "2 angles" reported, separation "within 0.119, between n/a"; NOT a refusal, and the shots are slide changes, not camera cuts
- 16:45 peek yt_dlp -> projects/dana-workshop-5veo/temp/peek-openai.mp4 (--download-sections *00:10:00-00:12:00, the channel's 48k-view interview, for format only)
- 16:50 survey ffmpeg -> projects/dana-workshop-5veo/temp/survey/ (3 whole-film contact sheets at 1 frame / 30 s, 8 full-res frames, 1 sheet of the peek)

Second channel audit, run under the video-channel-audit skill. Nothing was
rendered, nothing was committed, nothing was uploaded, and no re-cut of their
film exists.

THE ANSWER IS NOT A SCORE, BECAUSE THERE IS NOTHING TO SCORE. Their film is a
raw Zoom-style webinar export published whole: a 31-slide deck full frame with
the presenter's webcam pinned as a fixed 320x180 tile in the top-right corner,
Zoom's own nameplate "Bohdana Pavlychko" burned into it. There are ZERO camera
cuts in 50:57. Every change in the picture is a slide change -- 30 of them,
mean dwell 98.6 s, median 72 s, longest 351 s -- and the webcam tile is live in
all 6115 of the half-second samples, never frozen, never absent, never moved.
No captions, no lower third, no intro, no outro, no music, no b-roll, no
colour treatment. So stage 1 has no cut list to replay and stage 2 has no
angles to choose between; the round trip was correctly skipped, not deferred.

WHAT THIS MEANS FOR THE PITCH. The multicam capability -- the thing the first
audit proved frame-exact on УТ-2 -- is worth nothing to this channel on this
film. What is worth something is everything they have NOT done: this is an
unedited artefact from a channel whose brand design (the deck itself) is
genuinely good. The gap is production, not switching.

TWO NEW TRAPS, neither of which the УТ-2 audit could have exposed.

1. shot-detect.py does not refuse a single-camera film. The guard is
   `failed = between is not None and within >= between`, so when face identity
   finds only ONE person there is no between-cluster distance, `between` is
   None, and the guard passes by default. Here it printed "2 angles; identity
   separation within 0.119, between n/a" and would have written a 27-shot,
   2-angle shot list on a film with no cuts in it -- which split-cameras.py
   would then have turned into two phantom tapes and hours of encoding. The
   refusal was designed for angles that fail to separate; it has no case for
   "this is not a multicam film". `between is None` with more than one claimed
   angle should be a refusal, and it is a two-line fix.

2. ffmpeg silencedetect reports zero gaps on this film at -30, -35 AND -40 dB,
   and that is not because the film is tight -- it is tight, but the reason
   the detector says nothing is that the floor and the speech are far apart
   (p1 = -56.6 dB, p70 = -21.7 dB) while the pauses themselves never reach the
   floor inside 1.5 s. The README already warns never to measure silence on a
   loudnorm'd render; the new half is that an absolute threshold is the wrong
   instrument on ANY source whose speech level you have not measured first.
   Price pauses from a 50 ms RMS envelope thresholded RELATIVE to the p70
   speech level. Doing it that way found 27 s of >= 0.7 s gaps (0.9% of the
   film), 2 s at >= 1.0 s and none at >= 1.5 s: this presenter does not pause,
   and screencast-cut.py's whole reason for existing does not apply to her.

THE VERTICAL-SHORTS GAP IS REAL AND MEASURED. YuNet puts her face at 51-66 px
wide and 70-91 px tall inside 1920x1080 -- 6.5-9.0% of frame height, because
she only exists inside a 320x180 tile. auto-reframe.py face-tracks a crop
window on the assumption the subject is large in frame; here a 9:16 crop around
her head is roughly 100x180 px and would need a 5x upscale to reach 1080x1920.
Cropping the slide instead makes the body text unreadable. A short from this
film needs a COMPOSED vertical layout (slide stacked over speaker, or speaker
over a caption bed), which is a thing nothing in this repo builds today.

BRAND, MEASURED NOT CHOSEN, if a card is ever wanted: accent #CCFF60 (lime),
ink #0E1309, paper #FCFCFC, taken as the 85th percentile of 3.44M saturated
pixels across five frames with the PiP column excluded. Their type pairs a
geometric grotesque with a high-contrast didone italic on the accented words.
Do NOT put a name label on this film without asking: the only name in the
picture is Zoom's own, and the deck already introduces her.

THE CHANNEL, not just this film. 68 videos listed. The bulk is solo
talking-head, 8-25 minutes, and there are remote-call interviews, this one
workshop screencast, a 117-minute meditation and a city vlog. Their most
watched video (48k, the OpenAI interview) is a single-frame remote-call
recording carrying burned glossary cards top-right -- a term and its definition
held over the speaker. That IS make-card.py + image-overlay.py and it is the
cheapest real thing we could show them. If this becomes a pitch, audit ONE of
their solo talking-head videos next: that is their actual format, and it is the
one where captions, shorts, an end card and a dub all land without an ask.

WHAT WE WOULD HAVE TO ASK FOR. Zoom writes separate speaker and screenshare
tracks if the host enables it. Without them the PiP is baked in at 320x180 and
no relayout is possible -- we would be editing a picture of an edit. The
equivalent of "one episode's real camera cards" here is one workshop's raw Zoom
folder.

DELIBERATELY LEFT NO SCRIPT BEHIND. The slide-change scan, the PiP geometry
read and the relative-threshold pause pricing were all run inline and the
commands are in the event lines above. They want to be one `screencast-audit.py`
alongside shot-detect.py, but the scope of this run was the audit, and that
script needs its own README section, skill update and check-script pass. It is
the first thing to build if a screencast channel becomes real work.
