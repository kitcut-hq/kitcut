---
name: video-review
description: Judge a video the way a sensible viewer with good taste would, before its owner sees it. The whole piece first (what it is for, whether it does that, whether it is what the owner asked for), then at most three changes, each big enough that a viewer would notice it. Never a list of small fixes. Builds a review pack whose first picture is the whole opening on one sheet. Use on any film, opening or test before it is shown to anyone. It is the taste half of review; the studio's glitch reader is the other half and never judges taste.
---

# Reviewing a video for taste

A film can be free of glitches and still be one its owner switches off. The studio already has a
reader for what is **broken** (`studio/review.py`, `studio/prompts/review.md`), and that reader
is told never to judge taste. This skill is the other half: whether the piece is **right**, seen
whole.

It was written twice, and the second time is why it reads as it does.

- **2026-10-12.** The maker of a padel film rebuilt its opening and had a reviewer read it three
  times. The reviewer, briefed by the maker on what had changed and reading one frame a second,
  ended on "ship it". The owner: "still not perfect. can u do something completely different as
  opening. i dont like what i saw".
- **2026-10-13.** The first version of this skill sent six fresh reviewers at the next opening.
  It armed them with four frames a second, a bar of numbers and seven scores, and each came back
  with about two timed fixes: a label, a held frame, a ball out of shot. Every one was made. None
  of the six asked whether it was the right opening. The maker then measured the reviewer against
  a film the owner had approved and made that the level to reach. The owner: "i don't want you to
  consider the approved one an ideal. i never said it should be. instead i want the reviewer to
  have common sense. its goal not to provide feedback that require micro changes but see the
  entire picture", and asked for the kind of opening the channel's first film has. One look at
  the two openings side by side would have said that in round one.

So: the whole first, common sense over rulers, nothing treated as the ideal, and a review that is
allowed to say "it works".

## The one question

Would the owner, and a viewer who came for this subject, be glad that this is the opening (or the
film, or the test)? Everything below is a way of answering that about the whole piece.

## Who reviews

**Never the maker, and never someone the maker has briefed about the changes.**

- You made the film: start a fresh agent with the words of `brief.md` beside this file. It names
  this skill, the pack, the project's review sheet, what the film has to work with, and **what
  the owner asked for, in the owner's own words**. It says nothing about the film's history: not
  what was changed, not what was tried, not what an earlier reviewer said. A reviewer who knows
  what was fixed checks the fixes and stops watching the film.
- You are asked to review something you did not make: you are the reviewer. Read on.
- Every round gets a **new** reviewer with the same brief.

## 1. Make the pack

```
python scripts/review-pack.py <video> --out <folder> [--opening 30] [--lines <film>/audio/vo/timeline.json]
python scripts/review-pack.py <video> --list        # the counts only, no pictures
```

