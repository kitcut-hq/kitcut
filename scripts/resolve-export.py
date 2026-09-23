#!/usr/bin/env python
"""Hand a kitcut edit to DaVinci Resolve as an editable timeline.

Resolve's own project files are not ours to write -- a .drp is a ZIP of XML
whose interesting half is a hex blob with no published schema, so the only
things anyone does to one are subtractive (see docs/davinci-resolve.md). The
door that IS open is interchange, and it is open in the free edition: Resolve
imports OTIO, EDL and FCP7 XML, and imports SRT as a subtitle track.

So this converts a cut we already decided into a timeline somebody can open:

  otio    leads. Plain JSON, carries two video tracks, an audio track, per-clip
          media paths and our markers with their notes
  edl     the universal fallback. One video track, no paths (Resolve conforms
          by reel + timecode), and the frame rate travels OUT OF BAND
  fcpxml  FCP7 XML. Carries paths like otio, but every media reference needs a
          duration, so this one cannot be written without probing the sources
  srt     the words, from the same transcript the caption builder reads,
          remapped onto film time. The LOOK does not travel: Resolve has no
          ASS importer and draws its own subtitle

What does not travel at all, and is printed by --list rather than hidden: the
PiP transform, crop windows, the caption card, the redaction blurs, the
loudnorm. Cut decisions travel; pixels do not. Everything this repo burns in is
a render, and a render is what Resolve would import as a flat clip anyway.

The input is a keep-list -- `<manifest>.cuts.json` from tighten-cut.py --plan or
`<id>.cuts.json` from screencast-cut.py -- plus the manifest it came from, for
the media paths, the bookends and the label/overlay windows that become markers.
A keep-list ALONE is not the film: on claude-demo it is 22.5s short, because the
opening bookend lives in the manifest. That gap is a refusal here, not a
surprise in Resolve.

  --list   print the timeline, the markers and what each format drops; write
           nothing. This is also the honesty report -- run it before promising
           somebody an editable file

Invoke as:  python scripts/resolve-export.py --manifest projects/<id>/tighten.json --list
            python scripts/resolve-export.py --manifest projects/<id>/tighten.json --format all
"""

import sys
import os
import json
import argparse
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import
import _project  # noqa: E402

ROOT = _env.ROOT
PRESET = "config/resolve/export.json"

# What each format cannot carry. Printed by --list, because a promise about an
# editable timeline is a promise about these lines.
DROPS = {
    "otio": [
        "the PiP transform, crop windows and every burned graphic (pixels, not decisions)",
        "speed changes survive as a LinearTimeWarp, but whether Resolve honours it is untested",
    ],
    "edl": [
        "media paths -- Resolve conforms by reel name and timecode, and reel names are truncated",
        "the frame rate itself: an EDL does not state it, so the import dialog must be told",
        "the second video track, the audio track and every marker",
    ],
    "fcpxml": [
        "speed changes -- the FCP7 adapter writes no timemap at all (measured)",
        "the PiP transform and every burned graphic",
    ],
    "srt": [
        "the caption look entirely: card, outline, per-word highlight, grouping",
    ],
}


def probe_duration(path):
    """Source length in seconds, or None when it cannot be read.

    None is not a failure here: otio and edl do not need it. Only fcpxml does,
    and it refuses by name rather than writing a file Resolve would reject.
    """
    try:
        out = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=nk=1:nw=1",
                path,
            ],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        return float(out)
    except Exception:
        return None


# ---------------------------------------------------------------- the model
#
# One timeline is tracks of items in FILM time. An item is a clip (a span of a
# source) or a gap. Keeping gaps explicit is what keeps two video tracks in
# step -- an editor reading V2 alone must still see the camera where the film
# shows it.


def new_timeline(name, fps):
    return {
        "name": name,
        "fps": float(fps),
        "tracks": [
            {"name": "V1 picture", "kind": "Video", "items": []},
            {"name": "V2 overlay", "kind": "Video", "items": []},
            {"name": "A1 sound", "kind": "Audio", "items": []},
        ],
        "markers": [],
        "notes": [],
    }


