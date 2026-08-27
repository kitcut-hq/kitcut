---
name: video-project
description: Change something about a video that has already been edited or published with this repo's pipelines — move or restyle a name label, fix a dub line, recut with more or less dead air, restyle captions, change a crop, update a description or chapters, or answer "what is on this video". Reads projects/<id>/project.json to learn what every render contains and which manifest key controls it, routes the change to the owning pipeline, re-renders, and records the result. Use when asked to modify, fix, update, re-edit, regenerate or explain an existing video, or when a request names a rendered/uploaded file rather than raw footage.
---

# Re-editing a video the repo has already made

A finished render is not the end of a project; it is a state the project was
in. Everything about one video lives in `projects/<id>/` — the manifests that
made it, `project.json` (current state), `journal.md` (history addressed to
you). This skill is the entry point when the user wants that state changed.

The one rule: **never start from the mp4.** Start from the metadata, find the
control that owns the thing being changed, change the control, re-render
through the owning pipeline. Re-encoding a finished file is the fallback for
lost sources only — it costs a generation (see the name-label skill's warning).

## Order of work

1. **Identify the project.** From the ask's id or slug; from an output
   filename by matching `deliverables` keys (`python scripts/project-scan.py
   --all` lists projects). If nothing matches, the video may predate the
   convention — scan the legacy dirs, then `--init` a project for it.
2. **Read `project.json`.** The `current` deliverable of the relevant kind is
   the thing being changed; its `burned` list says what is on it, `controls`
   says which file to edit, `published` says whether an audience already has
   it. Then skim `journal.md` — the change being asked for may have been
   considered, made, or deliberately not made before.
3. **Route the ask** (the table below), edit the control, and **price the
   change before encoding** — every pipeline has a free mode (`--list`,
   `--plan-only`, `--frame`, `--dry-run`). A placement or plan check costs
   nothing; a wrong encode costs minutes and a second generation.
4. **Re-render via the owning pipeline's skill.** The finishing script records
   the new render into `project.json` and stamps `journal.md` itself.
5. **Settle the aftermath.** Mark the replaced render `superseded` with a
   `_why` (scripts never demote — that is editorial, yours). If the old render
   was published, decide with the user: upload the new file (new URL) or leave
   the old one; record the decision. Run `python scripts/project-scan.py --id
   <id> --check` — it must come back clean or say exactly the true thing.
6. **Close the journal.** A short prose note: what was asked, which knob
   changed, why, anything the next session should not rediscover.

## Routing table: what the user says → what you edit

| the ask | the control | knob and caveat |
|---|---|---|
| move/reword a name label | `screencast.json` → `name_labels[]` | `at` is **film time** (after the pause cut, not camera time). Prove placement free with `name-label.py --frame T` before any encode |
| restyle the label | `config/labels/lower-third.json` | shared styling — changing it changes every future label; a one-off variant belongs in the manifest entry |
| caption style/colour/size | the preset under `controls.caption-style` | style values were measured, not chosen (`_measured` block); re-verify with the captions pipeline's verify stage, not by eye |
| cut more / less dead air | `screencast.json` → `cut.min_silence` etc. | **sweep with `--list`, do not pick** — price 3-4 settings first. Editing one decision: edit the keep-list `<id>.cuts.json` and re-run with `--cuts` |
| film starts/ends wrong | `screencast.json` → `film.start_text` / `end_text` (+ `start_pad`/`end_pad`) | quote what is said, and read the picture before trusting the transcript |
| fix a dub line | the `.translation.json` under the dub deliverable's `sidecars` | re-run `dub-clips.py` with `--engine manual --translation <file>`, or a fresh `--tag` to keep both. A cached translation is fingerprinted to its plan — changing `--max-dur`/engine refuses stale reuse |
| different dub voice | `--tts` / `--voice` (+ `config/elevenlabs-voices.json`) | a tag holds ONE backend/voice; use a distinct `--tag`, never `--force`, to keep the old one |
| reframe/crop a short | `clips-vertical.reframe.json` | that file exists to be edited; keys are `[time, centre_x]` pairs |
| clip boundaries wrong | `clips*.json` → the clip's `start_text`/`end_text` | re-running the manifest rebuilds only entries whose output is missing; `--only <id> --force` for the one you changed |
| handle badge text/style | `clips*.json` → `handle`, `config/handles/*.json` | manifest for the text, config for the look |
| move/replace an end card or image overlay | the manifest's `image_overlays[]` | `at` is film time and **negative counts back from the end**, which is what keeps a card attached to the ending through a re-cut. Prove placement free with `image-overlay.py --frame T` |
| restyle an end card | the page under `controls.overlay-*`, or `config/overlays/end-card.json` | the HTML in `projects/<id>/assets/` is the editable control — edit it and re-render; the PNG in `temp/` regenerates from it. The preset holds animation/treatment defaults shared by every future card |
| description / chapters | `description.txt` / `chapters.txt` + `yt-set-chapters.py` | chapters edit the LIVE description; `--dry-run` first |
| "what is on this video?" | nothing — read `project.json` | answer from `burned`, `published`, and the journal; do not re-derive from the files |

If the ask fits no row, that is not a dead end — it is a missing knob. Add the
knob: a manifest key, script support behind it, a README paragraph, a row in
this table. The scripts are an SDK you maintain, not a fixed appliance (see
`## House rules` in CLAUDE.md). A change is done when the code, the metadata
writer, the README and the skill all say the same thing.

## Worked example: "move the name label 2 seconds later"

1. `projects/claude-demo/project.json` → the `current` screencast deliverable;
   `burned` shows the label at 2.0s; `controls.manifest` is
   `projects/claude-demo/screencast.json`.
2. `journal.md` says the label must be gone before the b-roll cut at ~8.2s of
   film time — so 4.0 + 5.5s duration still fits, barely; check it.
3. Edit `name_labels[0].at` from `2.0` to `4.0`.
4. Free placement proof: `python scripts/name-label.py --frame 4.0 --video
   projects/claude-demo/outputs/claude-demo.mp4 --labels ...` → look at the PNG.
5. `python scripts/screencast-cut.py --manifest
   projects/claude-demo/screencast.json` — the render records itself.
6. Mark the old deliverable `superseded` (with `_why`), decide re-upload with
   the user, run `project-scan.py --id claude-demo --check`, write the journal
   note.

## Traps

- **A label past the end of the film fails silently** — `enable` never fires.
  `screencast-cut.py` asserts the runtime against every label; keep it that way.
- **`at` moved by the cut.** Film time ≠ camera time; every pause removed
  before the label's moment shifts it. The `--frame` check exists because
  arithmetic here has been wrong before.
- **Do not measure leftover silence on a rendered film** — `loudnorm` lifted
  the room tone; measure the source and intersect with the keep-list.
- **Superseded ≠ deletable.** A first-generation render beats relabelling a
  second-generation file; keep the lineage in `_why` so the next session knows
  which file to regenerate from.
- **`--check` says STALE after any manifest edit** — that is the point. Either
  the render is genuinely behind the manifest (re-render) or the edit was
  non-material (set `checked_utc` on the deliverable, say why).
