#!/usr/bin/env python
"""The studio's home mirrored off the machine: one pass to the R2 bucket kitcut-backup.

    python studio/backup.py --plan       what a pass would send and remove; sends nothing
    python studio/backup.py              one pass (every 15 minutes by kitcut-backup.timer)
    python studio/backup.py --full       the same, comparing every file by checksum (nightly)
    python studio/backup.py --status     the last pass; exit 1 when it is older than it may be
    python studio/backup.py --verify     every mirrored file against the bucket, by checksum;
                                         changes nothing, exit 1 on a difference
    (on the VM: ops.sh backup [--plan | --full | status | verify | install])

Why: everything needed to work on a film again -- its code, its narration takes, its maker's
uploads, the project's cast and voice lines, the templates -- was on one disk of one machine, with
one snapshot fourteen days old (2026-10-12). Azure Backup now copies the machine nightly; this is
the copy that is off Azure and at most a quarter of an hour behind.

What is mirrored is one file: studio/deploy/backup-filter.txt. In the bucket:

    home/                     the studio's home, as that file says
    usage/                    the usage logs (appended to all day: no history kept)
    models/                   the checkout's models/ (soundfonts, face and matting models)
    _history/<day>/home/      what a pass that day replaced or removed, kept 30 days by the
                              bucket's own rule: a wrong delete is not mirrored into a loss
    _status/latest.json       what the last pass did
    db/<day>/                 the site's database, exported nightly (studio/dbdump.py)

How a pass compares, and why not the obvious way. S3 keeps a file's own time in metadata that only
a request per object returns: 85,000 requests a pass, 96 passes a day. So:

    every pass   new files, files whose size changed, files that are gone      one listing
                 files changed in the last hours whatever their size            a request each
    --full       every file by checksum (a listing gives each object's MD5,
                 because nothing is uploaded in parts: --s3-upload-cutoff)      reads the disk

What only --full sees: a file put back with an old time and the very same size (a version swapped
back). A pass refuses to run on a home that is not there (a disk that did not mount would
otherwise read as "everything was deleted") and stops at MAX_DELETE removals.

The key: STUDIO_BACKUP_R2_KEY_ID / _SECRET / _ENDPOINT in the studio's .env (a key of its own,
allowed to write kitcut-backup and nothing else), else the films' own STUDIO_R2_ three. It reaches
rclone through the environment, never the command line. Needs rclone (scripts/setup-linux.sh).
"""

import os
import sys
import json
import time
import shutil
import argparse
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.environ.get("STUDIO_REPO") or os.path.dirname(HERE))
HOME = os.path.abspath(
    os.environ.get("STUDIO_HOME") or os.path.join(os.path.dirname(REPO), "studio")
)
ENV_FILE = os.environ.get("STUDIO_ENV_FILE") or os.path.join(REPO, ".env")
FILTER = os.path.join(HERE, "deploy", "backup-filter.txt")
STATUS = os.path.join(HOME, "backup.json")
REMOTE = "kitcut"  # rclone's name for the bucket's account, configured from the environment
MAX_DELETE = 5000  # removals in one pass before it is taken for a mistake, not a clean-up
RECENT_H = 6  # a pass looks again at files changed in this many hours, whatever their size
QUICK_MAX_MIN = 45  # --status: a pass every 15 minutes may be this old
FULL_MAX_H = 36  # and the nightly one this old
# nothing is uploaded in parts, so every object's ETag is its MD5 and a listing is enough to
# compare by checksum (R2 takes 5 GiB in one request; the largest master is under 1 GB)
CUTOFF = "4G"


def setting(name, path=None):
    """The last `NAME=value` of the studio's .env, without quotes; "" when it is not there."""
    out = ""
    try:
        with open(path or ENV_FILE, encoding="utf-8-sig") as f:
            for line in f:
                k, eq, v = line.partition("=")
                if eq and k.strip() == name:
                    out = v.strip().strip("\"'")
    except OSError:
        pass
    return out


