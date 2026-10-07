#!/usr/bin/env python
"""A film's own motion check and the reader that looks at it before it is called done, checked
without Claude: python studio/test_review.py

    the sheets     the whole film a frame a second, in the film's own shape, with the words said
    the strips     the times of a close look stay inside the film
    the events     what motion.events() reads from a probe report: the same character twice, a
                   body cut by what it is inside, into a thing, squashed through flat, a colour
                   over the whole frame -- and what it leaves alone (furniture, a held squash)
    the probe      sketch/probe.js in a real browser, on a small film that does each of those
    the reader     its answer made safe (kinds, times as printed, sentences), which moments get a
                   close-up, what a second reading may drop, two calls with the pictures in order

About fifteen seconds; the probe is the browser's.
"""

import os
import sys
import json
import asyncio
import tempfile
import subprocess

HOME = tempfile.mkdtemp(prefix="studio-test-")
os.environ["STUDIO_HOME"] = HOME
HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import agent  # noqa: E402, F401 -- imports _env first
import motion  # noqa: E402
import review  # noqa: E402
import tools  # noqa: E402

bad = []


def expect(name, ok, detail=""):
    print(
        "%s  %s%s"
        % ("ok  " if ok else "FAIL", name, ("  -- " + str(detail)) if detail and not ok else "")
    )
    if not ok:
        bad.append(name)


# ------------------------------------------------------------------ a probe report made by hand
def report(frames, keys, step=0.1):
    return {"step": step, "w": 1920, "h": 1080, "keys": keys, "frames": frames}


def scope(k, x0, y0, x1, y1, an=1.0, cut=0.0, clipped=0, parent=-1, ov=0, alpha=1.0):
    return [k, x0, y0, x1, y1, 100, an, an, cut, clipped, alpha, ov, parent]


KEYS = ["room.draw", "cat.sit", "cat.walk", "box.draw", "room.sofa"]
ROOM, SOFA = scope(0, -200, -200, 1200, 1200), scope(4, 100, 600, 400, 800)


def film(fn, n=100, veil=None):
    """n frames a tenth of a second apart; fn(i) -> the scopes besides the room and its sofa."""
    return report(
        [
            {"t": i / 10, "cam": [1, 0, 0], "v": veil(i) if veil else 0, "s": [ROOM, SOFA, *fn(i)]}
            for i in range(n)
        ],
        KEYS,
    )


def kinds(ev):
    return sorted({e["kind"] for e in ev})


