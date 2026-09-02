#!/usr/bin/env python
"""Self-test for the silent-screencast pipeline: no GPU, no files, no OCR.

`check-dub.py` exercises the fitting and retune logic that only a paid run
would otherwise reach; `check-multicam.py` does the same for the frame
arithmetic. This is that test for `screen-activity.py`, `screen-cut.py` and
`scan-pii.py`, and it covers the two halves that a render cannot check for you:

  the PII rules      every one of these cases came off real frames. The false
                     positives are the point -- a Threads thread id passes
                     Luhn, and OCR of mangled Cyrillic produces something that
                     matches a loose email pattern. Both would have pixelated
                     content that mattered.

  the cut arithmetic hold/absorb/air on a synthetic label track, the three-way
                     classification, and that --target actually converges. A
                     stutter costs a 20-minute encode to discover.

Invoke as:  python scripts/check-screen.py
"""
import sys
import os
import json
import importlib.util

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import
import numpy as np  # noqa: E402

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name):
    """Import a hyphenated script by path; they are not importable by name."""
    spec = importlib.util.spec_from_file_location(
        name.replace("-", "_"), os.path.join(HERE, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


FAILS = []


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label:<52} "
          f"got={got!s:<6}{'' if ok else ' want=' + str(want)}")
    if not ok:
        FAILS.append(label)


def pii_rules():
    print("scan-pii: pattern rules")
    sp = load("scan-pii")
    rules = {n: f for n, s, f in sp.rules()}
    cases = [
        # (text, kind, expected) -- the SHAPES seen on real frames from
        # books-giveaway, with every value replaced by a synthetic one. The
        # rules are shape rules, so the fixtures cost nothing by being fake --
        # and this file ships to anyone the tooling is shared with.
        ("4111 1111 1111 1111", "card", True),
        ("4111 **** **** 1111", "card", True),
        ("---- 1111111", "card", True),
        ("Замовлення #1234567890", "card", False),
        ("https://www.threads.com/messages/t/1234567890123456/", "card", False),
        ("UA57 ---- 1111111", "iban", True),
        # OCR splits a masked IBAN across boxes and hands back the head on its
        # own. That head IS the account, so it is a hit, not a false positive.
        ("UA39", "iban", True),
        ("UA", "iban", False),
        ("someone@example.com", "email", True),
        ("Ел. пошта someone@example.com", "email", True),
        ("pMEAHyrOCbAo@nGaRbLeD.FoTOBMionJaTMTW10AWTqyWxKHMKOK3caiT",
         "email", False),
        ("+38 (050) 123-4567", "phone", True),
        ("+380501234567", "phone", True),
        # The national form, with no +38. This one reached a proof frame with
        # a name and a delivery branch beside it before the rule covered it.
        ("Київ, відділення 57, 0501234567, Тестенко Тест", "phone", True),
        ("050 123 4567", "phone", True),
        # ...but a long digit run is an id, not a phone
        ("1234567890123456", "phone", False),
        ("132 420.45 UAH", "balance", True),
        ("1 190 грн", "balance", False),
        ("CVV2 / CVC2 123", "cvv", True),
        ("11/27", "expiry", True),
    ]
    for text, kind, want in cases:
        got = bool(rules[kind](text, text.lower()))
        check(f"{kind}: {text[:40]}", got, want)

    print("\nscan-pii: Luhn")
    check("Luhn accepts a real PAN", sp.luhn("4111111111111111"), True)
    check("Luhn rejects the same with one digit mistyped",
          sp.luhn("4111111111111112"), False)
    check("Luhn rejects a 10-digit order number", sp.luhn("1234567890"), False)

    print("\nscan-pii: merge pads and unions overlapping hits")
    hits = [
        {"t": 10.0, "kind": "card", "severity": "high", "text": "a",
         "rect": [0.30, 0.40, 0.10, 0.03]},
        {"t": 14.0, "kind": "card", "severity": "high", "text": "b",
         "rect": [0.32, 0.41, 0.10, 0.03]},
        {"t": 90.0, "kind": "card", "severity": "high", "text": "c",
         "rect": [0.80, 0.10, 0.05, 0.03]},
    ]
    g = sp.merge(hits, gap=6.0)
    check("two overlapping hits become one region", len(g), 2)
    first = [x for x in g if x["n"] == 2][0]
    check("its window covers both, plus the gap", first["when"], [4.0, 20.0])
    check("its rect unions both, plus the pad",
          [round(v, 3) for v in first["rect"]], [0.288, 0.388, 0.144, 0.064])


