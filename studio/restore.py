#!/usr/bin/env python
"""The studio's home brought back from its mirror (the R2 bucket kitcut-backup, backup.py).

    python studio/restore.py --plan                 what the mirror holds, folder by folder, and
                                                    when it was last written; changes nothing
    python studio/restore.py --all [--drill]        everything the mirror has that is missing
                                                    here, or newer there; and models/
    python studio/restore.py --film <id>            one film's folder and its Claude sessions
    python studio/restore.py --film <id> --from-history <day>
                                                    what a pass replaced or removed of it that
                                                    day, into a folder beside the home to look at
    python studio/restore.py --check-drill          exit 1 unless this machine is a rehearsal
    python studio/restore.py --settle               a rehearsal's copy only: films that were being
                                                    made when it was mirrored are put down here
    (on the VM: ops.sh restore ...; the whole procedure: studio/deploy/README.md)

It only adds: a file that is here and newer than the mirror's stays, nothing here is removed. So
it is the same command onto an empty disk (the whole home, about 140 GB) and onto a disk restored
from last night's Azure Backup (what was made since: minutes).

A rehearsal is a second machine built from the mirror to prove the mirror works. It must not act
as the studio: a server started on a restored home adopts every film that was being made when
the home was mirrored (server.adopt) -- starts the queued ones, marks the rest interrupted -- and
writes that into the live database, where the site refunds and emails their makers. So a
rehearsal's .env says STUDIO_DRILL=1 and has no MONGODB_URI, no STUDIO_ANNOUNCE, no tunnel and no
key to the films' bucket (deploy/provision.sh --drill writes it that way); --check-drill says
which of those is not so; --settle puts those films down in the copy alone and takes away the
marks of rounds and unbrandings under way; and backup.py refuses to write the mirror from it.
"""

import os
import sys
import json
import time
import shutil
import argparse
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backup  # noqa: E402 -- the stdlib only; the bucket's key and the studio's .env

# in a rehearsal these are not copied: each is "someone asked, and it is not over" (rounds.MARKS,
# unbrand.MARKS), which a server takes as work to pick up
DRILL_SKIP = ("/rounds/_asked/**", "/unbrand/**")
ACTIVE = ("queued", "claude", "finishing")  # film.ACTIVE (test_restore.py holds it to that)
PUT_DOWN = "interrupted"


def not_a_drill():
    """Why this machine may not be treated as a rehearsal: [] when it is one."""
    out = []
    if backup.setting("STUDIO_DRILL") != "1":
        out.append("STUDIO_DRILL=1 is not in %s" % backup.ENV_FILE)
    if backup.setting("MONGODB_URI") or os.environ.get("MONGODB_URI"):
        out.append("MONGODB_URI is set: this machine writes the live database")
    if backup.setting("STUDIO_ANNOUNCE") == "1":
        out.append("STUDIO_ANNOUNCE=1: this machine tells kitcut.ai it is the studio")
    if backup.setting("STUDIO_TUNNEL"):
        out.append("STUDIO_TUNNEL is set: this machine would run the studio's tunnel")
    if backup.setting("STUDIO_R2_KEY_ID") or backup.setting("STUDIO_MEDIA_SAS"):
        out.append("a key to the films' bucket is set: this machine would publish films")
    return out


def _rclone(cmd, env):
    r = subprocess.run(cmd, env=env, capture_output=True, text=True, errors="replace", check=False)
    return r.returncode, r.stdout, r.stderr


def common():
    out = ["--transfers", "8", "--checkers", "16", "--retries", "2", "--s3-no-check-bucket"]
    return out + [
        "--use-json-log",
        "--log-level",
        "NOTICE",
        "--stats",
        "1h",
        "--stats-log-level",
        "NOTICE",
    ]


def pulls(bucket, drill=False):
    """The rclone commands of --all, in order: [(what, argv)]."""
    src = "%s:%s" % (backup.REMOTE, bucket)
    home = ["rclone", "copy", src + "/home", backup.HOME, "--update", "--fast-list"]
    for pattern in DRILL_SKIP if drill else ():
        home += ["--exclude", pattern]
    out = [("home", home + common())]
    out.append(
        (
            "models",
            [
                "rclone",
                "copy",
                src + "/models",
                os.path.join(backup.REPO, "models"),
                "--size-only",
                *common(),
            ],
        )
    )
    if not drill:  # a rehearsal has no use for the live machine's usage log
        out.append(
            (
                "usage",
                [
                    "rclone",
                    "copy",
                    src + "/usage",
                    os.path.join(backup.HOME, "usage"),
                    "--size-only",
                    *common(),
                ],
            )
        )
    return out


def plan():
    bucket, env = backup.account()
    src = "%s:%s" % (backup.REMOTE, bucket)
    rc, out, err = _rclone(
        ["rclone", "cat", src + "/_status/latest.json", "--s3-no-check-bucket"], env
    )
    if rc == 0:
        try:
            st = json.loads(out)
            print(
                "the mirror was last written %s (%s pass, ok=%s)"
                % (st.get("at"), st.get("kind"), st.get("ok"))
            )
        except ValueError:
            pass
    rc, out, err = _rclone(["rclone", "lsf", src + "/home/", "--s3-no-check-bucket"], env)
    if rc != 0:
        sys.exit("cannot read the mirror: %s" % err.strip()[-300:])
    total_n = total_b = 0
    for name in sorted(out.split()):
        rc, o, _ = _rclone(
            [
                "rclone",
                "size",
                src + "/home/" + name,
                "--json",
                "--fast-list",
                "--s3-no-check-bucket",
            ],
            env,
        )
        try:
            j = json.loads(o)
        except ValueError:
            j = {}
        n, b = j.get("count", 0), j.get("bytes", 0)
        total_n, total_b = total_n + n, total_b + b
        here = os.path.exists(os.path.join(backup.HOME, name.rstrip("/")))
        print(
            "  %-22s %8d file(s) %9.2f GB   %s"
            % (name, n, b / 1e9, "here too" if here else "NOT HERE")
        )
    print("the mirror's home: %d files, %.1f GB" % (total_n, total_b / 1e9))


