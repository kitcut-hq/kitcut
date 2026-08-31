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
        # (text, kind, expected) -- all seen on real frames from books-giveaway
        ("4149 4390 2701 0499", "card", True),
        ("4441 **** **** 7789", "card", True),
        ("---- 2527428", "card", True),
        ("Замовлення #1806413786", "card", False),
        ("https://www.threads.com/messages/t/2239405853520443/", "card", False),
        ("UA57 ---- 2527428", "iban", True),
        # OCR splits a masked IBAN across boxes and hands back the head on its
        # own. That head IS the account, so it is a hit, not a false positive.
        ("UA39", "iban", True),
        ("UA", "iban", False),
        ("agamanuk@gmail.com", "email", True),
        ("Ел. пошта agamanuk@gmail.com", "email", True),
        ("pMEAHyrOCbAo@gorokhovsky.FoTOBMionJaTMTW10AWTqyWxKHMKOK3caiT",
         "email", False),
        ("+38 (066) 317-3125", "phone", True),
        ("+380664134978", "phone", True),
        # The national form, with no +38. This one reached a proof frame with
        # a name and a delivery branch beside it before the rule covered it.
        ("Київ, відділення 57, 0939589090, Стрельченко Марія", "phone", True),
        ("066 431 4978", "phone", True),
        # ...but a long digit run is an id, not a phone
        ("1788200601981963", "phone", False),
        ("132 420.45 UAH", "balance", True),
        ("1 190 грн", "balance", False),
        ("CVV2 / CVC2 123", "cvv", True),
        ("11/27", "expiry", True),
    ]
    for text, kind, want in cases:
        got = bool(rules[kind](text, text.lower()))
        check(f"{kind}: {text[:40]}", got, want)

    print("\nscan-pii: Luhn")
    check("Luhn accepts a real PAN", sp.luhn("4149439027010499"), True)
    check("Luhn rejects the same with two digits swapped",
          sp.luhn("4149439027010949"), False)
    check("Luhn rejects a 10-digit order number", sp.luhn("1806413786"), False)

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


def main():
    print("check-screen: silent-screencast pipeline self-test\n")
    pii_rules()
    cut_arithmetic()
    print()
    if FAILS:
        print(f"{len(FAILS)} FAILURE(S):")
        for f in FAILS:
            print(f"  - {f}")
        raise SystemExit(1)
    print("all checks passed")


if __name__ == "__main__":
    main()
