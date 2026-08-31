---
name: video-channel-audit
description: Decide whether this repo can reproduce how a particular channel edits, from one of their published videos — rebuild the raw tapes their film was cut from, re-cut it, score it, and report the capability gaps with honest baselines. Use when asked whether we could edit for a channel, to analyse or replicate a video's editing style from a URL, to find what capabilities a target video needs that we lack, or to prepare evidence before approaching a channel about editing their videos.
---

# Auditing a channel we might edit for

The question is never "is our score good". It is **"which parts of this
channel's video can we produce, and which can we not"**. Answer that with
measurements off their own footage, and say the gaps out loud — a pitch built on
an inflated number dies at the first frame they watch.

The audit costs ~15 minutes; the frame-exact proof costs ~1 hour on a 20-minute
segment and 5–7 hours on a full-length film. Audit every candidate; prove only
the channel actually being approached.

Read `video-multicam-switch` for the machinery this leans on. Worked example end
to end: `projects/yt2-fpv33-seg/` and `projects/yt2-fpv33-val/`, plus their
journals.

## Ground rules, before anything is measured

- **Never publish a reconstruction.** Re-cutting someone's published video to
  test ourselves is ordinary work; posting the result is not. Show it, do not
  upload it.
- **A reconstruction is not a showreel.** A rebuilt tape holds real frames only
  where the editor used that angle, so a machine cut freezes wherever it
  disagrees — measured at **40.5% of the runtime** (11852 of 29250 frames) on
  the first channel audited. Never hand that file over as something to watch.
  The watchable artifact is the stage-1 replay plus finishing; the machine's own
  cut is evidence for us, and becomes watchable only on their real camera cards.
- **Quote a score with its do-nothing baseline.** "59%" means nothing until you
  say that never cutting away from their wide scores 52%.

## 1. Acquire and audit (~15 minutes, and it answers most of the question)

```powershell
python scripts/project-scan.py --init <id>
.venv/Scripts/python.exe -m yt_dlp -f "bestvideo[height<=1080]+bestaudio" `
    --merge-output-format mp4 -o "projects/<id>/sources/original.%(ext)s" "<URL>"