def cut_arithmetic():
    print("\nscreen-cut: hold dilation")
    sc = load("screen-cut")
    flag = np.zeros(20, bool)
    flag[10] = True
    got = sc.hold_on(flag, fps=2.0, seconds=1.0)
    check("one sample becomes five at 2 fps / 1 s hold", int(got.sum()), 5)
    check("nothing leaks past the ends",
          bool(sc.hold_on(np.zeros(10, bool), 2.0, 1.0).any()), False)

    print("\nscreen-cut: three-way classification")
    n = 60
    track = {
        "activity": [0.0] * n, "sample_fps": 2.0, "duration": 30.0,
        "region_activity": {
            # 0-10s nothing, 10-20s panel only, 20-30s main
            "main":  [0.0] * 40 + [0.05] * 20,
            "panel": [0.0] * 20 + [0.05] * 20 + [0.0] * 20,
        },
    }
    cfg = dict(sc.DEFAULTS, hold=0.0, panel_hold=0.0)
    lab = sc.classify(track, cfg)
    check("dead stretch classifies as drop", int(lab[5]), 0)
    check("panel-only stretch classifies as speed", int(lab[25]), 1)
    check("main stretch classifies as keep", int(lab[50]), 2)

    print("\nscreen-cut: short runs are absorbed by the LONGER neighbour")
    lab = np.array([1] * 40 + [2] * 2 + [1] * 40, np.int8)
    out = sc.smooth(lab, fps=2.0, cfg=dict(sc.DEFAULTS, air=0.0, min_keep=1.2))
    check("a 1 s keep island inside a long wait joins the wait",
          sorted(set(out.tolist())), [1])

    print("\nscreen-cut: air is handed back at 1x, not sped")
    lab = np.array([2] * 10 + [0] * 40 + [2] * 10, np.int8)
    out = sc.smooth(lab, fps=2.0,
                    cfg=dict(sc.DEFAULTS, air=1.0, min_drop=1.0, min_keep=0.5))
    check("the sample either side of a dropped run is keep, not speed",
          (int(out[10]), int(out[59])), (2, 2))
    check("the middle of the dropped run is still dropped", int(out[35]), 0)

    print("\nscreen-cut: segments and speeds")
    segs = sc.segments(np.array([2] * 10 + [0] * 10 + [1] * 10, np.int8),
                       fps=2.0, dur=15.0)
    check("three runs become three segments", len(segs), 3)
    check("boundaries land on the sample grid",
          [(a, b, c) for a, b, c in segs], [(0.0, 5.0, 2), (5.0, 10.0, 0),
                                            (10.0, 15.0, 1)])

    print("\nscreen-cut: parse_hms")
    check("8:00 is 480 s", sc.parse_hms("8:00"), 480.0)
    check("1:02:03 is 3723 s", sc.parse_hms("1:02:03"), 3723.0)
    check("90 is 90 s", sc.parse_hms("90"), 90.0)

    print("\nscreen-cut: blur rects survive the round trip to pixels")
    sa = load("screen-activity")
    ys, xs = sa.rect_slice([0.5, 0.25, 0.25, 0.5], 400, 200)
    check("x fraction maps to columns", (xs.start, xs.stop), (200, 300))
    check("y fraction maps to rows", (ys.start, ys.stop), (50, 150))

    print("\nscreen-activity: mask_from blanks the ignored rectangle")
    keep = sa.mask_from([[0.0, 0.0, 0.5, 1.0]], 100, 10)
    check("half the frame is masked out", int(keep.sum()), 500)


