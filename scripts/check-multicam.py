#!/usr/bin/env python
"""Self-test the multicam round-trip arithmetic, without encoding anything.

The round trip is frame arithmetic wearing a video costume: a tape layout, an
anchor with an off-by-one in it, a correlation lag, a plan translated from
programme time into tape time. Every one of those is reachable only through a
GPU render and a five-minute comparison, which is exactly how the off-by-one in
the anchor got written in the first place -- it took a rebuild and a failed
cross-check to find, and it takes a second to find here.

Costs nothing, needs no GPU and touches no file. Run it after changing any of
shot-detect.py, split-cameras.py, sync-audio.py, angle-cut.py,
compare-videos.py, auto-switch.py or debug-notes.py.

    python scripts/check-multicam.py

Invoke as:  python scripts/check-multicam.py
"""

import sys
import os

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
_dbg = import_module("debug-notes")

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
check(
    "one live span, head then hold to the end",
    _split.layout(LIVE, 2796, 87, 25),
    [(0, 87, ("hold", 0)), (87, 588, ("live", 0)), (588, 2908, ("hold", 500))],
)
LIVE2 = [(501, 632), (848, 932)]
lay = _split.layout(LIVE2, 2796, 98, 46)
check(
    "a tape used twice tiles gaplessly",
    [(a, b) for a, b, _ in lay],
    [(0, 599), (599, 730), (730, 946), (946, 1030), (1030, 2940)],
)
check("the head holds the FIRST live frame, not frame zero", lay[0][2], ("hold", 501))
check("a gap holds the LAST frame of the span before it", lay[2][2], ("hold", 631))
check("the layout totals head + programme + tail", sum(b - a for a, b, _ in lay), 98 + 2796 + 46)
for pads in ((0, 0), (1, 1), (240, 3)):
    tiles = _split.layout(LIVE2, 2796, *pads)
    check(
        "gapless with pads %s" % (pads,),
        all(y == x2 for (_, y, _), (x2, _, _) in zip(tiles, tiles[1:])),
        True,
    )
    check("total with pads %s" % (pads,), sum(b - a for a, b, _ in tiles), pads[0] + 2796 + pads[1])

print("== audio boundaries: exact where possible, half a sample where not ==")
check(
    "24000/1001 stays exact: 87 frames is 87*2002 samples",
    _split.samples_at(87, 24000, 1001),
    87 * 2002,
)
check("25 fps stays exact", _split.samples_at(10, 25, 1), 10 * 1920)
check(
    "29.97 rounds: 1 frame of 1601.6 samples becomes 1602", _split.samples_at(1, 30000, 1001), 1602
)
check(
    "...and 10 frames is 16016 exactly (the .6s cancel)", _split.samples_at(10, 30000, 1001), 16016
)
worst = max(
    abs(_split.samples_at(f, 30000, 1001) - f * 48000 * 1001 / 30000.0) for f in range(1, 500)
)
check(
    "no boundary is ever more than half a sample out, and it cannot accumulate", worst <= 0.5, True
)

print("== the anchor's off-by-one ==")
# A tape that opens on a held frame: the held frame IS the first live frame, so
# the first frame that DIFFERS is one later. picture_start returns that frame;
# the anchor is it, minus the programme frame, minus one.
for head, first_live in ((87, 0), (98, 501), (85, 632), (73, 932)):
    ps = head + first_live + 1  # what picture_start finds on such a tape
    check("head %d, first used at %d" % (head, first_live), ps - first_live - 1, head)

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
    a = np.concatenate(
        [np.zeros(max(0, lag), np.float32), base, np.zeros(max(0, -lag), np.float32)]
    )
    b = np.concatenate(
        [np.zeros(max(0, -lag), np.float32), base, np.zeros(max(0, lag), np.float32)]
    )
    k, _, z = _sync.xcorr(a, b)
    check("lag %+d recovered" % lag, k, lag)
    if lag:
        check("lag %+d is a spike, not a field (z>%d)" % (lag, 8), z > 8.0, True)

