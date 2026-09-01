# flatten-pdf -- edit journal
AI notes for future sessions. Scripts append the `- HH:MM` event lines;
after each editing session, append a short prose note: what was asked,
which knob changed, why, and anything the next session should not rediscover.

## 2026-09-01
- 14:34 project created
- 15:08 render scripts/tighten-cut.py -> projects/flatten-pdf/outputs/flatten-pdf-tight.mp4 (--manifest projects/flatten-pdf/tighten.json)
- 15:18 render scripts/run-captions.py -> projects/flatten-pdf/outputs/flatten-pdf-tight-captioned.mp4 (--input projects/flatten-pdf/outputs/flatten-pdf-tight.mp4 --id flatten-pdf-tight --project flatten-pdf --style config/presets/instafill.json --no-overlays --force render)
- 15:23 render scripts/tighten-cut.py -> projects/flatten-pdf/outputs/flatten-pdf-tight.mp4 (--manifest projects/flatten-pdf/tighten.json --force)
- 15:25 render scripts/tighten-cut.py -> projects/flatten-pdf/outputs/flatten-pdf-tight.mp4 (--manifest projects/flatten-pdf/tighten.json --force)
- 15:27 render scripts/run-captions.py -> projects/flatten-pdf/outputs/flatten-pdf-tight-captioned.mp4 (--input projects/flatten-pdf/outputs/flatten-pdf-tight.mp4 --id flatten-pdf-tight --project flatten-pdf --style config/presets/instafill.json --no-overlays --force ass)

### Session note — first edit, 2026-09-01

**Asked for:** cut the "ekaying" and the long silences out of a raw screen
recording, remove the bit near the end where he says he will pause the video,
add captions that do not look like the red ones from last time, and prepare
everything needed to publish on @instafill_ai.

**What the material actually was.** One file, 4:54, 1280x720, VFR averaging
30.02 fps, with the browser, the round webcam bubble and the narration already
composited by the recorder. `screencast-cut.py` cannot touch that — it lays a
film out in camera time against a *separate* screen recording. So this session
wrote `scripts/tighten-cut.py`, the subtractive pass for a single clock, and
the `video-tighten` skill that teaches it.

**The cut.** 42% of the source was silence over 0.5s. `min_silence 0.7 /
keep_pause 0.35`, picked off the `--list` sweep: 0.6/0.30 buys another six
seconds and starts making the webcam bubble jump faster than the eye forgives.
Two named removals do the rest — the 14.5s where he tries to say which forms
are already fillable and never lands it (Whisper's own confidence collapses
there, 0.22 on one word), and the 20s wait plus "we'll pause the video". Result
3:21, 31% off.

**Do not re-transcribe with the default settings.** The first pass
(distil-large-v3, no hotwords) spelled the product three different ways and
called the tool "flat and PDF". `--hotwords-file config/vocab/instafill.txt`
with `large-v3` fixed it; that flag was added this session. It is ~45 minutes
on this CPU, which is why the transcript is committed-adjacent and why
`corrections[]` exists rather than a re-run.

**Two bugs this film found, both now fixed in the tooling:**
- `apply_corrections` first spread replacement words evenly across the phrase's
  whole span. A phrase contains pauses; words landed in them; the pause cut
  then deleted the pauses and the words with them, and the film was captioned
  "So you just tool." for "So you can just open this tool." Retiming is
  one-for-one where the word count matches, and walks spoken time only where it
  does not.
- `verify-captions.py` sampled a box ±fsize/2 around each word, which on a
  two-line card reaches into the line below and reads its colour. It failed a
  provably correct ASS. The box is clamped to its own line now.

**Captions:** `config/presets/instafill.json`, written this session. Near-black
slab at 12% transparency, sentence case, mint `#13BA82` spotlight. `red-card`
was measured off a news channel and fights a screen recording for attention —
that is what "the red ones looked unprofessional" was actually about. The
geometry is fitted around the webcam bubble (x<190) and the taskbar (y>682);
`_geometry` in the preset records both.

