#!/usr/bin/env python
"""Recover the edit from a finished video: where it cuts, and which angle each
shot was taken on.

This is the reader half of the multicam round-trip test. Given a programme that
somebody else cut out of several cameras, it answers the two questions you need
in order to rebuild the raw tapes it came from: at which FRAME does the picture
change, and which shots are the same camera as each other.

Three measurements, one decode pass:

  cut       a spike in frame-to-frame difference that is also a local maximum
            AND far above the local median. The last two conditions are what
            separates a cut from a fade: a fade is a sustained moderate
            difference with no peak, and this video ends on one.
  angle     shots cluster by their MEDIAN fingerprint, not their mean. The
            speaker moves; the room behind them does not, and the median is the
            room. Complete linkage, so two angles never chain together through
            a shot that happens to sit between them.
  re-split  a shot whose two halves have different medians was never one shot --
            the cut detector missed it because the angles look alike. Candidate
            split points are the sub-threshold peaks only, so a speaker standing
            up mid-shot (a real change, but a gradual one) cannot be mistaken
            for a cut.

Everything is in FRAME INDICES on the source's own grid. Seconds are derived
and never stored as the truth: at 24000/1001 a rounded second is a third of a
frame out, and the round-trip test scores joins to the frame.

  --list    print the threshold sweep and the shot table, write nothing
  --sheets  one contact sheet per detected angle, to eyeball the clustering
  (none)    write projects/<id>/<id>.shots.json

Invoke as:  python scripts/shot-detect.py --src projects/<id>/temp/program.mp4
"""
import sys, os, json, argparse, subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import

from importlib import import_module  # noqa: E402

import numpy as np  # noqa: E402
import cv2  # noqa: E402

import _project  # noqa: E402

_thumbs = import_module("chapter-thumbs")   # hyphen: not importable by name

ROOT = _env.ROOT
ENV = _env.ENV

# Analysis resolution. Wide enough that two close-ups of different people in
# different corners of the room differ, small enough to stream a whole film.
AW = 128
SIG = 16

SEPARATION_FAILED = (
    "the fingerprints do not separate these angles: a shot resembles a "
    "DIFFERENT angle more than it resembles its own. No threshold fixes that, "
    "because the signal is not there.\n"
    "     What it usually means: every camera shares a background. This method "
    "reads the room behind the speaker, so a studio shooting four people "
    "against one black backdrop gives it nothing to read -- measured on two "
    "hour-long interviews, same-angle distance ran 0.44x the between-angle "
    "distance, where a usable margin is several times ABOVE 1.0. Masking the "
    "lower third and normalising contrast were both tried and neither helped.\n"
    "     Burned-in lower-third name cards do the same thing on a smaller "
    "scale: the same camera fingerprints as a new angle for as long as the "
    "card is up.\n"
    "     Look at --sheets and believe your eyes over the numbers. Telling "
    "these angles apart needs person identity, not appearance -- which this "
    "script does not do.")

DEFAULT_DETECT = {
    "threshold": 0.055,   # mean abs frame difference, 0..1 grey
    "ratio": 4.0,         # ... and this many times the local median
    "window": 4,          # ... and the largest within +/- this many frames
    "median_win": 60,     # frames either side for the local median
    "alike": 0.055,       # two shots this close are the same angle
    "split": 0.070,       # ... and one shot whose halves differ by this is two
    "min_shot": 8,        # frames; shorter than this is a flash, not a shot
}


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, capture_output=True, text=True,
                          env=ENV, **kw)


