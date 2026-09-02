# SKv9fUHeckE -- edit journal
AI notes for future sessions. Scripts append the `- HH:MM` event lines;
after each editing session, append a short prose note: what was asked,
which knob changed, why, and anything the next session should not rediscover.

## 2026-09-02
- 04:16 project created
- 04:51 render scripts/cut-clips.py -> projects/SKv9fUHeckE/outputs/shorts-vertical/SKv9fUHeckE-v-01-hunting-our-engineers.mp4 (--manifest projects/SKv9fUHeckE/clips-vertical.json)
- 04:51 render scripts/cut-clips.py -> projects/SKv9fUHeckE/outputs/shorts-vertical/SKv9fUHeckE-v-02-dont-wait-to-be-mobilised.mp4 (--manifest projects/SKv9fUHeckE/clips-vertical.json)
- 04:58 render scripts/cut-clips.py -> projects/SKv9fUHeckE/outputs/shorts-vertical/SKv9fUHeckE-v-01-hunting-our-engineers.mp4 (--manifest projects/SKv9fUHeckE/clips-vertical.json --only 01-hunting-our-engineers --force)
- 05:01 render scripts/cut-clips.py -> projects/SKv9fUHeckE/outputs/shorts-vertical/SKv9fUHeckE-v-01-hunting-our-engineers.mp4 (--manifest projects/SKv9fUHeckE/clips-vertical.json --only 01-hunting-our-engineers --force)
- 05:02 render scripts/cut-clips.py -> projects/SKv9fUHeckE/outputs/shorts-vertical/SKv9fUHeckE-v-02-dont-wait-to-be-mobilised.mp4 (--manifest projects/SKv9fUHeckE/clips-vertical.json --only 02-dont-wait-to-be-mobilised --force)

## 2026-09-01 — two vertical shorts, and three bugs the source exposed

Asked for 2 shorts from DOU DefTech (third-party footage, capability test, so no
handle badge). Both cut, both verified, neither uploaded — publishing was not
asked for.

**What the source made us learn.** It carries burned-in Ukrainian subtitles, but
*only* over the host's off-camera questions — measured, not assumed: the
y=850..1050 band reads 0.0280 near-white under a host question and exactly
0.0000 in every guest-speaking sample. A 607 px 9:16 window would shred
full-width text, so every clip had to be guest-only. That constraint, not taste,
killed the two other strong candidates: "what if Delta goes down" (payoff
"a price in lives, not money") and "do the russians have an analogue" — in both
the hook lives in the host's subtitled question, and in the second the guest
only ever says "вони", so the short would be 45 s about an unnamed subject.

It is also a **two-camera interview**, which a first pass missed: `scene>0.25`
found nothing because both cameras show the same man in the same room. Frame
differencing found the cuts instantly (median diff 0.36, cuts >12). Every
`auto-reframe` window jump lands within 0.01 s of a real cut, so the ±140 px
snaps that looked like a defect are correct and invisible — the picture cuts at
the same instant. **Do not judge a reframe plan by its jumps; judge it against
where the cuts actually are.**

**Three bugs, all now fixed.**

1. `cut-clips.py` and `auto-reframe.py` **ignored a per-clip `pad`**, using only
   the manifest-level one, while `check-openings.py` honoured it. The checker and
   the renderer therefore disagreed about where a clip began: the check passed on
   a start that never shipped. Both now honour it. NOTE this also affected
   dHYrpun-XTs clip 02, which declared `pad.head 0.0` to dodge an interstitial
   wipe and was rendered with 0.15 anyway.
2. `verify-captions.py` failed a probe on the conjunction 'І', whose active
   window is 4 cs — **exactly one frame at 25 fps**. A one-frame probe cannot
   decide a one-frame highlight (cs-quantised ASS plus a 70 ms fade), so words
   under two frames are now skipped, and the skipped count is printed. Only
   2/167 and 2/88 words fall in that bucket, so the check keeps its teeth.
   A first attempt raised `min_active_ms` 40→80 in a new preset; that was WRONG
   and was reverted — the word is the last of its caption group, so its highlight
   is clamped by the group end no matter what the floor says.
3. `check-openings.py` measured lead-in **only from the transcript, which lied.**
   It reported a comfortable 0.48 s gap before clip 1's hook while the waveform
   ran at -12 dB straight through it: faster-whisper truncates word ENDS ('є'
   really runs to ~1003.74, not 1003.44). Word *starts* are reliable. The check
   now measures the waveform too and flags a transcript gap the audio disagrees
   with, because that is more dangerous than a short one — it reads as "ok".

**Where clip 1 opens, and why it is not silent.** There is no silence anywhere
between 1003.16 and 1008 — the speaker runs the sentence straight into the hook.
So the head pad was set to land on the measured RMS minimum (-21.8 dB at 1003.88,
against -16.5 as 'Вони' begins and -12 before), which is also the calmest of the
eight frames across 1003.68-1003.96; he never closes his mouth in that window
either. Recorded as `open_ok`. Clip 2 needed none of this: frame 0 is genuinely
silent with 0.54 s of air before the first word.

