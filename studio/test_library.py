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


def narrate(film, texts, vo):
    """A narration as sketch-vo.py leaves one: vo.json, a take per line, timeline.json."""
    import numpy as np

    sys.path.insert(0, os.path.join(KIT, "scripts"))
    import _sketch

    write(film, "vo.json", json.dumps(dict(vo, lines=[{"text": t} for t in texts])))
    lines, t = [], 0.5
    for i, text in enumerate(texts):
        rel = "audio/vo/L%02d_T0_x_line.wav" % i
        y = 0.2 * np.sin(np.arange(int(1.5 * _sketch.SR)) * 2 * np.pi * (180 + 40 * i) / _sketch.SR)
        os.makedirs(film.path("audio", "vo"), exist_ok=True)
        _sketch.write_wav(film.path(*rel.split("/")), y)
        lines.append({"i": i, "text": text, "file": rel, "dur": 1.5, "start": t, "end": t + 1.5})
        t += 1.85
    write(film, "audio/vo/timeline.json", json.dumps({"duration": 5, "lines": lines}))


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

        projects(check)
    finally:
        shutil.rmtree(HOME, ignore_errors=True)
    print("%d failed" % len(bad))
    sys.exit(1 if bad else 0)


P1, P2 = "p-aaaaaaaaaa", "p-bbbbbbbbbb"
OWL = (
    "SK.cast.owl = { about: 'Olga, a wise grey owl', draw(x, y, o = {}) {\n"
    "  SK.wash(SK.S.ellC(x, y - 60, 50, 60), '#888');\n} };\n"
)


def episode(prompt, project=P1, client="u:alice", bring=False):
    return Film.create(
        prompt,
        5,
        "drawn",
        client=client,
        project={
            "id": project,
            "name": "Olga's Forest",
            "brief": "A bedtime series for 4-year-olds. Calm narrator, soft piano.",
            "from_account_cast": bring,
        },
    )


