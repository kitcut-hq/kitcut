#!/usr/bin/env python
"""One-command pipeline: video URL (or local file) -> captioned MP4.

    python -X utf8 -E scripts/run-captions.py --url <URL> --style config/presets/red-card.json

Stages: download audio transcribe overlays ass verify render
- Resumable: a stage is skipped when its artifact already exists.
- --force <stage> reruns that stage and everything after it.
- --stop-after <stage> stops right after that stage completes.
- transcribe and overlays run IN PARALLEL (independent inputs). While they do,
  overlay detection decodes on CPU so the GPU is left to the ASR model --
  4 GB of VRAM cannot host ctranslate2 and an NVDEC session reliably.

Artifacts: the transcript lands in transcripts/ (the one expensive artifact --
minutes of GPU time), everything else in temp/ (regenerates in seconds, safe to
delete). A manifest with tool versions, arguments and hashes is written next to
the output for reproducibility.

Every visual choice lives in the style preset JSON -- font, colours, corner
radius, padding, position, grouping, timing, animation. Never edit code to
change how captions look. Presets are authored for a 1920x1080 canvas and are
scaled automatically to the actual video dimensions.
"""
import sys, os, json, argparse, subprocess, time, shutil, hashlib, struct

# Drop any site-packages that belongs to a DIFFERENT Python install. A stale
# machine-wide PYTHONPATH gets prepended to sys.path and shadows this
# interpreter's packages with incompatible ones (or, once that install is
# removed, with nothing at all). sys.path is frozen at startup so clearing
# os.environ in-process cannot help -- hence also `-E` at the call site.
import sysconfig as _sc, site as _site
def _norm(p):
    return os.path.normcase(os.path.abspath(p))
_own = {_norm(p) for p in (_sc.get_paths().get("purelib"),
                           _sc.get_paths().get("platlib")) if p}
for _getter in (lambda: [_site.getusersitepackages()], _site.getsitepackages):
    try:
        _own.update(_norm(p) for p in _getter())
    except Exception:
        pass          # user site is where Store Python puts pip installs
sys.path[:] = [p for p in sys.path
               if "site-packages" not in p.lower() or _norm(p) in _own]
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = [sys.executable, "-X", "utf8", "-E"]
# Invoke yt-dlp as a MODULE, never as a bare `yt-dlp` command. The console-script
# shim on PATH hardcodes the interpreter it was installed by, so it dies silently
# (exit 1, zero output) if that Python is removed or upgraded -- and a freshly
# pip-installed replacement often lands in a Scripts dir that is not on PATH.
# Going through sys.executable guarantees we run the yt-dlp that belongs to the
# same interpreter as everything else in this pipeline.
YTDLP = PY + ["-m", "yt_dlp"]
ENV = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
STAGES = ["download", "audio", "transcribe", "overlays", "ass", "verify", "render"]


def sh(cmd, **kw):
    r = subprocess.run(cmd, cwd=ROOT, env=ENV, **kw)
    if r.returncode != 0:
        sys.exit("FAILED (%d): %s" % (r.returncode, " ".join(str(c) for c in cmd[:6])))
    return r


def out(cmd):
    return subprocess.run(cmd, cwd=ROOT, env=ENV, capture_output=True, text=True,
                          encoding="utf-8", errors="replace").stdout.strip()


def probe(path, entries, stream=None):
    c = ["ffprobe", "-v", "error"]
    if stream:
        c += ["-select_streams", stream]
    c += ["-show_entries", entries, "-of", "default=nw=1:nk=1", path]
    return out(c).splitlines()


def md5(path, limit=None):
    h = hashlib.md5()
    with open(path, "rb") as f:
        while True:
            b = f.read(1 << 20)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def first_boxes(path, n=4):
    """Top-level MP4 box order; faststart means moov before mdat."""
    boxes = []
    with open(path, "rb") as f:
        while len(boxes) < n:
            hdr = f.read(8)
            if len(hdr) < 8:
                break
            sz, typ = struct.unpack(">I4s", hdr)
            boxes.append(typ.decode("latin1"))
            if sz == 1:
                sz = struct.unpack(">Q", f.read(8))[0]
                f.seek(sz - 16, 1)
            elif sz == 0:
                break
            else:
                f.seek(sz - 8, 1)
    return boxes


