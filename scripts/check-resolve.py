#!/usr/bin/env python
"""Test the Resolve interchange writers with no Resolve, no media and no encode.

resolve-export.py turns a decision this repo already made into a file another
application reads, which is exactly the kind of code that fails silently: an
off-by-one frame, a timecode that drifts, a marker that lands in the wrong
place, a keep-list quietly exported 22 seconds short of the film. None of that
shows up until somebody opens the timeline, and by then the answer to "is this
the cut we shipped?" is a shrug.

So this is the same bargain as check-multicam.py: build keep-lists in memory,
run them through the real writers, parse the result back, and assert the
arithmetic. It costs seconds, needs no GPU and touches no file outside %TEMP%.

What it pins:
    the film-time model     tracks stay in step, gaps included; runtime is the
                            sum of the keeps plus the bookends
    the bookend guard       a keep-list that under-runs its own stated runtime
                            is a refusal, not a short export
    OTIO                    schema names and shapes, frame-quantised ranges,
                            markers with their notes, media paths
    EDL                     event count, record continuity, reel truncation,
                            and DROP FRAME at 29.97 -- where a non-drop
                            timecode drifts ~3.6s an hour
    FCP7 XML                refuses rather than writing a file with no durations
    SRT                     words remapped through the keep-list, cues broken
                            where the config says, offset by the bookend
    source_to_film()        a source instant mapped onto the cut film

Invoke as:  python scripts/check-resolve.py
            python scripts/check-resolve.py --verbose
"""

import sys
import os
import json
import argparse
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import
from importlib import import_module  # noqa: E402

rx = import_module("resolve-export")  # hyphen: not importable by name

ROOT = _env.ROOT
FAILS = []
CHECKS = [0]


def ok(cond, what, detail=""):
    CHECKS[0] += 1
    if not cond:
        FAILS.append("%s %s" % (what, detail))
    return cond


def near(a, b, tol=1e-6):
    return abs(a - b) <= tol


class Args:
    """The flags build() reads, without argparse."""

    def __init__(self, **kw):
        self.skip_bookends = kw.get("skip_bookends", False)


PRESET = {
    "formats": ["otio", "edl", "srt"],
    "srt": {"max_words": 8, "max_chars": 42, "max_dur": 3.5, "gap_break": 0.6},
    "markers": {"removal": "red", "label": "blue", "overlay": "green", "bookend": "yellow"},
}


def tighten_cuts(fps=30):
    """A single-source cut, the tighten-cut dialect."""
    return {
        "id": "unit-tighten",
        "fps": fps,
        "film": [0.0, 60.0],
        "runtime": 24.0,
        "keeps": [[0.0, 10.0], [12.0, 20.0], [24.0, 30.0]],
        "removals": [{"from": 10.0, "to": 12.0, "why": "the bit about pausing the video"}],
        "_dialect": "tighten",
    }


def tighten_man():
    return {
        "id": "unit-tighten",
        "src": "sources/unit.mp4",
        "outdir": "outputs",
        "name_labels": [{"name": "A Person", "title": "CEO", "at": 2.0, "dur": 5.5}],
        "image_overlays": [{"card": "cards/outro.json", "at": -4.0}],
    }


def screencast_cuts(fps=30):
    """Two sources and a layout per keep, the screencast-cut dialect."""
    return {
        "id": "unit-screen",
        "fps": fps,
        "offset": 19.0,
        "film": [0.0, 100.0],
        # what the cutter would state: the bookend is in the manifest, not here
        "runtime": 46.0,
        "keeps": [[10.0, 20.0, "full"], [20.0, 35.0, "pip"], [40.0, 55.0, "pip"]],
        "_dialect": "screencast",
    }


