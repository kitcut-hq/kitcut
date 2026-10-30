#!/usr/bin/env python
"""A tall film's paintings are painted tall: the film's frame reaches the painter, a tall film is
painted by the same painter as a wide one (Muse, or its project's style picture's painter), and
Claude is told the painting's real shape (film.TALL_PAINTING). No model, no network: the painter
is stood in. Seconds.

    python studio/test_paint_frame.py

Covers: frame_aspect reads a manifest's frame; sketch-paint.py sends each scene in the film's shape
(16:9 with no frame, 9:16 for a Short) and keeps a cut-out's own; a wide painting keeps the key it
had before frames, so no wide film repaints, while a tall one gets a key of its own; paint_pins
gives a tall film exactly a wide film's pins (Muse with no style or a style line, a style
picture's painter with its picture); and the first message of a tall painted film says what shape
its paintings come back in and how wide to draw one (Muse's 2:3, drawn larger to keep its rough
paper edges off screen; a style picture's painter's 9:16), while a tall drawn film's and a wide
film's say nothing of it.
"""

import io
import os
import sys
import json
import shutil
import tempfile
import importlib

HOME = tempfile.mkdtemp(prefix="studio-paint-frame-test-")
os.environ["STUDIO_HOME"] = HOME
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "scripts"))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import
import film as films  # noqa: E402
from PIL import Image  # noqa: E402

SP = importlib.import_module("sketch-paint")
FAILED = []


def expect(what, ok, got=None):
    print("  %s %s%s" % ("ok  " if ok else "FAIL", what, "" if ok else " -- got %r" % (got,)))
    if not ok:
        FAILED.append(what)


def shape_cases():
    print("frame_aspect")
    expect("a tall frame is 9:16", SP.frame_aspect({"frame": [1080, 1920]}) == "9:16")
    expect("a square one 1:1", SP.frame_aspect({"frame": [1080, 1080]}) == "1:1")
    expect("a wide one 16:9", SP.frame_aspect({"frame": [1920, 1080]}) == "16:9")
    expect("and no frame is wide", SP.frame_aspect({}) == "16:9")
    expect("nor does a broken one break it", SP.frame_aspect({"frame": "tall"}) == "16:9")


def key_cases():
    print("painting keys")
    s = {"backend": "muse", "model": "meta/muse-image", "style": "Loose gouache"}
    im = {"name": "fox", "prompt": "A small red fox kneads bread"}
    # computed with sketch-paint.py as it was before frames (studio-poc 0214a20)
    expect("a wide painting keeps the key it had", SP.fingerprint(s, im) == "ae755eaf04")
    expect(
        "and so does one with a reference and a style picture",
        SP.fingerprint(s, {**im, "ref": "x"}, "abc123", "def456", "16:9") == "1cfb4cd226",
    )
    expect(
        "and one with a quality",
        SP.fingerprint({**s, "quality": "medium"}, im, aspect="16:9") == "31bb85a437",
    )
    tall, square = SP.fingerprint(s, im, aspect="9:16"), SP.fingerprint(s, im, aspect="1:1")
    expect("a tall painting has a key of its own", tall not in ("ae755eaf04", square), tall)
    cut = {**im, "cutout": True, "aspect": "2:3"}
    expect(
        "a cut-out keeps its own shape's key in any frame",
        SP.fingerprint(s, cut, aspect="9:16") == SP.fingerprint(s, cut),
    )


def png():
    b = io.BytesIO()
    Image.new("RGB", (90, 160), (120, 160, 200)).save(b, "PNG")
    return b.getvalue()