def projects(check):
    """A project's library: its own cast, episodes and pictures, apart from the person's."""
    from PIL import Image

    check(library.owner("u:alice", "p-nope") is None, "a project id that is not one: no library")
    check(library.owner("1.2.3.4", P1) is None, "nor for a visitor without an account")
    before = library.load("u:alice")
    # ------------------------------------------------ pictures
    logo = os.path.join(HOME, "logo.png")
    Image.new("RGBA", (800, 400), (200, 40, 40, 255)).save(logo)
    e = library.add_picture("u:alice", P1, "logo", logo, "png")
    check(e["w"] == 800 and e["h"] == 400, "a picture joins the project")
    check(library.picture_thumb("u:alice", P1, "logo"), "with a thumbnail")
    check(library.picture_thumb("u:bob", P1, "logo") is None, "which only its person sees")
    for bad, status in (("Logo", 400), ("1x", 400)):
        try:
            library.add_picture("u:alice", P1, bad, logo, "png")
            check(False, "a bad name refused: %s" % bad)
        except library.PictureError as err:
            check(err.status == status, "a bad name refused: %s" % bad)
    for i in range(library.PICTURES - 1):
        library.add_picture("u:alice", P2, "p%d" % i, logo, "png")
    library.add_picture("u:alice", P2, "p0", logo, "png")  # the same name replaces it
    library.add_picture("u:alice", P2, "last", logo, "png")
    try:
        library.add_picture("u:alice", P2, "one_more", logo, "png")
        check(False, "at most %d pictures" % library.PICTURES)
    except library.PictureError as err:
        check(err.status == 409, "at most %d pictures" % library.PICTURES)
    check(library.delete_picture("u:alice", P2, "last"), "a picture taken out")
    check(
        not library.delete_picture("u:alice", P2, "last")
        and library.picture_thumb("u:alice", P2, "last") is None,
        "and gone",
    )
    check(
        [p["name"] for p in library.listing("u:alice", P1)["pictures"]] == ["logo"]
        and "pictures" not in library.listing("u:alice"),
        "a project's listing has its pictures; the person's own has none",
    )

    # ------------------------------------------------ the first episode, bringing the person's cast
    E1 = episode("Olga meets the moon", bring=True)
    got = library.seed(E1)
    check(
        sorted(c["name"] for c in got["cast"]) == ["kite", "pip"],
        "a project that asked for it starts with the person's cast",
    )
    check(
        os.path.exists(E1.path("inputs", "pic_logo.png"))
        and got["pictures"]
        == [{"name": "pic_logo", "file": "inputs/pic_logo.png", "w": 800, "h": 400}],
        "and its pictures, in inputs/",
    )
    with open(E1.manifest, encoding="utf-8") as f:
        check(json.load(f)["images"].get("pic_logo") == "inputs/pic_logo.png", "in the manifest")
    note = library.note(E1)
    check(
        'episode of the project "Olga\'s Forest"' in note
        and "Calm narrator, soft piano." in note
        and "- pic_logo (800x400): inputs/pic_logo.png" in note
        and "project's cast" in note
        and "first episode" in note,
        "the note names the project, its brief, pictures and cast",
    )
    text = agent.ask(E1, [{"look": "drawn", "ground": "paper", "voice": "Kore"}])
    check(note in text and "the project's brief" in text, "and is in ask()")
    write(E1, "cast/owl.js", OWL)
    write(E1, "film.js", scene("SK.cast.owl.draw(0, 0); SK.image('pic_logo', 0, 0, 200);"))
    check(agent.drop_unused_uploads(E1) == [], "a picture film.js draws stays")
    kept = finish(E1)
    check(kept["saved"] == ["owl"], "the episode's new member is kept (%s)" % kept)
    pidx = library.load(("u:alice", P1))
    check(pidx["films"] == [E1.id] and "owl" in pidx["cast"], "in the project's library")
    after = library.load("u:alice")
    check(
        "owl" not in after["cast"] and after["films"] == before["films"],
        "and not in the person's own",
    )

    # ------------------------------------------------ voice lines, approved from an episode
    GREET, TODAY = "Привіт! Це Очеретинська школа економіки.", "Сьогодні — про кешбек."
    VO = {"voice": "Sadachbia", "model": "gemini-3.1-flash-tts-preview", "language": "uk"}
    narrate(E1, [GREET, TODAY], VO)
    lines = library.film_lines(E1)
    check(
        [x["text"] for x in lines] == [GREET, TODAY] and not any(x["approved"] for x in lines),
        "a finished episode's lines, none approved yet",
    )
    mp3 = library.film_line_audio(E1, 0)
    check(mp3 and os.path.getsize(mp3) > 1000, "each line to listen to, as MP3")
    check(library.film_line_audio(E1, 9) is None, "and not one it does not have")
    v = library.add_voice_from_film("u:alice", P1, E1.id, 0)
    check(
        v["text"] == GREET
        and (v["tts"], v["voice"], v["model"], v["language"])
        == ("gemini", "Sadachbia", "gemini-3.1-flash-tts-preview", "uk")
        and (v["film"], v["line"]) == (E1.id, 0)
        and abs(v["dur"] - 1.5) < 0.01,
        "a line approved from the episode, in its voice (%s)" % v,
    )
    lines = library.film_lines(E1)
    check(lines[0]["approved"] and not lines[1]["approved"], "and it shows as approved")
    check(
        library.voice_audio("u:alice", P1, v["key"])
        and library.voice_audio("u:bob", P1, v["key"]) is None
        and library.voice_audio("u:alice", P2, v["key"]) is None,
        "its recording plays for its person, in its project only",
    )
    check(
        [x["key"] for x in library.listing("u:alice", P1)["voice"]] == [v["key"]]
        and "voice" not in library.listing("u:alice"),
        "a project's listing has its voice lines",
    )
    for who, proj, fid, i, status, why in (
        ("u:bob", P1, E1.id, 0, 404, "someone else's film"),
        ("u:alice", P2, E1.id, 0, 404, "an episode of another project"),
        ("u:alice", P1, E1.id, 5, 404, "a line it does not have"),
        ("u:alice", P1, E1.id, True, 404, "a line that is not a number"),
        ("u:alice", P1, "studio-nope", 0, 404, "a film that is not there"),
    ):
        try:
            library.add_voice_from_film(who, proj, fid, i)
            check(False, "refused: %s" % why)
        except library.VoiceError as err:
            check(err.status == status, "refused: %s" % why)
    unfinished = episode("still being made")
    narrate(unfinished, [GREET], VO)
    try:
        library.add_voice_from_film("u:alice", P1, unfinished.id, 0)
        check(False, "refused: a film still being made")
    except library.VoiceError as err:
        check(err.status == 409, "refused: a film still being made")

    # ------------------------------------------------ the next episode
    E2 = episode("Olga and the first snow")
    got = library.seed(E2)
    check(
        "owl.js" in os.listdir(E2.path("cast")) and len(got["films"]) == 1,
        "the next episode gets the owl and the first episode",
    )
    note = library.note(E2)
    check(
        "Its earlier episodes" in note and "belongs with the others" in note,
        "and hears it is one of a series",
    )
    approved = E2.path("audio", "vo", "approved")
    with open(os.path.join(approved, "index.json"), encoding="utf-8") as f:
        given = json.load(f)
    check(
        list(given) == [v["key"]]
        and given[v["key"]]["text"] == GREET
        and os.path.exists(os.path.join(approved, v["key"] + ".wav"))
        and [x["key"] for x in got["voice"]] == [v["key"]],
        "the next episode gets the approved voice line in audio/vo/approved/",
    )
    check(
        "approved voice lines" in note and '"%s" (Sadachbia' % GREET in note,
        "and is told to say it word for word",
    )
    write(
        E2, "cast/badge.js", "SK.cast.badge = { draw(x, y) { SK.image('pic_logo', x, y, 90); } };\n"
    )
    write(E2, "film.js", scene("SK.cast.badge.draw(0, 0);"))
    check(agent.drop_unused_uploads(E2) == [], "a picture a cast member draws stays")
    os.remove(E2.path("cast", "badge.js"))
    write(E2, "film.js", scene(""))
    library.drop_unused(E2)
    check(agent.drop_unused_uploads(E2) == ["pic_logo"], "one nothing draws leaves the manifest")

    # ------------------------------------------------ kept apart
    H = Film.create("alice, outside any project", 5, "drawn", client="u:alice")
    library.seed(H)
    check(
        "owl.js" not in os.listdir(H.path("cast")) and not os.path.exists(H.path("inputs")),
        "a film outside the project gets none of it",
    )
    other = episode("another project", project=P2)
    got = library.seed(other)
    check(
        got["cast"] == [] and got["films"] == [] and len(got["pictures"]) == library.PICTURES - 1,
        "another project of hers has only its own (%s)" % [p["name"] for p in got["pictures"]],
    )
    B = episode("bob names alice's project", client="u:bob")
    got = library.seed(B)
    check(
        got["cast"] == [] and got["pictures"] == [] and got["films"] == [] and got["voice"] == [],
        "the same id from someone else is their own, empty",
    )
    check(
        library.delete("u:alice", "owl", P1) and not library.delete("u:alice", "owl"),
        "a member leaves the project it is in, not the person's own",
    )
    check(
        not library.delete_voice("u:bob", P1, v["key"])
        and library.delete_voice("u:alice", P1, v["key"])
        and library.voice_audio("u:alice", P1, v["key"]) is None
        and library.listing("u:alice", P1)["voice"] == []
        and not library.delete_voice("u:alice", P1, v["key"]),
        "a voice line taken out of its project, by its person only",
    )
    src = E1.path("audio", "vo", "L01_T0_x_line.wav")
    for i in range(library.VOICE_LINES):
        library.add_voice("u:alice", P2, "Line %d." % i, src, VO)
    library.add_voice("u:alice", P2, "Line 0.", src, VO)  # the same words again replace it
    try:
        library.add_voice("u:alice", P2, "One line too many.", src, VO)
        check(False, "at most %d voice lines" % library.VOICE_LINES)
    except library.VoiceError as err:
        check(err.status == 409, "at most %d voice lines" % library.VOICE_LINES)
    # someone whose films came before libraries: their episodes are not their own films
    dave = Film.create("dave's film", 5, "drawn", client="u:dave")
    dave.update(state="done")
    ep = episode("dave's episode", client="u:dave")
    ep.update(state="done")
    check(
        library.load("u:dave")["films"] == [dave.id], "a person's earlier films leave out episodes"
    )
    check(library.load(("u:dave", P1))["films"] == [], "and a project starts from nothing")


if __name__ == "__main__":
    main()
