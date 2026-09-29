#!/usr/bin/env python
"""Thumbnail self-test: the rules _thumb.py holds every option to, on pictures made here.

Every rule a thumbnail option is checked against is a number somebody measured (the bake-off in
docs/reference.md "Thumbnail options"), and a rule that quietly stops applying ships a thumbnail
nobody can read at feed size. So, in two halves:

  rules   no browser, no film, no OCR: the contrast arithmetic against WCAG's own pairs, the
          safe zones (the duration stamp's corner, the margins), where a block of words goes on
          a picture with a busy side and a quiet one, that it never lands on the film's own
          words, line breaks, the starred accent word, the concepts' rules (four, apart, short,
          not the title, one layout each), the fallback order, a frame caught mid-crossfade
          against a settled one, and the accent colour of a picture with one thing that pops
  live    one real browser shot (headless Edge/Chrome, as the studio uses): a headline and a
          slab painted on a synthetic frame, composed, and passed through every check -- then
          the same words forced over the frame's own lettering must fail the "hides the film's
          words" check. Skipped, and said so, when no browser is found.

Invoke as:  python scripts/check-thumbnail.py
            python scripts/check-thumbnail.py --rules-only   (no browser, no OCR)
"""

import os
import sys
import tempfile
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import
import numpy as np  # noqa: E402
from PIL import Image, ImageDraw, ImageFilter  # noqa: E402
import _thumb  # noqa: E402

FAILED = []
PASSED = [0]


def check(name, cond, detail=""):
    if cond:
        PASSED[0] += 1
        print("  ok   %s" % name)
    else:
        FAILED.append(name)
        print("  FAIL %s%s" % (name, ("  -- " + str(detail)) if detail else ""))


