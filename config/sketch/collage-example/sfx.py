"""Write sfx.json for the paperwork film from the voice timeline, on the same words film.js cues.

Every sheet that slides in gets a whoosh and a paper landing; every stamp a thunk; every picture
that pops, a pop; every drop, a soft landing; typing gets keys, handwriting and marker lines a
scribble. Cue times come from audio/vo/timeline.json, so a re-recorded line moves its sounds with
it, exactly as it moves its pictures. Run after sketch-vo.py: python projects/collage-paperwork/sfx.py
"""

import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    with open(os.path.join(HERE, "audio", "vo", "timeline.json"), encoding="utf-8") as f:
        lines = json.load(f)["lines"]

    def norm(s):
        return re.sub(r"[^\w$]", "", s.lower().replace("'", ""))

    def w(li, word, n=0):
        hits = [x["s"] for x in lines[li]["words"] if norm(x["text"]) == norm(word)]
        return hits[n]

    def at(li):
        return lines[li]["start"] - 0.15

    cues = []

    def add(t, fx, db, pan=0.0, **args):
        c = {"t": round(t, 3), "fx": fx, "db": db}
        if pan:
            c["pan"] = pan
        if args:
            c["args"] = args
        cues.append(c)

    def slide(t, pan):  # a sheet slides in and lands
        add(t, "whoosh", -24, pan, sec=0.55, f0=250, f1=2200)
        add(t + 0.42, "crinkle", -29, pan * 0.5, sec=0.3, seed=int(t * 10))

    def stamp(t, db=-17):
        add(t, "thunk", db, sec=0.35)
        add(t, "click", db - 10, sec=0.01, lo=900, hi=3000)

    def pop(t, db=-26, pan=0.0):
        add(t, "pop", db, pan, f0=820, f1=240, sec=0.08)

    def land(t, db=-27, pan=0.0):  # a dropped picture lands (drop takes ~.3 s to arrive)
        add(t + 0.3, "thunk", db, pan, sec=0.25)

    def tape(t, db=-30, pan=0.0):
        add(t, "crinkle", db, pan, sec=0.18, seed=int(t * 7))

    def scribble(t, sec, db=-29):
        add(t, "scribble", db, sec=sec, seed=int(t * 3))

    # 0. front page
    add(0.0, "swoosh_soft", -30, sec=0.5)
    tape(0.6, -27)
    pop(0.9, -25, 0.3)
    land(1.15, -26, 0.3)
    add(1.3, "zip", -27, -0.2, sec=0.4, f0=500, f1=2600)
    stamp(w(0, "paperwork"))
    # I
    slide(at(1), -0.6)
    stamp(w(1, "thousand") + 0.25, -19)
    land(w(1, "receipts"), -28)
    scribble(w(1, "receipts") + 0.3, 0.35)
    land(w(1, "barley"), -27, 0.2)
    tape(w(1, "barley") + 0.15)
    land(w(1, "beer"), -27, 0.4)
    tape(w(1, "beer") + 0.15)
    scribble(w(1, "out"), 0.3)
    # II
    slide(at(2), 0.6)
    stamp(w(2, "fiftyfour") + 0.15, -19)
    pop(w(2, "printed") + 0.1, -26, 0.5)
    tape(w(2, "first"))
    land(w(2, "forms"), -26)
    scribble(w(2, "indulgences"), 0.5)
    scribble(w(2, "blanks"), 0.5, -27)
    scribble(w(2, "blanks") + 0.55, 0.3, -27)
    # III
    slide(at(3), 0.0)
    stamp(w(3, "eighteeneighties") + 0.5, -20)
    add(w(3, "typewriters") + 0.45, "keys", -30, -0.3, sec=0.8, rate=13)
    land(w(3, "carbon"), -28, 0.3)
    tape(w(3, "carbon") + 0.3)
    land(w(3, "turned"), -29)
    add(w(3, "one"), "swoosh_soft", -28, 0.4, sec=0.35)
    add(w(3, "form"), "crinkle", -28, 0.2, sec=0.6, dens=400)
    # IV
    slide(at(4), 0.6)
    add(at(4) + 0.3, "whoosh", -30, 0.6, sec=0.4, f0=400, f1=2400)
    tape(w(4, "thirteen"), -26)
    pop(at(4) + 0.55, -25, 0.2)
    add(w(4, "four"), "crinkle", -27, -0.4, sec=0.35)
    land(w(4, "four") + 0.2, -28, 0.5)
    tape(w(4, "four") + 0.3)
    scribble(w(4, "four") + 0.55, 0.4)
    stamp(w(4, "instructions") + 0.1, -18)
    # V
    slide(at(5), -0.6)
    land(w(5, "offices"), -27, -0.3)
    pop(w(5, "rubber"), -25, 0.4)
    for word, extra in (("approved", 0.25), ("denied", 0.2), ("resubmit", 0.25)):
        stamp(w(6, word) + extra, -14)
    # VI
    slide(at(7), 0.6)
    stamp(w(7, "ninetythree") + 0.3, -20)
    land(w(7, "screens") - 0.3, -28, -0.2)
    pop(w(7, "screens") - 0.4, -25, 0.3)
    add(w(7, "soon"), "keys", -27, 0.3, sec=2.1, rate=14)
    tape(w(7, "boxes"))
    # VII
    slide(at(8), -0.6)
    stamp(w(8, "thousand") + 0.2, -19)
    land(w(8, "signature") - 0.35, -28)
    scribble(w(8, "signature") + 0.1, 1.2, -26)
    pop(w(8, "needed") - 0.2, -26, 0.6)
    scribble(w(8, "ink"), 0.2, -25)
    scribble(w(8, "ink") + 0.18, 0.2, -25)
    # VIII
    slide(at(9), 0.6)
    stamp(w(9, "today") + 0.15, -18)
    land(w(9, "reads") + 0.1, -27, 0.3)
    scribble(w(9, "form"), 0.3)
    te = w(9, "every")
    for i, pan in enumerate((-0.6, 0.0, -0.6, 0.1, 0.6, 0.7, -0.3, 0.7, -0.7)):
        tc = te - 0.35 + i * 0.13
        add(tc, "pop", -28, pan, f0=700 + 60 * i, f1=260, sec=0.07)
        add(tc + 0.45, "blip", -33, pan, f=1320 + 90 * i, sec=0.07)
    add(w(9, "seconds") - 0.1, "thunk", -23, 0.3, sec=0.3)
    # the last page
    slide(at(10), -0.6)
    pop(at(10) + 0.55, -25, 0.4)
    add(at(10) + 0.6, "swoosh_soft", -30, sec=0.4)
    add(w(10, "still"), "thunk", -22, sec=0.3)
    add(w(10, "just") - 0.05, "zip", -25, sec=0.4, f0=500, f1=2600)
    stamp(64.29, -15)

    cues.sort(key=lambda c: c["t"])
    with open(os.path.join(HERE, "sfx.json"), "w", encoding="utf-8") as f:
        json.dump(cues, f, indent=0)
    print("sfx.json: %d cues" % len(cues))


if __name__ == "__main__":
    main()
