#!/usr/bin/env python
"""A film's captions as data: rendered clean, written beside the video, burned into a copy only
when one leaves KitCut (film.CAPS "captions", sketch/captions-layer.js, scripts/captions-burn.py,
studio/captions.py, youtube.py). No model, no network. With a browser, a small film is rendered
and burned for real (about a minute); without one those cases are skipped.

    python studio/test_captions.py

Covers: every film from an idea has the captions, live, whatever its frame, and a template's
film too when it has narration; a look picked on the film's page is checked before it reaches a
command line; a version with no captions.json has nothing to burn; a copy is asked for once and
answered the same afterwards, a new look is another copy, and an old one is pruned after its days;
a YouTube send asked for with captions sends the copy with them, and one asked without the film;
and, rendered: the video has no card in it, captions.json holds the cards the stills drew, and the
burned copy's card is the one the stills drew (the band's pixels within a few levels of the
still's, against a clean frame's that are not).
"""

import os
import sys
import json
import time
import asyncio
import shutil
import tempfile
import subprocess

HOME = tempfile.mkdtemp(prefix="studio-captions-test-")
os.environ["STUDIO_HOME"] = HOME
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "scripts"))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import
import captions  # noqa: E402
import film as films  # noqa: E402
import youtube  # noqa: E402

FAILED = []


def expect(what, ok, got=None):
    print("  %s %s%s" % ("ok  " if ok else "FAIL", what, "" if ok else " -- got %r" % (got,)))
    if not ok:
        FAILED.append(what)


WORDS = "This is a test of live captions. They are drawn over the video, not in it."
FILM_JS = """
SK.film({ duration: 5, scenes: [{ from: 0, to: 5, draw(t) {} }] });
"""


def small_film(frame="9:16"):
    f = films.Film.create("a test", 5, "drawn", client="t", frame=frame, captions=True)
    with open(f.path("film.js"), "w", encoding="utf-8") as fh:
        fh.write(FILM_JS)
    os.makedirs(f.path("audio", "vo"), exist_ok=True)
    t, words = 0.3, []
    for w in WORDS.split():
        words.append({"text": w, "s": round(t, 2), "e": round(t + 0.22, 2)})
        t += 0.3
    line = {"start": words[0]["s"], "end": words[-1]["e"], "words": words}
    with open(f.path("audio", "vo", "timeline.json"), "w", encoding="utf-8") as fh:
        json.dump({"lines": [line]}, fh)
    return f


