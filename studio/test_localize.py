#!/usr/bin/env python
"""A finished film in another language (studio/localize.py, kitcut.ai's Translate), end to end
through the API with the film itself stubbed: no Claude, no voice, seconds.

    python studio/test_localize.py

Covers: what a translation is given of the original (its code, pictures, cast, engine, music,
voice; never its narration takes, renders, YouTube drafts, share, notes or record) and what its
record says; the refusals (another's film, not finished, a new version being made, own voice, a
template, scene by scene, people, no narration, its own language, a language it has, Russian and
any language not offered); asking twice with one key is one film; Claude's first message; a
narration left untranslated fails, words left on screen get a turn; a film made in another
language is not an episode's next one; and the YouTube draft's language and "fresh".
"""

import os
import sys
import json
import asyncio
import tempfile

HOME = tempfile.mkdtemp(prefix="studio-localize-test-")
os.environ["STUDIO_HOME"] = HOME
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server  # noqa: E402 -- imports agent, which imports _env first
import agent  # noqa: E402
import episode  # noqa: E402
import localize  # noqa: E402
import store  # noqa: E402
import ytdraft  # noqa: E402
from film import Film, _write_json  # noqa: E402

from aiohttp.test_utils import TestClient, TestServer  # noqa: E402

TOKEN = "test-token"
ALICE, BOB = "u:" + "a" * 24, "u:" + "b" * 24
LINES = [
    {"text": "Bees visit thousands of flowers every single day."},
    {"text": "They carry nectar home inside a second stomach."},
    {"text": "Then they fan it with their wings until it thickens."},
]


def touch(p, body="x"):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(body)
    return p


def original(client=ALICE, **rec):
    """A finished, narrated film from an idea, with everything a made film has in its folder."""
    f = Film.create("How bees make honey", 30, "drawn", client=client)
    touch(f.path("film.js"), 'SK.text("How bees make honey", {size: 64});\nconst c = "#ffcc00";\n')
    touch(f.path("cast", "bee.js"), "export default {}")
    touch(f.path("images", "hive.png"))
    touch(f.path("music", "score.json"), "{}")
    touch(f.path("sfx.json"), "[]")
    _write_json(f.path("vo.json"), {"language": "en", "voice": "kc-warm", "lines": LINES})
    touch(f.path("audio", "vo", "timeline.json"), '{"lines": []}')
    touch(f.path("audio", "vo", "line1.mp3"))
    touch(f.path("outputs", "film.mp4"))
    touch(f.path("web", "film_web.mp4"))
    touch(f.path("youtube", "UC" + "x" * 22, "draft.json"), '{"title": "How bees make honey"}')
    touch(f.path("share", "card.jpg"))
    touch(f.path("notes", "n1.json"), "{}")
    touch(f.path("versions", "v1", "film.js"))
    f.update(**{"state": "done", "ok": True, "title": "How bees make honey", "version": 2, **rec})
    return f


