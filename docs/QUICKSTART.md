# Quick Start: Video Editing Workflows

Ready-to-use workflows for common video editing tasks.

## Initial Setup (One-time)

### 1. Install Dependencies

**Python packages:**
```powershell
pip install requests
```

**System tools:**
- FFmpeg: `choco install ffmpeg` (or download from ffmpeg.org)
- FFprobe: Included with FFmpeg

### 2. Configure Credentials

```powershell
cd C:\instafill\video-editing
Copy-Item .env.template .env
```

Edit `.env` and add:
- `ELEVENLABS_API_KEY` from https://elevenlabs.io/app/settings/api-keys
- `OPENAI_API_KEY` from https://platform.openai.com/account/api-keys

## Workflow 1: Add Voiceover to Existing Video

**Goal:** Add narration with background music ducking.

### Step 1: Prepare Your Recording

1. Record yourself speaking (use voice memo, Zoom, Audacity, etc.)
2. Export as `.m4a` or `.wav`
3. Place in `audio/` folder

### Step 2: Transcribe to Verify Timing

```powershell
cd C:\instafill\video-editing

python scripts/transcribe-audio.py audio/my-recording.m4a --pretty > temp/transcript.json
```

This creates a JSON file with word-level timestamps. **Review it** to check:
- Are words spelled correctly? (Whisper may mishear)
- Are timings reasonable? (should be ~0.5s per word)

### Step 3: Create Script File (JSON)

Manually craft a script file with target timings:

`scripts/my-project-script.json`:
```json
[
  {"time": 1.60, "text": "First line of narration."},
  {"time": 9.10, "text": "Second line where you pause."},
  {"time": 15.50, "text": "Third line on the action."}
]
```

Times can be adjusted based on video content. Plan them by:
1. Opening the video in a player
2. Pausing at key moments
3. Noting the timestamp
4. Writing what should be said there

### Step 4: Generate TTS Voiceover

```powershell
python scripts/generate-voiceover.py `
  --script scripts/my-project-script.json `
  --output temp/voiceover-with-music.wav `
  --background-music audio/background-music.mp3 `
  --voice nPczCjzI2devNBz1zQrb `
  --model eleven_turbo_v2_5
```

This:
1. Generates TTS for each line
2. Places them at the right times
3. Mixes in background music
4. Applies ducking (music gets quieter when speaking)
5. Normalizes loudness to -14.5 LUFS

**Cost:** ~0.5 credits per character with turbo model.

### Step 5: Combine into Final Video

```powershell
ffmpeg -i sources/original-video.mp4 -i temp/voiceover-with-music.wav `
  -c:v copy -c:a aac -b:a 128k `
  -filter_complex "[1]alimiter=limit=0.95,loudnorm=I=-14:TP=-1.5:LRA=11[aout];[0:a][aout]amix=inputs=2:normalize=0:dropout_transition=0[mixed]" `
  -map 0:v:0 -map "[mixed]" `
  outputs/final-video-with-vo.mp4
```

Done! Final video is in `outputs/`.

---

## Workflow 2: Add Overlay (Talking Head)

**Goal:** Add a circular talking-head video in corner without syncing lips.

### Step 1: Prepare Source Videos

```
sources/main-video.mp4          # Your main video
sources/talking-head-video.mp4  # Video clip to extract head from
```

### Step 2: Create Circular Overlay

```powershell
# Create a circular mask (1x for source size, then scale down)
# Assuming the head is in a 170x170 region at position (7, 507)

ffmpeg -i sources/talking-head-video.mp4 `
  -i sources/main-video.mp4 `
  -filter_complex "
  [0:v]crop=170:170:7:507,setpts=PTS-STARTPTS[face];
  format=gray[m];
  [face][m]alphamerge,scale=105:105:flags=lanczos,format=yuva420p[bubble];
  [1:v][bubble]overlay=x=24:y=H-105-24:shortest=1[vout]
  " `
  -map "[vout]" -map 1:a `
  outputs/video-with-overlay.mp4
```

