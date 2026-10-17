#!/usr/bin/env python
"""Self-test for actors (actor-pack.py, _actor.py, sketch/actors.js): no API, no GPU, seconds.

Draws a cartoon figure with OpenCV and the redraws an image model hands back -- a mouth changed,
the same redraw a little larger and moved (as MAI and Grok send them), one with an arm moved, a
different character, a pose with the head looking out and one with it turned -- and checks what a
paid run would otherwise be the first to find: the white key keeps a white shirt, the fit lays a
moved redraw back to within a pixel, drift is near nothing for a mouth and large for an arm or a
stranger, a patch put back on the base gives the redraw, the head is found in a pose (and not in
a turned one), the atlas packs without overlap, the spec and its fingerprints, a whole pack cut
from pictures already drawn, and the page bundler inlining a pack with its module.

After touching _actor.py, actor-pack.py, config/actors/ or sketch/actors.js, run it.

Invoke as:  python scripts/check-actors.py
"""

import sys
import os
import json
import shutil
import argparse
import tempfile
import subprocess
from importlib import import_module

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import

import numpy as np  # noqa: E402
import cv2  # noqa: E402

import _actor  # noqa: E402
import _sketch  # noqa: E402

FAILS = []
INK, SKIN, SHIRT, SHORTS, HAT = (
    (30, 27, 36),
    (120, 160, 220),
    (250, 250, 250),
    (235, 235, 240),
    (120, 200, 230),
)


def check(name, ok, detail=""):
    print("  %s  %s%s" % ("ok  " if ok else "FAIL", name, ("  (%s)" % detail) if detail else ""))
    if not ok:
        FAILS.append(name)


def draw(mouth="closed", arm=False, skin=SKIN, head_dx=0, profile=False, w=640, h=960):
    """A cartoon figure on white, BGR: hat, head, eyes, mouth, a white shirt, shorts, legs, arms."""
    im = np.full((h, w, 3), 255, np.uint8)
    cx = w // 2
    hx = cx + head_dx

    def shape(fn, *a, fill):
        fn(im, *a, fill, -1, cv2.LINE_AA)
        fn(im, *a, INK, 4, cv2.LINE_AA)

    shape(
        cv2.rectangle, (cx - 70, 300), (cx + 70, 520), fill=SHIRT
    )  # the shirt: white inside its outline
    shape(cv2.rectangle, (cx - 68, 520), (cx + 68, 610), fill=SHORTS)
    for s in (-1, 1):
        shape(cv2.rectangle, (cx + s * 40 - 14, 610), (cx + s * 40 + 14, 860), fill=skin)
        shape(cv2.ellipse, (cx + s * 48, 875), (34, 16), 0, 0, 360, fill=SHIRT)
    for s in (-1, 1):
        up = arm and s > 0
        p0, p1 = (cx + s * 72, 320), (cx + s * 130, 200 if up else 500)
        cv2.line(im, p0, p1, INK, 30, cv2.LINE_AA)
        cv2.line(im, p0, p1, skin, 22, cv2.LINE_AA)
    if profile:
        shape(cv2.ellipse, (hx, 190), (78, 100), 0, 0, 360, fill=skin)
        shape(cv2.ellipse, (hx + 80, 200), (18, 12), 0, 0, 360, fill=skin)
        cv2.circle(im, (hx + 40, 170), 9, INK, -1, cv2.LINE_AA)
    else:
        shape(cv2.circle, (hx, 190), 100, fill=skin)
        for s in (-1, 1):
            shape(cv2.circle, (hx + s * 36, 170), 20, fill=(255, 255, 255))
            cv2.circle(im, (hx + s * 36, 172), 9, INK, -1, cv2.LINE_AA)
        if mouth == "closed":
            cv2.ellipse(im, (hx, 235), (34, 12), 0, 10, 170, INK, 5, cv2.LINE_AA)
        elif mouth == "open":
            shape(cv2.ellipse, (hx, 238), (30, 24), 0, 0, 360, fill=(60, 40, 120))
        elif mouth == "round":
            shape(cv2.ellipse, (hx, 238), (14, 16), 0, 0, 360, fill=(60, 40, 120))
    shape(cv2.ellipse, (hx, 105), (130, 22), 0, 0, 360, fill=HAT)
    shape(cv2.rectangle, (hx - 75, 40), (hx + 75, 100), fill=HAT)
    return im


def moved(bgr, dx, dy, s):
    """The picture as some models hand a redraw back: scaled by s about its middle, then moved."""
    h, w = bgr.shape[:2]
    M = np.float32([[s, 0, (1 - s) * w / 2 + dx], [0, s, (1 - s) * h / 2 + dy]])
    return cv2.warpAffine(bgr, M, (w, h), flags=cv2.INTER_LINEAR, borderValue=(255, 255, 255))


