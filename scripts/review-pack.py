#!/usr/bin/env python
"""A video laid out for a reviewer who cannot play it: pictures to read, and what can be counted.

A reader of contact sheets a frame a second passes an opening that a person switches off: on
2026-10-12 a reviewer said "ship it" to the first 25 seconds of a padel film that was one painting
standing still, and its owner's answer after watching was "I don't like what I saw". A second in
an opening is long. This puts the opening in front of the reviewer four frames a second, with the
words being spoken under each frame, and measures the things an eye misjudges from stills:

    opening-NN.jpg  the first --opening seconds, four frames a second, twelve to a sheet, each
                    frame with its time and (with --lines) the narrator's words of that quarter
    film-NN.jpg     the whole video, a frame a second, thirty-five to a sheet
    cut-NN.jpg      each hard cut of the opening as six frames, 0.2 s before it to 0.4 s after
    first.jpg       the file's first frame at full size (what a player shows before it starts)
    at-<t>.jpg      --at: any other moments at full size
    pack.md         the count: length, frame rate, the cuts and the shots between them, the
                    stretches where the picture is slow or still (the bars of short-stillness.py),
                    loudness second by second with the quiet seconds marked, the narration's
                    first word and its pauses

Nothing here judges. The video-review skill is the judge; this is what it reads.

Stillness is read on the whole frame, so words that pop in over a frozen picture count as
movement: a stretch this calls still is still, a stretch it passes may only have had type moving.
Hard cuts only: a dissolve is not listed. Loudness is the whole mix; nothing here can tell a voice
from music, which is why --lines exists.

Invoke as:
    python scripts/review-pack.py <video> [--out DIR] [--opening 30] [--lines timeline.json]
                                  [--at 2.4,6.1] [--list]
    --list   measure and print pack.md's text; write no pictures
"""

import argparse
import importlib
import itertools
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402, F401 -- re-execs into .venv; before any 3rd-party import

import numpy as np  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

stillness = importlib.import_module("short-stillness")  # its bars, so both tools mean the same

OPEN_FPS, OPEN_TILE, OPEN_GRID = 4, 480, (4, 3)  # the opening: frames a second, tile width, sheet
FILM_TILE, FILM_GRID = 384, (7, 5)  # the whole video, a frame a second
CUT_FPS, CUT_W, CUT_H = 10, 160, 90  # what cuts are found at
CUT_LEVEL, CUT_RATIO = 12.0, 3.0  # a cut: this many grey levels of change, and this many times its
#                                   neighbourhood's (a fast pan changes a lot too, but all along)
MIN_SHOT = 0.4  # two cuts closer than this are one (a title slamming in right after a cut)
QUIET = 10.0  # a second this far under the video's own loudness is marked quiet
PAUSE = 1.5  # a gap between two narration lines worth naming, seconds


def run(cmd):
    """One ffmpeg or ffprobe call that must work, with its output."""
    return subprocess.run(cmd, capture_output=True, check=True)


def probe(path):
    """-> {seconds, fps, w, h, audio}."""
    ask = "stream=codec_type,width,height,r_frame_rate:format=duration"
    j = json.loads(
        run(["ffprobe", "-v", "error", "-show_entries", ask, "-of", "json", path]).stdout
    )
    v = next(s for s in j["streams"] if s["codec_type"] == "video")
    n, d = v["r_frame_rate"].split("/")
    return {
        "seconds": float(j["format"]["duration"]),
        "fps": float(n) / float(d or 1),
        "w": v["width"],
        "h": v["height"],
        "audio": any(s["codec_type"] == "audio" for s in j["streams"]),
    }


def frames(path, fps, w, h, mode="gray", seconds=None):
    """The video sampled `fps` times a second at w x h, as one array (frames, h, w[, 3])."""
    cmd = ["ffmpeg", "-v", "error", "-i", path]
    cmd += ["-t", "%.3f" % seconds] if seconds else []
    pix = "gray" if mode == "gray" else "rgb24"
    cmd += ["-vf", "fps=%g,scale=%d:%d" % (fps, w, h), "-pix_fmt", pix, "-f", "rawvideo", "-"]
    raw = np.frombuffer(run(cmd).stdout, np.uint8)
    return raw.reshape(-1, h, w) if mode == "gray" else raw.reshape(-1, h, w, 3)


def cuts_of(path):
    """The hard cuts' times: one frame unlike the last, in a stretch that is not all change."""
    f = frames(path, CUT_FPS, CUT_W, CUT_H).astype(np.int16)
    d = np.abs(np.diff(f, axis=0)).mean(axis=(1, 2))
    out = []
    for i, v in enumerate(d):
        near = np.concatenate([d[max(0, i - CUT_FPS) : i], d[i + 1 : i + 1 + CUT_FPS]])
        if v >= CUT_LEVEL and v >= CUT_RATIO * max(1.0, float(np.median(near)) if len(near) else 0):
            t = (i + 1) / CUT_FPS
            if not out or t - out[-1] >= MIN_SHOT:  # type landing after a cut is not a second cut
                out.append(t)
    return out