**Next session:** the film is rendered and not published. `title.txt`,
`description.txt` and `chapters.txt` are ready; `yt-upload.py` has not been run
and no name label was added (his title was never confirmed).
- 18:45 project created
- 18:59 render scripts/cut-clips.py -> projects/flatten-pdf/outputs/shorts/flatten-pdf-01-free-tool.mp4 (--manifest projects/flatten-pdf/clips-vertical.json --no-captions)
- 18:59 render scripts/cut-clips.py -> projects/flatten-pdf/outputs/shorts/flatten-pdf-02-whole-packet.mp4 (--manifest projects/flatten-pdf/clips-vertical.json --no-captions)
- 19:00 render scripts/cut-clips.py -> projects/flatten-pdf/outputs/shorts/flatten-pdf-01-free-tool.mp4 (--manifest projects/flatten-pdf/clips-vertical.json --no-captions --force)
- 19:01 render scripts/cut-clips.py -> projects/flatten-pdf/outputs/shorts/flatten-pdf-02-whole-packet.mp4 (--manifest projects/flatten-pdf/clips-vertical.json --no-captions --force)
- 19:04 render scripts/cut-clips.py -> projects/flatten-pdf/outputs/shorts/flatten-pdf-01-free-tool.mp4 (--manifest projects/flatten-pdf/clips-vertical.json --no-captions --force)
- 19:04 render scripts/cut-clips.py -> projects/flatten-pdf/outputs/shorts/flatten-pdf-02-whole-packet.mp4 (--manifest projects/flatten-pdf/clips-vertical.json --no-captions --force)
- 19:05 render scripts/cut-clips.py -> projects/flatten-pdf/outputs/shorts/flatten-pdf-01-free-tool.mp4 (--manifest projects/flatten-pdf/clips-vertical.json --no-captions --force --only 01-free-tool)
- 19:07 render scripts/cut-clips.py -> projects/flatten-pdf/outputs/shorts/flatten-pdf-02-whole-packet.mp4 (--manifest projects/flatten-pdf/clips-vertical.json --no-captions --force --only 02-whole-packet)

### Session note — stage 1, picture only

Asked for two shorts out of our own `youtu.be/6LQnRd0JxGU` with a voice-over
replacing the original sound, then asked to see the cuts first and decide about
the voice after. So this session is picture only. **Neither render is the
deliverable look** — they carry the source narration as a reference track and no
captions, because captions get rebuilt from the voice-over's word timings and
burning the old speech now would be work thrown away.

**A screencast is not a talking head, and `auto-reframe.py` is the wrong tool.**
It face-tracks a subject into a 607 px 9:16 window; there is no subject, and
607 px of a 1280 px browser is unreadable. `cut-clips.py` grew `crop_rect` /
`place` / `mask` for this — see the README section and the video-shorts skill.

**The webcam is what makes this hard, and masking it is what unlocked the
framing.** Three things had to go: the burned caption card (source y 612-660),
the taskbar (y 682+) and the webcam PiP (x 21-183, y 498-660). The first two sit
below the content, so the rect drops them. The webcam sits *inside* the content,
in the same vertical band as the buttons the demo is about — every attempt to
crop around it either clipped the headline (x≥200 cuts a hero starting at x=82)
or lost the buttons (y≤495 cuts the Download button at y=513). Masking it first
decoupled the two decisions and the rect could then be chosen for readability
alone. `delogo` is the only mode that actually disappears: `blur` turned the
dark circle into a grey smudge, and copying the strip to its right duplicated
the buttons next to it. Both were rendered and looked at before being rejected.

**Verified with a detector, and calibrated.** YuNet found the webcam in 30/30
sampled source frames (box [69,539,51,68], inside the mask rect) and 0/80 across
the two finished shorts. The source number is the half that makes the zero mean
anything — that is the CLAUDE.md rule about calibrating a detector where the
thing provably exists.

