#!/usr/bin/env python
"""Cut a list of episodes out of one long video into standalone clips.

Boundaries are given either as seconds or, better, as a phrase from the
transcript -- `start_text` / `end_text` / `end_before_text` are resolved against
`transcripts/<id>.words.json`, so a manifest keeps reading like the edit
decisions you actually made ("start where she says X") instead of magic numbers.

Cuts are frame-accurate: the source is re-encoded rather than stream-copied, so
a clip starts on the requested frame and not on the preceding keyframe. Pass
--copy for an instant, keyframe-snapped cut when that is good enough.

Each clip is skipped when its output already exists (--force reruns it), so
re-running after editing one entry only re-renders that entry.

Invoke as:  python -X utf8 -E scripts/cut-clips.py --manifest config/clips/<id>.json
"""
import sys, os, json, argparse, subprocess, shutil
from importlib import import_module

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
_outline = import_module("transcript-outline")   # hyphen: not importable by name
_handle = import_module("handle-overlay")

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

ENV = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}

DEFAULT_RENDER = {
    "encoder": "h264_nvenc", "preset": "p5", "cq": 21,
    "maxrate": "16M", "bufsize": "32M", "audio_bitrate": "192k",
}


def run(cmd, **kw):
    return subprocess.run(cmd, env=ENV, **kw)


def probe(path):
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
               "-of", "json", path], capture_output=True, text=True)
    if out.returncode:
        sys.exit("ffprobe failed on %s\n%s" % (path, out.stderr.strip()))
    return float(json.loads(out.stdout)["format"]["duration"])