def all_(drill=False):
    if drill:
        why = not_a_drill()
        if why:
            sys.exit("--drill, and this is not a rehearsal:\n  " + "\n  ".join(why))
    bucket, env = backup.account()
    os.makedirs(backup.HOME, exist_ok=True)
    ok = True
    for what, cmd in pulls(bucket, drill):
        t0 = time.time()
        rc, _, err = _rclone(cmd, env)
        st, errs = backup.stats_of(err)
        print(
            "%-7s %6d file(s) %9.2f GB  %5.0f s%s"
            % (
                what,
                st["files"],
                st["bytes"] / 1e9,
                time.time() - t0,
                "" if rc == 0 else "   EXIT %d" % rc,
            ),
            flush=True,
        )
        for e in errs[:5]:
            print("  ERROR: " + e)
        ok = ok and rc == 0
    return ok


def film(fid, day=None):
    bucket, env = backup.account()
    src = "%s:%s" % (backup.REMOTE, bucket)
    if day:  # beside the home, never over the film: these are files the film itself replaced
        dst = os.path.join(os.path.dirname(backup.HOME), "restored", "%s-%s" % (fid, day))
        cmd = [
            "rclone",
            "copy",
            "%s/_history/%s/home/projects/%s" % (src, day, fid),
            dst,
            *common(),
        ]
        rc, _, err = _rclone(cmd, env)
        st, _ = backup.stats_of(err)
        print("%d file(s) of %s from %s into %s" % (st["files"], fid, day, dst))
        return rc == 0
    ok = True
    for sub in ("projects", "claude"):
        dst = os.path.join(backup.HOME, sub, fid)
        cmd = ["rclone", "copy", "%s/home/%s/%s" % (src, sub, fid), dst, "--update", *common()]
        rc, _, err = _rclone(cmd, env)
        st, _ = backup.stats_of(err)
        print("%-8s %6d file(s) %8.2f GB into %s" % (sub, st["files"], st["bytes"] / 1e9, dst))
        ok = ok and rc == 0
    return ok


def settle():
    """A rehearsal's copy only: every film that was being made is put down in its own record --
    no database, no site -- and the marks of rounds and unbrandings under way go. -> the ids."""
    why = not_a_drill()
    if why:
        sys.exit("this is not a rehearsal, nothing was changed:\n  " + "\n  ".join(why))
    done = []
    projects = os.path.join(backup.HOME, "projects")
    for fid in sorted(os.listdir(projects) if os.path.isdir(projects) else []):
        p = os.path.join(projects, fid, "studio.json")
        try:
            with open(p, encoding="utf-8") as f:
                rec = json.load(f)
        except (OSError, ValueError):
            continue
        changed = False
        if rec.get("state") in ACTIVE:
            rec.update(state=PUT_DOWN, error="put down in a rehearsal copy (restore.py --settle)")
            changed = True
        if (rec.get("round") or {}).get("state") in ("queued", "running", "finishing"):
            rec["round"] = dict(rec["round"], state="failed", error="a rehearsal copy")
            changed = True
        if changed:
            with open(p + ".tmp", "w", encoding="utf-8") as f:
                json.dump(rec, f, indent=1, ensure_ascii=False)
            os.replace(p + ".tmp", p)
            done.append(fid)
    for marks in (
        os.path.join(backup.HOME, "rounds", "_asked"),
        os.path.join(backup.HOME, "unbrand"),
    ):
        shutil.rmtree(marks, ignore_errors=True)
    shutil.rmtree(os.path.join(backup.HOME, "servers"), ignore_errors=True)
    return done


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--plan", action="store_true", help="what the mirror holds; changes nothing")
    g.add_argument("--all", action="store_true", help="everything missing here or newer there")
    g.add_argument("--film", metavar="ID", help="one film's folder and sessions")
    g.add_argument("--check-drill", action="store_true", help="exit 1 unless this is a rehearsal")
    g.add_argument(
        "--settle", action="store_true", help="a rehearsal: put down films in the making"
    )
    ap.add_argument(
        "--drill", action="store_true", help="--all for a rehearsal: no marks of work under way"
    )
    ap.add_argument(
        "--from-history", metavar="DAY", help="--film: what a pass filed that day (YYYY-MM-DD)"
    )
    a = ap.parse_args()
    if a.plan:
        plan()
    elif a.all:
        sys.exit(0 if all_(a.drill) else 1)
    elif a.film:
        if not a.film.startswith("studio-") or "/" in a.film or ".." in a.film:
            ap.error("not a film id: %s" % a.film)
        sys.exit(0 if film(a.film, a.from_history) else 1)
    elif a.check_drill:
        why = not_a_drill()
        print(
            "a rehearsal: it cannot reach the database, the site, the tunnel or the films' bucket"
            if not why
            else "NOT a rehearsal:\n  " + "\n  ".join(why)
        )
        sys.exit(1 if why else 0)
    else:
        ids = settle()
        print(
            "%d film(s) put down in this copy%s" % (len(ids), ": " + ", ".join(ids) if ids else "")
        )
