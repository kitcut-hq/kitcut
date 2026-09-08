#!/usr/bin/env python
"""Turn a cut this repo computed into a real DaVinci Resolve timeline.

The edit decisions are made where they are cheap -- silence detection, filler
removal and quoted removals in tighten-cut.py, which prices every threshold
with --list before anything is encoded. This script is the other end: it takes
that keep-list and lays it out in Resolve as a media pool, a timeline cut to
frame, and a subtitle track, so the operator inherits a project they can open,
scrub, adjust and re-render -- not an opaque mp4.

Why bother, when tighten-cut.py can already render the film? Because the two
answer different questions. The ffmpeg render is the deliverable; the Resolve
project is what makes the NEXT change cost minutes instead of a re-run. A
note like "keep the pause before the pricing section" is a drag in Resolve and
a threshold re-sweep here.

STATUS: this is one of two parallel answers to the same question -- see
docs/todo.md #5. The other, on claude/davinci-editor-file-compat, exports
OTIO/EDL/FCPXML and is the better foundation. The measured problem with the
LIVE half below is that external scripting is STUDIO-ONLY: Resolve 21.1's
notes say "Advanced scripting now requires DaVinci Resolve Studio", and on the
free 21.1 scriptapp("Resolve") returns None from both our venv and the bundled
ResolvePython. Do not merge this branch without reading that entry.

It works in two modes and picks one for you:

  LIVE      Resolve is running with external scripting on. The project, the
            media pool, the timeline and the subtitles are built directly, and
            --render queues and waits on a Resolve render.
  HANDOFF   Anything else. The same edit is written as FCPXML next to the
            manifest, which Resolve imports from File > Import > Timeline.
            Nothing is lost but the automation.

Two things here are worth knowing before changing them:

  The keep-list is in SOURCE seconds and Resolve addresses SOURCE frames, and
  its endFrame is INCLUSIVE. _resolve.build_timeline() does that conversion in
  one place; do not re-spell it at a call site, because being one frame long on
  every segment is a drift that only shows up as late audio ten minutes in.

  The subtitle track is grouped by the SAME code that groups the burned-in
  captions (build-captions-ass.group_words, with the same style file), so the
  editable subtitles in Resolve say the same words in the same chunks as the
  picture. Regrouping them independently is how a caption fix gets applied to
  one of the two and not the other.

  --list   what would be built, and where it would land; touches nothing

Invoke as:  python scripts/resolve-edit.py --manifest projects/<id>/tighten.json --list
"""

import sys
import os
import json
import argparse
from importlib import import_module

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import
import _resolve  # noqa: E402
import _project  # noqa: E402

_outline = import_module("transcript-outline")  # words-envelope loader
_ass = import_module("build-captions-ass")  # grouping, so SRT == burned-in

ROOT = _env.ROOT

# Resolve's own render presets are named per install; these are the settings
# that do not depend on one. H.264 in an mp4 at the timeline's own resolution.
DEFAULT_RENDER = {
    "format": "mp4",
    "codec": "H264",
    "VideoQuality": 0,
    "AudioCodec": "aac",
    "AudioBitRate": 192000,
    "ExportVideo": True,
    "ExportAudio": True,
}


