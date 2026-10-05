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
          and deepened just enough where it does not, the film's outline and the fills inside it
          (a collage film's cream and lemon edged in indigo), the concepts' rules (four, apart,
          short, the title's message allowed, the layouts as listed -- a second headline; an old
          "slab" read as a card, an old "still" given a layout and asked for words), which options
          carry the logo, the subject read off the film's pictures (not its logo, not a painted
          scene, not a prop), the push and the side the words take, the film's frame border and a
          progress bar's labels cropped, the discs and cards that would show empty once the words
          are left out, the fallback order, and a frame caught mid-crossfade against a settled one
  live    the repo's example film (a crayon film in Caveat) in a throwaway copy, drawn by headless
          Edge/Chrome as the studio draws it: the probe reads its look (hand-drawn, its Caveat,
          its palette), its uncluttered still leaves its title out, four options are made from
          four concepts and every one passes every check in the film's own type -- then a headline
          forced over the film's own title must fail the "hides the film's words" check. Skipped,
          and said so, with no browser.

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
        {"at": 11, "layout": "headline", "words": "Could *not* sleep", "place": "right"},
    ]
    cs, notes, probs = _thumb.check_concepts(good, 20, "Little Hedgehog Could Not Sleep")
    check("four good concepts pass, two of them headlines", len(cs) == 4 and not probs, probs)
    check(
        "the layouts as the writer gave them",
        [c["layout"] for c in cs] == ["headline", "card", "panel", "headline"],
        cs,
    )
    old_still = [*good[:3], {"at": 11, "layout": "still", "words": ""}]
    cs, _, probs = _thumb.check_concepts(old_still, 20)
    check(
        "an old draft's still takes the free layout and is asked for words",
        cs[3]["layout"] == "headline"
        and any(p["n"] == 4 and "needs words" in p["text"] for p in probs),
        (cs[3], probs),
    )
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
        "the title's message in fewer words is allowed (2026-09-30: 'a random still')",
        not probs,
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
    check(
        "the logo on options 1 and 3; all or none when asked",
        [_thumb.wants_logo(n, None) for n in (1, 2, 3, 4)] == [True, False, True, False]
        and _thumb.wants_logo(2, "all")
        and not _thumb.wants_logo(1, "none"),
    )

    print("\nthe film's shout")
    lemon, cream, indigo = "#ffd84a", "#fffaf0", "#1f1b5c"
    styles = [
        {"kind": "headline", "font": "Oswald", "wt": "700", "col": lemon, "max": 176, "n": 4,
         "letters": 36, "upper": 36, "stroke": {"w": 0.117, "col": indigo}},
        {"kind": "headline", "font": "Oswald", "wt": "700", "col": indigo, "max": 118, "n": 8,
         "letters": 112, "upper": 112, "stroke": None},
        {"kind": "headline", "font": "Oswald", "wt": "700", "col": cream, "max": 80, "n": 2,
         "letters": 44, "upper": 44, "stroke": {"w": 0.15, "col": indigo}},
        {"kind": "tape", "font": "Oswald", "wt": "600", "col": cream, "max": 76, "n": 28,
         "letters": 376, "upper": 376, "stroke": None},
    ]  # fmt: skip
    col = _thumb.colour
    o = _thumb.outline_of(
        styles, col("#f4ecd8"), col("#2b2870"), col("#2a2521"), col("#ffd76a"), col("#f6cd4b")
    )
    check(
        "a collage film's outline: cream words, lemon for the starred one, edged in its indigo",
        o
        and o["fill"] == col(cream)
        and o["accent"] == col(lemon)
        and o["stroke"]["col"] == col(indigo)
        and abs(o["stroke"]["w"] - 0.117) < 1e-6,
        o,
    )
    plain_styles = [dict(x, stroke=None) for x in styles]
    check(
        "a film that never outlines a title has no outline",
        _thumb.outline_of(
            plain_styles,
            col("#f4ecd8"),
            col("#2b2870"),
            col("#2a2521"),
            col("#ffd76a"),
            col("#f6cd4b"),
        )
        is None,
    )

    print("\nthe picture under the words")
    W, H = _thumb.size()
    boxes = [
        {"name": "doctor", "box": [1268, 309, 1534, 962]},
        {"name": "cashier", "box": [1494, 317, 1815, 949]},
        {"name": "pic_logo", "box": [118, 118, 308, 308]},
        {"name": "kettle", "box": [900, 100, 960, 170]},
        {"name": "scene", "box": [-20, -20, W + 20, H + 20]},
    ]
    S, how = _thumb.subject_box(frame(), boxes)
    check(
        "the subject is the film's pictures: not its logo, a painted scene or a prop",
        how == "pictures" and tuple(S) == (1268, 309, 1815, 962),
        (S, how),
    )
    flat = Image.new("RGB", (W, H), (46, 185, 165))
    comp = _thumb.compose(flat, boxes[:3])
    check(
        "the words take the free side and the camera pushes the subject in",
        comp["side"] == "left"
        and comp["zoom"] > 1.3
        and comp["subject"][3] - comp["subject"][1] > 0.8 * H,
        {k: comp[k] for k in ("side", "zoom", "subject")},
    )
    check(
        "a push that leaves the logo out does not cut it in two", comp["logo"] is None, comp["logo"]
    )
    framed = flat.copy()
    ImageDraw.Draw(framed).rectangle([0, 0, W, 44], fill=(43, 40, 112))
    check(
        "the film's own frame border is found",
        any(b[1] == 0 and 36 <= b[3] <= 52 for b in _thumb.frame_border(framed)),
        _thumb.frame_border(framed),
    )
    backs = [
        {"name": "#burst", "id": "empty", "box": [100, 100, 230, 230]},
        {"name": "#burst", "id": "behind-heart", "box": [600, 400, 1000, 800]},
        {"name": "heart", "box": [680, 450, 1010, 765]},
        {"name": "#card", "id": "card|title", "box": [500, 40, 1400, 200]},
        {"name": "#words", "box": [950, 115, 952, 117]},
        {"name": "#card", "id": "card|screen", "box": [100, 500, 500, 1000]},
        {"name": "#words", "box": [300, 520, 302, 522]},
    ]
    screen = flat.copy()
    d = ImageDraw.Draw(screen)
    for y in range(560, 960, 30):  # an app screen's rows, left on the clean picture
        d.line([150, y, 450, y], fill=(20, 20, 20), width=6)
    hide = _thumb.empty_backings(backs, screen)
    check(
        "what would show empty goes: a disc with nothing on it, a title card whose words are out",
        "empty" in hide and "card|title" in hide,
        hide,
    )
    check(
        "what still holds something stays: a burst behind a heart, a screen with its rows",
        "behind-heart" not in hide and "card|screen" not in hide,
        hide,
    )

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


