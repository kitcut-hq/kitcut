#!/usr/bin/env python
"""Bring one or more Zoom local recordings into a project, in the order they
were actually recorded, and say what each one really contains.

A Zoom "recording" is a FOLDER, not a file, and four things about it cost real
time to learn. All four are checked here so no caller has to know them:

  `recording.conf` is the authority, not the glob. It is JSON:
  {"items":[{"video":..., "audio":..., "prefix":..., "process":100}], ...}.
  `process` is a PERCENTAGE. Anything below 100 means Zoom has not finished
  converting the take: the folder then holds `double_click_to_convert_NN.zoom`
  plus `video*.mp4.tmp`, and the .tmp probes clean as a valid short mp4. On
  this machine one such folder holds a 181 MB .zoom next to a 551 KB video
  stub of a 30-minute meeting. Importing it would silently take the stub, so
  an unconverted folder is REFUSED with the reason.

  The sidecar `audio<magic>.m4a` is the same mix as the mp4's own audio track,
  not a separate channel. Measured: decoded to 16 kHz mono, the first 60 s of
  both files have identical MD5s. So it is never muxed in -- adding it as a
  second track doubles the voice. It is a fallback for a damaged mp4 and a
  cheap input for transcription, and that is all.

  `creation_time` on the mp4 is when Zoom FINISHED CONVERTING, not when the
  recording started. Measured here: a take whose folder is stamped 10:26:31
  local (= 17:26:31Z) carries creation_time 17:36:00Z, ten minutes later, and
  the gap is the conversion. The folder NAME -- "YYYY-MM-DD HH.MM.SS <topic>",
  in LOCAL time -- is the only honest capture start, so parts are ordered by
  that. Ordering by creation_time orders by how fast each part encoded.

  Separate audio per participant, when it was enabled, is the one genuinely
  distinct audio Zoom writes: `Audio Record/`. Screen share recorded apart
  from the speaker is `as<magic>.mp4`. Both are reported; neither is guessed at.

Two or more `--meeting` folders are the normal case for a talk recorded in
parts: Zoom starts a new folder every time the host stops and restarts, and
the parts are one film. They are imported as ordered `parts` so the cutter can
lay them end to end.

  --list   what would be imported, with durations and levels; copies nothing

Invoke as:  python scripts/zoom-import.py --project <id> --meeting "<dir>" --list
"""

import sys
import os
import re
import json
import glob
import shutil
import argparse
import subprocess
import datetime as dt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import
import _project  # noqa: E402

# "YYYY-MM-DD HH.MM.SS <topic>" -- Zoom's folder name, in LOCAL time.
FOLDER_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2}) (\d{2})\.(\d{2})\.(\d{2})\s*(.*)$")

# A silent Windows capture sits at -91 dB mean AND max; real room tone does not.
SILENT_DB = -80.0


def zoom_dir(explicit=None):
    """Where Zoom keeps local recordings. ~/Documents/Zoom is its default."""
    if explicit:
        return os.path.abspath(os.path.expanduser(explicit))
    return os.path.join(os.path.expanduser("~"), "Documents", "Zoom")


def folder_start(path):
    """Capture start from the folder NAME (local time), and the topic.

    Returns (datetime|None, topic). See the module docstring for why the mp4's
    creation_time is not used for this.
    """
    m = FOLDER_RE.match(os.path.basename(path.rstrip("\\/")))
    if not m:
        return None, ""
    y, mo, d, h, mi, s, topic = m.groups()
    try:
        return dt.datetime(*(int(x) for x in (y, mo, d, h, mi, s))), topic.strip()
    except ValueError:
        return None, topic.strip()