```

1080p, never 2160p: everything downstream encodes N tapes of whatever comes
down. Bare `yt-dlp` prints nothing on this machine — always
`.venv/Scripts/python.exe -m yt_dlp`.

Cut a **representative segment** with ffmpeg (`-ss`/`-to`, re-encoded at cq 14)
rather than working on a two-hour film: 15–20 minutes of ordinary content, past
any intro montage — a montage is not a multicam cut and flatters nothing. Cut a
**second, non-adjacent segment** at the same time; step 4 needs it.

```powershell
python scripts/shot-detect.py --src projects/<id>/sources/original.mp4 --sheets --angle-by auto
```

Then **look at the contact sheets** under `temp/shot-detect-<id>/`. They say what
each angle is, who is in it, and what is not a camera at all — inserts, graphics,
archive, screen recordings. Read the transition matrix too:

```python
seq = [s["camera"] for s in json.load(open("projects/<id>/<id>.shots.json"))["shots"]]
collections.Counter(zip(seq, seq[1:]))       # what follows what
```

Write the capability table from what you find, each row marked have / partial /
missing:

| what the film contains | where it is handled |
|---|---|
| N camera angles, switched full frame | `angle-cut.py` — have |
| angles that separate at all | `shot-detect.py --angle-by auto`; quote the margin |
| burned lower thirds | `name-label.py`, read by `angle-cut.py` — have |
| end cards, logos, stamps | `make-card.py` + `image-overlay.py` — have |
| burned captions, any language | `run-captions.py` — have |
| insert b-roll, archive, graphics | **partial**: detected into the `xtra` bin, never *chosen* |
| colour treatments (a B&W cold open) | `image-overlay.py` background treatments — partial |
| the editorial rhythm itself | measured in step 3 — usually the real gap |

## 2. The frame-exact proof (stage 1)

Three manifests copied from the closest existing film, then the round trip in
`video-multicam-switch`. The bar is absolute: zero shifted frames, zero frozen
filler, cut counts equal, every cut at offset 0, 100.00% angle agreement. This
proves their film is recoverable and replayable from tapes — the claim that
actually survives contact with a customer.

## 3. Can we make their editorial choices? (stage 2)

**Count the people at the shoot first, including the ones no camera points at.**
This is the highest-value input in the whole workflow and it is free: watch
thirty seconds of the wide. On the first audit a third man sat behind the
camera; his voice merged into a host's and the switcher spent his speech on the
wrong face. Declaring him moved the held-out score from **49.5% to 63.9%** with
nothing else changed — worth seven times the best grammar change, which did not
survive its control anyway.

`K` is people, and `cluster_people()` now raises the cluster count until `K`
groups are actually people rather than coughs; `--list` prints the `k` it
needed. Two segments of the same film needed k=4 and k=8. If it warns that
fewer than `K` voices clear the bar, sweep `k` yourself before believing
anything downstream:

```python
lab, _ = auto.cluster(E, k)      # one embedding pass, several k
```

A cluster that splits into two large shares as `k` rises was two people all
along (84.6% → 47.1% + 37.5%, and 82.4% → 42.4% + 39.6% on the other segment).

Then establish the baselines *before* reading any score:

- **always their most-used angle** — the do-nothing number to beat;
- **speaker-following at the right K** — what the tool does out of the box.

**Do not tune a grammar into the gap.** `--sweep --score` reads the answer;
whatever wins there is a hypothesis, and step 4 decides it.

## 4. The held-out segment decides (never skip it)

The second segment, never swept against. It builds **no tapes and renders
nothing**: three camera entries all pointing at the programme's own file,
anchors 0, a `sync` sidecar carrying only `fps`, and `--score` against that
segment's own shot list. Fifteen minutes — copy `projects/yt2-fpv33-val/`.

It exists because a metronome grammar fitted on the first segment scored 59.1%
there and **35.8%** on this one, while plain speaker-following held 49.5%.
Without the control that would have gone into a pitch as a result.

Two things the second segment routinely exposes: angle detection that split or
merged differently (merge two wide framings into one `camW` in a
`*.shots-merged.json`, and say you did), and a speaker hint that resolved to the
wrong voice.

## 5. Finishing, on their footage

Rebuild their edit, then put our graphics on it in the same pass — lower third,
end card, captions. Use a **separate manifest and output name**: burning
graphics changes pixels, so the finished file is no longer frame-comparable to
the programme.

Design the card from their own brand: a new `config/cards/brands/<channel>.json`
whose colours are **measured off their footage** (sample the set, take the 85th
percentile of the saturated pixels), never chosen by eye.

**Do not put a real person's name on a face you have not verified.** If their
film carries no name cards, label the show and leave `name_labels` for them.

## When the film is not multicam at all

The second channel audited published a **raw Zoom webinar**: a slide deck full
frame, the presenter pinned as a fixed 320×180 tile, Zoom's own nameplate burned
in, and **zero camera cuts in 51 minutes**. Stage 1 had no cut list to replay
and stage 2 had no angles to choose between, so the capability table *was* the
deliverable — and it was worth more than a score, because it said which of the
things they have not done we could do today (captions, chapters, glossary cards,
an end card, a dub) and which have no tooling at all (intro/outro animation,
music beds, removing the Zoom chrome, a composed vertical layout for shorts).

`shot-detect.py` refuses this now rather than inventing angles from slide
changes. When a film turns out to be single-camera, say so in one line and
spend the time on the table instead.

**Their most-published format is what matters, not the one you were handed.**
That channel's 68 videos are mostly solo talking heads; the workshop was an
outlier, and its raw Zoom folder is the ask that would unblock it. Check the
channel's shape before concluding anything about the channel.

## Traps this workflow has already paid for

- **A close-up does not mean that person is talking.** A channel that cuts to
  listening faces will send a speaker hint to the wrong voice. Take hint moments
  from `--list`'s own voice track, never from a long close-up in their edit.
- **The speaker model dies above 122.88 s** in one embedding. Handled in
  `embed_span()`; re-probe if a model is swapped.
- **A 1 cs caption-group overlap is a zero-length Whisper word**, not the timing
  knobs the refusal blames. Handled in `sanitize()`.
- **Camera numbering is per segment**, ordered by prevalence: `cam1` in one
  segment is not `cam1` in another. Map them from the sheets.
- **`silencedetect`'s absolute threshold is the wrong instrument** on a source
  whose speech level you have not measured. A webinar returned zero gaps at
  −30, −35 and −40 dB; its floor sat at −56.6 dB and its speech at −21.7 dB, so
  the pauses never reached any of those. Threshold an RMS envelope *relative* to
  the film's own speech level instead.
- **The GPU is shared.** Check `python scripts/render-status.py` before starting
  an encode if another session may be rendering.

## What to report

Lead with what we can and cannot produce, never with a percentage. Then:

- the frame-exact result, or its failure;
- the stage-2 score, its held-out score and the do-nothing baseline, together;
- the capability table with the gaps marked;
- absolute paths of the artifacts that are actually watchable;
- and the ask: **one episode's real camera cards**, the only thing that turns
  this into a film they can watch.
