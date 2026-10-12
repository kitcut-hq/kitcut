#!/usr/bin/env python
"""Remove the working pictures a finished film leaves in its temp/ folder.

    python studio/prune.py --plan [--older-than 6] [--film <id>]   what would go; removes nothing
    python studio/prune.py [--older-than 6] [--film <id>]          remove it
    (on the VM: ops.sh prune [--plan]; every hour by kitcut-prune.timer)

Why: every film is read a frame or two a second before it is called done (tools.film_sheets,
review.py), and its thumbnails are cut from stills of it (scripts/_thumb.py). Those frames are
full-size PNGs, about 3 MB each, and nothing removed them. Measured on the VM's 512 GB data disk,
2026-10-12: 222 GB of the 399 in use, 61,659 files, growing 48 GB a day since the review went
live on 2026-10-07 -- two days from a full disk, and a full disk stops every film (KI-063).

What goes:

    temp/motion                 the film a few times a second and the probe's report. A cache:
                                both readers (tools._motion_fresh, review.folder_frames) render
                                it again when it is not there
    temp/motion-before          review.fix's copy of it, read only inside that one fix
    temp/motion-after           the frames after the fix, likewise
    temp/strip                  a close look's frames: every call removes and renders them again
    temp/thumbs/**/*.png        the thumbnail stills: _thumb.render_stills renders the ones that
                                are missing. The moments sheet, style.json and boxes.json beside
                                them stay (the draft reads the sheet and never waits for a render)
    temp/*_silent.mp4,          the render before its sound was added (sketch-render.py): the
    temp/*_silent_segments      film itself is outputs/film.mp4

The four folders go whole, in one rename and then removed, so a reader finds a cache or none,
never half of one (a motion folder with its report and no frames would be read as a film in which
nothing is drawn). What never goes: temp/brand (the Free plan's closing, which the film's manifest
loads), temp/record.lock, temp/lines, and anything not named above.

Of which films: one that is over -- not being made, not waiting for its narrator's voice -- with
no round of changes and no unbranding under way, and only a piece nothing has written to for
--older-than hours (a thumbnail being made writes into temp/thumbs as it goes). A round works on
its own copy and never takes temp/ along (rounds.OWN), so pruning cannot break a later version.
"""

import os
import re
import sys
import json
import time
import shutil
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import film as films  # noqa: E402 -- the stdlib and locks.py only: this runs from a timer

OLDER_H = 6.0
WHOLE = ("motion", "motion-before", "motion-after", "strip")  # folders that go whole
STILLS = ("thumbs",)  # folders that lose only their *.png
SILENT = re.compile(r"_silent(\.mp4|_segments)$")
GONE = re.compile(r"\.pruned-\d+$")  # a folder renamed to be removed, left by a run that died
# the same paths and words rounds.py and unbrand.py use (test_prune.py holds them to it): not
# imported, because both import the whole studio and this runs every hour beside the films
ROUND_MARKS = os.path.join(films.HOME, "rounds", "_asked")
UNBRAND_MARKS = os.path.join(films.HOME, "unbrand")
ROUND_ACTIVE = ("queued", "running", "finishing")


def busy(f):
    """Why this film's temp/ is left alone now, or None."""
    rec = f.record()
    st = f.state
    if st in films.ACTIVE or st == "waiting":
        return "being made"
    if (rec.get("round") or {}).get("state") in ROUND_ACTIVE or os.path.exists(
        os.path.join(ROUND_MARKS, f.id + ".json")
    ):
        return "being changed"
    if os.path.exists(os.path.join(UNBRAND_MARKS, f.id + ".json")):
        return "being drawn again"
    return None


def _tree(p):
    """(bytes, files, the newest change) of a file, or of a folder and everything in it."""
    try:
        st = os.lstat(p)
    except OSError:
        return 0, 0, 0.0
    if not os.path.isdir(p) or os.path.islink(p):
        return st.st_size, 1, st.st_mtime
    size, n, newest = 0, 0, st.st_mtime
    for root, dirs, names in os.walk(p):
        for group, is_file in ((dirs, False), (names, True)):
            for name in group:
                try:
                    s = os.lstat(os.path.join(root, name))
                except OSError:
                    continue
                newest = max(newest, s.st_mtime)
                if is_file:
                    size, n = size + s.st_size, n + 1
    return size, n, newest


def _kind(name):
    """What a name in temp/ is to this script: a folder that goes whole, the silent render, a
    folder a dead run left renamed, or None (not ours)."""
    if name in WHOLE:
        return name
    if SILENT.search(name):
        return "silent"
    if GONE.search(name):
        return "leftover"
    return None


