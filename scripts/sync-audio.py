#!/usr/bin/env python
"""Line up N recordings of the same event by their sound.

sync-tracks.py answers a different question and keeps its own shape: one screen
recording with no audio against one camera that has it, correlating picture
CHANGE against sound. Here every tape carries the same programme audio, so the
sound can be correlated against itself, and the answer is good to a fraction of
a frame instead of a fifth of a second.

Two independent measurements, which is the point:

  offset       waveform cross-correlation against the reference tape, by FFT.
               Gives the RELATIVE stagger between any two tapes, and a
               confidence that is the peak's z-score against the rest of the
               curve -- a number that says "this is a spike", not "this is the
               largest of a flat field". This is the measurement; on the a16z
               fixture it recovered every stagger to the exact frame.
  audio_start  roughly where sound begins on each tape, by onset. A SECOND
               OPINION, not an anchor: it finds where the recording becomes
               audible, which is a little after it starts, because a programme
               usually opens on a quiet moment. Measured here at 41 ms late
               and, being a property of the mix rather than of the tape,
               equally late on all of them.

They must roughly agree. The difference of two tapes' audio_start is the same
quantity the correlation measures, arrived at a completely different way, so
reporting both and the drift between them catches a correlation that locked
onto the wrong peak -- while the tolerance stays loose enough not to pretend
the onset is frame-exact. The pairwise residual matrix is the strict check:
offset(a,b) + offset(b,c) must equal offset(a,c) to the millisecond, and it is
checked rather than assumed.

Nothing here anchors the programme absolutely -- correlation can say two tapes
are 1.2 s apart without saying where the film starts on either. That is the
cut's decision, and angle-cut.py measures it from the picture.

  --verify   write N-up frames at the same synced instant, to look at
  (none)     write projects/<id>/<id>.anglesync.json

Invoke as:  python scripts/sync-audio.py --manifest projects/<id>/anglecut.json
"""
import sys, os, json, argparse, subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import

import numpy as np  # noqa: E402

import _project  # noqa: E402

ROOT = _env.ROOT
ENV = _env.ENV

RATE = 8000                 # 0.125 ms a sample: far finer than a frame
WIN = 80                    # 10 ms onset window
DEFAULT_SYNC = {"onset_db": -100.0, "min_confidence": 8.0,
                "max_residual_ms": 5.0, "max_onset_drift_ms": 60.0}


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, capture_output=True, text=True,
                          env=ENV, **kw)


def hhmmss(t):
    return "%d:%05.2f" % (int(t) // 60, t % 60)


def rel(p):
    return _env.resolve(p)


def probe(path):
    out = run(["ffprobe", "-v", "error", "-select_streams", "v:0",
               "-show_entries", "stream=width,height,r_frame_rate,duration",
               "-of", "json", path]).stdout
    s = json.loads(out)["streams"][0]
    num, den = (int(x) for x in s["r_frame_rate"].split("/"))
    return {"width": int(s["width"]), "height": int(s["height"]),
            "fps_num": num, "fps_den": den, "fps": num / float(den)}


def mono(path):
    """The whole soundtrack as one float32 vector at RATE."""
    p = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-i", path,
         "-vn", "-map", "0:a:0", "-f", "f32le", "-acodec", "pcm_f32le",
         "-ac", "1", "-ar", str(RATE), "-"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=ENV)
    if p.returncode != 0:
        sys.exit("no audio from %s:\n%s" % (path, (p.stderr or b"")[-2000:]))
    a = np.frombuffer(p.stdout, dtype=np.float32)
    if a.size == 0:
        sys.exit("empty soundtrack: %s" % path)
    return a.astype(np.float32)


