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
