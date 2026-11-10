#!/usr/bin/env python
"""A project's actors (library.py, actor_put.py, film.CAPS "actors"), without Claude or an image
model: python studio/test_actors.py

Covers: a pack (cut by scripts/actor-pack.py from pictures drawn here, as check-actors.py cuts
one) put into a project, and the packs that are refused (a folder without one, a name an episode
could not draw it by, a page outside the pack, a piece it does not hold, the same name twice);
the project's next episode getting it -- its files, the manifest's "actors", the capability, the
modules in its engine copy, the first message naming its faces and poses, the system prompt's
section -- and Claude allowed to Read it but not change it; the episode drawing it (a real
render, a few seconds); a film outside the project, and an episode after the actor is taken out,
getting none of it, with their prompts what they were. Everything in a throwaway STUDIO_HOME.
"""

import os
import sys
import json
import shutil
import tempfile
import subprocess
from importlib import import_module

HOME = tempfile.mkdtemp(prefix="studio-actors-test-")
os.environ["STUDIO_HOME"] = HOME
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agent  # noqa: E402 -- imports _env first
import library  # noqa: E402
from film import KIT, Film  # noqa: E402
from guard import guard  # noqa: E402

P1 = "p-aaaaaaaaaa"
PROJECT = {"id": P1, "name": "Racket history", "brief": "Padel's story, told by its inventor."}
FILM = """SK.film({ duration: 5, camera: SK.camera([[0, [0, 0, 1]]]), draw(t) {
  const c = SK.ctx();
  c.fillStyle = '#ffffff'; c.fillRect(-1200, -800, 2400, 1600);
  SK.actor('tester', 0, 450, 900, { face: 'happy', pose: t > 2.5 ? 'wave' : null });
} });
"""


def make_pack(tmp):
    """A pack cut from cartoon pictures drawn here (check-actors.py's), with no model."""
    sys.path.insert(0, os.path.join(KIT, "scripts"))
    ca = import_module("check-actors")
    out = ca.spec_and_pack(tmp)
    if ca.FAILS:
        raise RuntimeError("check-actors could not cut its pack: %s" % ca.FAILS)
    return out


def render(manifest, times, into):
    return subprocess.run(
        [sys.executable, "-X", "utf8", os.path.join(KIT, "scripts", "sketch-render.py")]
        + ["--manifest", manifest, "--stills", ",".join("%g" % t for t in times), "--into", into],
        capture_output=True,
        text=True,
        timeout=300,
    )


def episode(prompt, project=PROJECT, client="u:alice"):
    return Film.create(prompt, 5, "drawn", client=client, project=dict(project))


