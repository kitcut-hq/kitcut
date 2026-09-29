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
import asyncio
import tempfile
import subprocess

HOME = tempfile.mkdtemp(prefix="studio-test-")
os.environ["STUDIO_HOME"] = HOME
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agent  # noqa: E402
import film as films  # noqa: E402
import validate  # noqa: E402
from guard import guard, pin_after  # noqa: E402
from sched import Sched  # noqa: E402
from tools import ToolError, Tools  # noqa: E402


def caps_cases(expect, A, B, C):
    """A look is a recipe of capabilities (film.CAPS), fixed in the film's record: what each film
    is given, what the page says, and that the syntax check covers a module too."""
    expect(
        "caps: each look's recipe",
        (A.caps, B.caps, C.caps),
        (("grounds",), ("paintings",), ("cutouts", "collage")),
    )
    expect("caps: in the record", C.record().get("caps"), ["cutouts", "collage"])
    for look, recipe in films.RECIPES.items():
        for c in recipe:
            cap = films.CAPS[c]
            there = [os.path.join(films.KIT, "sketch", m + ".js") for m in cap.get("modules", ())]
            there += [os.path.join(films.KIT, f["file"]) for f in cap.get("fonts", ())]
            there += [os.path.join(films.KIT, *p) for p in cap.get("fills", {}).values()]
            missing = [p for p in there if not os.path.exists(p)]
            expect("caps: %s/%s files exist" % (look, c), missing, [])
    expect(
        "caps: engine files",
        (A.engine_files(), C.engine_files()),
        (("engine.js", "props.js"), ("engine.js", "props.js", "collage.js")),
    )
    # a film from before looks were recorded: painted if it has a paint.json
    old = films.Film.create("an old painted film", 5, "painted")
    rec = old.record()
    for k in ("look", "caps"):
        rec.pop(k)
    with open(old.path("studio.json"), "w", encoding="utf-8") as f:
        json.dump(rec, f)
    expect("caps: an old film's look", (old.look, old.caps), ("painted", ("paintings",)))
    # what the page says while it paints, and when Claude looks at the sheet
    paint = "mcp__studio__paint"
    expect(
        "labels: painting",
        (agent._describe(paint, {}, B), agent._describe(paint, {}, C)),
        ("painting the scenes (Muse)", "painting the cut-outs"),
    )
    expect(
        "labels: the sheet",
        agent._describe("Read", {"file_path": "images/sheet.jpg"}, C),
        "looking at the cut-outs",
    )
    # a refused write names only the film's own engine files
    why_a = guard("Write", {"file_path": "engine/extra.js"}, A)[1]
    why_c = guard("Write", {"file_path": "engine/extra.js"}, C)[1]
    expect(
        "refusal: engine files",
        ("collage.js" in why_a, "engine/collage.js" in why_c),
        (False, True),
    )
    # the syntax check covers every engine file the film has, its modules too
    if not shutil.which("node"):
        return
    with open(C.path("film.js"), "w", encoding="utf-8") as f:
        f.write("// For: a test\nSK.film({ duration: 30, draw() {} });\n")
    with open(C.path("engine", "collage.js"), "a", encoding="utf-8") as f:
        f.write("\nSK.broken = function ( {\n")
    try:
        asyncio.run(Tools(C, Sched(), lambda ev: None).check())
        said = ""
    except ToolError as e:
        said = str(e)
    expect("check: engine/collage.js is checked", "engine/collage.js" in said, True)


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
            # a system file: on Linux "C:/..." is only a relative name inside the film
            (
                "Read",
                {"file_path": "C:/Windows/win.ini" if os.name == "nt" else "/etc/passwd"},
                False,
            ),
            ("Read", {"file_path": os.path.join(HOME, "claude", A.id, ".claude.json")}, False),
            ("Write", {"file_path": "film.js"}, True),
            ("Write", {"file_path": A.path("score.json")}, True),
            ("Edit", {"file_path": "sfx.json"}, True),
            ("Edit", {"file_path": "vo.json"}, True),
            ("Edit", {"file_path": "engine/props.js"}, True),
            ("Write", {"file_path": "engine/engine.js"}, True),
            ("Write", {"file_path": "engine/extra.js"}, False),
            ("Write", {"file_path": "engine/collage.js"}, False),  # a collage film's module
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

        # a collage film: cut-outs in its paint.json, the collage pieces and the print faces
        C = films.Film.create("a collage test", 30, "collage")
        expect("collage: the look", (A.look, B.look, C.look), ("drawn", "painted", "collage"))
        expect(
            "collage: only it gets collage.js",
            (
                os.path.exists(C.path("engine", "collage.js")),
                os.path.exists(A.path("engine", "collage.js")),
            ),
            (True, False),
        )
        with open(C.manifest, encoding="utf-8") as f:
            cfonts = {x["family"] for x in json.load(f)["fonts"]}
        with open(A.manifest, encoding="utf-8") as f:
            afonts = {x["family"] for x in json.load(f)["fonts"]}
        expect(
            "collage: the print faces",
            ("Abril Fatface" in cfonts, "Abril Fatface" in afonts),
            (True, False),
        )
        with open(C.path("paint.json"), encoding="utf-8") as f:
            cp = json.load(f)
        expect(
            "collage: cut-outs pinned",
            (cp["cutouts"], cp["max_images"]),
            (films.CUTOUTS_PINNED, films.limits(30)["cutouts"]),
        )
        expect("collage: Write paint.json", guard("Write", {"file_path": "paint.json"}, C)[0], True)
        expect(
            "collage: Write its collage.js",
            guard("Write", {"file_path": "engine/collage.js"}, C)[0],
            True,
        )
        cut = {"name": "cone", "prompt": "a waffle cone", "cutout": {"border": 0}, "aspect": "2:3"}
        for f_, film_ in ((C, C), (B, B)):
            with open(f_.path("paint.json"), encoding="utf-8") as f:
                d = json.load(f)
            d["images"] = [cut]
            with open(f_.path("paint.json"), "w", encoding="utf-8") as f:
                json.dump(d, f)
        expect("collage: a cut-out is fine", validate.problems(C, "paint.json"), [])
        expect("painted: a cut-out is not", bool(validate.problems(B, "paint.json")), True)
        with open(C.path("paint.json"), encoding="utf-8") as f:
            d = json.load(f)
        d["images"] = [dict(cut, cutout={"border": 99}, aspect="5:1")]
        d["cutouts"] = {"model": "somebody/else"}
        with open(C.path("paint.json"), "w", encoding="utf-8") as f:
            json.dump(d, f)
        note = pin_after("paint.json", C)
        with open(C.path("paint.json"), encoding="utf-8") as f:
            back = json.load(f)
        expect("collage: the cut-out model pinned back", back["cutouts"], films.CUTOUTS_PINNED)
        expect(
            "collage: a bad border and shape are named",
            ("cutout" in note, "aspect" in note),
            (True, True),
        )

        caps_cases(expect, A, B, C)

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
        n = len(cases) + 32
    finally:
        shutil.rmtree(HOME, ignore_errors=True)
    print("%d cases, %d failed" % (n, len(bad)))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
