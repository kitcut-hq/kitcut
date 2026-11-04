---
name: video-still-film
description: Make an "entire history of X" explainer from still pictures and a narrator, the way CEOzoned's long-form history videos are built, as a vertical 120-second Short or any length. One cartoon picture per narrated line (about 3.6 s each), a calm documentary voice, a quiet music bed, no burned captions, a cold open on a contrast, "This is the story of", the history in order, three lessons, "That was the entire history of". Pictures come from Gemini or Grok on the web (9:16); the voice from Gemini TTS on kc-local; scripts/still-film.py voices, times and renders. Use when asked to recreate that style of video, to make a company/product/person history Short from AI pictures, or to render a film from a list of lines and pictures.
---

# Still-picture history films

The format, measured off CEOzoned's "The ENTIRE History of Instagram" (1063 s, 267 shots): a new
picture every 3.57 s median (p10 2.3 s, p90 6.0 s), one hand-drawn cartoon look throughout
(round white stick-figure heads, warm palette, words lettered inside the pictures), narration
at 156 words a minute with 0.48 s pauses, a bed 9 dB under the voice, no burned captions,
hard cuts. Numbers and frames: `projects/anthropic-history-short/still-film.json`, `reference._measured`.

## Procedure

1. **Script as lines**, one picture each, about 2.6 words a second. Cold open on a contrast, two
   questions, "This is the story of ...", chronology, three lessons, "That was the entire history
   of ...". Check every number against its original page.
2. **Manifest** `projects/<id>/still-film.json`: `voice`, `style` (prefix for every picture
   prompt), `cast` (a line per recurring character), `scenes[{id, line, image}]`.
   `python scripts/still-film.py --manifest <m> --prompts` prints each full picture prompt.
3. **Voice on kc-local** with KitCut's own model (`STUDIO_TTS_MODEL`, now `gemini-3.1-flash-tts-preview`),
   never older models and never the laptop (its Gemini API project has the API off). Make a worktree
   under `/srv/kitcut/worktrees/`, link `.env`, `.venv`, `models`, copy the script and manifest,
   run `--voice`, copy `audio/vo/` back. A line Gemini refuses is rephrased, not retried.
   `voice.tempo` speeds the take (pitch kept) without re-recording.
4. **Pictures**: attach the style sheet and one finished scene as references, then one prompt per
   scene. Gemini web caps image makers (resets at a stated time); Grok Imagine (Edge) does not
   block downloads. Save each as `images/<id>.jpg`. `--plan` shows what is still missing.
5. **Render on kc-local**, never the laptop (standing rule): tar the project into the worktree and run
   `sudo systemd-run --uid=kitcut --wait --pipe --collect -p MemoryMax=6G ... still-film.py --render`. `--render`. Every still gets a linear push or pan (a Short may not stand still:
   `python scripts/short-stillness.py <mp4> --check` must pass; an eased move failed it at 7%).

6. **Captions** (the owner wants them on Shorts, though the reference has none):
   `python scripts/run-captions.py --input <render> --project <id> --id <id> --style config/presets/cartoon-short-card.json --lang en --no-overlays --stop-after transcribe`,
   diff the words against the script and fix names in the words.json (Whisper gave "Amadei", "claw" for Claude,
   "III", split "GPT -2"), then run again without `--stop-after`. The card preset sits as low as rule 25 allows.
7. **Camera and music:** keep the move subtle (`motion: {"zoom": 0.04, "kinds": ["in", "out"]}`); the owner found
   0.12 zoom with alternating pans annoying. A one-chord string loop was "bad"; the score in
   `projects/anthropic-history-short/score.json` (piano + harp arpeggio, tense low open, major lift for the lessons) replaced it.

8. **Openings:** the owner cut the 24 s cold open as too slow. Mark scenes `"cut": true` (kept, not played) and set
   `music.offset_s` so the score stays on the story; shift the caption words rather than re-transcribing.

9. **Horizontal (16:9) films** (`projects/mongodb-history`, 6:57, 92 stills): `frame: [1920, 1080]`, Grok's aspect menu
   set to 16:9 (1792x1008 out), captions `config/presets/cartoon-wide-card.json` (one line, 95% down). A cast line-up
   sheet made first in the same style (`temp/refs/mdb-cast.jpeg`) and attached as the second reference keeps the
   founders recognisable; scenes without named people attach only the style sheet.
10. **Check every picture and redo the weak ones** (owner, 2026-11-03): look at each batch as a contact sheet. Redo on
    gibberish lettering, stray labels, a named person drawn wrong (Dev kept getting CJ's glasses: describe him
    explicitly and say "NO glasses"), people who are not in that moment of the story, and the style sheet's places
    bleeding in (a Stanford-like campus): the prompt now says "never copy any place from the reference".
    **Few people**: "too often there are too many people" -- every prompt carries "at most three or four people,
    never a crowd"; write "three developers", not "a crowd of developers".
11. **Thumbnail**: `make-thumbnail.py --html` with a page of our own (text on a dark panel at left, one still at
    right uncovered); make several, compare at 168 px, pick the one whose words read and whose picture is whole.

## Traps (each cost time)

- Chrome blocks a site's repeated downloads and freezes the tab. Read the picture inside the page
  and POST it to a local server; for Grok select the image by the current post id, because the
  page also holds thumbnails of earlier ones and the first 1008x1792 image is NOT the new one.
- PowerShell's `Set-Content -Encoding utf8` writes a BOM, which `json.load` rejects: write files
  with Python.
- The browser tool kills a call at 45 s. Split a Grok scene into a submit-and-wait call (30 s cap) and a
  separate save call that picks the image up by post id; keep the prompt prefix and both functions in the page's
  localStorage so each call carries only the scene text.
- Gemini web ignores a dropped image; paste it as a ClipboardEvent file into the editor.
