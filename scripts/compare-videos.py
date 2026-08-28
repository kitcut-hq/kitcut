#!/usr/bin/env python
"""Score one video against another, frame by frame, and say whether it passes.

Written to judge the multicam round trip -- a film re-cut out of rebuilt camera
tapes, against the film it was rebuilt from -- but it is a general "are these
the same edit" comparator.

Four measurements, because a single number hides the failure that matters:

  ssim        per frame, on downscaled greyscale. Says the pictures are the
              same. A re-encode costs a little; a wrong picture costs a lot.
  shift       for every frame, SSIM against the reference frame BEFORE, AT and
              AFTER it, and which of the three wins. This is the measurement
              the whole test turns on: a join placed one frame early still
              scores a high average SSIM, because 2795 of 2796 frames are
              right, but the frames after that join match the reference's
              PREVIOUS frame better than its own, and that shows up instantly.
              Reported as the count of frames whose best match is not itself.
  cuts        both films read back through shot-detect.py, so the comparison
              is between two recovered edits rather than between one edit and
              a claim. Boundaries are matched and their offsets reported.
  audio       cross-correlation offset, then the residual of the aligned
              waveforms. Catches a soundtrack that is right but late.

The pass bar is not a global average. A film can be 99.9% identical and still
be wrong in the way that matters, so the thresholds are on the worst join, the
shift count and the frame count -- all of which are exact -- and SSIM is only
asked to rule out gross corruption.

Invoke as:  python scripts/compare-videos.py --rendered a.mp4 --reference b.mp4
"""
import sys, os, json, argparse, subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import
from importlib import import_module  # noqa: E402

import numpy as np  # noqa: E402
import cv2  # noqa: E402

import _project  # noqa: E402

_shots = import_module("shot-detect")   # hyphen: not importable by name

ROOT = _env.ROOT
ENV = _env.ENV

SW = 320                     # SSIM analysis width
RATE = 8000                  # audio analysis rate
DEFAULT_PASS = {"frames_exact": True, "max_shifted": 0, "min_ssim_median": 0.95,
                "min_ssim_p5": 0.90,
                # One frame, because that is the shot detector's own precision
                # -- not a relaxation of frame-exactness, which the shift probe
                # still holds at zero. Measured: a boundary that is a smooth
                # plateau rather than a cut peaked at frame 62167 in one film
                # and 62168 in the other, values differing in the fifth
                # decimal. A real misalignment moves every cut, not one.
                "max_cut_offset": 1,
                "max_audio_offset_ms": 1.0, "max_frozen_frames": 0}
# Calibrated against a render known to be pixel-identical to its reference, so
# every run it reports is a false positive. A looser 0.0015 over half a second
# called 12.8% of that film frozen -- which was the podcast's own stillness, not
# the cut's. A held frame scores 0.0000 (worst 0.0005); live footage sits above.
FROZEN = {"still": 0.0005, "min_run_s": 1.0}
SHIFT_MARGIN = 0.001         # see the comment where it is used


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, capture_output=True, text=True,
                          env=ENV, **kw)