**Both moments were re-picked twice after looking at contact sheets.** The first
attempt at short 1 opened on 23 seconds of the landing hero being read aloud;
the first attempt at short 2 spent 30 of its 49 seconds on an "Adding fields"
progress bar that goes 1% → done without visibly moving. Neither was visible
from the transcript — only from a 4x3 sheet of the render. Short 2 now opens 3 s
before the status chip flips at **167.75 s**, found by tracking the chip's hue
across sampled frames rather than guessing.

**720p is the ceiling and the token cannot lift it.** YouTube has not processed
1080p (checked across six player clients); Data API v3 has no video-download
endpoint and Studio's "Download original" has no API surface; no master on this
machine. The framing was chosen so 720p is enough — the rect is 900-1280 px wide
at source and lands at 1080 wide, so nothing is upscaled more than 1.2x. If the
master turns up, both manifests re-render against it with a one-line change.

**Next session (stage 2):** write the voice-over to the picture, not to the old
speech. That needs a timed-script plan source in `dub-clips.py` — `build_plan()`
derives every slot from the source transcript's pauses and hard-exits when there
are none, so free-form narration needs `--script` taking `[{"t":…, "text":…}]`
and skipping segmentation. Everything after that (fit → place → words.json →
`cut-clips.py --dub`) works unchanged. Voice is Brian, chosen by the user;
audition with `dub-tts.py --say` before a batch. Render to tag `vo`, which makes
new files and leaves these two alone.
- 19:20 dub scripts/dub-clips.py -> projects/flatten-pdf/outputs/dub/flatten-pdf-01-free-tool.vo.wav (--manifest projects/flatten-pdf/clips-vertical.json --only 01-free-tool --script projects/flatten-pdf/vo/01-free-tool.json --tts elevenlabs --voice brian --tag vo --outdir projects/flatten-pdf/outputs) -- sync 77.0%, elevenlabs/nPczCjzI2devNBz1zQrb
- 19:21 dub scripts/dub-clips.py -> projects/flatten-pdf/outputs/dub/flatten-pdf-01-free-tool.vo.wav (--manifest projects/flatten-pdf/clips-vertical.json --only 01-free-tool --script projects/flatten-pdf/vo/01-free-tool.json --tts elevenlabs --voice brian --tag vo --outdir projects/flatten-pdf/outputs) -- sync 78.1%, elevenlabs/nPczCjzI2devNBz1zQrb
- 19:21 dub scripts/dub-clips.py -> projects/flatten-pdf/outputs/dub/flatten-pdf-01-free-tool.vo.wav (--manifest projects/flatten-pdf/clips-vertical.json --only 01-free-tool --script projects/flatten-pdf/vo/01-free-tool.json --tts elevenlabs --voice brian --tag vo --outdir projects/flatten-pdf/outputs) -- sync 80.3%, elevenlabs/nPczCjzI2devNBz1zQrb
- 19:22 dub scripts/dub-clips.py -> projects/flatten-pdf/outputs/dub/flatten-pdf-01-free-tool.vo.wav (--manifest projects/flatten-pdf/clips-vertical.json --only 01-free-tool --script projects/flatten-pdf/vo/01-free-tool.json --tts elevenlabs --voice brian --tag vo --outdir projects/flatten-pdf/outputs) -- sync 79.3%, elevenlabs/nPczCjzI2devNBz1zQrb
- 19:23 render scripts/cut-clips.py -> projects/flatten-pdf/outputs/shorts/flatten-pdf-01-free-tool-vo.mp4 (--manifest projects/flatten-pdf/clips-vertical.json --only 01-free-tool --dub projects/flatten-pdf/outputs/dub --dub-tag vo)

### Session note — stage 2 on short 1: voice-over, captions, publish package

Asked to take short 1 through to publish-ready. Done and dry-run verified;
**not uploaded** — waiting on the go-ahead.

