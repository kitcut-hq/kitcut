# The brief for a reviewer

Copy this, fill the brackets, and give it to a fresh agent. Every round's reviewer gets the same
words. None of them is told what an earlier round said or what was changed since. All of them are
told what the owner asked for: that is the assignment, not the history.

---

You are reviewing [the opening of] a video for taste. You did not make it. Follow the review
skill exactly: read it in full before anything else, and look at `story.jpg` before any other
picture.

- The skill: [path]/.claude/skills/video-review/SKILL.md
- The project's review sheet (the series, what must be true of the subject, the owner's
  verdicts): [path]/REVIEW.md

What you are reviewing: [the first N seconds of a M-minute film, its title, which episode of
which channel]. Review [from frame 0 to where chapter 1 begins (about 0:SS), and the hand-off into
chapter 1 (to 0:SS)].
- The video ([size, frame rate, draft or final], with sound): [path]
- Its review pack (already built): [folder]

What the owner asked for, in their words: "[the request, quoted whole]"
[If they named a model: its pack is at [folder]. Lay its story.jpg beside this one.]

What the film has to work with, so that anything you ask for can be made:
- [its pictures: each painting or shot in a few words; whether more can be made]
- [its drawn or animated material]
- [the narration: recorded or not, and whether words or pauses can change; the music]
- [what cannot change, and what is the owner's to decide about the whole film, said plainly]

Rules for you: read-only. Change nothing outside your scratch folder (create it: [folder]). No
network. To look closer use ffmpeg as the skill says.

Before you write the verdict, go through every one of the owner's verdicts in the review sheet,
oldest first, and ask of each: does this piece do what that verdict asked? A piece that breaks any
of them is NOT YET, however well it does the rest; name the verdict, in the owner's words. (The
owner, 2026-10-22, after two reviewers had passed a film that broke one: "remember my comments for
the future i'm tired repeating them".)

Answer with the report exactly as the skill's section 6 sets it out, under 300 words.
