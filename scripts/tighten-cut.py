#!/usr/bin/env python
"""Tighten one already-composited recording: shorten its pauses, drop its stumbles.

The material this is built for is the screencast that came out of the recorder
in one piece -- screen, webcam bubble and narration already burned together, no
second tape to sync. screencast-cut.py cannot help there: it lays a film out in
camera time against a separate screen recording. This one has a single clock.

What it does is subtractive and nothing else. It never re-frames, never
composites, never speeds anything up. It removes three kinds of time:

  pauses    a silence longer than `min_silence` is SHORTENED to `keep_pause`,
            not deleted. A demo with every breath removed sounds like a
            ransom note; a demo where no pause outlives half a second reads as
            edited. One knob, and `--list` prices it.
  fillers   an "um" that sits against a pause is swallowed by that pause.
            Fillers in the middle of a phrase are left alone on purpose --
            cutting one leaves an audible seam and buys 0.3s.
  removals  a span you name by quoting what is said in it. This is the one
            that takes out "let me pause the video while this runs", which no
            detector can find because it is perfectly fluent speech.

Joins are crossfaded by `join_fade` ms of audio (12 by default). A hard splice
between two room-tone samples clicks, and a click is the one artefact that
makes an edit audible to somebody who was not looking for it.

The word transcript is remapped through the keep-list and written next to the
render as <out>.words.json, in the envelope transcribe-words.py produces. That
is what lets run-captions.py caption the tightened film without paying for a
second transcription -- and the remap is exact, because a cut only deletes.

  --list   print the plan, the pause sweep and the runtime; encode nothing
  --plan   also write the keep-list beside the manifest
  (none)   render

Invoke as:  python scripts/tighten-cut.py --manifest projects/<id>/tighten.json --list
"""
import sys, os, json, argparse, subprocess, shutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import
import _encode  # noqa: E402 -- the one place encoder keys are chosen
from importlib import import_module  # noqa: E402

_outline = import_module("transcript-outline")  # hyphen: not importable by name
_namelabel = import_module("name-label")
_imgoverlay = import_module("image-overlay")
import _progress  # noqa: E402
import _project  # noqa: E402

ROOT = _env.ROOT

# No "encoder": _encode picks one this machine can actually run, and a manifest
# that names one overrides it. "speed" is family-neutral.
DEFAULT_RENDER = {"speed": 5, "cq": 20, "maxrate": "12M", "bufsize": "24M",
                  "audio_bitrate": "192k"}
DEFAULT_CUT = {"min_silence": 1.0, "keep_pause": 0.45, "silence_db": -34,
               "min_drop": 0.30, "join_fade_ms": 12}
DEFAULT_FILLERS = {"enabled": True, "words": ["um", "uh", "erm", "uhm", "mm",
                                              "hmm", "ah", "eh"],
                   "pad": 0.06, "max_dur": 1.0, "reach": 0.45}
DEFAULT_AUDIO = {"loudnorm": "I=-16:TP=-1.5:LRA=11"}


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kw)


