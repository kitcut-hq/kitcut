#!/usr/bin/env python
"""Cut one film out of N synchronised cameras, switching full frame, in one pass.

The other half of the round-trip test, and the general multicam cutter this repo
did not have: screencast-cut.py composites two tracks into one picture, this one
chooses BETWEEN tracks. Given the tapes, the offsets sync-audio.py measured, and
a plan saying which angle covers which stretch, it renders the programme.

Where programme frame zero sits on each tape is a separate question from how far
apart the tapes are, and sync cannot answer it -- offsets are relative. Two ways
to settle it, both in the manifest under `anchor`:

  picture_start  measured. Find the first frame on each tape whose picture
                 MOVES, and subtract the programme frame at which the plan
                 first uses that angle. Exact to the frame, and it uses only
                 the tape and the plan.
  <frames>       declared, per camera: the editor's in-point, which is what a
                 real cut uses. A tape with footage running before the film
                 starts has no motion onset to find.

Whichever is used, the anchors must reproduce the audio offsets: anchor(c)
minus anchor(reference) is the stagger sync-audio.py measured from the sound,
and the two are asserted against each other before a frame is encoded. Picture
and sound agreeing to the frame is the evidence that the film will land right;
everything after it is arithmetic.

The audio comes whole from ONE tape. Every camera carries the same sound, so a
programme cut from them has no audio joins at all -- one atrim across the span,
no concat, nothing to click.

  --list   print the plan, the anchors and the runtime; encode nothing
  (none)   render

Invoke as:  python scripts/angle-cut.py --manifest projects/<id>/anglecut.json
"""
import sys, os, json, argparse, subprocess, shutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import
from importlib import import_module  # noqa: E402

import _progress  # noqa: E402
import _project  # noqa: E402

_shots = import_module("shot-detect")   # hyphen: not importable by name

ROOT = _env.ROOT
ENV = _env.ENV

DEFAULT_RENDER = {"encoder": "h264_nvenc", "preset": "p5", "cq": 18,
                  "maxrate": "40M", "bufsize": "80M", "audio_bitrate": "192k"}
DEFAULT_ANCHOR = {"still": 0.0015, "tolerance_frames": 1}


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, capture_output=True, text=True,
                          env=ENV, **kw)


def hhmmss(t):
    return "%d:%05.2f" % (int(t) // 60, t % 60)


def rel(p):
    return p if os.path.isabs(p) else os.path.join(ROOT, p)


def probe_video(path):
    out = run(["ffprobe", "-v", "error", "-select_streams", "v:0",
               "-show_entries", "stream=width,height,r_frame_rate",
               "-of", "json", path]).stdout
    s = json.loads(out)["streams"][0]
    num, den = (int(x) for x in s["r_frame_rate"].split("/"))
    return int(s["width"]), int(s["height"]), num, den


def count_frames(path):
    out = run(["ffprobe", "-v", "error", "-select_streams", "v:0",
               "-count_packets", "-show_entries", "stream=nb_read_packets",
               "-of", "csv=p=0", path]).stdout
    return int(out.strip().rstrip(","))


def peak_db(path):
    p = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path,
                        "-vn", "-af", "volumedetect", "-f", "null", "-"],
                       capture_output=True, text=True, env=ENV)
    for line in (p.stderr or "").splitlines():
        if "max_volume:" in line:
            try:
                return float(line.split("max_volume:")[1].split()[0])
            except (IndexError, ValueError):
                return None
    return None


def rotation(path):
    out = run(["ffprobe", "-v", "error", "-select_streams", "v:0",
               "-show_entries", "stream_side_data=rotation",
               "-of", "default=noprint_wrappers=1:nokey=1", path]).stdout
    return out.strip()


def picture_start(path, w, h, still):
    """Where the leading held frame ends: (first moving frame, floor, margin).

    The opening run of the tape is one frame held, so it is looked for as a RUN
    that breaks, not as the first frame anywhere above a threshold. Scanning
    the whole tape for a threshold crossing finds whatever the loosest moment
    of the film happens to be; stopping at the end of the still run cannot.

    Measured on this fixture: held frames score 0.0000 (worst 0.0005), and the
    frame that breaks the run scores 0.0032. The default sits in that gap, and
    the margin is reported so it stays a decision rather than a hope.

    Caller beware of the off-by-one: the held frame IS the tape's first live
    frame, repeated. So the first frame that DIFFERS is the second live one,
    and whoever wants the anchor subtracts one.
    """
    diff, _ = _shots.scan(path, w, h)
    i = 1
    while i < len(diff) and diff[i] <= still:
        i += 1
    if i >= len(diff):
        return None, 0.0, 0.0
    floor = float(max(diff[1:i])) if i > 1 else 0.0
    return i, floor, float(diff[i])


def load_plan(m):
    """[(camera, start, end)] in programme frames, from the manifest or a
    shot list read off a finished film."""
    if m.get("plan"):
        return [(p["camera"], int(p["start"]), int(p["end"])) for p in m["plan"]]
    with open(rel(m["plan_from"]), encoding="utf-8") as f:
        sh = json.load(f)
    return [(s["camera"], int(s["start"]), int(s["end"])) for s in sh["shots"]]