def track(tl, name):
    return next(t for t in tl["tracks"] if t["name"].startswith(name))


def track_end(t):
    return sum(i["dur"] for i in t["items"])


def place(t, at, src, start, dur, name):
    """Put a clip at film time `at`, padding with a gap when the track is short.

    Rounding is done by the caller in frames; a gap under half a frame is
    swallowed rather than written, because a 3ms gap in a timeline is a black
    flash somebody has to hunt for.
    """
    have = track_end(t)
    if at - have > 1e-6:
        t["items"].append({"kind": "gap", "dur": at - have, "name": "gap"})
    t["items"].append({"kind": "clip", "src": src, "start": start, "dur": dur, "name": name})


def quantise(t, fps):
    return round(t * fps) / fps


def read_cuts(path):
    """A keep-list, with its dialect named.

    screencast-cut writes [start, end, layout] in CAMERA time and carries an
    offset to the screen; tighten-cut writes [start, end] in the source's own
    time. Nothing else here needs to know which cutter ran.
    """
    doc = json.load(open(path, encoding="utf-8"))
    keeps = doc.get("keeps") or []
    if not keeps:
        sys.exit(
            "%s carries no keeps -- re-run the cutter with --plan" % os.path.relpath(path, ROOT)
        )
    doc["_dialect"] = "screencast" if len(keeps[0]) > 2 else "tighten"
    return doc


def bookend_span(spec, which):
    """(source, start, dur) for one bookend, or a refusal.

    A bookend bounded by a QUOTE is resolved by screencast-cut against that
    clip's own transcript; doing it again here would mean re-transcribing, so a
    text-bounded bookend is refused by name instead of guessed at.
    """
    src = spec.get("source")
    a, b = spec.get("start"), spec.get("end")
    if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
        sys.exit(
            "bookend %r is bounded by text, not seconds -- resolve it first "
            "(screencast-cut.py --list prints the seconds) or pass --skip-bookends"
            % spec.get("id", which)
        )
    return _env.resolve(src), float(a), float(b) - float(a)


