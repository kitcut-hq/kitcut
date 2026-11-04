# Task: "The Entire History of Bending Spoons" — a still-picture film, made on kc-local

You are a Claude Code session on **kc-local** (user `kitcut`). Make this film end to end, up to a
finished, checked render and thumbnail. Do not upload it (see step 10). The owner has approved the
work; carry it through without asking about each step, and report at the end.

## Where everything is

- Worktree: `/srv/kitcut/worktrees/bending-spoons` (branch `bs-film`, from GitHub branch
  `still-film-bending-spoons`). `.env`, `.venv` and `models` are linked in. Run Python as
  `.venv/bin/python scripts/<x>.py`.
- Project: `projects/bending-spoons-history/` (this file is in it).
- **Facts: `projects/bending-spoons-history/research/facts.md`.** Every number and date you say
  comes from it, with its label (MEASURED / REPORTED / CLAIM / ESTIMATE). Say a CLAIM as a claim
  ("the company says..."). Leave out anything it lists under "Could not confirm", and nothing in
  "Commonly misreported" may be repeated. If you need a fact it does not have, check it on its
  original page before using it, and add it to the fact sheet with a source line.
- Things the fact sheet settles that are often told wrong: Filmic was bought in **2022** (its 22
  staff cut in Nov 2023); the October 2026 bond grew from $1.5B to **about $1.8B**; Berkshire's
  stake is "**about 4%**" (of ordinary shares); the IPO raised **$1.68B in all**, of which the
  company itself got about $1.0B. Spot-checked against the source pages: IPO at $29 on Nasdaq as
  BSP, first close $40.50, Berkshire's 10 million shares at $33 ($330M) on 14 Oct 2026.
- **Miro is left out of the film completely**: not in the voice, not in any picture, not in the
  description or chapters. It was founded by Russians and started in Perm, and the owner's rule
  is that nothing tied to russia goes into what we make, not even as a neutral fact. The same goes
  for any other company, person or source the research turns out to tie to russia: drop it, and
  say in the report what was dropped. Count the acquisitions and the 2026 deals without it.
- **How the founders look is not in the fact sheet** (the research could not view photos). Before
  the cast sheet, open their public photos in the browser (bendingspoons.com's team/about pages,
  press photos of Luca Ferrari and his co-founders) and write one line per founder: hair, beard,
  glasses, usual clothes. If a founder has no findable photo, draw him plainly and say so.
- Read first: `.claude/skills/video-still-film/SKILL.md` (the format and procedure),
  `tools/grok-imagine/README.md` (how pictures are made), and the finished example
  `/srv/kitcut/worktrees/still-film/projects/mongodb-history/` (`still-film.json`, `score.json`,
  `journal.md`, `description.txt`): **copy its manifest shape, voice, motion, gaps and music
  settings.** That film is 6:57, 92 stills, and the owner liked its pictures after the fixes.
