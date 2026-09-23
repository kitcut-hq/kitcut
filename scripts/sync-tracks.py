#!/usr/bin/env python
"""Align a silent screen recording with the camera take that carries the sound.

A screen recorder that captured no audio leaves nothing to cross-correlate
against, so the offset has to come from somewhere else. Three sources, in
increasing order of trust:

  creation_time   both containers stamp the START of capture in UTC, so they
                  subtract directly. Whole-second granularity, so this is a
                  seed accurate to about +/-1 s, not an answer.
  correlate       the screen changes when keys are pressed, and the camera mic
                  hears those keys. Cross-correlating screen change-energy
                  against high-band audio energy refines the seed to a frame --
                  WHEN it works. Claude streaming output moves the screen
                  silently and speech moves the audio without touching the
                  screen, so the peak can be mush. The confidence is reported
                  and a weak peak is refused rather than used.
  anchors         a phrase in the transcript pinned to a time on screen. Exact
                  when the phrase is one that was typed AND read aloud, because
                  then the same words exist in both streams.

Nothing here renders. It writes config/screencast/<id>.sync.json and, with
--verify, a contact sheet pairing each screen frame with the camera frame the
offset claims is simultaneous, so a human can confirm before an encode is spent.

Invoke as:  python scripts/sync-tracks.py --manifest config/screencast/<id>.json
"""

import sys
import os
import json
import argparse
import subprocess
import datetime
import hashlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import
import numpy as np  # noqa: E402
from importlib import import_module  # noqa: E402

_outline = import_module("transcript-outline")

ROOT = _env.ROOT


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kw)


def probe(path):
    """Container and video-stream facts, including the rotation side-data.

    Rotation is REPORTED, never applied blindly. See the note in rotation_of().
    """
    out = run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,avg_frame_rate,duration",
            "-show_entries",
            "format=duration,size",
            "-show_entries",
            "format_tags=creation_time",
            "-of",
            "json",
            path,
        ]
    ).stdout
    d = json.loads(out)
    st = (d.get("streams") or [{}])[0]
    fm = d.get("format") or {}
    num, _, den = (st.get("avg_frame_rate") or "0/1").partition("/")
    fps = float(num) / float(den) if float(den or 0) else 0.0
    return {
        "path": path,
        "width": int(st.get("width") or 0),
        "height": int(st.get("height") or 0),
        "fps": fps,
        "duration": float(fm.get("duration") or st.get("duration") or 0.0),
        "size": int(fm.get("size") or 0),
        "creation_time": (fm.get("tags") or {}).get("creation_time"),
        "rotation": rotation_of(path),
    }


def rotation_of(path):
    """Degrees in the display matrix, or None.

    Deliberately separate from probe(): this repo has been bitten from BOTH
    sides. Ignoring the tag turns portrait phone footage into a landscape crop;
    honouring it turned this shoot's main take on its side, because the phone
    was mounted flat and iOS guessed the orientation wrong. The tag is evidence,
    not instruction -- the manifest decides, and --verify shows the frame.
    """
    out = run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream_side_data=rotation",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            path,
        ]
    ).stdout
    for line in out.splitlines():
        line = line.strip()
        if line:
            try:
                return float(line)
            except ValueError:
                pass
    return None


def parse_utc(s):
    if not s:
        return None
    s = s.replace("Z", "+00:00")
    try:
        return datetime.datetime.fromisoformat(s)
    except ValueError:
        return None


def sha1_head(path, n=1 << 20):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        h.update(f.read(n))
    return h.hexdigest()[:16]


def change_signal(path, hz, w, h, noautorotate=False):
    """Per-bin mean absolute frame difference -- 'how much did the screen move'.

    Decoded to tiny greyscale so the whole pass is I/O rather than pixels, and
    streamed so a 2 GB source never lands in memory.
    """
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error"]
    if noautorotate:
        cmd.append("-noautorotate")
    cmd += [
        "-i",
        path,
        "-an",
        "-vf",
        "fps=%g,scale=%d:%d,format=gray" % (hz, w, h),
        "-f",
        "rawvideo",
        "-",
    ]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=1 << 23)
    n = w * h
    prev, out = None, []
    while True:
        buf = p.stdout.read(n)
        if len(buf) < n:
            break
        cur = np.frombuffer(buf, dtype=np.uint8).astype(np.int16)
        if prev is not None:
            out.append(float(np.abs(cur - prev).mean()))
        prev = cur
    p.stdout.close()
    p.wait()
    return np.asarray(out, dtype=np.float64)


