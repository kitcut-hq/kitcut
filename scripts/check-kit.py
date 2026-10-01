#!/usr/bin/env python
"""Self-test sketch/kit.js, the pieces every studio film is given.

Two things go wrong with a library nobody renders:

  Its header is what Claude reads (the studio puts only the header in the system prompt), so a
  piece the header names and the code no longer defines is a film that throws on its first frame,
  after the narration and the paintings were already paid for.

  A piece that draws fine on the clean look can throw or vanish on crayon, where it draws with the
  pen instead (and collage, where it enters on twos). The gallery film shows every piece in both.

So: every SK.* the header names is defined in the code, the studio prompt carries the header and
not the code, and the gallery (config/sketch/kit-example) renders a page of each group in both
looks with no page error. --sheet keeps the contact sheet to look at (outputs/review/sheet.png).
About 15 s, headless Edge, no GPU, no API.

Invoke as:  python scripts/check-kit.py [--sheet]
"""

import argparse
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import

KIT = os.path.join(_env.ROOT, "sketch", "kit.js")
GALLERY = os.path.join(_env.ROOT, "config", "sketch", "kit-example", "sketch.json")
# a page of each group (the gallery's 3 s pages), clean then crayon
TIMES = [
    2.6,
    5.6,
    8.6,
    11.6,
    14.6,
    17.6,
    20.6,
    23.6,
    26.6,
    29.6,
    32.6,
    35.6,
    38.6,
    41.6,
    44.6,
    47.6,
]

fails = []


def check(name, ok, detail=""):
    print("%s  %s%s" % ("ok  " if ok else "FAIL", name, "" if ok else "  -- " + str(detail)))
    if not ok:
        fails.append(name)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--sheet", action="store_true", help="keep the gallery's contact sheet")
    args = ap.parse_args()

    src = open(KIT, encoding="utf-8").read()
    header, code = src.split("*/", 1)
    named = set(re.findall(r"\bSK\.([A-Za-z]\w*)\s*\(", header))
    defined = set(re.findall(r"\bSK\.([A-Za-z]\w*)\s*=", code)) | set(
        re.findall(
            r"\bSK\.([A-Za-z]\w*)\s*=",
            open(os.path.join(_env.ROOT, "sketch", "engine.js"), encoding="utf-8").read(),
        )
    )
    check("every piece the header names is defined", named <= defined, sorted(named - defined))
    paths = set(re.findall(r"\bS\.(len|at|cut)\(", header))
    check("the path helpers it names are defined", all("S.%s = " % p in code for p in paths), paths)

    sys.path.insert(0, os.path.join(_env.ROOT, "studio"))
    agent = __import__("agent")
    for look in ("drawn", "painted", "collage"):
        p = agent.system_prompt(look)
        check(
            "%s: the prompt carries the kit's header, not its code" % look,
            "Reference: the kit" in p
            and "SK.cues({name" in p
            and "function place(o, w, h, fn)" not in p,
        )
    film = __import__("film")
    check(
        "every look's recipe starts with the kit",
        all(r[0] == "kit" for r in film.RECIPES.values()),
        film.RECIPES,
    )

    r = subprocess.run(
        [
            *_env.PY,
            os.path.join(_env.ROOT, "scripts", "sketch-render.py"),
            "--manifest",
            GALLERY,
            "--stills",
            ",".join("%g" % t for t in TIMES),
            "--sheet",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    out = r.stdout + r.stderr
    check(
        "the gallery renders every page, clean and crayon, with no page error",
        r.returncode == 0 and "page error" not in out,
        out[-1500:],
    )
    review = os.path.join(os.path.dirname(GALLERY), "outputs", "review")
    if args.sheet:
        print("sheet:", os.path.join(review, "sheet.png"))

    print("\nall passed" if not fails else "\n%d failed" % len(fails))
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