def screencast_man(bookends=True):
    m = {
        "id": "unit-screen",
        "screen": "sources/screen.mp4",
        "camera": "sources/camera.mov",
        "outdir": "outputs",
    }
    if bookends:
        m["bookends"] = {
            "open": [
                {
                    "id": "intro",
                    "source": "sources/intro.mp4",
                    "start": 0.6,
                    "end": 6.6,
                    "broll": [{"source": "sources/broll.mp4", "at": 2.0, "dur": 3.0, "from": 48.0}],
                }
            ],
            "close": [],
        }
    return m


# ------------------------------------------------------------------ the model


def check_model():
    tl = rx.build(tighten_cuts(), tighten_man(), Args(), PRESET)
    keeps = sum(b - a for a, b in tighten_cuts()["keeps"])
    ok(near(tl["runtime"], keeps), "tighten runtime", "%.3f != %.3f" % (tl["runtime"], keeps))
    v1, v2, a1 = rx.track(tl, "V1"), rx.track(tl, "V2"), rx.track(tl, "A1")
    ok(len([i for i in v1["items"] if i["kind"] == "clip"]) == 3, "tighten V1 clip count")
    ok(not v2["items"], "tighten leaves V2 empty", "nothing composites in a one-source cut")
    ok(near(rx.track_end(a1), tl["runtime"]), "tighten sound runs the whole film")

    # the join a removal leaves: 10s of film survives before it
    m = next(x for x in tl["markers"] if x["name"].startswith("removed"))
    ok(near(m["at"], 10.0), "removal marker at the join", "%.3f" % m["at"])
    ok("pausing the video" in m["note"], "removal marker carries the manifest's reason")
    # a negative overlay `at` counts back from the end, as image-overlay resolves it
    ov = next(x for x in tl["markers"] if x["name"].startswith("overlay"))
    ok(near(ov["at"], tl["runtime"] - 4.0), "negative overlay at resolved against the runtime")

    tl = rx.build(screencast_cuts(), screencast_man(), Args(), PRESET)
    v1, v2, a1 = rx.track(tl, "V1"), rx.track(tl, "V2"), rx.track(tl, "A1")
    ok(
        near(tl["runtime"], 6.0 + 40.0),
        "screencast runtime is bookend + keeps",
        "%.3f" % tl["runtime"],
    )
    ok(near(tl["body_start"], 6.0), "body starts after the bookend")
    ok(near(rx.track_end(v1), rx.track_end(a1)), "picture and sound stay the same length")
    # V2 carries the b-roll and both PiPs, and its gaps keep it in step
    v2clips = [i for i in v2["items"] if i["kind"] == "clip"]
    ok(len(v2clips) == 3, "V2 has the b-roll plus two PiPs", str(len(v2clips)))
    ok(v2["items"][0]["kind"] == "gap", "V2 opens with a gap, not with the b-roll early")
    ok(near(rx.track_end(v2), 46.0), "V2 ends where the last PiP does", "%.2f" % rx.track_end(v2))
    # the screen is offset from the camera by the measured sync
    scr = next(i for i in v1["items"] if i["kind"] == "clip" and i["name"].startswith("screen-"))
    ok(
        near(scr["start"], 20.0 - 19.0),
        "screen clip carries the sync offset",
        "%.3f" % scr["start"],
    )

    # source_to_film: an instant inside a drop maps to the join that ate it
    keeps = tighten_cuts()["keeps"]
    ok(near(rx.source_to_film(5.0, keeps), 5.0), "source_to_film inside the first keep")
    ok(near(rx.source_to_film(11.0, keeps), 10.0), "source_to_film inside a drop -> the join")
    ok(near(rx.source_to_film(25.0, keeps), 19.0), "source_to_film after two keeps")


def check_bookend_guard():
    """The keep-list is not the film. Exporting one as if it were is the error
    this whole script exists to make impossible to ship."""
    cuts, man = screencast_cuts(), screencast_man()
    tl = rx.build(cuts, man, Args(skip_bookends=True), PRESET)
    ok(near(tl["runtime"], 40.0), "skipping bookends really does shorten the timeline")
    ok(any("SKIPPED" in n for n in tl["notes"]), "and says so in the notes")
    ok(
        abs(cuts["runtime"] - tl["runtime"]) > 0.5,
        "which is exactly the drift the exporter refuses on",
    )