print("== onset finds where silence ends ==")
sig = np.concatenate(
    [np.zeros(8000, np.float32), (rng.standard_normal(8000) * 0.2).astype(np.float32)]
)
at, _ = _sync.onset(sig, -100.0)
close("onset within a window of the true edge", at, 8000, _sync.WIN)
check("all-silent tape has no onset", _sync.onset(np.zeros(4000, np.float32), -100.0)[0], None)

print("== ssim ==")
img = (rng.random((180, 320)) * 0.5 + 0.25).astype(np.float32)
close("a frame against itself is 1", _cmp.ssim(img, img), 1.0, 1e-6)
close(
    "against noise it is not", _cmp.ssim(img, rng.random((180, 320)).astype(np.float32)), 0.0, 0.35
)
soft = np.clip(img + rng.standard_normal(img.shape).astype(np.float32) * 0.004, 0, 1)
check(
    "a re-encode still scores above the bar",
    _cmp.ssim(img, soft) > _cmp.DEFAULT_PASS["min_ssim_median"],
    True,
)

print("== the plan is translated into tape time correctly ==")
plan = [("cam1", 0, 501), ("cam2", 501, 632), ("cam1", 632, 700)]
g = _angle.build_graph(
    plan,
    ["cam1", "cam2"],
    {"cam1": 87, "cam2": 98},
    {"cam1": 0, "cam2": 1},
    "cam1",
    87 * 2002,
    (87 + 700) * 2002,
)
check("cam1 is split for its two segments", "[0:v]split=2[xcam1_0][xcam1_1]" in g, True)
check("cam2 taps straight through", "[1:v]null[xcam2_0]" in g, True)
check("first segment is anchor..anchor+len", "trim=start_frame=87:end_frame=588" in g, True)
check("the other tape uses ITS anchor", "trim=start_frame=599:end_frame=730" in g, True)
check("cam1 comes back at its own anchor", "trim=start_frame=719:end_frame=787" in g, True)
check("one concat over every segment", "concat=n=3:v=1:a=0[vout]" in g, True)
check(
    "audio is one atrim, never a concat",
    "atrim=start_sample=174174:end_sample=1575574" in g and "a=1" not in g,
    True,
)
check("no select filter anywhere -- aselect passes every audio frame", "select=" not in g, True)

print("== shot detection separates cuts from fades ==")
d = np.full(600, 0.004, dtype=np.float32)
d[200] = 0.28  # a cut
d[400:460] = np.linspace(0.02, 0.05, 60)  # a fade: sustained, no spike
cuts = _shots.find_cuts(d, _shots.DEFAULT_DETECT)
check("the cut is found", 200 in cuts, True)
check("the fade is not a cut", [c for c in cuts if 395 <= c <= 465], [])

print("== the switching grammar ==")
FPS = 24000 / 1001.0
CAM = {0: "cam1", 1: "cam2"}
# a speaker track: 100 frames of voice 0, 10 of voice 1, 100 of voice 0.
track = np.array([0] * 100 + [1] * 10 + [0] * 100, dtype=np.int32)
check(
    "runs are found",
    [(a, b, s) for a, b, s in _auto.runs_of(track)],
    [(0, 100, 0), (100, 110, 1), (110, 210, 0)],
)


def shape(plan):
    """(camera, start, end) only -- the reason is prose and tested separately."""
    return [(c, a, b) for c, a, b, _ in plan]


