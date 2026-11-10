#!/usr/bin/env python
"""A finished film made the start of a project (fromfilm.py), without Claude:
python studio/test_fromfilm.py

Covers: what the film used becomes the project's (its attached pictures with their roles, its
drawn cast with their descriptions, the film itself among the project's earlier films), asking
twice copies nothing twice, someone else's film or an unfinished one is refused, what Claude is
asked (the idea, the narrator, the music, the lettering, the cast, the pictures, and to leave the
film's own story out), the answer held to its shape, and how the brief stands on disk (writing,
done, failed, and a "writing" whose server went away). Everything in a throwaway STUDIO_HOME.
"""

import os
import sys
import json
import asyncio
import tempfile
from datetime import datetime, timedelta

HOME = tempfile.mkdtemp(prefix="studio-fromfilm-test-")
os.environ["STUDIO_HOME"] = HOME
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fromfilm  # noqa: E402 -- imports _env first
import library  # noqa: E402
import ytdraft  # noqa: E402
from film import Film  # noqa: E402

P1 = "p-aaaaaaaaaa"
PIP = """SK.cast.pip = {
  about: 'Pip, a small orange fox in a blue scarf',
  draw(x, y, o = {}) { SK.wash(SK.S.ellC(x, y, 70, 90), '#e0782f'); },
};
"""
FILM = """// For: children of 4 to 6; calm and curious
SK.setGround('paper', { paper: '#fdf6e3', accent: '#e0782f' });
SK.film({ duration: 5, camera: SK.camera([[0, [0, 0, 1]]]), draw(t) { SK.cast.pip.draw(0, 0); } });
"""


def write(film, rel, text):
    p = film.path(*rel.split("/"))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text if isinstance(text, str) else json.dumps(text))


def picture(path, size=(600, 400)):
    from PIL import Image

    os.makedirs(os.path.dirname(path), exist_ok=True)
    Image.new("RGB", size, "#3366aa").save(path)


def finished(client="u:alice"):
    """A finished drawn film of alice's: a picture attached as a logo to show, Pip drawn,
    narrated by Kore, with music and two faces."""
    F = Film.create("Pip learns why the sky is blue. Keep it calm.", 5, "drawn", client=client)
    write(F, "cast/pip.js", PIP)
    write(F, "film.js", FILM)
    write(
        F,
        "vo.json",
        {
            "voice": "Kore",
            "style": "warm, slow",
            "language": "en",
            "lines": [
                {"text": "Look up, Pip. Why is the sky so blue?"},
            ],
        },
    )
    write(F, "score.json", {"bpm": 84, "events": [{"inst": "piano"}, {"inst": "celesta"}]})
    picture(F.path("inputs", "upload1.png"))
    picture(F.path("inputs", "upload2.jpg"))
    write(F, "inputs/roles.json", {"upload1": "show"})
    with open(F.manifest, encoding="utf-8") as f:
        m = json.load(f)
    m["fonts"] = [{"file": "fonts/Anton-Regular.ttf", "family": "Anton"}]
    with open(F.manifest, "w", encoding="utf-8") as f:
        json.dump(m, f)
    F.update(state="done", title="Why the sky is blue")
    return F


