#!/usr/bin/env python
"""backup.py without rclone, a bucket or a network: what is mirrored, how a pass is asked for,
and when the mirror counts as behind. Seconds.

    python studio/test_backup.py

The rules file (deploy/backup-filter.txt) keeps what a person made and leaves out what the machine
makes again -- read here by a small matcher for the part of rclone's patterns the file uses. Every
folder the studio's code makes at the top of its home is named in that file, so a new one cannot
be added without deciding. A pass never carries the key on its command line, files what it
replaces under the day's history, stops at a limit of removals, and refuses a home that is not
there. The status says "stale" for a pass too old, a nightly pass too old, and a pass that failed.
"""

import os
import re
import sys
import glob
import json
import time
import shutil
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
HOME = tempfile.mkdtemp(prefix="studio-backup-test-")
os.environ["STUDIO_HOME"] = os.path.join(HOME, "studio")
os.environ["STUDIO_REPO"] = os.path.join(HOME, "repo")
os.environ["STUDIO_ENV_FILE"] = os.path.join(HOME, "repo", ".env")
sys.path.insert(0, HERE)
import backup  # noqa: E402 -- the stdlib only

bad = []


def check(ok, what, got=None):
    print("%s  %s%s" % ("ok   " if ok else "FAIL ", what, "" if ok else "  -- %r" % (got,)))
    if not ok:
        bad.append(what)


