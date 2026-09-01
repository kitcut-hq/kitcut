# flatten-pdf -- edit journal
AI notes for future sessions. Scripts append the `- HH:MM` event lines;
after each editing session, append a short prose note: what was asked,
which knob changed, why, and anything the next session should not rediscover.

## 2026-09-01
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
