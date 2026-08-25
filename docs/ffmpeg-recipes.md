# FFmpeg Recipes & Filter Chains

Tested FFmpeg commands and filter chains for common video editing tasks.

## Audio & Voiceover

### Mix Voiceover + Background Music with Ducking

Reduces background music volume when voiceover is speaking (sidechain compression).

```bash
ffmpeg -i video.mp4 -i voiceover.wav -i background-music.mp3 \
  -filter_complex "
  [1]volume=+7.04dB,asplit=2[vo1][sc];
  [2]aformat=channel_layouts=stereo[mus];
  [sc]aformat=channel_layouts=stereo[scs];
  [mus][scs]sidechaincompress=threshold=0.035:ratio=9:attack=12:release=380:makeup=1[duck];
  [vo1]aformat=channel_layouts=stereo[vos];
  [duck][vos]amix=inputs=2:normalize=0:dropout_transition=0[pre];
  [pre]alimiter=limit=0.95,loudnorm=I=-14:TP=-1.5:LRA=11[aout]
  " \
  -map 0:v -map "[aout]" -c:v copy -c:a aac -b:a 128k \
  output.mp4
```

**Parameters:**
- `threshold=0.035` — Starts ducking at -29.6 dB
- `ratio=9` — 9:1 compression (strong ducking)
- `attack=12` — Fast response (12ms)
- `release=380` — Smooth recovery (380ms)
- `makeup=1` — Full makeup gain
- `loudnorm=I=-14:TP=-1.5:LRA=11` — YouTube compliance (-14.5 LUFS)

**Result:** Music drops ~5-8 dB under speech, recovers smoothly after.

### Normalize Audio Loudness (YouTube Compliance)

```bash
ffmpeg -i input.mp3 \
  -af "loudnorm=I=-14:TP=-1.5:LRA=11" \
  output.mp3
```

**Targets:** -14 LUFS integrated loudness, -1.5 TP peak, 11 LU range.

### Extract Audio as MP3

```bash
ffmpeg -i video.mp4 -q:a 9 -n audio.mp3
```

**-q:a 9** = variable bitrate, high quality.
**-n** = don't overwrite existing files.

### Change Audio Bitrate

```bash
ffmpeg -i input.wav -b:a 128k output.wav
```

## Video Trimming & Cutting

### Trim to Timerange (10s to 80s)

```bash
ffmpeg -i input.mp4 -ss 10 -to 80 -c:v copy -c:a aac output.mp4
```

**-ss 10** = start at 10 seconds.
**-to 80** = end at 80 seconds.
**-c:v copy** = copy video stream untouched (no re-encode).

### Remove First N Seconds (Black Fade)

Trim first 0.6 seconds:

```bash
ffmpeg -i input.mp4 -ss 0.6 -c:v copy -c:a aac output.mp4
```

## Overlays & Compositing

### Circular Overlay with Anti-Aliasing

Places a 105×105 px circular talking-head at bottom-left with no jagged edges.

```bash
ffmpeg -i video.mp4 -i face-video.mp4 -i mask.png \
  -filter_complex "
  [1:v]crop=170:170:7:507,setpts=PTS-STARTPTS[face];
  [2:v]format=gray[m];
  [face][m]alphamerge,scale=105:105:flags=lanczos,format=yuva420p[bubble];
  [0:v][bubble]overlay=x=24:y=H-105-24:shortest=1[vout];
  [0:a]volume=1.0[aout]
  " \
  -map "[vout]" -map "[aout]" -c:v libx264 -c:a aac \
  output.mp4
```

**Key steps:**
1. `crop=170:170:7:507` — Extract 170×170 region (source talking head)
2. `alphamerge` — Merge video with alpha mask
3. `scale=105:105:flags=lanczos` — 30% smaller (105 vs 150 original)
4. `overlay=x=24:y=H-105-24` — Bottom-left corner, 24px margin
5. `shortest=1` — Stop overlay when video ends

**flags=lanczos** uses high-quality Lanczos resampling (better than default bilinear).

### Blur Background (Depth of Field)

```bash
ffmpeg -i input.mp4 \
  -filter_complex "split=2[orig][blur];[blur]boxblur=10[blurred];[orig][blurred]blend=all_expr=A*(1-0.3)+B*0.3" \
  output.mp4
```

Creates a shallow focus effect.

## Fade In/Out

### Fade In (First 2 Seconds)

```bash
ffmpeg -i input.mp4 \
  -vf "fade=t=in:st=0:d=2" \
  -c:a copy \
  output.mp4
```

**-vf** = video filter.
**fade=t=in:st=0:d=2** = fade in, start at 0s, duration 2s.

### Fade Out (Last 2 Seconds)

```bash
ffmpeg -i input.mp4 \
  -vf "fade=t=out:st=58:d=2" \
  -c:a copy \
  output.mp4
```

## Detection & Analysis

### Detect Frame Brightness (Fade Points)

Find where video transitions from black to full brightness:

```bash
ffmpeg -i input.mp4 -vf "format=gray" -f null - 2>&1 | grep -i "frame\|brightness"
```

Or more targeted:

```bash
ffprobe -v error -show_entries frame=pts_time,pkt_duration_time \
  -of csv=p=0 -select_streams v:0 input.mp4 | head -20
```

### List All Frames (Debug)

```bash
ffmpeg -i input.mp4 -vf "select='gt(scene\,0.4)',showinfo" -f null - 2>&1 | head -30
```

Shows scene changes (cuts/transitions).

## Batch Operations

### Convert All MP4s to WebM (Smaller for Web)

```bash
for f in *.mp4; do
  ffmpeg -i "$f" -c:v libvpx-vp9 -b:v 1000k -c:a libopus -b:a 128k "${f%.mp4}.webm"
done
```

### Create Thumbnail Every 5 Seconds

```bash
ffmpeg -i input.mp4 -vf fps=1/5 -q:v 2 thumb_%04d.jpg
```

## Quick Reference: Common Flags

| Flag | Meaning |
|------|---------|
| `-c:v copy` | Copy video stream (no re-encode) |
| `-c:a aac` | Use AAC audio codec |
| `-b:a 128k` | Audio bitrate (128 kbps) |
| `-ss HH:MM:SS` | Seek/start time |
| `-to HH:MM:SS` | End time (with trim) |
| `-vf "filter"` | Apply video filter |
| `-af "filter"` | Apply audio filter |
| `-filter_complex` | Complex multi-stream filter graph |
| `-map 0:v` | Map video from input 0 |
| `-map 0:a` | Map audio from input 0 |
| `-map "[label]"` | Map from filter output label |
| `-n` | Don't overwrite output |
| `-y` | Auto-overwrite output |
| `-shortest` | Stop at shortest stream |

## Performance Tips

1. **Use `-c:v copy` when possible** — Skip re-encoding (10× faster)
2. **Chain filters instead of separate ffmpeg calls** — Reduces disk I/O
3. **Use H.264 for compatibility** — `-c:v libx264 -preset fast`
4. **Test on short segment first** — `-ss 0 -to 10` to validate 5s clip
5. **Specify output format explicitly** — `-f mp4`, `-f webm`, etc.

## Reference

- [FFmpeg Filters](https://ffmpeg.org/ffmpeg-filters.html)
- [FFmpeg Audio Filters](https://ffmpeg.org/ffmpeg-filters.html#Audio-Filters)
- [Sidechain Compression](https://ffmpeg.org/ffmpeg-filters.html#sidechaincompress)