def rules():
    """[(keep, pattern)] of the filter file, in order."""
    out = []
    with open(backup.FILTER, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            line = line.rstrip("\n")
            if not line.strip() or line.lstrip().startswith(("#", ";")):
                continue
            m = re.match(r"^([+-]) (\S+)$", line)
            check(bool(m), "backup-filter.txt:%d is '+ pattern' or '- pattern'" % n, line)
            if m:
                out.append((m.group(1) == "+", m.group(2)))
    return out


def regex(pattern):
    """The part of rclone's patterns the file uses: * within a name, ** across folders, a leading
    / for the top of the home, and no / at all for a name at any depth."""
    body = ""
    i = 0
    while i < len(pattern):
        if pattern.startswith("**", i):
            body, i = body + ".*", i + 2
        elif pattern[i] == "*":
            body, i = body + "[^/]*", i + 1
        else:
            body, i = body + re.escape(pattern[i]), i + 1
    return re.compile("^" + body + "$" if pattern.startswith("/") else "(^|.*/)" + body + "$")


def kept(path, rs):
    """Whether a path (from the top of the home, with its leading /) is mirrored."""
    for keep, pattern in rs:
        if regex(pattern).match(path):
            return keep
    return True  # a path no rule names is mirrored


def the_rules():
    rs = rules()
    f = "/projects/studio-20261001-000000-abcdef"
    keeps = (
        f + "/film.js",
        f + "/studio.json",
        f + "/engine/engine.js",
        f + "/cast/pip.js",
        f + "/inputs/upload1.jpg",
        f + "/audio/vo/L07_T0_1a2b.wav",
        f + "/images/scene-3.png",
        f + "/outputs/film.mp4",
        f + "/outputs/review/sheet-1.jpg",
        f + "/versions/v2/film.js",
        f + "/versions/v2/outputs/film.mp4",
        f + "/youtube/draft-UCx.json",
        f + "/temp/brand/outro.js",
        f + "/temp/voice.json",
        f + "/temp/system-prompt.md",
        "/library/abc123/p-abcdefghij/cast/pip/v3.js",
        "/library/abc123/p-abcdefghij/voice/hello.wav",
        "/library/abc123/p-abcdefghij/brand/originals/book.pdf",
        "/templates/t-open-house/v8/film.js",
        "/uploads/abc123/u-1.jpg",
        "/claude/studio-20261001-000000-abcdef/projects/x/session.jsonl",
        "/rounds/_asked/studio-20261001-000000-abcdef.json",
        "/rounds/studio-20261001-000000-abcdef.r2/film.js",
        "/unbrand/studio-20261001-000000-abcdef.json",
        "/backups/studio-20261001-000000-abcdef-20261005-120000.tar.gz",
        "/git/p-abcdefghij.git/HEAD",
        "/outbox.jsonl",
        "/a-folder-nobody-thought-about/file.bin",
    )
    skips = (
        f + "/temp/motion/012.50.png",
        f + "/temp/thumbs/stills-0123/012.40.png",
        f + "/temp/film_silent.mp4",
        f + "/temp/record.lock",
        f + "/temp/castsheet/stills/000.75.png",
        "/rounds/studio-20261001-000000-abcdef.r2/temp/motion/001.00.png",
        "/releases/c994ee4b4d7e/studio/server.py",
        "/servers/current",
        "/servers/a926.json",
        "/deploy.lock",
        "/outbox.jsonl.lock",
        "/library/abc123/index.json.lock",
        "/cache/web/page.html",
        "/tmp/deleted-studio-x/film.js",
        "/scratch/notes.txt",
        "/usage/2026-10-12.jsonl",
        "/backup.json",
    )
    for p in keeps:
        check(kept(p, rs), "mirrored: %s" % p)
    for p in skips:
        check(not kept(p, rs), "left out: %s" % p)


def every_folder_is_named():
    """Every name the studio's code joins onto its home is decided by a rule, kept or left out
    -- as a file at the top of the home, or as a folder with something in it."""
    rs = rules()
    named = {}
    join = re.compile(r"os\.path\.join\(\s*(?:films\.|film\.)?HOME,\s*\"([A-Za-z0-9_.\-]+)\"")
    for path in sorted(glob.glob(os.path.join(HERE, "*.py"))):
        if os.path.basename(path).startswith("test_"):
            continue
        with open(path, encoding="utf-8") as f:
            for name in join.findall(f.read()):
                named.setdefault(name, os.path.basename(path))
    check(len(named) >= 10, "the code's folders were found (projects, library, claude ...)", named)
    for name, where in sorted(named.items()):
        hit = [p for _, p in rs if regex(p).match("/" + name) or regex(p).match("/%s/x" % name)]
        check(bool(hit), "%s (%s) is decided by a rule in backup-filter.txt" % (name, where))
    check(
        not [p for _, p in rs if regex(p).match("/a-new-folder/x")],
        "and a folder no rule names is not decided by one (it is mirrored)",
    )


def write_env(**kv):
    os.makedirs(os.path.dirname(backup.ENV_FILE), exist_ok=True)
    with open(backup.ENV_FILE, "w", encoding="utf-8") as f:
        for k, v in kv.items():
            f.write('%s="%s"\n' % (k, v))


def a_pass():
    write_env(
        STUDIO_R2_ENDPOINT="https://acct.r2.cloudflarestorage.com/kitcut-media",
        STUDIO_R2_KEY_ID="films-key",
        STUDIO_R2_SECRET="films-secret",
    )
    bucket, env = backup.account()
    check(bucket == "kitcut-backup", "the bucket is kitcut-backup unless the .env says", bucket)
    check(
        env["RCLONE_CONFIG_KITCUT_ENDPOINT"] == "https://acct.r2.cloudflarestorage.com",
        "the account's address, without the films' bucket",
        env["RCLONE_CONFIG_KITCUT_ENDPOINT"],
    )
    check(env["RCLONE_CONFIG_KITCUT_ACCESS_KEY_ID"] == "films-key", "the films' key by default")
    write_env(
        STUDIO_R2_ENDPOINT="https://acct.r2.cloudflarestorage.com/kitcut-media",
        STUDIO_R2_KEY_ID="films-key",
        STUDIO_R2_SECRET="films-secret",
        STUDIO_BACKUP_R2_KEY_ID="backup-key",
        STUDIO_BACKUP_R2_SECRET="backup-secret",
        STUDIO_BACKUP_BUCKET="another",
    )
    bucket, env = backup.account()
    check(
        (bucket, env["RCLONE_CONFIG_KITCUT_ACCESS_KEY_ID"]) == ("another", "backup-key"),
        "a key of its own, and another bucket, when the .env names them",
        bucket,
    )
    os.makedirs(os.path.join(backup.HOME, "usage"), exist_ok=True)
    quick = backup.passes("kitcut-backup", day="2026-10-12")
    full = backup.passes("kitcut-backup", full=True, day="2026-10-12")
    flat = " ".join(a for _, cmd in quick + full for a in cmd)
    check("secret" not in flat and "backup-key" not in flat, "no key is on a command line")
    home = dict(quick)["home"]
    check(home[:2] == ["rclone", "sync"] and "--size-only" in home, "a pass syncs the home by size")
    check(
        "kitcut:kitcut-backup/_history/2026-10-12/home" in home,
        "what it replaces or removes is filed under the day's history",
    )
    check(
        home[home.index("--max-delete") + 1] == str(backup.MAX_DELETE),
        "it stops at a limit of removals",
    )
    check(home[home.index("--filter-from") + 1] == backup.FILTER, "by the rules file")
    recent = dict(quick)["recent"]
    check(
        recent[:2] == ["rclone", "copy"] and "--max-age" in recent and "--no-traverse" in recent,
        "then looks again at what changed lately, file by file",
    )
    check(
        "--checksum" in dict(full)["home"] and "recent" not in dict(full),
        "a full pass compares checksums",
    )
    usage = dict(quick)["usage"]
    check("--backup-dir" not in usage, "the usage log goes without history")
    check("--dry-run" in dict(backup.passes("b", dry=True))["home"], "a plan is a dry run")


def no_home_no_pass():
    shutil.rmtree(os.path.join(backup.HOME, "projects"), ignore_errors=True)
    check(
        "not there" in (backup.there() or ""), "a home with no projects/ is refused", backup.there()
    )
    os.makedirs(os.path.join(backup.HOME, "projects"))
    check("no film" in (backup.there() or ""), "and one with no film in it", backup.there())
    res = backup.run()
    check(not res["ok"] and res["errors"], "a refused pass is a failed pass", res)
    check(backup.last().get("ok") is False, "and is written down as one", backup.last())
    os.makedirs(os.path.join(backup.HOME, "projects", "studio-20261001-000000-abcdef"))
    check(backup.there() is None, "a home with a film may be mirrored", backup.there())


def staleness():
    now = time.mktime(time.strptime("2026-10-12T12:00:00", "%Y-%m-%dT%H:%M:%S"))
    good = {"ok": True, "last_quick": "2026-10-12T11:50:00", "last_full": "2026-10-12T03:30:00"}
    check(backup.stale(good, now) == [], "ten minutes old, with last night's full pass: not stale")
    check(backup.stale({}, now), "no pass at all is stale", backup.stale({}, now))
    late = dict(good, last_quick="2026-10-12T10:00:00")
    check(any("min ago" in s for s in backup.stale(late, now)), "two hours without a pass is")
    old = dict(good, last_full="2026-10-10T03:30:00")
    check(any("full pass" in s for s in backup.stale(old, now)), "two days without a full pass is")
    failed = dict(good, ok=False, errors=["home: AccessDenied"])
    check(
        any("AccessDenied" in s for s in backup.stale(failed, now)),
        "a pass that failed says why",
        backup.stale(failed, now),
    )
    log = "\n".join(
        [
            json.dumps({"level": "error", "msg": "Failed to copy: AccessDenied"}),
            "not json",
            json.dumps(
                {
                    "level": "notice",
                    "stats": {"transfers": 3, "bytes": 2048, "deletes": 1, "errors": 1},
                }
            ),
        ]
    )
    st, errs = backup.stats_of(log)
    check(
        (st["files"], st["bytes"], st["deleted"], st["errors"]) == (3, 2048, 1, 1)
        and len(errs) == 1,
        "rclone's log is read for what went and what failed",
        (st, errs),
    )


if __name__ == "__main__":
    try:
        the_rules()
        every_folder_is_named()
        a_pass()
        no_home_no_pass()
        staleness()
    finally:
        shutil.rmtree(HOME, ignore_errors=True)
    print("\n%d failed" % len(bad) if bad else "\nall passed")
    sys.exit(1 if bad else 0)