def main():
    ap = argparse.ArgumentParser()
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--url")
    src.add_argument("--input")
    ap.add_argument("--id", help="slug for artifacts; defaults to the video id / filename")
    ap.add_argument("--style", required=True)
    ap.add_argument("--height", type=int, default=1080)
    ap.add_argument("--lang", default=None, help="ASR language code; autodetect if omitted")
    ap.add_argument("--model", default="large-v3")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--compute-type", default="int8_float16")
    ap.add_argument("--samples", type=int, default=60, help="sync probes")
    ap.add_argument("--force", choices=STAGES, help="rerun this stage and all after it")
    ap.add_argument("--stop-after", choices=STAGES)
    ap.add_argument("--no-overlays", action="store_true")
    ap.add_argument("--overlay-fps", type=float, default=3.0,
                    help="sampling rate for source-graphic detection; 2-4 is plenty "
                         "for graphics that last several seconds")
    ap.add_argument("--min-free-gb", type=float, default=8.0,
                    help="abort before starting if the disk has less than this free")
    ap.add_argument("--preview", nargs=2, type=float, metavar=("START", "DUR"),
                    help="render only this window (regenerates a time-shifted ASS)")
    args = ap.parse_args()

    t_start = time.time()
    marks = []

    def mark(name):
        marks.append((name, time.time() - t_start))
        print("[%6.1fs] %s" % (marks[-1][1], name), flush=True)

    def maybe_stop(stage):
        if args.stop_after == stage:
            report(marks, None)
            sys.exit(0)

    forced = STAGES.index(args.force) if args.force else len(STAGES)

    def do(stage, target):
        """True if this stage must run."""
        if STAGES.index(stage) >= forced:
            return True
        return not (target and os.path.exists(os.path.join(ROOT, target)))

    free_gb = shutil.disk_usage(ROOT).free / 1e9
    if free_gb < args.min_free_gb:
        sys.exit("ABORT: only %.1f GB free (need %.1f). A render can die on ENOSPC "
                 "mid-encode -- and +faststart doubles the output's peak footprint."
                 % (free_gb, args.min_free_gb))

    vid = args.id
    if not vid:
        if args.url:
            vid = out(YTDLP + ["--no-warnings", "--print", "%(id)s", args.url]).splitlines()[-1]
        else:
            vid = os.path.splitext(os.path.basename(args.input))[0]
    print("id: %s | style: %s | disk free: %.1f GB" % (vid, args.style, free_gb))

    src_mp4 = "sources/%s.mp4" % vid
    wav = "audio/%s.16k.mono.wav" % vid
    words = "transcripts/%s.words.json" % vid       # the one expensive artifact
    overl = "temp/%s.overlays.json" % vid
    ass = "temp/%s.captions.ass" % vid
    dbg = "temp/%s.captions.debug.json" % vid
    final = "outputs/%s-captioned.mp4" % vid

    for d in ("sources", "audio", "transcripts", "temp", "outputs"):
        os.makedirs(os.path.join(ROOT, d), exist_ok=True)

    style_cfg = json.load(open(os.path.join(ROOT, args.style), encoding="utf-8"))

    # ---- download -------------------------------------------------------
    if args.input:
        if not os.path.exists(os.path.join(ROOT, src_mp4)):
            shutil.copy(args.input, os.path.join(ROOT, src_mp4))
        mark("source ready (local)")
    elif do("download", src_mp4):
        # Prefer avc1 (NVDEC-decodable) and, crucially, the ORIGINAL audio track:
        # YouTube AI auto-dubs appear as extra audio formats and a naive selector
        # can silently hand you a dubbed language.
        h = args.height
        fmt = ("bv*[height<=%d][vcodec^=avc1]+ba[format_note*=original]/"
               "bv*[height<=%d][vcodec^=avc1]+ba/"
               "bv*[height<=%d]+ba/b[height<=%d]") % (h, h, h, h)
        sh(YTDLP + ["-f", fmt, "--merge-output-format", "mp4",
                    "-o", src_mp4, "--write-info-json", "--no-overwrites",
                    "--no-warnings", "--newline", args.url])
        mark("downloaded")
    else:
        mark("download skipped (exists)")

    vw, vh, fps_raw = probe(src_mp4, "stream=width,height,r_frame_rate", "v:0")[:3]
    vw, vh = int(vw), int(vh)
    num, den = fps_raw.split("/")
    fps = int(num) / float(den)
    dur = float(probe(src_mp4, "format=duration")[0])
    print("   source: %dx%d @ %.3f fps, %.1fs" % (vw, vh, fps, dur))
    maybe_stop("download")

    # ---- audio ----------------------------------------------------------
    if do("audio", wav):
        sh(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", src_mp4,
            "-vn", "-sn", "-dn", "-map", "0:a:0", "-ac", "1", "-ar", "16000",
            "-c:a", "pcm_s16le", wav])
        mark("audio extracted")
    else:
        mark("audio skipped (exists)")
    maybe_stop("audio")

    # ---- transcribe + overlays, in parallel -----------------------------
    need_t = do("transcribe", words)
    need_o = (not args.no_overlays) and do("overlays", overl)
    if args.no_overlays:
        overl = None

    procs = {}
    if need_t:
        cmd = PY + ["scripts/transcribe-words.py", wav, "--out", words,
                    "--raw-out", "temp/%s.asr.raw.json" % vid,
                    "--model", args.model, "--device", args.device,
                    "--compute-type", args.compute_type]
        if args.lang:
            cmd += ["--language", args.lang]
        procs["transcribe"] = (subprocess.Popen(cmd, cwd=ROOT, env=ENV), None)
    if need_o:
        ocfg = style_cfg.get("overlays", {})
        ocmd = PY + ["scripts/detect-overlays.py", "--src", src_mp4, "--out", overl,
                     "--fps", str(args.overlay_fps)]
        if ocfg.get("auto"):
            ocmd += ["--auto"]
        elif ocfg.get("colour"):
            ocmd += ["--colour", ocfg["colour"]]
        if need_t and args.device == "cuda":
            ocmd += ["--no-hwaccel"]        # leave the GPU to the ASR model
        olog = open(os.path.join(ROOT, "temp/%s.overlays.log" % vid), "w", encoding="utf-8")
        procs["overlays"] = (subprocess.Popen(ocmd, cwd=ROOT, env=ENV,
                                              stdout=olog, stderr=subprocess.STDOUT), olog)

    for name in ("transcribe", "overlays"):        # ASR is the long pole; wait it first
        if name not in procs:
            mark("%s skipped (exists)" % name)
            continue
        p, log = procs[name]
        rc = p.wait()
        if log:
            log.close()
            for line in open(os.path.join(ROOT, "temp/%s.overlays.log" % vid),
                             encoding="utf-8").read().splitlines()[-4:]:
                print("   overlays| " + line)
        if rc != 0:
            sys.exit("FAILED: %s stage (exit %d)" % (name, rc))
        mark("%s done%s" % (name, " (parallel)" if len(procs) == 2 else ""))

    d = json.load(open(os.path.join(ROOT, words), encoding="utf-8"))
    ws = d["words"]
    cov = sum(x["end"] - x["start"] for x in ws) / d["duration"]
    tail = d["duration"] - ws[-1]["end"]
    print("   %d words | lang %s p=%.2f | coverage %.2f | tail gap %.1fs"
          % (len(ws), d["language"], d["language_probability"], cov, tail))
    if tail > 60:
        print("   WARNING: transcript ends %.0fs before the audio does -- "
              "possible early stop" % tail)
    if d["language_probability"] < 0.8:
        print("   WARNING: low language confidence -- check this is not a dubbed track")
    maybe_stop("transcribe")
    maybe_stop("overlays")

    # ---- ass ------------------------------------------------------------
    if do("ass", ass):
        cmd = PY + ["scripts/build-captions-ass.py", "--words", words,
                    "--style", args.style, "--out", ass, "--debug-out", dbg,
                    "--scale-to", str(vw), str(vh)]
        if overl:
            cmd += ["--overlays", overl]
        sh(cmd)
        mark("captions built")
    else:
        mark("ass skipped (exists)")
    maybe_stop("ass")

    # ---- verify ---------------------------------------------------------
    r = subprocess.run(PY + ["scripts/verify-captions.py", "--debug", dbg,
                             "--style", args.style, "--ass", ass,
                             "--fps", "%.6f" % fps,
                             "--samples", str(args.samples)],
                       cwd=ROOT, env=ENV)
    mark("sync verified" if r.returncode == 0 else "SYNC VERIFY FAILED")
    if r.returncode != 0:
        sys.exit("sync verification failed -- refusing to render")
    maybe_stop("verify")

    # ---- render ---------------------------------------------------------
    R = style_cfg.get("render", {})
    acodec = probe(src_mp4, "stream=codec_name", "a:0")
    audio = (["-c:a", "copy"] if acodec and acodec[0] == "aac"
             else ["-c:a", "aac", "-b:a", "192k", "-ar", "48000"])

    fontsdir = style_cfg["font"].get("fontsdir", "fonts")
    vf = "ass=filename=%s:fontsdir=%s:shaping=simple,format=yuv420p" % (ass, fontsdir)
    render_out = final
    pre = []
    if args.preview:
        s, dsec = args.preview
        pass_ass = "temp/%s.preview.ass" % vid
        cmd = PY + ["scripts/build-captions-ass.py", "--words", words,
                    "--style", args.style, "--out", pass_ass,
                    "--debug-out", "temp/%s.preview.debug.json" % vid,
                    "--scale-to", str(vw), str(vh),
                    "--range", str(s), str(s + dsec), "--time-offset", str(s)]
        if overl:
            cmd += ["--overlays", overl]
        sh(cmd)
        vf = "ass=filename=%s:fontsdir=%s:shaping=simple,format=yuv420p" % (pass_ass, fontsdir)
        pre = ["-ss", str(s), "-t", str(dsec)]
        render_out = "outputs/%s-preview.mp4" % vid

    sh(["ffmpeg", "-hide_banner", "-loglevel", "error", "-stats", "-y"]
       + pre + ["-i", src_mp4, "-vf", vf,
                "-c:v", R.get("encoder", "h264_nvenc"),
                "-preset", R.get("preset", "p6"), "-tune", "hq",
                "-rc", "vbr", "-cq", str(R.get("cq", 20)), "-b:v", "0",
                "-maxrate", R.get("maxrate", "20M"),
                "-bufsize", R.get("bufsize", "40M"),
                "-rc-lookahead", "32", "-spatial-aq", "1",
                "-aq-strength", str(R.get("aq_strength", 12)), "-temporal-aq", "1",
                "-bf", "3", "-g", "120", "-profile:v", "high", "-level", "4.2",
                "-pix_fmt", "yuv420p", "-fps_mode", "passthrough",
                "-movflags", "+faststart"] + audio + [render_out])
    mark("rendered")

    # ---- post-render checks + manifest (full renders only) --------------
    if not args.preview:
        op = os.path.join(ROOT, render_out)
        odur = float(probe(render_out, "format=duration")[0])
        obr = int(probe(render_out, "format=bit_rate")[0])
        boxes = first_boxes(op)
        fast = "moov" in boxes and "mdat" in boxes and boxes.index("moov") < boxes.index("mdat")
        problems = []
        if abs(odur - dur) > 0.5:
            problems.append("duration %.2fs vs source %.2fs" % (odur, dur))
        if obr < 1_500_000:
            problems.append("bitrate %.1f Mbps suspiciously low -- was -b:v 0 dropped? "
                            "(-cq is silently ignored without it)" % (obr / 1e6))
        if not fast:
            problems.append("faststart missing (box order: %s)" % boxes)
        if problems:
            for pr in problems:
                print("   POST-CHECK FAIL: " + pr)
            sys.exit("output failed post-render checks")
        print("   post-checks OK: duration %.1fs | %.1f Mbps | faststart | %s"
              % (odur, obr / 1e6, boxes))
        mark("output verified")

        manifest = dict(
            id=vid, url=args.url, source=dict(w=vw, h=vh, fps=fps, duration=dur),
            style=dict(path=args.style, md5=md5(os.path.join(ROOT, args.style))),
            words=dict(path=words, md5=md5(os.path.join(ROOT, words)), count=len(ws)),
            asr=dict(model=args.model, device=args.device,
                     compute_type=args.compute_type, language=d["language"]),
            versions=dict(
                yt_dlp=out(YTDLP + ["--version"]),
                ffmpeg=out(["ffmpeg", "-version"]).splitlines()[0],
            ),
            argv=sys.argv[1:], timings={n: round(t, 1) for n, t in marks},
            output=dict(path=render_out, bytes=os.path.getsize(op),
                        duration=odur, bit_rate=obr),
        )
        mpath = os.path.join(ROOT, "outputs/%s.manifest.json" % vid)
        with open(mpath, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=1)
        print("   manifest: outputs/%s.manifest.json" % vid)

    report(marks, render_out)


def report(marks, final):
    print("\n" + "=" * 58)
    prev = 0.0
    for name, t in marks:
        print("  %-28s %7.1fs  (+%.1fs)" % (name, t, t - prev))
        prev = t
    print("=" * 58)
    print("TOTAL: %.1fs (%.1f min)" % (prev, prev / 60))
    if final:
        p = os.path.join(ROOT, final)
        if os.path.exists(p):
            print("OUTPUT: %s  (%.2f GB)" % (p, os.path.getsize(p) / 1e9))


if __name__ == "__main__":
    main()