def account():
    """(bucket, the environment rclone needs) -- raises when no key is set."""
    pick = "STUDIO_BACKUP_R2" if setting("STUDIO_BACKUP_R2_KEY_ID") else "STUDIO_R2"
    kid, sec = setting(pick + "_KEY_ID"), setting(pick + "_SECRET")
    end = setting(pick + "_ENDPOINT") or setting("STUDIO_R2_ENDPOINT")
    if not (kid and sec and end):
        raise RuntimeError("no R2 key in %s (STUDIO_BACKUP_R2_* or STUDIO_R2_*)" % ENV_FILE)
    # the films' setting names their bucket too (https://<account>.r2.cloudflarestorage.com/<b>)
    scheme, _, rest = end.partition("://")
    env = dict(os.environ)
    p = "RCLONE_CONFIG_%s_" % REMOTE.upper()
    env.update(
        {
            p + "TYPE": "s3",
            p + "PROVIDER": "Cloudflare",
            p + "ENDPOINT": "%s://%s" % (scheme, rest.split("/")[0]),
            p + "ACCESS_KEY_ID": kid,
            p + "SECRET_ACCESS_KEY": sec,
            p + "REGION": "auto",
            p + "NO_CHECK_BUCKET": "true",  # a key for one bucket may not ask whether it exists
        }
    )
    return setting("STUDIO_BACKUP_BUCKET") or "kitcut-backup", env


def there():
    """Why the home cannot be mirrored now, or None: a pass on an empty folder would file the
    whole mirror as deleted, and a rehearsal's copy of the home (restore.py) is not the studio's."""
    if setting("STUDIO_DRILL") == "1":
        return "this machine is a rehearsal (STUDIO_DRILL=1): it never writes the mirror"
    projects = os.path.join(HOME, "projects")
    if not os.path.isdir(projects):
        return "%s is not there (is the data disk mounted?)" % projects
    if not any(n.startswith("studio-") for n in os.listdir(projects)):
        return "%s holds no film" % projects
    return None


def short_of_memory(floor_mb=None):
    """Megabytes the machine has available when that is under the floor, else None. A pass reads
    the films' disk through the page cache; on a machine already short of memory that is what
    pushes it over (KI-066: the studio froze with a first upload running beside a runaway step).
    The mirror being a quarter of an hour later is the cheaper of the two."""
    floor = (
        float(os.environ.get("STUDIO_BACKUP_MIN_FREE_MB") or 3000) if floor_mb is None else floor_mb
    )
    try:
        with open("/proc/meminfo", encoding="ascii") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    mb = int(line.split()[1]) / 1024
                    return mb if mb < floor else None
    except (OSError, ValueError):
        pass
    return None


def lock():
    """This pass's hold on the mirror, or None when another pass has it (the nightly full pass
    runs for a while, and the quarter-hourly one must not start beside it). An open file: the
    kernel lets go of it when the process ends, however it ends."""
    try:
        import fcntl  # noqa: PLC0415 -- Linux; a laptop has no second pass to keep apart
    except ImportError:
        return True
    f = open(os.path.join(HOME, "backup.lock"), "w")  # noqa: SIM115 -- held until exit
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        return None
    return f


def common(dry=False):
    # few at once: it reads the films' disk beside films being made (KI-066)
    out = ["--fast-list", "--transfers", "3", "--checkers", "6", "--retries", "2"]
    # the home's only links are Claude Code's logs/latest pointers: nothing to mirror
    out += ["--s3-upload-cutoff", CUTOFF, "--s3-no-check-bucket", "--skip-links"]
    out += [
        "--use-json-log",
        "--log-level",
        "NOTICE",
        "--stats",
        "1h",
        "--stats-log-level",
        "NOTICE",
    ]
    return out + (["--dry-run"] if dry else [])