def still_of(path, h):
    """-> (share still, share slow, [(start, length)] of the slow stretches), on the whole frame."""
    f = frames(path, stillness.FPS, 160, h).astype(np.int16)
    m = stillness.moved(f)
    if not len(m):
        return 0.0, 0.0, []
    runs = stillness.stretches(m < stillness.SLOW)
    return float((m < stillness.STILL).mean()), float((m < stillness.SLOW).mean()), runs


def loudness_of(path):
    """-> ([loudest moment of each second, LUFS], integrated LUFS, true peak dBFS)."""
    err = subprocess.run(
        ["ffmpeg", "-nostats", "-i", path, "-vn", "-af", "ebur128=peak=true", "-f", "null", "-"],
        capture_output=True,
        check=True,
    ).stderr.decode("utf-8", "replace")
    per = {}
    for t, m in re.findall(r"t:\s*([\d.]+)\s+TARGET:.*?M:\s*(-?[\d.]+|-?inf)", err):
        v = float(m) if "inf" not in m else -120.0
        per[int(float(t))] = max(per.get(int(float(t)), -120.0), v)
    tail = err[err.rfind("Summary:") :]
    integrated = re.search(r"I:\s*(-?[\d.]+) LUFS", tail)
    peak = re.search(r"Peak:\s*(-?[\d.]+) dBFS", tail)
    return (
        [per.get(i, -120.0) for i in range(max(per) + 1)] if per else [],
        float(integrated.group(1)) if integrated else None,
        float(peak.group(1)) if peak else None,
    )


