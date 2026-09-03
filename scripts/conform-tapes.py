#!/usr/bin/env python
"""Put N real recordings from different devices onto one grid, provably.

`angle-cut.py` trims each tape by FRAME NUMBER and concatenates the pieces, so
every tape must share one frame rate and one frame size. Synthetic tapes do by
construction. Real ones never do: a phone, a webcam and a mirrorless are three
rates and three sizes, and the phone is usually not even on the rate it claims.

Nothing checked this. `angle-cut.py` reads the rate and the size off the
REFERENCE tape and applies them to all of them, so a 60 fps webcam beside a
30 fps phone addresses frames at half speed on one of the two and the film is
silently wrong -- the failure the whole conform-before-measuring discipline
exists to prevent, arriving through the one door that had no lock on it.

Three ways to reach a target rate, and which one is used is decided by
arithmetic and printed, never guessed:

  regrid    the source is already at the target within --rate-tol (a phone
            claiming 30 and delivering 30.03). setpts by frame INDEX, frame
            for frame; the count is asserted unchanged. Never the `fps`
            filter, which hits its target by duplicating and dropping -- the
            one thing this step exists to rule out.
  decimate  the source is an exact integer multiple (60 -> 30). Keep every
            k-th frame with `select`, which is exact and says so in the
            filtergraph; the count is asserted to be ceil(n/k).
  refuse    anything else (50 -> 30, 23.976 -> 30). Resampling those means
            inventing or discarding frames unevenly, and a tape that has to
            be resampled is a decision for a person, not a default.

Size is `scale` + `pad` -- letterboxed, never cropped. A tape is evidence;
cropping one to fit the grid throws away picture the edit might want, and the
pad is visible while a crop is not.

  --list    print what each tape would become and which route it takes,
            encode nothing
  (none)    conform, asserting size and frame count on every output

Invoke as:  python scripts/conform-tapes.py --manifest projects/<id>/anglecut.json
            python scripts/conform-tapes.py --tapes a.mkv b.mp4 --outdir projects/<id>/tapes --fps 30 --size 1920x1080
"""
import sys
import os
import json
import math
import shutil
import argparse
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import
import _encode  # noqa: E402 -- the one place encoder keys are chosen
import _project  # noqa: E402

ROOT = _env.ROOT
ENV = _env.ENV

SR = 48000                      # every tape resampled to this, as split-cameras
# A conform is an intermediate that a real render reads again, so it is kept
# visually lossless-ish: cq 16 is what split-cameras.py conforms at.
DEFAULT_CONFORM = {"speed": 5, "cq": 16, "maxrate": "40M", "bufsize": "80M",
                   "audio_bitrate": "256k"}
DEFAULT_RATE_TOL = 0.002        # 30.03 vs 30 is 0.1%; 30 vs 29.97 is 0.1% too,
                                # so this is deliberately tight enough to keep
                                # those two apart and force an explicit choice


def rel(p):
    return _env.resolve(p)