def hhmmss(t):
    t = max(0.0, float(t))
    return "%d:%02d:%02d" % (int(t) // 3600, int(t) % 3600 // 60, int(t) % 60)


def srt_time(t):
    ms = int(round(max(0.0, t) * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return "%02d:%02d:%02d,%03d" % (h, m, s, ms)


def srt_from_words(words_doc, style_path, out_path):
    """Write an .srt whose lines are the caption groups, not one line per word.

    Uses the caption builder's own grouping so the Resolve subtitle track and
    the burned-in captions are the same text in the same chunks. Word times in
    the words envelope are centiseconds (that is what the ASS builder consumes),
    so they are divided here exactly once.
    """
    cfg = json.load(open(_env.resolve(style_path), encoding="utf-8"))
    F = cfg["font"]
    m = _ass.Metrics(
        _env.resolve(F["file"]),
        F.get("size"),
        F.get("spacing", 0),
        F.get("fudge", 1.0),
        F.get("cap_height_px"),
    )
    groups = _ass.group_words(_ass.sanitize(words_doc, cfg), cfg, m)
    lines = []
    for i, g in enumerate(groups, 1):
        lines += [
            "%d" % i,
            "%s --> %s" % (srt_time(g[0]["s"] / 100.0), srt_time(g[-1]["e"] / 100.0)),
            " ".join(w["text"] for w in g),
            "",
        ]
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return len(groups)


def load_cuts(manifest_path, manifest):
    """The keep-list tighten-cut.py --plan writes beside the manifest."""
    p = os.path.splitext(manifest_path)[0] + ".cuts.json"
    if not os.path.exists(p):
        sys.exit("no keep-list at %s -- run tighten-cut.py --plan first" % os.path.relpath(p, ROOT))
    doc = json.load(open(p, encoding="utf-8"))
    if not doc.get("keeps"):
        sys.exit("%s has no keeps" % os.path.relpath(p, ROOT))
    return doc, p


def main():
    ap = argparse.ArgumentParser(
        description="Build the computed cut as a DaVinci Resolve timeline."
    )
    ap.add_argument(
        "--manifest",
        required=True,
        help="the tighten/screencast manifest; its .cuts.json is the cut",
    )
    ap.add_argument(
        "--list", action="store_true", help="print what would be built and touch nothing"
    )
    ap.add_argument(
        "--fcpxml",
        action="store_true",
        help="write the handoff file even when Resolve is reachable",
    )
    ap.add_argument("--render", action="store_true", help="also queue and wait on a Resolve render")
    ap.add_argument(
        "--subtitles",
        default=None,
        help="words.json for the subtitle track (default: the "
        "manifest's, remapped through the cut)",
    )
    ap.add_argument("--no-subtitles", action="store_true")
    _env.add_workspace_arg(ap)
    a = ap.parse_args()
    _env.set_workspace(a.workspace)

    mpath = _env.resolve(a.manifest, _env.workspace())
    m = json.load(open(mpath, encoding="utf-8"))
    mid = m.get("id") or os.path.splitext(os.path.basename(mpath))[0]
    R = dict(m.get("resolve") or {})
    src = _env.resolve(m["src"], _env.workspace())
    if not os.path.exists(src):
        sys.exit("source not found: %s" % m["src"])

    cuts, cuts_path = load_cuts(mpath, m)
    fps = float(cuts.get("fps") or m.get("fps") or 25)
    keeps = [(float(x), float(y)) for x, y in cuts["keeps"]]
    runtime = sum(b - a_ for a_, b in keeps)

    proj_name = R.get("project") or mid
    tl_name = R.get("timeline") or ("%s cut" % mid)
    media_dir = R.get("media_dir")
    width = int(R.get("width") or 1280)
    height = int(R.get("height") or 720)

    print("%s | %d segments | %s runtime @ %g fps" % (mid, len(keeps), hhmmss(runtime), fps))
    print("  source   %s" % _project.norm(src))
    print("  cuts     %s" % _project.norm(cuts_path))
    print("  project  %s / timeline %s" % (proj_name, tl_name))
    if media_dir:
        print("  media    %s" % media_dir)

    # Subtitles: the words remapped through the cut, which tighten-cut writes
    # next to its render. Falling back to the uncut transcript would put every
    # caption late by the removed time, so it is refused rather than guessed.
    srt_path = None
    if not a.no_subtitles:
        wp = a.subtitles
        if not wp:
            outdir = m.get("outdir") or os.path.join(os.path.dirname(mpath), "outputs")
            od = _env.resolve(outdir, _env.workspace())
            # tighten-cut.py names it after its render, not after the manifest
            for cand in ("%s-tight.words.json" % mid, "%s.words.json" % mid):
                if os.path.exists(os.path.join(od, cand)):
                    wp = os.path.join(od, cand)
                    break
        if wp and os.path.exists(_env.resolve(wp, _env.workspace())):
            srt_path = os.path.join(os.path.dirname(mpath), "%s.srt" % mid)
            print("  subs     %s" % _project.norm(srt_path))
        else:
            print(
                "  subs     none (no cut-remapped words.json yet; render "
                "tighten-cut.py first, or pass --subtitles)"
            )

    xml_path = os.path.join(os.path.dirname(mpath), "%s.fcpxml" % mid)
    resolve_app = _resolve.connect()
    mode = "LIVE" if resolve_app else "HANDOFF"
    print(
        "  mode     %s%s" % (mode, "" if resolve_app else "  (%s)" % _resolve.why_not_connected())
    )

    if a.list:
        print("\n--list: nothing built.")
        return 0

    if srt_path:
        wdoc = _outline.load_words(_env.resolve(wp, _env.workspace()))
        style = _env.resolve(
            m.get("caption_style")
            or (m.get("captions") or {}).get("style")
            or "config/presets/instafill.json"
        )
        n = srt_from_words(wdoc, style, srt_path)
        print("  wrote %s (%d subtitle lines)" % (_project.norm(srt_path), n))

    # The handoff file is written whenever Resolve is unreachable, and on
    # request otherwise -- it costs nothing and it is the artefact that
    # survives this machine.
    if a.fcpxml or not resolve_app:
        _resolve.fcpxml(
            xml_path,
            tl_name,
            [{"path": src, "duration": cuts["film"][1]}],
            [
                {"src": 0, "start": x, "end": y, "name": "%s %d" % (mid, i + 1)}
                for i, (x, y) in enumerate(keeps)
            ],
            fps,
            width,
            height,
        )
        print("  wrote %s" % _project.norm(xml_path))
        if not resolve_app:
            print(
                "\nHANDOFF: open Resolve and use File > Import > Timeline on "
                "that file.\n%s" % _resolve.why_not_connected()
            )
            if srt_path:
                print("Then File > Import > Subtitle on %s" % _project.norm(srt_path))
            return 0

    project = _resolve.open_project(resolve_app, proj_name, create=True, media_dir=media_dir)
    if project is None:
        sys.exit("could not open or create the Resolve project %r" % proj_name)
    project.SetSettings(
        {
            "timelineFrameRate": str(fps),
            "timelineResolutionWidth": str(width),
            "timelineResolutionHeight": str(height),
        }
    )
    items = _resolve.import_media(project, [src])
    item = items.get(os.path.abspath(src))
    if item is None:
        sys.exit("Resolve would not import %s" % src)

    tl = _resolve.build_timeline(
        project, tl_name, [{"item": item, "start": x, "end": y} for x, y in keeps], fps
    )
    if tl is None:
        sys.exit("Resolve would not build the timeline")
    got = (tl.GetEndFrame() - tl.GetStartFrame() + 1) / fps
    print(
        "  timeline %s: %d clips, %s"
        % (tl.GetName(), len(tl.GetItemListInTrack("video", 1) or []), hhmmss(got))
    )
    if abs(got - runtime) > 2.0:
        print("  !! timeline is %s but the keep-list predicted %s" % (hhmmss(got), hhmmss(runtime)))
    if srt_path:
        print(
            "  subtitles imported: %s"
            % (
                "yes"
                if _resolve.import_subtitles(tl, srt_path)
                else "NO -- import by hand (File > Import > Subtitle)"
            )
        )
    resolve_app.GetProjectManager().SaveProject()

    if a.render:
        rcfg = dict(DEFAULT_RENDER, **(R.get("render") or {}))
        outdir = _env.resolve(
            m.get("outdir") or os.path.join(os.path.dirname(mpath), "outputs"), _env.workspace()
        )
        os.makedirs(outdir, exist_ok=True)
        name = rcfg.pop("name", "%s-resolve" % mid)
        preset = rcfg.pop("preset", None)
        print("  rendering -> %s/%s.mp4 ..." % (_project.norm(outdir), name))
        st = _resolve.render(
            project,
            outdir,
            name,
            preset=preset,
            settings=rcfg,
            on_progress=lambda s: print("    %s%%" % s.get("CompletionPercentage", "?")),
        )
        out = os.path.join(outdir, name + ".mp4")
        print("  render %s" % st.get("JobStatus", "?"))
        if st.get("JobStatus") == "Complete" and os.path.exists(out):
            _project.record(
                mid,
                "resolve-render",
                out=out,
                script="scripts/resolve-edit.py",
                argv=sys.argv[1:],
                kind="film",
                manifest=_project.norm(mpath),
                burned=["cut per %s" % _project.norm(cuts_path)],
                note="rendered by DaVinci Resolve from timeline %r" % tl_name,
            )
    print("\nOpen Resolve: project %r, timeline %r." % (proj_name, tl_name))
    return 0


if __name__ == "__main__":
    sys.exit(main())
