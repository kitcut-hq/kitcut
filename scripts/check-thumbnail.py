#!/usr/bin/env python
"""Thumbnail self-test: the rules _thumb.py holds every option to, and the film's own look.

Every rule a thumbnail option is checked against is a number somebody measured (the bake-off in
docs/reference.md "Thumbnail options"), and a rule that quietly stops applying ships a thumbnail
nobody can read at feed size -- or one that does not look like the film it sells. In two halves:

  rules   no browser, no film, no OCR: the contrast arithmetic against WCAG's own pairs, the
          safe zones (the duration stamp's corner, the margins), where a block of words goes on
          a picture with a busy side and a quiet one, that words on the picture touch none of the
          film's own words while a card may hide one whole but never cut through it, the film's
          type chosen first and a type that has the glyphs when it has not, a .woff2 film font
          measured through the tooling's .ttf of its family, the film's ink kept where it reads
          and deepened just enough where it does not, the concepts' rules (four, apart, short,
          not the title, one layout each; an old "slab" read as a card), the fallback order, and
          a frame caught mid-crossfade against a settled one
  live    the repo's example film (a crayon film in Caveat) in a throwaway copy, drawn by headless
          Edge/Chrome as the studio draws it: the probe reads its look (hand-drawn, its Caveat,
          its palette), four options are made from four concepts and every one passes every
          check in the film's own type -- then a headline forced over the film's own title must
          fail the "hides the film's words" check. Skipped, and said so, with no browser.

Invoke as:  python scripts/check-thumbnail.py
            python scripts/check-thumbnail.py --rules-only   (no browser, no OCR)
"""

import os
import sys
import json
import shutil
import tempfile
import argparse
import importlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import
import numpy as np  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402
import _thumb  # noqa: E402

EXAMPLE = os.path.join(_env.ROOT, "config", "sketch", "example")
FAILED = []
PASSED = [0]


def check(name, cond, detail=""):
    if cond:
        PASSED[0] += 1
        print("  ok   %s" % name)
    else:
        FAILED.append(name)
        print("  FAIL %s%s" % (name, ("  -- " + str(detail)) if detail else ""))


def frame(busy_right=True, colour=(40, 60, 110)):
    """A 1920x1080 test frame: a flat ground, a busy textured subject on one side."""
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
    return im