def pieces():
    """A film's pictures as film_pieces() returns them: two figures, a prop, a print, a brand's
    mark and a flyer full of words."""

    def p(w, h, **kw):
        base = {"file": "", "w": w, "h": h, "cut": True, "being": False, "figure": False,
                "mark": False, "lettered": False, "about": "",
                "colours": [((242, 201, 76), 0.6), ((106, 152, 129), 0.4)]}  # fmt: skip
        return dict(base, **kw)

    return {
        "girl": p(408, 1053, being=True, figure=True),
        "mum": p(424, 1054, being=True, figure=True),
        "trap": p(1053, 808),
        "photo": p(900, 600, cut=False),
        "web_mark": p(600, 600, mark=True),
        "flyer": p(800, 1100, cut=False, lettered=True),
    }


def posters():
    """A poster's rules, with no browser: what varies and what never does, who it is built on,
    where its pieces and its words go in each template, and that its words are judged where
    they stand."""
    W, H = _thumb.size()
    k = _thumb.cfg()["poster"]
    safe, badge = _thumb.safe_rects()
    pcs = pieces()

    print("\nposters: what changes from one to the next")
    vs = [_thumb.poster_variant("film-a", n) for n in (1, 2, 3, 4)]
    check("the same film and option, the same poster", vs == [_thumb.poster_variant("film-a", n) for n in (1, 2, 3, 4)])  # fmt: skip
    check("four options take both templates, turn about",
          [v["template"] for v in vs[:2]] in (["side", "band"], ["band", "side"])
          and vs[0]["template"] == vs[2]["template"] and vs[1]["template"] == vs[3]["template"], vs)  # fmt: skip
    check("and both sides", {v["side"] for v in vs} == {"left", "right"}, vs)
    seeds = {json.dumps(_thumb.poster_variant("film-%d" % i, 1), sort_keys=True) for i in range(12)}
    check("another film, another poster", len(seeds) >= 4, len(seeds))

    print("\nposters: the stage")
    page = [{"box": [40, 53, 1880, 1003], "col": "#22c1b4"}]
    cam = _thumb.stage_camera(page)
    check("an inset page is pushed in until it fills the frame, and a little past its edge",
          cam and abs(cam["zoom"] - k["stage_overscan"] * H / 950) < 0.01, cam)  # fmt: skip
    plate = Image.new("RGB", (W, H), (43, 40, 112))
    ImageDraw.Draw(plate).rectangle([40, 53, 1880, 1003], fill=(34, 193, 180))
    shown = _thumb.staged(plate, cam)
    corners = [shown.getpixel(xy) for xy in ((4, 4), (W - 5, 4), (4, H - 5), (W - 5, H - 5))]
    check(
        "...so none of the mat under it shows", all(c == (34, 193, 180) for c in corners), corners
    )
    check("no page, no push", _thumb.stage_camera([]) is None)
    check("a page that fills the frame, no push",
          _thumb.stage_camera([{"box": [0, 0, W, H], "col": "#fff"}]) is None)  # fmt: skip

    print("\nposters: who it is built on")
    c4 = [{"at": 1.0, "words": "a"}, {"at": 2.0, "words": "b"}, {"at": 3.0, "words": "c"},
          {"at": 4.0, "words": "d"}]  # fmt: skip
    got = _thumb.poster_heroes(
        pcs, [["trap", "girl"], [], [], []], c4, {"photo": {"n": 9, "w": 400}}
    )
    check("somebody before an object, the object beside her", got[0] == ("girl", ["trap"]), got)
    check("a moment with nothing on screen takes a picture nobody has, somebody first",
          got[1][0] == "mum" and len({h for h, _ in got}) == 4, got)  # fmt: skip
    check("a brand's mark and a flyer full of words are the last a poster is built on",
          not {"web_mark", "flyer"} & {h for h, _ in got}, got)  # fmt: skip
    got = _thumb.poster_heroes(pcs, [["girl", "trap"], ["girl", "trap"]], c4[:2])
    check("two moments with the same pieces, two different heroes",
          [h for h, _ in got] == ["girl", "trap"], got)  # fmt: skip
    named = [dict(c4[0], hero="mum", **{"with": ["girl"]}), dict(c4[1], hero="nobody")]
    got = _thumb.poster_heroes(pcs, [["trap"], ["trap"]], named)
    check("the writer's own choice stands", got[0] == ("mum", ["girl"]), got)
    check("a name the film has no picture for: the frame's own", got[1][0] == "trap", got)
    got = _thumb.poster_heroes({"scene": dict(pcs["photo"])}, [[]], c4[:1], {"scene": {"n": 40, "w": 1920}})  # fmt: skip
    check("a painted scene laid across the frame is no piece of it", got[0][0] is None, got)
    cs, notes, probs = _thumb.check_concepts(
        [{"at": 2, "hero": "girl", "with": ["trap", "mum"], "words": "Stop and *think*"},
         {"at": 5, "hero": "ghost", "with": ["flyer"], "words": "Ask first"},
         {"at": 8, "words": "Never share codes"}, {"at": 11, "words": "It is *real* money"}],
        30, "", pieces=list(pcs))  # fmt: skip
    check("a concept carries its hero and one more picture",
          not probs and cs[0]["hero"] == "girl" and cs[0]["with"] == ["trap"], (cs, probs))  # fmt: skip
    check("a picture the film does not have is dropped, and said",
          cs[1].get("hero") is None and any("ghost" in x for x in notes), (cs[1], notes))  # fmt: skip
    check("a poster's writer names no layout: one is kept in hand, without a note",
          sorted(c["layout"] for c in cs) == sorted(_thumb.cfg()["concepts"]["layouts"])
          and not any("became" in x for x in notes), (cs, notes))  # fmt: skip

    print("\nposters: the words")
    st = style(outline={"fill": (255, 250, 240), "accent": (255, 216, 74),
                        "stroke": {"w": 0.14, "col": (31, 27, 92)}},
               strips=[(255, 216, 74), (224, 38, 47), (31, 27, 92)])  # fmt: skip
    st["heads"][0].update(file="fonts/Oswald-VF.ttf", family="Oswald", weight="700", upper=True)
    font = _thumb._font(st["heads"][0])
    toks = _thumb.tokens("Цифрові гроші — *справжні*")
    starts = []
    for width in (700, 900, 1200, 1700):
        b = _thumb.block_at(toks, font, 120, width, 900, 3, 0.24)
        starts += [L["text"].split()[0] for L in (b or {"lines": []})["lines"]]
    check("a dash ends a line, it never starts one", starts and "—" not in starts, starts)

    def boxes(lay):
        cut = [L for L in lay["spec"]["scene"] if L["k"] in ("cut", "print")]
        return cut[-1], cut[:-1], [L for L in lay["spec"]["scene"] if L["k"] == "burst"]

    for side in ("left", "right"):
        v = dict(_thumb.poster_variant("film-a", 1), template="side", side=side, strips=False)
        lay = _thumb.layout_poster("Знайомий голос — не *доказ*", st, pcs, "girl", ["trap"],
                                   page, v, "film-a", 1)  # fmt: skip
        hero, rest, burst = boxes(lay)
        b = lay["box"]
        half = hero["w"] / 2
        clear = b[2] <= hero["x"] - half if side == "right" else b[0] >= hero["x"] + half
        check("side, hero %s: the words on the other side, clear of the hero" % side,
              lay["template"] == "side" and clear, (b, hero))  # fmt: skip
        check("...inside the margins, out of YouTube's corner, at a size that reads",
              b[0] >= safe[0] - 1 and b[2] <= safe[2] + 1 and b[1] >= safe[1] - 1
              and not (b[2] > badge[0] and b[3] > badge[1])
              and lay["cap"] >= _thumb.cfg()["cap"]["min_px"], (b, lay["cap"]))  # fmt: skip
        check("...the hero drawn last, on its burst, the other piece behind it",
              lay["spec"]["scene"][-1] is hero and lay["spec"]["scene"][0]["k"] == "burst"
              and [r["name"] for r in rest] == ["trap"], lay["spec"]["scene"])  # fmt: skip
        h = hero["w"] * pcs["girl"]["h"] / pcs["girl"]["w"]
        check("...a figure from the waist up: head in the frame, feet far under it",
              hero["y"] - h / 2 >= 0 and hero["y"] + h / 2 >= 1.4 * H, (hero, h))  # fmt: skip
    check("the film's page under it, pushed in, nothing of the film on it",
          lay["spec"]["stage"] is True and lay["spec"]["camera"] == cam, lay["spec"]["camera"])  # fmt: skip
    check("the words in the film's own outline",
          lay["spec"]["lines"][0]["stroke"] and lay["stroke_px"] > 0, lay["spec"]["lines"][0])  # fmt: skip
    v = dict(_thumb.poster_variant("film-a", 2), template="band", side="left", strips=False)
    lay = _thumb.layout_poster("Покупки — з *дорослим*", st, pcs, "girl", ["mum"], page, v, "film-a", 2)  # fmt: skip
    hero, rest, _ = boxes(lay)
    top = hero["y"] - hero["w"] * pcs["girl"]["h"] / pcs["girl"]["w"] / 2
    check("band: the words across the top, in two lines at most, the hero under them",
          lay["template"] == "band" and len(lay["spec"]["lines"]) <= 2 and lay["box"][3] <= top + 1,
          (lay["box"], top))  # fmt: skip
    check("...somebody beside somebody: a second bust behind, nearly as large",
          len(rest) == 1 and rest[0]["name"] == "mum" and rest[0]["w"] >= 0.8 * hero["w"]
          and abs(rest[0]["x"] - hero["x"]) > 0.3 * hero["w"], (rest, hero))  # fmt: skip
    v = dict(v, template="side")
    lay = _thumb.layout_poster("Покупки тільки з *дорослим*", st, pcs, "trap", [], page, v, "film-a", 3,
                               strips=True)  # fmt: skip
    cards = lay["spec"].get("cards") or []
    check("strips: a line to a strip of the film's paper, no outline",
          lay["strips"] and len(cards) == len(lay["spec"]["lines"]) >= 2
          and not lay["spec"]["lines"][0]["stroke"], lay["spec"].get("cards"))  # fmt: skip
    check("...the starred word's line on a strip of another of its colours",
          len({c["fill"] for c in cards}) == 2, [c["fill"] for c in cards])  # fmt: skip
    check("...an object whole and turned, its burst behind the strips too",
          boxes(lay)[0]["rot"] != 0 and len(boxes(lay)[2]) == 1, lay["spec"]["scene"])  # fmt: skip
    lay = _thumb.layout_poster("One *canvas*", st, pcs, "photo", [], page, v, "film-a", 4)
    check("a picture with a ground of its own is set as a print, with a border of paper",
          boxes(lay)[0]["k"] == "print" and boxes(lay)[0]["border"] > 0, boxes(lay)[0])  # fmt: skip
    quiet = _thumb.backing_colour(st, (34, 193, 180), pcs["girl"], "film-a", 1)
    check("the burst is not the page's colour, nor the hero's",
          not _thumb._near(quiet, (34, 193, 180)) and not _thumb._near(quiet, (242, 201, 76)), quiet)  # fmt: skip

    print("\nposters: judged where the words stand")
    final = Image.new("RGB", (W, H), (240, 168, 60))
    mask = Image.new("L", (W, H), 0)
    d, dm = ImageDraw.Draw(final), ImageDraw.Draw(mask)
    f = _thumb.pil_font("fonts/Oswald-VF.ttf", 180, "700")
    for y, strip, ink in (
        (200, (255, 216, 74), (31, 27, 92)),
        (480, (106, 63, 214), (255, 250, 240)),
    ):
        d.rectangle([700, y, 1700, y + 220], fill=strip)
        d.text((740, y + 10), "ДОРОСЛИМ", font=f, fill=ink)
        dm.text((740, y + 10), "ДОРОСЛИМ", font=f, fill=255)
    o = {"layout": "poster", "cap": 146, "px": 180, "box": (700, 200, 1700, 700), "stroke_px": 0}
    res, fails = _thumb.checks(o, final, mask)
    check("dark words on a light strip and light on a dark one both read",
          not fails and res["contrast"] >= 4.5, (res, fails))  # fmt: skip
    d.rectangle([700, 480, 1700, 700], fill=(255, 240, 200))
    d.text((740, 490), "ДОРОСЛИМ", font=f, fill=(255, 250, 240))
    res, fails = _thumb.checks(o, final, mask)
    check("and one strip that does not read fails the whole poster",
          any("contrast" in x for x in fails), (res, fails))  # fmt: skip