def build_graph(plan, cams, anchors, idx, audio_from, a_start, a_end):
    """Per-segment trim from the tape that covers it, one concat, one atrim.

    Each camera's segments are monotonically increasing in its own time, so a
    later segment discards frames while an earlier one is still playing and
    nothing queues up behind the concat -- the same property that keeps
    screencast-cut.py's graph cheap, and it survives the extra inputs.
    """
    taps = {}
    for c, _, _ in plan:
        taps[c] = taps.get(c, 0) + 1
    ch, cursor = [], {}
    for c in cams:
        n = taps.get(c, 0)
        if n == 1:
            ch.append("[%d:v]null[x%s_0]" % (idx[c], c))
        elif n > 1:
            ch.append("[%d:v]split=%d%s"
                      % (idx[c], n, "".join("[x%s_%d]" % (c, i) for i in range(n))))
        cursor[c] = 0
    segs = []
    for i, (c, a, b) in enumerate(plan):
        k = cursor[c]
        cursor[c] += 1
        ch.append("[x%s_%d]trim=start_frame=%d:end_frame=%d,setpts=PTS-STARTPTS[v%d]"
                  % (c, k, anchors[c] + a, anchors[c] + b, i))
        segs.append("[v%d]" % i)
    if len(segs) == 1:
        ch.append("[v0]null[vout]")
    else:
        ch.append("%sconcat=n=%d:v=1:a=0[vout]" % ("".join(segs), len(segs)))
    ch.append("[%d:a]atrim=start_sample=%d:end_sample=%d,asetpts=PTS-STARTPTS[aout]"
              % (idx[audio_from], a_start, a_end))
    return ";".join(ch)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--list", action="store_true",
                    help="print the plan and the anchors, encode nothing")
    ap.add_argument("--out", help="default <outdir>/<id>.mp4")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    with open(rel(args.manifest), encoding="utf-8") as f:
        m = json.load(f)
    pid = _project.project_id(m, rel(args.manifest))
    render = dict(DEFAULT_RENDER, **(m.get("render") or {}))
    acfg = dict(DEFAULT_ANCHOR, **(m.get("anchor_cfg") or {}))

    cams = [c["id"] for c in m["cameras"]]
    files = {c["id"]: rel(c["file"]) for c in m["cameras"]}
    for c in cams:
        if not os.path.exists(files[c]):
            sys.exit("no such tape: %s" % _project.norm(files[c]))
    ref = m.get("reference", cams[0])
    audio_from = m.get("audio_from", ref)

    with open(rel(m["sync"]), encoding="utf-8") as f:
        sync = json.load(f)
    off = {t["id"]: t["offset_frames"] for t in sync["tracks"]}
    if sync.get("reference") != ref:
        sys.exit("the sync was measured against %s but the manifest says %s"
                 % (sync.get("reference"), ref))

    plan = load_plan(m)
    used = sorted({c for c, _, _ in plan})
    for c in used:
        if c not in files:
            sys.exit("the plan uses %s, which is not one of the cameras" % c)
    w, h, num, den = probe_video(files[ref])
    spf = den / float(num)
    n_prog = max(b for _, _, b in plan)

    anchors, margins, how = {}, {}, m.get("anchor", "picture_start")
    if how == "picture_start":
        first = {}
        for c, a, _ in plan:
            first[c] = min(first.get(c, a), a)
        for c in cams:
            if c not in first:
                anchors[c] = None
                continue
            i, floor, jump = picture_start(files[c], w, h, acfg["still"])
            if i is None:
                sys.exit("%s never moves: it cannot anchor itself, declare "
                         "`anchor` per camera instead" % c)
            if i == 1:
                sys.exit("%s moves from its very first frame, so it does not "
                         "open on a held frame -- declare `anchor` per camera"
                         % c)
            anchors[c] = i - first[c] - 1     # the held frame is the first live one
            margins[c] = (floor, jump)
    elif isinstance(how, dict):
        anchors = {c: int(how[c]) for c in cams if c in how}
    else:
        sys.exit("anchor must be \"picture_start\" or a map of camera to frame")

    print("%d tapes, reference %s, %dx%d %d/%d, programme %d frames (%s)"
          % (len(cams), ref, w, h, num, den, n_prog, hhmmss(n_prog * spf)))
    print("\n  cam   anchor   vs sync   tape frames   still/moving   covers")
    bad = []
    for c in cams:
        if anchors.get(c) is None:
            print("  %-5s      -         -                            "
                  "unused by the plan" % c)
            continue
        mine = []
        want = off.get(c)
        got = anchors[c] - anchors[ref]
        drift = None if want is None else got - want
        tot = count_frames(files[c])
        need = anchors[c] + n_prog
        if anchors[c] < 0 or need > tot:
            mine.append("%s: the plan needs frames %d-%d but the tape has %d"
                        % (c, anchors[c], need, tot))
        if drift is not None and abs(drift) > acfg["tolerance_frames"]:
            mine.append("%s: the picture says %+d frames from %s, the sound "
                        "says %+.2f -- they must agree" % (c, got, ref, want))
        mg = margins.get(c)
        print("  %-5s %6d   %+8s %13d   %13s   %s"
              % (c, anchors[c], "-" if drift is None else "%+d fr" % drift, tot,
                 "-" if not mg else "%.4f/%.4f" % mg,
                 "ok" if not mine else "FAILS"))
        bad += mine
    if bad:
        for b in bad:
            print("  !! %s" % b)
        sys.exit("the tapes and the plan do not line up; nothing rendered")

    print("\n   #  cam      start       end     len   tape frames")
    for i, (c, a, b) in enumerate(plan):
        print("  %2d  %-5s %8s %9s %7.2f   %6d-%-6d"
              % (i, c, hhmmss(a * spf), hhmmss(b * spf), (b - a) * spf,
                 anchors[c] + a, anchors[c] + b))
    total = sum(b - a for _, a, b in plan)
    switches = sum(1 for i in range(1, len(plan)) if plan[i][0] != plan[i - 1][0])
    print("\n%d segments, %d switches, %d frames (%s) of film"
          % (len(plan), switches, total, hhmmss(total * spf)))
    if total != n_prog:
        print("  note: the plan tiles %d frames but ends at %d -- it has holes "
              "or overlaps" % (total, n_prog))
    if args.list:
        return

    sr = sync.get("rate") and None
    a_rate = 48000
    if (a_rate * den) % num:
        sys.exit("%d Hz does not divide evenly into %d/%d fps" % (a_rate, num, den))
    aspf = a_rate * den // num
    a0 = anchors[audio_from] * aspf
    a1 = (anchors[audio_from] + n_prog) * aspf
    idx = {c: i for i, c in enumerate(cams)}
    graph = build_graph(plan, cams, anchors, idx, audio_from, a0, a1)

    outdir = rel(m.get("outdir", "projects/%s/outputs" % pid))
    os.makedirs(outdir, exist_ok=True)
    dst = rel(args.out) if args.out else os.path.join(outdir, "%s-anglecut.mp4" % pid)
    if os.path.exists(dst) and not args.force:
        sys.exit("%s exists -- pass --force to overwrite" % _project.norm(dst))
    tmp = dst + ".part.mp4"

    job = "anglecut-%s" % pid
    prog = _progress.begin(job, total * spf, os.path.relpath(dst, ROOT))
    cmd = ["ffmpeg", "-hide_banner", "-nostats", "-loglevel", "warning",
           "-progress", prog]
    for c in cams:
        cmd += ["-i", files[c]]
    cmd += ["-filter_complex", graph, "-map", "[vout]", "-map", "[aout]",
            "-r", "%d/%d" % (num, den), "-fps_mode", "cfr",
            "-video_track_timescale", str(num),
            "-c:v", render["encoder"], "-preset", render["preset"],
            "-rc", "vbr", "-cq", str(render["cq"]), "-b:v", "0",
            "-maxrate", render["maxrate"], "-bufsize", render["bufsize"],
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", render["audio_bitrate"],
            "-ar", str(a_rate), "-ac", "2",
            "-movflags", "+faststart", "-y", tmp]
    print("\nrendering %s" % _project.norm(dst))
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, env=ENV)
    finally:
        _progress.end(job)
    if p.returncode != 0:
        sys.exit("render failed:\n%s" % (p.stderr or "")[-4000:])

    got = count_frames(tmp)
    if got != total:
        sys.exit("rendered %d frames, planned %d -- leaving %s in place"
                 % (got, total, _project.norm(tmp)))
    gw, gh, gn, gd = probe_video(tmp)
    if (gw, gh) != (w, h):
        sys.exit("rendered %dx%d, want %dx%d" % (gw, gh, w, h))
    if (gn, gd) != (num, den):
        sys.exit("rendered %d/%d fps, want %d/%d" % (gn, gd, num, den))
    if rotation(tmp):
        sys.exit("the output carries a rotation of %s" % rotation(tmp))
    pk = peak_db(tmp)
    if pk is None or pk < -60:
        sys.exit("the output has no audio (peak %s dB)" % pk)
    shutil.move(tmp, dst)
    print("done: %d frames, %s, audio peak %.1f dB"
          % (got, hhmmss(total * spf), pk))
    print(os.path.abspath(dst))

    _project.record(pid, "anglecut", out=dst, script=__file__, argv=sys.argv[1:],
                    kind="anglecut", manifest=args.manifest,
                    sidecars={"sync": rel(m["sync"])},
                    burned=["%d segments switching between %d cameras full frame"
                            % (len(plan), len(used)),
                            "audio taken whole from %s -- no joins" % audio_from,
                            "anchored by %s" % (how if isinstance(how, str)
                                                else "declared frames")])


if __name__ == "__main__":
    main()