async def main():
    agent.STORE = store.MemoryStore()
    started = []
    server.start = lambda f, finish_only=False, resume=None: started.append(f.id)
    bad = []

    def check(ok, what, detail=""):
        print("%s  %s%s" % ("ok  " if ok else "FAIL", what, "" if ok else "  -- %s" % detail))
        if not ok:
            bad.append(what)

    def refused(spec, client=ALICE):
        try:
            localize.check(spec, client)
        except localize.Refused as e:
            return e.status, e.reason
        return None

    src = original()
    spec = {"from": src.id, "version": 2, "language": "es", "key": "hold-1"}

    # ---- what is refused, before anything is made
    check(refused(spec) is None, "a finished, narrated film of one's own can be translated")
    check(refused(spec, BOB) == (404, "localize"), "another's film is no such film")
    for lang in ("ru", "RU", "rus", "russian", "ru-RU", "ja", "xx", ""):
        check(
            refused({**spec, "language": lang}) == (400, "language"),
            "%r is not a language it is made in" % lang,
        )
    check(refused({**spec, "language": "en"}) == (409, "same"), "never its own language")
    check(refused({**spec, "key": "../x"}) == (400, "localize"), "a key is the site's hold id")
    for what, rec, reason in (
        ("not finished", {"state": "running"}, "state"),
        ("its own voice", {"narrator": {"source": "elevenlabs"}}, "own_voice"),
        ("a template's", {"template": {"id": "t-x", "version": 1}}, "template"),
        ("scene by scene", {"mode": "scenes"}, "long"),
        ("people from photos", {"people": [{"name": "Ann"}]}, "people"),
        ("no narration", {"narration": False}, "no_voice"),
    ):
        f = original(**rec)
        check(
            refused({**spec, "from": f.id}) == (409, reason),
            "a film %s is refused (%s)" % (what, reason),
            refused({**spec, "from": f.id}),
        )

    # ---- through the API
    async with TestClient(TestServer(server.make_app(TOKEN))) as c:
        me = {"Authorization": "Bearer " + TOKEN, "X-Client-Ip": ALICE}
        bob = {**me, "X-Client-Ip": BOB}

        async def ask(body, headers=me):
            r = await c.post("/api/films", json=body, headers=headers)
            return r.status, await r.json()

        st, j = await ask({"localize": {**spec, "language": "ru"}})
        check(st == 400 and j.get("reason") == "language", "Russian is refused at once", (st, j))
        st, j = await ask({"localize": spec}, bob)
        check(st == 404, "another's film is refused", (st, j))
        n_films = len(Film.all())
        st, j = await ask({"localize": spec})
        check(
            st == 202 and j.get("localized", {}).get("from") == src.id and started == [j.get("id")],
            "a translation starts as a film of its own",
            (st, j, started),
        )
        new = Film.open(j.get("id"))
        check(len(Film.all()) == n_films + 1 and new is not None, "one new film")
        rec = new.record()
        check(
            rec.get("localized")
            == {"from": src.id, "version": 2, "language": "es", "key": "hold-1"}
            and rec.get("client") == ALICE
            and rec.get("prompt") == "How bees make honey"
            and new.length == 30,
            "its record says what it is a translation of, with the original's idea and length",
            rec,
        )
        has = lambda *p: os.path.exists(new.path(*p))  # noqa: E731
        check(
            all(
                has(p)
                for p in (
                    "film.js",
                    "cast/bee.js",
                    "images/hive.png",
                    "music/score.json",
                    "sfx.json",
                )
            ),
            "it is given the original's code, cast, pictures, music and sounds",
        )
        check(
            not any(
                has(p)
                for p in (
                    "audio/vo/line1.mp3",
                    "outputs/film.mp4",
                    "web/film_web.mp4",
                    "youtube",
                    "share",
                    "notes",
                    "versions/v1",
                )
            ),
            "never the original's narration takes, renders, YouTube drafts, share, notes or versions",
            sorted(os.listdir(new.dir)),
        )
        with open(new.path("vo.json"), encoding="utf-8") as fh:
            vo = json.load(fh)
        with open(new.path("localize", "vo.json"), encoding="utf-8") as fh:
            was = json.load(fh)
        check(
            vo.get("language") == "es"
            and vo.get("voice") == "kc-warm"
            and vo.get("lines") == LINES,
            "its narration: the same voice and lines, its language Spanish, to translate",
            vo,
        )
        check(
            was.get("language") == "en" and has("localize", "timeline.json"),
            "the original's narration and word times are there to read",
        )
        with open(src.path("youtube", "UC" + "x" * 22, "draft.json"), encoding="utf-8") as fh:
            check("bees" in fh.read(), "the original is untouched")

        st, j2 = await ask({"localize": spec})
        check(
            st == 202 and j2.get("id") == new.id and len(started) == 1,
            "asked twice with one key: the same film",
            (st, j2),
        )
        st, j3 = await ask({"localize": {**spec, "key": "hold-2"}})
        check(
            st == 409 and j3.get("reason") == "exists" and j3.get("film") == new.id,
            "a language it has, being made, is not made twice",
            (st, j3),
        )
        st, j4 = await ask(
            {"localize": {**spec, "from": new.id, "language": "de", "key": "hold-3"}}
        )
        check(
            st == 409 and j4.get("reason") == "state",
            "a translation being made is not a source",
            j4,
        )
        st, j5 = await ask({"localize": {**spec, "key": "hold-4"}}, bob)
        check(st == 404, "another asking with another's key gets nothing", (st, j5))

    # ---- Claude's part
    msg = localize.ask(new)
    check(
        "Translate the film into Spanish" in msg and "never paint" in msg and "3 lines" in msg,
        "the first message: translate the words said and shown, keep everything else",
        msg[:200],
    )
    check(agent.ask(new) == msg if hasattr(agent, "ask") else True, "the agent asks it so")
    check(localize.untranslated(new), "a narration left as the original's is untranslated")
    _write_json(
        new.path("vo.json"),
        {
            **vo,
            "lines": [
                {"text": "Las abejas visitan miles de flores cada día."},
                {"text": "Llevan el néctar a casa en un segundo estómago."},
                {"text": "Luego lo abanican con sus alas hasta que espesa."},
            ],
        },
    )
    check(not localize.untranslated(new), "a translated narration is not")
    check(not localize.untranslated(src), "an original is never untranslated")
    check(
        localize.leftovers(new) == ["How bees make honey"],
        "words of the original still on screen are found (never code)",
        localize.leftovers(new),
    )
    touch(new.path("film.js"), 'SK.text("Cómo hacen miel las abejas", {size: 64});\n')
    check(localize.leftovers(new) == [], "none once translated")
    check(episode.wanted(new) is False, "a translation is never an episode's next one")

    # ---- the YouTube draft
    check(
        ytdraft.options({"language": "es", "fresh": True}) == {"language": "es", "fresh": True},
        "a draft ask may say the film's language and fresh",
    )
    check(
        ytdraft.options({"language": "ru"}) == {}
        and ytdraft.options({"language": "ru-RU", "fresh": "yes"}) == {}
        and ytdraft.options({"language": "<b>"}) == {}
        and ytdraft.options(None) == {},
        "never Russian, nothing else",
    )
    check(
        ytdraft.material(new).get("language") == "es",
        "a translation's draft is written in its language",
        ytdraft.material(new).get("language"),
    )

    print("\n%d failed" % len(bad) if bad else "\nall passed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