def build(cuts, man, args, preset):
    """Keep-list + manifest -> a timeline in film time."""
    fps = float(cuts.get("fps") or man.get("fps") or 30)
    tl = new_timeline(man.get("id") or cuts.get("id") or "kitcut", fps)
    v1, v2, a1 = track(tl, "V1"), track(tl, "V2"), track(tl, "A1")
    mcolour = preset["markers"]

    if cuts["_dialect"] == "screencast":
        picture, sound = _env.resolve(man["screen"]), _env.resolve(man["camera"])
        camera = sound
        offset = float(cuts.get("offset") or 0.0)
    else:
        picture = sound = camera = _env.resolve(man["src"])
        offset = 0.0

    # 1. the opening bookends, which are clips in their own right and the reason
    #    a keep-list alone under-runs the film
    bk = man.get("bookends") or {}
    opens = [] if args.skip_bookends else list(bk.get("open") or [])
    closes = [] if args.skip_bookends else list(bk.get("close") or [])
    if args.skip_bookends and (bk.get("open") or bk.get("close")):
        tl["notes"].append(
            "%d bookend(s) SKIPPED -- the exported timeline is shorter than the render"
            % (len(bk.get("open") or []) + len(bk.get("close") or []))
        )

    t = 0.0
    for spec in opens:
        src, a, dur = bookend_span(spec, "open")
        dur = quantise(dur, fps)
        place(v1, t, src, a, dur, spec.get("id", "bookend"))
        place(a1, t, src, a, dur, spec.get("id", "bookend"))
        for br in spec.get("broll") or []:
            at = t + float(br.get("at", 0.0))
            bd = quantise(float(br.get("dur", 0.0)), fps)
            place(v2, at, _env.resolve(br["source"]), float(br.get("from", 0.0)), bd, "b-roll")
        tl["markers"].append(
            {
                "at": t,
                "name": "bookend %s" % spec.get("id", ""),
                "note": "shot separately; not part of the keep-list",
                "colour": mcolour["bookend"],
            }
        )
        t += dur

    # 2. the body: one clip per keep. The camera is the sound in both dialects,
    #    so A1 mirrors it and V2 carries the PiP where the layout asked for one.
    body_start = t
    for i, keep in enumerate(cuts["keeps"]):
        a, b = float(keep[0]), float(keep[1])
        layout = keep[2] if len(keep) > 2 else None
        dur = quantise(b - a, fps)
        if layout == "pip":
            place(v1, t, picture, a - offset, dur, "screen-%03d" % i)
            place(v2, t, camera, a, dur, "pip-%03d" % i)
        else:
            # camera full frame (or a single-source cut): the picture IS the sound
            place(v1, t, camera if layout == "full" else picture, a, dur, "cam-%03d" % i)
        place(a1, t, sound, a, dur, "snd-%03d" % i)
        t += dur

    # 3. the closing bookends
    for spec in closes:
        src, a, dur = bookend_span(spec, "close")
        dur = quantise(dur, fps)
        place(v1, t, src, a, dur, spec.get("id", "bookend"))
        place(a1, t, src, a, dur, spec.get("id", "bookend"))
        t += dur

    tl["runtime"] = t
    tl["body_start"] = body_start

    # 4. the decisions we already record become markers. A removal has no
    #    duration in the film -- it is a JOIN -- so its marker lands where the
    #    cut is, carrying the reason the manifest gave for it.
    for r in cuts.get("removals") or []:
        film_t = body_start + source_to_film(float(r["from"]), cuts["keeps"])
        tl["markers"].append(
            {
                "at": film_t,
                "name": "removed %.1fs" % (float(r["to"]) - float(r["from"])),
                "note": r.get("why", ""),
                "colour": mcolour["removal"],
            }
        )
    for lab in man.get("name_labels") or []:
        tl["markers"].append(
            {
                "at": float(lab.get("at", 0.0)),
                "name": "label: %s" % lab.get("name", ""),
                "note": "%s -- %.1fs" % (lab.get("title", ""), float(lab.get("dur", 0))),
                "colour": mcolour["label"],
            }
        )
    for ov in man.get("image_overlays") or []:
        at = float(ov.get("at", 0.0))
        # negative counts back from the end, the same convention image-overlay
        # resolves against the runtime -- so it survives a re-cut
        tl["markers"].append(
            {
                "at": t + at if at < 0 else at,
                "name": "overlay: %s" % (ov.get("card") or ov.get("html") or ov.get("image") or ""),
                "note": "burned graphic; it does not travel, this marker is where it was",
                "colour": mcolour["overlay"],
            }
        )
    tl["markers"].sort(key=lambda m: m["at"])
    return tl


def source_to_film(t, keeps):
    """Where a source instant lands after the cut, in body time.

    Exact, because a cut only deletes: everything kept before it is what
    survives in front of it. An instant inside a dropped span maps to the join
    that swallowed it, which is where its marker belongs.
    """
    out = 0.0
    for keep in keeps:
        a, b = float(keep[0]), float(keep[1])
        if t >= b:
            out += b - a
        elif t >= a:
            return out + (t - a)
        else:
            break
    return out


# ---------------------------------------------------------------- writers


def otio_time(v, fps):
    return {"OTIO_SCHEMA": "RationalTime.1", "rate": fps, "value": round(v * fps)}


def otio_range(start, dur, fps):
    return {
        "OTIO_SCHEMA": "TimeRange.1",
        "duration": otio_time(dur, fps),
        "start_time": otio_time(start, fps),
    }


