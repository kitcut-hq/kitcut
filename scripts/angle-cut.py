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
_notes = import_module("debug-notes")

ROOT = _env.ROOT
ENV = _env.ENV

DEFAULT_RENDER = {"encoder": "h264_nvenc", "preset": "p5", "cq": 18,
                  "maxrate": "40M", "bufsize": "80M", "audio_bitrate": "192k"}
DEFAULT_ANCHOR = {"still": 0.0015, "tolerance_frames": 1, "min_margin": 3.0}
# Finding a HELD stretch is a stricter job than finding where the opening freeze
# ends, and wants its own numbers. Calibrated against stage 1, where the plan is
# the human's own edit and every frame therefore has real footage behind it, so
# any run reported there is a false positive: at 0.0015 over 10 frames cam1 alone
# produced 65, and at 0.0005 over a second all four tapes together produce 21 of
# 2796 -- the boundary frame and a few moments of someone sitting very still.
DEFAULT_DEBUG = {"held": 0.0005, "held_min_run_s": 1.0, "warn_frac": 0.2}


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

    Cached per (tape, size, threshold): every tape is scanned once for --list
    and again for the render, and on a thirteen-tape hour-long film that is
    half an hour of decoding to ask a question whose answer cannot change.
    """
    import hashlib
    ck = "%s|%d|%d|%.6f|%d" % (os.path.abspath(path), w, h, still,
                               int(os.path.getmtime(path)))
    cp = os.path.join(ROOT, "temp", "anglecut-anchor-%s.json"
                      % hashlib.md5(ck.encode("utf-8")).hexdigest()[:12])
    if os.path.exists(cp):
        try:
            with open(cp, encoding="utf-8") as f:
                v = json.load(f)
            return (v["i"], v["floor"], v["jump"])
        except Exception:
            pass
    diff, _ = _shots.scan(path, w, h)
    i = 1
    while i < len(diff) and diff[i] <= still:
        i += 1
    if i >= len(diff):
        got = (None, 0.0, 0.0)
    else:
        got = (i, float(max(diff[1:i])) if i > 1 else 0.0, float(diff[i]))
    try:
        os.makedirs(os.path.dirname(cp), exist_ok=True)
        with open(cp, "w", encoding="utf-8") as f:
            json.dump({"i": got[0], "floor": got[1], "jump": got[2],
                       "tape": _project.norm(path)}, f)
    except Exception:
        pass
    return got


def still_runs(diff, still, min_run):
    """Stretches of a tape where the picture is held rather than shot."""
    out, start = [], None
    for i in range(1, len(diff)):
        if diff[i] <= still:
            start = i if start is None else start
        else:
            if start is not None and i - start >= min_run:
                out.append((start, i))
            start = None
    if start is not None and len(diff) - start >= min_run:
        out.append((start, len(diff)))
    return out


def overlap(a, b, spans):
    return sum(max(0, min(b, y) - max(a, x)) for x, y in spans)


def debug_notes(plan, anchors, off, files, tapes, fps, spf, stage, plan_src,
                why, extra, warn_frac=0.2):
    """One note per segment: what the cut did here, and why.

    The freeze warning is the one that earns its place. A synthetic tape only
    carries real frames where the original editor used that angle, so a
    switcher that picks a different one is asking for footage that does not
    exist and gets a held frame. That is invisible in an average and obvious
    here, named on the picture at the moment it happens.
    """
    notes = []
    for i, (c, a, b) in enumerate(plan):
        ta, tb = anchors[c] + a, anchors[c] + b
        lines = ["ANGLE-CUT  %s  plan: %s" % (stage, plan_src),
                 "seg %02d/%02d   %s   %s-%s   %d frames"
                 % (i + 1, len(plan), c, hhmmss(a * spf), hhmmss(b * spf), b - a),
                 "why: %s" % (why.get(i) or "replaying the given plan"),
                 "tape %s  f%d-%d   anchor +%d   sync %+.2f fr"
                 % (os.path.basename(files[c]), ta, tb, anchors[c],
                    off.get(c, 0.0))]
        held = overlap(ta, tb, tapes.get(c, []))
        if held > warn_frac * (b - a):
            lines.append("!! %s is HELD for %.1fs of this shot -- no footage "
                         "exists for this angle here" % (c, held * spf))
        for x in extra:
            lines.append(x)
        notes.append({"start": a, "end": b, "lines": lines})
    return notes


def load_plan(m):
    """(plan, why, source) -- plan is [(camera, start, end)] in programme frames.

    `why` is whatever the planner recorded about each segment; a shot list read
    off a finished film has none, and says so.
    """
    if m.get("plan"):
        src = m["plan"]
        label = "inline in the manifest"
    else:
        with open(rel(m["plan_from"]), encoding="utf-8") as f:
            src = json.load(f)["shots"]
        label = os.path.basename(rel(m["plan_from"]))
    plan = [(s["camera"], int(s["start"]), int(s["end"])) for s in src]
    why = {i: s.get("why") for i, s in enumerate(src) if s.get("why")}
    return plan, why, label


def build_graph(plan, cams, anchors, idx, audio_from, a_start, a_end,
                vlabel="vout"):
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
        ch.append("[v0]null[%s]" % vlabel)
    else:
        ch.append("%sconcat=n=%d:v=1:a=0[%s]"
                  % ("".join(segs), len(segs), vlabel))
    ch.append("[%d:a]atrim=start_sample=%d:end_sample=%d,asetpts=PTS-STARTPTS[aout]"
              % (idx[audio_from], a_start, a_end))
    return ";".join(ch)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--list", action="store_true",
                    help="print the plan and the anchors, encode nothing")
    ap.add_argument("--debug", action="store_true",
                    help="burn a running commentary into the corner: what each "
                         "shot is, why, and whether its tape actually has "
                         "footage there")
    ap.add_argument("--debug-style", help="default config/overlays/debug-notes.json")
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

    plan, why, plan_src = load_plan(m)
    used = sorted({c for c, _, _ in plan})
    for c in used:
        if c not in files:
            sys.exit("the plan uses %s, which is not one of the cameras" % c)
    w, h, num, den = probe_video(files[ref])
    spf = den / float(num)
    n_prog = max(b for _, _, b in plan)

    # Anchoring uses each instrument where it is strong. The picture gives ONE
    # absolute anchor, taken from the tape whose opening hold breaks most
    # decisively -- a close-up, in practice. The sound, already proven exact
    # to the frame, places every other tape relative to it. A wide CANNOT
    # reliably anchor itself: its people are small at analysis size, its live
    # footage barely moves, and a fixed motion threshold finds its first live
    # frame late -- +2, +30 and +6 frames on three different films, caught by
    # this cross-check every time. Any tape whose own margin is clean still
    # measures independently and must agree; a thin margin reports itself,
    # because walking past the hold into near-still live frames is exactly
    # what raises the measured floor.
    anchors, how = {}, m.get("anchor", "picture_start")
    cand = {}
    if how == "picture_start":
        first = {}
        for c, a, _ in plan:
            first[c] = min(first.get(c, a), a)
        for c in cams:
            if c not in first:
                anchors[c] = None
                continue
            i, floor, jump = picture_start(files[c], w, h, acfg["still"])
            if i is None or i == 1:
                sys.exit("%s does not open on a held frame it ever leaves -- "
                         "declare `anchor` per camera instead" % c)
            cand[c] = (i - first[c] - 1,      # the held frame is the first live one
                       floor, jump, jump / max(floor, 1e-6))
        base = max(cand, key=lambda c: cand[c][3])
        if cand[base][3] < acfg["min_margin"]:
            sys.exit("no tape breaks its opening hold decisively (best margin "
                     "%.1fx on %s) -- declare `anchor` per camera instead"
                     % (cand[base][3], base))
        if off.get(base) is None:
            sys.exit("%s anchors the film but the sync has no offset for it"
                     % base)
        anchors[base] = cand[base][0]
        for c in cand:
            if c != base:
                anchors[c] = cand[base][0] + int(round(off[c] - off[base]))
    elif isinstance(how, dict):
        anchors = {c: int(how[c]) for c in cams if c in how}
        base = None
    else:
        sys.exit("anchor must be \"picture_start\" or a map of camera to frame")

    print("%d tapes, reference %s, %dx%d %d/%d, programme %d frames (%s)"
          % (len(cams), ref, w, h, num, den, n_prog, hhmmss(n_prog * spf)))
    print("\n  cam   anchor   tape frames   margin   picture check")
    bad = []
    for c in cams:
        if anchors.get(c) is None:
            print("  %-5s      -                             unused by the plan"
                  % c)
            continue
        mine = []
        tot = count_frames(files[c])
        need = anchors[c] + n_prog
        if anchors[c] < 0 or need > tot:
            mine.append("%s: the plan needs frames %d-%d but the tape has %d"
                        % (c, anchors[c], need, tot))
        note, mg = "declared", None
        if c in cand:
            mg = cand[c][3]
            if c == base:
                note = "anchors the film (%.4f -> %.4f)" % cand[c][1:3]
            elif mg >= acfg["min_margin"]:
                d = cand[c][0] - anchors[c]
                note = "agrees %+d fr" % d
                if abs(d) > acfg["tolerance_frames"]:
                    mine.append("%s: its own picture says anchor %d but the "
                                "sound-derived anchor is %d -- they must agree"
                                % (c, cand[c][0], anchors[c]))
            else:
                note = ("too still to self-anchor (%.1fx) -- placed by sound"
                        % mg)
        print("  %-5s %6d  %12d   %5s    %s"
              % (c, anchors[c], tot,
                 "-" if mg is None else "%.1fx" % mg, note))
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

    # Sample boundaries round to the nearest sample where 48 kHz does not
    # divide the frame time (29.97 fps): at most half a sample, computed from
    # frame zero so it cannot accumulate. See samples_at() in split-cameras.py.
    a_rate = 48000
    a0 = int(round(anchors[audio_from] * a_rate * den / float(num)))
    a1 = int(round((anchors[audio_from] + n_prog) * a_rate * den / float(num)))
    idx = {c: i for i, c in enumerate(cams)}
    tmpdir = os.path.join(ROOT, "temp", "anglecut-%s" % pid)
    ass = None
    if not args.debug:
        graph = build_graph(plan, cams, anchors, idx, audio_from, a0, a1)
    else:
        os.makedirs(tmpdir, exist_ok=True)
        # Read each tape's own picture to find where it is held rather than
        # shot. This runs AFTER the plan is fixed, so it cannot leak into an
        # editorial decision -- it only annotates one that was already made.
        dcfg = dict(DEFAULT_DEBUG, **(m.get("debug") or {}))
        tapes = {}
        mn = max(1, int(round(dcfg["held_min_run_s"] / spf)))
        for c in used:
            diff, _ = _shots.scan(files[c], w, h)
            tapes[c] = still_runs(diff, dcfg["held"], mn)
            held = sum(b - a for a, b in tapes[c])
            print("  %s: %d held runs, %d frames (%.0f%% of the tape)"
                  % (c, len(tapes[c]), held, 100.0 * held / max(1, len(diff))))
        stage = "stage 2 (chosen from sound)" if why else "stage 1 (given plan)"
        extra = list((m.get("debug") or {}).get("lines") or [])
        notes = debug_notes(plan, anchors, off, files, tapes, num / float(den),
                            spf, stage, plan_src, why, extra, dcfg["warn_frac"])
        ass, fc, _ = _notes.prepare(
            notes, w, h, num / float(den), tmpdir, tag=pid,
            preset=args.debug_style, base="vpre", label="vout")
        graph = ";".join([build_graph(plan, cams, anchors, idx, audio_from,
                                      a0, a1, vlabel="vpre"), fc])
        n_warn = sum(1 for n in notes if any(x.startswith("!!") for x in n["lines"]))
        print("  debug notes: %d, of which %d warn that the tape is held there"
              % (len(notes), n_warn))

    outdir = rel(m.get("outdir", "projects/%s/outputs" % pid))
    os.makedirs(outdir, exist_ok=True)
    # A debug render is a different artifact, never a replacement: burning text
    # changes pixels, so a debug copy of a stage-1 cut is no longer frame
    # identical to the programme and would fail its own comparison.
    dst = rel(args.out) if args.out else os.path.join(
        outdir, "%s-anglecut%s.mp4" % (pid, "-debug" if args.debug else ""))
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
                                                else "declared frames")]
                    + (["debug notes burned bottom-left: segment, reason, tape "
                        "frames, and a warning where the tape is held"]
                       if args.debug else []))


if __name__ == "__main__":
    main()
