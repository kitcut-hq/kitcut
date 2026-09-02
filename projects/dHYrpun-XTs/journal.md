# dHYrpun-XTs -- edit journal
AI notes for future sessions. Scripts append the `- HH:MM` event lines;
after each editing session, append a short prose note: what was asked,
which knob changed, why, and anything the next session should not rediscover.

## 2026-09-02
- 03:04 project created
- 03:32 render scripts/cut-clips.py -> projects/dHYrpun-XTs/outputs/shorts-vertical/dHYrpun-XTs-v-01-brain-vs-chip.mp4 (--manifest projects/dHYrpun-XTs/clips-vertical.json)
- 03:32 render scripts/cut-clips.py -> projects/dHYrpun-XTs/outputs/shorts-vertical/dHYrpun-XTs-v-02-nvidia-hugging-face.mp4 (--manifest projects/dHYrpun-XTs/clips-vertical.json)

Asked for two shorts as a **test of the extraction pipeline** -- this is DOU's
video, not ours, so there is deliberately **no handle badge**: stamping someone
else's footage with `@instafill_ai` would be wrong, and a clean cut is the
better control for a capability test anyway. Nothing here is published, and
nothing should be without asking whose call that is.

Source is a locked-off talking head separated by full-frame branded DOU
interstitial cards. Two things follow that the next session should not have to
rediscover:

**The interstitials are a reframing hazard, but they did not bite here.** A card
carries no face, so a clip spanning one risks a false `pad` letterbox. Both
clips were chosen to sit inside a single segment and auto-reframe came back
97%/98% detection with zero `pad` decisions. Clip 2 still opens ~0.8 s inside
the card's transition (the sentence's first word starts at 901.35 and the wipe
is at 901; measured frame stddev 45 -> 24 -> 89 -> 33, static from 902), so its
head pad is 0 rather than the default.

**The one real defect was not a detector error.** Clip 2's window jumped to
x=1408 for five seconds while every other key sat in 933..1007. That is the
tracker *correctly* following the host into a graphic-insert shot, where he
shifts right and a full-width news card takes the left. The card measures
x 232..873 -- 641 px wide against a 607 px vertical window, so cropping to it
would clip its edges. Letterboxed that shot instead (`pad` [[5.33, 10.29]] in
`clips-vertical.reframe.json`) and neutralised the two x=1408 keys to 968, so
that if the pad edge is ever a frame out the crop underneath still points at the
host rather than bare wall. **That override lives in the sidecar: re-running
`auto-reframe.py` regenerates the file and silently loses it.**

Verified: 24/24 caption-sync probes per clip, durations asserted (43.79 s /
76.58 s), frames checked at both ends and across the letterboxed span, endings
land on complete sentences. project-scan reports ok.

Transcription measurement, since the model choice came up: `large-v3` on
`cuda/int8_float16` took 977 s for 1881 s of audio (~1.9x realtime) and never
fell back a rung. Language autodetected as `uk`, which is the argument for
keeping the big model here -- the boundary phrases and the burned-in captions
are Ukrainian, and `start_text`/`end_before_text` matching breaks on bad words.
Note the elapsed number is pessimistic: most of that run was spent thrashing
against two other transcriptions on the same 4 GB card. That incident is what
produced `scripts/_gpulock.py`; see the README's "One heavy run at a time".
- 03:38 render scripts/cut-clips.py -> projects/dHYrpun-XTs/outputs/shorts-vertical/dHYrpun-XTs-v-01-brain-vs-chip.mp4 (--manifest projects/dHYrpun-XTs/clips-vertical.json --only 01-brain-vs-chip --force)

**Clip 1 was re-cut for its opening frame, not for its words.** Review caught
frame 0 opening mid-word: mouth half open, eyes down, hand frozen mid-gesture.
The cause is that this host essentially never pauses -- the largest gap in the
37 s around the clip is 0.28 s -- so the pad's halfway rule left only 0.12 s of
lead-in and the cut landed inside speech. Every frame of the 360.38..360.62 gap
is mouth-open; every frame of the earlier 357.40..357.68 gap is mouth-closed and
facing camera. Start moved back one sentence to "Можна так зробити" with
head pad 0.20 (lands ~357.54), clip now 46.75 s. Verified on the render's first
eight frames, all settled.

Lead-in there is still 0.14 s, under the 0.20 s threshold, so the clip carries
`open_ok` in the manifest recording that the frame was checked by eye. That is
deliberate: the threshold keeps its teeth rather than being tuned down to stop
the warning.

Note the reframe sidecar had to be regenerated for the new boundaries, which
destroyed clip 2's pad override exactly as warned above; it was re-applied
afterwards. If clip 1's start ever moves again, re-apply
`pad: [[5.33, 10.29]]` and the x=1408 -> 968 key fix to clip 2 by hand.

Both deliverables carry `checked_utc`: the manifest was edited after the renders
to add `open_ok` and notes, which changes no key controlling the pixels.

New tooling from this session: `scripts/check-openings.py` (lead-in silence,
contact sheets) and `scripts/_gpulock.py` + `gpu-lock.py` + `check-gpulock.py`
(one heavy GPU run at a time). Both are documented in the README and the
video-shorts skill.
- 03:53 render scripts/cut-clips.py -> projects/dHYrpun-XTs/outputs/shorts-vertical/dHYrpun-XTs-v-01-brain-vs-chip.mp4 (--manifest projects/dHYrpun-XTs/clips-vertical.json --only 01-brain-vs-chip --force)
- 03:55 render scripts/cut-clips.py -> projects/dHYrpun-XTs/outputs/shorts-vertical/dHYrpun-XTs-v-01-brain-vs-chip.mp4 (--manifest projects/dHYrpun-XTs/clips-vertical.json --only 01-brain-vs-chip --force)

