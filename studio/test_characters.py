#!/usr/bin/env python
"""A project's painted characters (library.py) and the characters a prompt names (@name), without
Claude or a painter: python studio/test_characters.py

Covers: a ready-made character put in (named, described, big enough, never over a drawn member,
at most CHARACTERS), its next version, its listing and thumbnail, its Remove and its return; an
episode getting each as inputs/cast_<name>.* and in its note (paint from it; keep a new one);
the check (validate.py) taking "ref": "cast_<name>" and lists of refs, and holding a kept
painting to its name, its "about", the cap and a project; a finished episode's kept painting
joining the cast, a later one making its next version, a stale one and a drawing never replacing
it; @name in a prompt (found, a typo said before anything is made, an e-mail and a handle left
alone), the film told who it must have, and its paintings held to their pictures. A throwaway
STUDIO_HOME, no network.
"""

import os
import sys
import json
import shutil
import asyncio
import tempfile

HOME = tempfile.mkdtemp(prefix="studio-characters-test-")
os.environ["STUDIO_HOME"] = HOME
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import library  # noqa: E402 -- imports _env first
import server  # noqa: E402
import validate  # noqa: E402
from film import Film  # noqa: E402
from PIL import Image  # noqa: E402

FAILS = []
CL, P1 = "u:alice", "p-cccccccccc"
PROJECT = {"id": P1, "name": "Brella", "brief": "Families and umbrellas."}


def check(ok, what, detail=""):
    print(("ok   " if ok else "FAIL ") + what + ("" if ok else "  " + str(detail)[:300]))
    if not ok:
        FAILS.append(what)


def picture(name, size=(600, 800), colour=(200, 120, 40), fmt="PNG"):
    p = os.path.join(HOME, name)
    Image.new("RGB", size, colour).save(p, fmt)
    return p


def refused(fn, status, words):
    try:
        fn()
    except library.PictureError as e:
        return e.status == status and words in e.text
    return False


def episode(prompt, look="painted", characters=None):
    f = Film.create(prompt, 5, look, client=CL, project=PROJECT)
    if characters:
        f.update(characters=characters)
    library.seed(f)
    return f


def paint(f, images):
    with open(f.path("paint.json"), encoding="utf-8") as fh:
        p = json.load(fh)
    p["images"] = images
    with open(f.path("paint.json"), "w", encoding="utf-8") as fh:
        json.dump(p, fh)
    return p


def painted(f, name, colour):
    """A painting sketch-paint.py would leave: images/<name>.jpg."""
    os.makedirs(f.path("images"), exist_ok=True)
    Image.new("RGB", (1920, 1280), colour).save(f.path("images", name + ".jpg"), "JPEG")


def finish(f):
    f.update(state="done")
    return library.keep(f, library.changes(f), {})


def characters():
    mom = picture("mom.png")
    for args, status, words in (
        (("Mom", "Mom", mom), 400, "lowercase"),
        (("mom", "  ", mom), 400, "Say who"),
        (("mom", "x" * 201, mom), 400, "at most 200"),
        (("mom", "Mom", picture("small.png", (300, 900))), 400, "512 px"),
        (("mom", "Mom", os.path.join(HOME, "nothing.png")), 400, "could not be read"),
    ):
        check(
            refused(lambda a=args: library.add_character(CL, P1, *a), status, words),
            "a character refused: %s" % words,
        )
    check(
        refused(lambda: library.add_character("1.2.3.4", P1, "mom", "Mom", mom), 404, "project"),
        "and for a visitor",
    )
    e = library.add_character(CL, P1, "mom", "Mom, mid-30s, yellow raincoat", mom)
    check(
        e["painted"] and e["version"] == 1 and e["thumb"] and e["about"].startswith("Mom"),
        "a ready-made character joins the cast, painted",
        e,
    )
    listed = {c["name"]: c for c in library.listing(CL, P1)["cast"]}
    check(listed.get("mom", {}).get("painted") is True, "the Cast lists it as painted", listed)
    check(library.thumb_of(CL, "mom", P1), "with its thumbnail")
    e2 = library.add_character(
        CL, P1, "mom", "Mom, mid-30s, green raincoat", picture("mom2.jpg", fmt="JPEG")
    )
    d = os.path.join(library.dir_of((CL, P1)), "cast", "mom")
    check(
        e2["version"] == 2 and os.path.exists(os.path.join(d, "v2.jpg")) and "green" in e2["about"],
        "the same name again is its next version",
        (e2, os.listdir(d)),
    )
    # a drawn member's name is not a character's
    with library._lock((CL, P1)):
        idx = library.load((CL, P1))
        code = "SK.cast.owl = { about: 'an owl', draw(x, y) {} };\n"
        os.makedirs(os.path.join(library.dir_of((CL, P1)), "cast", "owl"), exist_ok=True)
        with open(os.path.join(library.dir_of((CL, P1)), "cast", "owl", "v1.js"), "w") as fh:
            fh.write(code)
        idx["cast"]["owl"] = {"version": 1, "hash": library._hash(code), "about": "an owl"}
        library._save((CL, P1), idx)
    check(
        refused(lambda: library.add_character(CL, P1, "owl", "Owl", mom), 409, "drawn member"),
        "never over a drawn member",
    )
    for i in range(library.CHARACTERS - 1):
        library.add_character(CL, P1, "kid%d" % i, "Kid %d" % i, mom)
    check(
        refused(
            lambda: library.add_character(CL, P1, "extra", "One more", mom),
            409,
            "up to %d" % library.CHARACTERS,
        ),
        "at most %d painted characters" % library.CHARACTERS,
    )
    check(
        library.add_character(CL, P1, "kid0", "Kid 0, older", mom)["version"] == 2,
        "a full cast still takes a character's next version",
    )
    check(library.delete(CL, "kid10", P1), "Remove takes one out")
    check(
        "kid10" not in {c["name"] for c in library.listing(CL, P1)["cast"]}
        and library.thumb_of(CL, "kid10", P1) is None,
        "and it is gone from the Cast",
    )
    back = library.add_character(CL, P1, "kid10", "Kid 10 again", mom)
    check(back["version"] == 2, "a removed name put in again comes back as its next version")
    library.delete(CL, "kid10", P1)
    for i in range(1, library.CHARACTERS - 1):  # all but kid0, for the episodes below
        library.delete(CL, "kid%d" % i, P1)


