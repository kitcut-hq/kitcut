#!/usr/bin/env python
"""A painting made from a project's picture ("ref": "pic_<name>" in paint.json), with the
painter stood in for: python studio/test_paintref.py

Covers: a pic ref resolves to the film's inputs/pic_<name>.* and goes to the painter as it is,
never painted; the image made from it is painted before the scenes made from that image, which
get it as their reference; the picture's content is in the fingerprint (a new picture paints
afresh, the same one is cached); an unknown picture, another shape of name, a path escape and a
link out of inputs/ are refused, by the painter and by the check (validate.py); a film without
pic refs plans exactly as before. A throwaway folder, no network, no model.
"""

import io
import os
import sys
import json
import shutil
import tempfile
import importlib
import threading
import contextlib

HOME = tempfile.mkdtemp(prefix="studio-paintref-test-")
os.environ["STUDIO_HOME"] = HOME
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import validate  # noqa: E402 -- imports _env first
from PIL import Image  # noqa: E402

SP = importlib.import_module("sketch-paint")
SP._project.record = lambda *a, **k: None  # the run, not the workspace's project journal
FAILS = []
CAPS = ["paintings"]


def check(ok, what, detail=""):
    print(("ok   " if ok else "FAIL ") + what + ("" if ok else "  " + str(detail)[:300]))
    if not ok:
        FAILS.append(what)


def jpeg(colour):
    b = io.BytesIO()
    Image.new("RGB", (64, 48), colour).save(b, "JPEG")
    return b.getvalue()


COLOURS = {"cast": (200, 30, 30), "park": (30, 200, 30), "beach": (30, 30, 200)}
CALLS = []
LOCK = threading.Lock()


def fake_paint(
    prompt, model, ref=None, quality=None, aspect="16:9", transparent=False, style_ref=None
):
    """The painter: says what it was given (and what its reference looked like then), and
    paints each image a colour of its own, named first in its prompt."""
    name = prompt.split(":")[0]
    seen = None
    if ref and os.path.exists(ref):
        with Image.open(ref) as im:
            seen = im.convert("RGB").getpixel((5, 5))
    with LOCK:
        CALLS.append({"name": name, "ref": ref, "seen": seen, "style_ref": style_ref})
    return jpeg(COLOURS.get(name, (128, 128, 128))), {"cost_usd": 0.01}


SP.paint_openrouter = fake_paint


def film(name, images, pics=()):
    """A film folder: sketch.json, paint.json and its project pictures."""
    d = os.path.join(HOME, name)
    os.makedirs(os.path.join(d, "inputs"), exist_ok=True)
    for p, colour in pics:
        Image.new("RGB", (64, 48), colour).save(os.path.join(d, "inputs", p))
    paint = {"backend": "openrouter", "model": "m", "style": "", "images": images}
    json.dump(paint, open(os.path.join(d, "paint.json"), "w"))
    json.dump({"paint": "paint.json"}, open(os.path.join(d, "sketch.json"), "w"))
    return d


def run(d, *extra):
    """sketch-paint.py on a film: (its output, the exit message or None)."""
    out, err = io.StringIO(), None
    sys.argv = ["sketch-paint.py", "--manifest", os.path.join(d, "sketch.json"), *extra]
    CALLS.clear()
    with contextlib.redirect_stdout(out):
        try:
            SP.main()
        except SystemExit as e:
            err = str(e.code)
    return out.getvalue(), err