def hhmmss(t):
    return "%d:%05.2f" % (int(t) // 60, t % 60)


def rel(p):
    return _env.resolve(p)


def probe(path, entries, stream=None):
    cmd = ["ffprobe", "-v", "error", "-show_entries", entries,
           "-of", "default=noprint_wrappers=1:nokey=1"]
    if stream:
        cmd += ["-select_streams", stream]
    return run(cmd + [path]).stdout.split()


def probe_duration(path):
    return float(probe(path, "format=duration")[0])


def probe_fps(path):
    """The rate to render at.

    A screen recorder writes variable frame rate: this file claims 60 and
    averages 30.02. Rendering at the claimed rate doubles every frame; the
    average is what the material actually has, so that is what gets rounded to
    a sane constant rate. Every segment is resampled to it before the concat,
    because concat needs one timebase and VFR joins drift.
    """
    avg = probe(path, "stream=avg_frame_rate", "v:0")[0]
    num, den = (avg.split("/") + ["1"])[:2]
    v = float(num) / float(den or 1)
    for cand in (24.0, 25.0, 30.0, 50.0, 60.0):
        if abs(v - cand) < 0.75:
            return cand
    return round(v, 3)


def detect_spans(cmd, start_key, dur_key):
    """Parse a detector filter's start/duration metadata into [(a, b), ...]."""
    p = subprocess.run(cmd, capture_output=True, text=True)
    spans, cur = [], None
    for line in (p.stderr or "").splitlines():
        if start_key in line:
            try:
                cur = float(line.split(start_key)[1].split()[0])
            except (IndexError, ValueError):
                cur = None
        elif dur_key in line and cur is not None:
            try:
                spans.append((cur, cur + float(line.split(dur_key)[1].split()[0])))
            except (IndexError, ValueError):
                pass
            cur = None
    return spans


def silent_spans(src, db, min_dur):
    return detect_spans(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", src, "-vn",
         "-af", "silencedetect=noise=%ddB:d=%.3f" % (db, min_dur),
         "-f", "null", "-"],
        "silence_start:", "silence_duration:")


def merge(spans, gap=0.0):
    out = []
    for a, b in sorted(spans):
        if out and a - out[-1][1] <= gap:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def intersect(spans, a, b):
    out = []
    for x, y in spans:
        lo, hi = max(x, a), min(y, b)
        if hi - lo > 1e-6:
            out.append((lo, hi))
    return out


def subtract(a, b, holes):
    """[a, b] minus every hole, as a list of surviving spans."""
    out, cur = [], a
    for x, y in merge(holes):
        if y <= cur or x >= b:
            continue
        x, y = max(x, cur), min(y, b)
        if x > cur + 1e-6:
            out.append((cur, x))
        cur = max(cur, y)
    if b > cur + 1e-6:
        out.append((cur, b))
    return out


def quantise(t, fps):
    return round(t * fps) / float(fps)


def resolve_bound(m, words, key, default):
    """A film boundary given as a phrase, a number, or left to the source.

    Quoting what is said survives a re-record; a timecode does not.
    """
    film = m.get("film") or {}
    spec = film.get(key)
    if spec is None:
        return default
    if isinstance(spec, (int, float)):
        return float(spec)
    hit = _outline.find(words, spec)
    if hit is None:
        sys.exit("film.%s phrase not found in transcript: %r" % (key, spec))
    if key == "start_text":
        return max(0.0, hit[0] - float(film.get("start_pad", 0.0)))
    return hit[1] + float(film.get("end_pad", 0.0))


def resolve_removals(specs, words, a, b):
    """The spans named in `remove`, resolved from what is said inside them.

    Each is {"from_text", "to_text"} -- the first word to go and the last word
    to go -- plus a `why` that ends up in project.json, because six months from
    now the interesting question about a cut is never where it was.
    """
    out = []
    for i, spec in enumerate(specs or []):
        if "from" in spec and "to" in spec:
            x, y = float(spec["from"]), float(spec["to"])
        else:
            for key in ("from_text", "to_text"):
                if not spec.get(key):
                    sys.exit("remove[%d] needs %s (or numeric from/to)" % (i, key))
            hit_a = _outline.find(words, spec["from_text"], nth=int(spec.get("nth", 0)))
            if hit_a is None:
                sys.exit("remove[%d].from_text not in transcript: %r"
                         % (i, spec["from_text"]))
            hit_b = _outline.find(words, spec["to_text"], nth=int(spec.get("nth_to", 0)))
            if hit_b is None:
                sys.exit("remove[%d].to_text not in transcript: %r"
                         % (i, spec["to_text"]))
            x, y = hit_a[0], hit_b[1]
        # Take the breath on either side with it -- leaving the pause that
        # framed a removed sentence is what makes a removal audible.
        x -= float(spec.get("pad_in", 0.25))
        y += float(spec.get("pad_out", 0.25))
        if y <= x:
            sys.exit("remove[%d] resolves to an empty or backwards span" % i)
        if y < a or x > b:
            sys.exit("remove[%d] resolves to %s..%s, outside the film"
                     % (i, hhmmss(x), hhmmss(y)))
        out.append((max(x, a), min(y, b), spec.get("why", "")))
    return out


