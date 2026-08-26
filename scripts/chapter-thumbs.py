#!/usr/bin/env python
"""Show the thumbnail YouTube will use for each chapter, and find dull ones.

Per-chapter thumbnails cannot be uploaded. YouTube samples them from the video
itself at the chapter's start time -- the storyboard sprite sheet it also uses
for hover-scrubbing. So the only way to change a chapter thumbnail is to move
the mark to a timestamp that looks different.

This downloads that exact storyboard, cuts out the tile each mark lands on, and
writes them as a contact sheet. LOOK AT THE SHEET. The numeric verdicts below
it are a weak instrument and the picture is not.

On the difference scores, measured on this channel's webinar recording:

    two form views seconds apart          0.003   the same frame
    two shots of the same talking head    0.043   genuinely alike
    two DIFFERENT white documents         0.048   distinct content
    a Google results page vs a file list  0.078   clearly distinct
    talking head vs a form on screen      0.341   nothing alike

There is no threshold that separates "alike" from "different" in the 0.04-0.08
band, because a screen recording of paperwork is all pale rectangles of text.
That is not a defect in the measure so much as the actual problem: at the size
YouTube draws a chapter thumbnail, those frames really do read the same. So
only a score under 0.02 is called a duplicate; the middle band is reported as
"reads the same at thumbnail size", which is a claim about legibility, not
about the frames being identical.

For each such mark it proposes an alternative timestamp inside a search window.
Expect that to help only where the video actually cuts to something different
-- on a continuous screen share it will offer another pale rectangle. Nudging
is a judgement call: re-check any proposal against verify-chapters.py, since
moving a mark off its opening sentence to chase a picture is a bad trade.

Invoke as:
  python scripts/chapter-thumbs.py DlQc-IQ5gZY
  python scripts/chapter-thumbs.py DlQc-IQ5gZY --window 12 --out temp/thumbs
"""
import sys, os, re, email, argparse, subprocess, io

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import
import _ytchapters as ch  # noqa: E402


def fetch_storyboard(vid, level, outdir):
    """Download the sprite sheets; returns the .mhtml path."""
    os.makedirs(outdir, exist_ok=True)
    out = os.path.join(outdir, f"sb_{vid}.mhtml")
    if os.path.exists(out) and os.path.getsize(out) > 0:
        return out
    r = subprocess.run(
        _env.PY + ["-m", "yt_dlp", "-f", level,
                   "-o", os.path.join(outdir, f"sb_%(id)s.%(ext)s"), "--", vid],
        env=_env.ENV, capture_output=True, text=True,
        encoding="utf-8", errors="replace")
    if not os.path.exists(out):
        tail = [l for l in (r.stderr or "").splitlines() if l.startswith("ERROR")]
        sys.exit("could not fetch the storyboard: "
                 + (tail[-1] if tail else "unknown error"))
    return out


def _decode(data):
    """One sprite sheet as a PIL image.

    YouTube serves these as WebP, and this Pillow build refuses them --
    it routes every WebP through the animation decoder and raises
    "could not create decoder object" on a plain still. ffmpeg is already a
    hard dependency of this repo, so hand it over rather than fight Pillow.
    """
    from PIL import Image
    try:
        return Image.open(io.BytesIO(data)).convert("RGB")
    except Exception:
        pass
    p = subprocess.run(["ffmpeg", "-v", "error", "-i", "pipe:0",
                        "-f", "image2", "-c:v", "png", "pipe:1"],
                       input=data, capture_output=True)
    if p.returncode != 0 or not p.stdout:
        raise RuntimeError("ffmpeg could not decode a storyboard sheet: "
                           + p.stderr.decode("utf-8", "replace")[:200])
    return Image.open(io.BytesIO(p.stdout)).convert("RGB")


def sheets_from_mhtml(path):
    """The raw sprite-sheet images inside an MHTML container.

    Not parsed as MIME. yt-dlp writes these parts with Content-Transfer-
    Encoding: binary, and Python's email module silently truncates such a
    payload -- the extracted bytes came out shorter than the length in the
    image's own header, which ffmpeg then reported as corrupt data.

    A RIFF container states its own size, so scanning the file for RIFF/WEBP
    signatures and trusting that length sidesteps the container format
    entirely.
    """
    raw = open(path, "rb").read()
    out, i = [], 0
    while True:
        i = raw.find(b"RIFF", i)
        if i < 0:
            return out
        size = int.from_bytes(raw[i + 4:i + 8], "little")
        if raw[i + 8:i + 12] == b"WEBP" and 0 < size < len(raw):
            out.append(raw[i:i + 8 + size])
            i += 8 + size
        else:
            i += 4


def tiles_from_mhtml(path, tile_w, tile_h):
    """Every storyboard tile, in order, as PIL images."""
    sheets = [_decode(b) for b in sheets_from_mhtml(path)]
    if not sheets:
        sys.exit(f"no images inside {path}")
    out = []
    for sheet in sheets:
        cols, rows = sheet.width // tile_w, sheet.height // tile_h
        for r in range(rows):
            for c in range(cols):
                out.append(sheet.crop((c * tile_w, r * tile_h,
                                       (c + 1) * tile_w, (r + 1) * tile_h)))
    return out


def signature(img, size=16):
    """Small grayscale fingerprint, for comparing tiles."""
    import numpy as np
    g = img.convert("L").resize((size, size))
    a = np.asarray(g, dtype="float32")
    return a / 255.0


def distance(a, b):
    import numpy as np
    return float(np.abs(a - b).mean())


def detail(img):
    """How much is going on in the frame -- flat slides score near zero."""
    import numpy as np
    a = signature(img, 32)
    return float(np.abs(np.diff(a, axis=0)).mean()
                 + np.abs(np.diff(a, axis=1)).mean())