def pieces(f, older_s=OLDER_H * 3600, now=None):
    """What may go from this film now: [{"kind", "path", "bytes", "files", "only"}] -- "only" is
    the files to remove when the folder itself stays (the thumbnail stills), else None."""
    now = time.time() if now is None else now
    temp = f.path("temp")
    try:
        names = sorted(os.listdir(temp))
    except OSError:
        return []
    out = []
    for name in names:
        p = os.path.join(temp, name)
        kind = _kind(name)
        if kind:
            size, n, newest = _tree(p)
            if now - newest >= older_s and (n or os.path.isdir(p)):
                out.append({"kind": kind, "path": p, "bytes": size, "files": n, "only": None})
        elif name in STILLS and os.path.isdir(p):
            _, _, newest = _tree(p)
            if now - newest < older_s:
                continue
            only, size = [], 0
            for root, _, files in os.walk(p):
                for x in files:
                    if x.lower().endswith(".png"):
                        q = os.path.join(root, x)
                        try:
                            size += os.lstat(q).st_size
                        except OSError:
                            continue
                        only.append(q)
            if only:
                out.append(
                    {"kind": name, "path": p, "bytes": size, "files": len(only), "only": only}
                )
    return out


def remove(piece):
    """Remove one piece; the bytes that went (0 when it could not be touched)."""
    if piece["only"] is not None:
        went = 0
        for q in piece["only"]:
            try:
                n = os.lstat(q).st_size
                os.remove(q)
                went += n
            except OSError:
                pass
        return went
    p = piece["path"]
    if os.path.isdir(p) and not os.path.islink(p):
        gone = p if GONE.search(p) else "%s.pruned-%d" % (p, os.getpid())
        try:
            if gone != p:
                os.rename(p, gone)  # one rename: a reader finds the cache or none, never half
        except OSError:
            return 0
        shutil.rmtree(gone, ignore_errors=True)
        return 0 if os.path.lexists(gone) else piece["bytes"]
    try:
        os.remove(p)
    except OSError:
        return 0
    return piece["bytes"]


def sweep(older_h=OLDER_H, only=None, plan=False, now=None):
    """Every film's pieces, removed unless `plan`. -> {"kinds": {kind: {"films", "files",
    "bytes"}}, "films": how many films had something, "skipped": {why: n}, "bytes", "left":
    bytes that could not be removed}."""
    kinds, skipped, touched, total, left = {}, {}, 0, 0, 0
    for f in films.Film.all():
        if f.legacy or (only and f.id != only):
            continue
        why = busy(f)
        if why:
            skipped[why] = skipped.get(why, 0) + 1
            continue
        got = pieces(f, older_h * 3600, now)
        if got:
            touched += 1
        for piece in got:
            k = kinds.setdefault(piece["kind"], {"films": 0, "files": 0, "bytes": 0})
            k["films"] += 1
            k["files"] += piece["files"]
            k["bytes"] += piece["bytes"]
            total += piece["bytes"]
            if not plan:
                left += piece["bytes"] - remove(piece)
    return {"kinds": kinds, "films": touched, "skipped": skipped, "bytes": total, "left": left}


def _gb(n):
    return "%.1f" % (n / 1e9)


def report(res, plan, older_h):
    lines = ["%-16s %6s %8s %8s" % ("", "films", "files", "GB")]
    for kind, k in sorted(res["kinds"].items(), key=lambda kv: -kv[1]["bytes"]):
        lines.append("%-16s %6d %8d %8s" % (kind, k["films"], k["files"], _gb(k["bytes"])))
    lines.append(
        "%s %s GB from %d film(s), untouched for %g h or more"
        % (
            "would remove" if plan else "removed",
            _gb(res["bytes"] - res["left"]),
            res["films"],
            older_h,
        )
    )
    if res["left"]:
        lines.append("could not remove %s GB (see the folders' owners)" % _gb(res["left"]))
    if res["skipped"]:
        lines.append(
            "left alone: " + ", ".join("%d %s" % (n, w) for w, n in sorted(res["skipped"].items()))
        )
    try:
        d = shutil.disk_usage(films.HOME)
        lines.append(
            "disk: %s of %s GB used, %s GB free (%d%%)"
            % (_gb(d.used), _gb(d.total), _gb(d.free), round(100 * d.used / d.total))
        )
    except OSError:
        pass
    return "\n".join(lines)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--plan", action="store_true", help="say what would go; remove nothing")
    ap.add_argument(
        "--older-than",
        type=float,
        default=OLDER_H,
        metavar="H",
        help="only pieces nothing has written to for H hours (default %g)" % OLDER_H,
    )
    ap.add_argument("--film", help="only this film's")
    ap.add_argument("--json", action="store_true", help="the result as JSON")
    a = ap.parse_args()
    if a.older_than < 0:
        ap.error("--older-than is hours, 0 or more")
    res = sweep(a.older_than, a.film, a.plan)
    print(json.dumps(res, indent=1) if a.json else report(res, a.plan, a.older_than))
