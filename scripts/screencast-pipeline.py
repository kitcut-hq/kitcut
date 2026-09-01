#!/usr/bin/env python
"""One command from raw recordings to an uploaded, verified film -- with every
stage cached and one deliberate stop.

The first silent-screencast edit was ~40 hand-typed commands over six hours,
each one watched, several repeated because an earlier one had been redone.
This runs the same stages in the only order that does not waste work:

  import    raw captures + phone recordings -> projects/<id>/sources, ordered
  proxies   transcode once at the working size; everything after reads these
  activity  per-region motion tracks; the panel divider found, not assumed
  ocr       read every sampled frame ONCE (cached); rules are a cheap pass
  track     follow each secret's pixels; POOLED across the session's sources
  recall    measure the tracker against the OCR hits -- below 98%, stop here
  review    the STOP: a before/after sheet of every redaction; approve or not
  smoke     30 s of the busiest source through the full graph; a minute
  render    per-source pieces, content-addressed, joined by stream copy
  gate      the secrets' own pixels searched on the render; --patch and loop
  upload    unlisted, only after the gate is clean and the look approved

Every stage fingerprints its inputs into temp/pipeline/<stage>.json and is
skipped when nothing it depends on has changed, so a rerun after one manifest
edit costs one piece and one gate, not a morning.

Invoke as:  python scripts/screencast-pipeline.py --project <id> --target 8:00
"""
import sys
import os
import json
import time
import glob
import hashlib
import argparse
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import
import _project  # noqa: E402

ROOT = _env.ROOT
HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

STAGES = ["import", "proxies", "activity", "ocr", "track", "recall", "review",
          "smoke", "render", "gate", "upload"]


def fmt(t):
    return f"{int(t) // 60}:{t % 60:04.1f}"


def stat_sig(paths):
    """size+mtime of every path that exists; the identity of an input set."""
    h = hashlib.sha1()
    for p in sorted(paths):
        try:
            st = os.stat(p)
            h.update(f"{p}:{st.st_size}:{int(st.st_mtime)}|".encode())
        except OSError:
            h.update(f"{p}:missing|".encode())
    return h.hexdigest()[:16]


