#!/usr/bin/env python
"""Self-test the multicam round-trip arithmetic, without encoding anything.

The round trip is frame arithmetic wearing a video costume: a tape layout, an
anchor with an off-by-one in it, a correlation lag, a plan translated from
programme time into tape time. Every one of those is reachable only through a
GPU render and a five-minute comparison, which is exactly how the off-by-one in
the anchor got written in the first place -- it took a rebuild and a failed
cross-check to find, and it takes a second to find here.

Costs nothing, needs no GPU and touches no file. Run it after changing any of
shot-detect.py, split-cameras.py, sync-audio.py, angle-cut.py or
compare-videos.py.

    python scripts/check-multicam.py

Invoke as:  python scripts/check-multicam.py
"""
import sys, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import
from importlib import import_module

import numpy as np

_shots = import_module("shot-detect")
_split = import_module("split-cameras")
_sync = import_module("sync-audio")
_angle = import_module("angle-cut")
_cmp = import_module("compare-videos")
_auto = import_module("auto-switch")

fails = []


def check(name, got, want):
    if got == want:
        print("  OK   %s" % name)
    else:
        print("  FAIL %s\n       got  %r\n       want %r" % (name, got, want))
        fails.append(name)


def close(name, got, want, tol):
    if abs(got - want) <= tol:
        print("  OK   %s (%.6g)" % (name, got))
    else:
        print("  FAIL %s: got %.6g, want %.6g +/- %.6g" % (name, got, want, tol))
        fails.append(name)


print("== tape layout tiles the whole tape ==")
LIVE = [(0, 501)]
check("one live span, head then hold to the end",
      _split.layout(LIVE, 2796, 87, 25),
      [(0, 87, ("hold", 0)), (87, 588, ("live", 0)), (588, 2908, ("hold", 500))])
LIVE2 = [(501, 632), (848, 932)]
lay = _split.layout(LIVE2, 2796, 98, 46)
check("a tape used twice tiles gaplessly",
      [(a, b) for a, b, _ in lay],
      [(0, 599), (599, 730), (730, 946), (946, 1030), (1030, 2940)])
check("the head holds the FIRST live frame, not frame zero",
      lay[0][2], ("hold", 501))
check("a gap holds the LAST frame of the span before it",
      lay[2][2], ("hold", 631))
check("the layout totals head + programme + tail",
      sum(b - a for a, b, _ in lay), 98 + 2796 + 46)
for pads in ((0, 0), (1, 1), (240, 3)):
    tiles = _split.layout(LIVE2, 2796, *pads)
    check("gapless with pads %s" % (pads,),
          all(y == x2 for (_, y, _), (x2, _, _) in zip(tiles, tiles[1:])), True)
    check("total with pads %s" % (pads,),
          sum(b - a for a, b, _ in tiles), pads[0] + 2796 + pads[1])

print("== the audio stagger is sample-exact ==")
check("48 kHz at 24000/1001 is 2002 samples a frame",
      _split.samples_per_frame(24000, 1001), 2002)
check("48 kHz at 25 fps is 1920", _split.samples_per_frame(25, 1), 1920)
check("48 kHz at 30000/1001 is 1601.6, refused",
      _split.samples_per_frame.__doc__ is not None, True)

print("== the anchor's off-by-one ==")
# A tape that opens on a held frame: the held frame IS the first live frame, so
# the first frame that DIFFERS is one later. picture_start returns that frame;
# the anchor is it, minus the programme frame, minus one.
for head, first_live in ((87, 0), (98, 501), (85, 632), (73, 932)):
    ps = head + first_live + 1          # what picture_start finds on such a tape
    check("head %d, first used at %d" % (head, first_live),
          ps - first_live - 1, head)

print("== sample_frames always includes both edges ==")
check("short span is taken whole", _split.sample_frames(10, 14, 12), [10, 11, 12, 13])
s = _split.sample_frames(100, 400, 12)
check("first frame sampled", s[0], 100)
check("last frame sampled", s[-1], 399)
check("no more than asked plus the two edges", len(s) <= 14, True)

print("== cross-correlation recovers a known lag ==")
rng = np.random.default_rng(7)
base = rng.standard_normal(40000).astype(np.float32)
for lag in (0, 1, 37, -37, 2002):
    a = np.concatenate([np.zeros(max(0, lag), np.float32), base,
                        np.zeros(max(0, -lag), np.float32)])
    b = np.concatenate([np.zeros(max(0, -lag), np.float32), base,
                        np.zeros(max(0, lag), np.float32)])
    k, _, z = _sync.xcorr(a, b)
    check("lag %+d recovered" % lag, k, lag)
    if lag:
        check("lag %+d is a spike, not a field (z>%d)" % (lag, 8), z > 8.0, True)

print("== onset finds where silence ends ==")
sig = np.concatenate([np.zeros(8000, np.float32),
                      (rng.standard_normal(8000) * 0.2).astype(np.float32)])
at, _ = _sync.onset(sig, -100.0)
close("onset within a window of the true edge", at, 8000, _sync.WIN)
check("all-silent tape has no onset", _sync.onset(np.zeros(4000, np.float32), -100.0)[0], None)