**Clip 1 was re-cut a THIRD time, and the second cut is the cautionary one.**
Fixing the opening *frame* by moving the start back to "Можна так зробити"
(357.54) bought a closed mouth at the cost of ~7 s of back-reference to a
calculation made before the clip -- fluent, and about nothing. A short has about
two seconds to earn the watch, so that trade is always wrong. The rule now
written into the README and the skill: find the hook, cut there, and only then
place the exact frame; if a better frame costs the hook, keep the hook.

Final start is **371.57** -- numeric, not a phrase, because it needs frame
precision. It sits in the 0.02 s gap between "кажуть," (ends 371.56) and
"людина" (starts 371.58), so the clip opens on the hook line: a human runs at
3.3 tokens/second on a 20 W brain -> ~690 tokens/calorie -> 22x more efficient
than a B300. Clip is 32.74 s, down from 46.75 s, with the dry chip-baseline
setup dropped entirely.

An attempt at 371.50 shipped and was caught only by the RENDER's caption: it cut
0.06 s inside "кажуть,", so the audio opened mid-syllable and the first caption
card carried a word from the previous sentence. The picture alone had looked
fine. `check-openings.py --sheet` now writes the render's first eight frames
with captions burned in, which is where that class of error shows up first.

Reframe was regenerated twice more; clip 2's letterbox override was re-applied
each time. Detection on clip 1 is now 99% over the shorter range.
- 04:05 publish scripts/yt-upload.py -> projects/dHYrpun-XTs/outputs/shorts-vertical/dHYrpun-XTs-v-01-brain-vs-chip.mp4 (projects/dHYrpun-XTs/outputs/shorts-vertical/dHYrpun-XTs-v-01-brain-vs-chip.mp4 --title The Human Brain Is 22x More Efficient Than Nvidia's Best Chip #Shorts --description-file projects/dHYrpun-XTs/de) https://youtu.be/fcvw2ID7yNc -- uploaded The Human Brain Is 22x More Efficient Than Nvidia's Best Chip #Shorts
- 04:06 publish scripts/yt-upload.py -> projects/dHYrpun-XTs/outputs/shorts-vertical/dHYrpun-XTs-v-02-nvidia-hugging-face.mp4 (projects/dHYrpun-XTs/outputs/shorts-vertical/dHYrpun-XTs-v-02-nvidia-hugging-face.mp4 --title Nvidia Is Paying 80x Revenue for Hugging Face #Shorts --description-file projects/dHYrpun-XTs/description-) https://youtu.be/WI1kOto13qc -- uploaded Nvidia Is Paying 80x Revenue for Hugging Face #Shorts

### Published — both, as Shorts

- short 1 `https://youtu.be/fcvw2ID7yNc` (brain vs chip, 32.7 s)
- short 2 `https://youtu.be/WI1kOto13qc` (Nvidia/Hugging Face, 76.6 s)

Unlisted on @instafill_ai, uploader re-read both: title and privacy came back
as asked. Shorts classification verified the way flatten-pdf recorded it:
`youtube.com/shorts/<id>` returned 200 for both (after ~20 s and ~60 s -- it
303s until processing succeeds, so an early check reads as failure).
Descriptions credit DOU and link the full episode; this is their footage, cut
as a pipeline test, uploaded on explicit request.

Lessons from this session are now enforced, not just written down:
`check-openings.py` flags any cut landing inside a transcript word
unconditionally (the 371.50 bug, mechanical; 1 ms epsilon spares the
deliberate stop-1-ms-early pattern), and `auto-reframe.py` WARNs about each
sidecar pad it overwrites instead of silently destroying overrides (bit three
times today). Hook-first episode selection is in the skill's step 1 and the
README. The sidecar cannot auto-merge overrides -- entries are in clip time,
so a moved boundary re-times them; re-apply by hand after any regen.
- 05:35 publish scripts/yt-upload.py -> projects/dHYrpun-XTs/outputs/shorts-vertical/dHYrpun-XTs-v-01-brain-vs-chip.mp4 (projects/dHYrpun-XTs/outputs/shorts-vertical/dHYrpun-XTs-v-01-brain-vs-chip.mp4 --title The Human Brain Is 22x More Efficient Than Nvidia's Best Chip --description-file projects/dHYrpun-XTs/descriptio) https://youtu.be/nn69tcqiAwc -- uploaded The Human Brain Is 22x More Efficient Than Nvidia's Best Chip
- 05:35 publish scripts/yt-upload.py -> projects/dHYrpun-XTs/outputs/shorts-vertical/dHYrpun-XTs-v-02-nvidia-hugging-face.mp4 (projects/dHYrpun-XTs/outputs/shorts-vertical/dHYrpun-XTs-v-02-nvidia-hugging-face.mp4 --title Nvidia Is Paying 80x Revenue for Hugging Face --description-file projects/dHYrpun-XTs/description-shorts.t) https://youtu.be/vvrpRY3w1sY -- uploaded Nvidia Is Paying 80x Revenue for Hugging Face