def probe(path):
    """(width, height, r_num, r_den, n_frames, duration)."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets",
         "-show_entries",
         "stream=width,height,r_frame_rate,avg_frame_rate,nb_read_packets"
         ":format=duration", "-of", "json", path],
        env=ENV, capture_output=True, text=True)
    if out.returncode:
        sys.exit("ffprobe failed on %s\n%s" % (path, out.stderr.strip()))
    j = json.loads(out.stdout)
    if not j.get("streams"):
        sys.exit("%s has no video stream" % _project.norm(path))
    s = j["streams"][0]
    num, den = (int(x) for x in s["r_frame_rate"].split("/"))
    n = int(s.get("nb_read_packets") or 0)
    dur = float(j.get("format", {}).get("duration") or 0.0)
    return int(s["width"]), int(s["height"]), num, den, n, dur


def real_fps(n_frames, duration, num, den):
    """What the tape actually delivers, not what it claims.

    A download or a phone export is routinely a little off nominal -- the a16z
    clip averaged 23.9765 against 24000/1001, and the phone here delivers
    30.034 against a claimed 30. The measured rate is what decides the route.
    """
    if duration > 0 and n_frames > 1:
        return n_frames / duration
    return num / float(den or 1)


def pick_target(probes, rates, tol):
    """The lowest rate every tape can reach without inventing frames.

    Candidates are the tapes' CLAIMED rates, not their measured ones. The
    measured rate is drift -- this phone delivers 30.034 against a claimed 30 --
    and taking drift as the target is how a clean 2:1 decimation stops looking
    like one: 59.933 / 30.034 is 1.9952, which misses 2 by more than the
    tolerance and gets the whole tape refused. Against a clean 30 both tapes
    land, one by regrid and one by decimate, which is the true answer.

    Lowest, because a rate below a tape's own is reachable by dropping frames
    and a rate above it is not reachable at all without inventing them.
    """
    cands = sorted({round(num / float(den or 1), 3)
                    for _, _, num, den, _, _ in probes})
    for t in cands:
        if all(route(f, t, tol)[0] != "refuse" for f in rates):
            return t
    return round(min(rates), 3)          # nothing works; let --list say why


def route(src_fps, tgt_fps, tol=DEFAULT_RATE_TOL):
    """('regrid'|'decimate'|'refuse', k) for getting src_fps onto tgt_fps."""
    if tgt_fps <= 0:
        return "refuse", 0
    if abs(src_fps - tgt_fps) / tgt_fps <= tol:
        return "regrid", 1
    k = src_fps / tgt_fps
    kr = int(round(k))
    if kr >= 2 and abs(k - kr) / kr <= tol:
        return "decimate", kr
    return "refuse", 0


def size_filter(sw, sh, tw, th):
    """scale-to-fit plus pad, so nothing is cropped away.

    force_original_aspect_ratio=decrease fits the whole frame inside the
    target and the pad fills what is left. A 16:9 source into a 16:9 grid pads
    by zero and costs nothing, so this is written once rather than branched.
    """
    return ("scale=%d:%d:force_original_aspect_ratio=decrease:flags=lanczos,"
            "pad=%d:%d:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1"
            % (tw, th, tw, th))


def plan_one(path, tgt_fps, tw, th, tol):
    """Everything decided about one tape, before anything is encoded."""
    sw, sh, num, den, n, dur = probe(path)
    fps = real_fps(n, dur, num, den)
    how, k = route(fps, tgt_fps, tol)
    out_n = n if how == "regrid" else (math.ceil(n / float(k)) if k else 0)
    return {"src": path, "w": sw, "h": sh, "n": n, "dur": dur,
            "claimed_fps": num / float(den or 1), "real_fps": fps,
            "how": how, "k": k, "out_n": out_n,
            "out_dur": out_n / float(tgt_fps) if tgt_fps else 0.0,
            "resize": (sw, sh) != (tw, th)}


def conform(p, dst, cfg, tgt_fps, tw, th):
    """Encode one tape onto the grid, then prove it landed there."""
    os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
    tmp = dst + ".part.mp4"

    # Frame index -> time on the target grid. Both routes end in the same
    # setpts, because after a select the surviving frames must still be laid
    # on the grid at integer positions rather than keeping their old stamps.
    if p["how"] == "decimate":
        vf = "select='not(mod(n\\,%d))'," % p["k"]
    else:
        vf = ""
    vf += "setpts=N/%g/TB," % tgt_fps
    vf += size_filter(p["w"], p["h"], tw, th)

    cmd = (["ffmpeg", "-hide_banner", "-nostats", "-loglevel", "warning",
            "-i", p["src"], "-vf", vf,
            "-fps_mode", "passthrough",
            "-video_track_timescale", str(int(round(tgt_fps * 1000)))]
           + _encode.video_args(cfg) + _encode.audio_args(cfg, rate=SR)
           + ["-movflags", "+faststart", "-y", tmp])
    r = subprocess.run(cmd, capture_output=True, text=True, env=ENV)
    if r.returncode != 0:
        sys.exit("conform failed for %s:\n%s"
                 % (_project.norm(p["src"]), (r.stderr or "")[-3000:]))

    gw, gh, _, _, gn, _ = probe(tmp)
    if (gw, gh) != (tw, th):
        os.remove(tmp)
        sys.exit("conform produced %dx%d, wanted %dx%d -- %s left alone"
                 % (gw, gh, tw, th, _project.norm(p["src"])))
    # The assertion is the point. A route that silently duplicated or dropped
    # is exactly what makes a frame-addressed cut wrong, and it is invisible
    # in the picture.
    if gn != p["out_n"]:
        os.remove(tmp)
        sys.exit("conform produced %d frames, the %s route predicted %d. The "
                 "grid is wrong and nothing downstream can be trusted."
                 % (gn, p["how"], p["out_n"]))
    shutil.move(tmp, dst)
    return gn


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--manifest", help="an anglecut manifest; conforms its "
                                       "`cameras` in place of --tapes")
    ap.add_argument("--tapes", nargs="+", help="recordings to conform")
    ap.add_argument("--outdir", help="default projects/<id>/tapes")
    ap.add_argument("--id", help="project id, for the record")
    ap.add_argument("--fps", type=float, default=None,
                    help="target rate; default: the lowest real rate among "
                         "the tapes, because that is the only one every tape "
                         "can reach without inventing frames")
    ap.add_argument("--size", default=None, metavar="WxH",
                    help="target frame size; default: the largest width and "
                         "height present, so no tape is downscaled")
    ap.add_argument("--rate-tol", type=float, default=DEFAULT_RATE_TOL)
    ap.add_argument("--list", action="store_true",
                    help="print what each tape becomes and stop")
    ap.add_argument("--force", action="store_true",
                    help="re-conform tapes whose output already exists")
    _env.add_workspace_arg(ap)
    args = ap.parse_args()
    _env.set_workspace(args.workspace)

    m, pid = None, args.id
    tapes, ids = [], []
    if args.manifest:
        with open(rel(args.manifest), encoding="utf-8") as f:
            m = json.load(f)
        pid = pid or _project.project_id(m, rel(args.manifest))
        for c in m["cameras"]:
            tapes.append(rel(c["file"]))
            ids.append(c["id"])
    elif args.tapes:
        tapes = [rel(t) for t in args.tapes]
        ids = [os.path.splitext(os.path.basename(t))[0] for t in tapes]
    else:
        sys.exit("pass --manifest or --tapes")
    for t in tapes:
        if not os.path.exists(t):
            sys.exit("no such tape: %s" % _project.norm(t))

    probes = [probe(t) for t in tapes]
    rates = [real_fps(n, dur, num, den) for _, _, num, den, n, dur in probes]
    # The lowest rate is the only one every tape reaches by dropping frames
    # rather than by inventing them, and the largest size is the only one that
    # downscales nothing. Both are overridable; neither is a guess.
    tgt_fps = args.fps if args.fps else pick_target(probes, rates, args.rate_tol)
    if args.size:
        tw, th = (int(x) for x in args.size.lower().split("x"))
    else:
        tw = max(p[0] for p in probes)
        th = max(p[1] for p in probes)
    tw, th = tw // 2 * 2, th // 2 * 2          # yuv420p chroma wants even

    outdir = rel(args.outdir) if args.outdir else (
        os.path.join(_project.projects_dir(), pid, "tapes") if pid else None)
    if not outdir:
        sys.exit("pass --outdir, or --id/--manifest so one can be derived")

    plans = [plan_one(t, tgt_fps, tw, th, args.rate_tol) for t in tapes]

    print("target grid: %dx%d @ %g fps   ->  %s"
          % (tw, th, tgt_fps, _project.norm(outdir)))
    print("encoder: %s" % _encode.describe(_encode.resolve(dict(
        DEFAULT_CONFORM, **((m or {}).get("conform") or {})))))
    print("")
    print("  tape           source           claimed  real     route       out")
    refused = []
    for cid, p in zip(ids, plans):
        print("  %-14s %4dx%-4d %5df  %7.3f  %7.3f  %-11s %5df %6.2fs%s"
              % (cid[:14], p["w"], p["h"], p["n"], p["claimed_fps"], p["real_fps"],
                 p["how"] + ("/%d" % p["k"] if p["how"] == "decimate" else ""),
                 p["out_n"], p["out_dur"],
                 "  (letterboxed)" if p["resize"] else ""))
        if p["how"] == "refuse":
            refused.append((cid, p))

    if refused:
        print("")
        for cid, p in refused:
            print("  REFUSED %s: %.3f fps -> %g fps is neither the same rate "
                  "nor an integer multiple of it. Reaching it means dropping "
                  "or duplicating frames unevenly, which is what makes a "
                  "frame-addressed cut wrong. Pick --fps %g, or re-shoot the "
                  "tape on the grid." % (cid, p["real_fps"], tgt_fps,
                                         round(min(rates), 3)))
        if not args.list:
            sys.exit(1)

    if args.list:
        print("\n--list: nothing encoded")
        return

    cfg = _encode.resolve(dict(DEFAULT_CONFORM, **((m or {}).get("conform") or {})))
    print("")
    outs = {}
    for cid, p in zip(ids, plans):
        dst = os.path.join(outdir, "%s.mp4" % cid)
        outs[cid] = dst
        if os.path.exists(dst) and not args.force:
            print("  %s already conformed -- --force to redo" % cid)
            continue
        print("  conforming %s (%s) ..." % (cid, p["how"]))
        n = conform(p, dst, cfg, tgt_fps, tw, th)
        print("    %s  %d frames  %.2fs" % (_project.norm(dst), n,
                                            n / float(tgt_fps)))

    if pid:
        _project.record(pid, "conform", script=__file__, argv=sys.argv[1:],
                        note="conformed %d tapes to %dx%d @ %g fps"
                             % (len(tapes), tw, th, tgt_fps))
    print("\nconformed %d tapes to %dx%d @ %g fps"
          % (len(tapes), tw, th, tgt_fps))
    print("point the anglecut manifest's `cameras` at %s"
          % _project.norm(outdir))


if __name__ == "__main__":
    main()