def seeded():
    f = episode("Mom opens the umbrella")
    got = f.record()["library"]
    p = {c["name"]: c for c in got.get("painted") or []}
    check(
        set(p) == {"mom", "kid0"} and os.path.exists(f.path(*p["mom"]["file"].split("/"))),
        "an episode gets each live character in inputs/",
        got.get("painted"),
    )
    check(
        p["mom"]["file"] == "inputs/cast_mom.jpg" and "green" in p["mom"]["about"],
        "as cast_<name>, its latest version",
        p.get("mom"),
    )
    with open(f.manifest, encoding="utf-8") as fh:
        m = json.load(fh)
    check(m["images"].get("cast_mom") == "inputs/cast_mom.jpg", "in the manifest's images")
    check(
        not os.path.exists(f.path("cast", "mom.js")) and os.path.exists(f.path("cast", "owl.js")),
        "and never as code in cast/, beside the drawn members",
    )
    note = library.note(f)
    check(
        "cast_mom: Mom, mid-30s, green raincoat" in note
        and '"ref": "cast_<name>"' in note
        and '"keep": true' in note,
        "its note: who they are, paint from them, keep a new one",
        note,
    )
    drawn = episode("Mom, drawn", look="drawn")
    note = library.note(drawn)
    check(
        "SK.image('cast_<name>'" in note and '"keep": true' not in note,
        "a drawn episode is told to draw them as they are, and keeps none",
        note,
    )
    return f


def checks(f):
    cast = validate._cast_of(f)
    base = {"backend": "muse", "images": []}

    def problems(images, c=cast):
        return validate._paint(dict(base, images=images), 30, ["paintings"], f.dir, c)

    ok = [
        {"name": "sheet", "prompt": "a", "ref": "cast_mom"},
        {"name": "park", "prompt": "b", "ref": ["cast_mom", "cast_kid0", "sheet"]},
    ]
    check(problems(ok) == [], "a ref to a character, and a list of refs", problems(ok))
    for bad, words in (
        ({"name": "x", "prompt": "a", "ref": ["cast_mom"] * 2}, "twice"),
        (
            {"name": "x", "prompt": "a", "ref": ["sheet", "cast_mom", "cast_kid0", "a", "b"]},
            "up to",
        ),
        ({"name": "x", "prompt": "a", "ref": []}, "a name, or a list"),
        ({"name": "x", "prompt": "a", "ref": "cast_nobody"}, "painted characters (cast_<name>)"),
        ({"name": "x", "prompt": "a", "ref": ["x"]}, "must name another image"),
        ({"name": "x", "prompt": "a", "keep": "yes"}, "keep is true or false"),
        ({"name": "x-1", "prompt": "a", "keep": True, "about": "X"}, "under its name"),
        ({"name": "dad", "prompt": "a", "keep": True}, 'give it "about"'),
        ({"name": "owl", "prompt": "a", "keep": True, "about": "an owl"}, "drawn member"),
    ):
        out = problems([ok[0], bad])
        check(any(words in o for o in out), "the check refuses: %s" % words, out)
    out = problems([{"name": "dad", "prompt": "a", "keep": True, "about": "Dad"}], None)
    check(any("a project's episodes" in o for o in out), "keep outside a project is refused", out)
    full = dict(cast, painted=["c%d" % i for i in range(library.CHARACTERS)])
    out = problems([{"name": "dad", "prompt": "a", "keep": True, "about": "Dad"}], full)
    check(
        any("holds %d" % library.CHARACTERS in o for o in out),
        "a kept painting past the cap is refused",
        out,
    )
    check(validate.CHARACTERS == library.CHARACTERS, "the check and the library hold the same cap")
    out = problems([{"name": "c3", "prompt": "a", "keep": True, "about": "C3, again"}], full)
    check(out == [], "a full cast takes a character's next version", out)