def main():
    from PIL import Image, ImageDraw  # noqa: PLC0415

    # ---- the sheets
    for shape, cols in (((1920, 1080), 4), ((1080, 1080), 5), ((1080, 1920), 7)):
        d = os.path.join(HOME, "frames-%dx%d" % shape)
        os.makedirs(d)
        for i in range(90):  # 45 s at two frames a second
            im = Image.new("RGB", (shape[0] // 4, shape[1] // 4), "#f7f2e7")
            ImageDraw.Draw(im).rectangle((10 + i, 20, 60 + i, 70), fill="#c2592a")
            im.save(os.path.join(d, "%06.2f.png" % (i / 2)))
        said = [(0.5, 1.2, "Привіт,"), (1.2, 2.4, "world."), (30.0, 31.0, "Later.")]
        got = motion.sheets(d, os.path.join(HOME, "out-%dx%d" % shape), said)
        with Image.open(got[0]) as im:
            size = im.size
        cell = (motion.SHEET_W - 6 * (cols - 1)) // cols
        rows = -(-min(len(range(45)), motion.SHEET_PER) // cols)
        want_h = 34 + rows * (round(cell * shape[1] / shape[0]) + 50 + 6)
        expect(
            "sheets, %dx%d: 45 whole seconds on %d sheets of %d, cells in the film's shape"
            % (shape[0], shape[1], len(got), motion.SHEET_PER),
            len(got) == 3 and size == (motion.SHEET_W, want_h),
            (len(got), size, want_h),
        )
    again = motion.sheets(d, os.path.join(HOME, "out-%dx%d" % shape), [], span=(10, 20))
    left = [f for f in os.listdir(os.path.join(HOME, "out-%dx%d" % shape)) if f.startswith("film-")]
    expect(
        "sheets: a scene's stretch only, and the film's old sheets are gone",
        len(again) == 1 and left == ["film-01.jpg"],
        left,
    )
    expect(
        "spoken: a line without word times is said over its whole span",
        motion.spoken(os.devnull) == []
        and _spoken({"lines": [{"text": "Hello there", "start": 1, "end": 2}]})
        == [(1.0, 2.0, "Hello there")],
    )

    # ---- the strips
    a, b, c = (
        tools.strip_times(10, 0, 120),
        tools.strip_times(0.1, 0, 120),
        tools.strip_times(119.9, 0, 119.98),
    )
    expect(
        "strip: eight frames a tenth apart, the moment among the first, inside the film",
        a == [9.7, 9.8, 9.9, 10.0, 10.1, 10.2, 10.3, 10.4]
        and b[0] == 0
        and len(b) == 8
        and c[-1] <= 119.98
        and len(c) == 8,
        (a, b, c),
    )

    # ---- the events
    still = lambda i: [scope(1, 500, 500, 600, 700)]  # noqa: E731
    expect(
        "events: a room, a sofa and a cat who sits all film long are nobody's glitch",
        motion.events(film(still)) == [],
        motion.events(film(still)),
    )

    def twice(i):  # she walks; for half a second she also sits where she is going
        out = [scope(2, 200 + 5 * i, 500, 300 + 5 * i, 700)] if i < 55 else []
        return out + ([scope(1, 800, 500, 900, 700)] if i >= 50 else [])

    ev = motion.events(film(twice))
    expect(
        "events: the same cat in two places for half a second is a double, at its time",
        kinds(ev) == ["double"] and abs(ev[0]["t0"] - 5.0) < 0.11 and abs(ev[0]["t1"] - 5.4) < 0.11,
        ev,
    )

    def mirror(i):  # she walks past a second one that is there for most of the film
        return [
            scope(2, 200 + 5 * i, 500, 300 + 5 * i, 700),
            *([scope(1, 800, 500, 900, 700)] if i >= 20 else []),
        ]

    expect(
        "events: two of them together for most of the film are meant",
        "double" not in kinds(motion.events(film(mirror))),
        motion.events(film(mirror)),
    )

    def boxed(i):  # she walks to a box and is inside it, cut by its opening
        box = scope(3, 700, 500, 900, 700)
        if i < 40:
            return [box, scope(2, 300 + 9 * i, 500, 400 + 9 * i, 700)]
        return [box, scope(2, 690, 500, 790, 700, cut=0.55 if i < 70 else 0.1, clipped=1, parent=3)]

    ev = motion.events(film(boxed))
    expect(
        "events: into the box, and cut by its edge while more than a third of her is hidden",
        kinds(ev) == ["cut", "into"]
        and any(
            e["kind"] == "cut" and abs(e["t0"] - 4.0) < 0.11 and abs(e["t1"] - 6.9) < 0.11
            for e in ev
        )
        and "box" in next(e["text"] for e in ev if e["kind"] == "into"),
        ev,
    )

    def flip(i):  # she walks, and turns round by being scaled through flat
        an = 1.0 if i < 50 or i > 56 else abs(1 - (i - 50) / 3)
        return [scope(2, 200 + 5 * i, 500, 300 + 5 * i, 700, an=max(0.02, an))]

    ev = motion.events(film(flip))
    expect(
        "events: flipped through flat is a sliver, once",
        kinds(ev) == ["sliver"] and len(ev) == 1 and 5.0 <= ev[0]["t0"] <= 5.3,
        ev,
    )
    flat = lambda i: [
        scope(2, 200 + 5 * i, 500, 300 + 5 * i, 700),
        scope(1, 600, 720, 900, 760, an=0.2),
    ]  # noqa: E731
    expect(
        "events: a squash that is held (her shadow on the floor) is left alone",
        motion.events(film(flat)) == [],
        motion.events(film(flat)),
    )
    ev = motion.events(
        film(still, veil=lambda i: 0.2 if i < 40 else min(0.54, 0.2 + 0.017 * (i - 40)))
    )
    expect(
        "events: a colour laid over the frame and rising is a wash; a steady texture is not",
        kinds(ev) == ["wash"] and motion.events(film(still, veil=lambda i: 0.2)) == [],
        ev,
    )

    # ---- the probe, in a real browser
    d = os.path.join(HOME, "probed")
    os.makedirs(os.path.join(d, "cast"))
    with open(os.path.join(d, "sketch.json"), "w", encoding="utf-8") as f:
        json.dump(
            {"title": "probe", "duration": 6, "fps": 30, "film": "film.js", "cast": "cast"}, f
        )
    with open(os.path.join(d, "cast", "blob.js"), "w", encoding="utf-8") as f:
        f.write(CAST)
    with open(os.path.join(d, "film.js"), "w", encoding="utf-8") as f:
        f.write(FILM)
    r = subprocess.run(
        [
            sys.executable,
            "-X",
            "utf8",
            os.path.join(KIT, "scripts", "sketch-render.py"),
            "--manifest",
            os.path.join(d, "sketch.json"),
            "--stills",
            "0",
            "--into",
            "probe",
            "--probe",
            "0.1",
        ],
        cwd=d,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    try:
        with open(os.path.join(d, "probe", "report.json"), encoding="utf-8") as f:
            rep = json.load(f)["probe"]
    except (OSError, ValueError, KeyError):
        rep = {}
    expect(
        "probe: the film is played once more without painting, whole, and says who drew",
        r.returncode == 0
        and not rep.get("error")
        and len(rep.get("frames") or []) >= 15
        and {"blob.body", "blob.box"} <= set(rep.get("keys") or []),
        (r.stdout + r.stderr)[-600:] or rep.get("error"),
    )
    ev = motion.events(rep) if rep.get("frames") else []
    got = {e["kind"]: e for e in ev}
    expect(
        "probe: the flip at 1 s, the wash from 2 s, into the box at 4 s and cut by it after",
        {"sliver", "wash", "into", "cut"} <= set(got)
        and 0.8 <= got["sliver"]["t0"] <= 1.4
        and 1.8 <= got["wash"]["t0"] <= 2.3
        and 3.8 <= got["into"]["t0"] <= 4.2
        and got["cut"]["t0"] >= 3.9,
        ev,
    )
    expect(
        "probe: the still it was asked for is painted all the same",
        os.path.isfile(os.path.join(d, "probe", "000.00.png"))
        and _darkest(os.path.join(d, "probe", "000.00.png")) < 200,
    )

    # ---- the reader's answer
    c = review.clean(
        {
            "findings": [
                {
                    "t0": "1:20.1",
                    "t1": "1:20.7",
                    "kind": "Through",
                    "what": " she goes  through the wall ",
                    "fix": "the door",
                    "must": True,
                },
                {
                    "t0": 43,
                    "t1": 41,
                    "kind": "taste",
                    "what": "I would use another green",
                    "must": True,
                },
                {"t0": "9:00", "t1": "9:05", "kind": "idle", "what": "past the end"},
                {"t0": "x", "kind": "idle", "what": "no time"},
                {"t0": 3, "kind": "idle"},
            ],
            "look_closer": ["1:20.4", 80.6, 86.5, "nine", 500],
        },
        120,
    )
    f = c["findings"]
    expect(
        "reader: times as printed on the frames, kinds from the list, a must only for one of them",
        [x["kind"] for x in f] == ["through", "other"]
        and f[0]
        == {
            "t0": 80.1,
            "t1": 80.7,
            "kind": "through",
            "what": "she goes through the wall",
            "fix": "the door",
            "must": True,
        }
        and f[1]["must"] is False
        and (f[1]["t0"], f[1]["t1"]) == (41.0, 43.0),
        f,
    )
    expect(
        "reader: its close-ups are inside the film and apart",
        c["look_closer"] == [80.4, 86.5],
        c["look_closer"],
    )
    expect(
        "reader: an answer that is not one is a clean film, not a crash",
        review.clean(None, 60) == {"findings": [], "look_closer": []},
    )

    ev = [
        {"t0": 26.0, "t1": 36.3, "kind": "cut", "text": "cut"},
        {"t0": 49.9, "t1": 50.3, "kind": "double", "text": "twice"},
        {"t0": 10.2, "t1": 10.3, "kind": "pop", "text": "pop"},
        {"t0": 96.2, "t1": 100.6, "kind": "wash", "text": "wash"},
    ]
    m = review.moments(ev, [50.2, 80.5])
    expect(
        "reader: close-ups for the machine's telling moments (a long one twice), then its own; none for a pop or a wash",
        [t for t, _ in m] == [26.3, 31.1, 50.1, 80.5] and m[3][1] == "you asked",
        m,
    )
    first = [
        {"t0": 51.0, "t1": 62.0, "kind": "idle", "what": "a hand hangs", "fix": "", "must": True},
        {"t0": 80.2, "t1": 80.5, "kind": "through", "what": "the wall", "fix": "", "must": True},
        {"t0": 40.0, "t1": 49.5, "kind": "idle", "what": "the plant", "fix": "", "must": False},
    ]
    final = [
        {
            "t0": 80.1,
            "t1": 80.6,
            "kind": "through",
            "what": "the wall, seen closer",
            "fix": "",
            "must": True,
        }
    ]
    k = review.kept(first, final, [(45.5, ""), (80.4, "")])
    expect(
        "reader: the second reading can clear what it looked at closer, not what it did not",
        [x["what"] for x in k] == ["a hand hangs", "the wall, seen closer"],
        k,
    )

    # ---- the reader, with Claude stood in for
    calls = []

    async def ask(text, images):
        calls.append((text, images))
        if len(calls) == 1:
            return {"findings": first, "look_closer": ["1:20.4"]}, 0.25
        return {"findings": final, "look_closer": []}, 0.5

    async def sheets():
        return [got_sheet, got_sheet]

    async def strips(want):
        asked.extend(want)
        return [got_sheet for _ in want]

    asked, got_sheet = [], os.path.join(HOME, "out-1920x1080", "film-01.jpg")
    mat = {
        "title": "A test",
        "purpose": "For: everyone",
        "length": 120.0,
        "narration": [(1.0, 2.5, "Hello.")],
        "cast": ["cat: a cat"],
    }
    r = asyncio.run(
        review.read({"mat": mat, "sheets": sheets, "events": ev, "strips": strips}, ask)
    )
    expect(
        "reader: two calls -- the whole film, then the close-ups it and the machine asked for",
        r["calls"] == 2
        and r["cost_usd"] == 0.75
        and len(calls[0][1]) == 2
        and len(calls[1][1]) == len(asked) == 4
        and "0:01.0-0:02.5  Hello." in calls[0][0]
        and "- twice" in calls[0][0]
        and "around 1:20.4 -- you asked" in calls[1][0]
        and [x["what"] for x in r["findings"]]
        == ["a hand hangs", "the wall, seen closer", "the plant"],
        (r, asked),
    )
    calls.clear()

    async def nothing(text, images):
        calls.append(1)
        return {"findings": [], "look_closer": []}, 0.1

    r = asyncio.run(
        review.read({"mat": mat, "sheets": sheets, "events": [], "strips": strips}, nothing)
    )
    expect(
        "reader: a film with nothing to look closer at is read once",
        r["calls"] == 1 and len(calls) == 1 and r["findings"] == [],
    )
    expect(
        "reader: its list of kinds is the one its brief names",
        all("- %s:" % k in review.system() for k in review.KINDS),
    )
    w = review.words(first, must_only=True)
    expect(
        "reader: findings as lines for the author, the musts only when asked",
        w.count("\n") == 1 and "0:51.0 to 1:02.0 (idle): a hand hangs" in w,
        w,
    )

    # ---- the fix, judged: what is kept of the film before it, and what changed besides
    class Stub:  # a film's folder, as review.snapshot and review.restore use one
        def __init__(self, d):
            self.dir = d

        def path(self, *parts):
            return os.path.join(self.dir, *parts)

    fd = os.path.join(HOME, "fixed-film")
    os.makedirs(os.path.join(fd, "cast"))
    for name, text in (
        ("film.js", "v1"),
        ("vo.json", "{}"),
        ("sfx.json", "[]"),
        ("cast/cat.js", "c1"),
    ):
        with open(os.path.join(fd, *name.split("/")), "w", encoding="utf-8") as f:
            f.write(text)
    stub = Stub(fd)
    before = review.snapshot(stub)
    for name, text in (
        ("film.js", "v2"),
        ("vo.json", '{"moved": 1}'),
        ("cast/cat.js", "c2"),
        ("cast/dog.js", "d"),
    ):
        with open(os.path.join(fd, *name.split("/")), "w", encoding="utf-8") as f:
            f.write(text)
    review.restore(stub, before, only=("vo.json",))
    read = lambda n: open(os.path.join(fd, *n.split("/")), encoding="utf-8").read()  # noqa: E731, SIM115
    expect(
        "fix: the narration's words are put back on their own; the picture's change stays",
        read("vo.json") == "{}" and read("film.js") == "v2" and review._dirs_differ(stub, before),
    )
    review.restore(stub, before)
    expect(
        "fix: a fix that broke something is thrown away whole, a new cast file with it",
        read("film.js") == "v1"
        and read("cast/cat.js") == "c1"
        and not os.path.exists(os.path.join(fd, "cast", "dog.js"))
        and not review._dirs_differ(stub, before),
    )
    a_dir, b_dir = os.path.join(HOME, "was"), os.path.join(HOME, "now")
    os.makedirs(a_dir)
    os.makedirs(b_dir)
    for t in range(12):
        for d2, moved in ((a_dir, False), (b_dir, t in (4, 9))):  # the fix at 4 s also changed 9 s
            im = Image.new("RGB", (480, 270), "#f7f2e7")
            ImageDraw.Draw(im).rectangle(
                (40, 60, 240, 220) if not moved else (240, 60, 440, 220), fill="#c2592a"
            )
            im.save(os.path.join(d2, "%06.2f.png" % t))
    moved = review.changed_frames(a_dir, b_dir, [(3.5, 4.5)])
    expect(
        "fix: a frame that changed away from every finding is found; one beside a finding is expected to",
        [t for t, _, _ in moved] == [9.0],
        [t for t, _, _ in moved],
    )
    sheet = review.pairs_sheet(moved, os.path.join(HOME, "fix-check.jpg"))
    expect("fix: ... and shown as it was beside as it is", os.path.getsize(sheet) > 5000)

    print("\n%s" % ("ALL OK" if not bad else "FAILED: " + ", ".join(bad)))
    sys.exit(1 if bad else 0)


def _darkest(p):
    from PIL import Image  # noqa: PLC0415

    with Image.open(p) as im:
        return im.convert("L").getextrema()[0]


def _spoken(obj):
    p = os.path.join(HOME, "tl.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f)
    return motion.spoken(p)


# a cast member with a body and a box, and a film that does each thing the probe reads
CAST = """
SK.cast.blob = {
  about: 'a test blob and its box',
  body(o = {}) { SK.wash(SK.S.ellC(0, -60, 70, 60), '#c2592a', {}); SK.ink(SK.S.ell(0, -60, 70, 60), { w: 5 }); },
  box(x, y, o = {}) {
    SK.at(x, y, 0, 1, () => {
      const c = SK.ctx();
      SK.wash(SK.S.rrect(-90, -160, 180, 160, 6), '#8a8f98', {});
      if (o.inside) { c.save(); SK.rrPath(-60, -120, 120, 110, 8); c.clip(); try { o.inside(); } finally { c.restore(); } }
      SK.ink(SK.S.rrect(-90, -160, 180, 160, 6), { w: 5 });
    });
  },
};
"""
FILM = """
(function () {
  const { clamp } = SK, B = SK.cast.blob;
  SK.setStyle('clean');
  SK.film({
    duration: 6,
    camera: SK.camera([[0, [0, 0, 1]], [6, [0, 0, 1]]]),
    draw(t) {
      const flat = t > 1 && t < 1.6 ? Math.abs(1 - (t - 1) / .3) : 1;         // turned round by scaling through flat
      const x = -500 + 150 * Math.min(t, 4);                                    // she walks to the box by 4 s
      B.box(100, 200, { inside: t >= 4 ? () => SK.at(-40, 0, 0, 1.6, () => B.body()) : undefined }); // too big for it
      if (t < 4) SK.at(x, 200, 0, [Math.max(.02, flat), 1], () => B.body());
      if (t > 2) { const c = SK.ctx(), v = SK.view; c.save(); c.globalCompositeOperation = 'multiply'; c.globalAlpha = .4 * clamp((t - 2) / 1.5); c.fillStyle = '#f2a66e'; c.fillRect(v.x0, v.y0, v.x1 - v.x0, v.y1 - v.y0); c.restore(); }
    },
  });
})();
"""

if __name__ == "__main__":
    main()