def pipeline_pieces():
    print("\nscan-pii: rules re-applied to cached OCR lines")
    sp = load("scan-pii")
    frames = [{"t": 4.0, "carried": False, "lines": [
        {"box": [0.1, 0.2, 0.1, 0.02], "text": "+38 (066) 431-4978", "conf": 0.9},
        {"box": [0.1, 0.3, 0.1, 0.02], "text": "Замовлення #1234567890", "conf": 0.9}]},
              {"t": 8.0, "carried": True, "lines": [
        {"box": [0.1, 0.2, 0.1, 0.02], "text": "+38 (066) 431-4978", "conf": 0.9}]}]
    hits = sp.apply_rules(frames)
    check("a phone on two cached frames is two hits", len(hits), 2)
    check("an order number is not a card", any(h["kind"] == "card" for h in hits), False)
    check("hits keep the cached frame time", sorted(h["t"] for h in hits), [4.0, 8.0])

    print("\ntrack-blur: recall harness on a synthetic timeline")
    tb = load("track-blur")
    info = {"w": 1000, "h": 500, "fps": 10.0}
    # boxes on frames 40..59 covering (100..300, 100..120); nothing elsewhere
    runs = [[0, 39, []], [40, 59, [[100, 100, 300, 120, "phone:0661234567"]]], [60, 99, []]]
    check("boxes_at inside a run", len(tb.boxes_at(runs, 45)), 1)
    check("boxes_at outside every run", len(tb.boxes_at(runs, 70)), 0)
    import tempfile
    d = tempfile.mkdtemp()
    pii = os.path.join(d, "x.pii.json")
    with open(pii, "w", encoding="utf-8") as f:
        json.dump({"src": "fake/src.mp4", "sample_fps": 0.25, "hits": [
            {"t": 4.0, "kind": "phone", "text": "0661234567", "rect": [0.1, 0.2, 0.2, 0.04], "conf": 0.9},
            {"t": 8.0, "kind": "phone", "text": "0661234567", "rect": [0.5, 0.5, 0.2, 0.04], "conf": 0.9},
        ]}, f)
    per, misses = tb.recall(runs, [pii], "fake/src.mp4", info, [], {"phone"})
    check("covered hit at 4 s counts (slot-tolerant: frames 40..70)", per["phone:0661234567"][1], 1)
    check("uncovered hit at 8 s is a miss", len(misses), 1)
    hand = [{"rect": [0.5, 0.5, 0.2, 0.04], "when": [6.0, 10.0]}]
    per2, misses2 = tb.recall(runs, [pii], "fake/src.mp4", info, [], {"phone"}, hand_rects=hand)
    check("a hand rect active at the time counts as coverage", len(misses2), 0)
    # an OCR line that carries its label: the number is half the line, and a
    # box over the number alone (half the line's area) must count as covered
    pii2 = os.path.join(d, "y.pii.json")
    with open(pii2, "w", encoding="utf-8") as f:
        json.dump({"src": "fake/src.mp4", "sample_fps": 0.25, "hits": [
            {"t": 4.0, "kind": "phone", "text": "Телефон: 0661234567",
             "rect": [0.1, 0.2, 0.2, 0.04], "conf": 0.9}]}, f)
    half = [[0, 99, [[200, 100, 300, 120, "k"]]]]
    check("a labelled line needs only its digits covered",
          tb.recall(half, [pii2], "fake/src.mp4", info, [], {"phone"})[0]["phone:0661234567"][1], 1)
    check("...but a bare number still needs most of its box",
          tb.recall(half, [pii], "fake/src.mp4", info, [], {"phone"})[0]["phone:0661234567"][1], 0)

    print("\nscreen-cut: piece key ignores what does not touch the pixels")
    sc = load("screen-cut")
    plan = {"path": __file__, "segments": [{"start": 0, "end": 1, "speed": 1.0, "out": 1}],
            "src": {"blur": []}}
    a = sc.piece_key(plan, dict(sc.DEFAULTS, speed=6.0))
    b = sc.piece_key(plan, dict(sc.DEFAULTS, speed=19.0, min_drop=9))
    check("speed/min_drop are plan inputs, not piece inputs", a, b)
    c = sc.piece_key(plan, dict(sc.DEFAULTS, cq=15))
    check("cq changes the key", a == c, False)
    check("a blur rect changes the key",
          a == sc.piece_key(dict(plan, src={"blur": [{"rect": [0, 0, 1, 1]}]}), dict(sc.DEFAULTS)), False)


