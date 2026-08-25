# Word-synced burned-in captions

Pipeline for adding real-time transcript captions to a video, styled as a solid
lower-third card with the currently-spoken word highlighted.

**Primary entry point** (see `.claude/skills/video-captions/SKILL.md` for the
full reference — stages, presets, resuming, traps):

```powershell
python -X utf8 -E scripts/run-captions.py --url "<URL>" --style config/presets/red-card.json
```

The manual per-stage commands below document the anatomy; artifact paths shown
are the ones the orchestrator uses (`transcripts/<id>.words.json` for the
transcript, `temp/` for everything regenerable).

Style was derived by measuring `youtu.be/egr4Y4oZgLM` at t=393 on a native
1920x1080 frame: `#FF0000` card, rounded corners, white bold uppercase, centred,
2 lines max, 30 px cap height, 44 px line spacing, card bottom 170 px above the
frame bottom.

## Run order

```powershell
# 1. Download -- PIN the audio track. This video carries a YouTube AI auto-dub
#    as a second track; a bare bestaudio selector can silently fetch English.
#    Suffix -1 = original language, -0 = dubbed.
yt-dlp -f "299+140-1" --merge-output-format mp4 `
  -o "sources/%(id)s-1080p60.%(ext)s" --no-overwrites "<URL>"

# 2. ASR audio (16 kHz mono is what Whisper resamples to internally)
ffmpeg -i sources/<ID>-1080p60.mp4 -vn -sn -dn -map 0:a:0 `
  -ac 1 -ar 16000 -c:a pcm_s16le audio/<ID>.16k.mono.wav

# 3. Word-level transcript
python -X utf8 -E scripts/transcribe-words.py audio/<ID>.16k.mono.wav `
  --out transcripts/<ID>.words.json --raw-out temp/asr.raw.json

# 4. Find the source's own lower-third graphics (so cards can dodge them)
python -X utf8 -E scripts/detect-overlays.py `
  --src sources/<ID>-1080p60.mp4 --out temp/overlays.json --fps 4

# 5. Build the ASS
python -X utf8 -E scripts/build-captions-ass.py `
  --words transcripts/<ID>.words.json --style config/presets/red-card.json `
  --overlays temp/overlays.json `
  --out temp/captions.ass --debug-out temp/captions.debug.json

# 6. Prove sync before committing to a long render
python -X utf8 -E scripts/verify-captions.py `
  --debug temp/captions.debug.json --style config/presets/red-card.json `
  --ass temp/captions.ass --samples 60

# 7. Burn in
ffmpeg -i sources/<ID>-1080p60.mp4 `
  -vf "ass=filename=temp/captions.ass:fontsdir=fonts:shaping=simple,format=yuv420p" `
  -c:v h264_nvenc -preset p6 -tune hq -rc vbr -cq 20 -b:v 0 `
  -maxrate 20M -bufsize 40M -spatial-aq 1 -aq-strength 12 -temporal-aq 1 `
  -profile:v high -level 4.2 -g 120 -bf 3 -pix_fmt yuv420p `
  -movflags +faststart -c:a copy `
  outputs/<ID>-captioned-1080p60.mp4
```

All style tuning is in the preset (`config/presets/*.json`). Never edit the generator to
change the look.

## Traps found the hard way

**`python -X utf8 -E` is mandatory.** A machine-wide `PYTHONPATH` points at
another Python install's site-packages and is prepended to this interpreter's `sys.path`, breaking
`import faster_whisper`. `sys.path` is frozen at interpreter startup, so
scrubbing `os.environ` in-process does **not** help, and a venv does not either
(venvs honour `PYTHONPATH` too). `-E` is the only invocation-level fix — but it
also disables `PYTHONUTF8`, and this console is cp1252, so any Cyrillic log line
then raises `UnicodeEncodeError`. Hence both flags.

**libass scales `Fontsize` by `usWinAscent + usWinDescent`, not `unitsPerEm`.**
This silently makes text the wrong size. For Montserrat those are 1109+453=1562
against upem 1000, so a nominal 43 px renders at 0.640x — predicted 0.6402,
measured 0.6412. To hit a 30 px cap height the nominal size must be **67**.
`Metrics.px` in the generator encodes this; do not "fix" it back to upem.

**Variable fonts do not work here.** libass registers only a variable font's
*default* instance, so requesting Montserrat at weight 700 fell through to
`Arial-BoldMT`. fontTools-instanced statics were rejected by FreeType too
(rendering fell back while `fontselect` still reported a match — the logs lie).
Use a genuine static TTF; `fonts/Montserrat-Bold.ttf` is the upstream build.

**Diagnose font problems by measuring ink, not by eye.** At small sizes a
fallback grotesque and real Montserrat look similar enough to misdiagnose.
Render onto `color=c=black` via lavfi and compare the ink bounding box against
the `hmtx` prediction.

**Never seek with plain `-ss` when burning subtitles.** It rebases frame PTS to
0, so libass looks up the wrong dialogue lines and the preview appears desynced
when nothing is wrong. Either regenerate the ASS with `--time-offset`, or wrap
the filter: `setpts=PTS+T/TB,ass=...,setpts=PTS-T/TB`.

**`-b:v 0` is required with `-cq`.** Leave a bitrate set and nvenc ignores `-cq`
entirely and the text goes mushy. Sharp glyph edges at 60 fps are the hardest
case for any rate control, hence `-spatial-aq 1 -aq-strength 12`.

**Keep filter paths relative.** Run ffmpeg from the workspace root and use
`ass=filename=temp/captions.ass`. An absolute Windows path breaks the
filtergraph parser twice over (drive colon = option separator, backslash =
escape).

**Keyframe-only scanning misses short overlays.** The first overlay scan used
`-skip_frame nokey` (~5.9 s granularity) and found 4 ranges; a dense 4 fps pass
found **9** — five of them were 5-8 s long and fell between keyframes.

## Design notes

Captions use **one Dialogue event per (word x state)**, each holding a single
word at an absolute `\pos` computed in Python. Layout is therefore time-invariant
and cannot reflow when a word changes colour. ASS karaoke (`\k`) was rejected:
it is monotonic and two-state, so it cannot express a spotlight that returns
previous words to the base colour.

Timing is integer centiseconds, rounded exactly once at ingest, so consecutive
states share byte-identical boundaries. Rounding each interval independently
from floats produces occasional one-frame blank flashes that are maddening to
reproduce.

Widths come from fontTools `hmtx`, not PIL: PIL has no HarfBuzz here
(`raqm: False`) so it returns hinted integer advances that drift up to 0.5 px
per glyph and do not accumulate linearly.
