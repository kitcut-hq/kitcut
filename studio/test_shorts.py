#!/usr/bin/env python
"""A film from an idea in a frame of its own, with the narration's words in the picture: what a
YouTube Short needs (film.FRAMES, film.CAPS "captions", sketch/captions.js). No model, no
network, no browser; node runs the caption module against a stub when it is installed. Seconds.

    python studio/test_shorts.py

Covers: a film asked for in 9:16 with captions gets the frame in its manifest, the module in its
engine folder and both in its record; a film asked for as ever is byte for byte the film it was
(no frame, no module, no note); the first message names the frame and the caption band; the band
film.py tells the writer about is the one captions.js draws in, for every frame; and the cards it
cuts a narration into never hold more words than the frame allows, never leave a last word alone,
and never overlap in time.
"""

import os
import sys
import json
import shutil
import subprocess
import tempfile

HOME = tempfile.mkdtemp(prefix="studio-shorts-test-")
os.environ["STUDIO_HOME"] = HOME
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "scripts"))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import
import agent  # noqa: E402
import film as films  # noqa: E402

FAILED = []


def expect(what, ok, got=None):
    print("  %s %s%s" % ("ok  " if ok else "FAIL", what, "" if ok else " -- got %r" % (got,)))
    if not ok:
        FAILED.append(what)


# what the bundler injects as SK.VO: two lines, word times a quarter of a second apart
LINES = [
    "This week, a model wrote seven hundred and twenty-two mathematics papers.",
    "Nobody asked it to. Mathematicians are still reading them, one by one, and arguing.",
]


def timeline():
    t, lines = 0.5, []
    for text in LINES:
        words = []
        for w in text.split():
            words.append({"text": w, "s": round(t, 3), "e": round(t + 0.2, 3)})
            t += 0.25
        lines.append({"start": words[0]["s"], "end": words[-1]["e"], "words": words})
        t += 0.8
    return {"lines": lines}


STUB = """
const SK = { W: %d, H: %d, clamp: (v) => Math.max(0, Math.min(1, v)), VO: %s, film() { SK._film = {}; } };
globalThis.window = { SK };
require(%s);
console.log(JSON.stringify({ box: SK.captionBox(), cards: SK.captionCards() }));
"""


def module(w, h):
    """sketch/captions.js run by node against a stub of the engine: its band and its cards."""
    src = os.path.join(_env.ROOT, "sketch", "captions.js")
    code = STUB % (w, h, json.dumps(timeline()), json.dumps(src))
    out = subprocess.run(["node", "-e", code], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def main():
    _env.utf8_stdio()
    print("a film asked for as a Short")
    short = films.Film.create(
        "the week in AI", 30, "collage", client="t", frame="9:16", captions=True
    )
    with open(short.manifest, encoding="utf-8") as f:
        m = json.load(f)
    rec = short.record()
    expect("its manifest is 1080x1920", m.get("frame") == [1080, 1920], m.get("frame"))
    expect(
        "and loads the captions module", "captions" in (m.get("modules") or []), m.get("modules")
    )
    expect("which is in its engine folder", os.path.exists(short.path("engine", "captions.js")))
    expect(
        "its record says so",
        rec.get("frame") == "9:16" and "captions" in rec.get("caps"),
        (rec.get("frame"), rec.get("caps")),
    )
    first = agent.first_record(short, "web", "t")
    expect(
        "and so does the run the site reads",
        first.get("frame") == "9:16" and first.get("captions") == "burned",
        (first.get("frame"), first.get("captions")),
    )
    note = films.frame_note(short)
    x0, y0, x1, y1 = films.caption_band(1080, 1920)
    expect("the first message names the frame", "1080x1920" in note and "vertical" in note)
    expect(
        "and the band the captions take, in world units",
        "x %d to %d, y %d to %d" % (x0 - 540, x1 - 540, y0 - 960, y1 - 960) in note,
        note[-400:],
    )
    expect(
        "the band is clear of what a phone covers", y1 < 1920 * (1 - 0.2) and x1 < 1080, (y1, x1)
    )
    expect("and the whole of it is in the first message", note in agent.ask(short))

    print("a film asked for as ever")
    wide = films.Film.create("the week in AI", 30, "collage", client="t")
    with open(wide.manifest, encoding="utf-8") as f:
        m = json.load(f)
    expect("has no frame in its manifest", "frame" not in m, m.get("frame"))
    expect("no captions module", "captions" not in (m.get("modules") or []), m.get("modules"))
    expect("no frame in its record", "frame" not in wide.record(), wide.record().get("frame"))
    expect("and no note", films.frame_note(wide) == "")
    odd = films.Film.create("the week in AI", 30, "drawn", client="t", frame="4:3")
    expect("a frame the studio does not make is 16:9", "frame" not in odd.record())
    expect(
        "the look's prompt is the same with captions as without",
        agent.system_prompt("collage", short.caps) == agent.system_prompt("collage", wide.caps),
    )

    print("the caption module")
    if not shutil.which("node"):
        print("  skipped: node is not installed")
    for name, (w, h) in films.FRAMES.items() if shutil.which("node") else ():
        got = module(w, h)
        expect(
            "%s: the band film.py names is the one it draws in" % name,
            tuple(got["box"]) == films.caption_band(w, h),
            (got["box"], films.caption_band(w, h)),
        )
        cards = got["cards"]
        most = {"9:16": 4, "1:1": 5, "16:9": 8}[name]
        said = " ".join(c["text"] for c in cards)
        expect("%s: every word is on a card, in order" % name, said == " ".join(LINES), said)
        expect(
            "%s: no card holds more than %d words (one more to keep a last word company)"
            % (name, most),
            all(len(c["text"].split()) <= most + 1 for c in cards),
            [c["text"] for c in cards],
        )
        expect(
            "%s: no cards overlap" % name,
            all(a["e"] <= b["s"] + 1e-9 for a, b in zip(cards, cards[1:], strict=False)),
            [(c["s"], c["e"]) for c in cards],
        )
        expect(
            "%s: a sentence ends its card" % name,
            all(c["text"].endswith(".") for c in cards if "." in c["text"]),
            [c["text"] for c in cards],
        )
    shutil.rmtree(HOME, ignore_errors=True)
    print("\n%s" % ("FAILED: %s" % "; ".join(FAILED) if FAILED else "all passed"))
    sys.exit(1 if FAILED else 0)


if __name__ == "__main__":
    main()