def collage_fixture(home):
    """The collage example in a throwaway folder: its 17 cut-outs stood in for by paper shapes
    with a transparent ground (the real ones are painted by an image model), and a voice
    timeline for its cues."""
    src = os.path.join(_env.ROOT, "config", "sketch", "collage-example")
    d = os.path.join(home, "collage")
    os.makedirs(os.path.join(d, "audio", "vo"))
    os.makedirs(os.path.join(d, "images"))
    for n in ("film.js", "sketch.json", "paint.json"):
        shutil.copyfile(os.path.join(src, n), os.path.join(d, n))
    with open(os.path.join(d, "paint.json"), encoding="utf-8") as f:
        paint = json.load(f)
    rng = np.random.default_rng(3)
    for im in paint["images"]:
        w, h = {"2:3": (500, 750), "3:2": (750, 500)}.get(im.get("aspect"), (640, 640))
        pic = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        col = tuple(int(v) for v in rng.integers(40, 215, 3))
        dr = ImageDraw.Draw(pic)
        dr.ellipse([6, 6, w - 6, h - 6], fill=(250, 248, 240, 255))  # the white border paper has
        dr.ellipse([20, 20, w - 20, h - 20], fill=col + (255,))
        pic.save(os.path.join(d, "images", im["name"] + ".webp"))
    with open(os.path.join(d, "sketch.json"), encoding="utf-8") as f:
        m = json.load(f)
    lines = m["vo"]["lines"]
    step = m["duration"] / len(lines)
    tl = {"duration": m["duration"],
          "lines": [{"i": i, "start": round(0.5 + i * step, 2), "end": round((i + 1) * step, 2),
                     "text": x["text"], "words": []} for i, x in enumerate(lines)]}  # fmt: skip
    with open(os.path.join(d, "audio", "vo", "timeline.json"), "w", encoding="utf-8") as f:
        json.dump(tl, f)
    return d


