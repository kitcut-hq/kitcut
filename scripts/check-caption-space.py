#!/usr/bin/env python
"""Is the caption card sitting on the speaker's face?

A short can pass every check this repo already has -- frame-accurate cut, right
duration, 24/24 caption-sync probes, a hook inside 3 s, a settled opening frame
-- and still be unusable because the caption card is parked across the mouth.
Nothing measured that, because nothing was looking at the video and the captions
in the same coordinate system at the same time. That shipped: `g-YDNJcyuck`
clip 01 covered Rachel Metz's mouth completely for the last eight seconds, and
two rounds of frame spot-checks missed it because the frames I happened to pick
were the ones where it looked fine.

**The mistake underneath it is worth naming, because it will recur.** Caption
placement was inherited from a preset whose `bottom_margin_px` was measured on
somebody else's framing -- a loose podcast two-shot, where 602 px above the
frame bottom lands on the chest. The same 602 px on a tight news close-up lands
on the mouth. **A caption position is only safe relative to a framing**, so the
moment a crop changes -- and `crop_zoom` here changed twice to clear a broadcast
lower third -- the placement has to be re-measured, not re-used.

This is pure geometry, so unlike the mouth-openness detector rejected in
`check-openings.py` it can be measured honestly: YuNet gives a face box and five
landmarks, two of them mouth corners, and the caption card rectangle is already
written out per group by `build-captions-ass.py --debug-out`. Both are in output
pixels. The rest is intersection.

**It reads the RENDER, not the plan.** Deriving where the card will land from
the manifest means re-deriving the crop, and this repo has already paid for that
twice (`docs/retro-books-giveaway.md`: the mapping from source time back through
the cut is where the day goes, and two separate bugs lived there). The rendered
mp4 is the only artifact that cannot lie about what a viewer sees. The cost is
that a failure arrives after an encode -- which for a 30 s short is under a
minute, and is the cheaper half of the trade.

Verdicts, per caption group:

  * **FAIL -- mouth covered.** The midpoint of the two mouth-corner landmarks
    is inside the card. Not arguable and not stylistic; fix the placement.
  * **FAIL -- face eaten.** The card covers `FACE_FRAC` or more of the face
    box, even if the mouth itself escaped.
  * **WARN -- card in the face box.** The card's top edge is above the bottom of
    the face box. Often fine (YuNet's box stops around the mouth, so this is
    usually the chin), but it is where the next failure comes from.

A clip whose framing has been looked at and accepted anyway carries
`"caption_space_ok": "<why>"` in the manifest and stops being flagged -- the
same bargain `open_ok` and `checked_utc` strike elsewhere: the check keeps its
teeth and the reviewed exception is recorded next to the thing it excuses.

Invoke as:  python scripts/check-caption-space.py --manifest projects/<id>/clips-vertical.json
            python scripts/check-caption-space.py --manifest ... --list
"""

import sys
import os
import json
import argparse
import importlib
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import

import cv2
import numpy as np

_cut = importlib.import_module("cut-clips")  # hyphen: see CLAUDE.md
_outline = importlib.import_module("transcript-outline")
_project = importlib.import_module("_project")

ROOT = _env.ROOT

# Fraction of the face box the card may cover before it stops being a chin
# graze and starts being a blindfold. 0.15 is a card clipping the very bottom of
# YuNet's box, which sits around the mouth line; at 0.25 it is over the lips.
FACE_FRAC = 0.15
# YuNet confidence floor. Deliberately BELOW shot-detect.py's 0.7, and that is
# the whole point: a face the card is sitting on is a partly occluded face, so
# the frames this check exists to catch are exactly the frames the detector is
# least sure about. On the render that shipped, the worst frame -- card straight
# across the mouth -- scored 0.67 and was silently skipped at 0.7, while every
# frame where the card behaved scored 0.72-0.80. A floor tuned for "is this a
# face" is the wrong floor for "is this face being covered".
DET_SCORE = 0.5
# Above this share of sampled frames with no face at all, say so loudly rather
# than reporting a clean pass: "no face found" is how this check fails open.
BLIND_FRAC = 0.34
DET_MODEL = "models/face/face_detection_yunet_2023mar.onnx"


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def card_groups(clip, words_path, style, start, end, w, h, tmpdir, fontsdir):
    """The caption card rectangle and time window of every group, in OUTPUT px.

    Built by the same script and the same arguments the render used, so the
    rectangles are the render's own, not a second opinion about them.
    """
    dbg = os.path.join(tmpdir, "%s.capspace.json" % clip["id"]).replace("\\", "/")
    ass = os.path.join(tmpdir, "%s.capspace.ass" % clip["id"]).replace("\\", "/")
    cmd = _cut.PY + [
        "scripts/build-captions-ass.py",
        "--words",
        words_path,
        "--style",
        style,
        "--out",
        ass,
        "--debug-out",
        dbg,
        "--scale-to",
        str(w),
        str(h),
        "--range",
        "%.3f" % start,
        "%.3f" % end,
        "--time-offset",
        "%.3f" % start,
    ]
    if subprocess.run(cmd, cwd=ROOT, env=_cut.ENV).returncode:
        sys.exit("%s: could not rebuild caption geometry" % clip["id"])
    d = load(dbg)  # a bare list of groups, rebased to clip t=0
    out = []
    for g in d:
        cx0, cy0, cw, ch = g["card"]
        out.append(
            dict(
                gi=g["gi"],
                t0=g["g0"] / 100.0,
                t1=g["g1"] / 100.0,
                card=(float(cx0), float(cy0), float(cw), float(ch)),
                text=" ".join(w["t"] for w in g.get("words", [])),
            )
        )
    return out