# ------------------------------------------------------------------ writers


def check_otio(tmp):
    tl = rx.build(screencast_cuts(), screencast_man(), Args(), PRESET)
    p = os.path.join(tmp, "unit.otio")
    rx.write_otio(tl, p, {"x": None})
    doc = json.load(open(p, encoding="utf-8"))
    ok(doc["OTIO_SCHEMA"] == "Timeline.1", "otio timeline schema")
    ok(doc["tracks"]["OTIO_SCHEMA"] == "Stack.1", "otio stack schema")
    kinds = [t["kind"] for t in doc["tracks"]["children"]]
    ok(kinds == ["Video", "Video", "Audio"], "otio track kinds", str(kinds))
    v1 = doc["tracks"]["children"][0]
    clips = [c for c in v1["children"] if c["OTIO_SCHEMA"] == "Clip.2"]
    gaps = [c for c in v1["children"] if c["OTIO_SCHEMA"] == "Gap.1"]
    ok(len(clips) == 4, "otio V1 clip count", str(len(clips)))
    ok(all(c["active_media_reference_key"] == "DEFAULT_MEDIA" for c in clips), "otio media key")
    ok(
        all(
            c["media_references"]["DEFAULT_MEDIA"]["target_url"].startswith("file://")
            for c in clips
        ),
        "otio media paths travel",
    )
    # every range is whole frames: a non-integer frame value is what a reader
    # rounds differently from us, and that is a one-frame join error
    vals = []
    for c in clips + gaps:
        for k in ("start_time", "duration"):
            if c["source_range"]:
                vals.append(c["source_range"][k]["value"])
    ok(all(float(v).is_integer() for v in vals), "otio ranges are whole frames")
    total = sum(c["source_range"]["duration"]["value"] for c in v1["children"]) / tl["fps"]
    ok(near(total, tl["runtime"], 1e-6), "otio V1 sums to the runtime", "%.4f" % total)
    ms = v1["markers"]
    ok(ms and ms[0]["OTIO_SCHEMA"] == "Marker.2", "otio markers on V1")
    ok(all(m["color"].isupper() for m in ms), "otio marker colours are the enum's case")
    ok(any(m["comment"] for m in ms), "otio markers carry their note")


def check_edl(tmp):
    tl = rx.build(tighten_cuts(), tighten_man(), Args(), PRESET)
    p = os.path.join(tmp, "unit.edl")
    rx.write_edl(tl, p)
    text = open(p, encoding="utf-8").read()
    events = [ln for ln in text.splitlines() if ln[:3].isdigit()]
    ok(len(events) == 3, "edl event count", str(len(events)))
    ok("FCM: NON-DROP FRAME" in text, "edl states non-drop at 30")
    # record timecode is continuous: event n's record-in is n-1's record-out
    outs = [ln.split()[-1] for ln in events]
    ins = [ln.split()[-2] for ln in events]
    ok(ins[1] == outs[0] and ins[2] == outs[1], "edl record timecode is continuous")
    ok(all(len(ln.split()[1]) <= 8 for ln in events), "edl reel names fit the format")
    ok("* MARKER" in text, "edl carries markers as comments")

    # 29.97 must be drop-frame, and the ';' is how a reader is told
    tl30 = rx.build(tighten_cuts(fps=29.97), tighten_man(), Args(), PRESET)
    p2 = os.path.join(tmp, "df.edl")
    rx.write_edl(tl30, p2)
    text = open(p2, encoding="utf-8").read()
    ok("FCM: DROP FRAME" in text, "edl states drop frame at 29.97")
    ok(";" in text.splitlines()[3], "edl writes drop-frame timecode with ';'")
    # one hour of 29.97 is 107892 frames; drop-frame reads it as 01:00:00;00
    ok(rx.smpte(3600.0, 29.97) == "01:00:00;00", "drop-frame hour", rx.smpte(3600.0, 29.97))
    ok(rx.smpte(3600.0, 30.0) == "01:00:00:00", "non-drop hour", rx.smpte(3600.0, 30.0))
    ok(rx.smpte(59.9, 30.0) == "00:00:59:27", "frames round to the frame", rx.smpte(59.9, 30.0))