def style(**kw):
    """A film's look as film_style() returns it, for a clean film set in Anton."""
    st = {
        "crayon": False,
        "paper": (247, 242, 231),
        "text": (42, 37, 33),
        "ink": (42, 37, 33),
        "accent": (180, 90, 20),
        "accent_fill": (217, 115, 63),
        "heads": [
            {
                "file": "fonts/Anton-Regular.ttf",
                "family": "Anton",
                "weight": "400",
                "col": (42, 37, 33),
                "size": 96,
                "film": True,
                "stroke": None,
            },
            {
                "file": "fonts/Montserrat-Bold.ttf",
                "family": "Thumb Montserrat",
                "weight": "700",
                "col": (42, 37, 33),
                "film": False,
            },
        ],  # fmt: skip
        "card": {
            "fill": (255, 255, 255),
            "r": 18,
            "stroke": None,
            "strokeW": 2,
            "shadow": True,
            "sketch": False,
        },  # fmt: skip
        "logo": None,
    }
    st.update(kw)
    return st


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
    words = [(0, 0, W // 2, H)]  # the film's own words fill the quiet half
    p2 = _thumb.place(700, 300, dm, sm, avoid=words)
    check("words on the picture never touch the film's own", p2 is None or p2[0] >= W / 2, p2)
    label = (300, 400, 520, 440)  # a small label on the quiet side
    ok = True
    for area in ((96, 54, 900, 1000), (96, 300, 700, 700), (200, 330, 820, 800)):
        q = _thumb.place(600, 300, dm, sm, area=area, avoid=[label], whole=True)
        if q:
            b = (q[0], q[1], q[0] + 600, q[1] + 300)
            inside = b[0] <= label[0] and b[1] <= label[1] and b[2] >= label[2] and b[3] >= label[3]
            ok = ok and (inside or not _thumb._hits(b, label))
    check("a card hides a label whole or not at all -- never cuts through it", ok)

    print("\nthe film's type")
    st = style()
    check("words set in the film's own type", _thumb.pick_head(st, "One letter's journey")["family"] == "Anton")  # fmt: skip
    uk = _thumb.pick_head(st, "Знахідка в лісі")
    check(
        "Cyrillic falls through to a type that has it",
        uk and uk["file"].endswith("Montserrat-Bold.ttf"),
        uk,
    )
    font = _thumb._font(st["heads"][0])
    b = _thumb.block_at(_thumb.tokens("One letter's journey"), font, 120, 900, 700, 2, 0.3)
    check(
        "three words at 120 px fill two lines, not one too wide",
        b and len(b["lines"]) == 2,
        b and [L["text"] for L in b["lines"]],
    )
    check(
        "set as the film writes them, not forced into capitals",
        b and b["lines"][0]["text"] == "One letter's",
    )
    ratio = _thumb.cap_ratio("fonts/Anton-Regular.ttf")
    check("cap height read from the font (Anton 0.86 em)", 0.8 < ratio < 0.9, ratio)
    ff = _thumb.film_fonts(EXAMPLE)
    cav = [f for f in ff if f["family"] == "Caveat"]
    check(
        "a .woff2 film font is measured through the tooling's .ttf of its family",
        cav and cav[0]["file"].endswith(".ttf"),
        ff,
    )

    def ink(wt):
        m = _thumb.pil_font("fonts/Caveat-Cyrillic-VF.ttf", 100, wt).getmask("Pass it on")
        return int(np.asarray(m).sum())

    v4, v7 = ink("400"), ink("700")
    check("a variable font is measured at the weight it is drawn at", v7 > v4 * 1.15, (v4, v7))

    print("\nthe film's colours")
    need = _thumb.cfg()["contrast_min"] + _thumb.cfg()["ink_margin"]
    head = st["heads"][0]
    check("on its own paper, the film's ink stays", _thumb._ink(st, head, st["paper"]) == head["col"])  # fmt: skip
    night = (20, 24, 40)
    ink = _thumb._ink(st, head, night)
    check("on a night ground, the film's paper is the ink", ink == st["paper"], ink)
    mid = (128, 128, 128)
    ink = _thumb._ink(st, head, mid)
    check(
        "where none of its colours reads, the nearest is deepened just enough",
        _thumb._reads(ink, mid) >= need - 0.01,
        (ink, _thumb._reads(ink, mid)),
    )
    acc = _thumb._accent(st, head["col"], st["paper"])
    check(
        "the starred word in the film's accent, with the ink's margin",
        _thumb._reads(acc, st["paper"]) >= need - 0.01,
        (acc, _thumb._reads(acc, st["paper"])),
    )

    print("\nconcepts")
    good = [
        {"at": 2, "layout": "headline", "words": "Count *three* stars", "place": "top"},
        {"at": 5, "layout": "card", "words": "Eyes grow heavy"},
        {"at": 8, "layout": "panel", "words": "Olga's trick", "place": "left"},
        {"at": 11, "layout": "still", "words": ""},
    ]
    cs, notes, probs = _thumb.check_concepts(good, 20, "Little Hedgehog Could Not Sleep")
    check("four good concepts pass", len(cs) == 4 and not probs, probs)
    old = [dict(good[0]), dict(good[1], layout="slab"), *good[2:]]
    cs, _, probs = _thumb.check_concepts(old, 20)
    check("an old draft's slab is a card", cs[1]["layout"] == "card" and not probs, (cs, probs))
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
        "fallbacks: headline -> its glow -> a card -> the still",
        _thumb.FALLBACK["headline"] == ["headline+glow", "card", "still"],
    )
    check("a panel falls to a card before the picture alone", _thumb.FALLBACK["panel"][0] == "card")

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
    shutil.rmtree(tmp, ignore_errors=True)


def fixture(home):
    """The example film in a throwaway folder, with a voice timeline (its cues hang off it)."""
    d = os.path.join(home, "example")
    os.makedirs(os.path.join(d, "audio", "vo"))
    for n in ("film.js", "sketch.json"):
        shutil.copyfile(os.path.join(EXAMPLE, n), os.path.join(d, n))
    with open(os.path.join(d, "sketch.json"), encoding="utf-8") as f:
        m = json.load(f)
    lines = [(0.6, 4.2, "An invite you never used is just sitting there, waiting."),
             (4.6, 7.0, "So send it to a friend."), (7.4, 9.0, "Pass it on.")]  # fmt: skip
    tl = {"duration": m["duration"], "lines": [{"i": i, "start": s, "end": e, "text": t, "words": []} for i, (s, e, t) in enumerate(lines)]}  # fmt: skip
    with open(os.path.join(d, "audio", "vo", "timeline.json"), "w", encoding="utf-8") as f:
        json.dump(tl, f)
    return d


def live():
    print("\nlive: the example film, drawn")
    if not importlib.import_module("html-to-image").find_browsers():
        print("  skip no Edge/Chrome found (set HTML2IMG_BROWSER)")
        return
    home = tempfile.mkdtemp(prefix="check-thumb-live-")
    film = fixture(home)
    st = _thumb.film_style(film)
    check("the probe sees a hand-drawn film", st["crayon"], st)
    check(
        "its headline type is its own Caveat",
        st["heads"][0]["film"] and st["heads"][0]["family"] == "Caveat",
        st["heads"][:1],
    )
    check("its paper is its own", st["paper"] == _thumb.colour("#f7f2e7"), st["paper"])
    concepts = [
        {"at": 3.6, "layout": "headline", "words": "Still *waiting*?", "place": None},
        {"at": 6.6, "layout": "card", "words": "Send it on", "place": None},
        {"at": 8.6, "layout": "panel", "words": "A friend can *use* it", "place": None},
        {"at": 11.0, "layout": "still", "words": ""},
    ]
    opts = _thumb.make_options(film, concepts, os.path.join(home, "out"), log=print)
    for o in opts:
        ck = o["checks"]
        size = os.path.getsize(o["file"])
        check("option %d: a JPEG under 2 MB (%d KB)" % (o["n"], size // 1024), size < 2_000_000)
        if o["layout"] == "still":
            continue
        check(
            "option %d (%s): legible, in contrast, clear of the stamp and the film's words"
            % (o["n"], o["layout"]),
            ck.get("cap_168", 0) >= 8
            and ck.get("contrast", 0) >= 4.5
            and ck.get("in_badge") == 0
            and ck.get("hides_text", 0) <= _thumb.cfg()["text"]["hide_max_px"],
            (ck, o["notes"]),
        )
        check("option %d: in the film's own Caveat" % o["n"], o["font"] == "Caveat", o["font"])
    check(
        "four layouts asked, four kept",
        [o["layout"] for o in opts] == ["headline", "card", "panel", "still"],
        [(o["layout"], o["notes"]) for o in opts],
    )
    # a headline forced over the film's own title must fail
    t = opts[0]["t"]
    img = _thumb.load_still(_thumb.render_stills(film, [t])[t])
    boxes = _thumb.text_boxes(img, min_h=_thumb.cfg()["text"]["headline_min_h_px"])
    check("OCR finds the film's own title", bool(boxes), boxes)
    o = _thumb.layout_headline(img, "Still *waiting*?", st)
    if boxes and o:
        x0, y0 = boxes[0][:2]
        L0 = o["spec"]["lines"][0]
        dx, dy = x0 - L0["x"], y0 + o["px"] * 0.8 - L0["y"]
        o["spec"] = {"lines": [dict(L, x=L["x"] + dx, y=L["y"] + dy) for L in o["spec"]["lines"]]}
        b = o["box"]
        o.update({"n": 1, "t": t, "img": img, "glow": False,
                  "box": (b[0] + dx, b[1] + dy, b[2] + dx, b[3] + dy)})  # fmt: skip
        final, mask, foot = _thumb.paint(film, [o], os.path.join(home, "forced"), st)[1]
        res, fails = _thumb.checks(o, final, mask, foot)
        check(
            "a headline over the film's own words fails the check",
            any("film's own words" in f for f in fails),
            (fails, res),
        )
    shutil.rmtree(home, ignore_errors=True)


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
