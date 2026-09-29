# Studio: scenes as the unit of work -- implementation plan

Approved 2026-09-29. Why: docs/todo.md #7 and docs/known-issues.md KI-034. A film is today one
`film.js` written by one Claude conversation that grows with it (8-minute film: 73k -> 371k tokens,
the picture's first draft one 57k-token reply). Opus 5.5 allows 128K per reply and 1M per
conversation: the picture cannot be written in one reply past ~18 minutes of film, the conversation
outgrows the window past ~25, and cost grows faster than length. This plan makes every reply and
every conversation bounded whatever the film's length, and a failure cost one scene.

Built in a worktree (branch `studio-scenes`), behind a switch, proved before it is adopted.

## 0. Loose end from Phase 1

- **Reboot test** (first quiet moment: `ops.sh status` shows no films): `sudo reboot`; expect
  `kitcut-studio-boot` active (exited), the current instance up and leading, the studio announced,
  a 10 s login film done with a voice. Then note it in studio/deploy/README.md.

## 1. Engine: scenes (sketch/engine.js, scripts/sketch-render.py)

- `SK.scene({ id, lines: [a, b], lead = 0.3, draw(t, local, vis), camera? })` registers a scene
  that covers narration lines a..b: it starts `lead` s before line a is spoken and runs until the
  next scene starts (the last one to the film's end). `local` is seconds since the scene's start;
  word cues work as today (`SK.w(line, word)`). A scene may carry its own camera; otherwise the
  film's camera holds. Scenes are sorted by start; a gap or an overlap is an error at load.
- A film with scenes needs no `draw` of its own: `SK.film({ duration, camera, ... })` without
  `draw` draws the scene covering t (plus the next one during a declared crossfade `out: 0.4`).
  A film without scenes is unchanged -- every film made so far still renders.
- Bundle order: engine, props, cast/*.js, `film.js` (the shared look: palette, fonts, helpers,
  the camera -- helpers shared through `SK.look = {...}`), then `scenes/*.js` in name order, each
  in its own function scope like a cast member (`//# sourceURL=scenes/<name>`, so an error names
  its scene). Manifest key `"scenes": "scenes"`.
- Still a pure function of t: any frame renders on its own, so a scene renders on its own.
- **Per-scene render cache** (sketch-render.py): with scenes, chunks are cut at scene boundaries;
  a chunk's key is the hash of engine + props + cast + film.js + that scene's file + its slice of
  the timeline + fps/size; a chunk whose key is unchanged is reused from temp/render-cache/, the
  rest drawn in parallel as today, then joined by stream copy. A one-scene fix re-renders one scene.
- Test (`scripts/check-sketch.py` + a new example `config/sketch/example-scenes/`): three scenes
  that each fill the frame with their own colour; stills at each boundary +-1 frame show the right
  scene; a gap/overlap is refused; a single-file film renders byte-identical to before.

## 2. Studio: three passes instead of one conversation (studio/agent.py, guard.py, validate.py, tools.py)

The switch: films longer than `STUDIO_SCENES_OVER_S` (unset = off; 300 once proved) are made in
scenes; `studio.json` records `"mode": "scenes"`, the manifest gets `"scenes": "scenes"`.

One system prompt for all three passes (the engine/props/notation reference, 104 KB of today's
133 KB): identical across passes and films, so it stays in the prompt cache; each pass's own
instructions come in its first message (studio/prompts/director.md, scene.md, editor.md).

1. **Director** -- one conversation, bounded by the brief not the film's length: reads the
   brief and attachments, writes and records the narration (vo.json; the voice tool as today),
   writes `film.js` (the look and helpers, no scenes) and `scenes.json`: the plan, one entry per
   scene `{id, title, lines: [a, b], shows, style_notes}` -- 20-60 s each, contiguous, covering
   every line (validate.gate refuses anything else). It may render stills of a style test scene.
2. **Scenes** -- one fresh conversation per scene (no resume, no history): its first message
   carries the direction (film.js's first line), the shared look's helper names, its own lines
   with their words' times, what the neighbours show (their `shows` + summaries once written) and
   the neighbours' boundary stills. It may write only `scenes/<id>.js` (the guard is told per
   session), checks it (`check`), renders stills inside its own time range, fixes what it sees,
   and ends with a two-sentence summary saved into scenes.json. Each is bounded (~40-80k tokens,
   replies of a few thousand), so the per-reply cap and the window stop mattering at any length.
   Sequential first; two at once as a measured option later (an extra Claude slot only when one is
   free, never ahead of another person's film).
3. **Editor** -- one conversation over the whole film at contact-sheet level: motion sheets and
   stills at every boundary, scenes.json's summaries (not the scenes' code); fixes continuity
   (it may Edit any scene), writes score.json and sfx.json for the whole film, runs the sound check.

- **Checkpoints.** scenes.json records each scene's state (`todo | done`, session id, cost). A
  crash, restart, stall or cancel costs the scene in progress; `resume.py` and the leader's
  adopt() continue a scenes-mode film from the first scene not done -- nothing is replayed.
- **The watchdog** (Pulse, talk_to_claude) wraps every conversation; a stalled scene is picked
  up again in its own short session.
- **Accounting.** One Meter across the passes (cost and calls merged in the record, as resume
  already does); the film's working-time limit spans all passes; per-pass limits (director
  ~25 min, a scene ~6 + 1.5 per minute of scene, editor ~20 min) keep one pass from eating the
  rest. `ops.sh claude-log` lists each session (director, scene N, editor) from scenes.json.
- **Page.** Stages read "Claude is writing scene 7 of 16", so a long film shows progress.

## 3. Prove it before adopting it (house rule: measure, don't assume)

- **Stub ladder** (test_server.py / a new test_scenes.py, fake Claude): 8-, 16- and 30-minute
  films through all three passes; asserts every conversation's first message and history stay
  under a bound independent of length, a scene stalled or killed is redone alone, a restart mid-
  film continues from the next scene, scenes.json/guard refuse a scene writing another's file.
  Render stubbed at 1 fps for the ladder (the real render is covered by step 1's test).
- **Real films** on the VM's Claude login (no API spend), same briefs made both ways: 2, 8 and 16
  minutes. Compared on the picture (contact sheets side by side, a frame every 15 s), the voice,
  cost (the record), wall time, stalls. Adopt the scenes path for the lengths where it wins or
  ties on quality; below that the single-file path stays. The 30-minute case is run once real
  films at 16 hold up.

## 4. Roll out

- Ship with the switch off (blue-green: nothing stops), then turn it on at the measured threshold
  (`STUDIO_SCENES_OVER_S` in the VM's .env; `serve.sh restart` starts a fresh instance, nothing
  stops). kitcut.ai's Pro films (up to 8 minutes) are the first real users.
- Docs: docs/reference.md (SK.scene, the manifest key, the render cache), studio/README.md (the
  passes), studio/deploy/README.md, the studio-vm and video-sketch skills, KI-034 closed, todo #7
  closed.

## Order and size

| Step | What | Rough size |
|---|---|---|
| 0 | reboot test | minutes, at a quiet moment |
| 1 | engine scenes + bundle + render cache + tests | about a day |
| 2 | three passes, checkpoints, resume/adopt/log, page stages | 2-3 days |
| 3 | stub ladder; real 2/8/16-minute films both ways | a day of work, plus render/wait time |
| 4 | ship behind the switch, turn on, docs | hours |

Each step ships on its own behind the switch; nothing reaches kitcut.ai's films until step 4.