`story.jpg` is the one that matters: the opening as **one picture**, a frame every two seconds,
large, with everything said in those two seconds under it. `first.jpg` is the file's first frame.
The rest is for looking closer when the whole raises a doubt: `opening-NN.jpg` (four frames a
second), `film-NN.jpg` (the whole video a frame a second), `cut-NN.jpg` (each hard cut as six
frames), `pack.md` (cuts, stillness, loudness, the narration's pauses), `--at 2.4,6.1` for any
moment at full size.

If the owner has pointed at another film ("like the first one"), make its pack too. The two
`story.jpg` sheets side by side are the comparison.

## 2. See the whole first

Open `story.jpg` and `first.jpg`. Open nothing else yet. Then write, in plain words:

- **What it is.** In two sentences, what happens from the first second to the last, as you would
  tell a friend: "the name over a painting, then the claim, then three cards, then the lesson".
- **What it is for, and whether it does it.** An opening has three jobs: say what the film is,
  make this viewer want it, and hand over to the lesson. A chapter has one: leave the viewer
  knowing one thing they did not. Which jobs does this piece do?
- **How it feels.** Calm or rushed, clear or busy, one idea or several, sure of itself or
  anxious. Is that the right feeling for this channel and for someone who came to learn this?
- **Whether it is what the owner asked for.** Their request is in the brief and their earlier
  verdicts are in the project's review sheet. When they named a model, compare the shapes: what
  comes first, what follows, how long each part holds, how much is on screen at once. Shape and
  feel, never detail.
- **Whether you would keep watching.** If not, at which part, and why.

That paragraph is most of the review. If it says the piece works, the review is nearly done.

## 3. Common sense

What a sensible person checks without a ruler:

- Does the picture show what the words are saying at that moment?
- Is there one thing to look at at a time, and is it big enough to see on a phone?
- Can the words on screen be read in the time they are up?
- Is anything plainly wrong to someone who knows the subject? The project's review sheet lists
  what a picture can get wrong (a court's lines, a racket in every hand, where players stand).
- Does it look like the same channel as its other films?
- Is any part there twice, or there for no reason?
- Is anything dead: a stretch where nothing arrives and nobody speaks?

Use the close sheets, `pack.md` and `benchmarks.md` only to settle a doubt the whole raised ("the
middle felt slow: was it?"). Never read them through looking for things to report. That is how a
review turns into a list.

## 4. What does not go in a review

- Anything a viewer watching once, at speed, on a phone would not notice, or would notice and
  not mind: a label a little to one side, two rings at one height, a hold of 1.3 s that could be
  1.0, a single frame.
- A change the maker could make in ten minutes that no viewer would describe afterwards.
- A choice between two things that both work.
- Anything the brief says cannot change, or is the owner's to decide.
- A finding for the sake of having findings. **"It works. Show it." is a complete review.**

The test for a finding: *is this something the owner would say in a one-line reaction?* Theirs,
on record, are about the whole ("no intro at all", "i dont like what i saw", "it seems a bit too
long", "more like the first one") and, now and then, a plain mistake seen at a glance ("people
with no rackets"). A review speaks at those two sizes and no smaller.

## 5. Nothing is the ideal

- **An approved film is one the owner let through.** It is not their ideal and nobody said it
  was. Do not hold a new piece to it, score against it or copy it, and never run a reviewer on it
  to find a level to reach.
- **The openings in `benchmarks.md`** are how six well-watched videos happen to open. They are
  background for an opinion. A film is not wrong for being unlike them.
- **The only model is one the owner names,** for the piece in hand, in their own words. It is a
  model of shape and feel, and it stands until they say otherwise.
- **Numbers are evidence for something you already felt.** A count of cuts or a share of still
  frames never makes a finding by itself: the channel's most watched film holds one painting for
  eighteen seconds.

## 6. The report

Under 300 words, in this order.

1. **Verdict,** one line.
   - `SHOW IT`: the whole works and is what was asked for. Small things may remain.
   - `NOT YET`: the idea is right, and one to three big things stand between it and working.
   - `WRONG IDEA`: no fix reaches it. Say what the idea is and why it is wrong for this owner and
     this viewer, then three other ideas, a line each.
2. **The whole,** one paragraph: what it is, what it does, how it feels, whether it is what was
   asked for.
3. **The big things,** at most three, biggest first, and none if there are none. Each is about a
   part of the piece, not a frame: an order, a length, a picture, a tone, a part that should go.
   Say what is wrong with the whole because of it and what to do instead. A range of seconds,
   not a timestamp.
4. **Plain mistakes,** at most three, a line each: things that are simply wrong and that a viewer
   would see (a missing racket, a word cut by the edge, a number that is not true). No taste
   here, and nothing a viewer would miss.
5. **Keep:** the one or two things that make it work.
6. **Could not judge:** the sound by ear, anything the stills could not show.

No scores. No list of improvements. No "consider". Plain words a person would say out loud.

## 7. The loop, for the maker

1. **Before building,** write one sentence: what the piece is, and why this owner would want it.
   Check it against their words. If you cannot write it, you are about to build the wrong thing.
   The maker's own common sense is the first review, and the cheapest.
2. Build, make the pack, look at `story.jpg` yourself, then hand it to a fresh reviewer.
3. **`SHOW IT`:** fix the plain mistakes and show the owner, with what the review said in two
   lines. No further round to confirm a small fix.
4. **`NOT YET`:** do the big things, then one more round with a new reviewer. Three rounds at
   most. A third `NOT YET` means the idea is wrong.
5. **`WRONG IDEA`:** stop polishing. Make a different idea, or draw three as one picture and let
   the owner choose.
6. **Never** polish through rounds of small fixes, measure a reviewer on an approved film, or
   chase a score. Rounds that each find "about two things, somewhere new" are not converging on
   anything: they are the sign that nobody is looking at the whole.
7. Two reviewers will ask for opposite things. Neither is the instruction: find what both are
   complaining about. What is not yours to decide (a line re-recorded, a look for the whole
   film) goes to the owner as a question, and into the next brief as out of scope.
8. A reviewer's pass is not approval. The owner's eyes are the last review, and their verdict
   goes into the project's review sheet the same day, in their words.

## 8. The project's review sheet

`REVIEW.md` at the root of the channel, series or project. It holds what this skill cannot know:

- **The series:** its films and where their files are, its type, colours and furniture.
- **What must be true:** the facts of the subject that a picture can get wrong.
- **The owner's verdicts on this project,** dated, in their words, with what they were shown, and
  any model they have named.

If there is none, write it from the brief and the owner's messages before the first review, and
give it to every reviewer. It outranks everything in this file.

## What this owner has said

A reviewer's taste is worth what it predicts. These are the owner's own reactions, each to
something a careful maker had thought finished.

- **A tall cut made from a wide film's scenes:** "it's still for seconds. the image doesnt move
  at all."
- **A 3:22 technique film:** "Now it seems a bit too long. Can you do a fresh look at the timing,
  pacing and repeating."
- **The same film with no opening:** "there is no intro. the video immediiately starts showing
  the technic ... keep it short, dynamic, not boring", and "we need to reuse assets and styles
  from previous videos to make it work like a series."
- **A film that began with the narrator over a small diagram:** "dont you think the opening is
  bad? we immediately from 0:1 start pitching. no intro at all."
- **That opening rebuilt and passed by a reviewer:** "still not perfect. can u do something
  completely different as opening. i dont like what i saw."
- **The next one, after six rounds of reviewed small fixes:** "its goal not to provide feedback
  that require micro changes but see the entire picture ... make it more like the first one we
  made with a similar intro."

What that adds up to:

1. They judge the whole, in one line. A list of small fixes does not turn an opening they
   dislike into one they like.
2. An opening introduces: the film's name, what it is about, what it will cover, then the
   lesson. Not a lecture from second one.
3. People, large and painted, before diagrams.
4. A repeat is the first thing to cut, and a held diagram is not a picture.
5. A plain mistake is seen at once: one wrong prop is remembered longer than ten right scenes.
6. When they reject something they want a different idea, and they will often point at one they
   liked. Ask what they liked about it before building, or go and look.
7. Something they approved is not something they called ideal.

## What it cannot do

It reads pictures and counts. It cannot hear a voice, feel a rhythm at speed, or know that a joke
lands. The owner's eyes are the last review, every time.