def probe(path):
    """Duration, frame size/rate and stream presence for one file."""
    out = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-show_entries",
            "format_tags=creation_time",
            "-show_entries",
            "stream=codec_type,codec_name,width,height,r_frame_rate,channels,sample_rate",
            "-of",
            "json",
            path,
        ],
        capture_output=True,
        text=True,
        env=_env.ENV,
    ).stdout
    try:
        d = json.loads(out)
    except ValueError:
        return {"duration": 0.0, "video": None, "audio": None, "creation_time": None}
    fm = d.get("format") or {}
    info = {
        "duration": float(fm.get("duration") or 0.0),
        "creation_time": (fm.get("tags") or {}).get("creation_time"),
        "video": None,
        "audio": None,
    }
    for s in d.get("streams", []):
        if s.get("codec_type") == "video" and info["video"] is None:
            num, _, den = (s.get("r_frame_rate") or "0/1").partition("/")
            fps = float(num) / float(den or 1) if float(den or 1) else 0.0
            info["video"] = {
                "codec": s.get("codec_name"),
                "w": s.get("width"),
                "h": s.get("height"),
                "fps": round(fps, 4),
            }
        elif s.get("codec_type") == "audio" and info["audio"] is None:
            info["audio"] = {
                "codec": s.get("codec_name"),
                "channels": s.get("channels"),
                "sample_rate": s.get("sample_rate"),
            }
    return info


def audio_level(path):
    """(mean_db, max_db) over the whole track, or (None, None)."""
    r = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "info",
            "-i",
            path,
            "-map",
            "0:a:0",
            "-af",
            "volumedetect",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        env=_env.ENV,
    )
    txt = (r.stderr or "") + (r.stdout or "")
    got = {}
    for key in ("mean_volume", "max_volume"):
        m = re.search(key + r":\s*(-?[\d.]+)", txt)
        if m:
            got[key] = float(m.group(1))
    return got.get("mean_volume"), got.get("max_volume")


def read_conf(meeting):
    """Parse recording.conf. Returns (items, magic, complete, why).

    `complete` is False when Zoom has not finished converting -- see the
    module docstring; that is the case this function exists to catch.
    """
    p = os.path.join(meeting, "recording.conf")
    if not os.path.exists(p):
        return [], None, None, "no recording.conf"
    try:
        with open(p, encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, ValueError) as e:
        return [], None, None, "unreadable recording.conf (%s)" % e
    items = doc.get("items") or []
    magic = doc.get("magic_number")
    named = [it for it in items if (it.get("video") or it.get("audio"))]
    pending = [it for it in items if int(it.get("process") or 0) < 100]
    if not named or pending:
        stubs = sorted(os.path.basename(x) for x in glob.glob(os.path.join(meeting, "*.zoom")))
        why = "Zoom has not finished converting this recording (process=%s)" % ", ".join(
            str(it.get("process")) for it in items
        )
        if stubs:
            why += "; %d unconverted file(s) still present: %s" % (len(stubs), ", ".join(stubs[:3]))
        why += ". Open it in Zoom and let it convert, then re-run."
        return named, magic, False, why
    return named, magic, True, ""


