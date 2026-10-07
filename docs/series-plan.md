# Scaling a series: what the studio needs first

Decided 2026-10-02, with the owner, before scaling the Duchess cat series (kitcut.ai project
`p-myodgkrkbv`) in quality, episode length and episode count. The same changes serve every series
on kitcut.ai: a project is a series. Prepare the system first, then the content.

## Where a series stands today

What already works: a project keeps its cast and places (`studio/library.py`), approved voice
lines play the same take in every episode, films over 5 minutes are made a scene at a time
(`studio/scenes.py`, `STUDIO_SCENES_OVER_S=300`), and the publish dialog schedules a YouTube
release (`publish_at`).

What breaks at scale:

| | today | at 30 episodes |
|---|---|---|
| the brief | capped at 2,000 characters (`film.BRIEF_MAX`); the Duchess brief is already at it | a show bible is 8-10k: the household, rooms, running gags, catchphrases so far |
| memory | an episode sees only its last 5 (`library.MEMORY`) | episodes 1-25 are forgotten: twists and catchphrases repeat, no call-backs |
| sounds | the cast is kept; the bell, the "sad trombone", the fridge choir are re-invented each film | a show's sound is half its identity for kids |
| review | the first thing the owner sees is the finished film | a storyboard check costs 5 minutes; a wrong render costs an hour |
| checks | Claude may run out of time before the motion check (Leo's bus episode did) | stills-only review lets flat stretches through |

## The list, in build order

1. **A real series bible.** `BRIEF_MAX` 2,000 -> 10,000, in the studio (`studio/film.py`) and
   the site (`lib/projects.js`, the MCP project tools, the project page). *Built 2026-10-02.*
2. **The episode log.** After every finished episode the studio writes one entry to the
   project's `canon.json`: title, a one-line story, catchphrases, the twist, what was new (cast,
   places, sounds), and gags that could come back. Every next episode reads the whole log, so
   episode 30 knows episode 1. The last 5 episodes' files stay as they are. A back-fill builds
   the log for series made before it (`ops.sh canon`). *Built 2026-10-02 (`studio/canon.py`).*
3. **A storyboard stop** (optional per film): after the narration and first stills, the film
   waits (the `waiting` state the voice step already uses) for an OK or a redirect, then renders.
   In scene mode the natural stop is after the director pass.
4. **Kept sounds and a theme.** Named sound effects and a theme tune, kept in the project
   library the way the cast is: a film's `sounds.json`, used from `sfx.json` and `score.json` by
   name, kept after the film, seeded into the next. *Built 2026-10-02.*
5. **A guaranteed final check:** reserve Claude's time for the motion check, and flag any
   stretch where the picture holds with nothing said or happening. *Built 2026-10-07 as
   more than that, after three Duchess episodes shipped with glitches of half a second: the
   author reads the whole film a frame a second, the drawing code is read for what breaks
   between two stills, and the studio has the finished film read by a fresh Claude, with
   one bounded turn to fix what must be fixed (`studio/review.py`; studio/README.md, "A
   second pair of eyes"). The owner's standing corrections for a series go in its bible.*
6. **Pitches and a queue:** the project pitches ideas from the bible and the log; the owner
   picks; episodes are made one after another, each stopping at its storyboard. Replaces the
   hand-run batch scripts.
7. **Long episodes:** a 7-minute episode is one film made in scenes (three stories, one score),
   not three films stitched. Pilot first, to measure time and cost (an 8-minute film took ~2 h 20
   on the VM, `docs/studio-speed.md`).
8. **Shorts from a long episode:** a vertical render of one scene with the camera following the
   cast (every frame is code, so the studio knows where the character is).
9. **Publishing as a series:** a weekly slot per project, add each episode to the series
   playlist, "made for kids" by default.
10. **A brand kit per project** (asked for by a partner making a course): upload a brand book
    once; the studio reads it into colours, fonts, logo and tone the person checks; every
    episode uses it. Needs PDF and font-file uploads, which the studio does not take today
    (`studio/uploads.py`: pictures, voice notes, text). Advice given: a project-level step, not
    a prompt attachment, because a course is a series and a brand is decided once. Read the book
    into a brand card (palette as hex, fonts with a free stand-in where the font file is not
    given, logo files, tone of voice, do's and don'ts), show it for the person to correct, keep it
    in the project like its pictures. A brand book dropped on a single film's prompt still works
    and offers "keep it for the project". Get a real brand book first and build against it.
    *Built 2026-10-02* (`studio/brandkit.py`, the site's Brand tab; decided with the owner: the
    brand sets colours, type and logo while the look keeps the drawing style; one brand per
    project; uploaded fonts used after a tick). Any file goes up in parts; tested on two public
    brand books and a made-up one. Still open: a brand dropped on one film's prompt, "use the brand
    from another project", and the MCP tools (an assistant cannot see or set a brand yet).

Open question for the content, not the system: Duchess is "she" in every film so far; the owner
says "he" (Ukrainian кіт is masculine). The bible settles it.