def filler_hits(words, cfg, a, b):
    """Single filler words, with their own spans."""
    vocab = {w.casefold().strip(".,!?") for w in cfg.get("words") or []}
    pad, maxd = float(cfg.get("pad", 0.06)), float(cfg.get("max_dur", 1.0))
    out = []
    for w in words:
        t = w["text"].casefold().strip(" .,!?-—")
        if t not in vocab:
            continue
        if w["start"] < a or w["end"] > b or w["end"] - w["start"] > maxd:
            continue
        out.append((w["start"] - pad, w["end"] + pad))
    return merge(out)


def plan_cuts(m, cut, words, film_a, film_b, src, verbose=True):
    """Decide what to drop, in source time. Returns (keeps, drops, why).

    A pause is shortened, not deleted. `keep_pause` is what survives of it,
    split evenly across the join, so the cut lands in the middle of the silence
    where nobody can hear it rather than against a word.
    """
    min_sil = float(cut["min_silence"])
    keep = float(cut["keep_pause"])
    min_drop = float(cut.get("min_drop", 0.30))
    sil = intersect(silent_spans(src, int(cut["silence_db"]), min_sil),
                    film_a, film_b)
    if verbose:
        tot = sum(b - a for a, b in sil)
        print("  %d silences >= %.2fs at %ddB inside the film (%.1fs of %.1fs)"
              % (len(sil), min_sil, cut["silence_db"], tot, film_b - film_a))

    drops = []
    for a, b in sil:
        x, y = a + keep / 2.0, b - keep / 2.0
        if y - x >= min_drop:
            drops.append((x, y))
    pause_drop = sum(y - x for x, y in merge(drops))

    fcfg = dict(DEFAULT_FILLERS, **(m.get("fillers") or {}))
    fillers = []
    if fcfg.get("enabled", True) and words:
        reach = float(fcfg.get("reach", 0.45))
        for x, y in filler_hits(words, fcfg, film_a, film_b):
            # Only a filler that leans on a pause goes. One in the middle of a
            # phrase costs a seam and buys a third of a second.
            near = any(min(y, d1) - max(x, d0) > -reach for d0, d1 in drops)
            if near:
                fillers.append((x, y))
    drops = merge(drops + fillers, gap=0.0)
    filler_drop = sum(y - x for x, y in drops) - pause_drop

    removals = resolve_removals(m.get("remove"), words, film_a, film_b)
    drops = merge(drops + [(x, y) for x, y, _ in removals])
    if verbose:
        print("  pauses %.1fs | fillers %.1fs (%d) | named removals %.1fs (%d)"
              % (pause_drop, filler_drop, len(fillers),
                 sum(y - x for x, y, _ in removals), len(removals)))
        for x, y, why in removals:
            print("      remove %s -> %s  (%.1fs)  %s"
                  % (hhmmss(x), hhmmss(y), y - x, why))
    return drops, removals


def keeps_from(drops, film_a, film_b, fps):
    keeps = []
    for a, b in subtract(film_a, film_b, drops):
        a, b = quantise(a, fps), quantise(b, fps)
        if b - a >= 1.5 / fps:          # a one-frame keep is a flash, not a shot
            keeps.append((a, b))
    return keeps


