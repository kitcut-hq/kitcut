---
name: video-h3
description: Direct MiniMax H3, the open-weights video model, on kc-local to make AI-generated shots or a whole episode in a series' own look, keeping the episode's own narration and music. Covers the prompt format H3 actually follows, the rules learned from the first Leo pilot (each with the defect that taught it), how to rebuild an existing KitCut episode shot by shot, the review-and-experiment loop, and the machine traps. Use when asked to make a video with H3, MiniMax, Hailuo or "the AI video model", to re-shoot an episode with generated video instead of drawn code animation, to compare H3 with KitCut, or to write or fix an H3 prompt.
---

# Directing MiniMax H3

H3 is a video model: it **invents** every frame from a prompt and a few pictures. KitCut draws every frame
from code. The two fail in opposite ways. KitCut does exactly what the code says and nothing more. H3 does
roughly what the prompt says and fills every gap with its own guesses. **Directing H3 means leaving no
gaps,** and checking every shot, because no structural test can see a stranger wearing Dad's shorts.

This skill was written on 2026-10-23 from the Leo ep. 12 pilot (the first minute re-shot as 11 shots). The
experiment log is `temp/h3test/EXPERIMENTS.md`. The working shot builder is `leo_pilot.py` beside this
file, and it becomes a `scripts/` tool once the approach is adopted.

## Where it runs and what it costs

kc-local (RTX 3070 8 GB, 32 GB RAM), through **Wan2GP** in `/srv/kitcut/wan2gp`, with its own venv. MiniMax's own
release needs four large GPUs; Wan2GP streams the model through RAM.

| Setting | Value | Why |
|---|---|---|
| model | `minimax_h3_fasth3_omni` (FastH3, 8 steps, pruned 20B, int8) | Fastest. Takes reference pictures **and** first/last frames. |
| `config` | `gguf_q4_k_m,lower_ram` | Q4 text encoder (the Q2 one reads prompts worse). |
| `resolution` | `1344x768` | **Never 480p**: at 480p Leo turned into another boy halfway through a shot. |
| `seed` | fixed (42) | So an experiment changes one thing. |

Time at 768p: **about 1.1–1.3 GPU-minutes per second of film**, including ~1.5 min of model loading per shot
(4 s shot ≈ 4–5 min, 9 s shot ≈ 11 min). A 5-minute episode is about 6 hours of machine time. Electricity
only; no API spend.

Run every job capped, because it shares the machine with the live studio:

```bash
sudo systemd-run --unit=<name> --uid=kitcut --gid=kitcut -p MemoryMax=22G -p MemorySwapMax=2G -p Nice=10 \
  -E HOME=~kitcut -E PYTHONUNBUFFERED=1 -p StandardOutput=truncate:<log> -p StandardError=append:<log> bash <script>
# inside: cd /srv/kitcut/wan2gp && . .venv/bin/activate && python wgp.py --process <settings.json> --output-dir <dir>
```

## The prompt: six sections, each holding only its own kind of content

MiniMax's guide (`docs/VIDEO_PROMPT_WRITING_GUIDE_ref_en.md` in the HF repo MiniMaxAI/MiniMax-H3) defines
full-reference prompts as six sections, in this order:

```
subject_definitions:      one line per subject: "<Subject 1> is <who, every visible feature>, from <Picture 1>."
summary:                  "[reference generation] <one sentence of what the shot is>"
retention_analysis:       one line per subject: "<Subject 1> (appears in [Shot 1]): fully_preserved - <features> are retained."
detailed_description:     STYLE SENTENCE(S) FIRST, then "[Shot 1] ..." and "[Shot 2] At 00:03.500, the shot cuts to ..."
overall_soundscape:       physical sounds only
non_diegetic_music:       N/A when the episode's own score is laid on later
```

- **Style is the opening of `detailed_description`,** not a line in `retention_analysis`. v1 put style,
  "no adults" and Dad's rules into retention, which is only for how faithfully each reference is kept.
- **`detailed_description` is 350–500 words** for a generation task (MiniMax's number). Hard floor here:
  180. v1's were 60–100 words, and the model invented the rest: a yellow taxi interior, a stranger in Dad's
  clothes. For each shot write the framing, every subject's look and place in the frame, the surroundings
  and light, the actions in order with rough timing, the camera move, and what is heard.
- **Camera = type + amplitude + speed**: "the camera pushes in with small amplitude at slow speed". The
  types are Push In/Pull Out, Truck, Pan, Tilt, Pedestal, Arc Shot, Tracking Shot, Static Shot and Zoom.
- **Cuts inside one clip work**: `[Shot 2] At 00:04.000, the shot cuts to ...`, strictly increasing and
  inside the clip's length. The model also cuts by itself when the action needs it (S07 went from the shop
  front to the shelf to a close-up).
- **Visible text goes in "double quotes"**, exactly as it should read. Otherwise the model invents garbled
  signs ("Los colae"). Give walls as "plain blank walls".

## The rules, each with the defect that taught it

1. **Say only what is in the frame.** Naming something that must stay out tends to bring it in. Every
   shot's prompt explained how Dad may appear ("only his hands, or his legs in blue shorts"), so Dad's legs
   appeared in the back seat and walked through a street shot. Write "his feet are bare", not "no shoes,
   no socks".