def audio_signal(path, hz, highpass=3000, sr=16000):
    """Per-bin RMS of the high-passed audio -- biased towards key clicks.

    Voiced speech lives mostly below 3 kHz; keyboard transients are broadband.
    High-passing does not remove speech, but it stops speech from dominating a
    correlation whose only real evidence is typing.
    """
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        path,
        "-vn",
        "-af",
        "highpass=f=%d" % highpass,
        "-ac",
        "1",
        "-ar",
        str(sr),
        "-f",
        "s16le",
        "-",
    ]
    raw = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL).stdout
    x = np.frombuffer(raw, dtype=np.int16).astype(np.float64)
    step = max(1, int(round(sr / hz)))
    n = len(x) // step
    if n == 0:
        return np.zeros(0)
    x = x[: n * step].reshape(n, step)
    return np.sqrt((x * x).mean(axis=1))


def norm(a):
    a = a - a.mean()
    s = a.std()
    return a / s if s > 0 else a


def correlate(screen, camera, seed, search, hz):
    """Slide the screen signal over the camera signal around the seed.

    Returns (best_offset, confidence, curve). Confidence is the peak's z-score
    against the rest of the search curve: how far it stands out from the noise,
    not how tall it is. A real alignment spikes; mush does not.
    """
    s, c = norm(screen), norm(camera)
    lo = int(round((seed - search) * hz))
    hi = int(round((seed + search) * hz))
    lags, scores = [], []
    for lag in range(lo, hi + 1):
        if lag >= 0:
            n = min(len(s), len(c) - lag)
            if n < hz * 10:
                continue
            v = float(np.dot(s[:n], c[lag : lag + n]) / n)
        else:
            n = min(len(s) + lag, len(c))
            if n < hz * 10:
                continue
            v = float(np.dot(s[-lag : -lag + n], c[:n]) / n)
        lags.append(lag)
        scores.append(v)
    if not lags:
        return None, 0.0, []
    scores = np.asarray(scores)
    k = int(np.argmax(scores))
    spread = scores.std()
    z = float((scores[k] - scores.mean()) / spread) if spread > 0 else 0.0
    return lags[k] / float(hz), z, list(zip([l / float(hz) for l in lags], scores.tolist()))


def anchor_residuals(anchors, words, offset):
    """For each anchor: where the phrase is spoken vs where the screen shows it.

    An anchor names a phrase and the screen time of the event it belongs to.
    camera_t = screen_t + offset, so the residual is how far the spoken phrase
    sits from where the offset predicts it.
    """
    rows = []
    for a in anchors:
        hit = _outline.find(words, a["text"], loose=not a.get("exact"), nth=int(a.get("nth", 0)))
        if hit is None:
            rows.append({"text": a["text"], "screen_t": a.get("screen_t"), "found": False})
            continue
        spoke_a, spoke_b = hit
        want = float(a["screen_t"]) + offset
        rows.append(
            {
                "text": a["text"],
                "screen_t": float(a["screen_t"]),
                "spoken_start": spoke_a,
                "spoken_end": spoke_b,
                "predicted_camera_t": want,
                "residual": spoke_a - want,
                "found": True,
            }
        )
    return rows


def fit_offset(found, seed):
    """Least-squares offset (and rate) across anchors.

    Rate is only fitted with three or more anchors spanning real time: two
    points always fit a line exactly, which would report zero error for any
    pair of noisy readings.
    """
    if not found:
        return seed, 0.0, None
    xs = np.array([a["screen_t"] for a in found], dtype=np.float64)
    ys = np.array([a["spoken_start"] for a in found], dtype=np.float64)
    if len(xs) >= 3 and (xs.max() - xs.min()) > 60.0:
        rate, off = np.polyfit(xs, ys, 1)
        resid = ys - (rate * xs + off)
        return float(off), float(np.abs(resid).max()), float((rate - 1.0) * 1e6)
    off = float(np.mean(ys - xs))
    resid = (ys - xs) - off
    return off, float(np.abs(resid).max()), None