def hhmmss(t):
    return "%d:%05.2f" % (int(t) // 60, t % 60)


def rel(p):
    return p if os.path.isabs(p) else os.path.join(ROOT, p)


def probe(path):
    out = run(["ffprobe", "-v", "error", "-select_streams", "v:0",
               "-show_entries", "stream=width,height,r_frame_rate",
               "-of", "json", path]).stdout
    s = json.loads(out)["streams"][0]
    num, den = (int(x) for x in s["r_frame_rate"].split("/"))
    return {"width": int(s["width"]), "height": int(s["height"]),
            "fps_num": num, "fps_den": den, "fps": num / float(den)}


def count_frames(path):
    out = run(["ffprobe", "-v", "error", "-select_streams", "v:0",
               "-count_packets", "-show_entries", "stream=nb_read_packets",
               "-of", "csv=p=0", path]).stdout
    return int(out.strip().rstrip(","))


def frames(path, w, h):
    """Every frame, greyscale float, streamed."""
    p = subprocess.Popen(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin",
         "-i", path, "-vf", "scale=%d:%d" % (w, h), "-fps_mode", "passthrough",
         "-an", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
        stdout=subprocess.PIPE, env=ENV)
    n = w * h
    while True:
        buf = p.stdout.read(n)
        if len(buf) < n:
            break
        yield np.frombuffer(buf, np.uint8).reshape(h, w).astype(np.float32) / 255.0
    p.stdout.close()
    p.wait()


def ssim(a, b):
    """Structural similarity, the standard 11x11 Gaussian formulation.

    Hand-rolled because neither scipy nor scikit-image is installed here, and
    adding either to get fifteen lines of cv2 would be the tail wagging the dog.
    """
    C1, C2 = 0.01 ** 2, 0.03 ** 2
    k, s = (11, 11), 1.5
    mu_a = cv2.GaussianBlur(a, k, s)
    mu_b = cv2.GaussianBlur(b, k, s)
    aa, bb = mu_a * mu_a, mu_b * mu_b
    ab = mu_a * mu_b
    va = cv2.GaussianBlur(a * a, k, s) - aa
    vb = cv2.GaussianBlur(b * b, k, s) - bb
    vab = cv2.GaussianBlur(a * b, k, s) - ab
    m = ((2 * ab + C1) * (2 * vab + C2)) / ((aa + bb + C1) * (va + vb + C2))
    return float(m.mean())


def mono(path):
    p = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-i", path,
         "-vn", "-map", "0:a:0", "-f", "f32le", "-acodec", "pcm_f32le",
         "-ac", "1", "-ar", str(RATE), "-"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=ENV)
    if p.returncode != 0:
        return None
    a = np.frombuffer(p.stdout, dtype=np.float32)
    return a.astype(np.float32) if a.size else None


def audio_align(a, b):
    """(offset in samples of a relative to b, residual dB after aligning)."""
    x, y = a - a.mean(), b - b.mean()
    n = 1 << (x.size + y.size - 1).bit_length()
    c = np.fft.irfft(np.fft.rfft(x, n) * np.conj(np.fft.rfft(y, n)), n)
    k = int(np.argmax(c))
    if k > n // 2:
        k -= n
    if k >= 0:
        u, v = a[k:], b[:a.size - k]
    else:
        u, v = a[:b.size + k], b[-k:]
    m = min(u.size, v.size)
    u, v = u[:m], v[:m]
    ref = float(np.sqrt((v.astype(np.float64) ** 2).mean())) or 1e-12
    err = float(np.sqrt(((u.astype(np.float64) - v) ** 2).mean()))
    return k, 20.0 * np.log10(max(err, 1e-12) / ref)


def frozen_runs(diff, fps, still=None, min_run_s=None):
    """Stretches where the rendered film's own picture stops moving.

    Worth a first-class number, not a footnote. In the round-trip test a frozen
    run means the cut asked a camera for footage it does not have -- which is
    what happens whenever a stage-2 switcher picks an angle the original editor
    was not on, because the synthetic tape only carries real frames where that
    angle was used. A single frame proves nothing (a held frame and a still
    moment score alike), but a RUN of them is unambiguous.
    """
    still = FROZEN["still"] if still is None else still
    need = int(round((FROZEN["min_run_s"] if min_run_s is None else min_run_s) * fps))
    out, start = [], None
    for i in range(1, len(diff)):
        if diff[i] <= still:
            start = i if start is None else start
        else:
            if start is not None and i - start >= need:
                out.append((start, i))
            start = None
    if start is not None and len(diff) - start >= need:
        out.append((start, len(diff)))
    return out