def graph_blurs_after_the_cut():
    """build_filter(): one gaussian, after the trims, on a mask cut on the
    same boundaries -- the shape KI-021 asks for. A regression here is a
    silent 2-3x on every render, or a mask one frame out of step."""
    print("")
    print("screen-cut: the graph paints the mask in source time and blurs after the cut")
    sc = load("screen-cut")
    cfg = dict(sc.DEFAULTS)
    segs = [{"start": 0.0, "end": 1.0, "speed": 1.0, "out": 1.0},
            {"start": 2.5, "end": 4.0, "speed": 3.0, "out": 0.5},
            {"start": 9.0, "end": 9.5, "speed": 1.0, "out": 0.5}]
    soft = [{"rect": [0.1, 0.1, 0.2, 0.05], "when": [0.0, 3.0]},
            {"rect": [0.5, 0.6, 0.1, 0.05], "when": [9.0, 9.5]}]
    box = [{"rect": [0.3, 0.3, 0.1, 0.1], "mode": "box", "when": [0.0, 1.0]}]
    plan = {"path": "fake/src.mp4", "segments": segs, "src": {"blur": soft + box},
            "info": {"width": 1818, "height": 1080, "fps": 30.0},
            "mask_listing": "fake/masks.txt"}
    parts, vw, vh = sc.build_filter(plan, cfg, 0)
    first_concat = next(i for i, x in enumerate(parts) if "concat=n=3" in x)
    gauss = [i for i, x in enumerate(parts) if "gblur=sigma=3.0" in x]
    check("exactly one gaussian for mask + soft rects", len(gauss), 1)
    check("...and it runs after the cut", gauss[0] > first_concat, True)
    trims = lambda tag: [x.split(",")[0].split("]")[1] for x in parts
                         if x.startswith(f"[{tag}0_") and "trim=start=" in x]
    check("the mask is cut on the picture's boundaries", trims("mt"), trims("t"))
    check("both streams are cut into every segment", len(trims("t")), 3)
    white = [x for x in parts if "color=white" in x]
    check("every soft rect is painted onto the mask", len(white), 2)
    check("...gated to its source-time window", all("between(t" in x for x in white), True)
    boxi = next(i for i, x in enumerate(parts) if f"color={cfg['box_color']}" in x)
    check("a box rect stays per-rect, before the cut", boxi < first_concat, True)
    check("the mask stream is the second input", any("[1:v]" in x for x in parts), True)
    check("output is the padded source label", parts[-1].endswith("[v0]"), True)

    # no tracker, one soft rect: the mask comes from the video, not a color source
    plan2 = dict(plan, src={"blur": soft[:1]})
    plan2.pop("mask_listing")
    parts2, _, _ = sc.build_filter(plan2, cfg, 0)
    check("untracked: the mask is a black frame derived from the video",
          any("drawbox=x=0:y=0:w=iw:h=ih:color=black" in x for x in parts2), True)
    check("untracked: no second input is referenced", any("[1:v]" in x for x in parts2), False)
    check("untracked: still one gaussian, after the cut",
          [i > next(i for i, x in enumerate(parts2) if "concat=n=3" in x)
           for i, x in enumerate(parts2) if "gblur=sigma=3.0" in x], [True])

    # nothing to redact: no mask, no gaussian, no alphamerge
    plan3 = dict(plan, src={"blur": []})
    plan3.pop("mask_listing")
    parts3, _, _ = sc.build_filter(plan3, cfg, 0)
    check("nothing to redact: no gaussian at all", any("gblur=sigma=3.0" in x for x in parts3), False)
    check("nothing to redact: no alphamerge", any("alphamerge" in x for x in parts3), False)