g = dict(_auto.DEFAULT_GRAMMAR, min_shot_s=1.5, lead_s=0.0, wide_after_s=0.0)
plan = _auto.grammar(track, CAM, "cam3", g, FPS, 210)
check("a 10-frame interjection is absorbed, not cut to", shape(plan), [("cam1", 0, 210)])
g2 = dict(g, min_shot_s=0.2)
check(
    "...but it survives a shorter minimum",
    shape(_auto.grammar(track, CAM, "cam3", g2, FPS, 210)),
    [("cam1", 0, 100), ("cam2", 100, 110), ("cam1", 110, 210)],
)
long = np.array([0] * 100 + [1] * 100, dtype=np.int32)
lead = _auto.grammar(long, CAM, "cam3", dict(g, lead_s=0.5), FPS, 200)
check(
    "lead moves the cut earlier, never the film's start or end",
    shape(lead),
    [("cam1", 0, 88), ("cam2", 88, 200)],
)
check(
    "every shot carries a reason for the debug notes",
    all(isinstance(w, str) and w for _, _, _, w in lead),
    True,
)
check("and the reason names the voice behind it", "voice 1" in lead[1][3], True)
check("the plan still starts at 0 and ends at the last frame", [lead[0][1], lead[-1][2]], [0, 200])
check("and it is gapless", all(b == a for (_, _, b, _), (_, a, _, _) in zip(lead, lead[1:])), True)
w = _auto.grammar(
    np.zeros(600, dtype=np.int32), CAM, "cam3", dict(g, wide_after_s=10.0, wide_dur_s=2.0), FPS, 600
)
check(
    "a long monologue can be broken with the wide",
    [c for c, _, _, _ in w],
    ["cam1", "cam3", "cam1"],
)
check(
    "an unmapped voice falls back to the wide",
    shape(_auto.grammar(np.full(200, 7, dtype=np.int32), CAM, "cam3", g, FPS, 200)),
    [("cam3", 0, 200)],
)

print("== scoring against a human edit ==")
ref = [{"start": 0, "end": 100, "camera": "cam1"}, {"start": 100, "end": 200, "camera": "cam2"}]
check(
    "a perfect match is 100%",
    _auto.score([("cam1", 0, 100, "x"), ("cam2", 100, 200, "y")], ref, 200, FPS)["agreement_pct"],
    100.0,
)
half = _auto.score([("cam1", 0, 200, "x")], ref, 200, FPS)
check("half right is 50%", half["agreement_pct"], 50.0)
check("and it says which camera was missed", half["per_camera"]["cam2"][2], 0.0)

print("== clustering scales to a long film ==")
_c = rng.standard_normal((3, 192)).astype(np.float32)
_c /= np.linalg.norm(_c, axis=1, keepdims=True)


def voices(n, spread=0.18):
    who = rng.integers(0, 3, n)
    V = _c[who] + rng.standard_normal((n, 192)).astype(np.float32) * spread
    return V / np.linalg.norm(V, axis=1, keepdims=True), who


def purity(lab, who, k=3):
    import itertools

    n = len(who)
    return max(
        sum(int(((lab == i) & (who == p[i])).sum()) for i in range(k))
        for p in itertools.permutations(range(k))
    ) / float(n)


V, who = voices(400)
check("exact below the cap: every window keeps a label", len(_auto.cluster(V, 3)[0]), 400)
check("...and finds the three voices", purity(_auto.cluster(V, 3)[0], who) > 0.95, True)
# An hour of film is ~7200 windows. The old merge recomputed every pair from
# its members on every merge and never returned; this must stay affordable.
import time as _t

V, who = voices(7200)
_t0 = _t.perf_counter()
lab, groups = _auto.cluster(V, 3)
_el = _t.perf_counter() - _t0
check("an hour of windows still labels every one", len(lab), 7200)
check("...into three voices", len(groups), 3)
check("...correctly", purity(lab, who) > 0.95, True)
check("...in under a minute (took %.1fs)" % _el, _el < 60.0, True)
check("separation stays cheap too", _auto.separation(V, lab)[1] is not None, True)