def frame(busy_right=True, lettering=None, colour=(40, 60, 110)):
    """A 1920x1080 test frame: a flat ground, a busy textured subject on one side, a small
    yellow star (the thing that pops), and optionally a line of the film's own lettering."""
    W, H = _thumb.size()
    im = Image.new("RGB", (W, H), colour)
    d = ImageDraw.Draw(im)
    rng = np.random.default_rng(7)
    x0 = W // 2 + 100 if busy_right else 100
    for _ in range(900):
        x, y = rng.integers(x0, x0 + 760), rng.integers(200, 1000)
        r = int(rng.integers(6, 30))
        d.ellipse([x - r, y - r, x + r, y + r], outline=(230, 230, 230), width=3)
    d.regular_polygon((W // 2, 160, 40), 5, fill=(250, 205, 40))
    if lettering:
        f = _thumb.pil_font("fonts/Montserrat-Bold.ttf", 90)
        d.text(lettering[0], lettering[1], font=f, fill=(250, 250, 250))
    return im


def rules():
    print("\ncontrast (WCAG 2.2)")
    white, black = (255, 255, 255), (0, 0, 0)
    ratio = float(_thumb.contrast(_thumb.luminance(white), _thumb.luminance(black)))
    check("white on black is 21:1", abs(ratio - 21.0) < 0.01, ratio)
    grey = float(_thumb.contrast(_thumb.luminance((118, 118, 118)), _thumb.luminance(white)))
    check("#767676 on white is 4.54:1 (WCAG's own AA pair)", abs(grey - 4.54) < 0.02, grey)
    fixed = _thumb.fit_contrast((255, 214, 0), white, 4.5)
    got = float(_thumb.contrast(_thumb.luminance(fixed), _thumb.luminance(white)))
    check("an accent is moved until it reads on its ground", got >= 4.5, (fixed, got))

    print("\nYouTube's corners and margins")
    W, H = _thumb.size()
    safe, badge = _thumb.safe_rects()
    check(
        "the duration stamp's corner is the bottom-right 15%",
        badge == (1632, 918, 1920, 1080),
        badge,
    )
    check("5% margins", safe[:2] == (96, 54), safe)
    dm = np.zeros((H // 8, W // 8), dtype="float32")
    p = _thumb.place(600, 300, dm, area=(1300, 700, W, H))
    check(
        "a block asked for the bottom-right is kept off the stamp",
        p is None or not _thumb._hits((p[0], p[1], p[0] + 600, p[1] + 300), badge),
        p,
    )

    print("\nwhere the words go")
    im = frame(busy_right=True)
    dm, sm = _thumb.detail_map(im), _thumb.subject_map(im)
    p = _thumb.place(700, 300, dm, sm)
    check("words go on the quiet side, not over the subject", p and p[0] + 350 < W / 2, p)
    tm = np.zeros(dm.shape, dtype=bool)
    tm[:, : dm.shape[1] // 2] = True  # the film's own words fill the quiet half
    p2 = _thumb.place(700, 300, dm, sm, tmap=tm)
    check("never over the film's own words", p2 is None or p2[0] >= W / 2, p2)

    print("\nwords and lines")
    toks = _thumb.tokens("Can't *sleep*?")
    check(
        "a starred word is the accent; its ? is not",
        toks == [[("Can't", False)], [("sleep", True), ("?", False)]],
        toks,
    )
    check("plain words", _thumb.plain("Only *3* steps") == "Only 3 steps")
    font = _thumb.pick_font("One letter's journey", "clean")
    b = _thumb.block_at(_thumb.tokens("One letter's journey"), font, 120, 900, 700, 2, 0.3)
    check(
        "three words at 120 px fill two lines, not one too wide",
        b and len(b["lines"]) == 2,
        b and [L["text"] for L in b["lines"]],
    )
    check(
        "Anton, in capitals, for a clean film",
        b and b["lines"][0]["text"].isupper() and font["file"].endswith("Anton-Regular.ttf"),
    )
    uk = _thumb.pick_font("Знахідка в лісі", "clean")
    check(
        "Cyrillic falls through to a font that has it",
        uk and uk["file"].endswith("Montserrat-Bold.ttf"),
        uk,
    )
    ratio = _thumb.cap_ratio("fonts/Anton-Regular.ttf")
    check("cap height read from the font (Anton 0.86 em)", 0.8 < ratio < 0.9, ratio)

    print("\nconcepts")
    good = [
        {"at": 2, "layout": "headline", "words": "Count *three* stars", "place": "top"},
        {"at": 5, "layout": "slab", "words": "Eyes grow heavy"},
        {"at": 8, "layout": "panel", "words": "Olga's trick", "place": "left"},
        {"at": 11, "layout": "still", "words": ""},
    ]
    cs, notes, probs = _thumb.check_concepts(good, 20, "Little Hedgehog Could Not Sleep")
    check("four good concepts pass", len(cs) == 4 and not probs, probs)
    _, _, probs = _thumb.check_concepts(good[:3], 20)
    check("three are not four", any("exactly four" in p["text"] for p in probs), probs)
    near = [dict(good[0]), dict(good[1], at=2.4), *good[2:]]
    _, _, probs = _thumb.check_concepts(near, 20)
    check("two moments on one frame are a problem", any("apart" in p["text"] for p in probs), probs)
    rep = [dict(good[0], words="Hedgehog could not sleep"), *good[1:]]
    _, _, probs = _thumb.check_concepts(rep, 20, "Little Hedgehog Could Not Sleep")
    check(
        "words that repeat the title are a problem",
        any(p["n"] == 1 and "repeat" in p["text"] for p in probs),
        probs,
    )
    long = [dict(good[0], words="a b c d e"), *good[1:]]
    _, _, probs = _thumb.check_concepts(long, 20)
    check("five words are too many", any("too long" in p["text"] for p in probs), probs)
    edge = [dict(good[0], at=19.9), *good[1:]]
    cs, notes, probs = _thumb.check_concepts(edge, 20)
    check("a moment in the fade-out is moved inside", cs[0]["at"] <= 19.5 and notes, (cs[0], notes))
    fill = _thumb.fill_concepts(cs[:2], [1, 4, 9, 12, 15, 18], 20)
    check(
        "missing ones are made up from the film's moments",
        len(fill) == 4 and fill[-1]["layout"] == "still",
        fill,
    )
    check(
        "fallbacks: headline -> scrim -> slab -> still",
        _thumb.FALLBACK["headline"] == ["headline+scrim", "slab", "still"],
    )
    check("a panel falls to a slab before the picture alone", _thumb.FALLBACK["panel"][0] == "slab")

    print("\nthe frame")
    still = frame()
    fade = Image.blend(still, frame(busy_right=False), 0.5)
    stills = {}
    tmp = tempfile.mkdtemp(prefix="check-thumb-")
    # a crossfade under way from 1.4 to 2.6 s; the picture holds still from 2.6 s on
    for t in (1.0, 1.2, 1.4, 1.6, 1.8, 2.0, 2.2, 2.4, 2.6, 2.8):
        a = 0.0 if t >= 2.6 else min(1.0, max(0.0, (2.6 - t) / 1.2))
        img = Image.blend(still, fade, a)
        p = os.path.join(tmp, "%06.2f.png" % t)
        img.save(p)
        stills[round(t, 2)] = p
    t, rows = _thumb.settle(2.0, stills, 30)
    check("the settled frame, not the one mid-crossfade", t >= 2.6, rows)
    acc = _thumb.accent_colour(still)
    check(
        "the accent is the one yellow star, not the blue ground",
        acc[0] > 180 and acc[1] > 150 and acc[2] < 120,
        acc,
    )
    quiet = Image.new("RGB", (1920, 1080), (40, 40, 40))
    check(
        "no vivid colour: the default accent",
        _thumb.accent_colour(quiet) == _thumb.hex_rgb(_thumb.cfg()["colours"]["accent_default"]),
    )


def live():
    print("\nlive: one browser shot")
    h2i = _thumb._h2i()
    if not h2i.find_browsers():
        print("  skip no Edge/Chrome found (set HTML2IMG_BROWSER)")
        return
    im = frame(busy_right=True, lettering=((140, 820), "HELLO THERE"))
    im = im.filter(ImageFilter.SMOOTH)
    o1 = {"n": 1, "img": im, "place": None, "requested": "headline"}
    o1.update(_thumb.layout_headline(im, "Count *three* stars", "clean", where="top-left"))
    o2 = {"n": 2, "img": im, "place": None, "requested": "slab"}
    o2.update(_thumb.layout_slab(im, "Eyes grow heavy", "crayon", where="top"))
    work = tempfile.mkdtemp(prefix="check-thumb-live-")
    shots = _thumb.paint([o1, o2], work)
    for o, (layer, mask) in zip((o1, o2), shots):
        final = _thumb.compose(im, o, layer)
        res, fails = _thumb.checks(o, final, mask, layer)
        check("%s passes every check" % o["layout"], not fails, (fails, res))
        check(
            "%s: letters >= 8 px tall at 168 px wide" % o["layout"], res.get("cap_168", 0) >= 8, res
        )
        check("%s: nothing under the duration stamp" % o["layout"], res.get("in_badge") == 0, res)
        check(
            "%s: none of the film's own words hidden" % o["layout"],
            res.get("hides_text", 0) == 0,
            res,
        )
    boxes = _thumb.text_boxes(im)
    check("OCR finds the frame's own lettering", any(b[1] < 900 < b[3] for b in boxes), boxes)
    # the same slab forced over the lettering must fail
    forced = dict(o2)
    dy = 820 - forced["box"][1]
    forced["ctx"] = dict(o2["ctx"], lines=[dict(L, ry=L["ry"] + dy, y=L["y"] + dy, cy=L["cy"] + dy, rx=L["rx"] - o2["box"][0] + 120, x=L["x"] - o2["box"][0] + 120, cx=L["cx"] - o2["box"][0] + 120) for L in o2["ctx"]["lines"]])  # fmt: skip
    layer, mask = _thumb.paint([forced], os.path.join(work, "forced"))[0]
    res, fails = _thumb.checks(forced, _thumb.compose(im, forced, layer), mask, layer)
    check(
        "a slab over the film's own words fails the check",
        any("film's own words" in f for f in fails),
        (fails, res),
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--rules-only", action="store_true", help="no browser, no OCR")
    a = ap.parse_args()
    rules()
    if not a.rules_only:
        live()
    print("\n%d passed, %d failed" % (PASSED[0], len(FAILED)))
    for f in FAILED:
        print("  FAILED: %s" % f)
    sys.exit(1 if FAILED else 0)


if __name__ == "__main__":
    main()
