---
name: video-review
description: Judge a video the way a demanding editor with the owner's taste would, before the owner sees it. Builds a review pack (the opening four frames a second with the words spoken, the cuts, stillness, loudness), watches it cold, holds it against measured reference openings and the project's review sheet, and answers with a verdict and a short list of timed, specific changes. Use on any film, opening or test before it is shown to anyone, and in a loop (fix, then a fresh reviewer) until it passes. It is the taste half of review; the studio's glitch reader is the other half and never judges taste.
---

# Reviewing a video for taste

A film can be free of glitches and still be one its owner switches off. The studio already has a
reader for what is **broken** (`studio/review.py`, `studio/prompts/review.md`: a cat through a
wall, a hand left hanging), and that reader is told never to judge taste. This skill is the other
half: whether the film is **good**, and exactly what to change.

It exists because of one night. On 2026-10-12 the maker of a padel film rebuilt its opening and
had a reviewer read it three times; the reviewer ended on "ship it". The owner watched and wrote:
"still not perfect. can u do something completely different as opening. i dont like what i saw".
The reviewer had read one frame a second, had been told by the maker what had been changed, and
had no record of what this owner likes. Each of the three is fixed below.

## Who reviews

**Never the maker, and never someone the maker has briefed about the changes.**

- You made the film: start a fresh agent with the words of `brief.md` beside this file. It names
  this skill, the pack, the project's review sheet, the references' packs, and what the film has
  to work with (so the changes asked for can be made). It says nothing about the film's history:
  not what was changed, not what was tried, not what an earlier reviewer said. A reviewer who
  knows what was fixed checks the fixes and stops watching the film.
- You are asked to review something you did not make: you are the reviewer. Read on.
- Every round gets a **new** reviewer with the same brief. One who saw the last version reviews
  its own notes.

## 1. Make the pack

```
python scripts/review-pack.py <video> --out <folder> [--opening 30] [--lines <film>/audio/vo/timeline.json]
python scripts/review-pack.py <video> --list        # the counts only, no pictures
```

It writes `opening-NN.jpg` (the first 30 s, four frames a second, twelve to a sheet, each frame
with its time and the narrator's words of that quarter second), `film-NN.jpg` (the whole video a
frame a second), `cut-NN.jpg` (each hard cut of the opening as six frames), `first.jpg` (the
file's first frame at full size) and `pack.md` (cuts and the shots between them, slow and still
stretches, loudness second by second, the narration's first word and pauses). `--at 2.4,6.1`
adds any moment at full size.

Make a pack of the references too: the series' last approved episode, and whatever the project's
review sheet names. A reviewer who has only the candidate in front of them has nothing to hold it
against.

## 2. Watch it cold, before you read a single number

Open `first.jpg`, then the opening sheets in order, at reading pace, once. Then write the cold
notes, which go into the report unedited:

- **Frame 0:** what it is, and whether it works as the picture a player shows before it starts.
- **At 1 s, 3 s, 5 s, 10 s, 20 s, 30 s:** what a stranger has seen so far, what they know about
  what this video will give them, what has moved, and whether they are still watching. One line
  each.
- **The second you would have left,** if there is one, and why.

Do this before `pack.md`. Once you know the numbers you stop seeing the film.

## 3. Then look closely

- `pack.md`, against `benchmarks.md` beside this file.
- Every piece of text in the opening at full size (`--at`, or
  `ffmpeg -ss <t> -i <video> -frames:v 1 <out>.jpg`): can it be read in the time it is up (three
  words a second), does it touch anything.
- Every cut strip: does the eye know where to look in the first frame after the cut, does
  anything jump that should carry across.
- Motion that matters, as frames a tenth of a second apart: an entrance, a swing, a camera move.
  Four frames a second still hides what happens inside a quarter second.
- The body at a frame a second, for what a viewer feels (a stretch that drags, a picture that
  comes back, a chapter that looks like the last). Leave glitches to the glitch reader unless one
  is in your way.

## 4. The bar

Each line is a question to answer with a time and a frame. The numbers are from six openings
measured on 2026-10-13 (`benchmarks.md`): a small sample, a floor and not a recipe.

**The first frame and the first three seconds**
- Frame 0 is a picture someone would press play on: the subject large, or the title. Never an
  empty ground, a fade up from black, a logo alone, or a frame left over from another chapter.
- By 3 s something has moved and the viewer knows the subject: which sport, which shot, which
  question.
- There is sound in the first second. All six references have it. Music counts, silence does not.
  A voice that starts later than two seconds in needs pictures that carry the wait (a title cut to
  music); say how long the wait is and whether they do.

**The promise and the name**
- By 10 s the viewer knows what they will get, said or written. The references do it in 4 to 14 s.
- The film's name is on screen once, large, readable for two seconds or more, in the series'
  type, by 15 s. A cold open may push it later only if every second before it is action.
- The channel is named once in the opening, small.

**The subject is big**
- In a shot about a person or a figure, the figure is at least a third of the frame's height. The
  references' first shots: 45 to 90 per cent.
- A diagram fills the frame. A court or pitch that is a strip a third of the frame high, with
  figures under a tenth of it, is a diagram seen from too far.
- One thing to look at in each shot. If the eye has two places to go, it is two shots.
- The thing the shot is about (the ball, the hand, the number) is found in half a second on a
  phone: 1.5 per cent of the frame's width or more, or marked.

**It moves, and every second earns its place**
- In the opening there is a new picture or a plain change within every five seconds. The edited
  references cut every 0.5 to 6.8 s; the one-take references have a person moving and talking
  throughout. A painting under a slow push is one picture however long the push lasts.
- Nothing comes twice: not the same picture, not the same words on screen and in the voice, not
  the same move. A list shown and then shown again as a list is a repeat.
- Words on screen are the two to five words the viewer should keep, not the narrator's sentence.
- Nothing waits. A pause in the voice has a picture that needs the pause.

**It is true**
- People, places and things are what the subject's own people would recognise at a glance. The
  project's review sheet lists what a picture can get wrong (a court's lines, a racket in every
  hand, how many players, where they stand).
