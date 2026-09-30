#!/usr/bin/env python
"""People in a film (film.CAPS "people"): photos of real people drawn as talking characters,
end to end through the API with the drawing stubbed: no image model, no Claude, seconds.

    python studio/test_people.py

Covers: a film asked for with people and a character style, the photos landing in inputs/ and
the manifest's heads, the capability and its engine module, "auto" drawing them in the look's
own style, the requests refused (too many, the same photo twice, a voice note as a person, an
unknown style), the system prompt carrying the people only when there are people (every other
film's stays as it was), the first message naming them, vo.json's cast and who checked, and the
drawing step: a person drawn, a refused one tried again as a sticker, ready.json written, and the
picture tools telling Claude who could not be drawn. Everything in a throwaway STUDIO_HOME.
"""

import os
import io
import sys
import json
import asyncio
import tempfile

HOME = tempfile.mkdtemp(prefix="studio-people-test-")
os.environ["STUDIO_HOME"] = HOME
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server  # noqa: E402 -- imports agent, which imports _env first
import agent  # noqa: E402
import procs  # noqa: E402
import store  # noqa: E402
import validate  # noqa: E402
import film as films  # noqa: E402
from film import Film  # noqa: E402
from tools import Tools  # noqa: E402

from aiohttp.test_utils import TestClient, TestServer  # noqa: E402
from PIL import Image  # noqa: E402

TOKEN = "test-token"


def jpg(w, h, col=(180, 140, 110)):
    b = io.BytesIO()
    Image.new("RGB", (w, h), col).save(b, "JPEG")
    return b.getvalue()


