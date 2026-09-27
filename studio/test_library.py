#!/usr/bin/env python
"""A person's library (library.py), without Claude: python studio/test_library.py

Covers: a film's cast/ folder (what Claude may write there), the cast loading before film.js and
an error in one naming its file, what a finished film's cast becomes (versions, thumbnails, the
sheet, which films used a member), the next film of the same person getting it all (and its
note), another person and an anonymous visitor getting none of it, deleting a member, and the
index of someone whose films came before libraries. Everything in a throwaway STUDIO_HOME; the
renders are real (a few seconds each).
"""

import os
import sys
import json
import shutil
import tempfile
import subprocess

HOME = tempfile.mkdtemp(prefix="studio-library-test-")
os.environ["STUDIO_HOME"] = HOME
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agent  # noqa: E402 -- imports _env first
import library  # noqa: E402
from film import KIT, Film  # noqa: E402
from guard import guard  # noqa: E402

PIP = """// Pip: the series' fox
const ORANGE = '#e0782f';
function body(x, y, s) {
  SK.wash(SK.S.ellC(x, y - 80 * s, 70 * s, 90 * s), ORANGE);
  SK.ink(SK.S.ellC(x, y - 80 * s, 70 * s, 90 * s), { w: 5 * s });
}
SK.cast.pip = {
  about: 'Pip, a small orange fox in a blue scarf',
  draw(x, y, o = {}) {
    const s = o.s || 1;
    body(x, y, s);
    SK.P.face.eyes(x - 20 * s, y - 110 * s, x + 20 * s, y - 110 * s, o.mood || 'happy', 0, s);
  },
};
"""
KITE = """SK.cast.kite = { about: "Pip's red kite", draw(x, y, o = {}) {
  SK.wash(SK.S.poly([[x, y - 120], [x + 70, y], [x, y + 120], [x - 70, y]]), '#d33');
} };
"""
FILM = """const film = SK.cast.pip;  // read at load time: the cast is there before film.js
SK.film({ duration: 5, camera: SK.camera([[0, [0, 0, 1]]]), draw(t) {
  film.draw(0, 200, { s: 1.2 });
  SK.cast['kite'].draw(400, -200);
} });
"""


def scene(draw):
    """A 5 s film.js whose draw(t) is this."""
    return "SK.film({ duration: 5, camera: SK.camera([[0, [0, 0, 1]]]), draw(t) { %s } });\n" % (
        draw
    )


def write(film, rel, text):
    p = film.path(*rel.split("/"))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)


def render(manifest, times, into):
    return subprocess.run(
        [sys.executable, "-X", "utf8", os.path.join(KIT, "scripts", "sketch-render.py")]
        + ["--manifest", manifest, "--stills", ",".join("%g" % t for t in times), "--into", into],
        capture_output=True,
        text=True,
        timeout=300,
    )


def finish(film, names=None):
    """What agent.keep_cast does after a film, with the sheet rendered here."""
    items = library.changes(film)
    pictures = {}
    if items:
        names = [it["name"] for it in items]
        man, times = library.sheet(film, names)
        r = render(man, times, "stills")
        if r.returncode:
            raise RuntimeError(r.stdout[-800:] + r.stderr[-800:])
        pictures = library.thumbs(film, names)
    film.update(state="done")
    return library.keep(film, items, pictures)