print("== a film with one camera is not a shot list ==")
# `between` is None when only one identity is found: nothing was measured
# against anything. That used to pass the separation guard by default, so a
# Zoom webinar -- one webcam tile over slides, zero camera cuts -- came back as
# "2 angles, between n/a" and would have been handed to split-cameras.
check("one identity refuses", _shots.NOT_MULTICAM[:22], "there is only one iden")
_between, _names = None, ["cam1", "cam2"]
check("...the condition that catches it", _between is None and len(set(_names)) > 1, True)
_between, _names = None, ["cam1"]
check("a genuine single-angle list is not caught", _between is None and len(set(_names)) > 1, False)
_between, _names = 0.9, ["cam1", "cam2"]
check("a film that DID separate is not caught", _between is None and len(set(_names)) > 1, False)

print("== K counts people, not clusters ==")
# The geometry is the real film's, not an invented one: two people in one room
# share a microphone, a codec and an accent, so their windows sit far closer to
# each other than a speck -- a cough, a clipped word, a bar of music -- sits to
# anything. Average linkage then merges two SPEAKERS before it absorbs a speck,
# so asking for exactly K groups hands slots to the specks and leaves people
# fused. Reproduces the podcast's own numbers: 46/40/14 against its 47/38/15.
_base = rng.standard_normal(192).astype(np.float32)
_p = _base + 1.2 * rng.standard_normal((3, 192)).astype(np.float32)
_p /= np.linalg.norm(_p, axis=1, keepdims=True)
_who = np.array([0] * 300 + [1] * 260 + [2] * 90)
V = np.vstack(
    [
        _p[_who] + rng.standard_normal((len(_who), 192)).astype(np.float32) * 0.03,
        rng.standard_normal((4, 192)).astype(np.float32),
    ]
)
V /= np.linalg.norm(V, axis=1, keepdims=True)


def n_people(lab):
    return sum(1 for k in set(lab.tolist()) if (lab == k).sum() >= _auto.MIN_VOICE_SHARE * len(lab))


check("asking for exactly K leaves the speakers fused", n_people(_auto.cluster(V, 3)[0]), 1)

lab, groups, k_used, n_big = _auto.cluster_people(V, 3)
check("cluster_people finds all three people", n_big, 3)
check("...by raising k past the specks", k_used > 3, True)
check("...every window still has a label", len(lab), len(V))
check(
    "...and the quiet one survives",
    min(sorted((int((lab == k).sum()) for k in set(lab.tolist())), reverse=True)[:3]) > 50,
    True,
)
check(
    "headroom 0 cannot raise k, and reports the shortfall",
    _auto.cluster_people(V, 3, headroom=0)[3] < 3,
    True,
)

print("== the speaker model's length ceiling ==")
# TitaNet's ONNX export raises above 12288 feature frames (122.88 s). A stub
# extractor stands in for it here: no model, no audio, and it FAILS the way
# the real one does, so the chunking is what is being tested rather than a
# lucky length.
CEILING = int(122.88 * _auto.SR)