**Parameters:**
- `crop=170:170:7:507` — Extract 170×170 region (adjust based on your head location)
- `scale=105:105` — Final size (adjust for 30% smaller: original × 0.7)
- `x=24:y=H-105-24` — Position (24px from left, 24px from bottom with 105px height)

### Step 3 (Optional): Adjust Position

Find where your talking head is in the source video by using FFmpeg's `-vf "select='eq(n\,100)'"` to extract frame 100, then measure pixel positions.

**Common positions:**
- **Bottom-left:** `x=24:y=H-105-24`
- **Bottom-right:** `x=W-105-24:y=H-105-24`
- **Top-left:** `x=24:y=24`
- **Top-right:** `x=W-105-24:y=24`

---

## Workflow 3: Trim Fade-In/Out

**Goal:** Remove black frames at start or end.

### Step 1: Detect Fade Points

```powershell
ffmpeg -i sources/video.mp4 -vf "select='gt(scene\,0.05)',showinfo" -f null - 2>&1 | head -20
```

Look for the timestamp where the video becomes bright.

### Step 2: Trim Start

Remove first 0.6 seconds:

```powershell
ffmpeg -i sources/video.mp4 -ss 0.6 -c:v copy -c:a aac outputs/video-no-fade.mp4
```

Or trim end at 77 seconds:

```powershell
ffmpeg -i sources/video.mp4 -to 77 -c:v copy -c:a aac outputs/video-trimmed.mp4
```

---

## Workflow 4: Extract Audio for Editing

**Goal:** Pull audio out, edit in DAW, put back.

### Step 1: Extract

```powershell
ffmpeg -i sources/video.mp4 -q:a 9 -n audio/extracted.mp3
```

### Step 2: Re-combine

```powershell
ffmpeg -i sources/video.mp4 -i audio/edited.wav -c:v copy -map 0:v:0 -map 1:a outputs/video-new-audio.mp4
```

---

## Common Issues

### "ffmpeg not found"
Install FFmpeg from https://ffmpeg.org/download.html or `choco install ffmpeg`. Verify: `ffmpeg -version`

### "ElevenLabs key not found"
Check `.env` file exists and has `ELEVENLABS_API_KEY=sk_xxxx`. Run from the `C:\instafill\video-editing\` directory.

### "OpenAI key missing"
Transcription needs OpenAI Whisper. Add `OPENAI_API_KEY=sk-xxxx` to `.env`.

### "Audio out of sync"
Audio started late? Use FFmpeg delay:
```powershell
ffmpeg -i video.mp4 -i audio.wav -itsoffset 0.5 -i audio.wav -c:v copy -map 0:v:0 -map 2:a output.mp4
```
(offset by 0.5s; adjust as needed)

### "File is huge"
Lower bitrate:
```powershell
ffmpeg -i input.mp4 -b:v 4000k -c:a aac -b:a 96k output.mp4
```

---

## File Checklist

Before starting a project, ensure you have:

- [ ] `.env` file with API keys
- [ ] `sources/original-video.mp4`
- [ ] `audio/background-music.mp3` (if using)
- [ ] `scripts/my-project-script.json` (if narrating)
- [ ] FFmpeg installed and in PATH (`ffmpeg -version`)

## Pro Tips

1. **Test on short segment first:** Render 10 seconds before the full video
   ```powershell
   -ss 0 -to 10
   ```

2. **Use copy when possible:** `-c:v copy` skips re-encoding (10× faster)

3. **Check bitrates:** 
   - Video: 4-8 Mbps for 720p
   - Audio: 96-128 kbps (128 for voiceover + music)

4. **Save your FFmpeg commands:** Paste them into `config/ffmpeg-presets.txt` for next time

5. **Default to turbo model:** ElevenLabs `eleven_turbo_v2_5` is 0.5 credits/char vs 1.0 for multilingual

---

## Next: Read Full Documentation

- **FFmpeg recipes:** `docs/ffmpeg-recipes.md`
- **Full README:** `README.md`
- **Voiceover syncing tips:** `docs/whisper-sync-guide.md` (coming soon)
