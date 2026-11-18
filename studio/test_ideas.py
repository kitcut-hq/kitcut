#!/usr/bin/env python
"""Three ideas for a finished film's episode 2 (ideas.py), without Claude:
python studio/test_ideas.py

Covers: the cast a series would carry over (the members the film's code drew, then its painted
characters, each name once, descriptions trimmed), someone else's film and one that does not
exist are not found and an unfinished one is refused, what Claude is asked (the idea, the
audience, the narration, the cast by name, and never this film told again), the answer held to
three different one-line ideas, how they stand on disk (none, writing, done, failed, and a
"writing" whose server went away), a second ask starting nothing while they are writing or
written, and the two routes answering the site's shapes; each idea's still and the film's look
in the same answer, the stills painted by a stubbed Muse (small, 16:9, one failing leaving the
others), put online and kept, "painting" while it works and failed when it went away, and nothing
painted where media copying is off. Everything in a throwaway STUDIO_HOME.
"""

import os
import sys
import json
import asyncio
import tempfile
from datetime import datetime, timedelta

HOME = tempfile.mkdtemp(prefix="studio-ideas-test-")
os.environ["STUDIO_HOME"] = HOME
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ideas  # noqa: E402 -- imports _env first
import fromfilm  # noqa: E402
import ytdraft  # noqa: E402
from film import Film  # noqa: E402

PIP = """SK.cast.pip = {
  about: 'Pip, a small orange fox in a blue scarf',
  draw(x, y, o = {}) { SK.wash(SK.S.ellC(x, y, 70, 90), '#e0782f'); SK.cast.owl.draw(x, y); },
};
"""
OWL = "SK.cast.owl = {\n  about: '%s',\n  draw(x, y) {},\n};\n" % ("An old owl " * 20).strip()
FILM = """// For: children of 4 to 6; calm and curious
SK.film({ duration: 5, draw(t) { SK.cast.pip.draw(0, 0); SK.cast.tree.draw(0, 0); } });
"""


def write(film, rel, data):
    p = film.path(*rel.split("/"))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(data if isinstance(data, str) else json.dumps(data))


def picture(path):
    from PIL import Image

    os.makedirs(os.path.dirname(path), exist_ok=True)
    Image.new("RGB", (600, 400), "#3366aa").save(path)


def finished(client="u:alice"):
    """A finished film of alice's: Pip drawn (who draws Owl), a tree from the kit (no code of its
    own: not a cast member), Mom painted and kept, and a painting of Pip kept too (a name the
    drawn cast has already)."""
    F = Film.create("Pip learns why the sky is blue. Keep it calm.", 5, "drawn", client=client)
    write(F, "cast/pip.js", PIP)
    write(F, "cast/owl.js", OWL)
    write(F, "film.js", FILM)
    write(F, "vo.json", {"voice": "Kore", "language": "en", "lines": [{"text": "Look up, Pip."}]})
    write(
        F,
        "paint.json",
        {
            "images": [
                {"name": "mom", "prompt": "Mom", "about": "Mom, in a green coat", "keep": True},
                {"name": "pip", "prompt": "Pip", "about": "Pip, painted", "keep": True},
            ]
        },
    )
    picture(F.path("images", "mom.jpg"))
    picture(F.path("images", "pip.jpg"))
    picture(F.path("inputs", "upload1.png"))
    F.update(state="done", title="Why the sky is blue")
    return F