def fake_version(f, cards=1):
    """outputs/ as a render leaves it, without a render: a video, a web copy, captions.json."""
    out = f.path("outputs")
    os.makedirs(out, exist_ok=True)
    for n in ("film.mp4", "film_web.mp4"):
        with open(os.path.join(out, n), "wb") as fh:
            fh.write(b"video")
    data = {"v": 1, "frame": [1080, 1920], "cards": [{"s": 0, "e": 1, "words": []}] * cards}
    with open(os.path.join(out, "captions.json"), "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    return out


def cases_made():
    print("every film has them")
    for frame in ("16:9", "1:1", "9:16"):
        f = films.Film.create("an idea", 30, "drawn", client="t", frame=frame)
        rec = f.record()
        expect(
            "%s: live captions, starting hidden when nobody asked otherwise" % frame,
            rec.get("captions") == "live"
            and "captions" in rec["caps"]
            and rec.get("captions_on") is False,
            (rec.get("captions"), rec.get("captions_on")),
        )
    on = films.Film.create("an idea", 30, "drawn", client="t", captions=True).record()
    expect("asked for shown, it starts shown", on.get("captions_on") is True)


def cases_style():
    print("a look picked on the film's page")
    expect("none is the film's own", captions.clean_style(None) is None)
    got = captions.clean_style(
        {"preset": "plain", "card": "#192859", "said": "rgba(218,163,60,.9)", "font": "Outfit"}
    )
    expect(
        "a preset, colours and a face pass",
        got
        == {"preset": "plain", "card": "#192859", "said": "rgba(218,163,60,.9)", "font": "Outfit"},
        got,
    )
    bad = captions.clean_style(
        {"preset": "rm -rf", "ink": "red; x", "card": "url(x)", "font": 'a";b', "x": 1}
    )
    expect("anything else is dropped", bad is None, bad)


async def cases_copies():
    print("copies with captions")
    bare = films.Film.create("an idea", 30, "drawn", client="t")
    os.makedirs(bare.path("outputs"), exist_ok=True)
    expect(
        "a version with no captions.json has none",
        captions.want(bare, "download") == {"state": "none"},
    )
    f = films.Film.create("an idea", 30, "drawn", client="t")
    out = fake_version(f)
    made = []

    def burn(o, kind, style, path):
        made.append((kind, style))
        with open(path, "wb") as fh:
            fh.write(b"burned")

    real, captions.burn = captions.burn, burn
    try:
        first = captions.want(f, "download")
        expect("asked for, it is being made", first["state"] == "preparing", first)
        await asyncio.sleep(0.05)
        again = captions.want(f, "download")
        expect(
            "then it is there, under outputs/captioned/",
            again["state"] == "ready" and again["path"].startswith(os.path.join(out, "captioned")),
            again,
        )
        captions.want(f, "download")
        expect("and asked for again it is not made again", len(made) == 1, made)
        other = captions.want(f, "download", {"preset": "plain"})
        await asyncio.sleep(0.05)
        expect(
            "another look is another copy",
            other["name"] != first["name"] and made[-1] == ("download", {"preset": "plain"}),
            (other, made),
        )
        path = await captions.burned(f, "youtube")
        expect("a send waits for its copy", os.path.isfile(path))
        old = time.time() - (captions.CAPTIONED_DAYS + 1) * 86400
        os.utime(path, (old, old))
        captions.prune(f)
        expect("a copy not asked for in its days is deleted", not os.path.exists(path))
    finally:
        captions.burn = real

    print("YouTube")
    sent = []

    async def send(job, path, to):
        sent.append(path)
        return {"id": "v1"}

    async def burned(film, kind, style=None, version=None):
        return os.path.join(out, "captioned", "film-x.mp4")

    real_send, real_burned = youtube._send, youtube.captioned.burned
    youtube._send, youtube.captioned.burned = send, burned
    with open(os.path.join(out, "captioned", "film-x.mp4"), "wb") as fh:
        fh.write(b"burned!")
    try:
        to = "https://www.googleapis.com/upload/youtube/v3/videos?upload_id=abc"
        await youtube.start(f, "t", to, "post-with-captions", captions={"on": True})["task"]
        await youtube.start(f, "t", to, "post-without-cc", captions={"on": False})["task"]
        expect(
            "with captions the copy goes up, without them the film",
            sent == [os.path.join(out, "captioned", "film-x.mp4"), f.path("outputs", "film.mp4")],
            sent,
        )
        expect(
            "and the send says which it was",
            youtube.public(youtube.get("post-with-captions")).get("captions") is True
            and "captions" not in youtube.public(youtube.get("post-without-cc")),
        )
    finally:
        youtube._send, youtube.captioned.burned = real_send, real_burned


def render(f, *args):
    cmd = _env.PY + [
        os.path.join(_env.ROOT, "scripts", "sketch-render.py"),
        "--manifest",
        f.manifest,
    ]
    r = subprocess.run(cmd + list(args), capture_output=True, text=True, timeout=900, check=False)
    if r.returncode:
        print(r.stdout[-800:], r.stderr[-800:])
    return r.returncode == 0


def band_diff(a, b, box):
    from PIL import Image, ImageChops

    d = ImageChops.difference(
        Image.open(a).convert("RGB").crop(box), Image.open(b).convert("RGB").crop(box)
    )
    hist = d.convert("L").histogram()
    return sum(i * n for i, n in enumerate(hist)) / max(1, sum(hist))


def frame_at(video, t, png):
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-ss", str(t), "-i", video, "-frames:v", "1", png],
        check=True,
    )
    return png


async def cases_rendered():
    print("rendered")
    sys.path.insert(0, os.path.join(_env.ROOT, "scripts"))
    h2i = __import__("importlib").import_module("html-to-image")
    if not h2i.find_browsers():
        print("  skipped: no browser")
        return
    f = small_film()
    expect("a small tall film renders", render(f, "--jobs", "2"))
    out = f.path("outputs")
    p = os.path.join(out, "captions.json")
    expect("with captions.json beside its video", os.path.isfile(p))
    if not os.path.isfile(p):
        return
    with open(p, encoding="utf-8") as fh:
        data = json.load(fh)
    said = " ".join(w["text"] for c in data["cards"] for w in c["words"])
    expect("holding every word, in order", said == WORDS, said)
    expect(
        "and the face its card is set in, beside it",
        any(
            x["family"] == "Inter" and os.path.isfile(os.path.join(out, x["file"]))
            for x in data["fonts"]
        ),
        data.get("fonts"),
    )
    t = 1.0
    expect("a still draws the card", render(f, "--stills", "%g" % t, "--into", "temp/st"))
    still = f.path("temp", "st", "%06.2f.png" % t)
    clean = frame_at(f.path("outputs", "film.mp4"), t, f.path("temp", "clean.png"))
    x0, y0, x1, y1 = films.caption_band(1080, 1920)
    box = (x0, y0, x1, y1)
    expect(
        "the video has no card in it",
        band_diff(clean, still, box) > 20,
        band_diff(clean, still, box),
    )
    got = captions.want(f, "download")
    path = await captions.burned(f, "download")
    expect(
        "a copy with captions is burned",
        got["state"] in ("preparing", "ready") and os.path.isfile(path),
    )
    burned = frame_at(path, t, f.path("temp", "burned.png"))
    diff = band_diff(burned, still, box)
    expect("whose card is the one the stills draw", diff < 8, diff)


async def main():
    _env.utf8_stdio()
    cases_made()
    cases_style()
    await cases_copies()
    await cases_rendered()
    shutil.rmtree(HOME, ignore_errors=True)
    print("\n%s" % ("FAILED: %s" % "; ".join(FAILED) if FAILED else "all passed"))
    sys.exit(1 if FAILED else 0)


if __name__ == "__main__":
    asyncio.run(main())