def scan_meeting(meeting, levels=True):
    """Everything worth knowing about one Zoom recording folder."""
    meeting = os.path.abspath(os.path.expanduser(meeting))
    started, topic = folder_start(meeting)
    rec = {
        "dir": meeting,
        "name": os.path.basename(meeting),
        "topic": topic,
        "started": started.isoformat(sep=" ") if started else None,
        "_sort": started or dt.datetime.min,
        "ok": True,
        "why": "",
        "video": None,
        "audio_sidecar": None,
        "screen_share": None,
        "per_participant": [],
        "duration": 0.0,
    }
    if not os.path.isdir(meeting):
        rec.update(ok=False, why="no such folder")
        return rec

    items, magic, complete, why = read_conf(meeting)
    rec["magic"] = magic
    if complete is False:
        rec.update(ok=False, why=why)
        return rec

    vids, auds = [], []
    for it in items:
        if it.get("video"):
            vids.append(os.path.join(meeting, it["video"]))
        if it.get("audio"):
            auds.append(os.path.join(meeting, it["audio"]))
    if not vids:  # no conf, or an already-converted export
        vids = sorted(
            glob.glob(os.path.join(meeting, "video*.mp4"))
            + glob.glob(os.path.join(meeting, "zoom_*.mp4"))
        )
        auds = sorted(glob.glob(os.path.join(meeting, "audio*.m4a")))
        if not vids:
            rec.update(ok=False, why="no video file in the folder")
            return rec

    main = vids[0]
    if not os.path.exists(main):
        rec.update(
            ok=False, why="recording.conf names %s, which is missing" % os.path.basename(main)
        )
        return rec
    info = probe(main)
    rec["video"] = {"path": main, **info}
    rec["duration"] = info["duration"]
    if info["audio"] is None:
        rec["why"] = "the mp4 has no audio track"
    elif levels:
        mean, peak = audio_level(main)
        rec["video"]["mean_db"], rec["video"]["max_db"] = mean, peak
        if mean is not None and peak is not None and max(mean, peak) <= SILENT_DB:
            rec["why"] = (
                "the audio track is digitally silent (%.0f dB mean, "
                "%.0f dB peak) -- nobody's mic was recorded" % (mean, peak)
            )

    for a in auds:
        if os.path.exists(a):
            rec["audio_sidecar"] = {"path": a, **probe(a)}
            break
    # Screen share recorded separately from the speaker view.
    for s in sorted(glob.glob(os.path.join(meeting, "as*.mp4"))):
        rec["screen_share"] = {"path": s, **probe(s)}
        break
    # The one genuinely separate audio Zoom writes.
    pp = os.path.join(meeting, "Audio Record")
    if os.path.isdir(pp):
        rec["per_participant"] = sorted(
            glob.glob(os.path.join(pp, "*.m4a")) + glob.glob(os.path.join(pp, "*.mp4"))
        )
    return rec


def find_meetings(root, since=None):
    """Every Zoom recording folder under `root`, newest first."""
    out = []
    if not os.path.isdir(root):
        return out
    for name in os.listdir(root):
        p = os.path.join(root, name)
        if not os.path.isdir(p):
            continue
        started, _ = folder_start(p)
        if started is None:
            continue
        if since and started.date() < since:
            continue
        out.append(p)
    return sorted(out, key=lambda p: folder_start(p)[0], reverse=True)


def hhmmss(sec):
    sec = int(round(sec or 0))
    return "%d:%02d:%02d" % (sec // 3600, sec % 3600 // 60, sec % 60)


def part_name(pid, idx, total):
    return "%s-part%d.mp4" % (pid, idx + 1) if total > 1 else "%s.mp4" % pid


def join_parts(paths, out, fps):
    """Concatenate parts into one film source, stream-copied.

    Zoom writes every part with identical encoder settings, so the concat
    demuxer joins them without re-encoding -- no generation loss, seconds
    instead of minutes. What it CAN do is silently produce a file whose
    duration is not the sum, when a part carries a timestamp discontinuity, so
    the result is probed and the total asserted to within one frame. A film
    that is short by half a part is otherwise only discovered at the render.

    Joining is what gives the whole downstream one clock: the cut, the word
    transcript, the caption times and the Resolve timeline all address the same
    file, and no stage has to carry a per-part offset.
    """
    listing = out + ".concat.txt"
    with open(listing, "w", encoding="utf-8") as f:
        for p in paths:
            f.write("file '%s'\n" % os.path.abspath(p).replace("\\", "/").replace("'", r"'\''"))
    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-v",
        "error",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        listing,
        "-c",
        "copy",
        "-movflags",
        "+faststart",
        out,
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, env=_env.ENV)
    if r.returncode != 0:
        os.path.exists(listing) and os.remove(listing)
        raise RuntimeError("concat failed: %s" % (r.stderr or "").strip()[:400])
    os.remove(listing)
    want = sum(probe(p)["duration"] for p in paths)
    got = probe(out)["duration"]
    if abs(got - want) > (2.0 / max(fps, 1)):
        raise RuntimeError(
            "joined film is %.2fs but the parts sum to %.2fs -- a part carries a "
            "timestamp discontinuity the concat demuxer could not carry across. "
            "Re-encode the parts to a common timebase before joining." % (got, want)
        )
    return got