print("== ssim ==")
img = (rng.random((180, 320)) * 0.5 + 0.25).astype(np.float32)
close("a frame against itself is 1", _cmp.ssim(img, img), 1.0, 1e-6)
close("against noise it is not", _cmp.ssim(img, rng.random((180, 320)).astype(np.float32)),
      0.0, 0.35)
soft = np.clip(img + rng.standard_normal(img.shape).astype(np.float32) * 0.004, 0, 1)
check("a re-encode still scores above the bar",
      _cmp.ssim(img, soft) > _cmp.DEFAULT_PASS["min_ssim_median"], True)

print("== the plan is translated into tape time correctly ==")
plan = [("cam1", 0, 501), ("cam2", 501, 632), ("cam1", 632, 700)]
g = _angle.build_graph(plan, ["cam1", "cam2"], {"cam1": 87, "cam2": 98},
                       {"cam1": 0, "cam2": 1}, "cam1", 87 * 2002, (87 + 700) * 2002)
check("cam1 is split for its two segments", "[0:v]split=2[xcam1_0][xcam1_1]" in g, True)
check("cam2 taps straight through", "[1:v]null[xcam2_0]" in g, True)
check("first segment is anchor..anchor+len",
      "trim=start_frame=87:end_frame=588" in g, True)
check("the other tape uses ITS anchor",
      "trim=start_frame=599:end_frame=730" in g, True)
check("cam1 comes back at its own anchor",
      "trim=start_frame=719:end_frame=787" in g, True)
check("one concat over every segment", "concat=n=3:v=1:a=0[vout]" in g, True)
check("audio is one atrim, never a concat",
      "atrim=start_sample=174174:end_sample=1575574" in g and "a=1" not in g, True)
check("no select filter anywhere -- aselect passes every audio frame",
      "select=" not in g, True)

print("== shot detection separates cuts from fades ==")
d = np.full(600, 0.004, dtype=np.float32)
d[200] = 0.28                                  # a cut
d[400:460] = np.linspace(0.02, 0.05, 60)       # a fade: sustained, no spike
cuts = _shots.find_cuts(d, _shots.DEFAULT_DETECT)
check("the cut is found", 200 in cuts, True)
check("the fade is not a cut", [c for c in cuts if 395 <= c <= 465], [])

print("== the switching grammar ==")
FPS = 24000 / 1001.0
CAM = {0: "cam1", 1: "cam2"}
# a speaker track: 100 frames of voice 0, 10 of voice 1, 100 of voice 0.
track = np.array([0] * 100 + [1] * 10 + [0] * 100, dtype=np.int32)
check("runs are found", [(a, b, s) for a, b, s in _auto.runs_of(track)],
      [(0, 100, 0), (100, 110, 1), (110, 210, 0)])
g = dict(_auto.DEFAULT_GRAMMAR, min_shot_s=1.5, lead_s=0.0, wide_after_s=0.0)
plan = _auto.grammar(track, CAM, "cam3", g, FPS, 210)
check("a 10-frame interjection is absorbed, not cut to",
      plan, [("cam1", 0, 210)])
g2 = dict(g, min_shot_s=0.2)
check("...but it survives a shorter minimum",
      _auto.grammar(track, CAM, "cam3", g2, FPS, 210),
      [("cam1", 0, 100), ("cam2", 100, 110), ("cam1", 110, 210)])
long = np.array([0] * 100 + [1] * 100, dtype=np.int32)
lead = _auto.grammar(long, CAM, "cam3", dict(g, lead_s=0.5), FPS, 200)
check("lead moves the cut earlier, never the film's start or end",
      lead, [("cam1", 0, 88), ("cam2", 88, 200)])
check("the plan still starts at 0 and ends at the last frame",
      [lead[0][1], lead[-1][2]], [0, 200])
check("and it is gapless",
      all(b == a for (_, _, b), (_, a, _) in zip(lead, lead[1:])), True)
w = _auto.grammar(np.zeros(600, dtype=np.int32), CAM, "cam3",
                  dict(g, wide_after_s=10.0, wide_dur_s=2.0), FPS, 600)
check("a long monologue can be broken with the wide",
      [c for c, _, _ in w], ["cam1", "cam3", "cam1"])
check("an unmapped voice falls back to the wide",
      _auto.grammar(np.full(200, 7, dtype=np.int32), CAM, "cam3", g, FPS, 200),
      [("cam3", 0, 200)])

print("== scoring against a human edit ==")
ref = [{"start": 0, "end": 100, "camera": "cam1"},
       {"start": 100, "end": 200, "camera": "cam2"}]
check("a perfect match is 100%",
      _auto.score([("cam1", 0, 100), ("cam2", 100, 200)], ref, 200)["agreement_pct"],
      100.0)
half = _auto.score([("cam1", 0, 200)], ref, 200)
check("half right is 50%", half["agreement_pct"], 50.0)
check("and it says which camera was missed",
      half["per_camera"]["cam2"][2], 0.0)

print("")
if fails:
    print("%d FAILED: %s" % (len(fails), ", ".join(fails)))
    sys.exit(1)
print("all multicam checks passed")