def hhmmss(t):
    return "%d:%05.2f" % (int(t) // 60, t % 60)


def probe(src):
    """Dimensions and the frame rate as an exact ratio.

    r_frame_rate, not avg_frame_rate: a slightly variable file averages to
    something that is not the grid it was shot on, and every frame index here
    is meant to land on that grid.
    """
    out = run(["ffprobe", "-v", "error", "-select_streams", "v:0",
               "-show_entries", "stream=width,height,r_frame_rate",
               "-of", "json", src]).stdout
    s = json.loads(out)["streams"][0]
    num, den = (int(x) for x in s["r_frame_rate"].split("/"))
    return {"width": int(s["width"]), "height": int(s["height"]),
            "fps_num": num, "fps_den": den, "fps": num / float(den)}


def scan(src, w, h, hwaccel=True):
    """One sequential decode. Returns (diff, sigs) with one row per frame.

    Streaming on purpose: an hour of film is 86k frames, and holding them all
    at analysis resolution is 800 MB. Only the 16x16 fingerprints are kept.
    """
    ah = int(round(AW * h / float(w))) // 2 * 2
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin"]
    if hwaccel:
        cmd += ["-hwaccel", "cuda"]
    cmd += ["-i", src, "-vf", "scale=%d:%d" % (AW, ah),
            "-fps_mode", "passthrough", "-an",
            "-f", "rawvideo", "-pix_fmt", "gray", "-"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, env=ENV)
    nbytes = AW * ah
    diff, sigs, prev = [], [], None
    while True:
        buf = p.stdout.read(nbytes)
        if len(buf) < nbytes:
            break
        f = np.frombuffer(buf, np.uint8).reshape(ah, AW).astype(np.float32) / 255.0
        diff.append(0.0 if prev is None else float(np.abs(f - prev).mean()))
        sigs.append(cv2.resize(f, (SIG, SIG), interpolation=cv2.INTER_AREA))
        prev = f
    p.stdout.close()
    if p.wait() != 0 and hwaccel:
        return scan(src, w, h, hwaccel=False)     # no CUDA decoder for this codec
    return np.array(diff, dtype=np.float32), np.array(sigs, dtype=np.float32)


def local_median(diff, half):
    """Median of |frame difference| around each frame, as a motion floor."""
    n = len(diff)
    out = np.empty(n, dtype=np.float32)
    for i in range(n):
        lo, hi = max(0, i - half), min(n, i + half + 1)
        out[i] = np.median(diff[lo:hi])
    return out


def peaks(diff, window):
    """Frames that are the strictly largest difference within +/- window."""
    n = len(diff)
    out = []
    for i in range(1, n):
        lo, hi = max(1, i - window), min(n, i + window + 1)
        if diff[i] >= diff[lo:hi].max() and diff[i] > 0:
            out.append(i)
    return out


def find_cuts(diff, d):
    """Frame indices where a new shot STARTS."""
    floor = local_median(diff, d["median_win"])
    cuts = []
    for i in peaks(diff, d["window"]):
        if diff[i] >= d["threshold"] and diff[i] >= d["ratio"] * max(floor[i], 1e-4):
            if not cuts or i - cuts[-1] >= d["min_shot"]:
                cuts.append(i)
    return cuts


def med_sig(sigs, a, b, trim=2):
    """The median fingerprint of a span, ignoring the frames next to its edges.

    A frame either side of a cut can be a blend, and one blended frame in a
    short shot drags the median towards the neighbouring angle.
    """
    lo, hi = a + trim, b - trim
    if hi - lo < 1:
        lo, hi = a, b
    return np.median(sigs[lo:hi], axis=0)


def distance(a, b):
    return float(np.abs(a - b).mean())


def resplit(sigs, diff, a, b, d):
    """Split [a, b) wherever it is really two angles, recursively.

    The candidate split points are the difference peaks that did NOT clear the
    cut threshold. That is the whole trick: a missed cut is still a sharp
    frame, just not a sharp enough one, whereas a speaker leaning out of frame
    changes the median without any sharp frame at all.
    """
    if b - a < 2 * d["min_shot"]:
        return [(a, b)]
    cand = [i for i in peaks(diff[a:b], d["window"])
            if d["min_shot"] <= i <= (b - a) - d["min_shot"]]
    best, best_at = 0.0, None
    for i in sorted(cand, key=lambda i: -diff[a + i])[:16]:
        s = distance(med_sig(sigs, a, a + i), med_sig(sigs, a + i, b))
        if s > best:
            best, best_at = s, a + i
    if best_at is None or best < d["split"]:
        return [(a, b)]
    return resplit(sigs, diff, a, best_at, d) + resplit(sigs, diff, best_at, b, d)


def cluster(shot_sigs, alike):
    """Group shots into angles. Complete linkage: merge only when EVERY pair
    across the two groups is alike, so a borderline shot cannot chain two
    distinct angles into one."""
    groups = [[i] for i in range(len(shot_sigs))]
    dist = {}
    for i in range(len(shot_sigs)):
        for j in range(i + 1, len(shot_sigs)):
            dist[(i, j)] = distance(shot_sigs[i], shot_sigs[j])

    def link(g, h):
        return max(dist[(min(x, y), max(x, y))] for x in g for y in h)

    while len(groups) > 1:
        pair, best = None, None
        for i in range(len(groups)):
            for j in range(i + 1, len(groups)):
                v = link(groups[i], groups[j])
                if best is None or v < best:
                    pair, best = (i, j), v
        if best is None or best >= alike:
            break
        i, j = pair
        groups[i] = groups[i] + groups[j]
        groups.pop(j)
    # name the angles in order of first appearance
    groups.sort(key=lambda g: min(g))
    out = [None] * len(shot_sigs)
    for k, g in enumerate(groups):
        for i in g:
            out[i] = "cam%d" % (k + 1)
    return out, groups


def separation(shot_sigs, names):
    """Worst distance inside an angle vs best distance between two angles.

    One number that says whether the clustering was a decision or a coin toss:
    if the widest within-angle gap is larger than the closest between-angle
    gap, the fingerprints do not actually separate these cameras.
    """
    within, between = 0.0, None
    for i in range(len(shot_sigs)):
        for j in range(i + 1, len(shot_sigs)):
            v = distance(shot_sigs[i], shot_sigs[j])
            if names[i] == names[j]:
                within = max(within, v)
            elif between is None or v < between:
                between = v
    return within, between


def frame_png(src, idx, fps_num, fps_den, path, width=320):
    """One frame by index, addressed at the midpoint of its display slot."""
    t = (idx + 0.5) * fps_den / float(fps_num)
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin",
         "-ss", "%.4f" % t, "-i", src, "-frames:v", "1",
         "-vf", "scale=%d:-2" % width, "-y", path])
    return path


