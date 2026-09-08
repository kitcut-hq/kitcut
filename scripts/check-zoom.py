#!/usr/bin/env python
"""Self-test the Zoom import and caption emphasis.

Two things here are only reachable through something slow, which is exactly
why they get written wrong:

  The Zoom folder rules are reachable by importing a real recording, and the
  expensive failure is the SILENT one -- an unconverted folder whose
  `video*.mp4.tmp` probes clean as a short valid mp4, so a 30-minute meeting
  imports as a 551 KB stub and nobody notices until the cut is short.

  An emphasis phrase that matches nothing must fail rather than do nothing,
  and every occurrence must be marked rather than the first -- the same rule
  apply_corrections() carries, for the same reason.

Costs nothing, needs no GPU and no files. Run it after changing zoom-import.py
or the emphasis half of build-captions-ass.py.

    python scripts/check-zoom.py

Invoke as:  python scripts/check-zoom.py
"""

import sys
import os
import json
import tempfile
import datetime as dt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import
from importlib import import_module  # noqa: E402

_zoom = import_module("zoom-import")
_ass = import_module("build-captions-ass")

fails = []


def check(name, got, want):
    if got == want:
        print("  OK   %s" % name)
    else:
        print("  FAIL %s\n       got  %r\n       want %r" % (name, got, want))
        fails.append(name)


def truthy(name, got):
    check(name, bool(got), True)


def write(dirpath, name, text):
    p = os.path.join(dirpath, name)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)
    return p


print("== a Zoom folder is read from recording.conf, not from a glob ==")
with tempfile.TemporaryDirectory() as td:
    done = os.path.join(td, "2026-09-08 10.26.31 Standup")
    os.makedirs(done)
    write(
        done,
        "recording.conf",
        json.dumps(
            {
                "items": [
                    {"audio": "audio1.m4a", "prefix": "", "process": 100, "video": "video1.mp4"}
                ],
                "magic_number": "1",
            }
        ),
    )
    items, magic, complete, why = _zoom.read_conf(done)
    check("a converted recording is complete", complete, True)
    check("its video is named by the conf", items[0]["video"], "video1.mp4")

    # The expensive case: Zoom stopped halfway. The .tmp files it leaves behind
    # are valid short mp4s, so nothing downstream can tell this from a real
    # take -- the refusal has to happen here.
    part = os.path.join(td, "2022-06-08 11.02.39 Demo")
    os.makedirs(part)
    write(
        part,
        "recording.conf",
        json.dumps(
            {"items": [{"audio": "", "prefix": "", "process": 0, "video": ""}], "magic_number": "2"}
        ),
    )
    write(part, "double_click_to_convert_01.zoom", "x")
    write(part, "video2.mp4.tmp", "x")
    items, magic, complete, why = _zoom.read_conf(part)
    check("an unconverted recording is refused", complete, False)
    truthy("the refusal names the percentage", "process=0" in why)
    truthy("the refusal names the stub file", "double_click_to_convert_01.zoom" in why)

    scan = _zoom.scan_meeting(part, levels=False)
    check("scan_meeting refuses it too, rather than taking the .tmp", scan["ok"], False)

    # A folder Zoom half-wrote can also claim 100% while naming a file that is
    # gone. Importing "nothing" as a part is worse than refusing.
    gone = os.path.join(td, "2026-09-08 12.00.00 Missing")
    os.makedirs(gone)
    write(
        gone,
        "recording.conf",
        json.dumps(
            {
                "items": [{"audio": "", "prefix": "", "process": 100, "video": "video9.mp4"}],
                "magic_number": "9",
            }
        ),
    )
    check(
        "a conf naming a missing file is refused",
        _zoom.scan_meeting(gone, levels=False)["ok"],
        False,
    )

print("")
print("== parts are ordered by the folder NAME, never by creation_time ==")
# Measured on this machine: a take whose folder says 10:26:31 local carries a
# creation_time ten minutes later, because that stamp is when Zoom finished
# CONVERTING. Ordering by it orders parts by how fast each one encoded.
check(
    "the folder name parses to a local capture start",
    _zoom.folder_start("/x/2026-09-08 10.26.31 Team Standup")[0],
    dt.datetime(2026, 9, 8, 10, 26, 31),
)
check(
    "the topic survives the parse",
    _zoom.folder_start("/x/2026-09-08 10.26.31 Weekly sync")[1],
    "Weekly sync",
)
check(
    "a folder that is not a Zoom recording parses to nothing",
    _zoom.folder_start("/x/Some Other Folder")[0],
    None,
)
names = ["/x/2026-09-08 10.38.54 B", "/x/2026-09-08 10.26.31 A"]
check(
    "sorting by parsed start puts part 1 first",
    [os.path.basename(p)[-1] for p in sorted(names, key=lambda p: _zoom.folder_start(p)[0])],
    ["A", "B"],
)
check(
    "part naming is 1-based and only splits when there IS more than one",
    (_zoom.part_name("vid", 0, 1), _zoom.part_name("vid", 1, 2)),
    ("vid.mp4", "vid-part2.mp4"),
)

print("")
print("== emphasis marks every occurrence, and never fails silently ==")
cfg = json.load(
    open(os.path.join(_env.ROOT, "config", "presets", "instafill-uk.json"), encoding="utf-8")
)
truthy("the Ukrainian preset declares an emphasis colour", "emphasis" in cfg["states"])
check(
    "emphasis is NOT the spotlight colour -- one signal cannot mean two things",
    cfg["states"]["emphasis"]["colour"] == cfg["states"]["active"]["colour"],
    False,
)

words = _ass.sanitize(
    [
        {"text": "batch", "start": 0.0, "end": 0.4},
        {"text": "filling", "start": 0.4, "end": 0.9},
        {"text": "and", "start": 0.9, "end": 1.1},
        {"text": "batch", "start": 1.1, "end": 1.5},
        {"text": "filling", "start": 1.5, "end": 2.0},
    ],
    cfg,
)
hits, missed = _ass.mark_emphasis(words, ["batch filling"])
check("both occurrences are found, not just the first", hits, 2)
check(
    "every word the phrase covers is marked",
    [bool(w.get("emph")) for w in words],
    [True, True, False, True, True],
)
check("a phrase that matched is not reported missing", missed, [])

hits, missed = _ass.mark_emphasis(words, ["nothing like this"])
check("a phrase that matches nothing is REPORTED, not ignored", missed, ["nothing like this"])
# Matching folds punctuation and case, so a phrase survives a re-transcription
# that re-punctuates or re-capitalises the line it lives in.
w2 = _ass.sanitize(
    [{"text": "Batch,", "start": 0.0, "end": 0.4}, {"text": "Filling.", "start": 0.4, "end": 0.9}],
    cfg,
)
hits, missed = _ass.mark_emphasis(w2, ["batch filling"])
check("matching ignores case and punctuation", (hits, missed), (1, []))

print("")
if fails:
    print("%d FAILED: %s" % (len(fails), ", ".join(fails)))
    sys.exit(1)
print("all zoom checks passed")