class Stub:
    """Refuses anything the real model refuses; embeds towards a fixed vector."""

    def __init__(self):
        self.sizes = []

    def create_stream(self):
        self.buf = None
        return self

    def accept_waveform(self, sr, x):
        self.buf = x

    def input_finished(self):
        pass

    def compute(self, _s):
        n = self.buf.size
        self.sizes.append(n)
        if n > CEILING:
            raise RuntimeError(
                "Attempting to broadcast an axis by a dimension "
                "other than 1. 12288 by %d" % (n // 160)
            )
        v = np.zeros(8, dtype=np.float32)
        v[0] = 1.0
        v[1] = float(n) / CEILING
        return v


stub = Stub()
short = np.zeros(int(30 * _auto.SR), dtype=np.float32)
v = _auto.embed_span(stub, short)
check("a short span is one call", len(stub.sizes), 1)
close("...and comes back unit norm", float(np.linalg.norm(v)), 1.0, 1e-5)

stub = Stub()
long_ = np.zeros(int(200 * _auto.SR), dtype=np.float32)
v = _auto.embed_span(stub, long_)
check("200 s does not reach the model in one piece", max(stub.sizes) <= CEILING, True)
check("...it is cut into whole chunks plus a tail", len(stub.sizes), 4)
close("...and the average is renormalised", float(np.linalg.norm(v)), 1.0, 1e-5)

stub = Stub()
_auto.embed_span(stub, np.zeros(int(120.1 * _auto.SR), dtype=np.float32))
check("a span just under the ceiling is still split, not risked", max(stub.sizes) <= CEILING, True)

print("== angle identity by person ==")


def unit(v):
    v = np.array(v, dtype=np.float32)
    return v / np.linalg.norm(v)


A_ = unit([1, 0, 0, 0.1])
B_ = unit([0, 1, 0, 0.1])
C_ = unit([0, 0, 1, 0.1])
fs = {0: A_, 1: B_, 2: unit([0.98, 0.05, 0, 0.1]), 3: C_, 4: unit([0.02, 0.99, 0, 0.1])}
check(
    "three people found from five shots", _shots.group_by_identity(fs, 0.5), [[0, 2], [1, 4], [3]]
)
check(
    "a tighter bar splits nobody who is really one person",
    _shots.group_by_identity({0: A_, 1: unit([0.995, 0.02, 0, 0.1])}, 0.5),
    [[0, 1]],
)
check("an empty film has no people", _shots.group_by_identity({}, 0.5), [])
# a bridge shot halfway between two people cannot chain them into one
bridge = unit([1, 1, 0, 0.1])
got = _shots.group_by_identity({0: A_, 1: B_, 2: bridge}, 0.5)
check("a between-two-people shot cannot merge them", len(got) >= 2, True)
# average linkage absorbs a pose outlier that complete linkage refuses: one
# far pairwise (0.6) does not veto a shot whose MEAN distance to the person
# is fine -- an outstretched arm earned itself a phantom camera this way
Dm = np.array(
    [
        [0.00, 0.05, 0.05, 0.60, 0.90],
        [0.05, 0.00, 0.05, 0.30, 0.90],
        [0.05, 0.05, 0.00, 0.30, 0.90],
        [0.60, 0.30, 0.30, 0.00, 0.90],
        [0.90, 0.90, 0.90, 0.90, 0.00],
    ]
)
check(
    "a pose outlier is absorbed by its person, not made a camera",
    _shots._agg_threshold(Dm, 0.5),
    [[0, 1, 2, 3], [4]],
)
check(
    "nothing merges when nothing is alike",
    _shots._agg_threshold(np.full((3, 3), 0.7), 0.5),
    [[0], [1], [2]],
)
check("an empty matrix has no groups", _shots._agg_threshold(np.zeros((0, 0)), 0.5), [])

print("== debug notes ==")
check(
    "opaque ink writes alpha 00 -- ASS alpha is inverted, and getting this "
    "backwards renders NOTHING while the box shows fine",
    _dbg.ass_colour("#FFFFFF", 1.0),
    "&H00FFFFFF",
)
check("invisible writes FF", _dbg.ass_colour("#000000", 0.0)[:4], "&HFF")
check("the 1c override form carries no alpha byte", _dbg.ass_1c("#7FD1C4"), "&HC4D17F&")
check(
    "braces cannot open an override block from note text",
    _dbg.esc_text("a{b}c" + chr(92)),
    "a(b)c/",
)
check(
    "a drive letter never reaches a filter option",
    ":" in _dbg.filter_path(os.path.join(_dbg.ROOT, "temp", "x.ass")),
    False,
)
check("centiseconds format", _dbg.fmt_cs(360000 + 6000 + 100 + 1), "1:01:01.01")

print()
if fails:
    print("%d FAILED: %s" % (len(fails), ", ".join(fails)))
    sys.exit(1)
print("all multicam checks passed")
