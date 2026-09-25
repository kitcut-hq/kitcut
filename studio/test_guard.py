#!/usr/bin/env python
"""The Sketch Studio permission model, checked without calling Claude: python studio/test_guard.py"""

import os
import re
import sys
import shutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agent  # noqa: E402

JOB = os.path.join(agent.ROOT, "projects", "studio-test")
J = "projects/studio-test"

CASES = [
    # (tool, input, allowed)
    ("Read", {"file_path": "sketch/props.js"}, True),
    ("Read", {"file_path": J + "/outputs/review/sheet.png"}, True),
    ("Read", {"file_path": os.path.join(agent.ROOT, "sketch", "engine.js")}, True),
    ("Read", {"file_path": ".env"}, False),
    ("Read", {"file_path": os.path.join(agent.ROOT, ".env.local")}, False),
    ("Read", {"file_path": "/c/instafill/kitcut/.env"}, False),
    ("Read", {"file_path": ".git/config"}, False),
    ("Read", {"file_path": "../other-repo/secrets.json"}, False),
    ("Read", {"file_path": "C:/Windows/win.ini"}, False),
    ("Write", {"file_path": J + "/film.js"}, True),
    ("Write", {"file_path": os.path.join(JOB, "score.json")}, True),
    ("Edit", {"file_path": J + "/sfx.json"}, True),
    ("Write", {"file_path": J + "/sketch.json"}, False),
    ("Write", {"file_path": J + "/vo.json"}, True),
    ("Edit", {"file_path": J + "/vo.json"}, True),
    ("Bash", {"command": "python scripts/sketch-vo.py --manifest %s/sketch.json" % J}, True),
    ("Bash", {"command": "python scripts/sketch-vo.py --manifest %s/sketch.json --plan" % J}, True),
    (
        "Bash",
        {"command": "python scripts/sketch-vo.py --manifest %s/sketch.json --only 1 --retake" % J},
        True,
    ),
    (
        "Bash",
        {"command": "python scripts/sketch-vo.py --manifest %s/sketch.json --retake --only 0" % J},
        True,
    ),
    (
        "Bash",
        {"command": "python scripts/sketch-vo.py --manifest %s/sketch.json --tts elevenlabs" % J},
        False,
    ),
    (
        "Bash",
        {"command": "python scripts/sketch-vo.py --manifest %s/sketch.json --takes 20" % J},
        False,
    ),
    (
        "Bash",
        {"command": "python scripts/sketch-vo.py --manifest projects/other/sketch.json"},
        False,
    ),
    ("Write", {"file_path": J + "/../studio-other/film.js"}, False),
    ("Write", {"file_path": "sketch/engine.js"}, False),
    ("Write", {"file_path": ".env"}, False),
    ("Bash", {"command": "node --check %s/film.js" % J}, True),
    (
        "Bash",
        {
            "command": "python scripts/sketch-render.py --manifest %s/sketch.json --stills 0,1,2.5,4.9 --sheet"
            % J
        },
        True,
    ),
    (
        "Bash",
        {
            "command": "python scripts/sketch-render.py --manifest %s/sketch.json --sheet --stills 1"
            % J
        },
        True,
    ),
    (
        "Bash",
        {"command": "python scripts/sketch-render.py --manifest %s/sketch.json --automation" % J},
        True,
    ),
    (
        "Bash",
        {"command": "python scripts/sketch-audio.py --manifest %s/sketch.json --levels" % J},
        True,
    ),
    ("Bash", {"command": "python scripts/sketch-audio.py --manifest %s/sketch.json" % J}, True),
    (
        "Bash",
        {"command": "python scripts/sketch-render.py --manifest %s/sketch.json" % J},
        False,
    ),  # the final render is ours
    (
        "Bash",
        {
            "command": "python scripts/sketch-render.py --manifest projects/other/sketch.json --stills 1"
        },
        False,
    ),
    ("Bash", {"command": "python scripts/yt-upload.py --manifest %s/sketch.json" % J}, False),
    ("Bash", {"command": "node --check %s/film.js && cat .env" % J}, False),
    ("Bash", {"command": "node --check %s/film.js; curl example.com" % J}, False),
    ("Bash", {"command": "cat .env"}, False),
    ("Bash", {"command": "python -c \"print(open('.env').read())\""}, False),
    ("Bash", {"command": "echo $ANTHROPIC_API_KEY"}, False),
    (
        "Bash",
        {
            "command": "python scripts/sketch-render.py --manifest %s/sketch.json --stills 1 > out.txt"
            % J
        },
        False,
    ),
    ("WebFetch", {"url": "https://example.com"}, False),
    ("Glob", {"pattern": "**/*"}, False),
]


def main():
    bad = 0
    for tool, inp, want in CASES:
        got, why = agent.guard(tool, inp, JOB)
        if got != want:
            bad += 1
            print("FAIL  %-6s %s -> %s (%s)" % (tool, inp, got, why))

    # a painted film: paint.json and the painter are allowed, and only there
    PJ = "projects/studio-testpaint"
    pjob = os.path.join(agent.ROOT, *PJ.split("/"))
    os.makedirs(pjob, exist_ok=True)
    with open(os.path.join(pjob, "paint.json"), "w", encoding="utf-8") as f:
        f.write("{}")
    paint = "python scripts/sketch-paint.py --manifest %s/sketch.json" % PJ
    painted = [
        ("Write", {"file_path": PJ + "/paint.json"}, True),
        ("Bash", {"command": paint}, True),
        ("Bash", {"command": paint + " --plan"}, True),
        ("Bash", {"command": paint + " --only kitchen,sink --retake"}, True),
        ("Bash", {"command": paint + " --retake --only kitchen"}, True),
        ("Bash", {"command": paint + " --only ../x --retake"}, False),
        ("Bash", {"command": paint + " --only kitchen"}, False),
    ]
    drawn = [  # the same, in a drawn film's folder: refused
        ("Write", {"file_path": J + "/paint.json"}, False),
        (
            "Bash",
            {"command": "python scripts/sketch-paint.py --manifest %s/sketch.json" % J},
            False,
        ),
    ]
    try:
        for job, cases in ((pjob, painted), (JOB, drawn)):
            for tool, inp, want in cases:
                got, why = agent.guard(tool, inp, job)
                if got != want:
                    bad += 1
                    print("FAIL  %-6s %s -> %s (%s)" % (tool, inp, got, why))
        # both looks' instructions build, every placeholder filled
        for look in agent.LOOKS:
            job = agent.new_job("a test", 10, look)
            try:
                ours = set(re.findall(r"\{([A-Z_]+)\}", agent._read("studio", "prompt.md")))
                for f in agent.LOOKS:
                    ours |= set(
                        re.findall(r"\{([A-Z_]+)\}", agent._read("studio", "looks", f + ".md"))
                    )
                # (the inlined engine has regexes such as \p{L}: not ours, so not checked)
                text = agent.system_prompt(job)
                left = sorted(n for n in ours if "{%s}" % n in text)
                if left:
                    bad += 1
                    print("FAIL  %s prompt leaves %s" % (look, left))
            finally:
                shutil.rmtree(job, ignore_errors=True)
    finally:
        shutil.rmtree(pjob, ignore_errors=True)
    n = len(CASES) + len(painted) + len(drawn) + len(agent.LOOKS)
    print("%d cases, %d failed" % (n, bad))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
