---
name: check-script
description: Verify that a new or modified script in scripts/ follows this repo's conventions before it gets trusted or committed — the _env bootstrap, a docstring with Invoke as, a free mode that prices decisions, _project.record() on deliverables, no os.execve, docs in sync. Runs the mechanical checker (scripts/check-script.py) and then walks the judgement checks a grep cannot do. Use after writing or changing any script, before committing tooling, or when asked whether a script follows the repo's format or conventions.
---

# Checking a script against the house conventions

Every script here is written by the AI and called by the AI; nobody else will
ever notice a convention quietly skipped. A script that works but doesn't
follow the format is a trap deferred: it runs on the wrong interpreter one
day, or renders something no project file remembers, or costs an encode that
a `--list` mode would have priced for free. This check is how tooling earns
its way into a commit.

## 1. The mechanical half — run the checker

```powershell
python scripts/check-script.py --changed    # everything git sees as new/modified
python scripts/check-script.py --all        # the whole corpus (calibration)
python scripts/check-script.py scripts/x.py # one file
```

It enforces (FAIL, exit 1): a module docstring; `import _env` before any
third-party import; no `os.execve`; no writing `PYTHONPATH`; no absolute
machine path in a string literal; and the platform boundary (below). It flags
(warn): no `Invoke as:` line, no argparse, a script that encodes or spends with
no free mode, a deliverable-producer that never calls `_project.record()`,
backslash path literals, and a script the README does not mention.

`--all` additionally scans every `SKILL.md`, the README and CLAUDE.md for
absolute paths, because a skill is read by an agent on a machine that is not
this one — the repo shipped ten `cd C:\...` lines that way before this check
existed.

### The platform boundary

Eight files are **platform, not video** — `_env.py`, `_progress.py`,
`_project.py`, `check-env.py`, `check-script.py`, `project-scan.py`,
`render-status.py`, `statusline.py`. None of them may import anything from this
repo that is not also on that list. Third-party imports are fine; a dependency
on the *video pipeline* is not, because it turns "lift the platform out" from a
move into a rewrite. The set lives in `PLATFORM` in the checker.

Three of them — `_progress.py`, `render-status.py`, `statusline.py` — go
further and must be **stdlib-only**: they run on every status-line refresh or
as a watch tool that has to start instantly, and anything needing the venv
would re-exec a subprocess each time.

Adding a script to `PLATFORM` is a claim that it knows nothing about video.
Make the claim deliberately; the checker will hold you to it.

**The corpus passes clean — keep it that way.** `--all` is the calibration
run: if your change makes another script warn, either your change or the
checker's rules are wrong, and you find out which before committing.

## 2. Waivers are decisions, not escapes

A script that deliberately breaks a rule gets an entry in `EXCEPTIONS` inside
`scripts/check-script.py` **with the reason** — the checker prints the reason
as a `note` on every run, so the exception stays visible instead of becoming
a blind spot. Existing examples to copy the tone of: `render-status.py` must
NOT import `_env` (a re-exec per status refresh would spawn a subprocess every
second); `name-label.py`'s standalone burn doesn't record because it is the
lost-source fallback and the pipeline path records. Never waive without a
reason, and never delete a check to silence it.

## 3. The judgement half — what a grep cannot verify

Walk these by reading the script, not by pattern-matching:

- **Does the free mode actually price the decision?** `--list` that prints a
  filename is compliance theater; the standard is `cut-clips.py --list`
  pricing boundaries or `screencast-cut.py --list` pricing a threshold sweep
  without one encoded frame.
- **Does `record()` fire at the right moment?** After the output is moved
  into place — after the duration/rotation/audio assertions, never before.
  A record of a render that failed its own checks is worse than no record.
  And `--list`/`--plan`/`--dry-run` paths must record nothing (proven for the
  existing scripts by smoke test; keep it true).
- **Is every visual or editorial value in a manifest or config?** No hex
  colour, px size, timecode or phrase hardcoded — a DEFAULT_* dict the
  manifest overrides is the accepted pattern.
- **Does it verify before spending?** An assertion on the output (duration,
  dimensions, rotation, audio peak) is what caught a 463s render of a 55s
  clip and a silent film. New encode paths need an equivalent.
- **Do the docs say what the code does?** The SDK contract: a tooling change
  is not done until the README section, the affected skill, and (if it makes
  deliverables) `_project.record()` agree with the code. Touching `dub-*.py`
  also means running `python scripts/check-dub.py`.
- **Are new traps recorded with their reason** in the README `## Gotchas`,
  not just fixed?

## 4. When a new convention appears

The checker is itself part of the SDK. When a convention is added or changed
— a new required call, a renamed helper, a new rule in CLAUDE.md — extend
`check-script.py` in the same change, then run `--all`: the corpus is the
test suite for the rule. A convention the checker cannot see will drift; the
project-file convention is enforceable precisely because `record()` is a
grep-able call.
