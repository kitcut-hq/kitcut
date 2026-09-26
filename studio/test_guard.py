#!/usr/bin/env python
"""The Sketch Studio permission model, checked without calling Claude: python studio/test_guard.py

Two films side by side in a throwaway STUDIO_HOME: what one may read, write and call, and that
nothing reaches the other film, the studio's own files or the code's .env.
"""

import os
import re
import sys
import json
import shutil
import tempfile
import subprocess

HOME = tempfile.mkdtemp(prefix="studio-test-")
os.environ["STUDIO_HOME"] = HOME
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agent  # noqa: E402
import film as films  # noqa: E402
from guard import guard, pin_after  # noqa: E402


def main():
    bad = []

    def expect(what, got, want):
        if got != want:
            bad.append(what)
            print("FAIL  %s -> %s" % (what, got))

    try:
        A = films.Film.create("a drawn test", 5, "drawn")
        B = films.Film.create("a painted test", 10, "painted")
        kit_env = os.path.join(films.KIT, ".env")
        rel_b = os.path.relpath(B.dir, A.dir).replace("\\", "/")
        cases = [
            # (tool, input, allowed) -- all for film A
            ("Read", {"file_path": "film.js"}, True),
            ("Read", {"file_path": "outputs/review/sheet.png"}, True),
            ("Read", {"file_path": "audio/vo/timeline.json"}, True),
            ("Read", {"file_path": "engine/props.js"}, True),
            ("Read", {"file_path": A.path("sketch.json")}, True),
            ("Read", {"file_path": rel_b + "/film.js"}, False),
            ("Read", {"file_path": B.path("vo.json")}, False),
            ("Read", {"file_path": "temp/system-prompt.md"}, False),
            ("Read", {"file_path": "studio.json"}, False),
            ("Read", {"file_path": "events.jsonl"}, False),
            ("Read", {"file_path": ".."}, False),
            ("Read", {"file_path": kit_env}, False),
            ("Read", {"file_path": os.path.join(films.KIT, "sketch", "engine.js")}, False),
            ("Read", {"file_path": "/c/instafill/kitcut/.env"}, False),
            ("Read", {"file_path": "C:/Windows/win.ini"}, False),
            ("Read", {"file_path": os.path.join(HOME, "claude", A.id, ".claude.json")}, False),
            ("Write", {"file_path": "film.js"}, True),
            ("Write", {"file_path": A.path("score.json")}, True),
            ("Edit", {"file_path": "sfx.json"}, True),
            ("Edit", {"file_path": "vo.json"}, True),
            ("Edit", {"file_path": "engine/props.js"}, True),
            ("Write", {"file_path": "engine/engine.js"}, True),
            ("Write", {"file_path": "engine/extra.js"}, False),
            ("Write", {"file_path": "sketch.json"}, False),
            ("Write", {"file_path": "studio.json"}, False),
            ("Write", {"file_path": "paint.json"}, False),  # a drawn film has no paintings
            ("Write", {"file_path": "outputs/film.mp4"}, False),
            ("Write", {"file_path": rel_b + "/film.js"}, False),
            ("Write", {"file_path": os.path.join(films.KIT, "sketch", "engine.js")}, False),
            ("Write", {"file_path": kit_env}, False),
            ("mcp__studio__stills", {"times": [0, 1]}, True),
            ("mcp__studio__voice", {}, True),
            ("mcp__other__anything", {}, False),
            ("Bash", {"command": "node --check film.js"}, False),
            ("Glob", {"pattern": "**/*"}, False),
            ("Grep", {"pattern": "KEY"}, False),
            ("WebFetch", {"url": "https://example.com"}, False),
            ("Task", {"prompt": "x"}, False),
        ]
        for tool, inp, want in cases:
            expect("%s %s" % (tool, inp), guard(tool, inp, A)[0], want)
        # a painted film: its paint.json is its own
        expect("painted: Write paint.json", guard("Write", {"file_path": "paint.json"}, B)[0], True)

        # a link inside a film that leads to another film does not get through (real paths)
        link = A.path("link")
        if os.name == "nt":
            subprocess.run(["cmd", "/c", "mklink", "/J", link, B.dir], capture_output=True)
        else:
            os.symlink(B.dir, link)
        if os.path.exists(link):
            expect("Read through a link", guard("Read", {"file_path": "link/vo.json"}, A)[0], False)
            expect(
                "Write through a link", guard("Write", {"file_path": "link/film.js"}, A)[0], False
            )
            os.rmdir(link) if os.name == "nt" else os.remove(link)
        else:
            bad.append("could not make a link to test")

        # after a write, the studio's settings come back and foreign keys go
        with open(A.path("vo.json"), "w", encoding="utf-8") as f:
            json.dump(
                {
                    "tts": "elevenlabs",
                    "model": "x",
                    "takes": 9,
                    "whisper": "C:/models",
                    "voice": "Kore",
                    "language": "en",
                    "lines": [],
                },
                f,
            )
        note = pin_after("vo.json", A)
        with open(A.path("vo.json"), encoding="utf-8") as f:
            vo = json.load(f)
        expect("vo.json pinned", (vo["tts"], vo["takes"], "whisper" in vo), ("gemini", 1, False))
        expect("and Claude is told", "restored" in note and "whisper" in note, True)

        # both looks' instructions build, every placeholder of ours filled, and none of them
        # depends on the film (so films share Claude's prompt cache)
        ours = set(re.findall(r"\{([A-Z_]+)\}", agent._read("studio", "prompt.md")))
        for look in films.LOOKS:
            ours |= set(re.findall(r"\{([A-Z_]+)\}", agent._read("studio", "looks", look + ".md")))
        for look in films.LOOKS:
            text = agent.system_prompt(look)
            left = sorted(n for n in ours if "{%s}" % n in text)
            expect("%s prompt leaves no placeholder" % look, left, [])
            expect(
                "%s prompt names no Bash command" % look,
                bool(re.search(r"--manifest|--stills|node --check|{PY}", text)),
                False,
            )
        expect("the length is in the first message", "Length: 10 seconds" in agent.ask(B), True)
        n = len(cases) + 8
    finally:
        shutil.rmtree(HOME, ignore_errors=True)
    print("%d cases, %d failed" % (n, len(bad)))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