- The picture shows what is being said at that moment. "At the net" is drawn at the net.

**Type and layout**
- No text over a face, a ball, a racket, another text, or a line that runs through it. Nothing cut
  by an edge.
- Text meant to be read is at least 1/36 of the frame's height (30 px at 1080).
- A source line, a chapter mark and a label never sit on each other.

**Sound, by measurement only**
- You cannot hear. Say so in the report. What can be checked: about -14 LUFS integrated, a true
  peak at or under -1 dBFS, no second of the opening more than 10 LU under the rest unless the
  silence is meant, and the music under the voice where the film's mix reports it
  (`audio/balance.json`).

**One series**
- Hold it against the series' last approved episode: the same type, the same colours, the same
  kind of opening. Someone who saw the last one knows this one within two seconds.

## 5. What this owner has said

A reviewer's taste is worth what it predicts. These are the owner's own verdicts, each on
something a careful maker had thought finished. Predict the next one.

- **2026-10-09, a tall cut made from a wide film's scenes:** "it's still for seconds. the image
  doesnt move at all." A held diagram is not a picture.
- **2026-10-12, a 3:22 technique film:** "Now it seems a bit too long. Can you do a fresh look at
  the timing, pacing and repeating." Length is felt as repeats: cut the second showing.
- **2026-10-12, the same film with no opening:** "there is no intro. the video immediiately starts
  showing the technic ... keep it short, dynamic, not boring", and "we need to reuse assets and
  styles from previous videos to make it work like a series."
- **2026-10-12, a film that began with the narrator over a small diagram:** "dont you think the
  opening is bad? we immediately from 0:1 start pitching. no intro at all."
- **2026-10-13, that opening rebuilt as a slow-motion diagram under a headline, passed by a
  reviewer:** "still not perfect. can u do something completely different as opening. i dont like
  what i saw." Shown three different ideas as one picture, they chose the one with large painted
  people cut to music, then asked for the title first, and noticed that two painted players held
  no rackets.

What that adds up to:
1. An opening introduces: the name early, what the film is, then the lesson. Not a lecture from
   second one, and not a long logo either.
2. People, large and painted, before diagrams. A diagram is never the first picture.
3. Short and moving. A repeat is the first thing to cut.
4. The details of the subject are noticed. One wrong prop is remembered longer than ten right
   scenes.
5. When they reject something, they want a different idea, not the same one polished.

A project's own verdicts go in its review sheet (below), where they outrank these.

## 6. The report

Under 500 words, in this order.

1. **Verdict,** one line: `SHOW IT`, `FIX FIRST` or `CHANGE DIRECTION`. When the piece has parts
   (an opening and the hand-off into what follows), say which part each blocker is in: "the
   opening has no blocker; both are in the hand-off" tells the maker what is finished.