def write_otio(tl, path, durations):
    """OTIO by hand: it is plain JSON against a published schema, and writing it
    ourselves keeps opentimelineio out of requirements.txt. check-resolve.py is
    what proves the shape, and the library reads these files.
    """
    fps = tl["fps"]
    children = []
    for t in tl["tracks"]:
        items = []
        for it in t["items"]:
            if it["kind"] == "gap":
                items.append(
                    {
                        "OTIO_SCHEMA": "Gap.1",
                        "metadata": {},
                        "name": "gap",
                        "source_range": otio_range(0.0, it["dur"], fps),
                        "effects": [],
                        "markers": [],
                        "enabled": True,
                    }
                )
                continue
            ref = {
                "OTIO_SCHEMA": "ExternalReference.1",
                "metadata": {},
                "name": "",
                "available_range": None,
                "available_image_bounds": None,
                "target_url": url_for(it["src"]),
            }
            d = durations.get(it["src"])
            if d:
                ref["available_range"] = otio_range(0.0, d, fps)
            items.append(
                {
                    "OTIO_SCHEMA": "Clip.2",
                    "metadata": {},
                    "name": it["name"],
                    "source_range": otio_range(it["start"], it["dur"], fps),
                    "effects": [],
                    "markers": [],
                    "enabled": True,
                    "media_references": {"DEFAULT_MEDIA": ref},
                    "active_media_reference_key": "DEFAULT_MEDIA",
                }
            )
        children.append(
            {
                "OTIO_SCHEMA": "Track.1",
                "metadata": {},
                "name": t["name"],
                "source_range": None,
                "effects": [],
                "markers": markers_for(t, tl, fps),
                "enabled": True,
                "kind": t["kind"],
                "children": items,
            }
        )
    doc = {
        "OTIO_SCHEMA": "Timeline.1",
        "metadata": {"kitcut": {"exported_by": "scripts/resolve-export.py"}},
        "name": tl["name"],
        "global_start_time": otio_time(0.0, fps),
        "tracks": {
            "OTIO_SCHEMA": "Stack.1",
            "metadata": {},
            "name": "tracks",
            "source_range": None,
            "effects": [],
            "markers": [],
            "enabled": True,
            "children": children,
        },
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=4, ensure_ascii=False)


def markers_for(t, tl, fps):
    if not t["name"].startswith("V1"):
        return []
    return [
        {
            "OTIO_SCHEMA": "Marker.2",
            "metadata": {},
            "name": m["name"],
            "color": str(m.get("colour", "red")).upper(),
            "marked_range": otio_range(m["at"], 1.0 / fps, fps),
            "comment": m.get("note", ""),
        }
        for m in tl["markers"]
    ]


def url_for(path):
    p = str(path).replace("\\", "/")
    return "file://" + (p if p.startswith("/") else "/" + p)


def smpte(seconds, fps, drop=None):
    """HH:MM:SS:FF at the timeline rate.

    Drop-frame is the classic EDL trap and it is decided by the RATE, not by
    taste: 29.97 and 59.94 count 30 and 60 frames a second while running slower
    than that, so a non-drop timecode drifts ~3.6s an hour against the clock.
    Drop-frame skips the first 2 (or 4) frame numbers of every minute except
    every tenth, and is written with ';'.
    """
    nominal = int(round(fps))
    if drop is None:
        drop = abs(fps - 29.97) < 0.01 or abs(fps - 59.94) < 0.01
    f = int(round(seconds * fps))
    if drop:
        per = 2 if nominal == 30 else 4
        mins = f // (nominal * 60)
        tens = f // (nominal * 600)
        f += per * (mins - tens)
        sep = ";"
    else:
        sep = ":"
    return "%02d:%02d:%02d%s%02d" % (
        f // (nominal * 3600),
        f // (nominal * 60) % 60,
        f // nominal % 60,
        sep,
        f % nominal,
    )


def reel(path):
    """CMX3600 allows 8 characters. Truncating is not a bug we can fix -- it is
    the format -- but it IS why an EDL conforms by timecode and a viewer must be
    told which file each reel was.
    """
    base = os.path.splitext(os.path.basename(path))[0]
    return "".join(c for c in base.upper() if c.isalnum())[:8] or "AX"