- Reference pictures: `projects/bending-spoons-history/temp/refs/style-ref.jpg` (the art style,
  attach to every picture) and `mdb-cast.jpeg` (the MongoDB cast sheet, as an example of what a
  cast line-up looks like; do not use it as this film's cast).

## The film

- **Length: about 7.5 minutes**: about 1,200 spoken words at ~165 words a minute, about 100-110
  lines, one picture per line (~3.5-4.5 s each). 16:9, 1920x1080, 30 fps.
- Title: **"The Entire History of Bending Spoons in 8 Minutes"** (if the render comes out under
  7:30, say "in 7 Minutes" instead).
- Structure (the CEOzoned format in the skill):
  1. **A fast cold open on a contrast, under 15 seconds.** The owner cut a slow 24-second open on
     the Anthropic film. For example: you have probably used its apps (Evernote, WeTransfer, Vimeo,
     AOL, Eventbrite...) but have never heard its name; a company that buys apps everyone else gave
     up on, and Warren Buffett's company just bought more of it. Then one or two questions, then
     "This is the story of Bending Spoons."
  2. The history in order: the founders and their first startup, the failure, the restart, the
     move to Milan, the app years, Immuni, the funding, each big acquisition and what happened
     after (the layoffs and price rises are part of the story: say them plainly, with numbers),
     the IPO, Berkshire Hathaway, Airtable, the debt, where it stands today (as of the fact sheet's
     latest date).
  3. **Critical thinking out loud**: the strongest case for the playbook (products kept alive,
     profits) and against it (people cut, users charged more, debt), side by side, without taking
     a side the facts do not support.
  4. Three lessons.
  5. "That was the entire history of Bending Spoons." End there.
- Script rules: short spoken sentences; numbers as a narrator says them ("one point three eight
  billion dollars"); names spelled the way they are said. Write `projects/bending-spoons-history/
  script.md` first (the lines, each with its fact-sheet source) and **check every spoken number
  against the fact sheet before voicing**.

## Steps

1. **Manifest.** Write `projects/bending-spoons-history/still-film.json` in the MongoDB shape:
   frame [1920,1080], fps 30, voice Gemini `Charon`, model `gemini-3.1-flash-tts-preview`,
   tempo 1.0, the same `style` text, motion `{"zoom": 0.04, "kinds": ["in","out"]}`, music
   `score.json` at -10 dB under the voice, a `cast` block for the founders, and `scenes` (`id`
   s001..., `line`, `image` = the picture prompt). `--plan` prices the timing for free; use it
   until the length is right.
2. **Picture prompts.** One per line, concrete and simple: one clear focal point, **at most three
   or four people, never a crowd** ("three engineers", never "a crowd of engineers"). Words in a
   picture only when they help (an app name, a price, a year), short, in capitals, spelled exactly.
   Logos of real products are drawn as simple hand-lettered signs, not copied logos. Name the
   cast members who are in that moment of the story; leave everyone else as plain stick figures.
3. **Browser.** Grok is signed in on kc-local's Edge, profile `VideoMakers_io` (screen :101). In
   Claude it is the browser named **"Browser 2", platform Linux** in `list_connected_browsers`;
   select it (start Claude with `--chrome`, or run `/chrome`, if no browser tools are listed).
   Open `https://grok.com/imagine` in a tab and keep that tab the active one the whole time.
   Dismiss any cookie banner with "Reject All". Never type the owner's password anywhere; if Grok
   is signed out, stop and ask the owner to sign in through `xb view VideoMakers_io`.
4. **Receiver.** In a second shell, leave this running:
   `python3 -I tools/grok-imagine/receiver.py --out projects/bending-spoons-history/images --refs projects/bending-spoons-history/temp/refs`
   Install the runner in the Grok tab exactly as `tools/grok-imagine/README.md` says, then
   `SF.config({prefix: <the manifest's style text>, castPrompt: 'Named characters look exactly like the matching person in the second reference (the line-up sheet), but never draw their name labels. ', aspect: '16:9', width: 1792})`
   and `await SF.loadRef('style','style-ref.jpg')`.
   **Work only through the DOM and `SF.status()`: no screenshots of Grok, no clicks by coordinate.**
5. **Cast sheet first.** One job, no cast ref: a line-up of the founders side by side on a plain
   background, each drawn from the fact sheet's description of how they look, in the style, name
   labels under each. Save it as `bs-cast`, look at it, redo until each founder is distinct, then
   move it to `temp/refs/bs-cast.jpg` and `await SF.loadRef('cast','bs-cast.jpg')`. Scenes with a
   named founder get `cast: true`; all others `cast: false`.
6. **All pictures.** `SF.add([...])` the scenes in batches of about 15, `SF.start()`, poll
   `SF.status()` every minute or so. After each batch, **make a contact sheet and look at every
   picture** (owner's rule: "check images always and redo if needed"). Redo any with garbled or
   misspelled words, stray labels, more than four people, a founder drawn wrong, a person who was
   not there at that moment, or a place copied from the style reference. Re-adding a job with the
   same name replaces the picture (the old one is kept as `<id>_old.jpg`). If Grok starts
   failing or returning nothing, it is rate-limited: wait about 40 minutes, then carry on.
   `still-film.py --plan` lists what is still missing.
7. **Voice.** `.venv/bin/python scripts/still-film.py --manifest projects/bending-spoons-history/still-film.json --voice`.
   A line Gemini refuses is rephrased, not retried as it is. Listen to nothing; check the timing
   with `--plan`.
8. **Music.** Write `score.json` for this film's length from the MongoDB one: a tense open, a lift
   at the IPO and Buffett, a darker turn under the layoffs and criticism, a major lift for the
   lessons, quiet under the last line.
9. **Render on kc-local** (it is the production studio, so look at `ops.sh status` / the GPU
   first and do not start while customers' films are rendering heavily):
   `sudo systemd-run --uid=kitcut --wait --pipe --collect -p MemoryMax=6G -p WorkingDirectory=/srv/kitcut/worktrees/bending-spoons .venv/bin/python scripts/still-film.py --manifest projects/bending-spoons-history/still-film.json --render`
   Then captions as in the MongoDB journal: `run-captions.py` with `--style
   config/presets/cartoon-wide-card.json --lang en --no-overlays`, transcribed with `small.en`;
   **replace every caption word with the script's words, numbers as figures**, then burn. Watch
   the MongoDB journal's trap about `--force download`. Then:
   - `python scripts/short-stillness.py <render> --check` passes;
   - a 1-frame-a-second contact sheet of the whole film, looked at, end to end;
   - the `video-review` skill run by a fresh agent on the captioned render; fix what it finds
     that a viewer would notice (at most three changes).
10. **Thumbnail and description, then stop.** Make five or six thumbnails with
    `make-thumbnail.py --html` (big words on a dark panel at left, one still uncovered at right,
    at most four words, e.g. "$40K TO BUFFETT"), compare them at 168 px wide, pick one. Write
    `description.txt` like MongoDB's: two sentences, chapters with timestamps, the sources.
    **Do not upload**: the YouTube sign-in for @sp_500_explained is on the laptop. Leave the
    finished files in `projects/bending-spoons-history/outputs/` and `thumbs/`.
11. **Record and push.** A journal note in `journal.md` (what was made, every picture redone and
    why, what you would change), commit the manifest, script, score, description, journal and
    fact sheet (`git add -f` for files under `projects/`), push to kc-local's `origin`
    (`/srv/kitcut/git`) on branch `bs-film`.

## Report back (one short message to the owner)

The render's full path and length, the thumbnail you picked and the runners-up, how many pictures
were redone, anything left out of the script because it could not be confirmed, and the review's
verdict. Business language: what a viewer will see, not script names.

## Hard rules

- Nothing Russian, ever: no Russian sources, no Russia-connected people in the film.
- Every number on screen or in the voice is from the fact sheet. No invented quotes.
- At most 3-4 people per picture. No realistic people: round white stick-figure heads only.
- Do not upload, publish or post anything. Do not touch the studio's running films or services.