def rgba(bgr):
    return np.dstack([bgr, _actor.key_out(bgr)])


def actor_module():
    base = rgba(draw())
    a = base[..., 3]
    fig = _actor.figure(a)
    check(
        "the white key keeps the white shirt inside its outline", a[400, 320] > 250 and a[5, 5] == 0
    )
    check(
        "the figure: feet at the bottom, head at the top",
        fig["feet"][1] > 880 and fig["head"][1] < 60 and fig["head"][3] < 400,
        str(fig),
    )
    area = fig["area"]

    talk = rgba(draw("open"))
    im, mask, info = _actor.register(base, talk, fig["head"], area)
    check("a mouth redraw: near no drift", info["drift"] < 0.002, "%.4f" % info["drift"])
    got = _actor.patch(im, mask, fig["head"], 8, 4)
    ok = got is not None
    if ok:
        x, y, p = got
        comp = _actor.over(base.copy(), p, x, y)
        hb = fig["head"]
        err = np.abs(
            comp[hb[1] : hb[3], hb[0] : hb[2], :3].astype(int)
            - talk[hb[1] : hb[3], hb[0] : hb[2], :3].astype(int)
        ).mean()
        ok = err < 3 and y > 150 and y + p.shape[0] < 300
        check(
            "the mouth patch, put back on the base, gives the redraw (and sits on the mouth)",
            ok,
            "mean error %.2f, patch y %d..%d" % (err, y, y + p.shape[0]),
        )
    else:
        check("the mouth patch exists", False)

    far = rgba(moved(draw("open"), 12, -7, 1.025))
    _, _, info2 = _actor.register(base, far, fig["head"], area)
    check(
        "a redraw 2.5 % larger and moved: laid back on the base",
        info2["drift"] < 0.006 and abs(info2["scale"] - 1.025) < 0.01,
        str(info2),
    )

    arm = rgba(draw("open", arm=True))
    _, _, info3 = _actor.register(base, arm, fig["head"], area)
    check(
        "a redraw that moved an arm: drift over the mouth gate",
        info3["drift"] > 0.015,
        "%.4f" % info3["drift"],
    )

    other = rgba(draw("open", skin=(60, 90, 150), head_dx=70))
    _, _, info4 = _actor.register(base, other, fig["head"], area)
    check("a different character: large drift", info4["drift"] > 0.05, "%.4f" % info4["drift"])

    pose = rgba(moved(draw(arm=True), 30, 20, 0.9))
    s, _, score = _actor.find_head(base, fig["head"], pose)
    check(
        "the head found in a pose drawn smaller and moved",
        score > 0.85 and abs(s - 0.9) < 0.04,
        "score %.2f scale %.2f" % (score, s),
    )
    turned = rgba(draw(profile=True))
    _, _, score2 = _actor.find_head(base, fig["head"], turned)
    check("a turned head is not taken for the front one", score2 < 0.8, "score %.2f" % score2)
    check(
        "same_character: the pose like the base, a stranger not",
        _actor.same_character(base, pose) > _actor.same_character(base, other),
    )

    halo = base.copy()
    halo[..., 3] = np.maximum(
        halo[..., 3], (np.random.default_rng(1).random(halo.shape[:2]) * 60).astype(np.uint8)
    )
    clean = _actor.clean_alpha(halo)
    check("a model's own alpha: faint specks dropped", (clean[..., 3][:40, :40] == 0).all())

    rng = np.random.default_rng(7)
    pieces = {
        "p%d" % i: np.full(
            (int(rng.integers(20, 900)), int(rng.integers(20, 700)), 4), i + 1, np.uint8
        )
        for i in range(40)
    }
    pages, where = _actor.pack_atlas(pieces, page=2048)
    occupied = [np.zeros(pg.shape[:2], np.int32) for pg in pages]
    fine = True
    for k, v in where.items():
        occupied[v["p"]][v["sy"] : v["sy"] + v["h"], v["sx"] : v["sx"] + v["w"]] += 1
        fine &= bool(
            (
                pages[v["p"]][v["sy"] : v["sy"] + v["h"], v["sx"] : v["sx"] + v["w"]] == pieces[k]
            ).all()
        )
    check(
        "the atlas: every piece in place, none overlapping",
        fine and all(o.max() <= 1 for o in occupied),
        "%d pages" % len(pages),
    )