def run_log_survives_a_crash():
    """A killed run must still say it was killed.

    The whole point of the run log is the case where nobody was watching, so
    the format has to survive the process dying mid-write: JSONL, flushed per
    line, with an `end` record written by the context manager on the way out
    for every exit path.
    """
    print("")
    print("_runlog: a run records how it ended, on every exit path")
    import tempfile, json as _json
    rl = load("_runlog")
    d = tempfile.mkdtemp(prefix="runlog-")

    with rl.RunLog(d, argv=["--project", "x"], stages=["render", "gate"]) as log:
        log.stage("render", "ran", 12.5)
        log.note("gate", "round 1: 9 hit(s)", round=1, hits=9)
    recs = rl.read(rl.latest(d)[0])
    check("first record names the run", recs[0]["ev"], "run")
    check("the stage is recorded", [r["stage"] for r in recs if r["ev"] == "stage"], ["render"])
    check("the note keeps its numbers", [r["hits"] for r in recs if r["ev"] == "note"], [9])
    check("a clean exit ends 'ok'", rl.summary(recs)[0], "ok")

    try:
        with rl.RunLog(d) as log:
            log.stage("render", "ran", 1.0)
            raise SystemExit("STOP: the gate still finds secrets")
    except SystemExit:
        pass
    recs = rl.read(rl.latest(d)[0])
    check("a failed stage ends 'stopped'", rl.summary(recs)[0], "stopped")
    check("...and keeps the reason", "still finds secrets" in rl.summary(recs)[2], True)

    try:
        with rl.RunLog(d) as log:
            raise ZeroDivisionError("boom")
    except ZeroDivisionError:
        pass
    check("a crash ends 'failed'", rl.summary(rl.read(rl.latest(d)[0]))[0], "failed")

    # a run killed outright: no end line at all, and that must not read as ok
    log = rl.RunLog(d)
    log.stage("track", "ran", 3.0)
    recs = rl.read(log.path)
    check("no end record reads as 'running', not 'ok'", rl.summary(recs)[0], "running")

    # a half-written last line is skipped, not fatal
    with open(log.path, "a", encoding="utf-8") as f:
        f.write('{"ev": "stage", "stage": "gate"')
    check("a truncated last line is skipped", len(rl.read(log.path)), len(recs))


def known_issues_register():
    print("\ndocs/known-issues.md: every entry parses, ids are unique")
    import re
    path = os.path.join(HERE, "..", "docs", "known-issues.md")
    rx = re.compile(r"^### (KI-\d+) · (open|limitation|fixed) · ([\w,]+) · (.+?)\s*$")
    ids, bad = [], []
    for ln in open(path, encoding="utf-8"):
        if ln.startswith("### "):
            m = rx.match(ln)
            if m:
                ids.append(m.group(1))
            else:
                bad.append(ln.strip()[:60])
    check("every ### header has the fixed shape", bad, [])
    check("ids are unique", len(ids), len(set(ids)))
    check("the register is not empty", len(ids) > 0, True)


def frame_change_matches_numpy():
    """frame_change() must equal the numpy spelling it replaced, exactly.

    It is 13x faster and it decides which frames the tracker looks at, so a
    drift here would silently change what gets blurred. Compare the two on
    frames shaped like real screen content -- a static page, a caret blink,
    a scroll, a page change -- not on noise, where everything differs.
    """
    print("")
    print("track-blur: the fast frame-change equals the numpy original")
    import numpy as np
    tb = load("track-blur")
    rng = np.random.default_rng(7)
    h, w = 240, 400
    page = rng.integers(0, 255, (h, w), dtype=np.uint8)

    def ref(fr, prev):
        return float((np.abs(fr.astype(np.int16) - prev.astype(np.int16)) > 12).mean())

    cases = {}
    cases["identical frames"] = (page, page.copy())
    caret = page.copy()
    caret[10:20, 30:33] = 255
    cases["a caret blink"] = (page, caret)
    cases["a scroll"] = (page, np.roll(page, -7, axis=0))
    cases["a page change"] = (page, rng.integers(0, 255, (h, w), dtype=np.uint8))
    band = page.copy()
    band[100:140, :] = 255
    cases["one changed band"] = (page, band)
    # a difference of exactly the threshold must fall the same side on both
    edge = np.clip(page.astype(np.int16) + 12, 0, 255).astype(np.uint8)
    cases["a delta of exactly 12 (the boundary)"] = (page, edge)

    for label, (a, b) in cases.items():
        check(label, tb.frame_change(b, a), ref(b, a))

    # ...and the skip decision itself, which is what actually gates the work
    same = all((tb.frame_change(b, a) < tb.CHANGE_SKIP) ==
               (ref(b, a) < tb.CHANGE_SKIP) for a, b in cases.values())
    check("every CHANGE_SKIP decision agrees", same, True)