def write_edl(tl, path):
    fps = tl["fps"]
    v1 = track(tl, "V1")
    drop = abs(fps - 29.97) < 0.01 or abs(fps - 59.94) < 0.01
    lines = [
        "TITLE: %s" % tl["name"],
        "FCM: %s" % ("DROP FRAME" if drop else "NON-DROP FRAME"),
        "",
    ]
    rec, n = 0.0, 0
    for it in v1["items"]:
        if it["kind"] == "gap":
            rec += it["dur"]
            continue
        n += 1
        lines.append(
            "%03d  %-8s V     C        %s %s %s %s"
            % (
                n,
                reel(it["src"]),
                smpte(it["start"], fps),
                smpte(it["start"] + it["dur"], fps),
                smpte(rec, fps),
                smpte(rec + it["dur"], fps),
            )
        )
        lines.append("* FROM CLIP NAME: %s" % os.path.basename(it["src"]))
        rec += it["dur"]
    for m in tl["markers"]:
        lines.append(
            "* MARKER %s %s %s" % (smpte(m["at"], fps), m["name"], m.get("note", "")[:120])
        )
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def write_fcpxml(tl, path, durations):
    """FCP7 XML (xmeml v5). Every file element needs a duration, which is why
    this format is the one that cannot be written without reading the sources.
    """
    fps = tl["fps"]
    nominal = int(round(fps))
    ntsc = "TRUE" if abs(fps - nominal) > 0.001 else "FALSE"
    missing = sorted(
        {it["src"] for t in tl["tracks"] for it in t["items"] if it["kind"] == "clip"}
        - {k for k, v in durations.items() if v}
    )
    if missing:
        sys.exit(
            "fcpxml needs every source's duration and ffprobe could not read:\n  %s\n"
            "Write otio or edl instead, or make the sources readable."
            % "\n  ".join(os.path.relpath(m, ROOT) for m in missing)
        )

    def rate():
        return "<rate><timebase>%d</timebase><ntsc>%s</ntsc></rate>" % (nominal, ntsc)

    out = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        "<!DOCTYPE xmeml>",
        '<xmeml version="5">',
        "<sequence>",
        "<name>%s</name>" % esc(tl["name"]),
        "<duration>%d</duration>" % round(tl["runtime"] * fps),
        rate(),
        "<media>",
    ]
    seen = {}
    for kind in ("Video", "Audio"):
        out.append("<%s>" % kind.lower())
        for t in [x for x in tl["tracks"] if x["kind"] == kind]:
            out.append("<track>")
            rec = 0.0
            for it in t["items"]:
                if it["kind"] == "gap":
                    rec += it["dur"]
                    continue
                fid = seen.get(it["src"])
                out.append('<clipitem id="%s">' % esc(it["name"] + "-" + str(round(rec * fps))))
                out.append("<name>%s</name>" % esc(os.path.basename(it["src"])))
                out.append("<duration>%d</duration>" % round(durations[it["src"]] * fps))
                out.append(rate())
                out.append("<start>%d</start>" % round(rec * fps))
                out.append("<end>%d</end>" % round((rec + it["dur"]) * fps))
                out.append("<in>%d</in>" % round(it["start"] * fps))
                out.append("<out>%d</out>" % round((it["start"] + it["dur"]) * fps))
                if fid is None:
                    fid = "file-%d" % (len(seen) + 1)
                    seen[it["src"]] = fid
                    out.append('<file id="%s">' % fid)
                    out.append("<name>%s</name>" % esc(os.path.basename(it["src"])))
                    out.append("<pathurl>%s</pathurl>" % esc(url_for(it["src"])))
                    out.append(rate())
                    out.append("<duration>%d</duration>" % round(durations[it["src"]] * fps))
                    out.append("</file>")
                else:
                    out.append('<file id="%s"/>' % fid)
                out.append("</clipitem>")
                rec += it["dur"]
            out.append("</track>")
        out.append("</%s>" % kind.lower())
    out.append("</media>")
    for m in tl["markers"]:
        out.append(
            "<marker><name>%s</name><comment>%s</comment><in>%d</in><out>-1</out></marker>"
            % (
                esc(m["name"]),
                esc(m.get("note", "")),
                round(m["at"] * fps),
            )
        )
    out += ["</sequence>", "</xmeml>"]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")