2. **Cold notes,** as written in step 2.
3. **What the owner will say,** up to three lines, in their voice. If you cannot imagine them
   saying anything, you have not found the film's weakest second yet.
4. **Blockers,** up to five, most costly first: what a stranger leaves over, or the owner sends
   back. Each one has the time, what is seen (name the frame file), what it costs the viewer, and
   the change as an instruction: what, where, for how long. The change must be possible with what
   the film has; if it needs something new (a painting, a re-recorded line), say that.
5. **Improvements,** up to five, in the same form: worth doing if cheap.
6. **Keep:** what works and must not be touched.
7. **Scores,** 1 to 5 each: first three seconds, promise and name, subject size, movement and
   pacing, truth, type, series. Below 4 on any of the first three is `FIX FIRST`.
8. **Not judged:** the sound by ear, anything the frames could not show.

How to write it:
- Every finding has a time and a frame. No adjective without a number.
- Never "consider" or "could". Say the change.
- If you cannot name the change, it is not a finding.
- `CHANGE DIRECTION` when the trouble is the idea and not its execution: the cold watch says "I
  would have left" for a reason no fix reaches. Then give three different directions, a line
  each, with what each one needs.
- A clean film is a good answer. Do not invent findings to fill the list.

## 7. The loop, for the maker

1. Build, make the pack, hand it to a fresh reviewer who knows nothing of the history.
2. Check each finding by a number or a frame before changing anything. A third of the first
   reviewer's claims that night were about scenes the owner had already approved: those go back to
   the owner as questions, not into the film.
3. Fix the blockers. Do the improvements that are cheap. Rebuild.
   - **Two rounds will ask for opposite things in the same seconds** (one: open on the ball and
     tilt down to the players; the next: open on the players and tilt up to the ball). Neither is
     the instruction. Find what both are complaining about (there: a held frame, a small subject,
     a ball that left the picture) and fix that.
   - **A blocker in the same seconds two rounds running** means the idea for those seconds is
     wrong, however it was polished between. Replace the idea there, do not tune it. And when the
     picture has been replaced and the seconds still fail, read the words: four reviewers in a row
     marked one stretch as a repeat under cards, then a solo shot, then a split screen, because
     the narrator's line there named what the intro had just shown. No picture under a repeated
     line is new. The line was cut and the blocker went with it.
   - **What a reviewer asks for that is not yours to decide** (a logo on every scene of a
     published film, a re-recorded line) goes to the owner as a question, with the reviewer's
     reason. Say in the next brief that it is out of scope, or every round will ask again.
4. New pack, **new** reviewer, the same brief, no history.
5. **Know the reviewer's floor before you chase it.** Once per series, have a fresh reviewer read
   the last film the owner approved, with the same brief (and a copy of the review sheet that
   does not say it was approved). The night this was written the approved episode came back
   `FIX FIRST` with two blockers and scores of 4, 4, 4, 3, 3, 4, 4: a demanding reviewer finds
   about two things in anything, in a new place each round (that night: 4, 3, 1, 2, 2, 2 over
   six rounds, never `SHOW IT`). So the loop does not run to zero. It ends when:
   - a fresh reviewer says `SHOW IT`; or
   - the candidate reviews no worse than the approved film (as few blockers, no score lower, and
     "would have left: nowhere"), and its blockers are not the ones of the round before; or
   - four rounds have gone in one direction. If by then the same seconds keep failing, or the
     blockers are not falling, the direction is wrong: draw three different ideas as one picture
     and let the owner choose.
   Write the floor into the project's review sheet, so that the next film starts from it.
6. Then the owner. Send the clip and, in three lines, what the last review said and what it could
   not judge. A reviewer's pass is not approval.
7. Write the owner's verdict into the project's review sheet the same day, in their words. That
   file is how the next review gets better.

## 8. The project's review sheet

`REVIEW.md` at the root of the channel, series or project. It holds what this skill cannot know:

- **The series:** its approved episodes (where their files are), its type, colours and furniture,
  and how its openings go.
- **What must be true:** the facts of the subject that a picture can get wrong.
- **The owner's verdicts on this project,** dated, in their words, with what they were shown.

If there is none, write it from the brief and the owner's messages before the first review, and
give it to every reviewer.

## What it cannot do

It reads pictures and counts. It cannot hear a voice, feel a rhythm at speed, or know that a
joke lands. The owner's eyes are the last review, every time.
