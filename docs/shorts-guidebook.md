# The Shorts guidebook

The rules every YouTube Short made here is held to. Each one can be checked on the finished file
with a stopwatch, a ruler or a read of the script, and each says what it rests on.

- **STRONG**: YouTube or Google says it in its own words, or it is measured with a stated sample.
- **MEDIUM**: a named practitioner who publishes numbers, or our own measurement of 25 high-view
  news and explainer Shorts (2026-10-09; films that worked, with no failures to compare against).
- **OWNER**: the channel owner's call after watching our own films, with the date. An owner's call
  beats a MEDIUM rule; where the two differ, both are written down.

Why it exists: on 2026-10-09 five Shorts were made that opened on a clue and reached the news
seconds later. The owner watched the first seconds, found no hook, and they were all redone.
YouTube's Shorts lead says the same of every flop a creator shows him: the share who swiped away
"was just much higher. They didn't get them with the hook!"

## 1. The first three seconds

| # | Rule | Rests on |
|---|---|---|
| 1 | **The news is the first frame.** Frame 0 carries a headline of eight words or fewer in very large type and the thing the story is about. No logo, title card, greeting or scene-setting before it. | OWNER 2026-10-09; 0 of 25 open on a logo or greeting; text on screen inside one second in 24 of 25 |
| 2 | **The voice speaks at once.** The first word starts within 0.3 s of the first frame. No silence, no music alone. | 25 of 25 (median 0.07 s); Google: "Announce yourself with audio" |
| 3 | **The first sentence is the news:** who did what, naming the subject, in 16 words or fewer, finished by 0:05. Never a clue, a quote, a small detail or a question the film has not earned. | OWNER 2026-10-09; sample median 16 words ending at 4.4 s; 22 of 25 name the subject |
| 4 | **The same sentence, or the next, holds the reason to stay:** a consequence, a conflict, a number, "but". | The patterns in every opening of the sample |
| 5 | **The picture changes inside three seconds,** and at least twice in the first ten. | Sample: first cut at a median 2.9 s |
| 6 | **Sound off, the first five seconds still tell the news:** headline and captions carry it. | The Shorts player has a mute button and does not switch captions on by itself (STRONG) |
| 7 | **Frame 0 of the file is the film's own first frame.** Look at it: a feed shows it before anything plays. | The studio's cover frame put the film's ending there on every Short until 2026-10-09 |

## 2. A news Short: the bulletin

For any Short made from a news story.

| # | Rule | Rests on |
|---|---|---|
| 8 | **A bulletin, not a drama.** A strap across the top with the label, the headline under it, a lower band naming the source and date of what is on screen. Told evenly: not a thriller, not a mystery. | OWNER 2026-10-09 ("too dramatic. can we instead have a breaking news format") |
| 9 | **"BREAKING" only on news under two days old.** Otherwise a plain label ("AI NEWS · THIS WEEK"). | Ours; a stale "breaking" is a lie a viewer can check |
| 10 | **The source's own pages are on screen, always:** real screenshots of the headlines from the source websites, the primary source on the first frame and the press after it. | OWNER 2026-10-09 ("screenshot and show the news headlines directly from the source web sites. always.") |
| 11 | **Each screenshot shows masthead, the whole headline and the date,** one page at a time, large enough to read, with nothing laid over its text. Never redrawn or retyped. | A pilot stacked three pages so each hid the last and cut one headline in half |
| 12 | **Then "what we know": three to five facts,** one at a time, each with its proof on screen as it is said: a page, a number set large, a short quote with its speaker. | The bulletin format; YouTube's own feedback tool grades "the hook, the pacing, the visuals" |
| 13 | **Then what is not known, and stop on the payoff line.** No summary, no sign-off. | Payoff: YouTube does not count time spent waiting for an ending that never comes as value (STRONG) |
| 14 | **Every claim keeps its source's own caution** ("says", "believes"), and every number is the source's exact number. Check the finished narration against the primary source, not against the prompt. | Two of our first five Shorts repeated what the prompt had invented |

## 3. The body

| # | Rule | Rests on |
|---|---|---|
| 15 | **One story, one idea.** A fact that does not serve it is cut. | Hoyos on YouTube's channel (MEDIUM) |
| 16 | **Each beat follows from the last by "but" or "so".** A join that only works as "and then" is rewritten. | Hoyos, after Parker and Stone (MEDIUM) |
| 17 | **A new picture every three to five seconds.** | Sample: median shot 3.2 s |
| 18 | **Something on screen shows how far along the film is:** a count, numbered facts, a timeline. | Hoyos's "mechanism" (MEDIUM) |
| 19 | **Long enough to explain, 90 seconds to 3 minutes, and a stranger can follow it.** YouTube names no ideal length and adjusts for duration. | OWNER 2026-10-08; YouTube (STRONG) |
| 33 | **Nothing stands still.** The picture is frozen for no more than 5% of the running time and never drifts without real movement for longer than 3 seconds. A diagram a wide film would hold while the narrator explains it is moved in a Short: the camera follows the action, a picture is studied part by part on the narrator's words, a number counts up. `python scripts/short-stillness.py <mp4> --check` measures it on the finished file. | OWNER 2026-10-09 ("it's still for seconds. the image doesnt move at all"), of five padel Shorts cut from a wide film; measured, their picture stood still for 49 to 65% of the time, and 0% after they were rebuilt, with no slow stretch over 2 s |