def hhmmss(t):
    return "%02d:%05.2f" % (int(t) // 60, t % 60)


def resolve(clip, words, pad_head, pad_tail):
    """Return (start, end) in seconds, padded but never into a neighbouring word.

    A pad is a guess about silence. When the transcript says a word is still
    being spoken inside the pad, meet it halfway instead -- that keeps the head
    of a clip from opening on the tail of the previous sentence.
    """
    def phrase(key):
        hit = _outline.find(words, clip[key])
        if hit is None:
            sys.exit("%s: phrase not found in transcript: %r" % (clip["id"], clip[key]))
        return hit

    anchor_a = anchor_b = None
    if "start" in clip:
        start = float(clip["start"])
    elif "start_text" in clip:
        anchor_a, _ = phrase("start_text")
        start = anchor_a
    else:
        sys.exit("%s: needs start or start_text" % clip["id"])

    if "end" in clip:
        end = float(clip["end"])
    elif "duration" in clip:
        end = start + float(clip["duration"])
    elif "end_text" in clip:
        _, anchor_b = phrase("end_text")
        end = anchor_b
    elif "end_before_text" in clip:
        # cut just before the next thought begins
        anchor_b, _ = phrase("end_before_text")
        end = anchor_b
    else:
        sys.exit("%s: needs end, duration, end_text or end_before_text" % clip["id"])

    if anchor_a is not None:
        prev_end = max([w["end"] for w in words if w["end"] <= anchor_a + 1e-6],
                       default=0.0)
        start = max(anchor_a - pad_head, min(anchor_a, (prev_end + anchor_a) / 2.0))
    if anchor_b is not None and "end_before_text" in clip:
        prev_end = max([w["end"] for w in words if w["end"] <= anchor_b + 1e-6],
                       default=anchor_b)
        end = min(anchor_b, max(prev_end, (prev_end + anchor_b) / 2.0) + pad_tail)
    elif anchor_b is not None:
        next_start = min([w["start"] for w in words if w["start"] >= anchor_b - 1e-6],
                         default=None)
        end = anchor_b + pad_tail
        if next_start is not None and next_start < end:
            end = (anchor_b + next_start) / 2.0

    if end <= start:
        sys.exit("%s: end (%.2f) is not after start (%.2f)" % (clip["id"], end, start))
    return max(0.0, start), end


def cut(src, dst, start, dur, render, copy, overlay=None):
    """overlay is (png_paths, filter_complex, out_label) from handle-overlay."""
    extra = []
    if copy:
        if overlay:
            sys.exit("--copy cannot burn in a handle: stream copy does not filter")
        args = ["-c", "copy"]
    else:
        if overlay:
            pngs, fc, label = overlay
            for p in pngs:
                extra += ["-i", p]
            # the badge animates on the OUTPUT clock, which -ss rebases to 0,
            # so every clip starts its cycle at the same place
            args = ["-filter_complex", fc, "-map", "[%s]" % label, "-map", "0:a:0"]
        else:
            args = ["-map", "0:v:0", "-map", "0:a:0"]
        args += ["-c:v", render["encoder"], "-preset", render["preset"],
                 "-rc", "vbr", "-cq", str(render["cq"]),
                 # NVENC ignores -cq unless the average bitrate target is unset
                 "-b:v", "0", "-maxrate", render["maxrate"], "-bufsize", render["bufsize"],
                 "-pix_fmt", "yuv420p",
                 "-c:a", "aac", "-b:a", render["audio_bitrate"], "-ac", "2"]
    tmp = dst + ".part.mp4"
    # -ss goes BEFORE -i so it seeks the input: ffmpeg decodes from the
    # preceding keyframe and discards what precedes it, landing the cut on the
    # requested frame. -t goes AFTER every input, because an option placed
    # before an -i attaches to THAT input -- with badge PNGs in the graph a -t
    # sitting next to the source would silently become the PNG's duration and
    # leave the clip running to the end of the source.
    cmd = (["ffmpeg", "-hide_banner", "-v", "error", "-nostdin",
            "-ss", "%.3f" % start, "-i", src]
           + extra + args + ["-t", "%.3f" % dur, "-movflags", "+faststart", "-y", tmp])
    if run(cmd).returncode:
        if os.path.exists(tmp):
            os.remove(tmp)
        sys.exit("ffmpeg failed for %s" % dst)
    os.replace(tmp, dst)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--only", help="comma-separated clip ids to build")
    ap.add_argument("--outdir", help="override the manifest outdir")
    ap.add_argument("--copy", action="store_true",
                    help="stream-copy instead of re-encoding (fast, keyframe-snapped)")
    ap.add_argument("--force", action="store_true", help="rebuild existing outputs")
    ap.add_argument("--list", action="store_true",
                    help="resolve boundaries and print the plan, cut nothing")
    ap.add_argument("--handle", help="burn in this social handle, e.g. @name "
                                     "(overrides the manifest)")
    ap.add_argument("--handle-preset", help="override the manifest handle preset")
    ap.add_argument("--no-handle", action="store_true", help="skip the handle badge")
    args = ap.parse_args()

    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            sys.exit("%s not on PATH" % tool)

    m = json.load(open(args.manifest, encoding="utf-8"))
    src = m["source"]
    if not os.path.exists(src):
        sys.exit("source not found: %s" % src)
    outdir = args.outdir or m.get("outdir", "outputs/shorts")
    os.makedirs(outdir, exist_ok=True)
    prefix = m.get("prefix", "")
    pad = m.get("pad", {})
    pad_head, pad_tail = float(pad.get("head", 0.12)), float(pad.get("tail", 0.30))
    render = dict(DEFAULT_RENDER, **m.get("render", {}))
    words = _outline.load_words(m["words"]) if m.get("words") else []
    src_dur = probe(src)

    # One badge render for the whole manifest: every clip shares the source's
    # dimensions, and the animation is driven by the output clock, so each clip
    # starts its cycle from the same place.
    hcfg = dict(m.get("handle") or {})
    if args.handle:
        hcfg["text"] = args.handle
    if args.handle_preset:
        hcfg["preset"] = args.handle_preset
    overlay = None
    if hcfg.get("text") and not args.no_handle:
        w, h = _handle.probe_dims(src)
        overlay = _handle.prepare(hcfg.get("preset", _handle.DEFAULT_PRESET),
                                  hcfg["text"], w, h, m.get("tmp", "temp"))
        print("handle %s  (%s)" % (hcfg["text"],
                                   hcfg.get("preset", _handle.DEFAULT_PRESET)))

    wanted = set(x.strip() for x in args.only.split(",")) if args.only else None
    plan = []
    for clip in m["clips"]:
        if wanted and clip["id"] not in wanted:
            continue
        start, end = resolve(clip, words, pad_head, pad_tail)
        if end > src_dur:
            sys.exit("%s: end %.2f is past the source (%.2f)" % (clip["id"], end, src_dur))
        name = "%s-%s.mp4" % (prefix, clip["id"]) if prefix else "%s.mp4" % clip["id"]
        plan.append((clip, start, end, os.path.join(outdir, name)))

    if wanted:
        missing = wanted - set(c["id"] for c, _, _, _ in plan)
        if missing:
            sys.exit("no such clip id: %s" % ", ".join(sorted(missing)))
    if not plan:
        sys.exit("nothing to do")

    for clip, start, end, dst in plan:
        print("%-20s %s -> %s  %5.1fs  %s"
              % (clip["id"], hhmmss(start), hhmmss(end), end - start,
                 clip.get("title", "")))
    if args.list:
        return

    for clip, start, end, dst in plan:
        if os.path.exists(dst) and not args.force:
            print("skip (exists) %s" % dst)
            continue
        print("cutting %s ..." % os.path.basename(dst), flush=True)
        cut(src, dst, start, end - start, render, args.copy, overlay)
        got, want = probe(dst), end - start
        if abs(got - want) > 0.5:
            sys.exit("%s: duration %.2fs, expected %.2fs" % (dst, got, want))
        meta = dict(clip, source=src, start=round(start, 3), end=round(end, 3),
                    duration=round(got, 3), stream_copy=bool(args.copy),
                    render=None if args.copy else render)
        json.dump(meta, open(os.path.splitext(dst)[0] + ".json", "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
        print("  %s  %.2fs  %.1f MB" % (dst, got, os.path.getsize(dst) / 1e6))


if __name__ == "__main__":
    main()