def verify_sheet(screen, camera, offset, times, outdir, rotate_camera):
    """Pair each screen frame with the camera frame the offset calls simultaneous."""
    os.makedirs(outdir, exist_ok=True)
    made = []
    for t in times:
        dst = os.path.join(outdir, "sync_%07.2f.jpg" % t)
        cam_t = t + offset
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", "%.3f" % t, "-i", screen]
        if not rotate_camera:
            cmd.append("-noautorotate")
        cmd += [
            "-ss",
            "%.3f" % cam_t,
            "-i",
            camera,
            "-filter_complex",
            "[0:v]scale=-2:400,setsar=1[a];[1:v]scale=-2:400,setsar=1[b];[a][b]hstack=inputs=2",
            "-frames:v",
            "1",
            "-q:v",
            "4",
            "-y",
            dst,
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        made.append((t, cam_t, dst))
    return made


def busiest(signal, hz, k, skip=5.0):
    """The k moments the screen moved most -- the only frames worth pairing.

    A frozen frame proves nothing about alignment: two identical screenshots
    look aligned at every offset.
    """
    picked = []
    for i in np.argsort(signal)[::-1]:
        t = (i + 1) / float(hz)
        if all(abs(t - p) > skip for p in picked):
            picked.append(t)
        if len(picked) >= k:
            break
    return sorted(picked)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--offset", type=float, help="force this offset instead of measuring one")
    ap.add_argument(
        "--no-correlate", action="store_true", help="skip the screen-change vs key-click pass"
    )
    ap.add_argument(
        "--verify", action="store_true", help="write paired frames that prove the offset"
    )
    ap.add_argument("--samples", type=int, default=6)
    ap.add_argument(
        "--min-confidence",
        type=float,
        default=6.0,
        help="reject a correlation peak below this z-score",
    )
    ap.add_argument("-o", "--out", help="sidecar path (default beside manifest)")
    args = ap.parse_args()

    m = json.load(open(args.manifest, encoding="utf-8"))
    mid = m.get("id") or os.path.splitext(os.path.basename(args.manifest))[0]

    def rel(p):
        return _env.resolve(p)

    screen, camera = rel(m["screen"]), rel(m["camera"])
    for p in (screen, camera):
        if not os.path.exists(p):
            sys.exit("missing input: %s" % p)

    sync = m.get("sync") or {}
    hz = float(sync.get("hz", 10))
    search = float(sync.get("search", 6.0))
    rotate_camera = m.get("camera_rotate", "auto") != "none"

    ps, pc = probe(screen), probe(camera)
    print("screen  %s" % os.path.basename(screen))
    print(
        "        %dx%d  %.3f fps  %.2fs  start %s"
        % (ps["width"], ps["height"], ps["fps"], ps["duration"], ps["creation_time"])
    )
    print("camera  %s" % os.path.basename(camera))
    print(
        "        %dx%d  %.3f fps  %.2fs  start %s  rotation %s"
        % (
            pc["width"],
            pc["height"],
            pc["fps"],
            pc["duration"],
            pc["creation_time"],
            pc["rotation"],
        )
    )
    if pc["rotation"] and not rotate_camera:
        print("        camera_rotate=none in the manifest, so that tag is IGNORED")

    notes = []
    ts, tc = parse_utc(ps["creation_time"]), parse_utc(pc["creation_time"])
    seed = None
    if ts and tc:
        seed = (ts - tc).total_seconds()
        print("\nseed from creation_time %+.3fs  (screen t=0 is camera t=%.3f)" % (seed, seed))
        notes.append("creation_time seed %+.3fs; whole-second stamps, so +/-1s" % seed)
    else:
        print("\nno creation_time on one of the inputs")

    offset, method, confidence = seed, "creation_time", None

    if args.offset is not None:
        offset, method = args.offset, "manual"
        print("offset forced to %+.3fs" % offset)
    elif not args.no_correlate and seed is not None:
        print("\ncorrelating screen change against camera key clicks ...")
        sc = change_signal(screen, hz, 160, 96)
        ac = audio_signal(camera, hz)
        print("  screen %d bins, camera %d bins" % (len(sc), len(ac)))
        best, z, _ = correlate(sc, ac, seed, search, hz)
        if best is None:
            print("  no usable overlap")
        else:
            print(
                "  peak %+.3fs  z=%.1f  (seed %+.3fs, delta %+.3fs)" % (best, z, seed, best - seed)
            )
            if z >= args.min_confidence:
                offset, method, confidence = best, "correlate", z
                notes.append("correlation peak z=%.1f accepted" % z)
            else:
                print("  z below --min-confidence %.1f, keeping the seed" % args.min_confidence)
                notes.append("correlation z=%.1f rejected, seed kept" % z)

    rows = []
    anchors = sync.get("anchors") or []
    if anchors:
        wp = m.get("words")
        if not wp:
            sys.exit('anchors need a "words" transcript in the manifest')
        words = _outline.load_words(rel(wp))
        rows = anchor_residuals(anchors, words, offset)
        print("\nanchors")
        for r in rows:
            if not r["found"]:
                print("  NOT FOUND  %r" % r["text"][:50])
                continue
            print(
                "  screen %8.2f  spoken %8.2f  residual %+6.2fs  %r"
                % (r["screen_t"], r["spoken_start"], r["residual"], r["text"][:40])
            )
        found = [r for r in rows if r["found"]]
        if found:
            off2, worst, drift = fit_offset(found, offset)
            print(
                "  fitted offset %+.3fs   worst residual %.2fs%s"
                % (off2, worst, "" if drift is None else "   drift %+.0f ppm" % drift)
            )
            offset, method, confidence = off2, "anchors", worst
            notes.append("fitted from %d anchors, worst residual %.2fs" % (len(found), worst))

    if offset is None:
        sys.exit("no offset could be determined; pass --offset")

    cam_start, cam_end = offset, offset + ps["duration"]
    print("\ncoverage")
    print(
        "  screen 0.00 .. %.2f  ->  camera %.2f .. %.2f   (camera is %.2f)"
        % (ps["duration"], cam_start, cam_end, pc["duration"])
    )
    short = 0.0
    if cam_start < -0.001:
        print("  CAMERA STARTS LATE by %.2fs" % (-cam_start))
        notes.append("camera starts %.2fs after the screen" % (-cam_start))
    if cam_end > pc["duration"] + 0.001:
        short = cam_end - pc["duration"]
        print("  CAMERA RUNS OUT %.2fs before the screen ends" % short)
        notes.append("camera short by %.2fs at the tail" % short)
    if cam_start >= -0.001 and short <= 0.001:
        print(
            "  camera covers the whole screen recording "
            "(%.1fs lead-in, %.1fs tail)" % (cam_start, pc["duration"] - cam_end)
        )

    if args.verify:
        hz2 = 4.0
        times = busiest(change_signal(screen, hz2, 160, 96), hz2, args.samples)
        outdir = os.path.join(ROOT, "temp", "sync-%s" % mid)
        made = verify_sheet(screen, camera, offset, times, outdir, rotate_camera)
        print("\nverify frames (screen | camera) at the busiest screen moments:")
        for t, ct, dst in made:
            print("  screen %7.2f  camera %7.2f  %s" % (t, ct, os.path.relpath(dst, ROOT)))

    out = args.out or os.path.join(os.path.dirname(args.manifest), "%s.sync.json" % mid)
    doc = {
        "_comment": "Written by sync-tracks.py. offset is the camera time that "
        "lines up with screen t=0: camera_t = screen_t + offset.",
        "id": mid,
        "screen": m["screen"],
        "camera": m["camera"],
        "screen_probe": ps,
        "camera_probe": pc,
        "camera_rotate": m.get("camera_rotate", "auto"),
        "seed_offset": seed,
        "offset": round(float(offset), 4),
        "method": method,
        "confidence": confidence,
        "anchors": rows,
        "coverage": {
            "camera_start": round(cam_start, 3),
            "camera_end": round(cam_end, 3),
            "camera_duration": pc["duration"],
            "short_by": round(short, 3),
        },
        "notes": notes,
        "input_sha1_head": {
            os.path.basename(screen): sha1_head(screen),
            os.path.basename(camera): sha1_head(camera),
        },
    }
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    print("\noffset %+.3fs by %s -> %s" % (offset, method, os.path.relpath(out, ROOT)))


if __name__ == "__main__":
    main()