def passes(bucket, full=False, dry=False, day=None, recent_h=RECENT_H):
    """The rclone commands of one pass, in order: [(what, argv)]. Nothing secret is in them."""
    day = day or time.strftime("%Y-%m-%d")
    dst = "%s:%s" % (REMOTE, bucket)
    kept = ["--filter-from", FILTER, "--backup-dir", "%s/_history/%s/home" % (dst, day)]
    home = ["rclone", "sync", HOME, dst + "/home", *kept, "--max-delete", str(MAX_DELETE)]
    out = [("home", home + ["--checksum" if full else "--size-only"] + common(dry))]
    if not full:  # changed lately and the same size: asked one by one, by the file's own time
        out.append(
            (
                "recent",
                ["rclone", "copy", HOME, dst + "/home", *kept, "--max-age", "%dh" % recent_h]
                + ["--no-traverse"]
                + [a for a in common(dry) if a != "--fast-list"],
            )
        )
    for what, src in (
        ("usage", os.path.join(HOME, "usage")),
        ("models", os.path.join(REPO, "models")),
    ):
        if os.path.isdir(src):
            cmd = ["rclone", "sync", src, "%s/%s" % (dst, what), "--size-only"]
            out.append((what, cmd + ["--exclude", "*.lock"] + common(dry)))
    return out


def stats_of(text):
    """rclone's last stats line out of its JSON log -> {"files", "bytes", "deleted", "moved",
    "errors", "checked"}; and the error lines it wrote."""
    last, errors = {}, []
    for line in text.splitlines():
        try:
            j = json.loads(line)
        except ValueError:
            continue
        if isinstance(j.get("stats"), dict):
            last = j["stats"]
        elif j.get("level") == "error":
            errors.append((j.get("msg") or "")[:300])
    return (
        {
            "files": last.get("transfers", 0),
            "bytes": last.get("bytes", 0),
            "deleted": last.get("deletes", 0),
            "moved": last.get("renames", 0),
            "errors": last.get("errors", 0),
            "checked": last.get("checks", 0),
        },
        errors,
    )


def run(full=False, dry=False):
    """One pass. -> the status dict (also written to STATUS and the bucket unless `dry`)."""
    t0 = time.time()
    res = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "kind": "full" if full else "quick"}
    res.update(ok=False, parts={}, errors=[])
    why = there()
    held = None if why else lock()
    if not why and held is None:
        return dict(res, ok=True, skipped="another pass is running", seconds=0)
    short = None if why or dry else short_of_memory()
    if short is not None:
        said = "the machine has %d MB of memory available: the pass waits for the next turn" % short
        return dict(res, ok=True, skipped=said, seconds=0)
    if why:
        res["errors"].append(why)
    elif not shutil.which("rclone"):
        res["errors"].append("rclone is not installed (scripts/setup-linux.sh)")
    else:
        bucket, env = account()
        res["bucket"] = bucket
        for what, cmd in passes(bucket, full, dry):
            r = subprocess.run(cmd, env=env, capture_output=True, text=True, errors="replace")
            st, errs = stats_of(r.stderr)
            st["exit"] = r.returncode
            res["parts"][what] = st
            if r.returncode != 0:
                res["errors"] += ["%s: %s" % (what, e) for e in errs[:5]] or [
                    "%s: rclone exit %d: %s" % (what, r.returncode, r.stderr.strip()[-300:])
                ]
        res["ok"] = not res["errors"]
    res["seconds"] = round(time.time() - t0, 1)
    if dry:
        return res
    prev = last()
    for k in ("quick", "full"):  # when each kind last went through
        res["last_" + k] = res["at"] if res["ok"] and res["kind"] == k else prev.get("last_" + k)
    if res["ok"] and full:  # a full pass does everything a quick one does
        res["last_quick"] = res["at"]
    tmp = STATUS + ".%d.tmp" % os.getpid()
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1)
    os.replace(tmp, STATUS)
    if res.get("bucket"):
        dst = "%s:%s/_status/latest.json" % (REMOTE, res["bucket"])
        subprocess.run(
            ["rclone", "copyto", STATUS, dst, "--s3-no-check-bucket"],
            env=env,
            capture_output=True,
            check=False,
        )
    return res


