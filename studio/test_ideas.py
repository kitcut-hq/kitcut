#!/usr/bin/env python
"""The next episode of a finished film, proposed (ideas.py), without Claude:
python studio/test_ideas.py

Covers: the cast a series would carry over (the members the film's code drew, then its painted
characters, each name once, descriptions trimmed), someone else's film and one that does not
exist are not found and an unfinished one is refused, what Claude is asked (the idea, the
audience, the narration, the cast by name, a prompt as typed in the idea box with the cast as
@name, not the narration, and never this film told again), the answer held to its shape (its
paragraphs, a long one cut, an empty one refused), how it stands on disk
(none, writing, done, failed, and a "writing" whose server went away), a second ask starting
nothing while it is being written or is written, and the two routes answering the site's shapes;
its still and the film's look in the same answer, painted by a stubbed Muse (small, 16:9),
put online and kept, "painting" while it works and failed when it went away, and nothing painted
where media copying is off. Everything in a throwaway STUDIO_HOME.
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
        check(
            st
            == {
                "state": "none",
                "picture": {"state": "none", "url": None},
                "cast": c,
            },
            "none asked: none, with the cast",
            st,
        )
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
            ("Write the series' next episode", "one next episode, ready to make"),
            ("Never this film told again", "and never this film again"),
            ("its prompt, as the person would type it into the idea box", "a prompt, as typed"),
            ("Not its narration word for", "not the narration"),
            ("at most %d characters" % ideas.PROMPT_MAX, "at most its length"),
            ("is written as @ and their cast", "the cast written as @name"),
            ("narration's language (en)", "in the person's language, else the narration's"),
            ("never by their name", "a still describes the characters, never names them"),
            ("Nothing written in", "and has no words in it"),
            ('{"prompt": "...", "still": "...", "style": "..."}', "the answer's shape"),
        ]:
            check(want in text, "the ask has %s" % what)
        seen = fromfilm.images(F, mat)
        check(
            len(seen) == 1 and "Image 1 is the person's own picture" in ideas.ask_text(mat),
            "Claude sees the person's picture, named in the ask",
        )

        # the answer held to its shape
        got = ideas.clean({"prompt": '  "@pip finds\na kite.  \n\n  The wind pulls it away." '})
        check(
            got == {"prompt": "@pip finds a kite.\n\nThe wind pulls it away."},
            "its paragraphs kept, each on one line, no quotes around it",
            got,
        )
        long = ideas.clean({"prompt": "Pip flies a kite " * 200})["prompt"]
        check(
            len(long) <= ideas.PROMPT_MAX and long.split()[-1] in ("Pip", "flies", "a", "kite"),
            "a long one cut after a whole word",
        )
        for d, what in [
            ({"prompt": " "}, "an empty prompt: refused"),
            ({"prompt": 3}, "not words: refused"),
            ({}, "nothing: refused"),
            (None, "no answer: refused"),
        ]:
            try:
                ideas.clean(d)
                check(False, what)
            except ValueError:
                check(True, what)
        p = ideas.plan({"still": "A small orange fox runs with a red kite.", "style": "x" * 900})
        check(
            p["stills"] == ["A small orange fox runs with a red kite."]
            and len(p["style"]) <= ideas.STYLE_MAX,
            "its still, and the look in one line",
            p,
        )
        check(ideas.plan({})["stills"] == [""], "no still: nothing to paint")

        # written in the background, with Claude stubbed
        asked = []

        async def answer(*a, **k):
            asked.append(a)
            return answer_proposal(), 0.01

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

        none = {"state": "none", "url": None}
        real = ytdraft.ask_json
        try:
            ytdraft.ask_json = answer
            st, new = asyncio.run(started(F))
            check(
                st["state"] == "writing" and "proposal" not in st and st["cast"] == c and new,
                "asked: writing at once, with the cast",
                st,
            )
            st = ideas.state("u:alice", F.id)
            want = answer_proposal()
            check(
                st
                == {
                    "state": "done",
                    "proposal": want,
                    "picture": none,
                    "cast": c,
                },
                "written: done, with the proposal; media off: nothing painted",
                st,
            )
            check(
                asked[0][5] == ideas.EFFORT == "medium" and asked[0][6] == ideas.WRITER,
                "one call, with care, as the series' writer",
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
                st
                == {
                    "state": "failed",
                    "error": ideas.FAILED,
                    "picture": none,
                    "cast": c,
                },
                "still writing long after its server went away: failed",
                st,
            )

            ytdraft.ask_json = fails
            os.remove(ideas.state_path(F))
            asyncio.run(started(F))
            st = ideas.state("u:alice", F.id)
            check(
                st["state"] == "failed" and st["error"] == "The next episode was not written.",
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
    """The picture: painted by a stubbed Muse in the step's own function, then the whole of
    paint() with the step and the upload stubbed."""
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
        j = ideas.job(F, {"style": "Crayon on paper", "stills": ["A fox"]})
        check(
            j["refs"] == [F.path("images", "mom.jpg"), F.path("images", "pip.jpg")],
            "its painted characters as references",
            j["refs"],
        )
        got = ideas.paint_job(j, log=lambda *a: None)
        files = got["files"]
        check(files[0] and files[0].startswith("still-1-"), "painted", files)
        with Image.open(os.path.join(j["dir"], files[0])) as im:
            check(im.size == (ideas.PICTURE_W, ideas.PICTURE_H), "small and 16:9", im.size)
        check(
            painted[0][1] == "meta/muse-image" and painted[0][0].startswith("Crayon on paper."),
            "by Muse, in the film's look",
            painted[0][:2],
        )
        check(got["cost_usd"] == 0.01, "its cost", got)
        got = ideas.paint_job({**j, "stills": ["fails"]}, log=lambda *a: None)
        check(got["files"] == [None], "a picture that does not come: null", got)
    finally:
        ideas._sp = real_sp

    # paint(), with the step and the upload stubbed
    async def step(j):
        return {"files": ["still-1-aa.jpg"], "cost_usd": 0.01}

    async def broken(j):
        raise RuntimeError("the painting step failed")

    async def publish_one(film, name, ctype, out=None, rev=None, timeout=300):
        return "https://media.test/%s/%s" % (film.id, name)

    real = (ideas.paint_step, media.publish_one, media.enabled)
    try:
        base = {"state": "done", "at": ideas._now(), "proposal": answer_proposal()}
        films_write = ideas.films._write_json
        films_write(
            ideas.state_path(F),
            {
                **base,
                "plan": {"style": "x", "stills": ["a"]},
                "pictures": {"state": "painting", "at": ideas._now()},
            },
        )
        st = ideas.state("u:alice", F.id)
        check(st["picture"] == {"state": "painting", "url": None}, "painting: said so", st)
        old = (datetime.now() - timedelta(seconds=ideas.PAINTING_MAX_S + 5)).isoformat()
        films_write(ideas.state_path(F), {**base, "pictures": {"state": "painting", "at": old}})
        check(
            ideas.state("u:alice", F.id)["picture"]["state"] == "failed",
            "still painting long after its server went away: failed",
        )
        ideas.paint_step, media.publish_one = step, publish_one
        asyncio.run(ideas.paint(F))
        st = ideas.state("u:alice", F.id)
        check(
            st["picture"] == {"state": "done", "url": "https://media.test/%s/still-1-aa.jpg" % F.id}
            and st["proposal"] == answer_proposal(),
            "painted and put online: its address",
            st,
        )
        ideas.paint_step = broken
        asyncio.run(ideas.paint(F))
        check(
            ideas.state("u:alice", F.id)["picture"] == {"state": "failed", "url": None},
            "the step failing: failed, and the proposal stands",
        )

        # written with media on: painting at once, then painted
        async def answer(*a, **k):
            return {**answer_proposal(), "still": "a fox with a kite", "style": "Crayon"}, 0.01

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
            and seen[0]["plan"]["stills"] == ["a fox with a kite"],
            "the proposal kept first, painting, with what to paint",
            seen,
        )
        check(ideas.state("u:alice", F.id)["picture"]["state"] == "done", "then painted")
    finally:
        ideas.paint_step, media.publish_one, media.enabled = real


def answer_proposal():
    return {
        "prompt": "@pip finds a red kite and learns how wind works, with @mom holding the string.",
    }


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
                r.status == 200
                and body["state"] == "done"
                and body["proposal"] == answer_proposal(),
                "GET: done, with the proposal",
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