def remap_words(words, keeps):
    """Word times moved onto the film's clock.

    Exact, because a cut only deletes: a word that survives is the same word,
    displaced by however much was removed before it. A word straddling a join
    is clamped into the surviving part rather than dropped -- silencedetect
    puts the join in room tone, so this is a hundredth of a second, but a
    caption that inherits a start beyond its end breaks the ASS builder.
    """
    out, base = [], []
    t = 0.0
    for a, b in keeps:
        base.append((a, b, t))
        t += b - a
    for w in words:
        for a, b, off in base:
            if w["end"] <= a or w["start"] >= b:
                continue
            s = max(w["start"], a) - a + off
            e = min(w["end"], b) - a + off
            if e - s < 0.01:
                continue
            out.append({"text": w["text"], "start": round(s, 3),
                        "end": round(e, 3)})
            break
    return out


def build_graph(keeps, fps, audio_cfg, fade_ms, label_fc="", label_out=None):
    """One filtergraph: trim every kept span out of the one source and concat.

    trim/atrim, never select/aselect: on this ffmpeg build aselect passes every
    audio frame, so a select-based cut yields a file as long as the source with
    the picture racing ahead of the sound. The segments are sequential in the
    source's timeline, which is what keeps this cheap -- a later trim discards
    frames while an earlier one is still playing, so nothing queues up behind
    the concat.
    """
    fade = max(0.0, fade_ms / 1000.0)
    ch = []
    for i, (a, b) in enumerate(keeps):
        d = b - a
        ch.append("[0:v]trim=start=%.4f:end=%.4f,setpts=PTS-STARTPTS,"
                  "fps=%s,format=yuv420p,setsar=1[v%d]" % (a, b, fps, i))
        af = ["atrim=start=%.4f:end=%.4f" % (a, b), "asetpts=PTS-STARTPTS"]
        # Ramp each seam. Room tone spliced to room tone at a different phase
        # clicks, and a click is what makes an edit audible.
        f = min(fade, d / 4.0)
        if f > 0.001:
            af.append("afade=t=in:st=0:d=%.4f" % f)
            af.append("afade=t=out:st=%.4f:d=%.4f" % (d - f, f))
        ch.append("[0:a]%s[a%d]" % (",".join(af), i))
    # Labels and cards go on AFTER the concat, so their times are film time --
    # what the viewer sees on the scrubber -- not source time, which the cut has
    # already stopped being a straight line through.
    vcat = "vcat" if label_fc else "vout"
    pairs = "".join("[v%d][a%d]" % (i, i) for i in range(len(keeps)))
    if len(keeps) == 1:
        ch.append("[v0]null[%s]" % vcat)
        ch.append("[a0]anull[araw]")
    else:
        ch.append("%sconcat=n=%d:v=1:a=1[%s][araw]" % (pairs, len(keeps), vcat))
    if label_fc:
        ch.append(label_fc)
        ch.append("[%s]null[vout]" % label_out)

    af = []
    if audio_cfg.get("highpass"):
        af.append("highpass=f=%d" % int(audio_cfg["highpass"]))
    if audio_cfg.get("denoise"):
        af.append("afftdn=nr=%d" % int(audio_cfg["denoise"]))
    if audio_cfg.get("loudnorm"):
        af.append("loudnorm=%s" % audio_cfg["loudnorm"])
    af.append("aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo")
    ch.append("[araw]%s[aout]" % ",".join(af))
    return ";".join(ch)


def _peak_db(path):
    p = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path,
                        "-vn", "-af", "volumedetect", "-f", "null", "-"],
                       capture_output=True, text=True)
    for line in (p.stderr or "").splitlines():
        if "max_volume:" in line:
            try:
                return float(line.split("max_volume:")[1].split()[0])
            except (IndexError, ValueError):
                return None
    return None


def sweep(m, cut, words, film_a, film_b, src):
    """Price the pause setting without encoding anything.

    Picking keep_pause by eye is how 22 seconds of dead air survive a cut. The
    table below is the whole reason this mode exists.
    """
    print("\n  pause sweep (min_silence x keep_pause -> runtime)")
    print("    %-8s %-8s %8s %8s %7s" % ("min_sil", "keep", "cuts", "removed", "runtime"))
    full = film_b - film_a
    for min_sil in (0.6, 0.8, 1.0, 1.5):
        for keep in (0.30, 0.45, 0.60):
            c = dict(cut, min_silence=min_sil, keep_pause=keep)
            drops, _ = plan_cuts(m, c, words, film_a, film_b, src, verbose=False)
            gone = sum(y - x for x, y in drops)
            print("    %-8.2f %-8.2f %8d %7.1fs %7s"
                  % (min_sil, keep, len(drops), gone, hhmmss(full - gone)))


