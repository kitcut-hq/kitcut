# KitCut

**Raw footage in. Finished video out. On your own machine.**

- You say what you want in plain words. Claude does the editing.
- Nothing is uploaded until you say "publish."
- Every decision is remembered, so any video can be changed later in one sentence.

## Start

1. Install [Claude Code](https://claude.com/claude-code).
2. Open this folder in it. Say **"Set this up."** Claude installs what's missing and renders a test video to prove it works.
3. Record something. Say **"Import today's recordings."**

No dragging files. KitCut finds the session's recordings on your PC and on a connected phone, drops duplicate copies, orders them by when they were actually shot, and knows which ones have sound. Then say what you want made.

## Capabilities

### Captions
- **Word-synced captions**, spoken word highlighted, burned onto the whole video.
- **Style from a preset** or measured off a reference video and its brand colours.
- **Dodges the video's own graphics.**
- **Sync proven on real frames** before any render.

### Shorts
- **Finds the episodes** in a long video from what is said.
- **Opens on the hook**, within the first two seconds.
- **Vertical 9:16 with face tracking.**
- **Shorts from a screen recording**, camera placed and masked where you want it.
- **Animated social-handle badge.**
- **Captions re-rendered at vertical size.**

### Dubbing
- **Dub into another language keeping the rhythm**: speech starts and stops with the mouth.
- **Free voice or premium voice.**
- **Every line measured**, misfits re-tuned.
- **Captions timed from the dub.**
- **Replace a narration with a written script**, timed to the picture.

### Screen recording + camera
- **Syncs a screen recording with a phone take** that were never in sync, proven with paired frames.
- **Cuts pauses** only where the speaker is silent *and* the screen is still.
- **Camera picture-in-picture**, full-frame wherever the screen has nothing to show.
- **Start and end chosen by quoting what is said.**
- **Separately shot intro and outro**, with cutaway footage over them.
- **Phone import verified complete** before anything is cut.

### Multi-camera events
- **Lines up any number of cameras** from their sound alone, to the exact frame.
- **Cuts between angles** following who is speaking.
- **Tells cameras apart** by background or by face.
- **Benchmarks itself** against professionally edited videos, scored frame by frame.
- **Annotated review render** that explains each cut on screen.

### Silent screen recordings
- **One film from a session of silent desktop captures**, voice-over added later.
- **Drops dead air, fast-forwards** stretches where only an AI panel is streaming.
- **Hits a target length**, each option priced first.
- **Finds and blurs** card numbers, CVVs, IBANs, phones, emails, addresses.
- **Follows each secret's pixels** as it scrolls; measures what the blur caught.
- **Before/after review sheet**; nothing renders unapproved.
- **Draft of the riskiest minute** before the full render.
- **Final gate searches the render** for the secrets; patches and loops until clean.

### Graphics
- **Lower-third name labels.**
- **Image overlays and end cards**: entrance animation, transparency, footage under it blurred, dimmed or black-and-white.
- **Card designer**: template × brand × words. End cards, title cards, quotes, stats, corner tags.
- **Applied inside the render**, never a re-encode.

### Publishing
- **YouTube upload**, resumable, confirmed on the right channel, unlisted by default.
- **Chapters** from the transcript, written into the description.
- **Channel audit** for videos still missing chapters.
- **Delete**, dry run first.

### Memory
- **Every video has a record**: what is on each render, which setting controls it, where it went.
- **A journal of decisions**, written for the next session.
- **Change one thing later** in one sentence; only that re-renders.
- **Stale renders flagged** when a decision changed after them.

### Judgement
- **Every decision priced before encoding**: what a setting removes, what it costs.
- **Everything verified before a render is spent.**
- **Channel audit**: can KitCut reproduce a channel's editing style? Scored honestly.

## Requirements

| | |
|---|---|
| OS | Windows |
| GPU | NVIDIA recommended. Captions, shorts, dubbing run without one, slower. Screen-recording and multi-camera films need it. |
| Accounts | None. YouTube publishing and the premium dub voice are the only exceptions. |

## Not yet

Colour grading. Filler-word removal. Mac.

## Technical reference

Every command, setting and trap: [`docs/reference.md`](docs/reference.md).
