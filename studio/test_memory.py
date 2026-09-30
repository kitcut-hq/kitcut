#!/usr/bin/env python
"""What a long-running studio process may hold, and what a job beside the live server may take:
no browser, no network, seconds.

    python studio/test_memory.py

The lesson of KI-045: `share.py --missing` ran 55 films' thumbnails in one process, `_thumb.py`
kept every decoded still it ever opened (2,196 of them, 13.7 GB), and the films being made on the
same VM could not start Claude. Covers: the still cache stays under THUMB_STILLS_MB however many
films pass through it, hands back the same picture while it is cached and reads it again once it
is not; and every `systemd-run` in the deploy scripts is capped (MemoryMax) or says on the line
above why it is not ("# memory: uncapped -- <why>"), so the next batch job cannot be started
without a limit by accident.
"""

import os
import re
import sys
import glob
import shutil
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
os.environ["THUMB_STILLS_MB"] = "20"  # before _thumb reads it
sys.path.insert(0, os.path.join(REPO, "scripts"))
import _thumb  # noqa: E402 -- imports _env first
from PIL import Image  # noqa: E402

bad = []


def check(ok, what, got=None):
    print("%s  %s%s" % ("ok   " if ok else "FAIL ", what, "" if ok else "  -- %r" % (got,)))
    if not ok:
        bad.append(what)


def stills_stay_capped():
    d = tempfile.mkdtemp(prefix="studio-memory-test-")
    try:
        paths = []
        for i in range(40):  # 40 stills of 1280x720: 110 MB decoded, the cap is 20
            p = os.path.join(d, "%03d.png" % i)
            Image.new("RGB", (1280, 720), (i, 0, 0)).save(p, compress_level=0)
            paths.append(p)
        for p in paths:
            _thumb.load_still(p)
        held = sum(n for _, n in _thumb._STILLS.values())
        check(held <= 20_000_000, "40 stills held under THUMB_STILLS_MB=20", held)
        check(len(_thumb._STILLS) >= 2, "the newest stay cached", len(_thumb._STILLS))
        last = paths[-1]
        check(
            _thumb.load_still(last) is _thumb.load_still(last), "a cached still is the same picture"
        )
        check(paths[0] not in _thumb._STILLS, "the least recently used went first")
        check(
            _thumb.load_still(paths[0]).getpixel((0, 0)) == (0, 0, 0),
            "and is read again when asked",
        )
        big = os.path.join(d, "big.png")
        Image.new("RGB", (3000, 3000)).save(big, compress_level=0)  # 27 MB alone, over the cap
        check(
            _thumb.load_still(big).size == (3000, 3000), "a still bigger than the cap still loads"
        )
        check(len(_thumb._STILLS) == 1, "and is the only one kept", len(_thumb._STILLS))
    finally:
        _thumb._STILLS.clear()
        shutil.rmtree(d, ignore_errors=True)


def jobs_are_capped():
    scripts = sorted(
        glob.glob(os.path.join(HERE, "deploy", "*.sh")) + glob.glob(os.path.join(HERE, "*.sh"))
    )
    seen = 0
    for path in scripts:
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
        for i, line in enumerate(lines):
            if "systemd-run" not in line or line.lstrip().startswith("#"):
                continue
            seen += 1
            where = "%s:%d" % (os.path.relpath(path, REPO), i + 1)
            above = "\n".join(lines[max(0, i - 3) : i])
            capped = re.search(r"-p MemoryMax=\d", line)
            excused = re.search(r"# memory: uncapped -- \S", above)
            check(
                bool(capped or excused),
                "%s: systemd-run is capped (MemoryMax) or says why not" % where,
                line.strip()[:120],
            )
    check(seen >= 3, "the deploy scripts' jobs were found (share, resume, migrate)", seen)


if __name__ == "__main__":
    stills_stay_capped()
    jobs_are_capped()
    print("\n%d failed" % len(bad) if bad else "\nall passed")
    sys.exit(1 if bad else 0)
