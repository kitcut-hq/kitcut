# Video Editing Workspace Setup Complete

Organized and ready for video production workflows.

## What's Been Created

```
C:\instafill\video-editing/
├── sources/                          # Store original videos here (untouched)
├── outputs/                          # Final rendered videos
├── audio/                            # Voiceovers, background music, sound effects
├── scripts/                          # Processing scripts
│   ├── transcribe-audio.py          # Speech-to-text with word timestamps
│   └── generate-voiceover.py        # TTS + music ducking pipeline
├── config/                           # Configuration and presets
│   ├── elevenlabs-voices.json       # Voice library reference (25+ voices)
│   ├── video-specs.template.json    # Project metadata template
│   └── ffmpeg-presets.txt           # (Create as needed)
├── temp/                             # Working/intermediate files (safe to delete)
├── docs/                             # Documentation
│   ├── QUICKSTART.md                # Ready-to-use workflows (3 main tasks)
│   ├── ffmpeg-recipes.md            # 30+ FFmpeg commands and filters
│   ├── whisper-sync-guide.md        # (Create as needed)
│   └── video-troubleshooting.md     # (Create as needed)
├── .env.template                    # Environment variables template
├── .env                              # (Copy .env.template here, add credentials)
├── .gitignore                        # Ignore temp files, large media, .env
├── README.md                         # Full documentation and setup
└── WORKSPACE-SETUP.md               # This file
```

## Quick Setup Checklist

- [ ] Copy `.env.template` to `.env`
- [ ] Add `ELEVENLABS_API_KEY` to `.env`
- [ ] Add `OPENAI_API_KEY` to `.env`
- [ ] Verify FFmpeg installed: `ffmpeg -version`
- [ ] Read `docs/QUICKSTART.md` for first project

## What Each Directory Is For

| Directory | Purpose | File Types |
|-----------|---------|-----------|
| `sources/` | Original video files (NEVER edit these) | `.mp4`, `.mov`, `.mkv` |
| `outputs/` | Final rendered videos ready to share | `.mp4`, `.webm` |
| `audio/` | Voiceovers, background music, sound effects | `.mp3`, `.wav`, `.m4a`, `.flac` |
| `scripts/` | Python and shell scripts for processing | `.py`, `.sh` |
| `config/` | FFmpeg presets, settings, JSON metadata | `.json`, `.txt` |
| `temp/` | Working files, intermediate renders | (anything, safe to delete) |
| `docs/` | Guides, recipes, troubleshooting | `.md` |

## Key Files to Know

### For Getting Started
- **`QUICKSTART.md`** — Copy-paste workflows for 4 common tasks
- **`README.md`** — Full documentation, directory guide, tips

### For Doing Work
- **`scripts/transcribe-audio.py`** — Convert audio to text with word timestamps
- **`scripts/generate-voiceover.py`** — Generate TTS with music ducking
- **`docs/ffmpeg-recipes.md`** — 30+ ready-to-use FFmpeg commands

### For Configuration
- **`.env`** — Your API keys (keep secret, don't commit)
- **`config/elevenlabs-voices.json`** — Voice IDs for TTS
- **`config/video-specs.template.json`** — Project metadata template

## Project Workflow Pattern

1. **Organize inputs** → Put source video in `sources/`, audio in `audio/`
2. **Create script** → Write `scripts/my-project.json` with timing + text
3. **Generate assets** → Run `transcribe-audio.py` or `generate-voiceover.py`
4. **Render final** → Use FFmpeg command from `docs/ffmpeg-recipes.md`
5. **Save output** → Final video goes in `outputs/`
6. **Document** → Copy `config/video-specs.template.json` to save project settings

## Available Tools

### Python Scripts (in `scripts/`)
- **transcribe-audio.py** — OpenAI Whisper API wrapper for speech-to-text
- **generate-voiceover.py** — ElevenLabs TTS + FFmpeg audio mixing

### FFmpeg Recipes (in `docs/ffmpeg-recipes.md`)
- Audio mixing with sidechain compression (ducking)
- Circular overlays with anti-aliasing
- Fade detection and trimming
- Loudness normalization (YouTube compliant)
- Batch operations

### Documentation
- **QUICKSTART.md** — 4 ready-to-use workflows (copy-paste commands)
- **ffmpeg-recipes.md** — 30+ command-line recipes with explanations
- **README.md** — Full documentation and setup guide

## API Credentials You'll Need

### ElevenLabs (Text-to-Speech)
- **Key:** Get from https://elevenlabs.io/app/settings/api-keys
- **Scope:** TTS only (transcription uses OpenAI)
- **Cost:** 0.5 credits/character with `eleven_turbo_v2_5` (recommended)
- **Default voice:** Brian (nPczCjzI2devNBz1zQrb) — natural US male narrator

### OpenAI (Speech-to-Text / Whisper)
- **Key:** Get from https://platform.openai.com/account/api-keys
- **Use:** Transcribing audio, verifying TTS quality
- **Cost:** ~$0.02 per minute of audio

## Cost Estimates (per project)

Based on HPD OMO voiceover (210 words, 14 lines):

| Task | Cost | Model |
|------|------|-------|
| TTS generation | ~100 ElevenLabs credits | eleven_turbo_v2_5 |
| Transcription | ~$0.07 | Whisper |
| Total (1 project) | ~$2.00 | — |

Costs drop with batch work and are tiny compared to time saved.

## Workflow Tips

1. **Default to `eleven_turbo_v2_5`** — Saves 50% vs multilingual v2, sounds excellent
2. **Test early** — Render 5-10 second test before full video
3. **Use `-c:v copy`** — 10× faster (skip re-encoding when possible)
4. **Document your settings** — Save FFmpeg commands in `config/` for reuse
5. **Keep sources untouched** — Never edit files in `sources/`

## Common First Project

**Add voiceover to existing video:**

```powershell
# 1. Prepare
Copy-Item scripts/my-project.json.template scripts/my-project.json
# Edit with your timing + text

# 2. Generate
python scripts/generate-voiceover.py `
  --script scripts/my-project.json `
  --output temp/voiceover.wav `
  --background-music audio/background.mp3

# 3. Mix into video
ffmpeg -i sources/video.mp4 -i temp/voiceover.wav `
  -c:v copy -c:a aac `
  -filter_complex "[1]alimiter=limit=0.95,loudnorm=I=-14:TP=-1.5:LRA=11[aout];[0:a][aout]amix=inputs=2[mixed]" `
  -map 0:v -map "[mixed]" `
  outputs/final.mp4
```

## Next Steps

1. **Read:** `docs/QUICKSTART.md` for step-by-step workflows
2. **Configure:** Fill in `.env` with API keys
3. **Test:** Run transcription on a sample audio file
4. **Create:** Your first project!

## Questions?

- **How do I...?** → Check `docs/QUICKSTART.md`
- **FFmpeg command for...?** → Check `docs/ffmpeg-recipes.md`
- **API/tool question** → Check full `README.md` or memory files

---

**Workspace ready!** Start with `docs/QUICKSTART.md` for your first project.