def contact_sheet(images, labels, path, cols=4):
    from PIL import Image, ImageDraw
    if not images:
        return
    tw, th = images[0].size
    pad = 18
    rows = (len(images) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * tw, rows * (th + pad)), (16, 16, 16))
    draw = ImageDraw.Draw(sheet)
    for i, (im, lab) in enumerate(zip(images, labels)):
        x, y = (i % cols) * tw, (i // cols) * (th + pad)
        sheet.paste(im, (x, y + pad))
        draw.text((x + 3, y + 4), lab[:44], fill=(235, 235, 235))
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    sheet.save(path)
    return path


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("video", help="video id")
    ap.add_argument("--chapters", help="defaults to config/chapters/<id>.txt")
    ap.add_argument("--level", default="sb0", help="storyboard format")
    ap.add_argument("--tile", default="320x180", help="tile size of --level")
    ap.add_argument("--window", type=int, default=10,
                    help="seconds either side to search for a better frame")
    ap.add_argument("--dup", type=float, default=0.020,
                    help="below this is the same frame (see the docstring "
                         "for the measurements behind this number)")
    ap.add_argument("--alike", type=float, default=0.060,
                    help="below this two tiles read the same at thumbnail size")
    ap.add_argument("--out", default="temp/thumbs")
    args = ap.parse_args()

    vid = args.video
    cpath = args.chapters or os.path.join(_env.ROOT, "config", "chapters",
                                          f"{vid}.txt")
    if not os.path.exists(cpath):
        sys.exit(f"no chapters file at {cpath}")
    marks = ch.parse_marks("".join(
        l for l in open(cpath, encoding="utf-8")
        if not l.strip().startswith("#")))

    tw, th = (int(x) for x in args.tile.split("x"))
    mhtml = fetch_storyboard(vid, args.level, args.out)
    tiles = tiles_from_mhtml(mhtml, tw, th)

    # The sheet spans the whole video, so the tile spacing follows from the
    # count. Duration comes from the last mark only as a floor, so ask yt-dlp.
    r = subprocess.run(_env.PY + ["-m", "yt_dlp", "--skip-download",
                                  "--print", "%(duration)s", "--", vid],
                       env=_env.ENV, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    try:
        duration = float((r.stdout or "").strip())
    except ValueError:
        sys.exit("could not read the video duration")
    step = duration / len(tiles)
    print(f"{len(tiles)} storyboard tiles over {ch.fmt_ts(duration)} "
          f"-- one every {step:.1f}s\n")

    def tile_at(t):
        return tiles[min(len(tiles) - 1, max(0, int(round(t / step))))]

    picks = [tile_at(t) for t, _ in marks]
    sigs = [signature(im) for im in picks]

    labels = []
    for (t, line), im in zip(marks, picks):
        title = line.split(None, 1)[1] if len(line.split(None, 1)) > 1 else ""
        labels.append(f"{ch.fmt_ts(t)} {title}")
    sheet = contact_sheet(picks, labels,
                          os.path.join(args.out, f"{vid}-chapters.png"))

    dull = []
    for i, (t, line) in enumerate(marks):
        title = line.split(None, 1)[1] if len(line.split(None, 1)) > 1 else ""
        dists = [(distance(sigs[i], sigs[j]), j)
                 for j in range(len(marks)) if j != i]
        dups = [j for d, j in dists if d < args.dup]
        alike = [j for d, j in dists if args.dup <= d < args.alike]
        flat = detail(picks[i])
        note = []
        if dups:
            note.append("the same frame as " + ", ".join(
                ch.fmt_ts(marks[j][0]) for j in dups[:4]))
        if alike:
            note.append(f"reads the same at thumbnail size as "
                        + ", ".join(ch.fmt_ts(marks[j][0])
                                    for j in alike[:4])
                        + (f" (+{len(alike) - 4} more)" if len(alike) > 4
                           else ""))
        if flat < 0.010:
            note.append(f"very flat image ({flat:.3f})")
        print(f"{ch.fmt_ts(t):>6}  detail {flat:.3f}  {title[:44]}")
        for n in note:
            print(f"        !! {n}")
        if note:
            dull.append(i)

    if dull:
        print(f"\n{len(dull)} marks would show a dull or duplicate thumbnail. "
              f"Nearby alternatives within +/-{args.window}s:\n")
        for i in dull:
            t = marks[i][0]
            lo = max(0, t - args.window)
            hi = min(duration - 1, t + args.window)
            others = [sigs[j] for j in range(len(marks)) if j != i]
            here = min((distance(sigs[i], o) for o in others), default=1.0)
            best, best_gain = None, here
            tt = lo
            while tt <= hi:
                cand = signature(tile_at(tt))
                gain = min((distance(cand, o) for o in others), default=1.0)
                if gain > best_gain:
                    best, best_gain = tt, gain
                tt += step
            # A candidate only earns a mention if it clears the "reads the
            # same" bar. Without this the search always returned its least-bad
            # option, and measuring showed six of nine such proposals moved
            # the mark without making the thumbnail any more distinguishable.
            if best is not None and best_gain >= args.alike:
                print(f"  {ch.fmt_ts(t)} -> {ch.fmt_ts(best)} "
                      f"({best - t:+.0f}s, {here:.3f} -> {best_gain:.3f})  "
                      f"{marks[i][1].split(None, 1)[1][:38]}")
            else:
                print(f"  {ch.fmt_ts(t)}    nothing better within "
                      f"+/-{args.window}s -- the whole stretch looks alike")

    if sheet:
        print(f"\ncontact sheet: {sheet}")
    print("Per-chapter thumbnails cannot be uploaded -- moving the mark is the "
          "only lever. Re-check any nudge with verify-chapters.py.")


if __name__ == "__main__":
    main()