def film_time_redaction():
    """film-redact: the state -> mask union, and the hand-rect escape hatch.

    A rect missed here is a secret on YouTube, and the union rule is exactly
    the arithmetic a render cannot check for you: mask_runs coalesces states
    that blur the same pixels, so an off-by-one in the overlap test shows up
    as a stretch of film with no blur and nothing else wrong.
    """
    fr = load("film-redact")
    print("")
    print("film-redact: hand rects are unioned by film-time overlap")
    hand = [{"rect": [0.1, 0.2, 0.3, 0.05], "when": [10.0, 20.0], "why": "art"},
            {"rect": [0.5, 0.5, 0.1, 0.1], "why": "whole film"}]
    check("inside the window", len(fr.hand_boxes(hand, 12.0, 13.0)), 2)
    check("before it", [b["rect"][0] for b in fr.hand_boxes(hand, 0.0, 5.0)], [0.5])
    check("after it", [b["rect"][0] for b in fr.hand_boxes(hand, 25.0, 26.0)], [0.5])
    check("a state STRADDLING the start is covered",
          len(fr.hand_boxes(hand, 9.5, 10.5)), 2)
    check("a state ending exactly at t0 is not",
          len(fr.hand_boxes(hand, 5.0, 10.0)), 1)
    check("a rect with no window covers the whole film",
          len(fr.hand_boxes(hand, 999.0, 1000.0)), 1)
    check("the tile carries its reason, never the secret",
          fr.hand_boxes(hand, 12.0, 13.0)[0]["text"], "art")

    print("")
    print("film-redact: mask runs coalesce states that blur the same pixels")
    import tempfile
    states = [{"i0": 0, "i1": 29, "kind": "page", "t": 0.0, "dur": 1.0},
              {"i0": 30, "i1": 59, "kind": "page", "t": 1.0, "dur": 1.0},
              {"i0": 60, "i1": 89, "kind": "page", "t": 2.0, "dur": 1.0}]
    per = {"0": [{"rect": [0.1, 0.1, 0.2, 0.05], "kind": "card"}],
           "1": [{"rect": [0.1, 0.1, 0.2, 0.05], "kind": "card"}]}
    info = {"w": 320, "h": 180, "fps": 30.0}
    with tempfile.TemporaryDirectory() as td:
        runs, _ = fr.mask_runs(states, per, {}, info, td)
        check("two states with the same boxes make ONE run", len(runs), 2)
        check("...and it spans both", (runs[0]["i0"], runs[0]["i1"]), (0, 59))
        # A cleared state becomes empty, so it coalesces with the empty state
        # AFTER it -- fewer runs, not more. That is the whole point of keying
        # a run on its pixels: a still page costs one PNG however long it holds.
        runs, _ = fr.mask_runs(states, per, {"1": "clear"}, info, td)
        check("a cleared state joins the empty one next to it", len(runs), 2)
        check("...and only the first state is still blurred",
              (runs[0]["i0"], runs[0]["i1"], len(runs[0]["key"])), (0, 29, 1))
        check("...leaving the rest clear", len(runs[1]["key"]), 0)
        runs, _ = fr.mask_runs(states, per, {"0": "clear", "1": "clear"},
                               info, td)
        check("clearing every box leaves one empty run", len(runs), 1)
        hand = [{"rect": [0.5, 0.5, 0.1, 0.1], "when": [0.0, 3.0], "why": "art"}]
        runs, _ = fr.mask_runs(states, per, {"1": "clear"}, info, td, hand=hand)
        check("a hand rect outlives the clear that dropped the detection",
              [len(r["key"]) for r in runs], [2, 1])
        runs, _ = fr.mask_runs(states, per, {"0": "clear", "1": "clear"},
                               info, td, hand=hand)
        check("...and a review cannot clear it away at all",
              [len(r["key"]) for r in runs], [1])


def main():
    print("check-screen: silent-screencast pipeline self-test\n")
    pii_rules()
    cut_arithmetic()
    pipeline_pieces()
    frame_change_matches_numpy()
    film_time_redaction()
    graph_blurs_after_the_cut()
    run_log_survives_a_crash()
    known_issues_register()
    print()
    if FAILS:
        print(f"{len(FAILS)} FAILURE(S):")
        for f in FAILS:
            print(f"  - {f}")
        raise SystemExit(1)
    print("all checks passed")


if __name__ == "__main__":
    main()
