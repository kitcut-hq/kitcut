#!/usr/bin/env python
"""Turn the user's own review recording into a ticket list with frames attached.

The user reviews a cut the way a person does: scrubs the film in a player,
records the screen, and says out loud what is wrong -- "on this frame the
phone number is shown right in the chat". The film's own timecode sits in
the player's bottom-left corner. That recording is the highest-value input
an editing session gets, and turning it into actionable items was a
forty-minute manual job the first time: transcribe, read the timecode off
each frame, map film time back through the cut to a source and a source
time, write the table.

This does all of it. Every spoken remark becomes one row: when it was said,
what the film's timecode read at that moment, which source that maps to and
where in it, and the words. The mapping goes through the same plan
`screen-cut.py` renders from, so it is exact, not estimated. Where the
timecode cannot be read the row says so instead of guessing.

It writes `review-notes.md` next to the manifest (appending a dated pass) so
the reviewer's language is kept, and `temp/review/ingest.json` for tools.
It changes nothing else: what to DO about each remark is a decision, and the
manifest is edited by the person or the gate, not by this.

Invoke as:  python scripts/review-ingest.py --manifest projects/<id>/screen.json --recording <review.mp4> --target 8:00
"""
import sys
import os
import re
import json
import time
import argparse
import subprocess
import importlib.util

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import
import _project  # noqa: E402

ROOT = _env.ROOT
HERE = os.path.dirname(os.path.abspath(__file__))

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def load(name):
    spec = importlib.util.spec_from_file_location(
        name.replace("-", "_"), os.path.join(HERE, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def fmt(t):
    return f"{int(t) // 60}:{t % 60:04.1f}"


def transcribe(rec, outdir, language):
    """Segments with times, via the repo's own transcriber."""
    wav = os.path.join(outdir, "review.wav")
    raw = os.path.join(outdir, "review.raw.json")
    words = os.path.join(outdir, "review.words.json")
    if not os.path.exists(raw):
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", rec, "-vn", "-ac", "1",
                        "-ar", "16000", wav], check=True)
        argv = [sys.executable, os.path.join(HERE, "transcribe-words.py"), wav,
                "--out", words, "--raw-out", raw]
        if language:
            argv += ["--language", language]
        subprocess.run(argv, check=True, cwd=ROOT)
    d = json.load(open(raw, encoding="utf-8"))
    segs = d.get("segments") if isinstance(d, dict) else d
    return [{"start": float(s["start"]), "end": float(s["end"]),
             "text": s["text"].strip()} for s in segs if s.get("text", "").strip()]


def group_remarks_by_silence(segs, gap=2.5):
    """Merge segments spoken close together into one remark."""
    out = []
    for s in segs:
        if out and s["start"] - out[-1]["end"] <= gap:
            out[-1]["end"] = s["end"]
            out[-1]["text"] += " " + s["text"]
        else:
            out.append(dict(s))
    return out


def read_timecode(rec, t, crop):
    """OCR the player's timecode from the corner at time t -> film seconds."""
    from rapidocr_onnxruntime import RapidOCR
    import numpy as np
    x, y, w, h = crop
    out = subprocess.run(
        ["ffmpeg", "-v", "error", "-nostdin", "-ss", f"{t:.2f}", "-i", rec,
         "-frames:v", "1", "-vf", f"crop=iw*{w}:ih*{h}:iw*{x}:ih*{y},scale=760:-2",
         "-pix_fmt", "bgr24", "-f", "rawvideo", "-"], capture_output=True).stdout
    if not out:
        return None
    # width 760; height follows the crop's aspect
    hh = len(out) // (760 * 3)
    img = np.frombuffer(out[:hh * 760 * 3], np.uint8).reshape(hh, 760, 3)
    if not hasattr(read_timecode, "ocr"):
        read_timecode.ocr = RapidOCR()
    res, _ = read_timecode.ocr(img)
    for _box, text, _conf in (res or []):
        m = re.search(r"(\d{1,2}):(\d{2})\s*/\s*\d{1,2}:\d{2}", text)
        if m:
            return int(m.group(1)) * 60 + int(m.group(2))
    return None


def build_plans(sc, man, cfg):
    plans = []
    for s in man["sources"]:
        if s.get("skip"):
            continue
        p = sc.plan_source(s, cfg)
        chosen = _env.resolve(s["path"])
        if s.get("proxy") and os.path.exists(_env.resolve(s["proxy"])):
            chosen = _env.resolve(s["proxy"])
        p["path"] = chosen
        p["source_path"] = _env.resolve(s["path"])
        plans.append(p)
    return plans