def live_posters():
    print("\nlive: the collage example, its posters drawn")
    if not importlib.import_module("html-to-image").find_browsers():
        print("  skip no Edge/Chrome found (set HTML2IMG_BROWSER)")
        return
    home = tempfile.mkdtemp(prefix="check-thumb-poster-")
    film = collage_fixture(home)
    pcs = _thumb.film_pieces(film)
    check("its cut-outs are its pieces", len(pcs) == 17 and all(p["cut"] for p in pcs.values()), list(pcs))  # fmt: skip
    check("a portrait is somebody, a filing cabinet is not",
          pcs["printer"]["being"] and pcs["puzzled"]["being"] and not pcs["cabinet"]["being"],
          {n: p["being"] for n, p in pcs.items()})  # fmt: skip
    concepts = [
        {"at": 4.0, "layout": "headline", "words": "Paperwork is *old*", "place": None},
        {"at": 11.0, "layout": "card", "words": "Beer, on a *receipt*", "place": None},
        {
            "at": 19.0,
            "layout": "panel",
            "words": "The first *form*",
            "place": None,
            "hero": "printer",
        },
        {"at": 25.0, "layout": "headline", "words": "Fill in the *blanks*", "place": None},
    ]
    opts = _thumb.make_options(film, concepts, os.path.join(home, "out"), log=print)
    check("four posters", [o["layout"] for o in opts] == ["poster"] * 4,
          [(o["layout"], o["notes"]) for o in opts])  # fmt: skip
    for o in opts:
        ck = o["checks"]
        check("poster %d: legible, in contrast, clear of the stamp, under 2 MB" % o["n"],
              ck.get("cap_168", 0) >= 8 and ck.get("contrast", 0) >= 4.5 and ck.get("in_badge") == 0
              and os.path.getsize(o["file"]) < 2_000_000, (ck, o["notes"]))  # fmt: skip
    check("the writer's hero is the one it is built on",
          any("printer" in n.split(":")[-1].split("+")[0] for n in opts[2]["notes"] if n.startswith("poster")),
          opts[2]["notes"])  # fmt: skip
    check("the words are in the film's own type", all(o["font"] for o in opts), [o["font"] for o in opts])  # fmt: skip
    # the film opens on a newspaper, with no page down yet: its second moment has one
    t = opts[1]["t"]
    into = _thumb.stills_dir(film)
    pages = _thumb.stage_at(into, t)
    check("the stage pass found the film's page, and its colour",
          pages and _thumb._area(pages[0]["box"]) > 0.45 * 1920 * 1080 and pages[0]["col"].startswith("#"),
          pages or "no page")  # fmt: skip
    stage = _thumb.load_still(os.path.join(into, _thumb.still_name(_thumb.STAGE + t)))
    check("the stage is bare: none of the film's words on it",
          not _thumb.text_boxes(stage, min_h=40), _thumb.text_boxes(stage, min_h=40))  # fmt: skip
    final = opts[1]["final"]
    under = _thumb.staged(stage, _thumb.stage_camera(pages))
    diff = (
        np.abs(np.asarray(final, dtype="int16") - np.asarray(under, dtype="int16")).max(axis=2) > 40
    )
    check("and the poster put pieces and words on it (%d%% of the frame)" % round(100 * diff.mean()),
          0.12 < diff.mean() < 0.9, diff.mean())  # fmt: skip
    shutil.rmtree(home, ignore_errors=True)


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
        {"at": 11.0, "layout": "headline", "words": "Pass it *on*", "place": None},
    ]
    t0 = 3.6
    st0 = _thumb.render_stills(film, [t0, _thumb.DECLUTTER + t0])
    seen = _thumb.text_boxes(_thumb.load_still(st0[t0]), min_h=40)
    left = _thumb.text_boxes(_thumb.load_still(st0[_thumb.DECLUTTER + t0]), min_h=40)
    check(
        "the uncluttered still leaves the film's own title out",
        seen and len(left) < len(seen),
        (seen, left),
    )
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
        [o["layout"] for o in opts] == ["headline", "card", "panel", "headline"],
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
    posters()
    if not a.rules_only:
        live()
        live_posters()
    print("\n%d passed, %d failed" % (PASSED[0], len(FAILED)))
    for f in FAILED:
        print("  FAILED: %s" % f)
    sys.exit(1 if FAILED else 0)


if __name__ == "__main__":
    main()