def match_cameras(a_sigs, a_names, b_sigs, b_names):
    """Map the angle labels of one film onto the other's.

    Cluster names are assigned per film in order of first appearance, so they
    only coincide by luck. Matching them by fingerprint is what lets the two
    recovered edits be compared at all.
    """
    def centre(sigs, names, nm):
        xs = [s for s, x in zip(sigs, names) if x == nm]
        return np.median(np.array(xs), axis=0)

    out = {}
    for nm in sorted(set(a_names)):
        ca = centre(a_sigs, a_names, nm)
        best, at = None, None
        for om in sorted(set(b_names)):
            d = _shots.distance(ca, centre(b_sigs, b_names, om))
            if best is None or d < best:
                best, at = d, om
        out[nm] = (at, round(best, 5))
    return out


def label_track(spans, names, n):
    lab = [None] * n
    for (a, b), nm in zip(spans, names):
        for i in range(a, min(b, n)):
            lab[i] = nm
    return lab


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--rendered", required=True, help="the film under test")
    ap.add_argument("--reference", required=True, help="what it should equal")
    ap.add_argument("--manifest", help="reads its `pass` block for thresholds")
    ap.add_argument("--id", help="project id for the report and journal line")
    ap.add_argument("--out", help="default projects/<id>/<id>.compare.json")
    ap.add_argument("--json", action="store_true", help="print the report")
    ap.add_argument("--no-cuts", action="store_true",
                    help="skip the shot comparison (two extra decodes)")
    args = ap.parse_args()

    ren, ref = rel(args.rendered), rel(args.reference)
    for p in (ren, ref):
        if not os.path.exists(p):
            sys.exit("no such file: %s" % _project.norm(p))
    bar = dict(DEFAULT_PASS)
    if args.manifest:
        with open(rel(args.manifest), encoding="utf-8") as f:
            bar.update((json.load(f).get("pass") or {}))
    d = _project.find_project_dir(ren)
    pid = args.id or (os.path.basename(d) if d else
                      os.path.splitext(os.path.basename(ren))[0])

    ia, ib = probe(ren), probe(ref)
    na, nb = count_frames(ren), count_frames(ref)
    h = int(round(SW * ib["height"] / float(ib["width"]))) // 2 * 2
    fps = ib["fps"]
    print("rendered  %s  %dx%d  %d frames  %s"
          % (_project.norm(ren), ia["width"], ia["height"], na, hhmmss(na / fps)))
    print("reference %s  %dx%d  %d frames  %s"
          % (_project.norm(ref), ib["width"], ib["height"], nb, hhmmss(nb / fps)))

    scores, best_at = [], []
    ga, gb = frames(ren, SW, h), frames(ref, SW, h)
    prev_b, cur_b = None, next(gb, None)
    nxt_b = next(gb, None)
    for a in ga:
        if cur_b is None:
            break
        here = ssim(a, cur_b)
        cand = [(here, 0)]
        if prev_b is not None:
            cand.append((ssim(a, prev_b), -1))
        if nxt_b is not None:
            cand.append((ssim(a, nxt_b), 1))
        scores.append(here)
        # A neighbour only counts as the better match when it wins by more
        # than encode noise. Measured: on a near-still moment two adjacent
        # reference frames are 0.9996 alike and the coin-flip margin is
        # 0.00006; a real one-frame misalignment wins by 0.01 and more, and
        # arrives as a run, not as one frame. Without this guard a single
        # still frame of a 2540-frame film failed an otherwise exact round
        # trip.
        best, at = max(cand)
        best_at.append(at if best - here > SHIFT_MARGIN else 0)
        prev_b, cur_b, nxt_b = cur_b, nxt_b, next(gb, None)
    scores = np.array(scores, dtype=np.float64)
    if scores.size == 0:
        sys.exit("no overlapping frames to compare")
    shifted = [i for i, v in enumerate(best_at) if v != 0]

    p5 = float(np.percentile(scores, 5))
    print("\nssim over %d compared frames: median %.4f  p5 %.4f  min %.4f @ %s"
          % (scores.size, float(np.median(scores)), p5,
             float(scores.min()), hhmmss(int(np.argmin(scores)) / fps)))
    if p5 < 0.9:
        bad = int((scores < 0.9).sum())
        print("  !! %d frames (%.1f%%) score below 0.90 -- the MEDIAN IS NOT THE "
              "STORY here. A film can be 78%% right and still show something "
              "completely wrong for a fifth of its length."
              % (bad, 100.0 * bad / scores.size))
    print("frames whose best match is a NEIGHBOUR, not themselves: %d of %d"
          % (len(shifted), scores.size))
    for i in shifted[:12]:
        print("    frame %5d (%s) matches %+d better" % (i, hhmmss(i / fps), best_at[i]))
    if len(shifted) > 12:
        print("    ... and %d more" % (len(shifted) - 12))

    cuts_report, worst_join, agree, froz = None, None, None, []
    if not args.no_cuts:
        da, sa = _shots.scan(ren, ia["width"], ia["height"])
        db, sb = _shots.scan(ref, ib["width"], ib["height"])
        # Only frozen where the reference is MOVING. A talking head sitting
        # still is the source's own stillness and belongs to both films; what
        # matters is picture that stopped in ours and kept going in theirs.
        #
        # Compared run-to-run at first, and that was too fragile to trust: when
        # both films hover either side of the still threshold their runs come
        # out with different boundaries, and shared stillness gets reported as
        # filler. Measured on an hour-long film where it did exactly that --
        # rendered max 0.000858 against reference 0.000866 over the same
        # frames, the same stillness called two different ways. Asking whether
        # the REFERENCE moves over those frames has no boundary to disagree on.
        froz = [(a, b) for a, b in frozen_runs(da, fps)
                if float(db[a:b].mean()) > FROZEN["still"]]
        n_froz = sum(b - a for a, b in froz)
        print("\nfrozen picture in the rendered film that is not frozen in the "
              "reference: %d frames (%.1f%%) in %d runs"
              % (n_froz, 100.0 * n_froz / max(1, na), len(froz)))
        for a, b in froz[:8]:
            print("    %s-%s  %.2fs held" % (hhmmss(a / fps), hhmmss(b / fps),
                                             (b - a) / fps))
        if len(froz) > 8:
            print("    ... and %d more" % (len(froz) - 8))
        if n_froz:
            print("    a frozen run means the cut asked a camera for footage it "
                  "does not have. In this fixture that is every moment the "
                  "switcher chose an angle the original editor was not on.")
        pa, ssa, nma = _shots.build_shots(da, sa, _shots.DEFAULT_DETECT)
        pb, ssb, nmb = _shots.build_shots(db, sb, _shots.DEFAULT_DETECT)
        ca = [a for a, _ in pa[1:]]
        cb = [a for a, _ in pb[1:]]
        print("\ncuts: %d in the rendered film, %d in the reference" % (len(ca), len(cb)))
        offs = []
        for x in cb:
            near = min(ca, key=lambda y: abs(y - x)) if ca else None
            offs.append(None if near is None else near - x)
        matched = [o for o in offs if o is not None and abs(o) <= 4]
        worst_join = max((abs(o) for o in matched), default=0)
        for x, o in zip(cb, offs):
            if o is None or abs(o) > 0:
                print("    reference cut at %5d (%s): rendered %s"
                      % (x, hhmmss(x / fps), "none" if o is None else "%+d frames" % o))
        print("    worst matched cut offset: %d frames" % worst_join)

        amap = match_cameras(ssa, nma, ssb, nmb)
        la = label_track(pa, nma, min(na, nb))
        lb = label_track(pb, nmb, min(na, nb))
        same = sum(1 for x, y in zip(la, lb)
                   if x is not None and amap.get(x, (None,))[0] == y)
        agree = 100.0 * same / max(1, min(na, nb))
        print("    angle map: %s"
              % ", ".join("%s->%s(%.3f)" % (k, v[0], v[1]) for k, v in sorted(amap.items())))
        print("    same angle on %.2f%% of the timeline" % agree)
        cuts_report = {"rendered": ca, "reference": cb,
                       "offsets": offs, "worst_matched_offset": worst_join,
                       "angle_map": {k: v[0] for k, v in amap.items()},
                       "timeline_agreement_pct": round(agree, 3)}

    aud = None
    sa_, sb_ = mono(ren), mono(ref)
    if sa_ is not None and sb_ is not None:
        k, resid = audio_align(sa_, sb_)
        ms = 1000.0 * k / RATE
        print("\naudio: offset %+.3f ms, residual %.1f dB below the reference"
              % (ms, -resid))
        aud = {"offset_samples": k, "offset_ms": round(ms, 4),
               "residual_db": round(resid, 2)}

    fails = []
    if bar["frames_exact"] and na != nb:
        fails.append("frame count %d, reference %d" % (na, nb))
    if len(shifted) > bar["max_shifted"]:
        fails.append("%d frames are shifted (allowed %d)"
                     % (len(shifted), bar["max_shifted"]))
    if float(np.median(scores)) < bar["min_ssim_median"]:
        fails.append("median ssim %.4f below %.4f"
                     % (float(np.median(scores)), bar["min_ssim_median"]))
    if p5 < bar["min_ssim_p5"]:
        fails.append("5th-percentile ssim %.4f below %.4f -- a bad tail the "
                     "median cannot see" % (p5, bar["min_ssim_p5"]))
    n_froz = sum(b - a for a, b in froz)
    if n_froz > bar["max_frozen_frames"]:
        fails.append("%d frames of frozen picture (allowed %d)"
                     % (n_froz, bar["max_frozen_frames"]))
    if worst_join is not None and worst_join > bar["max_cut_offset"]:
        fails.append("a cut is %d frames out (allowed %d)"
                     % (worst_join, bar["max_cut_offset"]))
    if aud and abs(aud["offset_ms"]) > bar["max_audio_offset_ms"]:
        fails.append("audio is %+.2f ms out" % aud["offset_ms"])

    doc = {"_comment": "Round-trip score by scripts/compare-videos.py.",
           "id": pid, "rendered": _project.norm(ren),
           "reference": _project.norm(ref),
           "frames": {"rendered": na, "reference": nb, "compared": int(scores.size)},
           "ssim": {"median": round(float(np.median(scores)), 5),
                    "p5": round(float(np.percentile(scores, 5)), 5),
                    "min": round(float(scores.min()), 5),
                    "min_at_frame": int(np.argmin(scores))},
           "shifted_frames": {"count": len(shifted), "first": shifted[:32]},
           "frozen": {"frames": n_froz,
                      "pct": round(100.0 * n_froz / max(1, na), 2),
                      "runs": [[a, b] for a, b in froz]},
           "cuts": cuts_report, "audio": aud,
           "pass_bar": bar, "failures": fails, "verdict": "PASS" if not fails else "FAIL"}

    print("\n%s" % ("PASS" if not fails else "FAIL"))
    for f in fails:
        print("  !! %s" % f)

    out = args.out or os.path.join(d or os.path.join(ROOT, "temp"),
                                   "%s.compare.json" % pid)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2)
        f.write("\n")
    print("wrote %s" % _project.norm(out))
    if args.json:
        print(json.dumps(doc, indent=2))
    _project.record(pid, "compare", script=__file__, argv=sys.argv[1:],
                    note="%s: %s vs %s, median ssim %.4f, %d shifted frames"
                         % (doc["verdict"], _project.norm(ren), _project.norm(ref),
                            doc["ssim"]["median"], len(shifted)))
    sys.exit(0 if not fails else 1)


if __name__ == "__main__":
    main()
