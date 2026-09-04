#!/usr/bin/env python
"""Un-edit a finished multicam video: rebuild the raw tapes it was cut from.

The fixture half of the round-trip test. Given a programme and the shot list
read back off it by shot-detect.py, this writes one "camera raw" per angle --
each covering the WHOLE shoot, the way a real camera does, rather than the
handful of clips that angle contributed to the finished cut.

What a raw looks like, and why:

  live      where the finished cut used this angle, the real frames
  frozen    everywhere else, its last live frame held. A real second camera is
            rolling through the parts you did not use; we do not have that
            footage, so the picture stops while the clock does not. Freezing is
            the honest stand-in: it keeps the frame count and the timeline
            exact, and it is visibly not real footage, which matters --
            anything that scores this test by looking for MOTION would be
            reading the answer key. See the skill.
  audio     the whole programme's sound, on every raw, offset by that camera's
            own start. Cameras fed from one recorder; it is also what gives
            sync-audio.py something to measure.
  stagger   each raw starts and stops at its own moment, because nobody hits
            record on four cameras simultaneously. The pads are drawn from a
            seeded generator, so the same manifest rebuilds the same tapes.

Frames, never seconds. Every boundary is a frame index on the programme's own
grid, and the audio delay is a SAMPLE count -- exact where 48 kHz divides the
frame time (2002 a frame at 24000/1001; every integer rate), and rounded to the
nearest sample where it cannot (29.97), an error of ten microseconds that
cannot accumulate because boundaries are computed from frame zero.

Conforming comes first. A file off the internet is usually a little variable,
and a one-frame join error must not be able to hide behind timestamp jitter, so
`--conform-only` rewrites the source onto a strict CFR grid frame-for-frame
(setpts by frame index; no fps filter, which would duplicate or drop). The
conformed programme -- not the download -- is what the raws are built from and
what the finished re-cut is scored against.

  --conform-only   write temp/program.mp4 and stop
  --plan           print the tape layout and what it would cost, encode nothing
  (none)           build the raws and their truth sidecar

Invoke as:  python scripts/split-cameras.py --manifest projects/<id>/multicam-sim.json
"""
import sys, os, json, argparse, subprocess, shutil, random

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import
import _encode  # noqa: E402 -- the one place encoder keys are chosen

from importlib import import_module  # noqa: E402

import _progress  # noqa: E402
import _project  # noqa: E402

_shots = import_module("shot-detect")   # hyphen: not importable by name

ROOT = _env.ROOT
ENV = _env.ENV

DEFAULT_STAGGER = {"seed": 1, "head_s": [1.0, 6.0], "tail_s": [0.5, 4.0]}
# No "encoder": _encode picks one this machine can actually run, and a
# manifest that names one overrides it. "speed" is family-neutral.
DEFAULT_CONFORM = {"speed": 5, "cq": 16,
                   "maxrate": "40M", "bufsize": "80M", "audio_bitrate": "256k"}
DEFAULT_RENDER = {"speed": 5, "cq": 16,
                  "maxrate": "40M", "bufsize": "80M", "audio_bitrate": "192k"}
DEFAULT_VERIFY = {"match_max": 0.020, "samples_per_span": 12, "peak_db": -60}
SR = 48000                      # every raw is resampled to this


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, capture_output=True, text=True,
                          env=ENV, **kw)