def main():
    bad = []

    def check(ok, what):
        print("%s  %s" % ("ok  " if ok else "FAIL", what))
        if not ok:
            bad.append(what)

    try:
        F = finished()
        got = fromfilm.seed("u:alice", P1, F.id)
        idx = library.load(("u:alice", P1))
        check(got["pictures"] == ["picture1", "picture2"], "its attached pictures, in order")
        check(
            idx["pictures"]["picture1"].get("role") == "show"
            and "role" not in idx["pictures"]["picture2"],
            "each with the role it had, and none where it had none",
        )
        check(got["cast"] == ["pip"], "the cast member its code drew")
        check(
            idx["cast"]["pip"]["about"] == "Pip, a small orange fox in a blue scarf"
            and idx["cast"]["pip"]["from_film"] == F.id,
            "with its description, and where it came from",
        )
        lib_dir = library.dir_of(("u:alice", P1))
        check(os.path.exists(os.path.join(lib_dir, "cast", "pip", "v1.js")), "its code is kept")
        check(idx["films"][0] == F.id, "the film heads the project's earlier films")
        check(got["voice"] == "Kore" and got["fonts"] == ["Anton"], "its narrator and faces")

        again = fromfilm.seed("u:alice", P1, F.id)
        idx2 = library.load(("u:alice", P1))
        check(
            again["pictures"] == got["pictures"] and again["cast"] == got["cast"],
            "asked twice: the same names",
        )
        check(
            idx2["cast"]["pip"]["version"] == 1 and idx2["films"].count(F.id) == 1,
            "and nothing copied twice",
        )

        for client, film_id, status, what in [
            ("u:bob", F.id, 404, "someone else's film is not found"),
            ("u:alice", "studio-nope", 404, "nor one that does not exist"),
            ("1.2.3.4", F.id, 404, "a visitor has no project"),
        ]:
            try:
                fromfilm.seed(client, P1, film_id)
                check(False, what)
            except fromfilm.FromFilmError as e:
                check(e.status == status, what)
        U = Film.create("not done yet", 5, "drawn", client="u:alice")
        try:
            fromfilm.seed("u:alice", P1, U.id)
            check(False, "an unfinished film is refused")
        except fromfilm.FromFilmError as e:
            check(e.status == 409, "an unfinished film is refused")
        try:
            fromfilm.seed("u:alice", "p-nope", F.id)
            check(False, "a project id that is not one")
        except fromfilm.FromFilmError as e:
            check(e.status == 404, "a project id that is not one")

        # what Claude is asked
        text = fromfilm.ask_text(fromfilm.material(F, got))
        for want, what in [
            ("Pip learns why the sky is blue", "the person's idea"),
            ("children of 4 to 6", "who it was made for"),
            ("the voice Kore; warm, slow", "the narrator and how they speak"),
            ("celesta, piano, 84 bpm", "the music"),
            ("#fdf6e3", "the ground's colours"),
            ("Anton", "the typefaces"),
            ("- pip: Pip, a small orange fox", "the cast by name, described"),
            ("- pic_picture1 -- show", "the pictures by their project names, with roles"),
            ("Why is the sky so blue?", "the narration"),
            ("Leave out this film's own topic", "and to leave its own story out"),
        ]:
            check(want in text, "the ask has %s" % what)

        check(
            fromfilm.clean({"name": " Pip  and the sky ", "brief": "a\r\nb"})
            == {"name": "Pip and the sky", "brief": "a\nb"},
            "an answer is held to its shape",
        )
        try:
            fromfilm.clean({"name": "x"})
            check(False, "an answer with no brief is refused")
        except ValueError:
            check(True, "an answer with no brief is refused")

        # the brief in the background, with Claude stubbed
        check(fromfilm.state("u:alice", "p-bbbbbbbbbb")["state"] == "none", "none asked: none")

        async def answer(*a, **k):
            return {"name": "Pip's Sky", "brief": "For children of 4 to 6. Pip the fox..."}, 0.01

        async def fails(*a, **k):
            raise RuntimeError("no draft")

        real = ytdraft.ask_json
        try:
            ytdraft.ask_json = answer
            asyncio.run(fromfilm.write("u:alice", P1, F.id, got))
            st = fromfilm.state("u:alice", P1)
            check(
                st["state"] == "done" and st["name"] == "Pip's Sky" and st["film"] == F.id,
                "written: done, with its name and brief",
            )
            ytdraft.ask_json = fails
            asyncio.run(fromfilm.write("u:alice", P1, F.id, got))
            check(fromfilm.state("u:alice", P1)["state"] == "failed", "a failed ask: failed")
        finally:
            ytdraft.ask_json = real
        p = fromfilm.state_path(("u:alice", P1))
        old = (datetime.now() - timedelta(seconds=fromfilm.WRITING_MAX_S + 5)).isoformat()
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"state": "writing", "film": F.id, "at": old}, f)
        check(
            fromfilm.state("u:alice", P1)["state"] == "failed",
            "a brief still writing long after its server went away: failed",
        )
        check(fromfilm.state("u:bob", P1)["state"] == "none", "bob sees nothing of alice's")
    finally:
        import shutil

        shutil.rmtree(HOME, ignore_errors=True)

    print("\n%d failed" % len(bad) if bad else "\nall passed")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