def main():
    bad = []

    def check(ok, what):
        print("%s  %s" % ("ok  " if ok else "FAIL", what))
        if not ok:
            bad.append(what)

    try:
        # ------------------------------------------------ the first film: nothing to start from
        A = Film.create("Pip the fox learns to fly a kite", 5, "drawn", client="u:alice")
        with open(A.manifest, encoding="utf-8") as f:
            check(json.load(f).get("cast") == "cast", "a new film's manifest loads its cast/")
        got = library.seed(A)
        check(got == {"cast": [], "films": []}, "a person's first film starts with nothing")
        check(library.note(A) == "", "and its first message says nothing about a library")
        for tool, rel, want in [
            ("Write", "cast/pip.js", True),
            ("Edit", "cast/kite_2.js", True),
            ("Write", "cast/Pip.js", False),
            ("Write", "cast/pip.json", False),
            ("Write", "cast/deep/pip.js", False),
            ("Write", "library/cast.png", False),
            ("Write", "library/films/1-x/film.js", False),
            ("Read", "library/films/1-x/film.js", True),
            ("Read", "cast/pip.js", True),
        ]:
            check(guard(tool, {"file_path": rel}, A)[0] == want, "%s %s: %s" % (tool, rel, want))
        write(A, "cast/pip.js", PIP)
        write(A, "cast/kite.js", KITE)
        write(A, "film.js", scene("SK.cast.pip.draw(0, 200);"))
        # the render: the cast loads before film.js, in its own scope
        write(A, "film.js", FILM)
        r = render(A.manifest, [1], "temp/check")
        check(r.returncode == 0, "film.js can use the cast at load time (%s)" % r.stderr[-200:])
        write(A, "cast/zz_bad.js", "throw new Error('boom');\n")
        r = render(A.manifest, [1], "temp/check")
        said = r.stdout + r.stderr
        check(r.returncode != 0 and "cast/zz_bad.js" in said, "an error names its cast file")
        os.remove(A.path("cast", "zz_bad.js"))
        write(A, "film.js", scene("SK.cast.pip.draw(0, 200);"))

        kept = finish(A)
        check(
            kept == {"saved": ["kite", "pip"], "used": ["pip"]},
            "the film's cast is kept (%s)" % kept,
        )
        idx = library.load("u:alice")
        pip, kite = idx["cast"]["pip"], idx["cast"]["kite"]
        check(
            pip["about"] == "Pip, a small orange fox in a blue scarf" and pip["version"] == 1,
            "a member's about and version",
        )
        check(pip["films"] == [A.id] and kite["films"] == [], "which films used which member")
        d = library.dir_of("u:alice")
        check(
            pip["thumb"] and kite["thumb"] and os.path.exists(os.path.join(d, "cast.png")),
            "thumbnails and the sheet",
        )
        check(idx["films"] == [A.id], "the person's films")

        # ------------------------------------------------ the next film gets it all
        B = Film.create("Pip goes to the sea", 5, "drawn", client="u:alice")
        got = library.seed(B)
        check(
            sorted(os.listdir(B.path("cast"))) == ["kite.js", "pip.js"]
            and open(B.path("cast", "pip.js"), encoding="utf-8").read() == PIP,
            "the next film starts with the cast",
        )
        m = [x for x in got["films"] if x["dir"].startswith("library/films/1-")]
        check(
            m
            and os.path.exists(B.path(*m[0]["dir"].split("/"), "film.js"))
            and os.path.exists(B.path(*m[0]["dir"].split("/"), "about.json"))
            and os.path.exists(B.path("library", "cast.png")),
            "and the person's earlier film, read-only",
        )
        note = library.note(B)
        check(
            "- pip: Pip, a small orange fox in a blue scarf (in 1 film)" in note
            and "- kite: Pip's red kite (not used yet)" in note
            and "library/films/1-pip-the-fox-learns-to-fly-a-kite" in note,
            "the note names the cast and the film",
        )
        text = agent.ask(B, [{"look": "drawn", "ground": "paper", "voice": "Kore"}])
        check(note in text and "one of this person's films" in text, "the note is in ask()")
        sp = agent.system_prompt("drawn")
        check(
            "orange fox" not in sp and sp == agent.system_prompt("drawn") and "SK.cast.hero" in sp,
            "the system prompt stays the same for everyone (the cast is explained, not listed)",
        )
        # before its render, a film sheds the members it got and never names
        B2 = Film.create("Pip alone", 5, "drawn", client="u:alice")
        library.seed(B2)
        write(B2, "film.js", scene("const who = 'pip'; SK.cast[who].draw(0, 0);"))
        check(
            library.drop_unused(B2) == ["kite"]
            and os.listdir(B2.path("cast")) == ["pip.js"]
            and render(B2.manifest, [1], "temp/check").returncode == 0,
            "a film's files carry only the cast it draws",
        )
        # B leaves pip alone and changes the kite: only the kite gets a new version
        write(B, "cast/kite.js", KITE.replace("#d33", "#3a3"))
        write(B, "film.js", scene("SK.cast.pip.draw(0, 0);"))
        kept = finish(B)
        idx = library.load("u:alice")
        check(kept["saved"] == ["kite"] and idx["cast"]["kite"]["version"] == 2, "a changed member")
        check(idx["cast"]["pip"]["version"] == 1, "an unchanged one keeps its version")
        check(idx["cast"]["pip"]["films"] == [B.id, A.id], "and gains the film")
        check(os.path.exists(os.path.join(d, "cast", "kite", "v1.js")), "the old version stays")

        # the last KEEP versions only
        for i in range(library.KEEP + 1):
            F = Film.create("kite %d" % i, 5, "drawn", client="u:alice")
            library.seed(F)
            write(F, "cast/kite.js", KITE.replace("#d33", "#%03d" % i))
            write(F, "film.js", scene(""))
            finish(F)
        vs = sorted(os.listdir(os.path.join(d, "cast", "kite")))
        check(
            len([v for v in vs if v.endswith(".js")]) == library.KEEP,
            "%d versions kept (%s)" % (library.KEEP, vs),
        )

        # ------------------------------------------------ nobody else's
        C = Film.create("a film by bob", 5, "drawn", client="u:bob")
        library.seed(C)
        check(
            os.listdir(C.path("cast")) == [] and not os.path.exists(C.path("library")),
            "another person's film gets none of it",
        )
        check(library.note(C) == "", "and hears nothing of it")
        D = Film.create("an anonymous film", 5, "drawn", client="203.0.113.9")
        write(D, "cast/pip.js", PIP)
        check(library.seed(D) is None and library.changes(D) == [], "no library without an account")
        check(library.keep(D, []) is None, "and nothing kept")
        check(library.listing("203.0.113.9") == {"cast": [], "films": []}, "or listed")

        # ------------------------------------------------ deleting a member
        E1 = Film.create("before the delete", 5, "drawn", client="u:alice")
        library.seed(E1)
        E2 = Film.create("also before", 5, "drawn", client="u:alice")
        library.seed(E2)
        check(library.delete("u:alice", "pip"), "a member deleted")
        check(not library.delete("u:alice", "pip"), "only once")
        check(not library.delete("u:bob", "kite"), "only by its person")
        check(
            "pip" not in [c["name"] for c in library.listing("u:alice")["cast"]]
            and library.thumb_of("u:alice", "pip") is None,
            "and gone from the listing",
        )
        E = Film.create("after the delete", 5, "drawn", client="u:alice")
        library.seed(E)
        check(not os.path.exists(E.path("cast", "pip.js")), "the next film does not get it")
        write(E1, "film.js", scene("SK.cast.pip.draw(0, 0);"))
        finish(E1)  # it had pip, unchanged
        check(library.load("u:alice")["cast"]["pip"].get("deleted"), "a film using it keeps it out")
        write(E2, "cast/pip.js", PIP.replace("blue scarf", "green scarf"))
        write(E2, "film.js", scene(""))
        finish(E2)  # it changed pip: the person's film brought it back
        e = library.load("u:alice")["cast"]["pip"]
        check(
            not e.get("deleted") and "green" in e["about"], "a film that changed it brings it back"
        )

        # ------------------------------------------------ films from before libraries
        old = Film.create("carol's old film", 5, "drawn", client="u:carol")
        old.update(state="done")
        shutil.rmtree(old.path("cast"))  # made before films had one
        check(library.load("u:carol")["films"] == [old.id], "earlier films count")
        check(not old.writable(old.path("cast", "x.js")), "no cast/ to write in an old film")
        G = Film.create("carol's next", 5, "drawn", client="u:carol")
        got = library.seed(G)
        check(len(got["films"]) == 1 and got["cast"] == [], "and are remembered")
    finally:
        shutil.rmtree(HOME, ignore_errors=True)
    print("%d failed" % len(bad))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