def main():
    bad = []

    def check(ok, what, got=None):
        print("%s  %s%s" % ("ok  " if ok else "FAIL", what, "" if ok else "  (%r)" % (got,)))
        if not ok:
            bad.append(what)

    try:
        F = finished()

        # the cast, at once
        st = ideas.state("u:alice", F.id)
        c = st["cast"]
        check(
            [(m["name"], m["painted"]) for m in c]
            == [("owl", False), ("pip", False), ("mom", True)],
            "the cast: drawn first (with the members they draw), then painted, each name once",
            c,
        )
        check(c[1]["about"] == "Pip, a small orange fox in a blue scarf", "with its description")
        check(
            len(c[0]["about"]) <= ideas.ABOUT_MAX and c[0]["about"].endswith("\u2026"),
            "a long description trimmed to %d characters" % ideas.ABOUT_MAX,
            c[0]["about"],
        )
        check(c[2]["about"] == "Mom, in a green coat", "a painted character's description")
        check(st == {"state": "none", "cast": c}, "none asked: none, and nothing else", st)
        names = {m["name"] for m in c}
        got = fromfilm.seed("u:alice", "p-aaaaaaaaaa", F.id)
        check(
            names == set(got["cast"]) | set(got["painted"]),
            "the same characters fromfilm.seed copies into a project",
            got,
        )

        E = Film.create("no characters", 5, "drawn", client="u:alice")
        write(E, "film.js", "SK.film({ duration: 5, draw(t) {} });")
        E.update(state="done")
        check(ideas.state("u:alice", E.id)["cast"] == [], "a film with no cast: an empty list")

        for client, film_id, status, what in [
            ("u:bob", F.id, 404, "someone else's film is not found"),
            ("u:alice", "studio-nope", 404, "nor one that does not exist"),
            ("u:alice", "", 404, "nor no film at all"),
        ]:
            for how, call in [("state", ideas.state), ("start", ideas.start)]:
                try:
                    call(client, film_id)
                    check(False, "%s: %s" % (how, what))
                except fromfilm.FromFilmError as e:
                    check(e.status == status, "%s: %s" % (how, what), e.status)
        U = Film.create("not done yet", 5, "drawn", client="u:alice")
        for how, call in [("state", ideas.state), ("start", ideas.start)]:
            try:
                call("u:alice", U.id)
                check(False, "%s: an unfinished film is refused" % how)
            except fromfilm.FromFilmError as e:
                check(e.status == 409, "%s: an unfinished film is refused" % how, e.status)

        # what Claude is asked
        mat = ideas.material(F)
        text = ideas.ask_text(mat)
        for want, what in [
            ("Pip learns why the sky is blue", "the person's idea"),
            ("children of 4 to 6", "who it was made for"),
            ("Look up, Pip.", "the narration"),
            ("- pip: Pip, a small orange fox", "the cast by name, described"),
            ("- mom: Mom, in a green coat", "the painted cast too"),
            ("episode 2", "for episode 2"),
            ("Never this film told again", "and never this film again"),
            ("at most 160 characters", "one short sentence each"),
            ("narration's language (en)", "in the person's language, else the narration's"),
            ('{"style": "...", "ideas": [{"idea": "...", "still": "..."}', "the answer's shape"),
            ("never by their name", "a still describes the characters, never names them"),
            ("Nothing written in it", "and has no words in it"),
        ]:
            check(want in text, "the ask has %s" % what)
        seen = fromfilm.images(F, mat)
        check(
            len(seen) == 1 and "Image 1 is the person's own picture" in ideas.ask_text(mat),
            "Claude sees the person's picture, named in the ask",
        )

        # the answer held to its shape
        check(
            ideas.clean({"ideas": [' "Pip  finds\na kite" ', "1. Mom bakes bread", "- Owl sleeps"]})
            == ["Pip finds a kite", "Mom bakes bread", "Owl sleeps"],
            "one line each, with no quotes, numbers or bullets",
        )
        long = "Pip " + "and the wind " * 20
        out = ideas.clean({"ideas": [long, "b", "c"]})
        check(
            len(out[0]) <= ideas.IDEA_MAX and out[0].endswith("wind"),
            "a long idea cut after a whole word",
            out[0],
        )
        check(
            ideas.clean({"ideas": ["a", "b", "c", "d"]}) == ["a", "b", "c"], "never more than three"
        )
        for d, what in [
            ({"ideas": ["a", "A", "b"]}, "a duplicate leaves two: refused"),
            ({"ideas": ["a", " ", "b", None]}, "empties leave two: refused"),
            ({"ideas": "a, b, c"}, "not a list: refused"),
            ({}, "no ideas: refused"),
            (None, "no answer: refused"),
        ]:
            try:
                ideas.clean(d)
                check(False, what)
            except ValueError:
                check(True, what)

        # each idea's still, and the film's look
        d = {
            "style": "Soft crayon " * 40,
            "ideas": [
                {"idea": "Pip flies a kite", "still": "A small orange fox runs with a red kite."},
                "Mom plants a seed",
                {"idea": "pip flies a kite", "still": "the same again"},
                {"idea": "Owl counts the stars", "still": 7},
            ],
        }
        check(
            ideas.clean(d) == ["Pip flies a kite", "Mom plants a seed", "Owl counts the stars"],
            "ideas with stills, or plain: the same three ideas",
        )
        p = ideas.plan(d)
        check(
            p["stills"] == ["A small orange fox runs with a red kite.", "", ""]
            and len(p["style"]) <= ideas.STYLE_MAX,
            "one still for each idea kept ('' where none), the look in one line",
            p,
        )

        # written in the background, with Claude stubbed
        asked = []

        async def answer(*a, **k):
            asked.append(a)
            return {
                "ideas": ["Pip flies a kite", "Mom plants a seed", "Owl counts the stars"]
            }, 0.01

        async def fails(*a, **k):
            raise RuntimeError("no answer")

        async def started(F):
            """start() as a server's handler calls it; -> (what it answered, the task)."""
            before = set(ideas.TASKS)
            st = ideas.start("u:alice", F.id)
            new = ideas.TASKS - before
            if new:
                await asyncio.gather(*new)
            return st, new

        real = ytdraft.ask_json
        try:
            ytdraft.ask_json = answer
            st, new = asyncio.run(started(F))
            check(
                st["state"] == "writing" and "ideas" not in st and st["cast"] == c and new,
                "asked: writing at once, with the cast",
                st,
            )
            st = ideas.state("u:alice", F.id)
            check(
                st
                == {
                    "state": "done",
                    "ideas": answer_ideas(),
                    "pictures": {"state": "none", "urls": [None, None, None]},
                    "cast": c,
                },
                "written: done, with exactly the three ideas; media off: nothing painted",
                st,
            )
            check(
                asked[0][5] == ideas.EFFORT == "low" and asked[0][6] == ideas.WRITER,
                "one call, at low effort, as the series' writer",
            )
            on_disk = json.load(open(ideas.state_path(F), encoding="utf-8"))
            check(
                on_disk["state"] == "done" and on_disk["cost_usd"] == 0.01 and "at" in on_disk,
                "kept in the film's series_ideas.json, with its cost",
                on_disk,
            )
            st, new = asyncio.run(started(F))
            check(not new and st["state"] == "done" and len(asked) == 1, "done: asked again, none")

            ideas.TASKS.clear()
            with open(ideas.state_path(F), "w", encoding="utf-8") as f:
                json.dump({"state": "writing", "at": datetime.now().isoformat()}, f)
            st, new = asyncio.run(started(F))
            check(not new and st["state"] == "writing", "writing: asked again, nothing restarted")

            old = (datetime.now() - timedelta(seconds=ideas.WRITING_MAX_S + 5)).isoformat()
            with open(ideas.state_path(F), "w", encoding="utf-8") as f:
                json.dump({"state": "writing", "at": old}, f)
            st = ideas.state("u:alice", F.id)
            check(
                st == {"state": "failed", "error": ideas.FAILED, "cast": c},
                "still writing long after its server went away: failed",
                st,
            )

            ytdraft.ask_json = fails
            os.remove(ideas.state_path(F))
            asyncio.run(started(F))
            st = ideas.state("u:alice", F.id)
            check(
                st == {"state": "failed", "error": "The ideas were not written.", "cast": c},
                "a failed ask: failed",
                st,
            )
            ytdraft.ask_json = answer
            st, new = asyncio.run(started(F))
            check(
                new and ideas.state("u:alice", F.id)["state"] == "done",
                "failed: asked again, written again",
            )
        finally:
            ytdraft.ask_json = real

        pictures(check, F)
        asyncio.run(routes(check, F, U, answer))
    finally:
        import shutil

        shutil.rmtree(HOME, ignore_errors=True)

    print("\n%d failed" % len(bad) if bad else "\nall passed")
    sys.exit(1 if bad else 0)


