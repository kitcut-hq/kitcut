#!/usr/bin/env python
"""The Claude Code status line for this repo: what is rendering, and how far.

Wired up in `.claude/settings.json`, so it applies to every session opened in
this folder and to none opened anywhere else. Claude Code hands it a JSON blob
on stdin and prints the first line of stdout under the prompt.

With nothing rendering it shows the ordinary things -- model, folder, branch.
With a render running it appends that render's position, read from the files
`_progress.py` publishes:

    claude-demo ██████░░░░  61%  4:34/7:30  1.4x  eta 2:07

Two rules this file follows, both because of where it runs:

  * **stdlib only, and no `_env` import.** It is re-run on every status-line
    refresh; the repo's usual re-exec into `.venv` would spawn a subprocess each
    time. Nothing here needs a third-party package.
  * **it never fails.** Any exception would blank the status line with no
    explanation, so the whole body is guarded and the fallback still prints
    something useful.
"""
import sys, os, json, subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _progress

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Windows hands a child process cp1252, which cannot encode the bar (U+2588 /
# U+2591) at all -- the line would die on a UnicodeEncodeError and the status
# line would go blank. Measured, not assumed: sys.stdout.encoding is 'cp1252'
# here even though the terminal renders UTF-8 fine.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def git_branch():
    try:
        p = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                           cwd=ROOT, capture_output=True, text=True, timeout=2)
        return p.stdout.strip() if p.returncode == 0 else ""
    except Exception:
        return ""


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}

    left = []
    model = (payload.get("model") or {}).get("display_name")
    if model:
        left.append(model)
    cwd = (payload.get("workspace") or {}).get("current_dir") or payload.get("cwd")
    if cwd:
        left.append(os.path.basename(cwd.rstrip("\\/")) or cwd)
    branch = git_branch()
    if branch:
        left.append(branch)

    jobs = []
    try:
        jobs = [j for j in _progress.read() if not j.get("finished")]
    except Exception:
        pass

    if not jobs:
        print(" · ".join(left))
        return

    # One render is the normal case; if several are somehow live, show the
    # newest and say how many others there are rather than wrapping the line.
    line = _progress.describe(jobs[0])
    if len(jobs) > 1:
        line += "  +%d more" % (len(jobs) - 1)
    print(" · ".join(left + [line]) if left else line)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:                     # never blank the status line
        print("render-status: %s" % e)