def main():
    bad = []

    def check(ok, what):
        print("%s  %s" % ("ok  " if ok else "FAIL", what))
        if not ok:
            bad.append(what)

    tmp = tempfile.mkdtemp(prefix="actors-pack-")
    try:
        pack = make_pack(tmp)
        lib = library.owner("u:alice", P1)
        plain = agent.system_prompt("drawn", ("kit", "grounds"))

        # ------------------------------------------------ what is refused
        def refused(src, status, **kw):
            try:
                library.put_actor(lib, src, **kw)
            except library.ActorError as e:
                return e.status == status
            return False

        check(refused(tmp, 400), "a folder with no pack.json is refused")
        check(refused(pack, 400, name="Tester-1"), "so is a name SK.actor could not be given here")
        bent = os.path.join(tmp, "bent")
        shutil.copytree(pack, bent)
        P = json.load(open(os.path.join(bent, "pack.json"), encoding="utf-8"))
        json.dump(dict(P, pages=["../../secret.webp"]), open(os.path.join(bent, "pack.json"), "w"))
        check(refused(bent, 400), "a page outside the pack is refused")
        json.dump(
            dict(P, poses={**P["poses"], "wave": {**P["poses"]["wave"], "piece": "pose:nope"}}),
            open(os.path.join(bent, "pack.json"), "w"),
        )
        check(refused(bent, 400), "and a pose whose piece the pack does not hold")
        check(not library.load(lib)["actors"], "nothing is written by a refusal")

        # ------------------------------------------------ put in
        e = library.put_actor(lib, pack)
        d = os.path.join(library.dir_of(lib), "actors", "tester")
        check(
            e["name"] == "tester"
            and e["about"] == "A tester."
            and e["faces"] == ["neutral"]
            and set(e["poses"]) == {"wave", "turn_right"}
            and "neutral" in e["talk"],
            "put in under the pack's own name, with who it is and what it holds",
        )
        check(
            sorted(os.listdir(d)) == ["atlas-0.webp", "check.jpg", "pack.json"],
            "only the pack's own files are taken (not its raw pictures, its state or its spend)",
        )
        check(refused(pack, 409), "the same name again needs replace")
        check(
            library.put_actor(lib, pack, replace=True, about="Tess, the tester")["about"]
            == "Tess, the tester",
            "replace puts the pack in its place, and about overrides the pack's own",
        )
        check(
            [a["name"] for a in library.listing("u:alice", P1)["actors"]] == ["tester"],
            "the project's listing shows it",
        )
        check(
            library.listing("u:alice").get("actors") is None,
            "the person's own library has no actors (they belong to a project)",
        )

        # ------------------------------------------------ an episode gets it
        E = episode("the inventor waves hello")
        got = library.seed(E)
        m = json.load(open(E.manifest, encoding="utf-8"))
        check(
            [a["name"] for a in got.get("actors") or []] == ["tester"]
            and m.get("actors") == {"tester": "actors/tester"},
            "the next episode gets it: in its record and its manifest",
        )
        check(
            all(
                os.path.exists(E.path("actors", "tester", f))
                for f in ("pack.json", "atlas-0.webp", "check.jpg")
            ),
            "its pack is in the episode's own folder",
        )
        check(
            "actors" in E.caps
            and {"heads", "actors"} <= set(m.get("modules") or [])
            and len(m["modules"]) == len(set(m["modules"]))
            and os.path.exists(E.path("engine", "actors.js"))
            and os.path.exists(E.path("engine", "heads.js"))
            and "actors.js" in E.engine_files(),
            "the capability, with heads.js and actors.js in its engine copy, each once",
        )
        note = library.note(E)
        check(
            "tester: Tess, the tester" in note
            and "actors/tester/check.jpg" in note
            and "turn_right (turned)" in note
            and "Faces: neutral (it speaks in neutral)" in note,
            "the first message names it, its sheet, its faces and its poses",
        )
        sp = agent.system_prompt(E.look, E.caps)
        check(
            "# The actors (`SK.actor`)" in sp and "{ACTORS}" not in sp,
            "the system prompt carries the actors' section",
        )
        check(
            guard("Read", {"file_path": E.path("actors", "tester", "check.jpg")}, E)[0]
            and not guard("Write", {"file_path": E.path("actors", "tester", "pack.json")}, E)[0]
            and not guard("Write", {"file_path": E.path("engine", "x.js")}, E)[0],
            "Claude may Read the pack but not change it",
        )

        # ------------------------------------------------ and draws it
        with open(E.path("film.js"), "w", encoding="utf-8") as f:
            f.write(FILM)
        r = render(E.manifest, [1, 3], "stills")
        shots = [E.path("stills", "%06.2f.png" % t) for t in (1, 3)]
        if r.returncode or not all(os.path.exists(p) for p in shots):
            check(False, "the episode renders: %s" % (r.stdout[-600:] + r.stderr[-600:]))
        else:
            from PIL import Image
            import numpy as np

            a, b = (np.asarray(Image.open(p).convert("RGB")).astype(int) for p in shots)
            h, w = a.shape[:2]
            mid = a[h // 6 : h * 5 // 6, w * 2 // 5 : w * 3 // 5]
            check(
                (mid.sum(axis=2) < 200).mean() > 0.005,
                "the episode draws the actor (its dark outline in the middle of the frame)",
            )
            check(np.abs(a - b).mean() > 0.5, "and its pose changes on cue")

        # ------------------------------------------------ and nobody else does
        F = Film.create("a film of alice's own", 5, "drawn", client="u:alice")
        library.seed(F)
        check(
            "actors" not in F.caps
            and "actors" not in json.load(open(F.manifest, encoding="utf-8"))
            and not os.path.exists(F.path("actors")),
            "a film outside the project gets no actors",
        )
        check(
            agent.system_prompt(F.look, F.caps) == plain,
            "and its system prompt is byte for byte what a film without actors had",
        )
        check(library.delete_actor(lib, "tester"), "an actor taken out")
        check(not library.delete_actor(lib, "tester"), "(only once)")
        G = episode("after the inventor left")
        library.seed(G)
        check(
            "actors" not in G.caps
            and not (G.record().get("library") or {}).get("actors")
            and not os.path.exists(d),
            "the next episode goes without it, and its files are gone",
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        shutil.rmtree(HOME, ignore_errors=True)
    print("\n%d failed" % len(bad) if bad else "\nall passed")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
