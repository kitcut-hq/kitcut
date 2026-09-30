# Approved voice lines

A project's approved voice lines are recordings of narration lines that the person listened to and approved. Every later episode that says the same words in the same voice plays that recording instead of recording the line again.

Built 2026-09-30 for the Ocheretyne Economics School series (project p-mii4mannfx). Its narrator stressed the school's name wrongly (ОчеретИнська for ОчерЕтинська) in three of four episode openings.

## The problem: nobody can tell the voice, and nothing hears it

- **The voice guesses the stress on every take.** Gemini TTS has no stored pronunciation for a rare name, and samples it afresh each time. The same text came out right in some takes and wrong in others; in the test, plain text was right in about half.
- **It cannot be told.**
  - Gemini-TTS documents no phoneme or IPA input.
  - Google's voices that do take custom pronunciations (Chirp 3 HD) exclude uk-UA.
  - Three tricks were measured on 12 takes of one line (two LLM judges, 6 votes each):
    - a stress mark (Очере́тинська): 2/6 in every take, worse than plain text;
    - a capital vowel (ОчерЕтинська): 3-5/6, no reliable gain;
    - a spoken instruction in the style: 0-2/6, worse.
- **Nothing in the pipeline hears it.** The check after recording (Whisper, KI-047) turns speech into text, which is identical whichever syllable is stressed, so a wrong take scores 1.00.
- **An LLM judge is too noisy to gate on.**
  - Gemini 3.5 Flash and 3.1 Pro, judging stress from audio, got the film's own right and wrong lines right at temperature 0.
  - But the same greeting audio scored 6/6 alone and 3/6 inside a joined line.
  - Its votes are a hint, not a test.

So the fix records nothing new: it keeps what a person approved by ear, and plays it again.

## Design

**A voice line** is `{text, tts, voice, model, language, dur, added, film, line}`.

- **Storage.** It is kept in the project's library: `library\<sha20(client)>\<project>\voice\<key>.wav|mp3`, plus index.json `voice`. There are up to 12 per project (`library.VOICE_LINES`).
- **The key** is `_sketch.voice_line_key(text, vo)`, a hash of:
  - the spoken words, with `[tags]` out and spacing, quote marks and dashes evened;
  - the TTS;
  - the voice;
  - the model, defaulted the way sketch-vo.py defaults it.
- **The style is not in the key, deliberately.** An episode whose voice direction drifts still gets the series' approved greeting, which is what approving it is for.

**Approve.**

- **From the site.** The project's Voice tab lists a finished episode's lines, each playable, with an Approve button. It calls `POST /api/library/voice {project, film, line}`, which runs `library.add_voice_from_film`: the line's own picked take (`_line.wav`), in the voice that episode's vo.json names.
- **From the command line.** For a recording no episode has as a whole line, such as a greeting cut from a longer take, `studio/voicelines.py ... add --file --text --like <episode>` does it on the VM.

**Seed.** `library.seed` copies the project's voice lines into every new episode's `audio\vo\approved\` with an index, records them in the film's `library.voice`, and `note()` lists them for Claude. The note tells Claude that a vo.json line with exactly those words plays that recording and is never recorded again: "use each word for word, as a line of its own, where it fits".

**Play.** In sketch-vo.py's synth stage, a line whose key is in `approved/` becomes that line's only take:

- **The take:** `use_approved()` copies the recording in as `L<i>_T0_<fp>.wav`, then writes `.json {"approved": key, "sha"}`. It copies again only when the project's recording changed.
- **No new recording:** nothing is synthesized and nothing is paid for, and a `--retake` of the line does nothing.
- **Word times:** these still come from the scorer, like any Gemini take.
- **The record:** the timeline marks the line `approved`. The voice tool's report says so, and `voice(retake_line)` refuses such a line: to say something else there, change the words.

## What it does not do

- **A name elsewhere in the narration** is not protected; only exact whole lines are.
  - The planned next step is a watch-word list, each word with its stress, plus several takes of any line containing one, with the take picked by comparing the word against an approved recording of it.
  - It is not built, because the comparison has to be measured first against 10-15 takes the person labels by ear. Until it is proven, the fallback is to flag such lines as "listen before publishing".
- **A different voice or model** records the line afresh: an approved Sadachbia greeting does not play in a Kore episode.
- **Splicing** (the greeting of one take joined to the rest of another) is an operator's repair (2026-09-30, blogger and cashback episodes), not a studio feature. With the greeting approved as its own line, episodes need no joins.

## Verified

- **check-sketch.py:** the key's normalisation and what it separates; `approved_lines`; `use_approved` (copies once, again after a change, drops the old score).
- **test_library.py:**
  - approve from an episode (someone else's film, another project, a missing line, an unfinished film: all refused);
  - listing, audio and delete (the owner only);
  - the 12-line limit;
  - the next episode's `audio\vo\approved\` and its note.
- **End to end:** sketch-vo on a two-line narration with the greeting approved.
  - Line 0 played the approved file byte for byte, with no TTS call and no cost; only line 1 was synthesized ($0.0014).
  - A `--only 0 --retake` left it untouched.
- **Site:** the Voice tab on the fixture site, approving and removing (screenshots in the site's docs, `docs/img/project-voice.webp`).
