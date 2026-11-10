#!/usr/bin/env python
"""Films made in scenes (studio/scenes.py, SK.scene in sketch/engine.js), checked end to end with
Claude stubbed out: python studio/test_scenes.py

The engine, on real stills: each scene draws its own stretch of the film, a stretch no scene
covers yet draws nothing and does not fail the render, and a broken scene names itself. The plan's
rules and the per-pass guard. Then the passes (director, a conversation per scene, editor) on 8-,
16- and 30-minute films: every pass's opening stays bounded whatever the film's length, a scene
that goes silent is picked up in its own session, a server stopped half-way leaves the film to the
next one, which carries it on from the scene it was on, and a pass that never finishes fails the
film after its tries. Sound, render and the studio's sheets are stubbed in the ladder (their real
paths are covered by test_server.py); a throwaway STUDIO_HOME, removed at the end.
"""

import os
import sys
import json
import shutil
import asyncio
import tempfile

HOME = tempfile.mkdtemp(prefix="studio-scenes-")
os.environ["STUDIO_HOME"] = HOME
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agent  # noqa: E402 -- imports _env first
import film as films  # noqa: E402
import guard  # noqa: E402
import scenes  # noqa: E402
import store  # noqa: E402
import tools as tools_mod  # noqa: E402
import validate  # noqa: E402
from sched import Sched  # noqa: E402

os.environ.pop("STUDIO_MEDIA_BASE", None)
agent.procs.SECRETS.pop("STUDIO_MEDIA_SAS", None)
os.environ.pop("STUDIO_R2_ENDPOINT", None)  # nor to R2, whatever the .env says
os.environ.pop("STUDIO_MEDIA_OLD_BASE", None)
agent.procs.SECRETS.pop("STUDIO_R2_KEY_ID", None)
agent.procs.SECRETS.pop("STUDIO_R2_SECRET", None)
EX = os.path.join(films.KIT, "config", "sketch", "example")
USAGE = {"input_tokens": 100, "output_tokens": 200, "cache_read_input_tokens": 1000}


class Res:  # the part of the SDK's ResultMessage make_film reads
    def __init__(self, turns, text):
        self.num_turns, self.result, self.session_id = turns, text, "fake"
        self.is_error, self.subtype, self.total_cost_usd = False, "success", None


def timeline(film, n, every=10.0):
    """n narration lines, one every `every` s, each 8.5 s long, as sketch-vo writes them."""
    lines = [
        {
            "i": i,
            "text": "Line %d." % i,
            "start": 1 + every * i,
            "end": 1 + every * i + 8.5,
            "words": [{"text": "Line", "s": 1 + every * i, "e": 1.4 + every * i}],
        }
        for i in range(n)
    ]
    os.makedirs(film.path("audio", "vo"), exist_ok=True)
    with open(film.path("audio", "vo", "timeline.json"), "w", encoding="utf-8") as f:
        json.dump({"lines": lines}, f)
    with open(film.path("vo.json"), encoding="utf-8") as f:
        vo = json.load(f)
    vo["lines"] = [{"text": L["text"]} for L in lines]
    with open(film.path("vo.json"), "w", encoding="utf-8") as f:
        json.dump(vo, f)


def write(film, rel, text):
    p = film.path(*rel.split("/"))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)


def scene_js(sid, a, b, colour=None):
    body = (
        "const c = SK.ctx(); c.save(); c.setTransform(1, 0, 0, 1, 0, 0); c.fillStyle = '%s'; "
        "c.fillRect(0, 0, 1920, 1080); c.restore();" % colour
        if colour
        else "SK.txt('%s', 0, 0, { size: 60 });" % sid
    )
    return "SK.scene({ id: '%s', lines: [%d, %d], draw(t, local, vis) { %s } });\n" % (
        sid,
        a,
        b,
        body,
    )


LOOK = "// For: a test; calm\nSK.look = {};\nSK.film({ duration: %d, camera: SK.camera([[0, [0, 0, 1]]]) });\n"

# ------------------------------------------------------------------ the stubbed Claude, per pass
OPENINGS = []  # (pass, opening length, resumed)
EFFORTS = []  # (pass, the effort it was run at)
STALL_ON, HOLD_ON, NEVER_ON = [None], [None], [None]
HELD = []