async def main():
    agent.STORE = store.MemoryStore()
    server.start = lambda f, finish_only=False: None  # the film itself is test_server.py's job
    drawn = []
    agent.draw_people_soon = lambda f: drawn.append(f.id)  # the drawing is tested below
    bad = []

    def check(ok, what, detail=""):
        print("%s  %s%s" % ("ok  " if ok else "FAIL", what, "" if ok else "  -- %s" % detail))
        if not ok:
            bad.append(what)

    async with TestClient(TestServer(server.make_app(TOKEN))) as c:
        me = {"Authorization": "Bearer " + TOKEN, "X-Client-Ip": "u:alice"}

        async def up(data, ctype="image/jpeg"):
            r = await c.post("/api/uploads", data=data, headers={**me, "Content-Type": ctype})
            return (await r.json())["id"]

        a, b, c3 = (
            await up(jpg(900, 1200)),
            await up(jpg(800, 800, (90, 60, 40))),
            await up(jpg(600, 600)),
        )
        body = {
            "prompt": "The two of us introduce our bakery",
            "seconds": 10,
            "people": [{"upload": a, "name": "  Alex   Baker "}, {"upload": b}],
            "character_style": "felt",
        }
        r = await c.post("/api/films", json=body, headers=me)
        j = await r.json()
        check(r.status == 202 and j.get("people") == 2, "a film with two people", j)
        f = Film.open(j.get("id"))
        with open(f.manifest, encoding="utf-8") as fh:
            m = json.load(fh)
        rec = f.record()
        check(
            m.get("heads")
            == {
                "p1": {"photo": "inputs/person1.jpg", "look": "felt", "rig": "rigs/p1"},
                "p2": {"photo": "inputs/person2.jpg", "look": "felt", "rig": "rigs/p2"},
            },
            "their photos are the manifest's heads, in the style asked for",
            m.get("heads"),
        )
        check(
            all(os.path.exists(f.path("inputs", "person%d.jpg" % i)) for i in (1, 2))
            and m.get("images", {}).get("p1") == "inputs/person1.jpg",
            "photos in inputs/, and each an image to fall back on",
            m.get("images"),
        )
        check(
            [(p["id"], p["name"], p["style"]) for p in rec.get("people", [])]
            == [("p1", "Alex Baker", "felt"), ("p2", "", "felt")],
            "the record names them",
            rec.get("people"),
        )
        check(
            "people" in f.caps
            and m.get("modules") == ["heads"]
            and os.path.exists(f.path("engine", "heads.js"))
            and "heads.js" in f.engine_files(),
            "the people capability brings sketch/heads.js into the film's engine",
            (f.caps, m.get("modules")),
        )
        check(drawn == [f.id], "drawing them starts with the film", drawn)
        check(
            agent.first_record(f, "web", "u:alice").get("people") == 2,
            "the run record counts them (never their photos)",
        )

        # "auto": the look's own style
        r = await c.post(
            "/api/films",
            json={
                "prompt": "hello there",
                "seconds": 10,
                "look": "collage",
                "people": [{"upload": c3}],
            },
            headers=me,
        )
        f2 = Film.open((await r.json()).get("id"))
        with open(f2.manifest, encoding="utf-8") as fh:
            m2 = json.load(fh)
        check(
            m2["heads"]["p1"]["look"] == films.PEOPLE_AUTO["collage"] == "papercut"
            and m2.get("modules") == ["collage", "heads"],
            "auto draws them in the look's own style",
            m2.get("heads"),
        )

        # refused
        four = [{"upload": await up(jpg(400, 400, (i * 40, 90, 90)))} for i in range(5)]
        for what, extra in (
            ("more than four people", {"people": four}),
            ("the same photo twice", {"people": [{"upload": four[0]["upload"]}] * 2}),
            ("an unknown style", {"people": [four[0]], "character_style": "hologram"}),
            ("a look kept for local films", {"people": [four[0]], "character_style": "brick"}),
            ("a person that is not a list of objects", {"people": "Alex"}),
        ):
            r = await c.post(
                "/api/films", json={"prompt": "hi there", "seconds": 10, **extra}, headers=me
            )
            check(r.status == 400, "refused: " + what, await r.json())

        lim = server.limits_doc()["people"]
        check(
            lim["per_film"] == 4
            and lim["styles"][0] == "auto"
            and "felt" in lim["styles"]
            and "brick" not in lim["styles"]
            and set(lim["auto"].values()) <= set(lim["styles"]),
            "/api/limits publishes the people's styles (the site's list is held to it)",
            lim,
        )

        # the system prompt: the people only when there are people
        plain = agent.system_prompt("drawn")
        withp = agent.system_prompt("drawn", f.caps)
        check(
            "# The people (`SK.head`)" in withp and "# The people" not in plain,
            "the brief carries the people only for a film with people",
        )
        check("{PEOPLE}" not in plain and "{PEOPLE}" not in withp, "no placeholder left")
        check(
            withp.replace(
                open(os.path.join(agent.KIT, "studio", "people.md"), encoding="utf-8").read(), ""
            )
            == plain,
            "otherwise the brief is byte for byte a film's without people",
        )
        brief = agent.ask(f)
        check(
            "SK.head('p1'" in brief and '"Alex Baker"' in brief and "inputs/person2.jpg" in brief,
            "the first message names them and how to put them on screen",
            brief[-900:],
        )
        check(
            "SK.head(" not in agent.ask(f2).split("People in this film")[0], "only in its own note"
        )

        # vo.json: cast and who
        def vo(**over):
            d = {**films.VO_PINNED, "model": "m", "voice": "Kore", "style": "", "language": "en"}
            return {**d, **over}

        ok = vo(
            cast={"p1": {"voice": "Puck", "style": "warm"}, "p2": {"voice": "Kore"}},
            lines=[
                {"who": "p1", "text": "Hi."},
                {"who": "p2", "text": "Hello."},
                {"text": "They bake."},
            ],
        )
        check(validate._vo(ok, 6, 10, ["p1", "p2"]) == [], "a cast and its speakers pass")
        for what, d, ppl in (
            (
                "a speaker not in the film",
                vo(cast={"p9": {"voice": "Puck"}}, lines=[{"who": "p9", "text": "x"}]),
                ["p1"],
            ),
            ("a speaker with no voice", vo(cast={}, lines=[{"who": "p1", "text": "x"}]), ["p1"]),
            ("a voice that is not one", vo(cast={"p1": {"voice": "Bob"}}, lines=[]), ["p1"]),
            ("a cast in a film without people", vo(cast={"p1": {"voice": "Puck"}}, lines=[]), []),
        ):
            check(validate._vo(d, 6, 10, ppl) != [], "refused: " + what)
        check("cast" in validate.VO_KEYS, "the guard keeps cast when it pins vo.json")

    # the drawing step, head-rig stubbed: p1 draws; p2 is refused, then refused as a sticker too
    calls = []

    async def fake_run(argv, cwd, env, timeout, on_line=None, jobs=None):
        with open(os.path.join(cwd, "sketch.json"), encoding="utf-8") as fh:
            heads = json.load(fh)["heads"]
        calls.append({k: v["look"] for k, v in heads.items()})
        os.makedirs(os.path.join(cwd, "rigs", "p1"), exist_ok=True)
        with open(os.path.join(cwd, "rigs", "p1", "rig.json"), "w") as fh:
            fh.write("{}")
        return 1, [
            "  p2           %s: NOT BUILT -- the image model refused to draw gen_base.png"
            % heads["p2"]["look"]
        ]

    procs.run = fake_run
    got = await agent.draw_people(f)
    check(
        got["p1"]["state"] == "ready"
        and got["p2"]["state"] == "failed"
        and "refused" in got["p2"]["why"]
        and calls == [{"p1": "felt", "p2": "felt"}, {"p1": "felt", "p2": "sticker"}],
        "a refused person is tried once more as a sticker, then reported",
        (got, calls),
    )
    check(os.path.exists(f.path("rigs", "ready.json")), "ready.json written")
    t = Tools(f, server.SCHED, lambda ev: None)
    note = await t.people_ready()
    check(
        "p2 could not be drawn" in note
        and "SK.image('p2'" in note
        and "p1" not in note.split("p2")[0][-5:],
        "the picture tools tell Claude who could not be drawn, once",
        note,
    )
    check(await t.people_ready() == "", "and only once")

    print("\n%d failed" % len(bad) if bad else "\nall passed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
