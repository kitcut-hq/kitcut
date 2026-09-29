#!/usr/bin/env python
"""A film's four YouTube thumbnail options (thumbs.py, scripts/_thumb.py), made for real: the
repo's example sketch film, drawn by headless Edge/Chrome, in a throwaway STUDIO_HOME. No model
and no network. About half a minute, most of it the browser.

    python studio/test_thumbs.py

Covers: the moments a draft picks from (inside the film, spread, apart) and their sheet; the stills
are the film's own frames without anything added after it (a Free plan's closing mark -- stood in
for here by a tail that paints the whole frame red, which the film's own render shows and no still
may); four options made from a draft's concepts, each a 1920x1080 JPEG under YouTube's 2 MB, each
passing every check (legible at 168 px, in contrast, clear of the duration stamp, hiding none of
the film's own words); words that cannot be set legibly fall back rather than ship; the options
are kept, keyed by the draft, and told to the site without anything of the studio's.
"""

import os
import sys
import json
import asyncio
import shutil
import tempfile

HOME = tempfile.mkdtemp(prefix="studio-thumbs-test-")
os.environ["STUDIO_HOME"] = HOME
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "scripts"))
import thumbs  # noqa: E402 -- imports _thumb, which imports _env first
import _thumb  # noqa: E402
import _env  # noqa: E402
from film import Film  # noqa: E402

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

EXAMPLE = os.path.join(_env.ROOT, "config", "sketch", "example")
RED_TAIL = """(function () {
  const F = SK._film; if (!F) return;
  const own = F.overlay;
  F.overlay = (t) => {
    if (own) own(t);
    const c = SK.ctx(); c.save(); c.setTransform(1, 0, 0, 1, 0, 0);
    c.fillStyle = '#ff0000'; c.fillRect(0, 0, SK.W, SK.H); c.restore();
  };
})();
"""
LINES = [
    (0.6, 4.2, "An invite you never used is just sitting there, waiting."),
    (4.6, 7.0, "So send it to a friend."),
    (7.4, 9.0, "Pass it on."),
]


def fixture_film():
    """The example film as a studio film: its code, its manifest with a red tail, a voice
    timeline, a record."""
    d = os.path.join(HOME, "projects", "studio-20260929-120000-thumbs")
    os.makedirs(os.path.join(d, "audio", "vo"), exist_ok=True)
    os.makedirs(os.path.join(d, "temp", "brand"), exist_ok=True)
    shutil.copyfile(os.path.join(EXAMPLE, "film.js"), os.path.join(d, "film.js"))
    with open(os.path.join(EXAMPLE, "sketch.json"), encoding="utf-8") as f:
        m = json.load(f)
    m["slug"] = "film"
    m["tail"] = {"secs": 0, "scripts": ["temp/brand/red.js"]}
    # a font the film fetched for itself (the page tool keeps them in the film's web/fonts): its
    # path is the film's, not the tooling's -- the first real publish failed on exactly this
    os.makedirs(os.path.join(d, "web", "fonts"), exist_ok=True)
    shutil.copyfile(
        os.path.join(_env.ROOT, "fonts", "Montserrat-Bold.ttf"),
        os.path.join(d, "web", "fonts", "Own-700.ttf"),
    )
    m["fonts"] = [
        *m.get("fonts", []),
        {"file": "web/fonts/Own-700.ttf", "family": "Own", "weight": "700"},
    ]
    with open(os.path.join(d, "sketch.json"), "w", encoding="utf-8") as f:
        json.dump(m, f, indent=1)
    with open(os.path.join(d, "temp", "brand", "red.js"), "w", encoding="utf-8") as f:
        f.write(RED_TAIL)
    tl = {
        "duration": m["duration"],
        "lines": [
            {"i": i, "start": s, "end": e, "text": t, "words": []}
            for i, (s, e, t) in enumerate(LINES)
        ],
    }
    with open(os.path.join(d, "audio", "vo", "timeline.json"), "w", encoding="utf-8") as f:
        json.dump(tl, f)
    with open(os.path.join(d, "studio.json"), "w", encoding="utf-8") as f:
        json.dump(
            {"ok": True, "state": "done", "look": "drawn", "direction": {"style": "crayon"}}, f
        )
    return Film(d)