def last():
    try:
        with open(STATUS, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _age_min(stamp, now=None):
    try:
        then = time.mktime(time.strptime(stamp, "%Y-%m-%dT%H:%M:%S"))
    except (TypeError, ValueError):
        return None
    return ((now or time.time()) - then) / 60


def stale(st, now=None):
    """Why the mirror is behind, as words for a person; [] when it is not."""
    out = []
    q, f = _age_min(st.get("last_quick"), now), _age_min(st.get("last_full"), now)
    if q is None:
        out.append("no pass has gone through yet")
    elif q > QUICK_MAX_MIN:
        out.append("the last pass that went through was %d min ago" % q)
    if f is None:
        out.append("no full pass has gone through yet")
    elif f > FULL_MAX_H * 60:
        out.append("the last full pass was %d h ago" % (f / 60))
    # one failed pass is not news: a file a film is still writing changes under the upload
    # ("md5 hashes differ") and the next pass sends it. A failure only counts once the mirror
    # is behind by age, and then it says why.
    if out and st and not st.get("ok"):
        out.append("the last pass failed: %s" % "; ".join(st.get("errors") or ["?"])[:300])
    return out


def _gb(n):
    return "%.2f GB" % (n / 1e9)


def say(res, plan=False):
    if res.get("skipped"):
        return "skipped: %s" % res["skipped"]
    lines = []
    for what, p in res.get("parts", {}).items():
        lines.append(
            "%-7s %s %6d file(s) %10s   %s %d   checked %d%s"
            % (
                what,
                "would send" if plan else "sent",
                p["files"],
                _gb(p["bytes"]),
                "would remove" if plan else "removed",
                p["deleted"],
                p["checked"],
                "" if p["exit"] == 0 else "   EXIT %d" % p["exit"],
            )
        )
    for e in res.get("errors") or []:
        lines.append("ERROR: " + e)
    lines.append(
        "%s %s pass, %.0f s%s"
        % (
            "a dry" if plan else "ok:" if res.get("ok") else "FAILED:",
            res.get("kind"),
            res.get("seconds", 0),
            " -> %s" % res["bucket"] if res.get("bucket") else "",
        )
    )
    return "\n".join(lines)


def verify():
    """rclone check, one way: every mirrored file is in the bucket with the same checksum."""
    bucket, env = account()
    cmd = ["rclone", "check", HOME, "%s:%s/home" % (REMOTE, bucket), "--one-way", "--fast-list"]
    cmd += ["--filter-from", FILTER, "--checkers", "8", "--s3-no-check-bucket"]
    r = subprocess.run(cmd, env=env, capture_output=True, text=True, errors="replace")
    tail = [x for x in r.stderr.strip().splitlines() if x.strip()][-6:]
    print("\n".join(tail))
    return r.returncode


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--plan", action="store_true", help="what a pass would do; sends nothing")
    g.add_argument("--full", action="store_true", help="compare every file by checksum")
    g.add_argument("--status", action="store_true", help="the last pass; exit 1 when stale")
    g.add_argument("--verify", action="store_true", help="check the bucket against the home")
    a = ap.parse_args()
    if a.status:
        st = last()
        print(
            json.dumps(
                {k: st.get(k) for k in ("at", "kind", "ok", "seconds", "last_quick", "last_full")}
            )
        )
        bad = stale(st)
        for b in bad:
            print("STALE: " + b)
        sys.exit(1 if bad else 0)
    if a.verify:
        sys.exit(verify())
    out = run(full=a.full, dry=a.plan)
    print(say(out, a.plan))
    sys.exit(0 if out["ok"] else 1)
