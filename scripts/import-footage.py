#!/usr/bin/env python
"""Bring a recording session's raw files into a project, in the order they
were actually shot, and say which ones carry sound.

An hour of the first silent-screencast edit went here by hand, and every
minute of it is a fact this script now knows:

  Windows Game Bar writes `Videos/Recording <date> <HHMMSS>.mp4` AND a
  byte-identical copy under `Videos/Screen Recordings/` a few seconds apart.
  They are one take; the copy is dropped by hashing the first 5 MB.

  A phone is an MTP device with no drive letter. Its SCREEN recordings live
  in `Movies/` (`screen-<date>-<HHMMSS>-*.mp4`), not in `DCIM/Camera`, which
  is where the camera clips (`PXL_<date>_<HHMMSS>...mp4`) are. Listing it
  through Shell.Application sorts dates as STRINGS, so "9/9/2025" sorts above
  "8/31/2026"; this sorts by the timestamp in the filename instead.

  Three clocks: Game Bar names a capture for when it STOPPED, Android for
  when it started, and the PXL clip's creation_time is UTC. Ordering by
  filename interleaves them wrong; this converts all three to a local start
  time and orders by that, writing the reasoning into each source's `_why`.

  A Game Bar capture with no microphone has a digitally silent track: mean
  AND max at -91 dB, not room tone. Knowing that up front is what routes the
  edit to the silent-screencast pipeline without a wasted transcription.

Invoke as:  python scripts/import-footage.py --project <id> --since 2026-08-31 --dry-run
"""
import sys
import os
import re
import json
import glob
import shutil
import hashlib
import argparse
import subprocess
import datetime as dt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import
import _project  # noqa: E402

ROOT = _env.ROOT
HERE = os.path.dirname(os.path.abspath(__file__))

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def head_hash(path, n=5_000_000):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        h.update(f.read(n))
    return h.hexdigest()[:12]


def probe(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-show_entries", "format_tags=creation_time",
         "-show_entries", "stream=codec_type", "-of", "json", path],
        capture_output=True, text=True).stdout
    try:
        d = json.loads(out)
    except ValueError:
        return {"duration": 0.0, "creation_time": None, "has_audio": False}
    fm = d.get("format") or {}
    return {"duration": float(fm.get("duration") or 0.0),
            "creation_time": (fm.get("tags") or {}).get("creation_time"),
            "has_audio": any(s.get("codec_type") == "audio" for s in d.get("streams", []))}


def audio_level(path):
    """(mean_dB, max_dB) or None when there is no audio stream at all."""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-vn",
                        "-af", "volumedetect", "-f", "null", "-"],
                       capture_output=True, text=True)
    mean = max_ = None
    for ln in r.stderr.splitlines():
        m = re.search(r"mean_volume:\s*(-?[\d.]+)", ln)
        if m:
            mean = float(m.group(1))
        m = re.search(r"max_volume:\s*(-?[\d.]+)", ln)
        if m:
            max_ = float(m.group(1))
    if mean is None:
        return None
    return mean, max_


def local_tz():
    return dt.datetime.now().astimezone().tzinfo


def start_time(path, info):
    """Local start time, kind, and the reasoning -- one clock per naming scheme."""
    name = os.path.basename(path)
    m = re.match(r"Recording (\d{4})-(\d{2})-(\d{2}) (\d{2})(\d{2})(\d{2})", name)
    if m:
        stop = dt.datetime(*map(int, m.groups()), tzinfo=local_tz())
        return (stop - dt.timedelta(seconds=info["duration"]), "desktop",
                f"Game Bar names a capture for when it STOPPED ({stop:%H:%M:%S}); "
                f"start = stop - {info['duration']:.0f}s")
    m = re.match(r"screen-(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})(\d{2})", name)
    if m:
        st = dt.datetime(*map(int, m.groups()), tzinfo=local_tz())
        return st, "phone-screen", "Android screen recording: filename is the local START"
    m = re.match(r"PXL_(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})", name)
    if m:
        utc = dt.datetime(*map(int, m.groups()), tzinfo=dt.timezone.utc)
        return (utc.astimezone(local_tz()), "phone-camera",
                f"PXL filename is UTC ({utc:%H:%M:%S}Z); converted to local")
    ct = info.get("creation_time")
    if ct:
        try:
            utc = dt.datetime.fromisoformat(ct.replace("Z", "+00:00"))
            return utc.astimezone(local_tz()), "other", "container creation_time (UTC)"
        except ValueError:
            pass
    mt = dt.datetime.fromtimestamp(os.path.getmtime(path), tz=local_tz())
    return mt, "other", "file mtime (no timestamp in the name or container)"