def main():
    ap = argparse.ArgumentParser(
        description="Shorten the pauses and drop the stumbles in one recording.")
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--list", action="store_true",
                    help="print the plan and the pause sweep; encode nothing")
    ap.add_argument("--plan", action="store_true",
                    help="also write <manifest>.cuts.json, a keep-list")
    ap.add_argument("--out", help="output path (default outdir/<id>-tight.mp4)")
    ap.add_argument("--force", action="store_true", help="overwrite the output")
    args = ap.parse_args()

    mpath = rel(args.manifest)
    m = json.load(open(mpath, encoding="utf-8"))
    mid = m.get("id") or os.path.splitext(os.path.basename(mpath))[0]
    src = rel(m["src"])
    if not os.path.exists(src):
        sys.exit("source not found: %s" % m["src"])
    cut = dict(DEFAULT_CUT, **(m.get("cut") or {}))
    audio_cfg = dict(DEFAULT_AUDIO, **(m.get("audio") or {}))
    render = _encode.resolve(dict(DEFAULT_RENDER, **(m.get("render") or {})))

    name_specs = m.get("name_labels") or []
    for spec in name_specs:
        if "name" not in spec or "at" not in spec:
            sys.exit("every name_labels entry needs at least name and at")
    img_specs = m.get("image_overlays") or []
    img_preset = m.get("overlay_preset", _imgoverlay.DEFAULT_PRESET)
    for spec in img_specs:
        if "at" not in spec:
            sys.exit("every image_overlays entry needs at least at")
        given = [k for k in _imgoverlay.SOURCES if spec.get(k)]
        if len(given) != 1:
            sys.exit("every image_overlays entry needs exactly one of %s -- got %s"
                     % ("/".join(_imgoverlay.SOURCES), ", ".join(given) or "none"))

    words = _outline.load_words(rel(m["words"])) if m.get("words") else []
    # Corrections run BEFORE anything reads the transcript, so `remove` and
    # `film.start_text` quote the corrected wording -- one spelling of every
    # phrase in the manifest, not two.
    if words and m.get("corrections"):
        words = _outline.apply_corrections(words, m["corrections"],
                                           verbose=args.list)
    dur = probe_duration(src)
    fps = float(m.get("fps") or probe_fps(src))
    film_a = resolve_bound(m, words, "start_text", 0.0)
    film_b = resolve_bound(m, words, "end_text", dur)
    if film_b <= film_a:
        sys.exit("film.end is not after film.start")
    film_a, film_b = quantise(max(0.0, film_a), fps), quantise(min(dur, film_b), fps)

    print("%s | %s source at %gfps | film %s -> %s"
          % (mid, hhmmss(dur), fps, hhmmss(film_a), hhmmss(film_b)))
    drops, removals = plan_cuts(m, cut, words, film_a, film_b, src)
    keeps = keeps_from(drops, film_a, film_b, fps)
    runtime = sum(b - a for a, b in keeps)
    print("  %d segments, %s of %s kept (%.0f%% removed)"
          % (len(keeps), hhmmss(runtime), hhmmss(film_b - film_a),
             100.0 * (1 - runtime / (film_b - film_a))))
    # A cut is a jump for whatever is moving in the frame -- on a screencast
    # that is the webcam bubble. Segments are how often that happens, and the
    # shortest one is the flash you cannot un-see. Worth printing before an
    # encode, because neither is visible in the runtime.
    if keeps:
        lens = sorted(b - a for a, b in keeps)
        print("  segment length: shortest %.2fs | median %.2fs | longest %.2fs "
              "(a cut every %.1fs on average)"
              % (lens[0], lens[len(lens) // 2], lens[-1],
                 runtime / max(1, len(keeps) - 1)))

    # A label past the end of the cut film is not an error ffmpeg reports:
    # `enable` simply never turns true and the card silently never appears. The
    # runtime is only known here, after the cut, so this is where it is caught.
    for spec in name_specs:
        if float(spec["at"]) >= runtime:
            sys.exit("name label %r starts at %.1fs but the film runs %.1fs"
                     % (spec["name"], float(spec["at"]), runtime))
    img_preset_doc = json.load(open(
        _imgoverlay._overlay.repo_path(img_preset), encoding="utf-8")) \
        if img_specs else {}
    for i, spec in enumerate(img_specs):
        # A negative `at` means "this many seconds before the end", which only
        # becomes a number once the cut is planned. An end card is written that
        # way on purpose -- re-cutting the film moves it automatically.
        at, _dur = _imgoverlay.resolve_window(spec, img_preset_doc, runtime)
        if at >= runtime:
            sys.exit("image overlay %d starts at %.1fs but the film runs %.1fs"
                     % (i, at, runtime))
    if args.list and (name_specs or img_specs):
        print("\n  graphics (film time):")
        for spec in name_specs:
            print("  %8.2f %8.2f   %s -- %s"
                  % (float(spec["at"]),
                     float(spec["at"]) + float(spec.get("dur", 5.5)),
                     spec["name"], spec.get("title", "")))
        for spec in img_specs:
            at, d = _imgoverlay.resolve_window(spec, img_preset_doc, runtime)
            print("  %8.2f %8.2f   %s"
                  % (at, at + d,
                     _imgoverlay.describe(spec, img_preset_doc, runtime)))

    if args.plan or args.list:
        cuts_path = os.path.splitext(mpath)[0] + ".cuts.json"
        doc = {"id": mid, "fps": fps, "film": [film_a, film_b],
               "runtime": round(runtime, 3),
               "keeps": [[round(a, 4), round(b, 4)] for a, b in keeps],
               "removals": [{"from": round(x, 3), "to": round(y, 3), "why": w}
                            for x, y, w in removals]}
        if args.plan:
            json.dump(doc, open(cuts_path, "w", encoding="utf-8"), indent=1)
            print("  wrote %s" % os.path.relpath(cuts_path, ROOT))
    if args.list:
        sweep(m, cut, words, film_a, film_b, src)
        return

    outdir = rel(m.get("outdir") or os.path.join(os.path.dirname(mpath), "outputs"))
    os.makedirs(outdir, exist_ok=True)
    dst = rel(args.out) if args.out else os.path.join(outdir, "%s-tight.mp4" % mid)
    if os.path.exists(dst) and not args.force:
        sys.exit("%s exists; pass --force to overwrite"
                 % os.path.relpath(dst, ROOT))

    vw, vh = (int(x) for x in probe(src, "stream=width,height", "v:0")[:2])
    tmpdir = rel(m.get("tmpdir") or os.path.join(os.path.dirname(mpath), "temp"))
    inputs, nxt = ["-i", src], 1
    label_fc, label_out = "", None
    if name_specs:
        pngs, label_fc, label_out = _namelabel.prepare(
            m.get("label_preset", _namelabel.DEFAULT_PRESET), name_specs,
            vw, vh, tmpdir, tag=mid, base="vcat", first_input=nxt)
        for png in pngs:
            inputs += ["-loop", "1", "-framerate", str(fps), "-i", png]
            nxt += 1
    # Image overlays come after the labels on both counts -- later input
    # indices, and later in the chain -- so an end card sits on top of a lower
    # third rather than under it.
    if img_specs:
        pngs, img_fc, img_out = _imgoverlay.prepare(
            img_preset, img_specs, vw, vh, tmpdir, tag=mid,
            base=(label_out or "vcat"), first_input=nxt, runtime=runtime)
        for png in pngs:
            inputs += ["-loop", "1", "-framerate", str(fps), "-i", png]
            nxt += 1
        label_fc = ";".join(x for x in (label_fc, img_fc) if x)
        label_out = img_out

    graph = build_graph(keeps, fps, audio_cfg, float(cut.get("join_fade_ms", 12)),
                        label_fc, label_out)
    tmp = dst + ".part.mp4"
    prog = _progress.begin(mid, runtime, os.path.relpath(dst, ROOT))
    cmd = (["ffmpeg", "-hide_banner", "-nostats", "-loglevel", "warning",
            "-progress", prog]
           + inputs
           + ["-filter_complex", graph, "-map", "[vout]", "-map", "[aout]",
              "-r", str(fps)]
           + _encode.video_args(render) + _encode.audio_args(render)
           + ["-movflags", "+faststart", "-y", tmp])
    print("\n  rendering %s ..." % os.path.relpath(dst, ROOT))
    try:
        p = subprocess.run(cmd, capture_output=True, text=True)
    finally:
        _progress.end(mid)
    if p.returncode != 0:
        sys.stderr.write((p.stderr or "")[-4000:])
        sys.exit("ffmpeg failed")

    got = probe_duration(tmp)
    if abs(got - runtime) > max(2.0 / fps, 0.5):
        sys.stderr.write("output is %.2fs, the keep-list predicted %.2fs\n"
                         % (got, runtime))
        sys.exit("duration assertion failed; %s left in place" % tmp)
    peak = _peak_db(tmp)
    if peak is None or peak < -60:
        sys.exit("rendered audio is silent (peak %s dB); refusing to ship it"
                 % peak)
    shutil.move(tmp, dst)

    wout = os.path.splitext(dst)[0] + ".words.json"
    if words:
        # The FULL envelope transcribe-words.py writes, not just the word list:
        # run-captions.py refuses a transcript with no `duration`, and the
        # refusal ("re-run with --force transcribe") points at the one stage
        # that is not the problem.
        moved = remap_words(words, keeps)
        src_doc = json.load(open(rel(m["words"]), encoding="utf-8"))
        json.dump({"file": os.path.relpath(dst, ROOT), "duration": round(got, 3),
                   "language": src_doc.get("language", "en"),
                   "language_probability":
                       float(src_doc.get("language_probability", 1.0)),
                   "model": "remapped by tighten-cut.py from %s"
                            % src_doc.get("model", "?"),
                   "source_words": _project.norm(rel(m["words"])),
                   "text": " ".join(w["text"] for w in moved), "words": moved},
                  open(wout, "w", encoding="utf-8"), ensure_ascii=False)
    print("  %s  %s  %.1f MB  audio peak %.1f dB"
          % (os.path.relpath(dst, ROOT), hhmmss(got),
             os.path.getsize(dst) / 1e6, peak))
    if words:
        print("  %s  remapped word transcript (feed it to run-captions.py)"
              % os.path.relpath(wout, ROOT))

    _project.record(
        _project.project_id(m, args.manifest), "render",
        out=dst, script=__file__, argv=sys.argv[1:], kind="tighten",
        manifest=args.manifest,
        sidecars={"words": wout if words else None},
        burned=(["pause cut: silences over %.2fs shortened to %.2fs "
                 "(%d segments, %.0f%% of the source removed)"
                 % (cut["min_silence"], cut["keep_pause"], len(keeps),
                    100.0 * (1 - runtime / (film_b - film_a)))]
                + ["removed %s -> %s: %s" % (hhmmss(x), hhmmss(y), w or "no reason given")
                   for x, y, w in removals]
                + ["name label '%s' at %ss film time for %ss"
                   % (s.get("name"), s.get("at"), s.get("dur"))
                   for s in name_specs]
                + [_imgoverlay.describe(s, img_preset_doc, runtime)
                   for s in img_specs]))


if __name__ == "__main__":
    main()
