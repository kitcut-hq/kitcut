# egr4Y4oZgLM -- edit journal
AI notes for future sessions. Scripts append the `- HH:MM` event lines;
after each editing session, append a short prose note: what was asked,
which knob changed, why, and anything the next session should not rediscover.

## 2026-08-25
- 18:10 render scripts/cut-clips.py -> outputs/shorts-vertical/*.mp4 (5 vertical shorts; reconstructed from file times)
- 22:46 render dub variant en-el (ElevenLabs voice)
- 22:48 render dub variant en (edge voice, first translation)
- 23:43 render dub variant en-fix (edge voice, manual translation fixes) -- the keeper

Captioned master rendered first (egr4Y4oZgLM-captioned-1080p60.mp4); the five
horizontal shorts cut FROM it, the vertical ones from the clean source with
captions re-rendered after the crop. Crop centres per clip live in
clips-vertical.reframe.json -- that file exists to be edited; per-shot framing
was measured and lost to fixed centres.

Dub history of clip 01: the first en translation left 14 of 26 lines drawling
at the slow-down floor, which is what the manual --engine manual fix (en-fix)
repaired. en is superseded by en-fix; en-el is the PAID ElevenLabs voice and
coexists deliberately. A cached translation carries a plan fingerprint --
changing --max-dur or engine refuses the stale reuse; pass --retranslate or a
fresh --tag.

## 2026-08-27
Project migrated into projects/egr4Y4oZgLM/ (manifests renamed clips.json /
clips-vertical.json, paths rewritten, per-project temp/). Both cut plans
verified identical before/after via --list diff; deliverables carry
checked_utc acknowledging the path-only manifest edit.

## 2026-08-31
- 04:46 publish scripts/yt-upload.py -> projects/egr4Y4oZgLM/outputs/shorts-vertical/egr4Y4oZgLM-v-01-silver-button.mp4 (projects/egr4Y4oZgLM/outputs/shorts-vertical/egr4Y4oZgLM-v-01-silver-button.mp4 --title The silver button — AI-cut vertical short --description-file temp/ytdesc/short.txt --channel @instafill_ai --pri) https://youtu.be/u40fcUf-1iY -- uploaded The silver button — AI-cut vertical short
- 04:46 publish scripts/yt-upload.py -> projects/egr4Y4oZgLM/outputs/shorts-vertical/egr4Y4oZgLM-v-02-immigrants.mp4 (projects/egr4Y4oZgLM/outputs/shorts-vertical/egr4Y4oZgLM-v-02-immigrants.mp4 --title Immigrants — AI-cut vertical short --description-file temp/ytdesc/short.txt --channel @instafill_ai --privacy unlis) https://youtu.be/0c_AF7kxaGQ -- uploaded Immigrants — AI-cut vertical short
- 04:47 publish scripts/yt-upload.py -> projects/egr4Y4oZgLM/outputs/shorts-vertical/egr4Y4oZgLM-v-03-paid-toilets.mp4 (projects/egr4Y4oZgLM/outputs/shorts-vertical/egr4Y4oZgLM-v-03-paid-toilets.mp4 --title Paid toilets — AI-cut vertical short --description-file temp/ytdesc/short.txt --channel @instafill_ai --privacy u) https://youtu.be/EbrDECCe9SE -- uploaded Paid toilets — AI-cut vertical short
- 04:47 publish scripts/yt-upload.py -> projects/egr4Y4oZgLM/outputs/shorts-vertical/egr4Y4oZgLM-v-04-wages-vs-rent.mp4 (projects/egr4Y4oZgLM/outputs/shorts-vertical/egr4Y4oZgLM-v-04-wages-vs-rent.mp4 --title Wages vs rent — AI-cut vertical short --description-file temp/ytdesc/short.txt --channel @instafill_ai --privacy) https://youtu.be/CqnGJR3lN9c -- uploaded Wages vs rent — AI-cut vertical short
- 04:47 publish scripts/yt-upload.py -> projects/egr4Y4oZgLM/outputs/shorts-vertical/egr4Y4oZgLM-v-05-ranch-tsa.mp4 (projects/egr4Y4oZgLM/outputs/shorts-vertical/egr4Y4oZgLM-v-05-ranch-tsa.mp4 --title Ranch and the TSA — AI-cut vertical short --description-file temp/ytdesc/short.txt --channel @instafill_ai --privacy) https://youtu.be/A8f_FTBI5A0 -- uploaded Ranch and the TSA — AI-cut vertical short

## 2026-08-30

Uploaded the finished render(s) to the @instafill_ai channel as **unlisted**, with a short
description in each saying what the AI did and which capabilities the film demonstrates.
Description sources are in `temp/ytdesc/`; the video ids are in the `.youtube.json`
sidecars beside each render.
- 04:56 publish scripts/yt-upload.py -> projects/egr4Y4oZgLM/outputs/shorts-vertical/egr4Y4oZgLM-v-01-silver-button-en-fix.mp4 (projects/egr4Y4oZgLM/outputs/shorts-vertical/egr4Y4oZgLM-v-01-silver-button-en-fix.mp4 --title The silver button - English dub (AI, neural voice) --description-file temp/ytdesc/short-dub.txt --channel) https://youtu.be/95GI0sX9M2o -- uploaded The silver button - English dub (AI, neural voice)
- 04:56 publish scripts/yt-upload.py -> projects/egr4Y4oZgLM/outputs/shorts-vertical/egr4Y4oZgLM-v-01-silver-button-en-el.mp4 (projects/egr4Y4oZgLM/outputs/shorts-vertical/egr4Y4oZgLM-v-01-silver-button-en-el.mp4 --title The silver button - English dub (AI, ElevenLabs voice) --description-file temp/ytdesc/short-dub.txt --chan) https://youtu.be/4h798ptPd3s -- uploaded The silver button - English dub (AI, ElevenLabs voice)

## 2026-08-31

Deleted the 5 vertical shorts and the 3 English dub variants (en, en-fix,
en-el) of the silver-button clip — from YouTube (@instafill_ai) and locally
(`outputs/shorts-vertical/`, `outputs/dub/`). project.json entries removed
to match. The 16:9 shorts under `outputs/shorts/` and the full captioned
render are untouched.