def clock(t):
    """Seconds as m:ss.s."""
    return "%d:%04.1f" % (t // 60, t % 60)


def font(size):
    """A plain face for the stamps on the tiles, whatever the machine has."""
    for name in ("arial.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def said_in(lines, t0, t1):
    """The narrator's words that begin in [t0, t1)."""
    return " ".join(w["text"] for ln in lines for w in ln.get("words", []) if t0 <= w["s"] < t1)


def sheet(tiles, grid, tile, out, strip=0):
    """tiles: [(RGB array, stamp, words)] -> one picture; `strip` px under each for the words."""
    th = tiles[0][0].shape[0]
    im = Image.new("RGB", (grid[0] * tile, grid[1] * (th + strip)), (16, 16, 16))
    d, f, small = ImageDraw.Draw(im), font(15), font(max(11, tile // 34))
    for k, (a, stamp, words) in enumerate(tiles):
        x, y = (k % grid[0]) * tile, (k // grid[0]) * (th + strip)
        im.paste(Image.fromarray(a), (x, y))
        d.rectangle([x, y, x + 10 + 8 * len(stamp), y + 19], fill=(0, 0, 0))
        d.text((x + 4, y + 2), stamp, fill=(255, 255, 255), font=f)
        if strip and words:
            d.text((x + 6, y + th + 4), words[: tile // 7], fill=(235, 225, 150), font=small)
    im.save(out, quality=88)


def sheets(path, out, name, fps, tile, grid, seconds, src_h, lines):
    """The video (or its first `seconds`) as numbered sheets of stamped tiles; -> the files."""
    th = round(tile * src_h) // 2 * 2
    f = frames(path, fps, tile, th, mode="rgb", seconds=seconds)
    strip, per, files = (24 if lines else 0), grid[0] * grid[1], []
    for n in range(0, len(f), per):
        part = [
            (f[i], clock(i / fps), said_in(lines, i / fps, (i + 1) / fps) if lines else "")
            for i in range(n, min(n + per, len(f)))
        ]
        files.append(os.path.join(out, "%s-%02d.jpg" % (name, n // per + 1)))
        sheet(part, grid, tile, files[-1], strip)
    return files


def still_frame(path, t, out, width=None):
    """One frame at t, full size (or `width` wide)."""
    cmd = ["ffmpeg", "-v", "error", "-y", "-ss", "%.3f" % max(0, t), "-i", path, "-frames:v", "1"]
    cmd += ["-vf", "scale=%d:-2" % width] if width else []
    run([*cmd, "-q:v", "2", out])


def report(path, p, cuts, still, loud, lines, opening):
    """pack.md's text."""
    share_still, share_slow, runs = still
    per, integrated, peak = loud
    o = ["# Review pack: %s" % os.path.basename(path), ""]
    o.append(
        "%s long, %dx%d, %g frames a second%s."
        % (
            clock(p["seconds"]),
            p["w"],
            p["h"],
            round(p["fps"], 2),
            "" if p["audio"] else ", NO SOUND",
        )
    )
    o += ["", "## Cuts (hard cuts only; a dissolve is not listed)", ""]
    first = [c for c in cuts if c <= opening]
    marks = [0.0, *first, min(opening, p["seconds"])]
    shots = [b - a for a, b in itertools.pairwise(marks)]
    o.append("%d in the whole video, %d in the first %g s." % (len(cuts), len(first), opening))
    if first:
        o.append("Opening cuts at: " + ", ".join(clock(c) for c in first))
    o.append(
        "Opening shots, seconds each: %s (longest %.1f)"
        % (" ".join("%.1f" % s for s in shots), max(shots))
    )
    o += [
        "",
        "## Stillness (whole frame; type moving over a frozen picture counts as movement)",
        "",
    ]
    o.append("Still %d%% of the time, slow or still %d%%." % (share_still * 100, share_slow * 100))
    if runs:
        o.append("Slow stretches of %g s and longer:" % stillness.RUN)
        o += ["- %s to %s (%.1f s)" % (clock(s), clock(s + d), d) for s, d in runs]
    else:
        o.append("No slow stretch of %g s or longer." % stillness.RUN)
    o += ["", "## Loudness (the whole mix; nothing here tells a voice from music)", ""]
    if integrated is None:
        o.append("No sound to measure.")
    else:
        o.append("Integrated %.1f LUFS, true peak %s dBFS." % (integrated, peak))
        quiet = [i for i, v in enumerate(per) if v < integrated - QUIET]
        o.append(
            "Seconds more than %g LU under that: %s"
            % (QUIET, ", ".join(clock(i) for i in quiet[:40]) or "none")
        )
        o.append("The opening, the loudest moment of each second (LUFS):")
        row = ["%d:%02d %.0f" % (i // 60, i % 60, v) for i, v in enumerate(per[: int(opening) + 1])]
        o += ["  " + "   ".join(row[i : i + 8]) for i in range(0, len(row), 8)]
    if lines:
        o += ["", "## Narration", ""]
        o.append("First word at %s." % clock(lines[0]["start"]))
        gaps = [
            (a["end"], b["start"] - a["end"])
            for a, b in itertools.pairwise(lines)
            if b["start"] - a["end"] >= PAUSE
        ]
        o.append("Pauses of %g s and longer between lines:" % PAUSE if gaps else "No long pause.")
        o += ["- at %s, %.1f s" % (clock(t), g) for t, g in gaps[:60]]
        o += ["", "Lines in the opening:"]
        o += [
            "- %s to %s  %s" % (clock(ln["start"]), clock(ln["end"]), ln["text"])
            for ln in lines
            if ln["start"] < opening
        ]
    return "\n".join(o) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("video")
    ap.add_argument("--out", help="the pack's folder (default temp/review/<video's name>)")
    ap.add_argument("--opening", type=float, default=30.0, help="seconds read at 4 frames a second")
    ap.add_argument("--lines", help="the narration's timeline.json (audio/vo/timeline.json)")
    ap.add_argument("--at", default="", help="more moments at full size, seconds, comma separated")
    ap.add_argument("--list", action="store_true", help="measure and print; write no pictures")
    a = ap.parse_args()
    path = _env.resolve(a.video, base=_env.workspace())
    p = probe(path)
    opening = min(a.opening, p["seconds"])
    lines = []
    if a.lines:
        with open(_env.resolve(a.lines, base=_env.workspace()), encoding="utf-8") as f:
            lines = [ln for ln in json.load(f)["lines"] if ln["start"] < p["seconds"]]
    cuts = cuts_of(path)
    loud = loudness_of(path) if p["audio"] else ([], None, None)
    text = report(path, p, cuts, still_of(path, 90), loud, lines, opening)
    if a.list:
        print(text)
        return
    stem = os.path.splitext(os.path.basename(path))[0]
    out = a.out or os.path.join(_env.workspace(), "temp", "review", stem)
    out = _env.resolve(out, base=_env.workspace())
    os.makedirs(out, exist_ok=True)
    ratio = p["h"] / p["w"]
    made = sheets(path, out, "opening", OPEN_FPS, OPEN_TILE, OPEN_GRID, opening, ratio, lines)
    made += sheets(path, out, "film", 1, FILM_TILE, FILM_GRID, None, ratio, lines)
    for n, c in enumerate([c for c in cuts if c <= opening][:16], 1):
        tiles = []
        for dt in (-0.2, -0.1, 0.0, 0.1, 0.2, 0.4):
            tmp = os.path.join(out, "_cut.jpg")
            still_frame(path, c + dt, tmp, 640)
            tiles.append((np.asarray(Image.open(tmp).convert("RGB")), clock(c + dt), ""))
            os.remove(tmp)
        made.append(os.path.join(out, "cut-%02d.jpg" % n))
        sheet(tiles, (3, 2), 640, made[-1])
    still_frame(path, 0, os.path.join(out, "first.jpg"))
    for t in [float(x) for x in a.at.split(",") if x.strip()]:
        still_frame(path, t, os.path.join(out, "at-%s.jpg" % ("%.1f" % t).replace(".", "_")))
    with open(os.path.join(out, "pack.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print(text)
    print("%d pictures and pack.md in %s" % (len(made) + 1, out))


if __name__ == "__main__":
    main()