class Pipeline:
    def __init__(self, pid, args):
        self.pid = pid
        self.args = args
        self.pdir = os.path.join(_project.projects_dir(), pid)
        self.mpath = os.path.join(self.pdir, "screen.json")
        self.tdir = os.path.join(self.pdir, "temp")
        self.state_dir = os.path.join(self.tdir, "pipeline")
        os.makedirs(self.state_dir, exist_ok=True)
        self.timings = []

    # -- manifest helpers -------------------------------------------------
    def man(self):
        return json.load(open(self.mpath, encoding="utf-8"))

    def save_man(self, m):
        with open(self.mpath, "w", encoding="utf-8") as f:
            json.dump(m, f, ensure_ascii=False, indent=2)

    def rel(self, p):
        return os.path.relpath(p, ROOT).replace("\\", "/")

    def sources(self):
        return [s for s in self.man().get("sources", []) if not s.get("skip")]

    def base(self, s):
        return os.path.splitext(os.path.basename(s["path"]))[0]

    def proxy_or_src(self, s):
        p = s.get("proxy")
        if p and os.path.exists(_env.resolve(p)):
            return _env.resolve(p)
        return _env.resolve(s["path"])

    # -- caching ---------------------------------------------------------
    def done_path(self, stage):
        return os.path.join(self.state_dir, stage + ".json")

    def is_done(self, stage, sig):
        if stage in self.args.force:
            return False
        try:
            d = json.load(open(self.done_path(stage), encoding="utf-8"))
            return d.get("sig") == sig
        except (OSError, ValueError):
            return False

    def mark(self, stage, sig, secs, note=""):
        with open(self.done_path(stage), "w", encoding="utf-8") as f:
            json.dump({"sig": sig, "secs": round(secs, 1), "note": note,
                       "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, f)

    def run(self, argv, what, ok_codes=(0,)):
        """A stage subprocess with its output streamed, never captured."""
        print(f"    $ {' '.join(os.path.basename(a) if i == 1 else a for i, a in enumerate(argv))}",
              flush=True)
        r = subprocess.run([PY] + argv, cwd=ROOT)
        if r.returncode not in ok_codes:
            raise SystemExit(f"\n  stage failed: {what} (exit {r.returncode})")
        return r.returncode

    def run_parallel(self, jobs, what, workers=None):
        """Run per-source jobs concurrently, one process each.

        OCR and template matching are CPU-bound and single-threaded in
        practice: onnxruntime here has no CUDA provider, so RapidOCR runs on
        the CPU, and the first pipeline left fifteen of sixteen cores idle
        while it read one recording at a time. Sources are independent, so
        the honest fix is processes, not a GPU build that would replace the
        onnxruntime sherpa-onnx needs.

        Output is captured per job and printed when it finishes, so two
        streams never interleave into nonsense.
        """
        workers = workers or self.args.jobs
        if workers <= 1 or len(jobs) <= 1:
            for argv, label in jobs:
                self.run(argv, label)
            return
        import concurrent.futures as cf
        print(f"    {len(jobs)} job(s) on {workers} worker(s)", flush=True)
        fails = []
        with cf.ThreadPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(subprocess.run, [PY] + argv, cwd=ROOT,
                              capture_output=True, text=True): (argv, label)
                    for argv, label in jobs}
            for fut in cf.as_completed(futs):
                argv, label = futs[fut]
                r = fut.result()
                tail = [ln for ln in (r.stdout or "").splitlines()
                        if ln.strip() and not ln.lstrip().startswith("...")]
                print(f"    -- {label}")
                for ln in tail[-6:]:
                    print(f"       {ln}")
                if r.returncode != 0:
                    fails.append((label, (r.stderr or "").strip().splitlines()[-6:]))
        if fails:
            for label, err in fails:
                print(f"    FAILED {label}:")
                for ln in err:
                    print(f"       {ln}")
            raise SystemExit(f"\n  stage failed: {what}")

    # -- stages ----------------------------------------------------------
    def st_import(self):
        have = glob.glob(os.path.join(self.pdir, "sources", "*.mp4"))
        if have and os.path.exists(self.mpath):
            return "skip", f"{len(have)} source(s) present"
        argv = [os.path.join(HERE, "import-footage.py"), "--project", self.pid]
        if self.args.since:
            argv += ["--since", self.args.since]
        self.run(argv, "import-footage")
        return "ran", ""

    def st_proxies(self):
        srcs = [_env.resolve(s["path"]) for s in self.sources()]
        sig = stat_sig(srcs + [self.mpath_sources_only()])
        if self.is_done("proxies", sig):
            return "cached", ""
        self.run([os.path.join(HERE, "make-proxies.py"), "--manifest", self.rel(self.mpath)],
                 "make-proxies")
        return "ran", sig

    def mpath_sources_only(self):
        """A file whose identity changes only when the source LIST changes."""
        p = os.path.join(self.state_dir, "sources.sig")
        lst = json.dumps([s["path"] for s in self.sources()])
        cur = open(p, encoding="utf-8").read() if os.path.exists(p) else ""
        if cur != lst:
            with open(p, "w", encoding="utf-8") as f:
                f.write(lst)
        return p

    def st_activity(self):
        m = self.man()
        if not (m.get("regions") or {}).get("panel"):
            longest = max(self.sources(), key=lambda s: os.path.getsize(self.proxy_or_src(s)))
            self.run([os.path.join(HERE, "screen-activity.py"), "--src",
                      self.rel(self.proxy_or_src(longest)), "--find-panel",
                      "--write-regions", self.rel(self.mpath)], "find-panel")
            m = self.man()
        ins = [self.proxy_or_src(s) for s in self.sources()]
        sig = stat_sig(ins) + hashlib.sha1(json.dumps(m.get("regions"), sort_keys=True)
                                           .encode()).hexdigest()[:8]
        if self.is_done("activity", sig):
            return "cached", ""
        m = self.man()
        for s in self.sources():
            out = os.path.join(self.tdir, self.base(s) + ".activity.json")
            argv = [os.path.join(HERE, "screen-activity.py"), "--src",
                    self.rel(self.proxy_or_src(s)), "--out", self.rel(out)]
            # the panel regions were found on a landscape desktop capture; a
            # portrait phone clip has no such panel, and applying the desktop
            # split there would speed up whatever happens in its right strip
            info = subprocess.run(
                ["ffprobe", "-v", "error", "-select_streams", "v:0",
                 "-show_entries", "stream=width,height", "-of", "csv=p=0",
                 self.proxy_or_src(s)], capture_output=True, text=True).stdout
            w, _, h = info.strip().partition(",")
            if w and h and int(w) >= int(h):
                argv += ["--ignore-from", self.rel(self.mpath)]
            self.run(argv, f"activity {self.base(s)}")
            s["activity"] = self.rel(out)
        for s2 in m["sources"]:
            for s in self.sources():
                if s2["path"] == s["path"]:
                    s2["activity"] = s["activity"]
        self.save_man(m)
        return "ran", sig

    def st_ocr(self):
        ins = [self.proxy_or_src(s) for s in self.sources()]
        rules_sig = stat_sig([os.path.join(HERE, "scan-pii.py")])
        sig = stat_sig(ins) + rules_sig
        if self.is_done("ocr", sig):
            return "cached", ""
        jobs = []
        for s in self.sources():
            base = self.base(s)
            out = os.path.join(self.tdir, "pii", base + ".pii.json")
            cache = os.path.join(self.tdir, "ocr", base + ".ocr.json")
            argv = [os.path.join(HERE, "scan-pii.py"), "--src",
                    self.rel(self.proxy_or_src(s)), "--out", self.rel(out),
                    "--ocr-cache", self.rel(cache), "--fps", str(self.args.ocr_fps),
                    "--width", "1600", "--report"]
            if os.path.exists(cache):
                argv.append("--from-cache")
            jobs.append((argv, f"ocr {base}"))
        self.run_parallel(jobs, "ocr")
        return "ran", sig

    def tracked_sources(self):
        """Sources that get a tracker: have OCR hits, not opted out."""
        out = []
        for s in self.sources():
            if s.get("track") is False:
                continue
            pii = os.path.join(self.tdir, "pii", self.base(s) + ".pii.json")
            if not os.path.exists(pii):
                continue
            d = json.load(open(pii, encoding="utf-8"))
            if d.get("hits"):
                out.append(s)
        return out

    def st_track(self):
        piis = glob.glob(os.path.join(self.tdir, "pii", "*.pii.json"))
        ins = [self.proxy_or_src(s) for s in self.sources()] + piis + \
              [os.path.join(HERE, "track-blur.py")]
        sig = stat_sig(ins)
        if self.is_done("track", sig):
            return "cached", ""
        m = self.man()
        jobs = []
        for s in self.tracked_sources():
            tdir = os.path.join(self.tdir, "track", self.base(s))
            jobs.append(([os.path.join(HERE, "track-blur.py"), "--src",
                          self.rel(self.proxy_or_src(s)), "--outdir", self.rel(tdir),
                          "--manifest", self.rel(self.mpath)], f"track {self.base(s)}"))
            for s2 in m["sources"]:
                if s2["path"] == s["path"]:
                    s2["track"] = self.rel(tdir)
        # the manifest must name the track dirs BEFORE the jobs run: each
        # tracker reads it to pool the other sources' scans
        self.save_man(m)
        self.run_parallel(jobs, "track")
        return "ran", sig

    def st_recall(self):
        worst = 1.0
        for s in self.tracked_sources():
            if not s.get("track"):
                continue
            rc = self.run([os.path.join(HERE, "track-blur.py"), "--src",
                           self.rel(self.proxy_or_src(s)), "--outdir", s["track"],
                           "--manifest", self.rel(self.mpath), "--recall",
                           "--recall-min", str(self.args.recall_min)],
                          f"recall {self.base(s)}", ok_codes=(0, 1))
            if rc == 1:
                worst = 0.0
        if worst < 1.0:
            raise SystemExit(f"\n  STOP: recall below {self.args.recall_min:.0%} on at least one "
                             f"source. Fix the tracker or add hand rects, then rerun.")
        return "ran", ""

    def st_review(self):
        rc = self.run([os.path.join(HERE, "redaction-review.py"), "--manifest",
                       self.rel(self.mpath), "--check"], "review --check", ok_codes=(0, 3))
        if rc == 0:
            return "approved", ""
        self.run([os.path.join(HERE, "redaction-review.py"), "--manifest",
                  self.rel(self.mpath)], "review sheet", ok_codes=(0, 2))
        if self.args.approve:
            self.run([os.path.join(HERE, "redaction-review.py"), "--manifest",
                      self.rel(self.mpath), "--approve"], "review --approve")
            return "approved", "with --approve"
        raise SystemExit("\n  STOP: look at temp/review/redaction-sheet.jpg, then rerun "
                         "with --approve (or change the manifest and rerun).")

    def cut_argv(self):
        argv = [os.path.join(HERE, "screen-cut.py"), "--manifest", self.rel(self.mpath)]
        if self.args.target:
            argv += ["--target", self.args.target]
        return argv

    def st_smoke(self):
        self.run(self.cut_argv() + ["--smoke"], "smoke")
        return "ran", ""

    def st_render(self):
        self.run(self.cut_argv(), "render")
        return "ran", ""

    def st_gate(self):
        for rnd in range(1, self.args.gate_rounds + 1):
            argv = [os.path.join(HERE, "render-gate.py"), "--manifest", self.rel(self.mpath)]
            if self.args.target:
                argv += ["--target", self.args.target]
            if rnd < self.args.gate_rounds:
                argv.append("--patch")
            rc = self.run(argv, f"gate round {rnd}", ok_codes=(0, 1))
            if rc == 0:
                return "clean", f"round {rnd}"
            if rnd < self.args.gate_rounds:
                print(f"\n  gate round {rnd}: leaks patched into the manifest; re-rendering")
                self.run(self.cut_argv(), f"render after gate {rnd}")
        raise SystemExit(f"\n  STOP: the gate still finds secrets after "
                         f"{self.args.gate_rounds} round(s). See temp/gate.json.")

    def st_upload(self):
        if not self.args.upload:
            return "skip", "no --upload"
        m = self.man()
        out = _env.resolve(m["output"])
        argv = [os.path.join(HERE, "yt-upload.py"), self.rel(out),
                "--title", self.args.title or f"{self.pid} (draft)",
                "--channel", self.args.channel, "--privacy", self.args.upload]
        desc = os.path.join(self.pdir, "description.txt")
        if os.path.exists(desc):
            argv += ["--description-file", self.rel(desc)]
        self.run(argv, "yt-upload")
        return "ran", ""

    # -- driver ----------------------------------------------------------
    def go(self):
        start_at = STAGES.index(self.args.start) if self.args.start else 0
        stop_at = STAGES.index(self.args.stop) if self.args.stop else len(STAGES) - 1
        print(f"{self.pid}: stages {STAGES[start_at]} -> {STAGES[stop_at]}"
              f"{'  target ' + self.args.target if self.args.target else ''}")
        t_all = time.time()
        for i, stage in enumerate(STAGES):
            if i < start_at or i > stop_at:
                continue
            fn = getattr(self, "st_" + stage)
            t0 = time.time()
            print(f"\n  [{i + 1:>2}/{len(STAGES)}] {stage:<9}", flush=True)
            state, note = fn()
            secs = time.time() - t0
            if state == "ran" and note:
                self.mark(stage, note, secs)
            self.timings.append((stage, state, secs))
            print(f"  [{i + 1:>2}/{len(STAGES)}] {stage:<9} {state:<9} {fmt(secs):>7}"
                  f"{'  ' + note if note and state != 'ran' else ''}")
        print(f"\n  total {fmt(time.time() - t_all)}")
        for stage, state, secs in self.timings:
            print(f"    {stage:<9} {state:<9} {fmt(secs):>7}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--target", help="film length, e.g. 8:00 (solves both speeds)")
    ap.add_argument("--start", choices=STAGES, help="first stage to run")
    ap.add_argument("--stop", choices=STAGES, help="last stage to run")
    ap.add_argument("--force", action="append", default=[], choices=STAGES,
                    help="re-run this stage even if its inputs are unchanged")
    ap.add_argument("--approve", action="store_true",
                    help="you have looked at the review sheet: record approval and go on")
    ap.add_argument("--upload", choices=["unlisted", "private", "public"],
                    help="upload after a clean gate; unlisted is the review default")
    ap.add_argument("--title")
    ap.add_argument("--channel", default="@instafill_ai")
    ap.add_argument("--since", help="import: only captures from this date (YYYY-MM-DD)")
    ap.add_argument("--jobs", "-j", type=int,
                    default=max(1, min(6, (os.cpu_count() or 4) // 3)),
                    help="parallel per-source processes for the CPU-bound "
                         "stages (ocr, track). Default is a third of the "
                         "cores, capped at 6: onnxruntime already uses "
                         "several threads per process, so more workers than "
                         "that mostly contend.")
    ap.add_argument("--ocr-fps", type=float, default=0.25)
    ap.add_argument("--recall-min", type=float, default=0.98)
    ap.add_argument("--gate-rounds", type=int, default=3,
                    help="gate -> patch -> render rounds before giving up")
    ap.add_argument("--list", action="store_true",
                    help="show which stages would run and which are cached")
    args = ap.parse_args()

    p = Pipeline(args.project, args)
    if not os.path.exists(p.mpath) and not os.path.isdir(os.path.join(p.pdir, "sources")):
        print(f"{args.project}: no manifest and no sources yet; the import stage will create both")
    if args.list:
        for i, stage in enumerate(STAGES):
            d = p.done_path(stage)
            state = "done " if os.path.exists(d) else "todo "
            note = ""
            if os.path.exists(d):
                dd = json.load(open(d, encoding="utf-8"))
                note = f"{fmt(dd.get('secs', 0))} on {dd.get('utc', '')}"
            print(f"  [{i + 1:>2}] {stage:<9} {state} {note}")
        return
    p.go()


if __name__ == "__main__":
    main()