def pictures(check, F):
    """The stills: painted by a stubbed Muse in the step's own function, then the whole of paint()
    with the step and the upload stubbed."""
    import media
    from io import BytesIO

    from PIL import Image

    painted = []

    class Muse:
        @staticmethod
        def full_prompt(spec, im):
            return "%s.\n\n%s" % (spec["style"], im["prompt"])

        @staticmethod
        def paint_openrouter(prompt, model, ref=None, style_ref=None, **k):
            painted.append((prompt, model, ref, style_ref))
            if "fails" in prompt:
                raise RuntimeError("no picture")
            buf = BytesIO()
            Image.new("RGB", (1536, 1024), "#88aa33").save(buf, "PNG")
            return buf.getvalue(), {"cost_usd": 0.01}

    real_sp = ideas._sp
    ideas._sp = lambda: Muse
    try:
        j = ideas.job(F, {"style": "Crayon on paper", "stills": ["A fox", "", "fails"]})
        check(
            j["refs"] == [F.path("images", "mom.jpg"), F.path("images", "pip.jpg")],
            "its painted characters as references",
            j["refs"],
        )
        got = ideas.paint_job(j, log=lambda *a: None)
        files = got["files"]
        check(
            files[0] and files[0].startswith("still-1-") and files[1:] == [None, None],
            "painted where there are words; one failing leaves the others",
            files,
        )
        with Image.open(os.path.join(j["dir"], files[0])) as im:
            check(im.size == (ideas.PICTURE_W, ideas.PICTURE_H), "small and 16:9", im.size)
        check(
            painted[0][1] == "meta/muse-image" and painted[0][0].startswith("Crayon on paper."),
            "by Muse, in the film's look",
            painted[0][:2],
        )
        check(got["cost_usd"] == 0.01, "its cost", got)
    finally:
        ideas._sp = real_sp

    # paint(), with the step and the upload stubbed
    async def step(j):
        return {"files": ["still-1-aa.jpg", None, "still-3-cc.jpg"], "cost_usd": 0.02}

    async def broken(j):
        raise RuntimeError("the painting step failed")

    async def publish_one(film, name, ctype, out=None, rev=None, timeout=300):
        return "https://media.test/%s/%s" % (film.id, name)

    real = (ideas.paint_step, media.publish_one, media.enabled)
    try:
        base = {"state": "done", "at": ideas._now(), "ideas": answer_ideas()}
        films_write = ideas.films._write_json
        films_write(
            ideas.state_path(F),
            {
                **base,
                "plan": {"style": "x", "stills": ["a", "b", "c"]},
                "pictures": {"state": "painting", "at": ideas._now()},
            },
        )
        st = ideas.state("u:alice", F.id)
        check(st["pictures"] == {"state": "painting", "urls": [None] * 3}, "painting: said so", st)
        old = (datetime.now() - timedelta(seconds=ideas.PAINTING_MAX_S + 5)).isoformat()
        films_write(ideas.state_path(F), {**base, "pictures": {"state": "painting", "at": old}})
        check(
            ideas.state("u:alice", F.id)["pictures"]["state"] == "failed",
            "still painting long after its server went away: failed",
        )
        ideas.paint_step, media.publish_one = step, publish_one
        asyncio.run(ideas.paint(F))
        st = ideas.state("u:alice", F.id)
        check(
            st["pictures"]
            == {
                "state": "done",
                "urls": [
                    "https://media.test/%s/still-1-aa.jpg" % F.id,
                    None,
                    "https://media.test/%s/still-3-cc.jpg" % F.id,
                ],
            }
            and st["ideas"] == answer_ideas(),
            "painted and put online: each idea's address, null for one that did not come",
            st,
        )
        ideas.paint_step = broken
        asyncio.run(ideas.paint(F))
        check(
            ideas.state("u:alice", F.id)["pictures"] == {"state": "failed", "urls": [None] * 3},
            "the step failing: failed, and the ideas stand",
        )

        # written with media on: painting at once, then painted
        async def answer(*a, **k):
            return {
                "style": "Crayon",
                "ideas": [{"idea": t, "still": "still of " + t} for t in answer_ideas()],
            }, 0.01

        seen = []

        async def step_seen(j):
            seen.append(json.load(open(ideas.state_path(F), encoding="utf-8")))
            return await step(j)

        real_ask = ytdraft.ask_json
        ytdraft.ask_json, ideas.paint_step, media.enabled = answer, step_seen, lambda: True
        try:
            os.remove(ideas.state_path(F))
            asyncio.run(ideas.write("u:alice", F.id))
        finally:
            ytdraft.ask_json = real_ask
        check(
            seen
            and seen[0]["pictures"]["state"] == "painting"
            and seen[0]["plan"]["stills"][0] == "still of Pip flies a kite",
            "the ideas kept first, painting, with what to paint",
            seen,
        )
        check(ideas.state("u:alice", F.id)["pictures"]["state"] == "done", "then painted")
    finally:
        ideas.paint_step, media.publish_one, media.enabled = real