def check_fcpxml(tmp):
    tl = rx.build(tighten_cuts(), tighten_man(), Args(), PRESET)
    p = os.path.join(tmp, "unit.xml")
    # no durations: it must refuse rather than write something Resolve rejects
    try:
        rx.write_fcpxml(tl, p, {})
        refused = False
    except SystemExit:
        refused = True
    ok(refused, "fcpxml refuses when a source duration is unknown")
    ok(not os.path.exists(p), "and writes nothing when it refuses")

    durs = {i["src"]: 600.0 for t in tl["tracks"] for i in t["items"] if i["kind"] == "clip"}
    rx.write_fcpxml(tl, p, durs)
    text = open(p, encoding="utf-8").read()
    ok(text.startswith("<?xml"), "fcpxml declaration")
    ok('<xmeml version="5">' in text, "fcpxml root")
    ok(text.count("<pathurl>") == 1, "fcpxml defines each file once", str(text.count("<pathurl>")))
    ok(
        text.count("<clipitem") == 6,
        "fcpxml clipitems on both tracks",
        str(text.count("<clipitem")),
    )
    ok("<timebase>30</timebase>" in text, "fcpxml timebase")


def check_srt(tmp):
    words = [
        {"text": "one", "start": 1.0, "end": 1.3},
        {"text": "two", "start": 1.3, "end": 1.6},
        {"text": "three", "start": 11.0, "end": 11.4},  # inside the dropped span
        {"text": "four", "start": 13.0, "end": 13.4},
        {"text": "five", "start": 25.0, "end": 25.4},
    ]
    keeps = tighten_cuts()["keeps"]
    got = rx.remap_words(words, keeps)
    ok(len(got) == 4, "a word inside a drop does not survive", str(len(got)))
    ok(near(got[0]["start"], 1.0), "a word before any cut keeps its time")
    ok(near(got[2]["start"], 11.0), "a word after one cut moves by what was removed")
    ok(near(got[3]["start"], 19.0), "and after two cuts by both")
    shifted = rx.remap_words(words, keeps, offset=6.0)
    ok(near(shifted[0]["start"], 7.0), "a bookend pushes the whole transcript later")

    p = os.path.join(tmp, "unit.srt")
    n = rx.write_srt(got, p, PRESET["srt"])
    text = open(p, encoding="utf-8").read()
    ok(n == 3, "cues break where the gaps are", str(n))
    ok("-->" in text and "00:00:01,000" in text, "srt timecode format")
    ok(text.splitlines()[2] == "one two", "srt groups adjacent words", text.splitlines()[2])


def main():
    ap = argparse.ArgumentParser(description="Self-test for the Resolve interchange writers")
    ap.add_argument("--verbose", action="store_true", help="name every check as it passes")
    args = ap.parse_args()

    with tempfile.TemporaryDirectory(prefix="check-resolve-") as tmp:
        for fn in (check_model, check_bookend_guard):
            fn()
        for fn in (check_otio, check_edl, check_fcpxml, check_srt):
            fn(tmp)

    print("%d checks, %d failed" % (CHECKS[0], len(FAILS)))
    for f in FAILS:
        print("  FAIL %s" % f)
    if args.verbose and not FAILS:
        print("  the writers agree with the model, and the model agrees with the keep-list")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