def build_shots(diff, sigs, d):
    cuts = find_cuts(diff, d)
    bounds = [0] + cuts + [len(diff)]
    spans = []
    for a, b in zip(bounds, bounds[1:]):
        if b - a >= d["min_shot"]:
            spans.extend(resplit(sigs, diff, a, b, d))
        elif spans:
            spans[-1] = (spans[-1][0], b)          # a flash belongs to its host
        else:
            spans.append((a, b))
    shot_sigs = [med_sig(sigs, a, b) for a, b in spans]
    names, _ = cluster(shot_sigs, d["alike"])
    return spans, shot_sigs, names


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--src", required=True, help="the finished video to read")
    ap.add_argument("--id", help="project id; default: the folder under projects/")
    ap.add_argument("--out", help="default projects/<id>/<id>.shots.json")
    ap.add_argument("--list", action="store_true",
                    help="print the sweep and the shot table, write nothing")
    ap.add_argument("--sheets", action="store_true",
                    help="write one contact sheet per angle into temp/")
    ap.add_argument("--json", action="store_true", help="print the document")
    ap.add_argument("--force", action="store_true",
                    help="write the shot list even if the angles do not separate")
    for k, v in DEFAULT_DETECT.items():
        ap.add_argument("--" + k.replace("_", "-"), type=type(v), default=None,
                        help="default %s" % v)
    args = ap.parse_args()

    d = dict(DEFAULT_DETECT)
    for k in DEFAULT_DETECT:
        v = getattr(args, k, None)
        if v is not None:
            d[k] = v

    src = args.src if os.path.isabs(args.src) else os.path.join(ROOT, args.src)
    if not os.path.exists(src):
        sys.exit("no such file: %s" % args.src)
    pdir = _project.find_project_dir(src)
    pid = args.id or (os.path.basename(pdir) if pdir else
                      os.path.splitext(os.path.basename(src))[0])

    info = probe(src)
    diff, sigs = scan(src, info["width"], info["height"])
    n = len(diff)
    if n < 2:
        sys.exit("decoded %d frames from %s" % (n, args.src))
    fps = info["fps"]

    spans, shot_sigs, names = build_shots(diff, sigs, d)
    within, between = separation(shot_sigs, names)

    if args.list:
        print("%s  %d frames  %.4f fps (%d/%d)  %s"
              % (args.src, n, fps, info["fps_num"], info["fps_den"],
                 hhmmss(n / fps)))
        print("\nthreshold sweep (ratio %.1f, window %d) -- pick a plateau:"
              % (d["ratio"], d["window"]))
        print("  thresh   cuts  shots  angles")
        for t in (0.030, 0.040, 0.050, 0.055, 0.060, 0.070, 0.090, 0.120):
            dd = dict(d, threshold=t)
            sp, ss, nm = build_shots(diff, sigs, dd)
            print("  %6.3f  %5d  %5d  %6d%s"
                  % (t, len(find_cuts(diff, dd)), len(sp), len(set(nm)),
                     "   <- current" if abs(t - d["threshold"]) < 1e-9 else ""))
        print("\nangle separation: worst within %.4f, closest between %s"
              % (within, "n/a" if between is None else "%.4f" % between))
        if between is not None and within >= between:
            print("  !! " + SEPARATION_FAILED)

    print("\n  #  cam    start      end     len  frames        peak")
    for i, ((a, b), nm) in enumerate(zip(spans, names)):
        print("  %2d  %-5s %8s %8s %7.2f  %5d-%-5d  %8.4f"
              % (i, nm, hhmmss(a / fps), hhmmss(b / fps), (b - a) / fps,
                 a, b, diff[a] if a else 0.0))
    by = {}
    for (a, b), nm in zip(spans, names):
        e = by.setdefault(nm, [0, 0])
        e[0] += 1
        e[1] += b - a
    print("")
    for nm in sorted(by):
        print("  %-5s %2d shots  %6d frames  %7.2fs  %4.1f%%"
              % (nm, by[nm][0], by[nm][1], by[nm][1] / fps,
                 100.0 * by[nm][1] / n))

    doc = {
        "_comment": "Shots and angles read back off a finished video by "
                    "scripts/shot-detect.py. Frame indices on the source's "
                    "own grid; end is exclusive. seconds = frame*fps_den/fps_num.",
        "source": _project.norm(src),
        "width": info["width"], "height": info["height"],
        "fps_num": info["fps_num"], "fps_den": info["fps_den"], "fps": fps,
        "n_frames": n,
        "detect": d,
        "separation": {"within": round(within, 5),
                       "between": None if between is None else round(between, 5)},
        "cuts": [a for a, _ in spans[1:]],
        "shots": [{"start": a, "end": b, "camera": nm}
                  for (a, b), nm in zip(spans, names)],
        "cameras": [{"id": nm,
                     "n_shots": sum(1 for x in names if x == nm),
                     "frames": sum(b - a for (a, b), x in zip(spans, names)
                                   if x == nm)}
                    for nm in sorted(set(names))],
    }

    if args.sheets:
        tmp = os.path.join(ROOT, "temp", "shot-detect-%s" % pid)
        os.makedirs(tmp, exist_ok=True)
        from PIL import Image
        for nm in sorted(set(names)):
            imgs, labs = [], []
            for i, ((a, b), x) in enumerate(zip(spans, names)):
                if x != nm:
                    continue
                png = os.path.join(tmp, "%s-shot%02d.png" % (nm, i))
                frame_png(src, (a + b) // 2, info["fps_num"], info["fps_den"], png)
                imgs.append(Image.open(png).copy())
                labs.append("#%d %s %s" % (i, hhmmss(a / fps), hhmmss(b / fps)))
            out = _thumbs.contact_sheet(imgs, labs, os.path.join(tmp, "%s.png" % nm))
            print("sheet: %s" % _project.norm(out))

    if args.json:
        print(json.dumps(doc, indent=2))

    if args.list:
        return

    # Refuse to hand on a shot list whose angles do not separate. Downstream,
    # split-cameras.py builds one full-length tape per angle: on an hour-long
    # interview that mis-clustered into 55, this check is the difference
    # between a warning and fifty-five hours of encoding nobody wanted.
    if between is not None and within >= between and not args.force:
        print("\n!! %s" % SEPARATION_FAILED)
        sys.exit("refusing to write a shot list with %d angles that do not "
                 "separate -- pass --force if you know better" % len(set(names)))

    out = args.out or (os.path.join(pdir, "%s.shots.json" % pid) if pdir
                       else os.path.join(ROOT, "temp", "%s.shots.json" % pid))
    with open(out, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2)
        f.write("\n")
    print("\nwrote %s -- %d shots, %d angles"
          % (_project.norm(out), len(spans), len(set(names))))
    _project.record(pid, "shot-detect", script=__file__, argv=sys.argv[1:],
                    note="%d shots, %d angles, %d cuts from %s"
                         % (len(spans), len(set(names)), len(doc["cuts"]),
                            _project.norm(src)))


if __name__ == "__main__":
    main()
