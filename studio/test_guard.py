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
import library  # noqa: E402
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
        (("kit", "grounds"), ("kit", "paintings"), ("kit", "cutouts", "collage")),
    )
    expect("caps: in the record", C.record().get("caps"), ["kit", "cutouts", "collage"])
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
        (("engine.js", "props.js", "kit.js"), ("engine.js", "props.js", "kit.js", "collage.js")),
    )
    mods = []
    for film in (A, B, C):
        with open(film.manifest, encoding="utf-8") as f:
            mods.append(json.load(f).get("modules"))
    expect("caps: the manifest names its modules", mods, [["kit"], ["kit"], ["kit", "collage"]])
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


def role_cases(expect):
    """What a person said a picture is for is held (validate._roles, _style_refs, _scenes_show),
    each at the earliest file that can show it, and only where it can be kept: a film's own
    attachments, while Claude writes the film for the first time."""
    D = films.Film.create("a film with marked pictures", 10, "painted")
    os.makedirs(D.path("inputs"), exist_ok=True)
    roles = {"upload1": "show", "upload2": "scene", "upload3": "style", "pic_logo": "show"}
    with open(D.path("inputs", "roles.json"), "w", encoding="utf-8") as f:
        json.dump(roles, f)
    for n in ("upload1", "upload2", "upload3", "pic_logo"):  # the files a ref must find
        with open(D.path("inputs", n + ".png"), "wb") as f:
            f.write(b"\x89PNG")

    def js(code, where="film.js"):
        with open(D.path(*where.split("/")), "w", encoding="utf-8") as f:
            f.write(code)

    def problems(name="film.js"):
        return validate.problems(D, name)

    # show: nothing asked before film.js; then the attachment, never the project's picture
    expect("roles: nothing asked before film.js", problems(), [])
    js("SK.setGround('white');\n")
    got = problems()
    expect(
        "roles: a show attachment film.js never names stops the film",
        (len(got), "upload1" in got[0], "Show it as it is" in got[0]),
        (1, True, True),
    )
    expect(
        "roles: a project's show picture an episode leaves out is not asked for",
        any("pic_logo" in g for g in got),
        False,
    )
    expect("roles: the gate says it too", validate.gate(D) == got, True)
    js("SK.setGround('white');\n// upload1 goes on the wall later\n/* and upload1 here */\n")
    expect("roles: a name in a comment is not a draw", len(problems()), 1)
    js("const wall = ['upload1'];\nwall.forEach((n, i) => SK.image(n, i * 300, 0, 280));\n")
    expect("roles: drawn through a loop of its own counts", problems(), [])
    js('SK.image("upload1", 0, 0, 600); // https://example.com/a\n')
    expect("roles: a link in a comment after the draw does not hide it", problems(), [])

    # scene: never named in code
    js("SK.image('upload1', 0, 0, 600);\nSK.cutout('upload2', 0, 400, 600);\n")
    got = problems()
    expect(
        "roles: a scene picture in code is refused, whatever helper draws it",
        (len(got), "upload2" in got[0], "never on screen" in got[0]),
        (1, True, True),
    )
    js("SK.image('upload1', 0, 0, 600);\n// upload2: three windows, a palm tree\n")
    expect("roles: a scene picture named in a comment is fine", problems(), [])

    # style: checked when paint.json is saved, before anything is painted
    paint = json.load(open(D.path("paint.json"), encoding="utf-8"))
    paint["images"] = [{"name": "street", "prompt": "a street at dusk"}]
    with open(D.path("paint.json"), "w", encoding="utf-8") as f:
        json.dump(paint, f)
    got = problems("paint.json")
    expect(
        "roles: a style attachment no painting is made from is said at paint.json",
        any("upload3" in g and "How we draw this" in g for g in got),
        True,
    )
    paint["images"] = [
        {"name": "street", "prompt": "a street at dusk", "ref": "upload3"},
        {"name": "door", "prompt": "the same street, a door", "ref": ["street", "upload3"]},
    ]
    with open(D.path("paint.json"), "w", encoding="utf-8") as f:
        json.dump(paint, f)
    expect(
        "roles: made from it, paint.json passes",
        [g for g in problems("paint.json") if "upload3" in g],
        [],
    )

    # a round, a translation and a template are not held: their promise is another one
    js("SK.setGround('white');\nSK.image('upload2', 0, 0, 600);\n")
    for k, v in (("round_of", {"film": "x"}), ("localized", {"from": "x"}), ("template", "t")):
        D.update(**{k: v})
        expect("roles: a film with %s is not held" % k, problems(), [])
        D.update(**{k: None})
    expect("roles: and the same film, first written, is", len(problems()), 2)

    # a film made in scenes: the plan names the show picture before any scene is written
    js("SK.image('upload1', 0, 0, 600);\n")
    os.makedirs(D.path("scenes"), exist_ok=True)
    D.update(mode="scenes")
    js("SK.setGround('white');\n")
    plan = {"scenes": [{"id": "s1", "shows": "the street"}, {"id": "s2", "shows": "the end"}]}
    with open(D.path("scenes.json"), "w", encoding="utf-8") as f:
        json.dump(plan, f)
    expect(
        "roles: in scenes, a plan that gives no scene the show picture is told at once",
        any("upload1" in g and "shows" in g for g in problems("scenes.json")),
        True,
    )
    expect("roles: in scenes, film.js is not held while a scene is unwritten", problems(), [])
    plan["scenes"][1]["shows"] = "the photo upload1, pinned to the wall"
    with open(D.path("scenes.json"), "w", encoding="utf-8") as f:
        json.dump(plan, f)
    expect(
        "roles: in scenes, the plan names it",
        [g for g in problems("scenes.json") if "upload1" in g],
        [],
    )
    import scenes  # noqa: PLC0415

    expect(
        "roles: the scene that shows it is told what it is for, the other is not",
        (
            "upload1" in validate.scene_pictures(D, plan["scenes"][1]),
            validate.scene_pictures(D, plan["scenes"][0]),
        ),
        (True, ""),
    )
    expect("roles: scene_message carries it", callable(scenes.scene_message), True)
    js("// the opening\n", "scenes/s1.js")
    js("// the close\n", "scenes/s2.js")
    expect("roles: in scenes, every scene written and none draws it", len(problems()), 1)
    js("SK.image('upload1', 0, 0, 600);\n", "scenes/s2.js")
    expect("roles: in scenes, drawn", problems(), [])
    expect(
        "roles: drawn_pictures is what the render keeps", validate.drawn_pictures(D), {"upload1"}
    )

    # what Claude reads: the role wins over the prompt; a project's show picture is optional
    expect(
        "roles: the attachment's note says it is required, a project picture's that it is not",
        (
            "not finished" in library.role_line("show"),
            "where this episode uses it" in library.role_line("show", required=False),
        ),
        (True, True),
    )
    expect(
        "roles: the show note puts it where the prompt does, with no fallback place",
        (
            "exactly where the prompt puts it" in library.role_line("show"),
            "framed print" in library.role_line("show"),
        ),
        (True, False),
    )

    # @picture1...: where the prompt puts each picture, told to Claude with its role
    expect(
        "roles: the prompt's sentences that name each picture",
        library.picture_places(
            "Open on the sea. Then @picture1 on the last frame, big!\n"
            "@Picture3 is the hill's look; @picture1 @picture1 again. a@picture2.com"
        ),
        {1: ["Then @picture1 on the last frame, big!", "@Picture3 is the hill's look; @picture1 @picture1 again."], 3: ["@Picture3 is the hill's look; @picture1 @picture1 again."]},
    )
    P = films.Film.create("A bakery. @picture1 on the last frame, over the shop's door.", 10, "painted")
    os.makedirs(P.path("inputs"), exist_ok=True)
    with open(P.path("inputs", "roles.json"), "w", encoding="utf-8") as f:
        json.dump({"upload1": "show", "upload2": "show"}, f)
    expect(
        "roles: each picture's place, as the prompt says it",
        (library.place_line(P, "upload1"), library.place_line(P, "upload2"), library.place_line(P, "pic_logo")),
        (' The prompt names it @picture1, and it goes where this says: "@picture1 on the last frame, over the shop\'s door."', "", ""),
    )
    expect(
        "roles: a scene's pass is told the place too",
        "over the shop's door" in validate.scene_pictures(P, {"shows": "upload1 over the door"}),
        True,
    )


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
            # the web: search at Anthropic, pages on the public internet only (_web.public_url)
            ("WebSearch", {"query": "instafill.ai logo"}, True),
            ("WebFetch", {"url": "https://example.com", "prompt": "x"}, True),
            ("WebFetch", {"url": "http://127.0.0.1:8765/api/health"}, False),
            ("WebFetch", {"url": "http://localhost:8765/"}, False),
            ("WebFetch", {"url": "http://169.254.169.254/metadata/instance"}, False),
            ("WebFetch", {"url": "http://10.0.1.10/"}, False),
            ("WebFetch", {"url": "http://168.63.129.16/"}, False),
            ("WebFetch", {"url": "http://[::1]/"}, False),
            ("WebFetch", {"url": "http://[::ffff:10.0.0.1]/"}, False),
            ("WebFetch", {"url": "file:///etc/passwd"}, False),
            ("WebFetch", {"url": "https://user:pw@example.com/"}, False),
            ("mcp__studio__picture", {"url": "https://example.com/a.png", "name": "a"}, True),
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
        role_cases(expect)

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

        # a narrator the person picked (the site's voice setting): its voice is pinned too, the
        # rest of the voice is still Claude's, Claude is told in the first message, and other films
        # do not count it as a choice
        P = films.Film.create(
            "a pinned voice", 5, "drawn", narrator={"source": "kitcut", "voice": "Puck"}
        )
        with open(P.path("vo.json"), encoding="utf-8") as f:
            expect("a picked narrator starts in vo.json", json.load(f)["voice"], "Puck")
        with open(P.path("vo.json"), "w", encoding="utf-8") as f:
            json.dump({"voice": "Kore", "style": "hushed, slow", "language": "uk", "lines": []}, f)
        note = pin_after("vo.json", P)
        with open(P.path("vo.json"), encoding="utf-8") as f:
            vo = json.load(f)
        expect(
            "a picked voice comes back, the style and language stay Claude's",
            (vo["voice"], vo["style"], vo["language"]),
            ("Puck", "hushed, slow", "uk"),
        )
        expect("and Claude is told it was put back", "voice='Puck'" in note, True)

        # a person's own ElevenLabs voice: every key its pins write is one the check accepts
        # (2026-09-30: "jobs" was pinned and refused, so the film's voice step never ran)
        E = films.Film.create(
            "an own voice",
            5,
            "drawn",
            narrator={
                "source": "elevenlabs",
                "voice": "a1B2c3D4e5F6g7H8i9J0",
                "model": "eleven_v3",
                "jobs": 3,
                "chars": 900,
                "grant": "Gq7" * 14 + "x",
            },
        )
        with open(E.path("vo.json"), "w", encoding="utf-8") as f:
            json.dump({"style": "warm", "language": "en", "lines": []}, f)
        note = pin_after("vo.json", E)
        with open(E.path("vo.json"), encoding="utf-8") as f:
            vo = json.load(f)
        expect("an own voice's pins are put in", (vo["tts"], vo["jobs"]), ("elevenlabs", 3))
        expect("and none of them is refused", "not yours" in note, False)
        # a film whose lines were never spoken is not finished silent, and a resume says so
        # (2026-09-30: told "the narration is recorded", Claude left 52k5en without a voice)
        with open(E.path("vo.json"), "w", encoding="utf-8") as f:
            json.dump({"lines": [{"text": "Leo is turning four!", "start": 1.0}]}, f)
        expect("lines, no recording: unvoiced", agent.unvoiced(E), True)
        os.makedirs(E.path("audio", "vo"), exist_ok=True)
        with open(E.path("audio", "vo", "timeline.json"), "w", encoding="utf-8") as f:
            json.dump({"lines": []}, f)
        expect("recorded: voiced", agent.unvoiced(E), False)
        expect("no lines: nothing to record", agent.unvoiced(A), False)
        expect(
            "the unvoiced resume asks for the voice",
            "voice tool first" in agent.RESUME_UNVOICED,
            True,
        )
        expect(
            "own-voice pins are all keys vo.json may hold",
            set(E.vo_pins()) - validate.VO_KEYS,
            set(),
        )
        expect("the first message names it", "person's choice: Puck" in agent.voice_note(P), True)
        expect("a film without one says nothing", agent.voice_note(A), "")
        d = P.direction()
        expect("its direction marks the voice as picked", d.get("voice_pinned"), True)
        tally = agent.recent_note("drawn", [d, {"look": "drawn", "voice": "Kore"}])
        expect("other films' notes count Claude's choices only", "Puck" in tally, False)

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
        # a site that turns WebFetch away: Claude is pointed at the page tool, not left to cite it
        refused = "The server returned HTTP 403 Forbidden. The response body was not retrieved."
        note = agent.refused_note(refused)
        expect("WebFetch refused -> the page tool", "page tool" in note, True)
        expect("WebFetch fine -> nothing", agent.refused_note("# GPT-6 Sol. OpenAI said..."), "")
        n = len(cases) + 43
    finally:
        shutil.rmtree(HOME, ignore_errors=True)
    print("%d cases, %d failed" % (n, len(bad)))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