def esc(s):
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def srt_time(t):
    ms = int(round(t * 1000))
    return "%02d:%02d:%02d,%03d" % (ms // 3600000, ms // 60000 % 60, ms // 1000 % 60, ms % 1000)


def remap_words(words, keeps, offset=0.0):
    """Word times on the film's clock. The same arithmetic tighten-cut uses, and
    exact for the same reason: a cut only deletes.
    """
    out, t = [], offset
    for keep in keeps:
        a, b = float(keep[0]), float(keep[1])
        for w in words:
            if w["end"] <= a or w["start"] >= b:
                continue
            s = max(w["start"], a) - a + t
            e = min(w["end"], b) - a + t
            if e > s:
                out.append({"text": w["text"], "start": s, "end": e})
        t += b - a
    return out


def write_srt(words, path, cfg):
    """One cue per group. The grouping is for reading, not for burning -- see
    the note in config/resolve/export.json.
    """
    cues, cur = [], []
    for w in words:
        if cur:
            gap = w["start"] - cur[-1]["end"]
            wide = len(" ".join(x["text"] for x in cur)) + 1 + len(w["text"]) > cfg["max_chars"]
            long = w["end"] - cur[0]["start"] > cfg["max_dur"]
            if gap > cfg["gap_break"] or wide or long or len(cur) >= cfg["max_words"]:
                cues.append(cur)
                cur = []
        cur.append(w)
    if cur:
        cues.append(cur)
    lines = []
    for i, g in enumerate(cues, 1):
        lines += [
            str(i),
            "%s --> %s" % (srt_time(g[0]["start"]), srt_time(g[-1]["end"])),
            " ".join(x["text"] for x in g),
            "",
        ]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return len(cues)


# ---------------------------------------------------------------- driver


def default_cuts(mpath, mid):
    """Where each cutter puts its keep-list."""
    for c in (
        os.path.splitext(mpath)[0] + ".cuts.json",  # tighten-cut.py
        os.path.join(os.path.dirname(mpath), "%s.cuts.json" % mid),  # screencast-cut.py
    ):
        if os.path.exists(c):
            return c
    return None


def report(tl, formats):
    print()
    print("  %s  %.3fs  %g fps" % (tl["name"], tl["runtime"], tl["fps"]))
    for t in tl["tracks"]:
        clips = [i for i in t["items"] if i["kind"] == "clip"]
        srcs = sorted({os.path.basename(i["src"]) for i in clips})
        print(
            "  %-12s %3d clips  %7.2fs  %s"
            % (t["name"], len(clips), track_end(t), ", ".join(srcs) or "-")
        )
    print("  %d markers" % len(tl["markers"]))
    for m in tl["markers"][:12]:
        print("    %8.2f  %-28s %s" % (m["at"], m["name"], (m.get("note") or "")[:60]))
    if len(tl["markers"]) > 12:
        print("    ... %d more" % (len(tl["markers"]) - 12))
    for n in tl["notes"]:
        print("  ! %s" % n)
    print()
    print("  what each format drops:")
    for f in formats:
        for line in DROPS[f]:
            print("    %-7s %s" % (f, line))


def main():
    ap = argparse.ArgumentParser(description="Export a kitcut edit for DaVinci Resolve")
    ap.add_argument("--manifest", required=True, help="the project manifest the cut was made from")
    ap.add_argument("--cuts", help="keep-list; defaults to the one the cutter wrote beside it")
    ap.add_argument(
        "--format",
        default="otio",
        help="otio | edl | fcpxml | srt | all (default otio; 'all' is the preset's list)",
    )
    ap.add_argument("--outdir", help="where to write (default the manifest's outdir)")
    ap.add_argument("--words", help="word transcript for --format srt (default the manifest's)")
    ap.add_argument(
        "--skip-bookends",
        action="store_true",
        help="export the keep-list alone; the timeline will be SHORTER than the render",
    )
    ap.add_argument("--preset", default=PRESET, help="export defaults (%s)" % PRESET)
    ap.add_argument(
        "--list", action="store_true", help="print the timeline and drops; write nothing"
    )
    args = ap.parse_args()

    preset = json.load(open(_env.resolve(args.preset), encoding="utf-8"))
    mpath = _env.resolve(args.manifest)
    man = json.load(open(mpath, encoding="utf-8"))
    mid = man.get("id") or os.path.basename(os.path.dirname(mpath))

    cpath = _env.resolve(args.cuts) if args.cuts else default_cuts(mpath, mid)
    if not cpath or not os.path.exists(cpath):
        sys.exit(
            "no keep-list beside %s -- make one first:\n"
            "  python scripts/tighten-cut.py --manifest %s --plan\n"
            "  (or screencast-cut.py --manifest %s --plan)"
            % (os.path.relpath(mpath, ROOT), args.manifest, args.manifest)
        )
    cuts = read_cuts(cpath)

    formats = (
        preset["formats"] if args.format == "all" else [f.strip() for f in args.format.split(",")]
    )
    for f in formats:
        if f not in DROPS:
            sys.exit("unknown format %r -- one of %s" % (f, ", ".join(sorted(DROPS))))

    tl = build(cuts, man, args, preset)

    # The trap this exporter exists to not repeat: a keep-list is not the film.
    stated = float(cuts.get("runtime") or 0.0)
    if stated and abs(stated - tl["runtime"]) > 0.5:
        msg = "the keep-list states %.2fs but these tracks run %.2fs (%.2fs adrift)" % (
            stated,
            tl["runtime"],
            stated - tl["runtime"],
        )
        if args.skip_bookends or args.list:
            tl["notes"].append(msg)
        else:
            sys.exit(
                "%s\nThe manifest's bookends are usually the difference. Resolve them, "
                "or pass --skip-bookends to export the keep-list alone." % msg
            )

    durations = {}
    for t in tl["tracks"]:
        for it in t["items"]:
            if it["kind"] == "clip" and it["src"] not in durations:
                durations[it["src"]] = probe_duration(it["src"])

    if args.list:
        report(tl, formats)
        unreadable = [k for k, v in durations.items() if not v]
        if unreadable:
            print()
            print("  %d source(s) unreadable here -- fcpxml would refuse:" % len(unreadable))
            for u in unreadable:
                print("    %s" % os.path.relpath(u, ROOT))
        return

    outdir = (
        _env.resolve(args.outdir)
        if args.outdir
        else _env.resolve(man.get("outdir") or os.path.dirname(mpath))
    )
    os.makedirs(outdir, exist_ok=True)
    written = []
    for f in formats:
        out = os.path.join(outdir, "%s.%s" % (mid, "xml" if f == "fcpxml" else f))
        if f == "otio":
            write_otio(tl, out, durations)
        elif f == "edl":
            write_edl(tl, out)
        elif f == "fcpxml":
            write_fcpxml(tl, out, durations)
        elif f == "srt":
            wpath = _env.resolve(args.words or man.get("words") or "")
            if not wpath or not os.path.exists(wpath):
                sys.exit("srt needs a word transcript; none at %s" % (wpath or "<unset>"))
            words = json.load(open(wpath, encoding="utf-8"))["words"]
            # the words are the BODY's; an opening bookend pushes them later
            n = write_srt(
                remap_words(words, cuts["keeps"], offset=tl["body_start"]), out, preset["srt"]
            )
            print("  %d cues" % n)
        written.append(out)
        print("  wrote %s" % os.path.relpath(out, ROOT))

    for n in tl["notes"]:
        print("  ! %s" % n)

    _project.record(
        mid,
        "resolve export (%s)" % ", ".join(formats),
        out=written[0],
        script="scripts/resolve-export.py",
        argv=sys.argv[1:],
        kind="interchange",
        manifest=os.path.relpath(mpath, ROOT),
        sidecars={os.path.splitext(w)[1].lstrip("."): w for w in written[1:]},
        note="editable timeline for DaVinci Resolve; cut decisions only -- "
        "no PiP transform, no burned graphics, no captions look",
    )


if __name__ == "__main__":
    main()
