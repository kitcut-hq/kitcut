#!/usr/bin/env python
"""Burn a film's captions into a copy of its video: the card a player draws live, in the pixels.

A Sketch Studio film is rendered without its captions; they sit beside the video as
captions.json (sketch-render's "captions" stage: the cards, their word times, their look, and
the faces they name, as captions_font<N> files next to it). A player draws them live over the
video (sketch/captions-layer.js). This makes the copy that leaves KitCut with them in it -- a
download, a YouTube upload, the copy a chat app plays in a link preview -- drawn by the same
file, in headless Edge/Chrome, so the burned card is the live one.

Each different picture of the captions is drawn once (a card, the word being said; a card's
first tenth of a second moves, so those frames are drawn each), sent back as a PNG, and every
frame of the video is given the one it shows (hard links: a frame with no card is one blank
picture). ffmpeg lays them over the video and re-encodes it; the sound is copied as it is.

Invoke as:
    python scripts/captions-burn.py --video projects/<id>/outputs/film.mp4 \\
        --captions projects/<id>/outputs/captions.json --out temp/film_captioned.mp4 --plan
    python scripts/captions-burn.py --video projects/<id>/outputs/film.mp4 \\
        --captions projects/<id>/outputs/captions.json --out temp/film_captioned.mp4
    python scripts/captions-burn.py ... --style '{"preset": "plain"}'   # the look a person chose
    python scripts/captions-burn.py ... --encode '{"cq": 26, "maxrate": "5M", "bufsize": "10M"}'

--style is what the film's page saved ({preset, card, ink, said, font}); --encode the encoder's
settings (`_encode.resolve`; the master's by default). Prints the copy's path. --plan says what
it would draw and encode (the video's size and frames, the cards), and draws nothing.
"""

import os
import sys
import json
import time
import base64
import shutil
import argparse
import tempfile
import subprocess
from importlib import import_module

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import
import _encode  # noqa: E402

LAYER = os.path.join(_env.ROOT, "sketch", "captions-layer.js")
MASTER = {"cq": 18, "preset": "p5", "audio_bitrate": "320k"}  # sketch-render's own render block

PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>%(faces)s
html,body{margin:0;background:transparent}</style></head><body><canvas id="c"></canvas>
<script>%(layer)s</script>
<script>
(async function () {
  const post = async (path, body) => {
    for (let k = 0; ; k++) {
      try { const r = await fetch(path, { method: 'POST', body }); if (r.ok) return; throw new Error('HTTP ' + r.status); }
      catch (e) { if (k >= 6) throw e; await new Promise((res) => setTimeout(res, 150 * 2 ** k)); }
    }
  };
  try {
    const K = window.KCCaptions, data = %(data)s, over = %(over)s, V = %(video)s;
    await Promise.all((data.fonts || []).map((f) => document.fonts.load(`${f.style === 'italic' ? 'italic ' : ''}${String(f.weight).split(' ').pop()} 40px "${f.family}"`)));
    await document.fonts.ready;
    const cv = document.getElementById('c');
    cv.width = V.w; cv.height = V.h;
    const c = cv.getContext('2d'), o = K.style(data, over), rows = data.cards || [];
    const k = V.w / data.frame[0], end = data.duration || Infinity;
    const png = () => new Promise((r) => cv.toBlob(r, 'image/png'));
    const runs = [];
    let last = null;
    for (let i = 0; i < V.n; i++) {
      const t = i / V.fps;
      const key = t < end ? K.key(rows, t) : '';
      if (key === last) continue;
      last = key;
      runs.push([i, key !== '']);
      if (key === '') continue;
      c.setTransform(1, 0, 0, 1, 0, 0);
      c.clearRect(0, 0, cv.width, cv.height);
      K.draw(c, rows, t, o, k, end);
      await post('still?t=' + i, await png());
    }
    await post('report', JSON.stringify({ runs }));
  } catch (e) { await post('error', String(e && e.stack || e)); }
  await post('done', '');
})();
</script></body></html>"""


def probe(video):
    """(width, height, fps, frames) of a video's first picture stream."""
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets"]
        + [
            "-show_entries",
            "stream=width,height,r_frame_rate,nb_read_packets",
            "-of",
            "json",
            video,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    s = json.loads(r.stdout)["streams"][0]
    num, _, den = s["r_frame_rate"].partition("/")
    fps = float(num) / float(den or 1)
    return int(s["width"]), int(s["height"]), fps, int(s["nb_read_packets"])


def page(captions, over, size, fps, n):
    """The burner's page: the layer, the captions' faces inlined, and their data."""
    with open(captions, encoding="utf-8") as f:
        data = json.load(f)
    here = os.path.dirname(os.path.abspath(captions))
    faces = []
    for fnt in data.get("fonts") or []:
        p = os.path.join(here, os.path.basename(str(fnt.get("file") or "")))
        if not os.path.isfile(p):
            continue
        fmt = "woff2" if p.endswith(".woff2") else "truetype"
        with open(p, "rb") as f:
            b = base64.b64encode(f.read()).decode()
        faces.append(
            "@font-face{font-family:'%s';src:url(data:font/%s;base64,%s) format('%s');"
            "font-weight:%s;font-style:%s;font-display:block}"
            % (fnt["family"], fmt, b, fmt, fnt.get("weight", "400"), fnt.get("style", "normal"))
        )
    with open(LAYER, encoding="utf-8") as f:
        layer = f.read()
    return PAGE % {
        "faces": "\n".join(faces),
        "layer": layer,
        "data": json.dumps(data),
        "over": json.dumps(over or None),
        "video": json.dumps({"w": size[0], "h": size[1], "fps": fps, "n": n}),
    }


def burn(video, captions, out, over=None, encode=None):
    """The copy of `video` with its captions in it, written to `out`. Raises on a failure."""
    render = import_module("sketch-render")
    w, h, fps, n = probe(video)
    work = tempfile.mkdtemp(prefix="captions-burn-")
    try:
        stills = os.path.join(work, "drawn")
        os.makedirs(stills)

        def save(i, body):
            with open(os.path.join(stills, "%06d.png" % int(i)), "wb") as f:
                f.write(body)

        sess = render.Session(page(captions, over, (w, h), fps, n), on_still=save, size=(w, h))
        err = sess.run("burn=1", fatal=False)
        if err:
            raise RuntimeError("captions not drawn: %s" % err)
        runs = (sess.report or {}).get("runs") or []
        from PIL import Image

        blank = os.path.join(work, "blank.png")
        Image.new("RGBA", (w, h), (0, 0, 0, 0)).save(blank)
        frames = os.path.join(work, "frames")
        os.makedirs(frames)
        bounds = [r[0] for r in runs] + [n]
        for (start, shown), stop in zip(runs, bounds[1:], strict=False):
            src = os.path.join(stills, "%06d.png" % start) if shown else blank
            for i in range(start, stop):
                dst = os.path.join(frames, "%06d.png" % i)
                try:
                    os.link(src, dst)
                except OSError:
                    shutil.copyfile(src, dst)
        if not runs:  # no card anywhere: the copy is the video as it is
            shutil.copyfile(video, out)
            return out
        cfg = _encode.resolve({**MASTER, **(encode or {})})
        tmp = out + ".%d.tmp.mp4" % os.getpid()
        cmd = (
            ["ffmpeg", "-y", "-v", "error"]
            + _encode.decode_args()
            + ["-i", video, "-framerate", "%r" % fps, "-i", os.path.join(frames, "%06d.png")]
            + ["-filter_complex", "[0:v][1:v]overlay=0:0:eof_action=pass:format=auto[v]"]
            + ["-map", "[v]", "-map", "0:a?", "-c:a", "copy"]
            + _encode.video_args(cfg)
            + ["-movflags", "+faststart", tmp]
        )
        r = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if r.returncode or not os.path.isfile(tmp):
            if os.path.exists(tmp):
                os.remove(tmp)
            raise RuntimeError("captions not burned: %s" % (r.stderr.strip()[-300:] or "ffmpeg"))
        os.replace(tmp, out)
        return out
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main():
    _env.utf8_stdio()
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--video", required=True, help="the film's clean video")
    ap.add_argument("--captions", required=True, help="its captions.json (faces beside it)")
    ap.add_argument("--out", required=True, help="where the copy with captions goes")
    ap.add_argument("--style", help="JSON: the look chosen on the film's page")
    ap.add_argument("--encode", help="JSON: encoder settings over the master's")
    ap.add_argument("--plan", action="store_true", help="say what it would do; draw nothing")
    args = ap.parse_args()
    if args.plan:
        w, h, fps, n = probe(args.video)
        with open(args.captions, encoding="utf-8") as f:
            data = json.load(f)
        cfg = _encode.resolve({**MASTER, **(json.loads(args.encode) if args.encode else {})})
        print("  video:   %dx%d, %d frames at %g fps" % (w, h, n, fps))
        print("  cards:   %d, in a %dx%d frame" % (len(data.get("cards") or []), *data["frame"]))
        print("  encoder: %s" % _encode.describe(cfg))
        print("\n  --plan: nothing drawn")
        return
    t = time.time()
    out = burn(
        args.video,
        args.captions,
        args.out,
        json.loads(args.style) if args.style else None,
        json.loads(args.encode) if args.encode else None,
    )
    print(out)
    print("  %.1f s" % (time.time() - t), file=sys.stderr)


if __name__ == "__main__":
    main()