def main():
    ap = argparse.ArgumentParser(
        description="Import Zoom local recordings into projects/<id>/sources/."
    )
    ap.add_argument("--project", help="project id to import into")
    ap.add_argument(
        "--meeting",
        action="append",
        default=[],
        metavar="DIR",
        help="a Zoom recording FOLDER; repeat for a talk in parts",
    )
    ap.add_argument(
        "--latest",
        type=int,
        metavar="N",
        help="instead of --meeting, take the N most recent recordings",
    )
    ap.add_argument(
        "--since", metavar="YYYY-MM-DD", help="with --list or --latest, ignore anything older"
    )
    ap.add_argument(
        "--zoom-dir", default=None, help="where Zoom keeps recordings (default ~/Documents/Zoom)"
    )
    ap.add_argument(
        "--list", action="store_true", help="print what would be imported and copy nothing"
    )
    ap.add_argument(
        "--join",
        action="store_true",
        help="also concatenate the parts into one film source, so "
        "the cut, the transcript and the timeline share a clock",
    )
    ap.add_argument("--move", action="store_true", help="move the files instead of copying them")
    ap.add_argument("--force", action="store_true", help="overwrite sources already in the project")
    ap.add_argument(
        "--no-levels",
        action="store_true",
        help="skip the loudness probe (faster, no silence check)",
    )
    _env.add_workspace_arg(ap)
    a = ap.parse_args()
    _env.set_workspace(a.workspace)

    since = None
    if a.since:
        since = dt.datetime.strptime(a.since, "%Y-%m-%d").date()

    root = zoom_dir(a.zoom_dir)
    meetings = list(a.meeting)
    if a.latest:
        meetings = find_meetings(root, since)[: a.latest][::-1]
    if not meetings:
        # Bare survey: no project needed.
        found = find_meetings(root, since)
        print("Zoom recordings under %s" % root)
        for p in found[:40]:
            rec = scan_meeting(p, levels=False)
            flag = "  " if rec["ok"] else "!!"
            print(
                "%s %-20s %8s  %s"
                % (flag, rec["started"] or "?", hhmmss(rec["duration"]), rec["name"])
            )
            if not rec["ok"]:
                print("     %s" % rec["why"])
        if not found:
            print("  (none)")
        print('\nImport with: --project <id> --meeting "<folder>"')
        return 0

    parts = [scan_meeting(m, levels=not a.no_levels) for m in meetings]
    parts.sort(key=lambda r: r["_sort"])  # capture start, from the NAME
    bad = [p for p in parts if not p["ok"]]

    total = sum(p["duration"] for p in parts)
    print("== %d part(s), %s total" % (len(parts), hhmmss(total)))
    for i, p in enumerate(parts):
        v = p["video"] or {}
        vi = v.get("video") or {}
        print("%d. %s  %s  %s" % (i + 1, p["started"] or "?", hhmmss(p["duration"]), p["name"]))
        if p["ok"]:
            print(
                "     %s  %sx%s @ %g fps  audio %s"
                % (
                    os.path.basename(v.get("path", "?")),
                    vi.get("w"),
                    vi.get("h"),
                    vi.get("fps", 0),
                    (v.get("audio") or {}).get("codec") or "NONE",
                )
            )
            if v.get("mean_db") is not None:
                print(
                    "     level: %.1f dB mean, %.1f dB peak"
                    % (v["mean_db"], v.get("max_db") or 0.0)
                )
            if p.get("audio_sidecar"):
                print(
                    "     sidecar %s -- same mix as the mp4's own track, not muxed"
                    % os.path.basename(p["audio_sidecar"]["path"])
                )
            if p.get("screen_share"):
                print("     screen share: %s" % os.path.basename(p["screen_share"]["path"]))
            if p.get("per_participant"):
                print("     per-participant audio: %d file(s)" % len(p["per_participant"]))
        if p["why"]:
            print("     !! %s" % p["why"])

    if bad:
        print("\n%d recording(s) cannot be imported; nothing was copied." % len(bad))
        return 2
    if not a.project:
        print("\nPass --project <id> to import these.")
        return 0

    pid = a.project
    pdir = os.path.join(_project.projects_dir(), pid)
    sdir = os.path.join(pdir, "sources")
    plan = []
    for i, p in enumerate(parts):
        dest = os.path.join(sdir, part_name(pid, i, len(parts)))
        plan.append((p, dest))

    joined = os.path.join(sdir, "%s.mp4" % pid) if (a.join and len(plan) > 1) else None
    print("\n-> projects/%s/sources/" % pid)
    for p, dest in plan:
        print("   %s  <- %s" % (os.path.basename(dest), os.path.basename(p["video"]["path"])))
    if joined:
        print(
            "   %s  <- the %d parts, stream-copied end to end"
            % (os.path.basename(joined), len(plan))
        )
    if a.list:
        print("\n--list: nothing copied. Re-run without --list to import.")
        return 0

    os.makedirs(sdir, exist_ok=True)
    fps = {(p["video"].get("video") or {}).get("fps") for p, _ in plan}
    size = {
        ((p["video"].get("video") or {}).get("w"), (p["video"].get("video") or {}).get("h"))
        for p, _ in plan
    }
    if len(fps) > 1 or len(size) > 1:
        print(
            "!! parts differ in rate/size (%s / %s) -- conform before a "
            "frame-addressed cut (scripts/conform-tapes.py)" % (sorted(fps), sorted(size))
        )

    copied = []
    for p, dest in plan:
        src = p["video"]["path"]
        if os.path.exists(dest) and not a.force:
            print("   exists, kept: %s" % os.path.basename(dest))
        else:
            (shutil.move if a.move else shutil.copy2)(src, dest)
            print("   %s %s" % ("moved" if a.move else "copied", os.path.basename(dest)))
        copied.append((p, dest))

    film = None
    if joined:
        if os.path.exists(joined) and not a.force:
            print("   exists, kept: %s" % os.path.basename(joined))
        else:
            secs = join_parts(
                [d for _, d in copied],
                joined,
                (parts[0]["video"].get("video") or {}).get("fps") or 25,
            )
            print(
                "   joined %s (%s, sum of parts confirmed)"
                % (os.path.basename(joined), hhmmss(secs))
            )
        film = joined
    elif len(copied) == 1:
        film = copied[0][1]

    doc = _project.load(pid) or {}
    inputs = dict(doc.get("inputs") or {})
    inputs.update(
        {
            "source_kind": "zoom",
            "zoom_dir": root,
            "recorded": parts[0]["started"],
            "topic": parts[0]["topic"],
            "duration_s": round(total, 2),
            "video": "%sx%s @ %g fps"
            % (
                (parts[0]["video"].get("video") or {}).get("w"),
                (parts[0]["video"].get("video") or {}).get("h"),
                (parts[0]["video"].get("video") or {}).get("fps", 0),
            ),
            "parts": [
                {
                    "n": i + 1,
                    "src": _project.norm(dest),
                    "zoom_folder": p["dir"],
                    "started": p["started"],
                    "duration_s": round(p["duration"], 2),
                }
                for i, (p, dest) in enumerate(copied)
            ],
        }
    )
    if film:
        inputs["source"] = _project.norm(film)
    _project.record(
        pid,
        "zoom-import",
        script="scripts/zoom-import.py",
        argv=sys.argv[1:],
        note="%d Zoom part(s), %s total, ordered by folder-name "
        "capture time" % (len(copied), hhmmss(total)),
    )
    d = _project.load(pid) or {}
    d.setdefault("inputs", {}).update(inputs)
    pl = d.setdefault("pipelines", [])
    if "zoom" not in pl:
        pl.append("zoom")
    with open(_project.path_for(pid), "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print("\nrecorded in projects/%s/project.json" % pid)
    return 0


if __name__ == "__main__":
    sys.exit(main())