def answer_ideas():
    return ["Pip flies a kite", "Mom plants a seed", "Owl counts the stars"]


async def routes(check, F, U, answer):
    """POST and GET /api/library/ideas through aiohttp, as the site asks (its client in
    X-Client-Ip), on an app with only these two routes (the whole server is test_server.py's)."""
    import server
    from aiohttp import web
    from aiohttp.test_utils import TestClient, TestServer

    app = web.Application()
    app.router.add_post("/api/library/ideas", server.series_ideas)
    app.router.add_get("/api/library/ideas", server.series_ideas_state)
    me, bob = {"X-Client-Ip": "u:alice"}, {"X-Client-Ip": "u:bob"}
    os.remove(ideas.state_path(F))
    real, mode = ytdraft.ask_json, server.MODE
    ytdraft.ask_json, server.MODE = answer, "serving"
    try:
        async with TestClient(TestServer(app)) as c:
            r = await c.get("/api/library/ideas?film=" + F.id, headers=me)
            body = await r.json()
            check(
                r.status == 200 and body["state"] == "none" and len(body["cast"]) == 3,
                "GET: none, with the cast",
                body,
            )
            r = await c.post("/api/library/ideas", json={"film": F.id}, headers=me)
            body = await r.json()
            check(r.status == 202 and body["state"] == "writing", "POST: 202, writing", body)
            await asyncio.gather(*ideas.TASKS)
            r = await c.get("/api/library/ideas?film=" + F.id, headers=me)
            body = await r.json()
            check(
                r.status == 200 and body["state"] == "done" and body["ideas"] == answer_ideas(),
                "GET: done, with the three ideas",
                body,
            )
            for how, call in [
                ("POST", lambda h, f: c.post("/api/library/ideas", json={"film": f}, headers=h)),
                ("GET", lambda h, f: c.get("/api/library/ideas?film=" + f, headers=h)),
            ]:
                r = await call(bob, F.id)
                check(
                    r.status == 404 and "error" in await r.json(),
                    "%s: another's film, 404" % how,
                )
                r = await call(me, U.id)
                check(r.status == 409, "%s: an unfinished film, 409" % how, r.status)
            server.MODE = "stopping"
            r = await c.post("/api/library/ideas", json={"film": F.id}, headers=me)
            check(r.status == 503, "POST while the server stops: 503", r.status)
    finally:
        ytdraft.ask_json, server.MODE = real, mode


if __name__ == "__main__":
    main()