def main():
    family = (200, 180, 40)
    images = [
        {"name": "park", "prompt": "park: the family in a park", "ref": "cast"},
        {"name": "cast", "prompt": "cast: the family side by side", "ref": "pic_family"},
        {"name": "beach", "prompt": "beach: the family on a beach", "ref": "cast"},
    ]
    d = film("cast", images, [("pic_family.png", family)])

    # ---- the check: a pic ref of this film's passes, anything else is refused
    paint = json.load(open(os.path.join(d, "paint.json")))
    check(validate._paint(paint, 30, CAPS, d) == [], "the check takes a ref to the film's picture")
    for bad in ("pic_nobody", "family", "pic_../../x", "../inputs/pic_family", "pic_Family"):
        p = dict(paint, images=[dict(images[1], ref=bad)])
        out = validate._paint(p, 30, CAPS, d)
        check(
            out and "project pictures (pic_<name>)" in out[0],
            "the check refuses ref %r" % bad,
            out,
        )
    check(
        validate._paint(paint, 30, CAPS) != [],
        "the check without the film's folder takes no picture",
    )

    # ---- the painter: the picture as it is, the cast sheet first, the scenes from it
    _, err = run(d)
    by = {c["name"]: c for c in CALLS}
    pic = os.path.realpath(os.path.join(d, "inputs", "pic_family.png"))
    check(err is None and sorted(by) == ["beach", "cast", "park"], "three painted", (err, CALLS))
    check(
        by["cast"]["ref"] == pic and by["cast"]["seen"] == family,
        "the cast sheet goes to the painter with the project's picture",
        by.get("cast"),
    )
    check(
        all(
            by[n]["ref"] == os.path.join(d, "images", "cast.jpg")
            and by[n]["seen"]
            and all(abs(a - b) < 12 for a, b in zip(by[n]["seen"], COLOURS["cast"], strict=True))
            for n in ("park", "beach")
        ),
        "each scene is painted from this run's cast sheet, painted before it",
        [by[n] for n in ("park", "beach")],
    )
    check(
        not any(os.path.basename(c["ref"] or "").startswith("pic_family_") for c in CALLS)
        and not os.path.exists(os.path.join(d, "images", "pic_family.jpg")),
        "the picture itself is never painted",
    )

    # ---- the fingerprint: the same picture is cached, a new one paints afresh
    out, err = run(d, "--plan")
    check(err is None and out.count("cached ") == 3, "a rerun paints nothing", out)
    Image.new("RGB", (64, 48), (10, 10, 10)).save(os.path.join(d, "inputs", "pic_family.png"))
    out, err = run(d, "--plan")
    check(
        err is None and out.count("PAINT  ") == 3,
        "a new picture repaints the cast sheet and the scenes made from it",
        out,
    )

    # ---- refused by the painter: an unknown picture, a path escape, a link out of inputs/
    outside = os.path.join(HOME, "pic_secret.png")
    Image.new("RGB", (8, 8)).save(outside)
    for bad in ("pic_nobody", "pic_../pic_secret", "../pic_secret", "pic_linked"):
        e = film("bad-" + bad.replace("/", "_").replace(".", "_"), [dict(images[1], ref=bad)])
        if bad == "pic_linked":
            os.symlink(outside, os.path.join(e, "inputs", "pic_linked.png"))
        _, err = run(e, "--plan")
        check(
            err and "not one of the images, nor one of this film's project pictures" in err,
            "the painter refuses ref %r" % bad,
            err,
        )
    linked = film("linked", [dict(images[1], ref="pic_linked")])
    os.symlink(outside, os.path.join(linked, "inputs", "pic_linked.png"))
    check(
        validate._paint(json.load(open(os.path.join(linked, "paint.json"))), 30, CAPS, linked)
        != [],
        "the check refuses a picture that is a link out of inputs/",
    )

    # ---- a film without pic refs: as before, to the fingerprint and the order
    plain = [
        {"name": "kitchen", "prompt": "kitchen: a kitchen"},
        {"name": "table", "prompt": "table: a table", "ref": "kitchen"},
    ]
    p = film("plain", plain, [("pic_family.png", family)])
    spec = {"backend": "openrouter", "model": "m", "style": ""}
    k_fp = SP.fingerprint(spec, plain[0])
    want = {"kitchen": k_fp, "table": SP.fingerprint(spec, plain[1], k_fp)}
    _, err = run(p)
    names = [c["name"] for c in CALLS]
    check(
        err is None
        and names == ["kitchen", "table"]
        and CALLS[1]["ref"] == os.path.join(p, "images", "kitchen.jpg")
        and all(
            os.path.exists(os.path.join(p, "images", "%s_%s.jpg" % (n, fp)))
            for n, fp in want.items()
        ),
        "a film without pic refs paints and caches exactly as before",
        (err, CALLS, os.listdir(os.path.join(p, "images"))),
    )
    back = film("backwards", plain[::-1])  # a scene listed before its ref: keys as they were
    out, err = run(back, "--plan")
    check(
        err is None
        and SP.fingerprint(spec, plain[1]) != want["table"]
        and out.count("PAINT  ") == 2,
        "a film listing a scene before its ref plans as before",
        out,
    )
    paint = json.load(open(os.path.join(p, "paint.json")))
    check(validate._paint(paint, 30, CAPS, p) == [], "and its check passes as before")
    p2 = dict(paint, images=[dict(plain[1], ref="nothing")])
    check(
        validate._paint(p2, 30, CAPS, p) != [],
        "a ref to no image and no picture is still refused",
    )

    print("\n%s" % ("all passed" if not FAILS else "%d FAILED" % len(FAILS)))
    shutil.rmtree(HOME, ignore_errors=True)
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
