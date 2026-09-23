# bbg-nvidia-hf -- edit journal
AI notes for future sessions. Scripts append the `- HH:MM` event lines;
after each editing session, append a short prose note: what was asked,
which knob changed, why, and anything the next session should not rediscover.

## 2026-09-04
- 09:53 project created
- 10:36 render scripts/cut-clips.py -> projects/bbg-nvidia-hf/outputs/shorts-vertical/bbg-nvidia-hf-v-01-cognition-47b.mp4 (--manifest projects/bbg-nvidia-hf/clips-vertical.json)
- 10:37 render scripts/cut-clips.py -> projects/bbg-nvidia-hf/outputs/shorts-vertical/bbg-nvidia-hf-v-02-uber-micro-teams.mp4 (--manifest projects/bbg-nvidia-hf/clips-vertical.json)
- 10:45 render scripts/cut-clips.py -> projects/bbg-nvidia-hf/outputs/shorts-vertical/bbg-nvidia-hf-v-01-cognition-47b.mp4 (--manifest projects/bbg-nvidia-hf/clips-vertical.json --force)
- 10:46 render scripts/cut-clips.py -> projects/bbg-nvidia-hf/outputs/shorts-vertical/bbg-nvidia-hf-v-02-uber-micro-teams.mp4 (--manifest projects/bbg-nvidia-hf/clips-vertical.json --force)
- 10:47 render scripts/cut-clips.py -> projects/bbg-nvidia-hf/outputs/shorts-vertical/bbg-nvidia-hf-v-01-cognition-47b.mp4 (--manifest projects/bbg-nvidia-hf/clips-vertical.json --force)
- 10:47 render scripts/cut-clips.py -> projects/bbg-nvidia-hf/outputs/shorts-vertical/bbg-nvidia-hf-v-02-uber-micro-teams.mp4 (--manifest projects/bbg-nvidia-hf/clips-vertical.json --force)

### Session note

The ask was not really "cut two shorts" -- it was "does this product work on
macOS", with the shorts as the evidence. It does, end to end, on Apple silicon
with no NVIDIA card. What follows is what the machine changed, because none of
it is visible from the manifests.

**The encoder substitution works and is the headline result.** Both the preset
and the manifest name `h264_nvenc` with `preset: p6`; `_encode.py` said so out
loud, substituted `h264_videotoolbox`, and translated the NVENC speed scale
into the videotoolbox family. Nothing needed editing for that.

**Three things blocked a fresh machine, all now fixed.** `pyproject.toml` had no
`requires-python`, so every uv call warned and uv adopted the venv as its own,
writing a dependency-free `uv.lock` that a later `uv sync` would have enforced
by deleting all 146 installed packages -- `[project]` + `managed = false` stops
that. `transcribe-words.py` sets `HF_HUB_OFFLINE=1` and passes
`local_files_only=True`, so on a machine with an empty model cache it died with
a huggingface_hub traceback; it now names the model and prints the one
`hf download` line that fixes it. And yt-dlp needs a JavaScript runtime for
video streams now -- KI-027, use `--js-runtimes bun`.

**The caption margin was the only real editing defect, and the gate caught it.**
The preset's `bottom_margin_px: 816` was measured on a tighter framing of THIS
episode (crop_zoom ~1.556-1.714, to clear Bloomberg's own lower third). These
clips are reframed without that zoom, so faces sit higher and the card landed on
the chin: 10 FAIL, worst 18 % cover. Fixed at 950.

The trap worth remembering: `check-caption-space.py` run standalone measures the
PLAN, and the copy `cut-clips.py` runs after a render measures the RENDER, and
they disagree. Standalone said 900 cleared both clips at +58 / +48 px; the
render put clip 02 at -55 px with 3 warns. **Believe the render.** 950 gives
+134 and +32 px there, 0 fail 0 warn.

**Two things are known-bad and left alone.** `cv2` and `av` vendor different
FFmpeg majors, so every script holding both prints an objc duplicate-class
warning on macOS -- KI-028, cosmetic so far, and not fixable in our code because
`scenedetect` loads `av` at import. And the transcript's proper nouns are poor
(distil-large-v3, int8, CPU): "Nvidia" often decodes as "Invidia" or "in
videos". Clip anchors avoid those words on purpose; if these were ever going
out, re-transcribe on a CUDA box before trusting the burned-in captions.

Selection is in `shortlist.json` -- 5 candidates, 2 picked, 1 bench, 2 rejected
with reasons. The rejects are the useful part: the strongest single idea in the
episode (a retention pool sized to keep the acquired staff) lost on length at
13 s, and the biggest number lost because it is a 2050 projection the guest
herself undercuts.
