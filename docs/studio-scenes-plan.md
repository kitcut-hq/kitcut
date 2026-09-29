# Studio: scenes as the unit of work -- implementation plan

Approved 2026-09-29. **Status:** steps 1 and 2 built on branch `studio-scenes` (engine scenes,
the three passes, checkpoints, carry-on after a restart, `test_scenes.py`), **on since 2026-09-29
09:48 PDT for films over 5 minutes** (`STUDIO_SCENES_OVER_S=300`, the VM's .env and machine.env),
turned on before step 3 at the user's call; the per-scene render cache (in step 1) and step 3's
real films side by side are still to do -- watch the first real scenes films closely. Why: docs/todo.md #7 and docs/known-issues.md KI-034. A film is today one
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

## 2 in detail: the three passes, file by file

### Decisions (defaults; say if any should change)

- **The director writes scene 1 as the pilot.** It settles the look on a real scene, with stills,
  before anyone else draws -- every later scene copies a proven style, not a description of one.
- **Scenes one after another in v1**, in one Claude slot like a film today. Two at once is a later,
  measured option (it only saves wall time, and must never take a slot another person's film is
  waiting for).
- **A crash no longer loses a scenes film.** The live server carries it on from the next scene
  (adopt), up to 3 times; today a mid-Claude film can only be marked interrupted.
- **Short films keep today's path** until step 3's measurements say otherwise.

### What Claude may touch, per conversation

| Pass | May write | Sees in its first message |
|---|---|---|
| director | vo.json, film.js (the shared look), scenes.json (the plan), scenes/01-*.js (the pilot) | the brief, attachments, the series note -- as today |
| scene k | scenes/k-*.js only (the guard is told per conversation) | the direction (film.js's first line), film.js (the look, kept under ~300 lines), scene k's plan entry and its lines with word times, the neighbours' plan entries and summaries, a sheet of scene k-1's last frames |
| editor | any scenes/*.js, score.json, sfx.json | scenes.json with every scene's summary, the timeline's spans, contact sheets the studio rendered (boundaries +-0.5 s and each scene's middle) |

### The plan file, scenes.json (written by the director, checked by validate.py)

`{"scenes": [{"id": "01-orbit", "title": "...", "lines": [0, 4], "shows": "...", "notes": "..."}]}` --
ids `NN-slug`, in order, lines contiguous and covering every narration line, each scene 12-75 s
long once the narration is timed, at most one per 12 s of film. Progress is the studio's, not
Claude's: studio.json `"scenes": {"01-orbit": {"state": "todo|done", "session", "summary",
"cost_usd", "seconds", "tries"}}` (never readable by Claude, so it cannot mark itself done).

### Files and functions

- **studio/scenes.py (new):** load and validate the plan; progress in studio.json; each pass's
  first message (from studio/prompts/director.md, scene.md, editor.md); per-pass limits; the
  studio-rendered sheets (neighbour frames, the editor's contact sheets, through Tools).
- **studio/agent.py:** `make_film` hands a scenes film's Claude part to `make_scenes()`: director
  (unless its outputs are already done), then each scene not done, then the editor; each pass is
  one `talk_to_claude()` with its own first message, a fresh session (no resume) and its own
  limits inside the film's. `run_claude` keeps a pass's session id on the pass, not over the
  film's `claude_session`; the stall watchdog resumes the pass's own session. One Meter across
  passes (the record's cost and calls add up, as resume already does); the record gains
  `passes: [{pass, session, cost_usd, seconds, turns, stalls}]`.
- **studio/prompt_scenes.md (new system prompt):** the same reference as today (engine, props,
  notation -- identical across every pass of every scenes film, so it stays cached), with a
  "how a scenes film is made" section in place of the single-file "How to work". The single-file
  prompt is not touched: today's films are not changed by this work.
- **studio/guard.py:** `guard(tool, input, film, allow=None)` -- with `allow`, Write and Edit only
  to those files; the pass sets it.
- **studio/film.py:** `scenes/NN-slug.js` and `scenes.json` writable in scenes films;
  `MADE` for them includes every planned scene's file; the manifest gets `"scenes": "scenes"`;
  `mode` in the record.
- **studio/validate.py:** the plan's checks above; scene files under a size cap; at the editor's
  end, every planned scene present (the engine draws a missing one blank while scenes are being
  written -- a requirement on step 1: an uncovered stretch renders empty, never fails the bundle).
- **studio/tools.py:** `check` covers scenes/*.js; `stills` and `motion` take the pass's time
  range (a scene looks at its own stretch, not the whole film); a studio-side `sheets(times)`.
- **studio/server.py:** adopt() carries a scenes film in `claude` on (`start(f, scenes=True)`,
  `tries` capped); stage texts "Claude is planning the film", "Claude is writing scene 7 of 16",
  "Claude is checking the whole film" reach the page as today's stage text does.
- **studio/resume.py:** a scenes film resumes as `make_scenes()` from where it stands -- no
  session to replay. **studio/claude_log.py:** one block per pass (its session, replies, stalls).

### Tests (studio/test_scenes.py, fake Claude that answers per pass)

- 8-, 16- and 30-minute films run all three passes: sessions = 1 + scenes + 1; every first
  message and every conversation stays under a bound that does not grow with the film.
- A scene conversation that tries to write another scene's file is refused.
- A stall in scene 3 is picked up in scene 3's own session; the others do not rerun.
- The server stopped during scene 5: the next leader continues from scene 5 (scenes 1-4 not
  called again), and gives up after 3 tries with the film failed and refunded.
- A plan with a gap, an overlap or a 2-minute scene is refused with a reason Claude can act on.
- Sound and render stubbed for the ladder (their real paths are covered elsewhere).

### Size

About 2-3 days: scenes.py and the prompts (1), agent/guard/film/validate/tools (1), server,
resume, claude_log and the tests (0.5-1). Ships behind STUDIO_SCENES_OVER_S, off.

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