async def fake_claude(
    film,
    emit,
    meter,
    tools,
    auth="api",
    prompt=None,
    resume=None,
    budget_usd=None,
    system=None,
    effort=None,
):
    key = tools.pass_name
    OPENINGS.append((key, len(prompt or ""), bool(resume)))
    EFFORTS.append((key, effort))
    if not resume:
        tools.session = "fake-%s-%d" % (key, len(OPENINGS))
    meter.add("msg-%d" % len(OPENINGS), USAGE)
    emit({"type": "cost", "usd": round(meter.usd(), 4)})
    if key == STALL_ON[0] and not resume:
        await asyncio.sleep(120)  # nothing at all: no message, no event, no tool at work
        return None
    if key == HOLD_ON[0]:
        HELD[0].set()
        await asyncio.sleep(3600)
    if key == NEVER_ON[0]:
        return Res(1, "I could not.")  # writes nothing
    n = film.length
    if key == scenes.DIRECTOR:
        lines = n // 10
        timeline(film, lines)
        write(film, "film.js", LOOK % n)
        plan = [
            {
                "id": "%02d-part" % (k + 1),
                "title": "Part %d" % (k + 1),
                "lines": [3 * k, 3 * k + 2],
                "shows": "part %d of the story" % (k + 1),
            }
            for k in range(lines // 3)
        ]
        write(film, "scenes.json", json.dumps({"scenes": plan}))
        write(film, "scenes/01-part.js", scene_js("01-part", 0, 2))
        return Res(3, "The look: plain text, centred.")
    if key == scenes.EDITOR:
        for f in ("score.json", "sfx.json"):
            shutil.copy(os.path.join(EX, f), film.dir)
        return Res(2, "A finished film.")
    a = int(key[:2]) - 1
    write(film, "scenes/%s.js" % key, scene_js(key, 3 * a, 3 * a + 2))
    return Res(2, "It shows %s, and ends on the title." % key)


async def no_step(self, *a, **k):
    return "(stubbed)"


async def no_sheet(self, times, name):
    return "outputs/review/%s.png" % name


async def main():
    bad = []

    def check(ok, what):
        print("%s  %s" % ("ok  " if ok else "FAIL", what))
        if not ok:
            bad.append(what)

    agent.STORE = mem = store.MemoryStore()

    # ------------------------------------------------ the engine, on real stills
    f = films.Film.create("three colours", 30, "drawn", mode="scenes")
    timeline(f, 6, every=5.0)  # lines at 1, 6, ... 26 s
    write(f, "film.js", LOOK % 30)
    write(f, "scenes/01-red.js", scene_js("01-red", 0, 1, "#ff0000"))
    write(f, "scenes/02-green.js", scene_js("02-green", 2, 3, "#00ff00"))
    write(f, "scenes/03-blue.js", scene_js("03-blue", 4, 5, "#0000ff"))
    t = tools_mod.Tools(f, Sched(), lambda ev: None)
    await t.stills([0.2, 8, 15.2, 25])
    from PIL import Image  # noqa: PLC0415

    def centre(sec):
        im = Image.open(f.path("outputs", "review", "%06.2f.png" % sec)).convert("RGB")
        return im.getpixel((im.width // 2, im.height // 2))

    colours = [centre(s) for s in (0.2, 8, 15.2, 25)]
    main_ch = [max(range(3), key=lambda i: c[i]) for c in colours]
    check(
        main_ch == [0, 0, 1, 2],
        "each scene draws its own stretch: the first from 0 s, the rest from 0.3 s before their "
        "first line (%s)" % colours,
    )
    os.remove(f.path("scenes", "02-green.js"))
    await t.stills([15.2])
    c = centre(15.2)
    check(
        max(range(3), key=lambda i: c[i]) != 1 and abs(c[0] - c[2]) < 60,
        "a stretch no scene covers yet draws nothing, and the render does not fail (%s)" % (c,),
    )
    write(f, "scenes/02-green.js", "throw new Error('no such helper');\n")
    try:
        await t.stills([15.2])
        check(False, "a scene that throws fails its stills")
    except tools_mod.ToolError as e:
        check(
            "scenes/02-green.js" in str(e), "a scene that throws names itself (%s)" % str(e)[-160:]
        )
    # a script that does not parse never reads its own name (cast members alike): check names it
    write(f, "scenes/02-green.js", "SK.scene({ id: '02-green', lines: [2, 3], draw( {\n")
    try:
        await t.check()
        check(False, "a scene that does not parse fails the check")
    except tools_mod.ToolError as e:
        check("scenes/02-green.js" in str(e), "and one that does not parse is named by check")

    # ------------------------------------------------ the switch, set after film.py was imported
    # (the studio's .env is read after it: a value read at import would never have been seen)
    os.environ["STUDIO_SCENES_OVER_S"] = "300"
    for look in films.LOOKS:
        f = films.Film.create("who paints", 480, look, mode="scenes")
        check(
            ("paint.json" in agent.director_files(f)) == bool(films.paint_kinds(f.caps)),
            "a %s film's director %s order its pictures"
            % (look, "may" if films.paint_kinds(f.caps) else "has none to"),
        )
    long_one = films.Film.create("five and a bit", 305, "drawn")
    short_one = films.Film.create("five exactly", 300, "drawn")
    os.environ.pop("STUDIO_SCENES_OVER_S")
    unset = films.Film.create("no switch", 480, "drawn")
    check(
        long_one.mode == "scenes"
        and os.path.isdir(long_one.path("scenes"))
        and short_one.mode == "single"
        and unset.mode == "single",
        "STUDIO_SCENES_OVER_S=300 makes a 305 s film in scenes, a 300 s one in one piece; unset, none",
    )
    for x in (long_one, short_one, unset):
        x.update(state="done")  # asked about only: nothing is to make them

    # ------------------------------------------------ the plan's rules, and the guard per pass
    g = films.Film.create("a plan", 120, "drawn", mode="scenes")
    timeline(g, 12)
    ok = {
        "scenes": [
            {"id": "01-a", "lines": [0, 5], "shows": "x"},
            {"id": "02-b", "lines": [6, 11], "shows": "y"},
        ]
    }
    gap = {
        "scenes": [
            {"id": "01-a", "lines": [0, 4], "shows": "x"},
            {"id": "02-b", "lines": [6, 11], "shows": "y"},
        ]
    }
    one = {"scenes": [{"id": "01-a", "lines": [0, 11], "shows": "x"}]}
    tiny = {
        "scenes": [
            {"id": "01-a", "lines": [0, 0], "shows": "x"},
            {"id": "02-b", "lines": [1, 11], "shows": "y"},
        ]
    }
    check(validate._scenes(ok, g) == [], "a plan with every line in one scene, in order, passes")
    check(
        any("start at 5" in x for x in validate._scenes(gap, g)), "a gap is refused, saying where"
    )
    check(any("split it" in x for x in validate._scenes(one, g)), "a two-minute scene is refused")
    check(any("join it" in x for x in validate._scenes(tiny, g)), "a ten-second scene is refused")

    # a Free-plan film: every pass that draws is told the mark's corner is taken
    with open(g.path("scenes.json"), "w", encoding="utf-8") as fh:
        json.dump(ok, fh)

    def told():
        return [
            "kitcut.ai" in m
            for m in (
                agent.ask(g),
                scenes.director_message(g, agent.ask(g)),
                scenes.scene_message(g, 1),
                scenes.editor_message(g, []),
            )
        ]

    # a helper scene 1 puts on the shared look is shown to the scenes after it, not to scene 1
    first = scenes.scene_file(scenes.spans(g)[0][0])
    os.makedirs(os.path.dirname(g.path(*first.split("/"))), exist_ok=True)
    with open(g.path(*first.split("/")), "w", encoding="utf-8") as fh:
        fh.write(
            "// a medal on a ribbon\nSK.look.medal = (x, y, o = {}) => {};\nSK.look.size = 3;\n"
        )
    shared = scenes.scene_message(g, 1)
    check(
        "SK.look.medal(x, y, o = {})" in shared
        and "a medal on a ribbon" in shared
        and "SK.look.size" not in shared
        and "SK.look.medal(" not in scenes.scene_message(g, 0),
        "a helper an earlier scene shared is listed for the later ones, with its comment",
    )
    os.remove(g.path(*first.split("/")))

    plain = told()
    g.update(branding=True)
    branded = told()
    g.update(branding=False)
    check(
        plain == [False] * 4 and branded == [True] * 4,
        "a Free-plan film's director, scenes and editor are told to keep the mark's corner clear "
        "(%s, %s)" % (plain, branded),
    )
    check(
        guard.guard("Write", {"file_path": "scenes/03-c.js"}, g, ["scenes/03-c.js"])[0]
        and not guard.guard("Write", {"file_path": "scenes/02-b.js"}, g, ["scenes/03-c.js"])[0]
        and not guard.guard("Write", {"file_path": "film.js"}, g, ["scenes/03-c.js"])[0],
        "a scene's conversation may write its own file and nothing else",
    )
    check(
        guard.guard("Write", {"file_path": "scenes/01-orbit.js"}, g, ["scenes/01-*.js"])[0]
        and not guard.guard("Write", {"file_path": "scenes/02-x.js"}, g, ["scenes/01-*.js"])[0],
        "the director may write scene 1, whatever it names it, and no other",
    )

    # ------------------------------------------------ the passes, at 8, 16 and 30 minutes
    agent.run_claude = fake_claude
    tools_mod.Tools.sound = no_step
    tools_mod.Tools.render = no_step
    tools_mod.Tools.sheet_of = no_sheet
    tools_mod.Tools.check = (
        no_step  # node --check on 60 scene files, 60 times: real in the engine test
    )
    real_stall = agent.STALL_S
    agent.STALL_S = 2
    widest = {}
    for n in (480, 960, 1800):
        film = films.Film.create("a long one", 480, "drawn", mode="scenes")
        film.update(length=n)  # past the studio's 8 minutes: the pipeline, not the product
        with open(film.manifest, encoding="utf-8") as fh:
            m = json.load(fh)
        m["duration"] = float(n)
        with open(film.manifest, "w", encoding="utf-8") as fh:
            json.dump(m, fh)
        del OPENINGS[:], EFFORTS[:]
        STALL_ON[0] = "03-part" if n == 480 else None
        r = await agent.make_film(film, lambda ev: None, Sched(), auth="api")
        plan = scenes.plan(film)
        kinds = {}
        for key, size, _ in OPENINGS:
            k = "scene" if key and not key.startswith("_") else key
            kinds[k] = max(kinds.get(k, 0), size)
        widest[n] = kinds
        check(
            r.get("ok") and len(plan) == n // 30 and all(scenes.done(film, s["id"]) for s in plan),
            "%d-minute film: done, %d scenes each done (%s)" % (n // 60, len(plan), r.get("error")),
        )
        if n == 480:
            again = [x for x in OPENINGS if x[0] == "03-part"]
            check(
                [x[2] for x in again] == [False, True]
                and scenes.progress(film)["03-part"]["tries"] == 1
                and r.get("stalls") == 1,
                "a scene that goes silent is picked up in its own session, once, and finishes",
            )
            check(
                EFFORTS and all(e == scenes.EFFORT for _, e in EFFORTS),
                "every pass, a picked-up one too, thinks at %s (%s)"
                % (scenes.EFFORT, sorted({e for _, e in EFFORTS}, key=str)),
            )
            check(
                agent.limits(n)["claude_s"] < scenes.film_claude_s(film)
                and scenes.pass_limits(film, "scene", (0, 40))["claude_s"] >= 20 * 60,
                "a scene gets 20+ minutes, and the film all its passes' (%d min, not %d)"
                % (scenes.film_claude_s(film) // 60, agent.limits(n)["claude_s"] // 60),
            )
            check(
                mem.docs[film.id]["state"] == "done"
                and abs(film.record()["claude_cost_usd"] - scenes.spent(film)) < 1e-6,
                "the record's cost is the passes' costs added up",
            )
    check(
        widest[1800]["scene"] <= widest[480]["scene"] * 1.1
        and max(v["_director"] for v in widest.values()) < 15000,
        "a scene's opening does not grow with the film, nor the director's past its brief (%s)"
        % {k: (v.get("scene"), v.get("_director")) for k, v in widest.items()},
    )
    check(
        widest[1800]["_editor"] < 40000,
        "the editor's grows with the number of scenes only, a line each (%d chars at 30 min)"
        % widest[1800]["_editor"],
    )
    agent.STALL_S = real_stall

    # ------------------------------------------------ a server stopped half-way, then carried on
    STALL_ON[0] = None
    film = films.Film.create("stopped at scene 5", 480, "drawn", mode="scenes")
    HELD[:] = [asyncio.Event()]
    HOLD_ON[0] = "05-part"
    ctl = {}
    task = asyncio.create_task(
        agent.make_film(film, lambda ev: None, Sched(), auth="api", control=ctl)
    )
    await asyncio.wait_for(HELD[0].wait(), 60)
    ctl["shutdown"] = True
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    check(
        film.state == "claude"
        and not film.record().get("server")
        and all(scenes.done(film, "%02d-part" % k) for k in (1, 2, 3, 4))
        and not scenes.done(film, "05-part"),
        "a server stopped at scene 5 leaves the film to the next, with scenes 1-4 kept",
    )
    HOLD_ON[0] = None
    del OPENINGS[:]
    r = await agent.make_film(film, lambda ev: None, Sched(), auth="api")
    ran = [k for k, _, _ in OPENINGS]
    check(
        r.get("ok") and ran[0] == "05-part" and "_director" not in ran and "02-part" not in ran,
        "the next run carries it on from scene 5, nothing before it again (%s...)" % ran[:3],
    )

    # ------------------------------------------------ a pass that never finishes
    film = films.Film.create("never writes scene 2", 480, "drawn", mode="scenes")
    NEVER_ON[0] = "02-part"
    r = await agent.make_film(film, lambda ev: None, Sched(), auth="api")
    NEVER_ON[0] = None
    check(
        not r.get("ok")
        and "did not finish in %d tries" % scenes.TRIES in (r.get("error") or "")
        and scenes.progress(film)["02-part"]["tries"] == scenes.TRIES,
        "a scene that never gets written fails the film after %d tries (%s)"
        % (scenes.TRIES, r.get("error")),
    )
    print("%d failed" % len(bad))
    return 1 if bad else 0


if __name__ == "__main__":
    try:
        code = asyncio.run(main())
    finally:
        shutil.rmtree(HOME, ignore_errors=True)
    sys.exit(code)