def hhmmss(t):
    return "%d:%05.2f" % (int(t) // 60, t % 60)


def rel(p):
    return _env.resolve(p)


def probe_video(path):
    out = run(["ffprobe", "-v", "error", "-select_streams", "v:0",
               "-show_entries", "stream=width,height,r_frame_rate",
               "-of", "json", path]).stdout
    s = json.loads(out)["streams"][0]
    num, den = (int(x) for x in s["r_frame_rate"].split("/"))
    return int(s["width"]), int(s["height"]), num, den


def count_frames(path):
    """Packets, not decoded frames: same answer, seconds instead of minutes."""
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


def layout(live, n_frames, head, tail):
    """How the tape is tiled: (raw_start, raw_end, programme_frame_or_None).

    A live stretch maps frame to frame; a frozen one names the single
    programme frame being held. Returned in order and gapless, so the caller
    can assert it tiles the whole tape -- the check that catches a filler
    length computed one way and an encode that did it another.
    """
    out = []
    n = len(live)
    out.append((0, head + live[0][0], ("hold", live[0][0])))
    for i, (a, b) in enumerate(live):
        out.append((head + a, head + b, ("live", a)))
        end = (live[i + 1][0] if i + 1 < n else n_frames + tail)
        if end > b:
            out.append((head + b, head + end, ("hold", b - 1)))
    return [(x, y, k) for x, y, k in out if y > x]


def sample_frames(a, b, k):
    """Both edges always, then spread the rest: an off-by-one shows up at a
    boundary long before it shows up in the middle of a shot."""
    if b - a <= k:
        return list(range(a, b))
    inner = [a + int(round(i * (b - a - 1) / float(k - 1))) for i in range(k)]
    return sorted(set([a, b - 1] + inner))


def gaps_of(live, n_frames):
    """The frozen stretches between live spans, in programme frames."""
    out, cur = [], 0
    for a, b in live:
        if a > cur:
            out.append((cur, a))
        cur = b
    if n_frames > cur:
        out.append((cur, n_frames))
    return out


def conform(src, dst, cfg, fps_num, fps_den):
    """Rewrite onto a strict CFR grid, frame for frame.

    setpts by frame INDEX, not the fps filter: fps= would duplicate or drop to
    hit its target, and a frame count that changed under us is exactly the
    thing this file exists to rule out.
    """
    os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
    tmp = dst + ".part.mp4"
    cmd = ["ffmpeg", "-hide_banner", "-nostats", "-loglevel", "warning",
           "-i", src,
           "-vf", "setpts=N*%d/%d/TB" % (fps_den, fps_num),
           "-fps_mode", "passthrough", "-video_track_timescale", str(fps_num),
           ] + _encode.video_args(cfg) + _encode.audio_args(cfg, rate=SR) + [
           "-movflags", "+faststart", "-y", tmp]
    p = subprocess.run(cmd, capture_output=True, text=True, env=ENV)
    if p.returncode != 0:
        sys.exit("conform failed:\n%s" % (p.stderr or "")[-3000:])
    want, got = count_frames(src), count_frames(tmp)
    if got != want:
        sys.exit("conform changed the frame count: %d -> %d. The grid is wrong; "
                 "nothing downstream can be trusted." % (want, got))
    shutil.move(tmp, dst)
    return dst


def samples_at(frames, fps_num, fps_den):
    """The audio sample sitting at a frame boundary, at SR.

    Exact wherever SR divides the frame time -- 2002 samples a frame at
    24000/1001, and every integer rate. At a rate where it cannot (29.97:
    1601.6 a frame) the boundary rounds to the NEAREST sample, an error of at
    most half a sample -- ten microseconds, three-and-a-half thousand times
    smaller than a frame and far below anything the harness asserts. It cannot
    accumulate, because every boundary is computed from frame zero rather than
    by summing per-frame deltas; an earlier version refused non-dividing rates
    outright, which was purity at the price of refusing every NTSC video.
    """
    return int(round(frames * SR * fps_den / float(fps_num)))


def build_graph(live, n_frames, head, tail, fps_num, fps_den):
    """One camera's tape as a filtergraph.

    Each live span is a branch that carries the freeze FOLLOWING it, so the
    branch count is the shot count and not twice it. The first branch also
    carries everything before it -- the head pad and the wait until this angle
    was first used are the same held frame.
    """
    ch, segs = [], []
    n = len(live)
    ch.append("[0:v]split=%d%s" % (n, "".join("[s%d]" % i for i in range(n))))
    for i, (a, b) in enumerate(live):
        pre = (head + a) if i == 0 else 0
        post = (live[i + 1][0] - b) if i + 1 < n else (n_frames - b + tail)
        pad = []
        if pre:
            pad.append("start_mode=clone:start=%d" % pre)
        if post:
            pad.append("stop_mode=clone:stop=%d" % post)
        f = "[s%d]trim=start_frame=%d:end_frame=%d,setpts=PTS-STARTPTS" % (i, a, b)
        if pad:
            f += ",tpad=%s,setpts=PTS-STARTPTS" % ":".join(pad)
        ch.append(f + "[v%d]" % i)
        segs.append("[v%d]" % i)
    if n == 1:
        ch.append("[v0]null[vout]")
    else:
        ch.append("%sconcat=n=%d:v=1:a=0[vout]" % ("".join(segs), n))

    total = head + n_frames + tail
    ch.append("[0:a]aresample=%d,aformat=sample_fmts=fltp:sample_rates=%d:"
              "channel_layouts=stereo,adelay=%dS:all=1,apad,"
              "atrim=end_sample=%d,asetpts=PTS-STARTPTS[aout]"
              % (SR, SR, samples_at(head, fps_num, fps_den),
                 samples_at(total, fps_num, fps_den)))
    return ";".join(ch), total


def render_raw(program, dst, live, n_frames, head, tail, cfg, fps_num, fps_den,
               job):
    graph, total = build_graph(live, n_frames, head, tail, fps_num, fps_den)
    tmp = dst + ".part.mp4"
    prog = _progress.begin(job, total * fps_den / float(fps_num),
                           os.path.relpath(dst, ROOT))
    cmd = ["ffmpeg", "-hide_banner", "-nostats", "-loglevel", "warning",
           "-progress", prog, "-i", program,
           "-filter_complex", graph, "-map", "[vout]", "-map", "[aout]",
           "-r", "%d/%d" % (fps_num, fps_den), "-fps_mode", "cfr",
           "-video_track_timescale", str(fps_num),
           ] + _encode.video_args(cfg) + _encode.audio_args(cfg, rate=SR) + [
           "-movflags", "+faststart", "-y", tmp]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, env=ENV)
    finally:
        _progress.end(job)
    if p.returncode != 0:
        sys.exit("render failed for %s:\n%s" % (dst, (p.stderr or "")[-3000:]))
    return tmp, total


