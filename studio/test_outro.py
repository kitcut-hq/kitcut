#!/usr/bin/env python
"""The Free plan's mark and closing (outro.js) draw the same whatever the film left the canvas
set to: the repo's example film with the closing as its tail, drawn by headless Edge/Chrome twice
-- as it is, and as a right-to-left film (a Persian one sets the canvas `direction = 'rtl'` and
leaves it). No model and no network. About twenty seconds, all of it the browser.

    python studio/test_outro.py

On foeqt6 (2026-10-05) the mark read "m adew ih / k i'cu ta i" and the closing "M ake your awn
fih": SK.txt places each letter from its left edge, and on a right-to-left canvas a letter is
drawn from its right. Covers: the mark's corner (film.MARK_BOX) is the same picture both ways and
has ink in it; so is the closing's side of the frame.
"""

import os
import sys
import json
import shutil
import subprocess
import tempfile

HOME = tempfile.mkdtemp(prefix="studio-outro-test-")
os.environ["STUDIO_HOME"] = HOME
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "scripts"))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import
import agent  # noqa: E402
import film as films  # noqa: E402

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

EXAMPLE = os.path.join(_env.ROOT, "config", "sketch", "example")
# what a right-to-left film does in its draw, and leaves behind for whatever draws after it
RTL = """(function () {
  const F = SK._film; if (!F) return;
  const draw = F.draw;
  F.draw = (t, vis) => {
    draw(t, vis); const c = SK.ctx(); c.direction = 'rtl'; c.textAlign = 'right';
  };
})();
"""


def stills(name, rtl):
    """The example film with the closing, as a studio film: a still of the mark, one of its end."""
    d = os.path.join(HOME, "projects", "studio-20261005-120000-" + name)
    os.makedirs(d)
    shutil.copyfile(os.path.join(EXAMPLE, "film.js"), os.path.join(d, "film.js"))
    with open(os.path.join(EXAMPLE, "sketch.json"), encoding="utf-8") as f:
        m = json.load(f)
    m["slug"] = "film"
    with open(os.path.join(d, "sketch.json"), "w", encoding="utf-8") as f:
        json.dump(m, f, indent=1)
    f = films.Film(d)
    missing = agent.brand(f)
    assert not missing, missing
    with open(f.manifest, encoding="utf-8") as fh:
        m = json.load(fh)
    if rtl:
        with open(f.path("temp", "brand", "rtl.js"), "w", encoding="utf-8") as fh:
            fh.write(RTL)
        m["tail"]["scripts"].insert(0, "temp/brand/rtl.js")
        with open(f.manifest, "w", encoding="utf-8") as fh:
            json.dump(m, fh, indent=1)
    times = [2.0, float(m["duration"]) + agent.CLOSING_S - 0.2]
    r = subprocess.run(
        [
            *_env.PY,
            os.path.join(_env.ROOT, "scripts", "sketch-render.py"),
            "--manifest",
            f.manifest,
            "--stills",
            ",".join("%g" % t for t in times),
            "--into",
            "shots",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert r.returncode == 0 and "page error" not in r.stdout + r.stderr, (r.stdout + r.stderr)[
        -1500:
    ]
    names = sorted(os.listdir(f.path("shots")))
    return [np.asarray(Image.open(f.path("shots", n)).convert("RGB"), dtype="int16") for n in names]


def main():
    bad = []

    def check(ok, what, detail=""):
        print("%s  %s%s" % ("ok  " if ok else "FAIL", what, "" if ok else "  -- %s" % (detail,)))
        if not ok:
            bad.append(what)

    try:
        (mark, close), (mark_r, close_r) = stills("ltr", False), stills("rtl", True)
        h, w = mark.shape[:2]
        x0, y0, x1, y1 = (round(v * w / 1920) for v in films.MARK_BOX)
        a, b = mark[y0:y1, x0:x1], mark_r[y0:y1, x0:x1]
        white = float((a.min(axis=2) > 205).mean())
        check(white > 0.01, "the mark is in its corner", "white ink: %.3f of the box" % white)
        diff = float((abs(a - b).max(axis=2) > 24).mean())
        check(diff < 0.002, "the mark reads the same on a right-to-left film", "%.4f differ" % diff)
        a, b = close[:, int(w * 0.56) :], close_r[:, int(w * 0.56) :]
        diff = float((abs(a - b).max(axis=2) > 24).mean())
        check(diff < 0.002, "so does the closing", "%.4f of its side differ" % diff)
    finally:
        shutil.rmtree(HOME, ignore_errors=True)
    print("\nall passed" if not bad else "\n%d failed" % len(bad))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