## 4. Voice and sound

| # | Rule | Rests on |
|---|---|---|
| 20 | **The narrator is fast and confident with a steady voice:** energy and emphasis on the key words. Not a flat anchor, and not alarmed either. | OWNER 2026-10-09: an even anchor read was "too passive, too flat, no emotions"; a "very fast and excited" read was "too panicking now. find a middle ground" |
| 21 | **Pace: 150 words a minute or more, pauses included.** The owner approved the flow of a pilot at 155. The sample's median is 202 and none is under 144, so slower than 150 is too slow. | OWNER 2026-10-09; sample |
| 22 | **No music.** No score, and no pitched sounds among the effects (no chime, no sampled note). A few short, quiet, unpitched sounds on the cuts may stay. | OWNER 2026-10-09 ("music is cringe/ remove it"). Nothing with data was found for or against music under narration |
| 23 | **Let the owner choose the narrator by ear.** A model cannot hear: pace can be measured, emotion cannot. Record the same two sentences in several voices and put them on one page. | Three rounds on 2026-10-09 |

## 5. Captions and layout

| # | Rule | Rests on |
|---|---|---|
| 24 | **The spoken words are burned in from the first word,** two to five words a card, one or two lines. | 20 of 25; captions do not auto-start in Shorts (STRONG) |
| 25 | **The caption's centre line sits between 67% and 83% of the height;** nothing to be read lower than 80%, where the title and channel name lie. | 16 of 20 captioned Shorts in the sample; `film.TALL_COVERED` |
| 26 | **Nothing to be read in the right-hand strip of the lower half** (like, comment, share). | Google's vertical safe zone (STRONG, for ads) |
| 27 | **Type for a phone at arm's length:** a headline 90 px or more of 1920, nothing to be read under 44. | Ours |

## 6. The ending and the packaging

| # | Rule | Rests on |
|---|---|---|
| 28 | **End on the payoff line.** A small "Made with KitCut" may sit over the last held picture; never an outro card after it. | None of the 25 has an outro card or a logo sting |
| 29 | **The title names the subject and puts the news in the first 40 characters.** Three hashtags at most. | Sample median 41 characters; YouTube (STRONG) for hashtags |
| 30 | **A news Short goes out as soon as it is right, at any hour. A flop is never deleted and re-uploaded.** | YouTube's Shorts lead (STRONG) |
| 31 | **Over 60 seconds, every sound is our own:** a copyright claim of any kind blocks the film worldwide. | YouTube Help (STRONG) |
| 32 | **Nothing Russian:** no Russian companies, people, symbols or outlets, in the film or in a screenshot. | OWNER, standing rule |

## 7. How a Short is made

1. **Research** the story to a fact sheet with a link for every fact, and what is commonly
   misreported.
2. **Screenshot the sources** at phone width (the screenshots skill, `--phone`), keep the raw
   shots, and crop each to masthead + headline + date. A page that blocks the shot is taken
   another way or another outlet is used.
3. **Write the prompt:** the strap label, the headline (eight words or fewer), the first sentence,
   the facts in order, the screenshots named one by one.
4. **For a new format or a batch, make a 20-second pilot first** and get the owner's yes before
   making the rest. A full Short costs 35 to 40 minutes; a pilot about ten.
5. **Make it:** `npm run film -- make ... --short --no-music` (the site), or
   `python studio/agent.py "..." --frame 9:16 --captions --no-music`.
6. **Check the finished file** against sections 1 to 6: frame 0, the first word's time, the first
   sentence, each screenshot, the narration against the source, the last second, and
   `python scripts/short-stillness.py <mp4> --check` (rule 33).
7. **Publish**, then at 48 hours read "viewed vs. swiped away" beside the opening line. A film
   below the channel's own median has a hook problem.

## 8. What the studio does for a Short

| What | Where |
|---|---|
| 1080x1920 at 30 fps, composed for the tall frame | `film.FRAMES`, `film.frame_note` |
| Captions burned into the picture, in a band clear of the phone's own buttons | `sketch/captions.js`, `film.caption_band` |
| The first word 0.1 s in (a wide film waits 0.5 s) | `film.vo_lead`, `film.TALL_LEAD` |
| The film's own opening as the video's first frame (no cover frame) | the manifest's `"cover": false`, set by `Film.create` |
| No music when asked: the score is not played, nor any pitched cue | the manifest's `audio.music: false`, `_sketchaudio.no_music` |
| No 16:9 thumbnail on a tall film | `thumbs.wide` |

`studio/test_shorts.py` holds all of it.

## 9. Not known

- No measured comparison of 60 to 180 second Shorts against shorter ones was found.
- No data was found on music under narration, sound effects on cuts, or whether a closing call to
  action costs views (9 of the 25 end with one spoken request, six of them above 10 million views).
- YouTube publishes no figure for a good viewed-versus-swiped rate, for how many seconds a viewer
  gives a Short, or for where its buttons cover an ordinary Short in pixels.
- Our sample is 25 successful Shorts picked by hand; it shows what winners share, not what causes
  a win.
- Rule 33's limits (5% still, 3 s slow) are where five rebuilt Shorts of our own landed, not a
  figure anyone publishes. Neither the 25-Short sample nor the studio's own news Shorts have been
  run through `short-stillness.py` yet, so the limits may be loose or tight for footage and
  screenshots.
- Rule 33 is numbered out of order on purpose: rules 20 to 32 are cited by number elsewhere.