def detector(w, h):
    p = _env.resolve(DET_MODEL)
    if not os.path.exists(p):
        sys.exit(
            "no face model at %s -- see the video-multicam-switch skill "
            "for the download command" % _project.norm(p)
        )
    return cv2.FaceDetectorYN_create(p, "", (int(w), int(h)), DET_SCORE)


def best_face(det, frame):
    """The highest-scoring face as (box, mouth_xy), or None.

    YuNet's row is [x, y, w, h, then 5 landmark xy pairs, then score]; landmarks
    are right eye, left eye, nose, right mouth corner, left mouth corner.
    """
    n, faces = det.detect(frame)
    if faces is None or not len(faces):
        return None
    f = max(faces, key=lambda r: r[-1])
    box = (float(f[0]), float(f[1]), float(f[2]), float(f[3]))
    mouth = ((float(f[10]) + float(f[12])) / 2.0, (float(f[11]) + float(f[13])) / 2.0)
    return box, mouth


def overlap_frac(card, box):
    cx, cy, cw, ch = card
    bx, by, bw, bh = box
    ix = max(0.0, min(cx + cw, bx + bw) - max(cx, bx))
    iy = max(0.0, min(cy + ch, by + bh) - max(cy, by))
    area = bw * bh
    return (ix * iy / area) if area > 0 else 0.0


def gap(card, box):
    """Vertical separation between card and face box: + apart, - overlapping.

    Signed the same whichever side the card is on, because a card ABOVE the head
    is a legitimate placement -- and on a tight close-up it is the only one, so a
    metric that only understood "below" reported every top-placed card as a near
    miss.
    """
    cy, ch = card[1], card[3]
    by, bh = box[1], box[3]
    return max(cy - (by + bh), by - (cy + ch))


def mouth_covered(card, mouth, face_h):
    """Is the card sitting on the mouth?

    YuNet's landmark is the midpoint of the two mouth CORNERS, not the lower
    lip, and the lip plus the soft chin under it run up to ~10% of the face
    height below it. Testing the bare point lets a card that plainly covers the
    mouth escape on a technicality: on the frame that shipped, the landmark was
    at y 1163 and the card's top edge at y 1173 -- a 10 px "miss" that a viewer
    reads as the mouth being gone. So the test is a band, not a point.
    """
    cx, cy, cw, ch = card
    if not (cx <= mouth[0] <= cx + cw):
        return False
    lo, hi = mouth[1] - 0.02 * face_h, mouth[1] + 0.10 * face_h
    return not (cy > hi or cy + ch < lo)


def judge(groups, video, samples):
    """Sample one frame per caption group (up to `samples`) and score it."""
    cap = cv2.VideoCapture(video)
    if not cap.isOpened():
        sys.exit("cannot open %s" % _project.norm(video))
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    det = detector(w, h)
    pick = (
        groups
        if len(groups) <= samples
        else [groups[i] for i in np.linspace(0, len(groups) - 1, samples).astype(int)]
    )
    rows = []
    for g in pick:
        # Midpoint of the group: the card is fully up, past its fade.
        t = (g["t0"] + g["t1"]) / 2.0
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
        ok, frame = cap.read()
        if not ok or frame is None:
            continue
        got = best_face(det, frame)
        if got is None:
            rows.append(dict(g, t=t, face=None))
            continue
        box, mouth = got
        rows.append(
            dict(
                g,
                t=t,
                face=box,
                mouth=mouth,
                frac=overlap_frac(g["card"], box),
                mouth_hit=mouth_covered(g["card"], mouth, box[3]),
                clearance=gap(g["card"], box),
            )
        )
    cap.release()
    return rows, (w, h)