2. **A character's notes go only into the shots that character is in.**
3. **A stranger gets their own, different clothes, stated.** S09's "other dad" wore Leo's Dad's blue
   shorts and sneakers, because Dad's description was in that prompt.
4. **Every place is described in full in every shot.** The model has no memory between shots. Unstated,
   the car's interior was yellow-brown in one shot and dark brown in another. After the interior was spelled
   out ("light grey seats, grey door panels, grey dashboard, Leo's blue car seat in the middle of the back
   seat"), S10 matched.
5. **Light words change faces.** "Palm-tree shadows sliding across him" made Leo's face brown. Ask for
   "soft even daylight on his face".
6. **References keep identity; KitCut frames keep KitCut.** Leo's picture (a crop from an episode frame)
   and the car's picture held both across shots. A first and last frame taken from the KitCut episode gives
   a clean clip that **looks exactly like KitCut**, which defeats the point. Use first/last frames only to
   bridge two existing shots.
7. **A shot with no character in it gets no character picture** (`image_refs` empty). Otherwise the model
   tends to put that character in. The style sentence alone kept the look in S09.
8. **Label numbering follows picture order, and is checked.** `<Subject N>` is the Nth picture of that
   shot. Renumber in one pass: two sequential string replaces swapped a label twice. The builder's lint
   fails a prompt whose label sits next to another subject's words.
9. **One narrator means no character voices.** Series rule (Leo): every line is the narrator's. The
   soundscape lists only physical sounds and ends "There is no speech and no vocal sound of any kind; a
   narrator is added later." Check every shot's own audio for speech before mixing.
10. **Size the shot to the narration.** Each shot fills the time between line starts, from 4 to 15 s.
    Under 4 s, merge with a neighbour. The assembly trims or holds each shot to its exact slot.

## Re-shooting an existing KitCut episode

1. **The narration and its timings:** `projects/<film>/audio/vo/timeline.json` on the studio, with every
   line's start, end and file.
2. **The voice and music as stems:** copy the film folder without `outputs/ temp/ versions/`, then run the
   release's `scripts/sketch-audio.py --manifest <copy>/sketch.json --stems` with the **full path** (a
   relative path is read against the studio code, not the copy). It takes about 33 s, and the live film is
   never touched. KitCut's sound-effect stem is timed to KitCut's picture, so the model's own sound
   replaces it, set to the loudness of that effects stem.
3. **The shot list:** one shot per beat of narration, with the subjects in frame, the summary, the full
   description and the sounds. `leo_pilot.py check` lints it before any GPU time is spent.
4. **Generate one process per shot,** and skip shots whose file already exists so a run can resume.
5. **Assemble:** trim or hold each shot to its slot, concatenate, then mix the voice stem + music stem +
   model sound and normalise to -14 LUFS like the episode.

## Review and experiment, every time

- Look at **every shot at 1 fps as it lands** (`fps=1,tile=5x2` sheet), not just the finished minute.
  Write each defect down with its cause in the log.
- So far, **every defect traced back to the prompt, not to the model failing.** Fix the prompt, version
  it (v1 to v5 on the pilot), and redo the shot. Keep the old one as the baseline.
- Run one-change experiments on a single shot with everything else fixed: seed (**how many tries give a
  usable shot?** That decides whether an episode is one overnight run or needs a person choosing takes),
  length, model, words.
- Before a film goes to its owner, a fresh agent reviews it with the `video-review` skill.

## Machine traps

- **Wan2GP turns every blank-line paragraph of a prompt into a separate video** (its default
  `multi_prompts_gen_type` is `PG`) and then refuses the shot. That cost one round: v5's six sections are
  separated by blank lines. Every settings file carries `"multi_prompts_gen_type": "FG"` (the whole text is
  one prompt).
- **A refused shot exits cleanly.** The runner checks that the output file exists and prints `FAILED`
  otherwise. Never trust `rc=$?` printed after a `$(date)`.
- **A shell script written from Windows gets CRLF line endings,** and bash then exits in milliseconds with
  status 2. Strip `\r` and `bash -n` the script before starting a unit.
- **systemd's `file:` output overwrites from the start without clearing the file,** so an old run's lines
  sit behind the new ones. Use `truncate:` for stdout and `append:` for stderr.
- **The FL2VA PDD model is OOM-killed under the 22 GB cap** unless it runs with
  `--perc-reserved-mem-max 0.35`. It then runs at 86 s/step and is not better than FastH3.
- **Never edit a bash script that a running unit is executing.** Stop the unit and start a new one.
- **Prompts with apostrophes break `ssh '...'`.** Write the files locally, `scp` them, and run them.
- **Watching a log:** `tail -F | tr | grep` over ssh delivered nothing. Poll instead, by counting matching
  lines every 30 s.
- **The model's own audio is far louder than an effects stem.** It needed about -18 dB to sit where KitCut's
  effects did.

## Open questions (update as they are answered)

- Yield: of 3 seeds of one shot, how many are usable?
- Do 9 s shots hold up as well as 5 s ones?
- Does the full 350–500-word description beat ~250 words?
- Does a shot's own audio ever contain speech despite the soundscape line?
