"""Square talking loops of each speaker in a rendered sketch film: a picker's style tiles.

    python scripts/speaker-loops.py --page <film>.html --video <film>.mp4 --outdir <dir> --list
    python scripts/speaker-loops.py --page <film>.html --video <film>.mp4 --outdir <dir> \
        --crop 960,450,720 --size 200 --rename news=newspaper

A sketch film's page carries its voice timeline (SK.VO: each line's speaker, start and end). For
each speaker this cuts the render where their first line is spoken -- from `--trim-in` seconds
after it starts (a character's entrance is not a loop) to its end, at most `--secs` long -- crops
the square `--crop cx,cy,side` (the video's pixels), scales it to `--size` and writes
`<who>.mp4` (silent, for a muted looping <video>) and `<who>.jpg` (a frame `--poster` seconds
in: the tile before it plays, and off a character's entrance or a blink). kitcut.ai's character-style strip is thirteen of these, cut from the
thirteen-looks film, where each character says its own line full frame.

`--only` picks speakers, `--rename old=new` names a file differently from its speaker, `--nth`
takes a later line. `--list` prints each window and writes nothing.

Invoke as:  python scripts/speaker-loops.py --page <film>.html --video <film>.mp4 --outdir <dir>
"""

import _env  # noqa: F401 -- re-execs into .venv with a clean environment

import os
import sys
import json
import argparse
import subprocess

import _encode


def timeline(page):
    """SK.VO's lines [{who, start, end}] from a rendered film page."""
    with open(page, encoding="utf-8") as f:
        html = f.read()
    i = html.find("SK.VO = {")
    if i < 0:
        sys.exit("%s has no SK.VO: render the film with sketch-render.py first" % page)
    vo, _ = json.JSONDecoder().raw_decode(html[i + len("SK.VO = ") :])
    return vo["lines"]


def windows(lines, only, nth, trim_in, secs):
    """{who: (t0, t1)}: each speaker's nth line, trimmed, in the order they first speak."""
    seen, out = {}, {}
    for L in lines:
        who = L.get("who") or ""
        if not who or (only and who not in only):
            continue
        seen[who] = seen.get(who, 0) + 1
        if seen[who] == nth:
            t0 = L["start"] + trim_in
            out[who] = (t0, min(L["end"], t0 + secs))
    missing = [w for w in only or () if w not in out]
    if missing:
        sys.exit("no line %d for %s in the film" % (nth, ", ".join(missing)))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--page", required=True, help="the film's rendered page (<slug>.html)")
    ap.add_argument("--video", required=True, help="the film's render (<slug>.mp4)")
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--crop", default="960,450,720", help="cx,cy,side in the video's pixels")
    ap.add_argument("--size", type=int, default=200, help="the loop's side in pixels")
    ap.add_argument("--secs", type=float, default=3.0, help="longest loop")
    ap.add_argument("--trim-in", type=float, default=0.3, help="skip this much of each line")
    ap.add_argument("--nth", type=int, default=1, help="which of a speaker's lines")
    ap.add_argument("--only", default="", help="speakers, comma-separated")
    ap.add_argument("--rename", nargs="*", default=[], help="old=new file names")
    ap.add_argument("--poster", type=float, default=0.5, help="seconds into the loop for the .jpg")
    ap.add_argument("--cq", type=int, default=30, help="quality (smaller is better)")
    ap.add_argument("--list", action="store_true", help="print the windows, write nothing")
    args = ap.parse_args()

    only = [w for w in args.only.split(",") if w]
    names = dict(r.split("=", 1) for r in args.rename)
    got = windows(timeline(args.page), only, args.nth, args.trim_in, args.secs)
    cx, cy, side = (int(v) for v in args.crop.split(","))
    crop = "crop=%d:%d:%d:%d,scale=%d:%d:flags=lanczos" % (
        side,
        side,
        cx - side // 2,
        cy - side // 2,
        args.size,
        args.size,
    )
    for who, (t0, t1) in got.items():
        print("  %-12s %-14s %6.2f - %6.2f  (%.2f s)" % (who, names.get(who, who), t0, t1, t1 - t0))
    if args.list:
        return

    cfg = _encode.resolve({"encoder": "libx264", "cq": args.cq, "preset": "p7", "gop": 30})
    os.makedirs(args.outdir, exist_ok=True)
    for who, (t0, t1) in got.items():
        base = os.path.join(args.outdir, names.get(who, who))
        cut = ["ffmpeg", "-v", "error", "-y", "-ss", "%.3f" % t0, "-t", "%.3f" % (t1 - t0)]
        subprocess.run(
            cut
            + ["-i", args.video, "-vf", crop, "-an"]
            + _encode.video_args(cfg)
            + ["-movflags", "+faststart", base + ".mp4"],
            check=True,
        )
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-ss", "%.3f" % min(args.poster, (t1 - t0) / 2)]
            + ["-i", base + ".mp4", "-frames:v", "1", "-q:v", "3"]
            + [base + ".jpg"],
            check=True,
        )
        kb = (os.path.getsize(base + ".mp4") + os.path.getsize(base + ".jpg")) / 1024
        print("  wrote %s.mp4 + .jpg  (%.0f KB)" % (os.path.abspath(base), kb))


if __name__ == "__main__":
    main()
