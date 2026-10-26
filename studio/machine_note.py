#!/usr/bin/env python
"""What the studio's machine says about itself, written where the site can read it.

    python studio/machine_note.py --plan      print the note; write nothing
    python studio/machine_note.py             write it (after every pass of the mirror:
                                              kitcut-backup.service, every 15 minutes)

The note: how full the data disk is, where the mirror of the studio's home stands
(backup.py: its last pass, and why it counts as behind), and the last decision of the ship that
follows GitHub (deploy/autoship.py, which also writes the note at once when it fails or holds),
and what the machine's watch says stands wrong (deploy/monitor.py: memory, swap, the disk's
health and how fast it fills, temperatures, services, OOM kills, reboots...; it writes the note at
once when that changes).
It goes into kitcut.studio_hosts, document "studio", field "machine" (store.note_machine), and
the site's watch (sketch-studio lib/studiowatch.js) emails the owner from it: a disk past 80 %,
a mirror that is behind, a ship that failed or waits for a person, each of the watch's alerts
(and "all clear" when one ends), and -- because the note carries its own time -- a machine that
stopped reporting, or a watch that did.

Why through the database and not the studio's /api/health: that page is public, and the site
must be able to read the note while the tunnel is down. Until 2026-10-12 the disk's figure was
printed by `ops.sh status` and read by nobody: it was two days from full (KI-063).

A rehearsal (STUDIO_DRILL=1, restore.py) writes nothing: it is not the studio.
"""

import os
import sys
import json
import shutil
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backup  # noqa: E402 -- the stdlib only; the studio's .env and the mirror's status
import store  # noqa: E402


def note():
    out = {
        "mirror": {k: backup.last().get(k) for k in ("at", "kind", "ok", "last_quick", "last_full")}
    }
    out["mirror"]["stale"] = backup.stale(backup.last())
    try:  # deploy/autoship.py's last decision (its file, so this stays stdlib + backup)
        with open(os.path.join(backup.HOME, "autoship.json"), encoding="utf-8") as f:
            a = json.load(f)
        out["autoship"] = {k: a.get(k) for k in ("state", "why", "at", "head", "leader")}
        out["autoship"]["paused"] = os.path.exists(os.path.join(backup.HOME, "autoship.paused"))
    except (OSError, ValueError):
        pass  # autoship not on (or not yet looked): nothing to say
    try:  # deploy/monitor.py's alerts (kitcut-monitor.service), with the time it last looked
        with open(os.path.join(backup.HOME, "monitor", "health.json"), encoding="utf-8") as f:
            out["health"] = json.load(f)
    except (OSError, ValueError):
        pass  # the watch is not installed on this machine
    try:
        d = shutil.disk_usage(backup.HOME)
        out["disk"] = {"pct": round(100 * d.used / d.total), "free_gb": round(d.free / 1e9)}
    except OSError as e:
        out["disk"] = {"error": str(e)[:200]}
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--plan", action="store_true", help="print the note; write nothing")
    a = ap.parse_args()
    n = note()
    print(json.dumps(n))
    if a.plan:
        sys.exit(0)
    if backup.setting("STUDIO_DRILL") == "1":
        sys.exit("a rehearsal (STUDIO_DRILL=1): not written")
    uri = os.environ.get("MONGODB_URI") or backup.setting("MONGODB_URI")
    if not uri:
        sys.exit("MONGODB_URI is not set (the studio's .env): not written")
    store.MongoStore(uri=uri).note_machine(n)