def red(img):
    a = np.asarray(img.convert("RGB").resize((64, 36)), dtype="float32")
    return float(((a[..., 0] > 200) & (a[..., 1] < 60) & (a[..., 2] < 60)).mean())


def main():
    bad = []

    def check(ok, what, detail=""):
        print("%s  %s%s" % ("ok  " if ok else "FAIL", what, "" if ok else "  -- %s" % (detail,)))
        if not ok:
            bad.append(what)

    f = fixture_film()
    L = thumbs.length(f)

    # ---------------------------------------------------------------- the moments
    ms = thumbs.moments(f)
    check(6 <= len(ms) <= 12, "between six and twelve moments", ms)
    check(all(0.5 <= t <= L - 0.5 for t in ms), "all inside the film, clear of its fades", ms)
    check(all(b - a >= 1.0 for a, b in zip(ms, ms[1:])), "at least a second apart", ms)
    check(any(abs(t - (4.2 - 0.35)) < 0.01 for t in ms), "one just before a line ends", ms)
    sheet = thumbs.sheet_now(f)
    im = Image.open(__import__("io").BytesIO(sheet))
    check(im.format == "JPEG" and im.width == 1920, "the sheet is one JPEG, four across", im.size)
    # a finished film's premake and a draft asking at the same moment make it once, not twice
    os.remove(thumbs.sheet_path(f))
    made, real = [], _thumb.moments_sheet

    def counted(stills, out, **kw):
        made.append(out)
        return real(stills, out, **kw)

    _thumb.moments_sheet = counted

    async def both():
        return await asyncio.gather(thumbs.premake(f), thumbs.sheet(f))

    got = asyncio.run(both())
    _thumb.moments_sheet = real
    check(got[0] == got[1] == sheet and len(made) == 1, "two asks at once: made once", len(made))
    check(os.path.exists(thumbs.sheet_path(f)), "and kept for the next draft")

    # ---------------------------------------------------------------- the film's own frames
    man = _thumb.clean_manifest(f.dir, os.path.join(HOME, "copy"))
    with open(man, encoding="utf-8") as fh:
        m = json.load(fh)
    check("tail" not in m, "the copy draws no tail", m.get("tail"))
    check(
        os.path.isabs(m["film"]) and os.path.isabs(m["audio"]["vo_timeline"]),
        "and every path is absolute",
    )
    own = [x["file"] for x in m["fonts"] if x["family"] == "Own"]
    check(own and os.path.isabs(own[0]), "the film's own font too, where the film keeps it", own)
    # the control: the same copy with the tail put back, as the film's final render draws it
    ctl = dict(m, tail={"secs": 0, "scripts": [f.path("temp", "brand", "red.js")]})
    os.makedirs(os.path.join(HOME, "control"), exist_ok=True)
    ctl_man = os.path.join(HOME, "control", "sketch.json")
    with open(ctl_man, "w", encoding="utf-8") as fh:
        json.dump(ctl, fh)
    raw = os.path.join(HOME, "raw")
    r = __import__("subprocess").run(
        _env.PY
        + [
            os.path.join(_env.ROOT, "scripts", "sketch-render.py"),
            "--manifest",
            ctl_man,
            "--stills",
            "3.00",
            "--into",
            raw,
        ],  # fmt: skip
        env=_env.ENV,
        capture_output=True,
        text=True,
        timeout=300,
    )
    shot = os.path.join(raw, "003.00.png")
    check(
        os.path.exists(shot) and red(Image.open(shot)) > 0.9,
        "the film's own render shows its tail",
        r.stderr[-300:],
    )
    stills = _thumb.render_stills(f.dir, [3.0])
    check(
        red(Image.open(stills[3.0])) < 0.05,
        "a thumbnail's still never does",
        red(Image.open(stills[3.0])),
    )
    check(
        not os.path.exists(f.path("outputs", "thumbs.html")),
        "and nothing lands in the film's outputs",
    )

    # ---------------------------------------------------------------- four options
    draft = {
        "key": "draft-1",
        "title": "Pass It On: the invite you never used",
        "thumbnails": [
            {"at": 3.6, "layout": "headline", "words": "Still *waiting*?", "place": "top"},
            {
                "at": 6.6,
                "layout": "slab",
                "words": "Send it on",
                "place": None,
            },  # an old draft's name
            {"at": 8.6, "layout": "panel", "words": "A friend can *use* it", "place": None},
            {"at": 11.0, "layout": "still", "words": ""},
        ],
    }
    rec = thumbs.make_now(f, "UCtest", draft)
    opts = rec["options"]
    with open(_thumb.style_path(f.dir), encoding="utf-8") as fh:
        look = json.load(fh)
    heads = [x["font"] for x in sorted(look.get("txt") or [], key=lambda x: -x["max"])]
    check(
        heads[:1] == ["Caveat"] and look["style"]["boil"],
        "the probe read the film's own look: hand-drawn, in Caveat",
        heads,
    )
    check(
        [o["layout"] for o in opts] == ["headline", "card", "panel", "still"],
        "each in its layout (an old draft's slab is a card)",
        [(o["layout"], o["notes"]) for o in opts],
    )
    check([o["n"] for o in opts] == [1, 2, 3, 4], "four options", [o["n"] for o in opts])
    for o in opts:
        p = f.path("outputs", o["path"])
        ok = os.path.exists(p)
        size = os.path.getsize(p) if ok else 0
        img = Image.open(p) if ok else None
        check(ok and img.format == "JPEG" and img.size == (1920, 1080) and size < 2_000_000,
              "option %d: a 1920x1080 JPEG under 2 MB (%d KB)" % (o["n"], size // 1024))  # fmt: skip
        ck = o["checks"]
        if o["layout"] != "still":
            check(
                ck.get("cap_168", 0) >= 8
                and ck.get("contrast", 0) >= 4.5
                and ck.get("in_badge") == 0
                and ck.get("hides_text") == 0,
                "option %d (%s): legible, in contrast, clear of the stamp and the film's words"
                % (o["n"], o["layout"]),
                ck,
            )
        check(red(img) < 0.05, "option %d carries no tail" % o["n"])
    check(
        opts[0]["words"] == "Still waiting?",
        "the words as the site shows them, stars gone",
        opts[0]["words"],
    )

    # ---------------------------------------------------------------- kept, keyed, told
    check(thumbs.saved(f, "UCtest", "draft-1") is not None, "kept for its draft")
    check(thumbs.saved(f, "UCtest", "draft-2") is None, "and not for another")
    pub = thumbs.public(rec)
    check(
        pub["state"] == "done"
        and pub["v"] == "draft-1"
        and set(pub["options"][0]) == {"n", "path", "layout", "words", "at", "t"},
        "the site is told the options, not their checks or notes",
        pub,
    )
    check(thumbs.public({"state": "making"}) == {"state": "making"}, "or that they are being made")
    check(thumbs.public(None) == {"state": "none"}, "or that there are none")

    # ---------------------------------------------------------------- words that cannot be set
    draft2 = dict(draft, key="draft-2")
    draft2["thumbnails"] = [dict(draft["thumbnails"][0], words="Pneumonoultramicroscopicsilicovolcanoconiosis")] + draft["thumbnails"][1:]  # fmt: skip
    rec2 = thumbs.make_now(f, "UCtest", draft2)
    o = rec2["options"][0]
    check(
        o["layout"] != "headline" and o["notes"],
        "a word too long to read at feed size falls back",
        o,
    )

    shutil.rmtree(HOME, ignore_errors=True)
    print("\n%d failed" % len(bad) if bad else "\nall passed")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