def painted(frame):
    """Run sketch-paint.py on a one-scene, one-cut-out film in `frame`: the aspect each was
    asked for, by picture."""
    d = tempfile.mkdtemp(dir=HOME)
    m = {
        "duration": 10,
        "paint": {
            "backend": "openrouter",
            "model": "openai/gpt-image-2.5-flare",
            "style": "Loose gouache",
            "images": [
                {"name": "kitchen", "prompt": "A fox at the counter"},
                {"name": "spoon", "prompt": "A wooden spoon", "cutout": True},
            ],
        },
    }
    if frame:
        m["frame"] = frame
    path = os.path.join(d, "sketch.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(m, f)
    asked = {}

    def fake(
        prompt, model, ref=None, quality=None, aspect="16:9", transparent=False, style_ref=None
    ):
        asked["spoon" if "isolated subject" in prompt else "kitchen"] = aspect
        return png(), {"cost_usd": 0.01}

    SP.paint_openrouter, SP.model_caps = fake, lambda model: None
    argv = sys.argv
    sys.argv = ["sketch-paint.py", "--manifest", path]
    try:
        SP.main()
    finally:
        sys.argv = argv
    return asked


def call_cases():
    print("what the painter is asked for")
    tall = painted([1080, 1920])
    expect("a Short's scene is asked for 9:16", tall.get("kitchen") == "9:16", tall)
    expect("its cut-out keeps its own square", tall.get("spoon") == "1:1", tall)
    wide = painted(None)
    expect("a film with no frame is asked for 16:9, as ever", wide.get("kitchen") == "16:9", wide)
    expect("and a square film for 1:1", painted([1080, 1080]).get("kitchen") == "1:1")
    expect(
        "Muse, which is not in the catalogue, is asked for the film's shape too",
        SP.pick_params(None, aspect="9:16")["aspect_ratio"] == "9:16"
        and SP.pick_params(None)["aspect_ratio"] == "16:9",
    )


def pin_cases():
    print("who paints")
    P = ("paintings",)
    wide = films.paint_pins(30, P)
    expect(
        "a painted film with no style is Muse's",
        {k: wide[k] for k in ("backend", "model")}
        == {"backend": "muse", "model": "meta/muse-image"},
        wide,
    )
    words = {"route": "words", "ref": None, "line": "Loose gouache, warm light"}
    tw = films.paint_pins(30, P, words)
    expect(
        "and one with a style line is Muse's, with the line",
        tw["model"] == "meta/muse-image" and tw["style"] == words["line"] and "style_ref" not in tw,
        tw,
    )
    gpt = {"route": "gpt", "ref": "style/style.jpg", "line": "x"}
    tg = films.paint_pins(30, P, gpt)
    expect(
        "a style picture's painter keeps its picture",
        tg["model"] == "openai/gpt-image-2.5-flare"
        and tg["style_ref"] == "style/style.jpg"
        and tg["style"] == "",
        tg,
    )
    expect(
        "paint_pins takes no frame: a tall film's painter is a wide film's",
        "frame"
        not in films.paint_pins.__code__.co_varnames[: films.paint_pins.__code__.co_argcount],
    )
    expect("no tall painter is left anywhere", not hasattr(films, "TALL_PAINTER"))


def tall_film(look, route=None):
    f = films.Film.create("how a fox bakes bread", 15, look, client="t", frame="9:16")
    if route:
        f.update(paint_route=route)
    return f


def note_cases():
    print("what Claude is told")
    tall = tall_film("painted")
    note = films.frame_note(tall)
    expect(
        "a tall painted film with no style is told Muse's paintings come back 2:3",
        "come back tall, 2:3" in note,
        note[-800:],
    )
    expect(
        "drawn large enough that Muse's rough paper edges stay off screen",
        "about 1430 wide (2145 tall)" in note and "rough paper" in note,
        note[-800:],
    )
    expect("and narrower than 1280 shows bands", "narrower than 1280" in note, note[-800:])
    with open(tall.path("paint.json"), encoding="utf-8") as f:
        pins = json.load(f)
    expect("its paint.json names Muse", pins.get("model") == "meta/muse-image", pins)
    words = tall_film("painted", {"route": "words", "ref": None, "line": "Loose gouache"})
    expect(
        "so does one with a style line",
        "come back tall, 2:3" in films.frame_note(words),
    )
    pic = tall_film("painted", {"route": "gpt", "ref": "style/style.jpg", "line": "x"})
    note = films.frame_note(pic)
    expect(
        "one with a style picture is told 9:16, about 1170 wide",
        "come back tall, 9:16" in note
        and "about 1170 wide (2080 tall)" in note
        and "narrower than 1080" in note
        and "rough paper" not in note,
        note[-800:],
    )
    drawn = tall_film("drawn")
    expect(
        "a tall drawn film is told nothing of paintings", "paintings" not in films.frame_note(drawn)
    )
    wide = films.Film.create("how a fox bakes bread", 15, "painted", client="t")
    expect("and a wide painted film no note at all", films.frame_note(wide) == "")
    with open(wide.path("paint.json"), encoding="utf-8") as f:
        expect("and Muse paints it", json.load(f).get("model") == "meta/muse-image")


def main():
    shape_cases()
    key_cases()
    call_cases()
    pin_cases()
    note_cases()
    shutil.rmtree(HOME, ignore_errors=True)
    print("\n%s" % ("FAILED: %s" % "; ".join(FAILED) if FAILED else "all passed"))
    sys.exit(1 if FAILED else 0)


if __name__ == "__main__":
    main()
