# The brief for a reviewer

Copy this, fill the brackets, and give it to a fresh agent. Change nothing else: every round's
reviewer gets the same words, and none of them is told what an earlier round said or what was
changed since. What the last section lists is what makes the reviewer's changes ones that can be
made; leave it out and half of them will ask for footage the film does not have.

---

You are reviewing [the opening of] a video for taste. You did not make it. Follow the review
skill exactly, in its order (the cold watch comes before pack.md): read both files in full before
anything else.

- The skill: [path]/.claude/skills/video-review/SKILL.md and, beside it, benchmarks.md
- The project's review sheet (the series, what must be true of the subject, the owner's
  verdicts): [path]/REVIEW.md

What you are reviewing: [the first N seconds of a M-minute film, its title, which episode of
which channel]. Review [from frame 0 to where chapter 1 begins (about 0:SS), and the hand-off into
chapter 1 (to 0:SS)].
- The video ([size, frame rate, draft or final], with sound): [path]
- Its review pack (already built): [folder]
- The narration, with times, is in pack.md ("Lines in the opening").

Reference packs to hold it against (same layout):
- [the series' approved episodes: one line each, with the owner's words on it and the pack's folder]
- [the outside references of benchmarks.md, if their packs are on this machine]

What the film has to work with, so that every change you ask for is one that can be made:
- [its pictures: each painting or shot in a few words; whether more can be made or a part retouched]
- [its drawn or animated material, and what its camera can do]
- [its type and furniture: cards, marks, chapter chips, source lines]
- [the narration: recorded or not; whether words can change (say so when a change needs it) and
  whether pauses can; the music: a score that can be rewritten, or a track that cannot]
- [hard limits, in numbers: what cannot be had together (a lob that climbs seven metres and a
  player a third of the frame tall in one picture). A reviewer who is not told will ask for it]
- [what is out of scope because it is the owner's decision about the whole film, said plainly]

Rules for you: read-only. Change nothing outside your scratch folder (create it: [folder]). No
network. To look closer use ffmpeg as the skill says.

Answer with the report exactly as the skill's section 6 sets it out, under 500 words.
