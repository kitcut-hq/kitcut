#!/usr/bin/env python
"""What is rendering right now, and how far along it is.

Reads the files `_progress.py` publishes and prints one line per live render:

    claude-demo ██████░░░░  61%  4:34/7:30  1.4x  eta 2:07

This WAS the Claude Code status line, and mixing render progress into the
prompt turned out to be a mistake -- the status line belongs to the session
(see statusline.py). It survives as a hand-run watch tool; nothing else shows
a running encode's position.

Still stdlib-only with no `_env` import: it needs nothing from the venv, and
staying dependency-free keeps a hand-run instant.

Invoke as:  python scripts/render-status.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _progress

# Windows hands a child process cp1252, which cannot encode the bar (U+2588 /
# U+2591) at all -- the line would die on a UnicodeEncodeError and the status
# line would go blank. Measured, not assumed: sys.stdout.encoding is 'cp1252'
# here even though the terminal renders UTF-8 fine.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def main():
    jobs = []
    try:
        jobs = [j for j in _progress.read() if not j.get("finished")]
    except Exception:
        pass
    if not jobs:
        print("nothing rendering")
        return
    for j in jobs:
        print(_progress.describe(j))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # never blank the status line
        print("render-status: %s" % e)