def onset(a, db):
    """First sample where the sound starts, by short-window RMS."""
    n = (a.size // WIN) * WIN
    r = np.sqrt((a[:n].reshape(-1, WIN).astype(np.float64) ** 2).mean(axis=1))
    thr = 10.0 ** (db / 20.0)
    hit = np.nonzero(r > thr)[0]
    if hit.size == 0:
        return None, float(r.max())
    return int(hit[0]) * WIN, float(r[:hit[0]].max() if hit[0] else 0.0)


def xcorr(a, b):
    """Lag k maximising sum a[t+k]*b[t], plus the peak's z-score.

    Positive k means `a` is LATER than `b`: a started recording earlier, so the
    same moment sits further into it.
    """
    a = a - a.mean()
    b = b - b.mean()
    n = 1 << (a.size + b.size - 1).bit_length()
    c = np.fft.irfft(np.fft.rfft(a, n) * np.conj(np.fft.rfft(b, n)), n)
    k = int(np.argmax(c))
    peak = float(c[k])
    if k > n // 2:
        k -= n
    lo, hi = max(0, int(np.argmax(c)) - 200), int(np.argmax(c)) + 200
    rest = np.concatenate([c[:lo], c[hi:]])
    sd = float(rest.std()) or 1e-12
    return k, peak, (peak - float(rest.mean())) / sd


def nup(paths, times, path, width=320):
    """One frame from each tape at the same synced instant, side by side."""
    from PIL import Image
    imgs = []
    for p, t in zip(paths, times):
        png = path + ".%d.png" % len(imgs)
        run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin",
             "-ss", "%.4f" % max(0.0, t), "-i", p, "-frames:v", "1",
             "-vf", "scale=%d:-2" % width, "-y", png])
        imgs.append(Image.open(png).copy())
        os.remove(png)
    w, h = imgs[0].size
    sheet = Image.new("RGB", (w * len(imgs), h), (16, 16, 16))
    for i, im in enumerate(imgs):
        sheet.paste(im.resize((w, h)), (i * w, 0))
    sheet.save(path)
    return path


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--manifest", help="reads its `cameras` list")
    ap.add_argument("--tracks", nargs="+", help="recordings, instead of a manifest")
    ap.add_argument("--id", help="project id; default: the folder under projects/")
    ap.add_argument("--reference", help="the tape everything is measured against")
    ap.add_argument("--out", help="default projects/<id>/<id>.anglesync.json")
    ap.add_argument("--verify", type=int, default=0, metavar="N",
                    help="write N side-by-side frames at synced instants")
    ap.add_argument("--onset-db", type=float, default=None)
    ap.add_argument("--min-confidence", type=float, default=None)
    args = ap.parse_args()

    if not args.manifest and not args.tracks:
        ap.error("need --manifest or --tracks")
    cfg = dict(DEFAULT_SYNC)
    for k in ("onset_db", "min_confidence"):
        v = getattr(args, k, None)
        if v is not None:
            cfg[k] = v

    if args.manifest:
        with open(rel(args.manifest), encoding="utf-8") as f:
            m = json.load(f)
        cams = [(c["id"], rel(c["file"])) for c in m["cameras"]]
        cfg.update({k: v for k, v in (m.get("sync_cfg") or {}).items()})
        pid = args.id or _project.project_id(m, rel(args.manifest))
    else:
        cams = [(os.path.splitext(os.path.basename(t))[0], rel(t))
                for t in args.tracks]
        d = _project.find_project_dir(rel(args.tracks[0]))
        pid = args.id or (os.path.basename(d) if d else "tracks")

    for _, p in cams:
        if not os.path.exists(p):
            sys.exit("no such file: %s" % _project.norm(p))
    ref = args.reference or cams[0][0]
    if ref not in [c for c, _ in cams]:
        sys.exit("--reference %s is not one of %s"
                 % (ref, ", ".join(c for c, _ in cams)))

    info = probe(cams[0][1])
    fps = info["fps"]
    print("%d tapes, reference %s, %.4f fps" % (len(cams), ref, fps))

    sig = {c: mono(p) for c, p in cams}
    ons = {}
    for c, _ in cams:
        s, floor = onset(sig[c], cfg["onset_db"])
        ons[c] = s
        if s is None:
            print("  %-5s no onset above %.0f dBFS (loudest %.5f) -- this tape "
                  "cannot anchor a cut" % (c, cfg["onset_db"], floor))

    names = [c for c, _ in cams]
    pair, worst_conf = {}, None
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            k, _, z = xcorr(sig[a], sig[b])
            pair[(a, b)] = (k, z)
            pair[(b, a)] = (-k, z)
            if worst_conf is None or z < worst_conf:
                worst_conf = z
    for c in names:
        pair[(c, c)] = (0, float("inf"))

    print("\n  tape    offset      frames   conf   audio starts   onset-vs-corr")
    tracks, bad = [], []
    for c, p in cams:
        k, z = pair[(c, ref)]
        off = k / float(RATE)
        astart = ons[c]
        delta = ""
        if astart is not None and ons[ref] is not None:
            d_ms = 1000.0 * ((astart - ons[ref]) / float(RATE) - off)
            delta = "%+7.2f ms" % d_ms
            if abs(d_ms) > cfg["max_onset_drift_ms"]:
                bad.append("%s: onset and correlation disagree by %.2f ms"
                           % (c, d_ms))
        if z < cfg["min_confidence"]:
            bad.append("%s: correlation peak is mush (z=%.1f)" % (c, z))
        print("  %-5s %+9.4f s %+8.2f  %5.1f   %12s   %s"
              % (c, off, off * fps,
                 z if z != float("inf") else 999.0,
                 "-" if astart is None else "%.4f s" % (astart / float(RATE)),
                 delta))
        tracks.append({
            "id": c, "file": _project.norm(p),
            "offset_s": round(off, 6), "offset_frames": round(off * fps, 4),
            "confidence": None if z == float("inf") else round(z, 3),
            "audio_start_s": None if astart is None else round(astart / float(RATE), 6),
            "audio_start_frames": None if astart is None else
                int(round(astart / float(RATE) * fps)),
        })

    resid, worst_r = {}, 0.0
    for a in names:
        for b in names:
            for c in names:
                r = pair[(a, b)][0] + pair[(b, c)][0] - pair[(a, c)][0]
                if abs(r) > abs(worst_r):
                    worst_r = r
            resid["%s->%s" % (a, b)] = round(pair[(a, b)][0] / float(RATE), 6)
    print("\nworst three-way residual %+.3f ms (offset a->b plus b->c must equal "
          "a->c)" % (1000.0 * worst_r / RATE))
    if abs(worst_r) / float(RATE) * 1000.0 > cfg["max_residual_ms"]:
        bad.append("the offsets are not self-consistent: %.2f ms round trip"
                   % (1000.0 * worst_r / RATE))

    if args.verify:
        tmp = os.path.join(ROOT, "temp", "sync-audio-%s" % pid)
        os.makedirs(tmp, exist_ok=True)
        dur = min(sig[c].size for c in names) / float(RATE)
        base = ons[ref] / float(RATE) if ons[ref] is not None else 0.0
        for i in range(args.verify):
            t = base + (i + 1) * (dur - base) / (args.verify + 1.0)
            out = nup([p for _, p in cams],
                      [t + pair[(c, ref)][0] / float(RATE) for c, _ in cams],
                      os.path.join(tmp, "sync-%02d.png" % i))
            print("  %s  (reference %s)" % (_project.norm(out), hhmmss(t)))

    doc = {"_comment": "N-track audio alignment by scripts/sync-audio.py. "
                       "offset is seconds of THIS tape relative to the "
                       "reference: the same moment sits offset seconds later "
                       "into it, and is exact. audio_start is an approximate "
                       "second opinion -- where the tape becomes audible, "
                       "which is a little after it starts -- and must not be "
                       "used to anchor a cut.",
           "id": pid, "reference": ref,
           "fps_num": info["fps_num"], "fps_den": info["fps_den"], "fps": fps,
           "rate": RATE, "config": cfg,
           "tracks": tracks,
           "pairwise_offset_s": resid,
           "worst_three_way_residual_ms": round(1000.0 * worst_r / RATE, 4),
           "notes": []}

    if bad:
        doc["notes"] = bad
        print("")
        for b in bad:
            print("  !! %s" % b)
        sys.exit("refusing to write a sync that does not check out")

    out = args.out or os.path.join(
        _project.find_project_dir(cams[0][1]) or os.path.join(ROOT, "temp"),
        "%s.anglesync.json" % pid)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2)
        f.write("\n")
    print("\nwrote %s" % _project.norm(out))
    _project.record(pid, "sync-audio", script=__file__, argv=sys.argv[1:],
                    note="%d tapes aligned on %s, worst confidence %.1f, "
                         "worst three-way residual %.3f ms"
                         % (len(cams), ref, worst_conf or 0.0,
                            1000.0 * worst_r / RATE))


if __name__ == "__main__":
    main()