def kept():
    a = episode("Dad arrives")
    paint(
        a,
        [
            {"name": "dad", "prompt": "Dad alone", "keep": True, "about": "Dad, tall, blue coat"},
            {"name": "street", "prompt": "a street", "ref": ["dad", "cast_mom"]},
        ],
    )
    painted(a, "dad", (10, 20, 200))
    painted(a, "street", (90, 90, 90))
    with open(a.path("film.js"), "w", encoding="utf-8") as fh:
        fh.write("SK.image('cast_kid0', 0, 0, 400);\n")
    out = finish(a)
    e = library.load((CL, P1))["cast"].get("dad") or {}
    check(
        out.get("painted") == ["dad"] and e.get("painted") and e.get("from_film") == a.id,
        "a finished episode's kept painting joins the cast",
        (out, e),
    )
    idx = library.load((CL, P1))
    check(
        a.id in idx["cast"]["mom"].get("films", [])
        and a.id in idx["cast"]["kid0"].get("films", []),
        "the characters it painted from, or drew, count it as theirs",
        {n: idx["cast"][n].get("films") for n in ("mom", "kid0")},
    )
    b = episode("Dad in the rain")
    stale = episode("Dad, an older take")
    paint(b, [{"name": "dad", "prompt": "Dad, wet", "keep": True, "about": "Dad, soaked"}])
    painted(b, "dad", (10, 200, 20))
    out = finish(b)
    e = library.load((CL, P1))["cast"]["dad"]
    check(
        out.get("painted") == ["dad"] and e["version"] == 2 and e["about"] == "Dad, soaked",
        "a later episode keeping it again makes its next version",
        (out, e),
    )
    paint(stale, [{"name": "dad", "prompt": "Dad, old", "keep": True, "about": "Dad, old"}])
    painted(stale, "dad", (200, 10, 20))
    out = finish(stale)
    check(
        out.get("painted_refused") == ["dad"]
        and library.load((CL, P1))["cast"]["dad"]["version"] == 2,
        "one started before that version never saves over it",
        out,
    )
    c = episode("a drawing named mom", look="drawn")
    with open(c.path("cast", "mom.js"), "w", encoding="utf-8") as fh:
        fh.write("SK.cast.mom = { about: 'a drawn mom', draw(x, y) {} };\n")
    out = finish(c)
    e = library.load((CL, P1))["cast"]["mom"]
    check(
        "mom" in out.get("painted_refused", []) and e.get("painted") and e["version"] == 2,
        "a drawing never replaces a painted character",
        (out, e),
    )
    check(
        not os.path.isdir(os.path.join(library.dir_of((CL, P1)), library.CLASHED, "mom")),
        "nor is kept as a clash to fold in",
    )


def mentions():
    named, typos = library.mentioned(
        CL, P1, "@mom and @Dad walk; mail a@mom.com, follow @kitcut, and @mom again"
    )
    check(named == ["mom", "dad"] and typos == {}, "@names found, in order, once", (named, typos))
    named, typos = library.mentioned(CL, P1, "@mum and @dad")
    check(named == ["dad"] and typos == {"mum": "mom"}, "a near miss is a typo", (named, typos))
    check(library.mentioned(CL, None, "@mom") == ([], {}), "outside a project: plain text")
    library.delete(CL, "kid0", P1)
    check(library.mentioned(CL, P1, "@kid0")[0] == [], "a removed character is named by nobody")

    class Req:
        headers = {"X-Client-Ip": CL}
        remote, host = "203.0.113.1", "studio.example"

        async def json(self):
            return {"prompt": "@mum opens the umbrella", "project": PROJECT, "look": "painted"}

    server.MODE = "serving"
    r = asyncio.run(server.create(Req()))
    body = json.loads(r.body)
    check(
        r.status == 400
        and body.get("reason") == "characters"
        and "did you mean @mom" in body["error"],
        "a prompt with a typo is answered before any film is made",
        (r.status, body),
    )

    f = episode("@mom and @dad in the park", characters=["mom", "dad"])
    note = library.note(f)
    check(
        "@mom: Mom, mid-30s, green raincoat" in note and '"ref": "cast_dad"' in note,
        "the film is told the characters it must have",
        note,
    )
    cast = validate._cast_of(f)
    out = validate._paint(
        {"images": [{"name": "park", "prompt": "a park", "ref": "cast_mom"}]},
        30,
        ["paintings"],
        f.dir,
        cast,
    )
    check(any("@dad" in o and '"cast_dad"' in o for o in out), "and painted from them all", out)


def main():
    characters()
    f = seeded()
    checks(f)
    kept()
    mentions()
    print("\n%s" % ("all passed" if not FAILS else "%d FAILED" % len(FAILS)))
    shutil.rmtree(HOME, ignore_errors=True)
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