**`dub-clips.py` grew `--script`.** `build_plan()` derives every slot from the
original speaker's pauses, which is right for a dub and wrong for a voice-over
that replaces the sound — the old rhythm is the thing being fixed. `--script`
takes `[{"t":…, "text":…, "tight":…}]` timed against the picture, implies
`--engine manual`, and refuses unless `--only` narrows to one clip. Everything
downstream is untouched.

**Script units are `free`, and that mattered.** `fit_unit` draws a short line out
to fill its slot, because dead air under a moving mouth is worse than a slightly
long line. Nothing is lip-syncing here, so that stretch is just a drawl —
`free` skips it and the slack stays a pause. Brian reads at roughly 4 words/sec
against the planner's 3.2, so the first pass came in short on all seven slots and
would otherwise have been drawled end to end.

**Do not gate a written voice-over on `sync`.** It measures agreement with the
ORIGINAL speech, which a voice-over deliberately discards, and it read 79.3% on
a take where every line is right. The gate used instead: all seven slots report
`natural` (no rate change, no `tight` fallback, nothing squeezed), nothing
overruns, and the spoken words are the written ones — verified by transcribing
the generated wav with faster-whisper and diffing it against the script. Exact,
word for word (Whisper writes "97" where the script says "Ninety-seven"; that is
its numeral normalisation, not a mispronunciation).

**Three re-timing passes, and the reason is worth remembering.** The last three
lines needed 7.3 s of speech in 7.4 s of clip, so every nudge moved the squeeze
to a neighbour: line 7 fell back to `tight`, then line 6 took a +17% rate, then
line 7 again. The fix was to SHORTEN line 5, not to re-time a fourth time. Do not
let ElevenLabs run at its +20% cap — it is audible.

**Beats were read off the RENDERED clip**, sampled every 1-2 s, not off the
transcript. Clip time: 0.5 the free-tool page, 2.0 the file dialog, 5.0 the file
in the drop zone and flattening, 6.0 the green "Flattened. 97 form fields merged
into the page" with Download, 13.0 the flat PDF open, 14-20 its pages with the
boxes gone.

**Publish package** is in `description-01.txt` and recorded in `project.json`;
the dry-run asserted the token points at Instafill / @instafill_ai /
UCa57I5DFqulQaoMR_0H--kA. Privacy unlisted.

**Left for next time:** short 2 is still stage 1 — picture only, source audio, no
captions. Same treatment when wanted; its beats are the status flip at 3.25 s
into the clip, the "flat document / fields added automatically" modal, then the
field-covered pages.
- 19:30 publish scripts/yt-upload.py -> projects/flatten-pdf/outputs/shorts/flatten-pdf-01-free-tool-vo.mp4 (projects/flatten-pdf/outputs/shorts/flatten-pdf-01-free-tool-vo.mp4 --title Flatten a PDF for free - 97 form fields gone in seconds #Shorts --description-file projects/flatten-pdf/description-01.txt -) https://youtu.be/hmHbL-66G-o -- uploaded Flatten a PDF for free - 97 form fields gone in seconds #Shorts

### Published — short 1, as a Short

`https://youtu.be/hmHbL-66G-o`, unlisted, on @instafill_ai
(UCa57I5DFqulQaoMR_0H--kA). The uploader re-read it afterwards and title and
privacy came back as asked.

**There is no API flag for "this is a Short".** YouTube classifies on format
alone — vertical or square, three minutes or less. This file is 1080x1920 and
20.5 s, so it qualified without anything special; the `#Shorts` hashtag in the
title is a legacy hint that does not decide it.

**How to check, and the trap in checking.** `youtube.com/shorts/<id>` serves
**200** for a Short and **303**-redirects to `/watch` for a regular video. Ours
returned 303 for the first couple of minutes and 200 afterwards — the
classification only lands once `processingDetails.processingStatus` reaches
`succeeded`. Query that before concluding the upload came out as a normal video.

Unlisted was deliberate (standing preference: a review link that opens for
others). It does mean the Short will not appear in the Shorts feed — that needs
public.