def locate(plans, film_t):
    t = 0.0
    for p in plans:
        for seg in p["segments"]:
            if t <= film_t < t + seg["out"]:
                return os.path.basename(p["source_path"]), seg["start"] + (film_t - t) * seg["speed"]
            t += seg["out"]
    return None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--recording", required=True, help="the user's screen recording of their review")
    ap.add_argument("--target", help="the --target the reviewed film was rendered with")
    ap.add_argument("--language", default="uk", help="spoken language of the review; '' to autodetect")
    ap.add_argument("--timecode-crop", default="0.02,0.91,0.22,0.07",
                    help="x,y,w,h fractions of the recording where the player's "
                         "timecode sits (default: bottom-left, as in Edge's viewer)")
    ap.add_argument("--dry-run", action="store_true",
                    help="transcribe and map, print the table, write nothing")
    args = ap.parse_args()

    sc = load("screen-cut")
    mpath = _env.resolve(args.manifest)
    man = json.load(open(mpath, encoding="utf-8"))
    cfg = dict(sc.DEFAULTS)
    cfg.update(man.get("cut") or {})
    if args.target:
        cfg = sc.solve_target(man, cfg, sc.parse_hms(args.target))
    plans = build_plans(sc, man, cfg)
    rec = _env.resolve(args.recording)
    pdir = _project.find_project_dir(mpath) or os.path.dirname(mpath)
    outdir = os.path.join(pdir, "temp", "review")
    os.makedirs(outdir, exist_ok=True)
    crop = [float(v) for v in args.timecode_crop.split(",")]

    print(f"review-ingest: {os.path.basename(rec)}")
    segs = transcribe(rec, outdir, args.language or None)
    # One remark per FRAME THE REVIEWER PAUSED ON, not per pause in speech.
    # Speech-gap grouping merged three separate complaints made in one breath
    # at 3:16-3:45 and split one complaint made with a thinking pause. The
    # reviewer's own method is the right unit: they scrub to a frame, then
    # talk; the film timecode in the corner is constant for the whole remark
    # and changes when the next one starts. So read the timecode per segment
    # and group consecutive segments that read the same.
    for sg in segs:
        sg["film_t"] = read_timecode(rec, min(sg["end"], sg["start"] + 0.8), crop)
    remarks = []
    for sg in segs:
        if remarks and sg["film_t"] == remarks[-1]["film_t"]                 and sg["start"] - remarks[-1]["end"] <= 12.0:
            remarks[-1]["end"] = sg["end"]
            remarks[-1]["text"] += " " + sg["text"]
        else:
            remarks.append(dict(sg))
    print(f"  {len(segs)} segment(s) -> {len(remarks)} remark(s), one per frame paused on")

    rows = []
    for r in remarks:
        film_t = r["film_t"]
        src, st = (locate(plans, film_t) if film_t is not None else (None, None))
        rows.append({"said_at": round(r["start"], 1), "film_t": film_t,
                     "source": src, "source_t": round(st, 1) if st is not None else None,
                     "text": r["text"]})

    print(f"\n  {'said':>6} {'film':>6} {'source @ time':<40} remark")
    for w in rows:
        film = fmt(w["film_t"]) if w["film_t"] is not None else "?"
        src = f"{w['source']} @ {fmt(w['source_t'])}" if w["source"] else "(timecode not read)"
        print(f"  {fmt(w['said_at']):>6} {film:>6} {src:<40} {w['text'][:70]}")

    if args.dry_run:
        return

    with open(os.path.join(outdir, "ingest.json"), "w", encoding="utf-8") as f:
        json.dump({"recording": rec, "rows": rows}, f, ensure_ascii=False, indent=1)
    notes = os.path.join(pdir, "review-notes.md")
    stamp = time.strftime("%Y-%m-%d %H:%M")
    with open(notes, "a", encoding="utf-8") as f:
        f.write(f"\n\n## Review pass ingested {stamp} — `{os.path.basename(rec)}`\n\n")
        f.write("| said at | film | source @ source time | remark | disposition |\n|---|---|---|---|---|\n")
        for w in rows:
            film = fmt(w["film_t"]) if w["film_t"] is not None else "?"
            src = f"`{w['source']}` @ {fmt(w['source_t'])}" if w["source"] else "—"
            f.write(f"| {fmt(w['said_at'])} | {film} | {src} | {w['text']} | |\n")
        f.write("\nDisposition column is for the editor: what changed because of each row.\n")
    pid = os.path.basename(pdir)
    _project.record(pid, "review-ingest",
                    note=f"{len(rows)} remark(s) from {os.path.basename(rec)} mapped to sources; "
                         f"see review-notes.md")
    print(f"\n  appended {len(rows)} row(s) to {_project.norm(notes)}")


if __name__ == "__main__":
    main()