Both renders: 24/24 caption sync probes, 100% face detection, no `pad`
letterboxing, window jumps aligned to the camera cuts within 0.01 s.
- 05:10 render scripts/cut-clips.py -> projects/SKv9fUHeckE/outputs/shorts-vertical/SKv9fUHeckE-v-02-dont-wait-to-be-mobilised.mp4 (--manifest projects/SKv9fUHeckE/clips-vertical.json --only 02-dont-wait-to-be-mobilised --force)
- 05:16 render scripts/cut-clips.py -> projects/SKv9fUHeckE/outputs/shorts-vertical/SKv9fUHeckE-v-02-civilian-contract.mp4 (--manifest projects/SKv9fUHeckE/clips-vertical.json --only 02-civilian-contract)
- 05:16 render scripts/cut-clips.py -> projects/SKv9fUHeckE/outputs/shorts-vertical/SKv9fUHeckE-v-02-civilian-contract.mp4 (--manifest projects/SKv9fUHeckE/clips-vertical.json --only 02-civilian-contract --force)
- 05:18 render scripts/cut-clips.py -> projects/SKv9fUHeckE/outputs/shorts-vertical/SKv9fUHeckE-v-02-civilian-contract.mp4 (--manifest projects/SKv9fUHeckE/clips-vertical.json --only 02-civilian-contract --force)
- 05:19 render scripts/cut-clips.py -> projects/SKv9fUHeckE/outputs/shorts-vertical/SKv9fUHeckE-v-02-civilian-contract.mp4 (--manifest projects/SKv9fUHeckE/clips-vertical.json --only 02-civilian-contract --force)

## 2026-09-01 (later) — the hook gate, after making the same mistake twice

The user called it out: two clips in a row shipped with a slow opening. Every
check in the pipeline passed both — settled frame, silent lead-in, no mid-word
cut — and both were still unwatchable, because nothing measured *when the point
arrives*. That is now a gate in `cut-clips.py`, not a habit.

**Every clip declares `hook`, and the render refuses if it lands later than
3.0 s.** Validated retroactively against the two real failures: the first
shipped opening scores 32.6 s, the second 6.7 s, and both also trip a
filler-opener warning that names the phrase. `hook_ok` downgrades the timing
failure with a stated reason; nothing excuses a missing hook.

**Clip 02 was replaced, and the reason is the useful part.** The "if you have
already been mobilised" answer could not satisfy both standing rules at once:
its hook was reachable fast only by cutting mid-flow, which put a mouth-open
frame at 0, and cutting on the segment's real 0.72 s silence put the hook 6.7 s
in. A fast hook and a settled frame were **5 s apart in that material**. So the
material changed rather than the rules: the next answer (civilian contracts
without mobilisation) has a real 0.68 s silence, a settled frame and its hook
2.2 s in. To find such places, scan the WHOLE audio for real silences and read
what follows each -- the transcript's gaps are not silences and cannot be used
for this.

Two smaller things worth keeping. The final start moved 1693.45 -> 1693.52 for
the CAPTION, not the picture: the filler 'Ну,' ends at 1693.50, so an earlier
cut pulled it into the first caption group and frame 0 shipped a card reading a
word the viewer never hears. **Check the first card, not only the first frame.**
And `auto-reframe` must be re-run before the render whenever a boundary moves,
not after -- doing it in the wrong order renders against a stale sidecar whose
keys are offset from the new start.
- 05:36 publish scripts/yt-upload.py -> projects/SKv9fUHeckE/outputs/shorts-vertical/SKv9fUHeckE-v-01-hunting-our-engineers.mp4 (projects/SKv9fUHeckE/outputs/shorts-vertical/SKv9fUHeckE-v-01-hunting-our-engineers.mp4 --title Our Partners Are Hunting Ukraine's Military Software Engineers --description-file projects/SKv9fUHeckE/d) https://youtu.be/Np11eia-3mY -- uploaded Our Partners Are Hunting Ukraine's Military Software Engineers
- 05:36 publish scripts/yt-upload.py -> projects/SKv9fUHeckE/outputs/shorts-vertical/SKv9fUHeckE-v-02-civilian-contract.mp4 (projects/SKv9fUHeckE/outputs/shorts-vertical/SKv9fUHeckE-v-02-civilian-contract.mp4 --title You Can Work on Delta Without Being Mobilised --description-file projects/SKv9fUHeckE/description-shorts.txt) https://youtu.be/Rxjd5uqtjtI -- uploaded You Can Work on Delta Without Being Mobilised

## 2026-09-01 (later still) — published to @kitcut-hq, and per-channel grants

All four shorts (these two plus dHYrpun-XTs's two) uploaded unlisted to KitCut
(@kitcut-hq, UC2PK9SXpePZSRkT3LqiOgeg) and confirmed as real Shorts.

**Two YouTube traps, both cost a round trip.** Google's OAuth channel chooser
lists BRAND ACCOUNT names while YouTube lists CHANNEL names, so a renamed
channel is invisible: KitCut appears there as **TRNDS**. The first consent
landed on the personal channel instead and the upload refused on the channel
assertion, which is exactly what that assertion is for.

**Grants are now per channel**: `.yt-oauth/token-<handle>.json`, chosen by
`--channel`, with `--reauth` forcing a fresh consent for a channel this machine
has never used. Before this, one token.json meant authorising a second channel
burned the first -- and the misfire above would have destroyed a working
@instafill_ai grant. It did not: .env is only written for the unlabelled
default, so a named channel cannot overwrite it.