def spec_and_pack(tmp):
    AP = import_module("actor-pack")
    spec = {
        "name": "tester",
        "describe": "A tester.",
        "faces": ["happy"],
        "talk": ["neutral", "happy"],
        "poses": {"wave": True, "turn_right": True, "jump": "jumping in the air"},
        "pick": 1,
        "project": "check-actors",
    }
    sp = os.path.join(tmp, "tester.json")
    json.dump(spec, open(sp, "w"))
    a = AP.load_spec(sp)
    check(
        "a spec: default prompts picked, new ones kept",
        set(a["poses"]) == {"wave", "turn_right", "jump"}
        and a["poses"]["jump"] == "jumping in the air"
        and "happy" in a["faces"],
    )
    J = AP.jobs(a)
    ids = [j[0] for j in J]
    want = 1 + 1 + 2 * (len(a["mouths"]) + 1) + 3
    check(
        "the pictures a pack needs",
        len(J) == want
        and "mouth:happy:open" in ids
        and J[ids.index("mouth:happy:open")][1] == "face:happy",
        "%d" % len(J),
    )
    check(
        "a turned pose adds its own mouths",
        len(AP.jobs(a, {"wave": True, "turn_right": False, "jump": True}))
        == want + len(a["pose_mouths"]) + 1,
    )
    f1 = AP.fingerprint(a, "x", "r")
    check(
        "fingerprints change with the prompt and the reference",
        f1 != AP.fingerprint(a, "y", "r")
        and f1 != AP.fingerprint(a, "x", "q")
        and f1 == AP.fingerprint(a, "x", "r"),
    )

    # a pack cut from pictures already drawn: no model, the same code a real run packs with
    out = a["out"]
    os.makedirs(os.path.join(out, "raw"), exist_ok=True)
    pics = {
        "base": rgba(draw()),
        "face:happy": rgba(draw("closed")),
        "mouth:neutral:open": rgba(draw("open")),
        "mouth:neutral:round": rgba(draw("round")),
        "mouth:happy:open": rgba(draw("open")),
    }
    pics["pose:wave"] = rgba(moved(draw(arm=True), 20, 10, 0.92))
    pics["pose:turn_right"] = rgba(draw(profile=True))
    state = {}
    for k, im in pics.items():
        f = "raw/%s.png" % k.replace(":", "__")
        cv2.imwrite(os.path.join(out, f), im if k == "base" else im[..., :3])
        state[k] = {"fp": k, "file": f}
    json.dump(state, open(os.path.join(out, "state.json"), "w"))
    book = AP.Book(a, None)
    P = AP.pack(a, book)
    check(
        "pack.json: faces, mouths and poses",
        "open" in P["faces"]["neutral"]["mouths"]
        and "round" in P["faces"]["neutral"]["mouths"]
        and set(P["poses"]) == {"wave", "turn_right"},
        json.dumps({f: list(v.get("mouths", {})) for f, v in P["faces"].items()}),
    )
    check(
        "a pose looking out gets the front face; a turned one does not",
        "face_at" in P["poses"]["wave"] and "face_at" not in P["poses"]["turn_right"],
        json.dumps(P["report"].get("pose:wave")),
    )
    check(
        "the atlas pages and the check sheet are written",
        all(os.path.exists(os.path.join(out, n)) for n in P["pages"])
        and os.path.exists(os.path.join(out, "check.jpg")),
    )
    return out


def bundle(tmp, pack_dir):
    SR = import_module("sketch-render")
    d = os.path.join(tmp, "film")
    shutil.copytree(_env.resolve("config/sketch/example"), d)
    mp = os.path.join(d, "sketch.json")
    m = json.load(open(mp, encoding="utf-8"))
    m["actors"] = {"tester": os.path.relpath(pack_dir, d)}
    json.dump(m, open(mp, "w", encoding="utf-8"))
    page = SR.bundle(_sketch.load(mp), audio=False)
    check(
        "the page carries the pack, its atlas and the module",
        "SK.ACTORS = {" in page
        and "sourceURL=sketch/actors.js" in page
        and '"actor:tester:0": "data:image/webp' in page
        and "sourceURL=sketch/heads.js" in page,
    )


def js():
    node = shutil.which("node")
    if not node:
        print("  --    sketch/actors.js syntax (no node here)")
        return
    r = subprocess.run(
        [node, "--check", _env.resolve("sketch/actors.js")],
        capture_output=True,
        text=True,
        check=False,
    )
    check("sketch/actors.js parses", r.returncode == 0, r.stderr.strip()[:200])


def main():
    argparse.ArgumentParser(description=__doc__.split("\n")[0]).parse_args()
    print("[check-actors] the module")
    actor_module()
    tmp = tempfile.mkdtemp(prefix="check-actors-")
    try:
        print("[check-actors] the spec and a pack")
        pack_dir = spec_and_pack(tmp)
        print("[check-actors] the page")
        bundle(tmp, pack_dir)
        js()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("\n%d failed" % len(FAILS) if FAILS else "\nall passed")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