def windows_captures(videos_dir, since):
    """Game Bar captures, with the Screen Recordings copies dropped."""
    files = sorted(glob.glob(os.path.join(videos_dir, "Recording *.mp4")))
    copies = sorted(glob.glob(os.path.join(videos_dir, "Screen Recordings", "*.mp4")))
    keep, dropped = [], []
    seen = {}
    for p in files + copies:
        if since and dt.datetime.fromtimestamp(os.path.getmtime(p)).date() < since:
            continue
        h = head_hash(p)
        if h in seen:
            dropped.append((p, seen[h]))
            continue
        seen[h] = p
        keep.append(p)
    return keep, dropped


PS_LIST = r'''
$shell = New-Object -ComObject Shell.Application
$dev = $shell.NameSpace(17).Items() | Where-Object { $_.Name -eq '%(phone)s' }
if (-not $dev) { exit 2 }
$int = ($dev.GetFolder.Items() | Where-Object { $_.IsFolder } | Select-Object -First 1).GetFolder
function Walk($f, $sub) {
  $node = $f
  foreach ($s in $sub) { $it = $node.Items() | Where-Object { $_.Name -eq $s }; if (-not $it) { return }; $node = $it.GetFolder }
  $node.Items() | Where-Object { -not $_.IsFolder -and $_.Name -match '\.(mp4|mov)$' } | ForEach-Object { "{0}|{1}" -f ($sub -join '/'), $_.Name }
}
Walk $int @('Movies')
Walk $int @('DCIM','Camera')
'''

PS_COPY = r'''
$shell = New-Object -ComObject Shell.Application
$dev = $shell.NameSpace(17).Items() | Where-Object { $_.Name -eq '%(phone)s' }
$int = ($dev.GetFolder.Items() | Where-Object { $_.IsFolder } | Select-Object -First 1).GetFolder
$node = $int
foreach ($s in '%(sub)s'.Split('/')) { $node = ($node.Items() | Where-Object { $_.Name -eq $s }).GetFolder }
$item = $node.Items() | Where-Object { $_.Name -eq '%(name)s' }
$shell.NameSpace('%(dest)s').CopyHere($item, 16)
$p = Join-Path '%(dest)s' '%(name)s'
$prev = -1
for ($i = 0; $i -lt 900; $i++) {
  Start-Sleep -Seconds 2
  if (Test-Path $p) { $s = (Get-Item $p).Length; if ($s -eq $prev -and $s -gt 0) { break }; $prev = $s }
}
"copied $prev"
'''


def phone_files(phone, since):
    """[(subfolder, name)] on the phone that belong to the session."""
    if os.name != "nt":
        return []
    r = subprocess.run(["powershell", "-NoProfile", "-Command", PS_LIST % {"phone": phone}],
                       capture_output=True, text=True)
    if r.returncode == 2:
        print(f"  phone '{phone}' not connected; skipping")
        return []
    out = []
    for ln in r.stdout.splitlines():
        if "|" not in ln:
            continue
        sub, name = ln.strip().split("|", 1)
        m = re.search(r"(\d{4})(\d{2})(\d{2})", name)
        if since and m and dt.date(*map(int, m.groups())) < since:
            continue
        if not m and since:
            continue
        out.append((sub, name))
    return out