def report(cid, rows, size, verbose):
    """Print the worst of it, and return (fails, warns)."""
    seen = [r for r in rows if r.get("face")]
    if not seen:
        print("  %-28s no face found in %d sampled frame(s) -- nothing to judge" % (cid, len(rows)))
        return 0, 0
    blind = (len(rows) - len(seen)) / float(max(1, len(rows)))
    mouth = [r for r in seen if r["mouth_hit"]]
    eaten = [r for r in seen if not r["mouth_hit"] and r["frac"] >= FACE_FRAC]
    graze = [r for r in seen if not r["mouth_hit"] and r["frac"] < FACE_FRAC and r["clearance"] < 0]
    worst = max(seen, key=lambda r: r["frac"])
    print(
        "  %-28s %d/%d frames with a face | worst cover %.0f%% of the face "
        "at %.1fs | min clearance %+.0f px"
        % (
            cid,
            len(seen),
            len(rows),
            100 * worst["frac"],
            worst["t"],
            min(r["clearance"] for r in seen),
        )
    )
    if verbose:
        for r in seen:
            tag = (
                "MOUTH"
                if r["mouth_hit"]
                else "EATEN"
                if r["frac"] >= FACE_FRAC
                else "graze"
                if r["clearance"] < 0
                else "ok"
            )
            print(
                "      %6.2fs  %-5s  cover %3.0f%%  clearance %+5.0f px  %s"
                % (r["t"], tag, 100 * r["frac"], r["clearance"], r["text"][:46])
            )
    for r in mouth[:3]:
        print(
            "      FAIL  %.2fs the card covers the MOUTH (card top %.0f, "
            "mouth y %.0f)" % (r["t"], r["card"][1], r["mouth"][1])
        )
    for r in eaten[:3]:
        print("      FAIL  %.2fs the card covers %.0f%% of the face" % (r["t"], 100 * r["frac"]))
    if graze:
        print(
            "      warn  %d frame(s) put the card inside the face box "
            "(chin); nearest miss %+.0f px" % (len(graze), min(r["clearance"] for r in graze))
        )
    extra = 0
    if blind >= BLIND_FRAC:
        print(
            "      warn  no face in %.0f%% of sampled frames -- this check "
            "fails OPEN when the detector misses, so go and look at those "
            "frames before trusting a pass" % (100 * blind)
        )
        extra = 1
    return len(mouth) + len(eaten), len(graze) + extra


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--only", help="comma-separated clip ids")
    ap.add_argument("--samples", type=int, default=16, help="caption groups sampled per clip")
    ap.add_argument(
        "--list",
        action="store_true",
        help="report every sampled frame and always exit 0 -- "
        "prices a placement change without blocking on it",
    )
    args = ap.parse_args()

    mp = _env.resolve(args.manifest)
    m = load(mp)
    caps = m.get("captions")
    if not caps:
        sys.exit("manifest has no `captions` block -- nothing to check")
    words = _env.resolve(m["words"])
    src = _env.resolve(m["source"])
    outdir = _env.resolve(m.get("outdir", "outputs/shorts"))
    prefix = m.get("prefix", "")
    pad = m.get("pad", {})
    ph, pt = float(pad.get("head", 0.0)), float(pad.get("tail", 0.0))
    tmpdir = _env.resolve(m.get("tmp") or os.path.join(os.path.dirname(mp), "temp"))
    os.makedirs(tmpdir, exist_ok=True)
    wl = _outline.load_words(m["words"])
    only = set((args.only or "").split(",")) if args.only else None

    print("captions %s" % caps["style"])
    print("fail when the card covers the mouth, or >= %.0f%% of the face\n" % (100 * FACE_FRAC))

    fails = warns = skipped = 0
    for clip in m["clips"]:
        if only and clip["id"] not in only:
            continue
        name = "%s-%s" % (prefix, clip["id"]) if prefix else clip["id"]
        rendered = os.path.join(outdir, name + ".mp4")
        if not os.path.exists(rendered):
            print("  %-28s not rendered yet -- skipped" % clip["id"])
            skipped += 1
            continue
        cp = clip.get("pad", {})
        start, end = _cut.resolve(clip, wl, float(cp.get("head", ph)), float(cp.get("tail", pt)))
        cap = cv2.VideoCapture(rendered)
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()
        # The style must go through the SAME per-clip override path the render
        # used (`clip_style`), or the checker verifies a card position that is
        # not on the video. That is not hypothetical: clip 02 of g-YDNJcyuck
        # renders with a per-clip `bottom_margin_px` override, and this
        # checker's first version rebuilt geometry from the bare preset -- it
        # reported +319 px clearance for a card location the render does not
        # use. A guard that checks the wrong geometry passes for the wrong
        # reason, which is worse than no guard.
        cl_caps = dict(caps, **(clip.get("captions") or {}))
        style = _cut.clip_style(cl_caps, clip, tmpdir)
        groups = card_groups(
            clip, words, style, start, end, w, h, tmpdir, m.get("fontsdir", "fonts")
        )
        rows, size = judge(groups, rendered, args.samples)
        f, wn = report(clip["id"], rows, size, args.list)
        why = clip.get("caption_space_ok")
        if f and why:
            print("      accepted by caption_space_ok: %s" % why)
            f = 0
        fails += f
        warns += wn

    print("\n%d fail, %d warn%s" % (fails, warns, ", %d not rendered" % skipped if skipped else ""))
    if fails and not args.list:
        print(
            "\nThe card is on the face. Fix the PLACEMENT against THIS "
            "framing -- `layout.bottom_margin_px` in the preset, or a preset "
            "of its own for this crop. Do not reuse a margin measured on a "
            "looser shot, which is what caused this. If the framing has been "
            "reviewed and accepted, record why in the clip's "
            '"caption_space_ok".'
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