def verify_raw(tmp, want_frames, want_dims, live, n_frames, head, tail,
               fps_num, fps_den, v, psigs):
    """Everything that must be true of a tape before it is allowed to exist.

    The check that matters is not "is it static here" but "is THIS frame the
    programme frame it is supposed to be showing". Every sampled frame is
    fingerprinted and compared against the programme frame the layout names
    for it, live and held alike. That catches a filler one frame long, a
    segment pasted at the wrong offset, and a tape that drifts halfway
    through -- none of which a freeze detector would notice.

    Freeze detection was tried first and abandoned: NVENC re-encodes cloned
    frames independently, so a held frame differs from itself by up to 3/255,
    and freezedetect at the -60 dB this repo uses for screen recordings finds
    nothing at all. See the gotcha in README.
    """
    problems = []
    got = count_frames(tmp)
    if got != want_frames:
        problems.append("frame count %d, want %d" % (got, want_frames))
    w, h, num, den = probe_video(tmp)
    if (w, h) != want_dims:
        problems.append("dimensions %dx%d, want %dx%d" % (w, h, *want_dims))
    if (num, den) != (fps_num, fps_den):
        problems.append("frame rate %d/%d, want %d/%d" % (num, den, fps_num, fps_den))
    pk = peak_db(tmp)
    if pk is None or pk < v["peak_db"]:
        problems.append("audio peak %s dB" % pk)

    tiles = layout(live, n_frames, head, tail)
    tiled = sum(y - x for x, y, _ in tiles)
    if tiled != want_frames:
        problems.append("the layout tiles %d frames but the tape is %d"
                        % (tiled, want_frames))
    for (x1, y1, _), (x2, _, _) in zip(tiles, tiles[1:]):
        if y1 != x2:
            problems.append("layout is not gapless at frame %d" % y1)

    _, sigs = _shots.scan(tmp, w, h)
    if len(sigs) != want_frames:
        problems.append("decoded %d frames, want %d" % (len(sigs), want_frames))
        return problems, 0.0, 0.0

    worst = {"live": (0.0, None), "hold": (0.0, None)}
    for x, y, (kind, pf) in tiles:
        for i in sample_frames(x, y, v["samples_per_span"]):
            want = psigs[pf if kind == "hold" else pf + (i - x)]
            d = _shots.distance(sigs[i], want)
            if d > worst[kind][0]:
                worst[kind] = (d, i)
    for kind in ("live", "hold"):
        d, i = worst[kind]
        if d > v["match_max"]:
            problems.append("%s frame %d is not the programme frame it should "
                            "be (fingerprint distance %.4f > %.4f)"
                            % (kind, i, d, v["match_max"]))
    return problems, worst["live"][0], worst["hold"][0]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--conform-only", action="store_true",
                    help="write the CFR programme and stop")
    ap.add_argument("--plan", action="store_true",
                    help="print the tape layout and its cost, encode nothing")
    ap.add_argument("--only", help="build just this camera id")
    ap.add_argument("--force", action="store_true", help="overwrite existing raws")
    args = ap.parse_args()

    with open(rel(args.manifest), encoding="utf-8") as f:
        m = json.load(f)
    pid = _project.project_id(m, rel(args.manifest))
    stagger = dict(DEFAULT_STAGGER, **(m.get("stagger") or {}))
    conf_cfg = _encode.resolve(dict(DEFAULT_CONFORM, **(m.get("conform") or {})))
    render = _encode.resolve(dict(DEFAULT_RENDER, **(m.get("render") or {})))
    v = dict(DEFAULT_VERIFY, **(m.get("verify") or {}))

    src = rel(m["source"])
    program = rel(m.get("program", "projects/%s/temp/program.mp4" % pid))
    _, _, fps_num, fps_den = probe_video(src)

    if args.conform_only or not os.path.exists(program):
        if os.path.exists(program) and not args.force and args.conform_only:
            print("programme already conformed: %s" % _project.norm(program))
        else:
            print("conforming %s -> %s (%d/%d)"
                  % (m["source"], _project.norm(program), fps_num, fps_den))
            conform(src, program, conf_cfg, fps_num, fps_den)
            print("  %d frames, frame for frame" % count_frames(program))
            _project.record(pid, "conform", script=__file__, argv=sys.argv[1:],
                            note="CFR %d/%d programme from %s"
                                 % (fps_num, fps_den, m["source"]))
    if args.conform_only:
        return

    with open(rel(m["shots"]), encoding="utf-8") as f:
        shots = json.load(f)
    n_frames = shots["n_frames"]
    got = count_frames(program)
    if got != n_frames:
        sys.exit("the shot list was read off %d frames but the programme has %d "
                 "-- re-run shot-detect.py on %s"
                 % (n_frames, got, _project.norm(program)))
    w, h, num, den = probe_video(program)
    spf = den / float(num)

    cams = [c["id"] for c in shots["cameras"]]
    live = {c: [(s["start"], s["end"]) for s in shots["shots"] if s["camera"] == c]
            for c in cams}

    rnd = random.Random(stagger["seed"])
    pads = {}
    for c in cams:                                  # order is stable: sorted ids
        head = int(round(rnd.uniform(*stagger["head_s"]) / spf))
        tail = int(round(rnd.uniform(*stagger["tail_s"]) / spf))
        pads[c] = (head, tail)

    outdir = rel(m.get("outdir", "projects/%s/raws" % pid))
    print("programme %s  %dx%d  %d frames  %s  (%d/%d)"
          % (_project.norm(program), w, h, n_frames, hhmmss(n_frames * spf),
             num, den))
    print("\n  cam    head    tail    total  frames   live  frozen  shots")
    for c in cams:
        head, tail = pads[c]
        total = head + n_frames + tail
        lf = sum(b - a for a, b in live[c])
        print("  %-5s %6.2f  %6.2f  %7s  %6d  %5.1f%%  %5.1f%%  %5d"
              % (c, head * spf, tail * spf, hhmmss(total * spf), total,
                 100.0 * lf / total, 100.0 * (total - lf) / total, len(live[c])))
    if args.plan:
        print("\n  encoder: %s" % _encode.describe(render))
        print("  conform: %s" % _encode.describe(conf_cfg))
        print("\n  cam   #   live span (programme time)        frozen after")
        for c in cams:
            gaps = gaps_of(live[c], n_frames)
            for i, (a, b) in enumerate(live[c]):
                nxt = next((y - x for x, y in gaps if x == b), 0)
                print("  %-5s %2d  %8s %8s  %5d-%-5d  %8s"
                      % (c, i, hhmmss(a * spf), hhmmss(b * spf), a, b,
                         hhmmss(nxt * spf) if nxt else "-"))
        tot = sum(pads[c][0] + n_frames + pads[c][1] for c in cams)
        print("\nwould encode %d frames across %d tapes (%s of output)"
              % (tot, len(cams), hhmmss(tot * spf)))
        return

    os.makedirs(outdir, exist_ok=True)
    truth = {"_comment": "Ground truth for the multicam round-trip test, written "
                         "by scripts/split-cameras.py. Frame indices; live spans "
                         "are in PROGRAMME frames, pads are in that tape's own "
                         "frames. The pipeline under test must never read this "
                         "-- only the harness that scores it.",
             "id": pid, "program": _project.norm(program),
             "shots": _project.norm(rel(m["shots"])),
             "fps_num": num, "fps_den": den, "n_frames": n_frames,
             "width": w, "height": h, "sample_rate": SR,
             "stagger": stagger, "cameras": []}

    print("\nfingerprinting the programme once, to check every tape against")
    _, psigs = _shots.scan(program, w, h)
    if len(psigs) != n_frames:
        sys.exit("decoded %d frames from the programme, expected %d"
                 % (len(psigs), n_frames))

    built = []
    for c in cams:
        if args.only and c != args.only:
            continue
        head, tail = pads[c]
        dst = os.path.join(outdir, "%s.mp4" % c)
        if os.path.exists(dst) and not args.force:
            sys.exit("%s exists -- pass --force to rebuild" % _project.norm(dst))
        print("\n%s: %d + %d + %d frames" % (c, head, n_frames, tail))
        tmp, total = render_raw(program, dst, live[c], n_frames, head, tail,
                                render, num, den, "split-%s-%s" % (pid, c))
        problems, wlive, whold = verify_raw(tmp, total, (w, h), live[c],
                                            n_frames, head, tail, num, den,
                                            v, psigs)
        if problems:
            sys.exit("%s is wrong, leaving %s in place:\n  %s"
                     % (c, _project.norm(tmp), "\n  ".join(problems)))
        shutil.move(tmp, dst)
        print("  ok: %d frames; worst fingerprint distance from the programme "
              "%.4f live, %.4f held (limit %.4f)"
              % (total, wlive, whold, v["match_max"]))
        built.append(dst)
        truth["cameras"].append(
            {"id": c, "file": _project.norm(dst),
             "head_pad_frames": head, "tail_pad_frames": tail,
             "total_frames": total,
             "head_pad_s": round(head * spf, 6),
             "live_spans": [[a, b] for a, b in live[c]]})

    # Truth must describe EVERY camera: a --only rebuild keeps the existing
    # sidecar (same seed, same pads, so it stays true), and refuses to invent
    # one -- a truth listing a single camera would score the harness against
    # a fiction.
    tpath = os.path.join(os.path.dirname(rel(args.manifest)), "%s.truth.json" % pid)
    if args.only:
        if not os.path.exists(tpath):
            sys.exit("no %s -- build the full set once before rebuilding a "
                     "single tape" % _project.norm(tpath))
    else:
        with open(tpath, "w", encoding="utf-8") as f:
            json.dump(truth, f, indent=2)
            f.write("\n")
        print("\nwrote %s" % _project.norm(tpath))

    for dst in built:
        _project.record(pid, "sim-raw", out=dst, script=__file__,
                        argv=sys.argv[1:], kind="sim-raw",
                        manifest=args.manifest,
                        sidecars={"truth": tpath, "shots": rel(m["shots"])},
                        burned=["synthetic camera raw: real frames where the cut "
                                "used this angle, last live frame held elsewhere",
                                "programme audio, staggered by this tape's head pad"])


if __name__ == "__main__":
    main()