def phone_copy(phone, sub, name, dest):
    r = subprocess.run(["powershell", "-NoProfile", "-Command",
                        PS_COPY % {"phone": phone, "sub": sub, "name": name,
                                   "dest": dest.replace("/", "\\")}],
                       capture_output=True, text=True)
    return r.stdout.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--videos-dir", default=os.path.join(os.path.expanduser("~"), "Videos"))
    ap.add_argument("--phone", default="Pixel 9 Pro XL",
                    help="MTP device name as it appears under This PC; '' to skip")
    ap.add_argument("--since", help="only files from this date on (YYYY-MM-DD); default today")
    ap.add_argument("--move", action="store_true",
                    help="move the desktop captures instead of copying them")
    ap.add_argument("--dry-run", action="store_true",
                    help="list, order and audio-check; copy nothing, write nothing")
    args = ap.parse_args()

    since = dt.date.fromisoformat(args.since) if args.since else dt.date.today()
    pdir = os.path.join(_project.projects_dir(), args.project)
    sdir = os.path.join(pdir, "sources")

    keep, dropped = windows_captures(args.videos_dir, since)
    for p, orig in dropped:
        print(f"  duplicate dropped: {os.path.basename(p)} == {os.path.basename(orig)}")
    phone = phone_files(args.phone, since) if args.phone else []
    print(f"{args.project}: {len(keep)} desktop capture(s), {len(phone)} phone file(s) "
          f"since {since}")

    if not args.dry_run:
        if not os.path.exists(os.path.join(pdir, "project.json")):
            subprocess.run([sys.executable, os.path.join(HERE, "project-scan.py"),
                            "--init", args.project], cwd=ROOT, check=True)
        os.makedirs(sdir, exist_ok=True)

    entries = []
    for p in keep:
        m = re.match(r"Recording \d{4}-\d{2}-\d{2} (\d{6})", os.path.basename(p))
        newname = f"desktop-{m.group(1)}.mp4" if m else os.path.basename(p)
        dest = os.path.join(sdir, newname)
        if not args.dry_run and not os.path.exists(dest):
            (shutil.move if args.move else shutil.copy2)(p, dest)
        entries.append(dest if not args.dry_run else p)
    for sub, name in phone:
        dest = os.path.join(sdir, name)
        if not args.dry_run and not os.path.exists(dest):
            print(f"  copying {sub}/{name} from the phone ...")
            print("   ", phone_copy(args.phone, sub, name, sdir))
        entries.append(dest if not args.dry_run else f"phone:{sub}/{name}")

    rows = []
    for p in entries:
        if p.startswith("phone:"):
            rows.append({"path": p, "start": None, "kind": "phone", "why": "not copied (dry run)",
                         "dur": 0.0, "audio": "?"})
            continue
        info = probe(p)
        st, kind, why = start_time(p, info)
        lvl = audio_level(p) if info["has_audio"] else None
        if lvl is None:
            audio = "no audio stream"
        elif lvl[1] <= -90:
            audio = f"digital silence ({lvl[0]:.0f} dB)"
        elif lvl[0] < -50:
            audio = f"ambient only ({lvl[0]:.0f} dB mean)"
        else:
            audio = f"speech-level ({lvl[0]:.0f} dB mean)"
        rows.append({"path": p, "start": st, "kind": kind, "why": why,
                     "dur": info["duration"], "audio": audio})
    rows.sort(key=lambda r: (r["start"] is None, r["start"] or dt.datetime.max.replace(
        tzinfo=local_tz())))

    print(f"\n  {'#':>2} {'start':<8} {'len':>7} {'kind':<13} {'audio':<26} file")
    for i, r in enumerate(rows, 1):
        st = r["start"].strftime("%H:%M:%S") if r["start"] else "?"
        print(f"  {i:>2} {st:<8} {r['dur'] / 60:>4.0f}:{r['dur'] % 60:04.1f} {r['kind']:<13} "
              f"{r['audio']:<26} {os.path.basename(r['path'])}")
    silent = sum(1 for r in rows if r["audio"].startswith("digital") or r["audio"].startswith("no audio"))
    print(f"\n  {silent}/{len(rows)} carry no usable sound -> "
          f"{'silent-screencast pipeline (screencast-pipeline.py)' if silent >= len(rows) / 2 else 'a spoken cut may be possible'}")

    if args.dry_run:
        return

    mpath = os.path.join(pdir, "screen.json")
    man = json.load(open(mpath, encoding="utf-8")) if os.path.exists(mpath) else {
        "_comment": "silent screen recordings cut into one film by screencast-pipeline.py",
        "id": args.project,
        "output": _project.norm(os.path.join(pdir, "outputs", args.project + ".mp4")),
        "benign_text": [],
        "cut": {"canvas": [1920, 1080], "fps": 30, "blur_mode": "blur",
                "backdrop": "blur", "speed_badge": True, "cq": 21},
        "sources": [],
    }
    have = {s["path"] for s in man["sources"]}
    for r in rows:
        rel = _project.norm(r["path"])
        if rel in have:
            continue
        man["sources"].append({
            "_why": f"{r['start']:%H:%M:%S} local -- {r['why']}; audio: {r['audio']}",
            "path": rel, "blur": []})
    with open(mpath, "w", encoding="utf-8") as f:
        json.dump(man, f, ensure_ascii=False, indent=2)
    _project.record(args.project, "import-footage",
                    note=f"{len(rows)} source(s) imported and ordered by capture start; "
                         f"{silent} silent; {len(dropped)} duplicate(s) dropped")
    print(f"\n  wrote {len(man['sources'])} source(s) into {_project.norm(mpath)}")


if __name__ == "__main__":
    main()
