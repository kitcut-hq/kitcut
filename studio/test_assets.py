#!/usr/bin/env python
"""A project's scenes and characters, one at a time (assets.py), without Claude:

    python studio/test_assets.py

Covers: a member's page (its versions, which have a picture), a version's picture, going back to
an older version (painted: the old file again as the next version, still a place; drawn: the old
code again, with its pictures), what is refused (no such member, the version in use, one no
longer kept, a member that moved meanwhile), and the versions the library lets go. Everything in a
throwaway STUDIO_HOME; nothing is rendered (put_drawn is given its pictures).
"""

import os
import sys
import shutil
import tempfile

HOME = tempfile.mkdtemp(prefix="studio-assets-test-")
os.environ["STUDIO_HOME"] = HOME
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agent  # noqa: E402, F401 -- imports _env first
import assets  # noqa: E402
import library  # noqa: E402
from film import Film  # noqa: E402
from PIL import Image  # noqa: E402

CL, P1 = "u:assets", "p-assetsabcd"
PROJECT = {"id": P1, "name": "Assets", "brief": ""}
FAILS = []


def check(ok, what, got=None):
    print("%s %s" % ("ok  " if ok else "FAIL", what) + ("" if ok else "\n     %r" % (got,)))
    if not ok:
        FAILS.append(what)


def refused(fn, status, words):
    try:
        fn()
    except library.PictureError as e:
        return e.status == status and words in e.text
    return False


def picture(name, colour, size=(1280, 720)):
    p = os.path.join(HOME, name)
    Image.new("RGB", size, colour).save(p, "PNG")
    return p


def room(colour):
    return (
        "SK.cast.room = {\n  about: 'The room, %s walls',\n  kind: 'place',\n"
        "  camera: [960, 540, 1],\n  draw(x, y) { SK.wash(SK.S.rect(0, 0, 1920, 1080), '%s'); },\n};\n"
        % (colour, colour)
    )


def painted():
    Film.create("first", 5, "painted", client=CL, project=PROJECT)  # the project's library
    library.add_character(
        CL, P1, "kitchen", "The kitchen, yellow", picture("k1.png", (240, 220, 90)), "place"
    )
    library.add_character(
        CL, P1, "kitchen", "The kitchen, blue", picture("k2.png", (60, 90, 220)), "place"
    )
    got = assets.info(CL, P1, "kitchen")
    check(
        got["kind"] == "place"
        and got["version"] == 2
        and got["versions"]
        == [
            {"n": 2, "picture": True, "current": True},
            {"n": 1, "picture": True, "current": False},
        ],
        "a member's page: its versions, newest first",
        got,
    )
    p1, p2 = assets.picture(CL, P1, "kitchen", 1), assets.picture(CL, P1, "kitchen")
    check(
        p1 and p2 and p1.endswith("v1.png") and p2.endswith("v2.png"),
        "a version's picture, and the newest by default",
        (p1, p2),
    )
    check(assets.picture(CL, P1, "kitchen", 9) is None, "no picture of a version that never was")
    check(assets.picture("u:other", P1, "kitchen") is None, "nor for somebody else")
    check(refused(lambda: assets.info(CL, P1, "nobody"), 404, "No such"), "no such member: 404")
    check(
        refused(lambda: assets.restore(CL, P1, "kitchen", 2), 409, "in use"),
        "the version in use is not restored",
    )
    check(
        refused(lambda: assets.restore(CL, P1, "kitchen", 7), 404, "no longer kept"),
        "nor one that is not there",
    )
    got = assets.restore(CL, P1, "kitchen", 1)
    e = library.load((CL, P1))["cast"]["kitchen"]
    check(
        got["version"] == 3
        and e["hash"] == library._bytes_hash(p1)
        and e["kind"] == "place"
        and e["about"] == "The kitchen, blue"
        and e.get("restored") == 1,
        "going back writes the old picture as the next version; still a place",
        (got, e),
    )
    f = Film.create("next", 5, "painted", client=CL, project=PROJECT)
    library.seed(f)
    k = {c["name"]: c for c in f.record()["library"]["painted"]}["kitchen"]
    check(k["hash"] == e["hash"], "the next episode gets the restored one", k)
    for i in range(library.KEEP):
        library.add_character(
            CL, P1, "kitchen", "The kitchen", picture("k%d.png" % (i + 10), (i * 40, 9, 9)), "place"
        )
    got = assets.info(CL, P1, "kitchen")
    check(
        [v["n"] for v in got["versions"]]
        == list(range(got["version"], got["version"] - library.KEEP, -1)),
        "only the last %d versions are held" % library.KEEP,
        got["versions"],
    )


def drawn():
    lib = (CL, P1)
    small, large = Image.new("RGB", (480, 270), (9, 9, 9)), Image.new("RGB", (1280, 720), (9, 9, 9))
    a = assets.member_of("room", room("green"))
    check(a["kind"] == "place" and a["about"].startswith("The room"), "a drawn member read", a)
    wrote = assets.put_drawn(lib, [a], {"room": None}, {"room": small}, {"room": large})
    b = assets.member_of("room", room("red"))
    check(
        refused(lambda: assets.put_drawn(lib, [b], {"room": None}, {}, {}), 409, "meanwhile"),
        "a member that moved since the plan is never written over",
    )
    wrote2 = assets.put_drawn(lib, [b], {"room": a["hash"]}, {"room": small})
    got = assets.info(CL, P1, "room")
    check(
        wrote == {"room": 1}
        and wrote2 == {"room": 2}
        and got["versions"]
        == [
            {"n": 2, "picture": True, "current": True},
            {"n": 1, "picture": True, "current": False},
        ],
        "drawn versions: the newest shows its thumbnail, an older one its own picture",
        got,
    )
    check(
        assets.picture(CL, P1, "room").endswith("thumb.png")
        and assets.picture(CL, P1, "room", 1).endswith("v1.png"),
        "and those are the files served",
    )
    # going back draws the old code again: stand in for the render
    real = assets.draw
    assets.draw = lambda d, idx, items, episode, sizes=(480,): {s: {"room": large} for s in sizes}
    try:
        f = Film.create("an episode", 5, "drawn", client=CL, project=PROJECT)
        idx = library.load(lib)
        idx["films"] = [f.id]
        library._save(lib, idx)
        got = assets.restore(CL, P1, "room", 1)
    finally:
        assets.draw = real
    e = library.load(lib)["cast"]["room"]
    md = os.path.join(library.dir_of(lib), "cast", "room")
    check(
        got["version"] == 3
        and e["hash"] == a["hash"]
        and "green" in open(os.path.join(md, "v3.js"), encoding="utf-8").read()
        and os.path.exists(os.path.join(md, "v3.png")),
        "going back to a drawn version: its code again, with its pictures",
        (got, e),
    )


def main():
    painted()
    drawn()
    print("\n%s" % ("all passed" if not FAILS else "%d FAILED" % len(FAILS)))
    shutil.rmtree(HOME, ignore_errors=True)
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
