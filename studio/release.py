#!/usr/bin/env python
"""Sketch Studio releases: the code the public studio runs, frozen.

    python studio/release.py                 snapshot tag studio-stable, test it, make it current
    python studio/release.py --ref HEAD      the same for any commit
    python studio/release.py --list          what is built, and which one is current

A release is `git archive <commit>` unpacked into STUDIO_HOME\\releases\\<sha12>: committed files
only -- no .env, no projects\\, nobody's uncommitted edits -- and read-only. serve.ps1 starts the
server from the current one, and every film records the release that made it. So developers
(and their Claude sessions) edit the working tree freely: nothing they do reaches a film being
made until the next release. Moving the tag is the decision to ship:

    git tag -f studio-stable <commit>  &&  python studio/release.py  &&  serve.ps1 -Restart

Two things stay shared with the working tree: models\\ (a junction to the soundfont cache every
film adds to) and the .venv the server and its steps run under.
"""

import os
import sys
import json
import stat
import shutil
import tarfile
import argparse
import subprocess
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)  # run from the working tree
sys.path.insert(0, HERE)
import film as films  # noqa: E402

RELEASES = os.path.join(films.HOME, "releases")
CURRENT = os.path.join(RELEASES, "current")
TESTS = ("test_guard.py", "test_sched.py", "test_isolation.py")


def git(*args):
    return subprocess.run(
        ["git", "-C", REPO, *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def current():
    try:
        with open(CURRENT, encoding="utf-8") as f:
            return f.read().strip() or None
    except OSError:
        return None


def build(ref):
    """The snapshot of `ref` (reused when it exists). Returns its folder."""
    try:
        sha = git("rev-parse", ref + "^{commit}")
    except subprocess.CalledProcessError:
        sys.exit(
            "no commit %r -- to ship the working tree's HEAD: git tag -f studio-stable HEAD" % ref
        )
    dest = os.path.join(RELEASES, sha[:12])
    if os.path.isdir(dest):
        print("release %s (%s) is already built" % (sha[:12], ref))
        return dest
    part = dest + ".partial"
    shutil.rmtree(part, ignore_errors=True)
    os.makedirs(part)
    arc = subprocess.Popen(
        ["git", "-C", REPO, "archive", "--format=tar", sha], stdout=subprocess.PIPE
    )
    with tarfile.open(fileobj=arc.stdout, mode="r|") as tar:
        tar.extractall(part, filter="data")
    if arc.wait() != 0:
        sys.exit("git archive failed")
    with open(os.path.join(part, "RELEASE.json"), "w", encoding="utf-8") as f:
        json.dump(
            {
                "sha": sha,
                "ref": ref,
                "built": datetime.now().isoformat(timespec="seconds"),
                "from": REPO,
            },
            f,
            indent=2,
        )
    # read-only: a release is what was committed, and stays that (new files -- Python's caches,
    # the encoder probe -- may still appear beside them)
    for root, _, names in os.walk(part):
        for n in names:
            os.chmod(os.path.join(root, n), stat.S_IREAD)
    models = os.path.join(REPO, "models")
    os.makedirs(models, exist_ok=True)
    link = os.path.join(part, "models")
    if os.name == "nt":
        r = subprocess.run(
            ["cmd", "/c", "mklink", "/J", link, models], capture_output=True, text=True
        )
        if r.returncode:
            sys.exit("could not link models\\: %s" % (r.stdout + r.stderr).strip())
    else:
        os.symlink(models, link)
    os.rename(part, dest)
    print("built release %s (%s) in %s" % (sha[:12], ref, dest))
    return dest


def test(dest):
    """The studio's quick tests, run from inside the snapshot."""
    env = dict(os.environ, STUDIO_REPO=REPO, STUDIO_ENV_FILE=os.path.join(REPO, ".env"))
    env.pop("STUDIO_HOME", None)  # each test makes its own throwaway home
    for t in TESTS:
        r = subprocess.run(
            [sys.executable, "-X", "utf8", os.path.join(dest, "studio", t)],
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        last = (r.stdout.strip().splitlines() or ["(no output)"])[-1]
        print("  %-18s %s" % (t, last))
        if r.returncode:
            print(r.stdout[-3000:] + r.stderr[-2000:])
            return False
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--ref", default="studio-stable", help="the commit to ship (a tag, a sha)")
    ap.add_argument("--list", action="store_true", help="the releases built, and the current one")
    ap.add_argument("--no-test", action="store_true", help="make it current without testing it")
    args = ap.parse_args()
    if args.list:
        cur = current()
        for n in sorted(os.listdir(RELEASES)) if os.path.isdir(RELEASES) else []:
            p = os.path.join(RELEASES, n, "RELEASE.json")
            if os.path.exists(p):
                with open(p, encoding="utf-8") as f:
                    r = json.load(f)
                print("%s %s  %s  %s" % ("*" if n == cur else " ", n, r["built"], r["ref"]))
        return
    dest = build(args.ref)
    if not args.no_test and not test(dest):
        sys.exit("the release's tests failed: it is built but NOT current")
    os.makedirs(RELEASES, exist_ok=True)
    with open(CURRENT + ".tmp", "w", encoding="utf-8") as f:
        f.write(os.path.basename(dest))
    os.replace(CURRENT + ".tmp", CURRENT)
    print("current release: %s  (serve.ps1 -Restart to run it)" % os.path.basename(dest))


if __name__ == "__main__":
    main()
