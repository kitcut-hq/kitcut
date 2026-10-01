# Process brief: where does a film session's time go, and what is repeated work?

Context. kitcut.ai's studio makes animated films. Each film is one Claude (Opus) session (long
films: several sessions -- a director/plan pass, one per scene, an editor pass) with these tools:
Read/Write/Edit on its own folder, and studio tools: `voice` (records vo.json lines with TTS, then
times words; ~52 s a call), `stills` (renders still frames to a contact sheet PNG it then Reads),
`motion` (a motion-check sheet, ~50 s), `check` (lint/validate film.js, ~1 s), `sound` (score +
sfx mix, ~16 s), `paint` (image-model pictures, ~140 s), `page`, `picture`, `font`.
Measured over 90 sessions: ~24 h of Claude generation vs ~9 h of tool time.

Each file in `<pull>/timelines/` (`studio/harvest.py --timelines <pull>`) is one film's condensed timeline:
`<seconds since start> PROMPT|USER|SAY|TOOL|RESULT ...`. SAY lines are Claude's own words between
steps (often explaining what it saw in the stills and what it will fix). Edit lines show
`-<old chars> +<new chars>` and the start of the new code. RESULT lines show tool output
(studio tools only, plus errors).

## Your job

Read EVERY timeline in your list. For each film, find:

1. **Phases** -- seconds spent: planning before the first film.js/scene write; first build; then
   review/fix rounds (stills/motion -> edits). Note how many rounds.
2. **Every fix round**: what the check/stills/motion revealed and what was changed. Classify each
   fix into a cause:
   `text-fit` (text too long/overflow/wrapping/size), `overlap` (elements collide or cover each
   other/faces/text), `offscreen` (cropped, outside frame, safe area), `timing` (a cue off the voice,
   too fast/slow, held too long), `readability` (contrast, colour, legibility), `drawing` (something
   looks wrong/ugly/unrecognisable), `layout` (spacing, alignment, composition), `motion` (jitter,
   jumps, popping, transitions), `js-error` (exception, check failure), `voice` (pronunciation,
   pacing, re-record), `audio` (score/sfx/mix), `brand` (logo, colours, wrong name), `other`.
3. **Voice re-recordings**: how many `voice` calls, and why each re-record happened.
4. **Repeated work** that a reusable script/component/default would remove: e.g. reading the same
   reference files every film, re-deriving layout maths, re-writing the same helper, hitting the
   same validator error, writing score.json/sfx.json from scratch, rebuilding the same kind of
   end card or title. Quote the evidence (timestamp + short quote).

## Output

Write ONE JSON file `<pull>/process/<NAME>.out.json`:

```json
{"films": [{"film": "...", "length": "...", "total_s": 0, "plan_s": 0, "build_s": 0,
            "fix_rounds": 0, "fix_s": 0, "voice_calls": 0,
            "fixes": [{"t": 0, "cause": "text-fit", "what": "<= 20 words"}],
            "voice_reasons": ["..."],
            "repeated": ["<= 25 words each, with timestamp evidence"]}],
 "patterns": ["<= 30 bullets: the recurring causes of time across your films, each with a count
              and the reusable script/component/default that would remove it>"]}
```

Do not modify any other file. Finish by replying with a 6-line summary.
