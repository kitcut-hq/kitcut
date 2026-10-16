#!/usr/bin/env python3
"""Ship the studio by itself when studio-poc moves on GitHub: the machine pulls, nothing pushes in.

    python3 studio/deploy/autoship.py            look, and look again while there is a reason to
                                                 wait (kitcut-autoship.service: GitHub's hook, and
                                                 a poll every 15 min)
    python3 studio/deploy/autoship.py --plan     what a look would do now; changes nothing
    python3 studio/deploy/autoship.py --status   the last decision, and the log of the last ship
    python3 studio/deploy/autoship.py --forget   forget that the head failed: the next look tries it
    bash studio/deploy/ops.sh autoship ...       the same, from the laptop (and on, off, now)

Why the machine pulls: kitcut-hq/kitcut is public, so `git ls-remote https://github.com/...`
needs no key at all, and the machine still holds no GitHub credentials (push.sh); it reads, as
anyone can. What starts a look is GitHub's push hook: studio.kitcut.ai/hooks/github (server.py
github_hook) checks GitHub's signature and writes STUDIO_HOME/autoship.poke, and
kitcut-autoship.path starts this. Only GitHub can reach that path: Cloudflare blocks every other
address (deploy/hook-lock.mjs). The hook carries no code and no decision -- it says "look now";
everything below is decided from GitHub and the studio as they are. A poll every 15 minutes
(kitcut-autoship.timer) catches a push whose hook did not arrive (GitHub does not send one
again by itself).

A look ships only what `ops.sh ship` would, the same way: GitHub's studio-poc head, a fast-forward
of what the machine has, into the bare repo (/srv/kitcut/git) and the checkout as push.sh moves
them, then `serve.sh release` -- built, tested, a server of its own beside the running one, the
old one finishing its films. Then it asks the studio (and studio.kitcut.ai) which release leads.
It waits, and looks again every 30 s (for at most LOOK_FOR, 45 min; then the poll), when:

  - the head is younger than SETTLE (30 s): pushes in a row are one ship, not three;
  - the studio's sound machine is busy (the `cpu` pool: a voice being recorded, a film's sound):
    a ship's build and tests take the cores those steps time words on (KI-043). At most MAX_WAIT
    (40 min) after it first saw the head; then it ships anyway, since a ship slows a film, never
    stops it;
  - another deploy holds deploy.lock (a ship from the laptop);
  - the studio does not answer (it could not prove the ship).

It does not ship, and says so in the note the site emails the owner from (machine_note.py), when:

  - requirements*.txt changed: every release shares one venv, so installing them changes the
    films still being made on the old server -- ship that by hand at a quiet moment;
  - GitHub's head is not a fast-forward of the machine's (a rewritten branch);
  - the head already failed its release's tests: once per commit, never again by itself. A new
    commit is tried as usual; `--forget` (ops.sh autoship now --retry) lets the same one be tried
    again;
  - autoship is paused (STUDIO_HOME/autoship.paused): `ops.sh rollback` pauses it, or the next
    look would ship the head straight back; `ops.sh autoship on` lifts it.

Commits that change only docs/, projects/, market/, .github/ or the root's *.md are not shipped
(the release would be the same studio); the next commit that changes anything else takes them.

Stdlib only, on the system python3: it moves the checkout it was started from, which a bash script
would go on reading as it changed (ops.sh, 2026-10-12), and it must run when the venv does not.
"""

import os
import sys
import json
import time
import fcntl
import argparse
import subprocess
import urllib.request

HOME = os.environ.get("STUDIO_HOME", "/srv/kitcut/studio")
REPO = os.environ.get("STUDIO_REPO", "/srv/kitcut/repo")
BARE = os.environ.get("STUDIO_GIT", os.path.join(os.path.dirname(REPO), "git"))
URL = os.environ.get("AUTOSHIP_URL", "https://github.com/kitcut-hq/kitcut.git")
BRANCH = "studio-poc"
PORT = int(os.environ.get("STUDIO_PORT", "8765"))
PUBLIC = "https://studio.kitcut.ai/api/health"
STATE = os.path.join(HOME, "autoship.json")
PAUSED = os.path.join(HOME, "autoship.paused")
LOGS = os.path.join(HOME, "autoship")
LOCK = os.path.join(HOME, "deploy.lock")
POKE = os.path.join(HOME, "autoship.poke")  # written by the hook (server.py github_hook)
SETTLE = int(os.environ.get("AUTOSHIP_SETTLE_S", "30"))
LOOK_AGAIN = 30  # seconds between looks while it waits
LOOK_FOR = int(os.environ.get("AUTOSHIP_LOOK_FOR_S", str(45 * 60)))
MAX_WAIT = int(os.environ.get("AUTOSHIP_MAX_WAIT_S", str(40 * 60)))
KEEP_LOGS = 30
# the states a person has to act on: the note carries them, and the site emails the owner
PROBLEMS = ("failed", "hold", "refuse")
# paths whose change alone never changes the studio a release runs
DOCS = ("docs/", "projects/", "market/", ".github/")


def docs_only(paths):
    return bool(paths) and all(
        p.startswith(DOCS) or ("/" not in p and p.endswith(".md")) for p in paths
    )


def decide(st, f, now):
    """What one look does: (action, why). action: idle | wait | skip | hold | refuse | failed |
    ship.
    st: the saved state; f: the facts (head, leader, ff, changed, cpu_busy, locked, paused)."""
    head, leader = f["head"], f["leader"]
    if not head:
        return "wait", "GitHub did not answer"
    if f["paused"]:
        return "idle", "paused: %s" % f["paused"]
    if leader and head.startswith(leader):
        return "idle", "%s leads" % leader
    if not leader:
        return "wait", "the studio does not answer on 127.0.0.1:%d" % PORT
    if not f["ff"]:
        return "refuse", "GitHub's %s (%s) is not a fast-forward of the machine's" % (
            BRANCH,
            head[:12],
        )
    if st.get("failed") == head:
        # still "failed", so the note keeps saying so until a new commit (or --retry) ships
        return "failed", "%s did not ship (%s); waiting for a new commit" % (
            head[:12],
            st.get("failed_why") or "see its log",
        )
    changed = f["changed"]
    if docs_only(changed):
        return "skip", "only docs changed since %s" % leader
    req = [
        p for p in changed if os.path.basename(p).startswith("requirements") and p.endswith(".txt")
    ]
    if req:
        return "hold", "%s changed: ship it by hand at a quiet moment (ops.sh ship)" % " ".join(req)
    seen = (st.get("seen") or {}).get(head, now)
    if now - seen < SETTLE:
        return "wait", "%s is %ds old; waiting %ds for the pushes to settle" % (
            head[:12],
            now - seen,
            SETTLE,
        )
    if f["locked"]:
        return "wait", "another deploy holds deploy.lock: %s" % f["locked"]
    if f["cpu_busy"] and now - seen < MAX_WAIT:
        return "wait", "the sound machine is busy (a voice or a film's sound, KI-043)"
    return "ship", "%s -> %s" % (leader, head[:12])


def sh(*cmd, cwd=None, check=True):
    r = subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if check and r.returncode:
        raise RuntimeError("%s: %s" % (" ".join(cmd), (r.stderr or r.stdout).strip()[-400:]))
    return r.stdout.strip()


def health(url):
    # Cloudflare answers Python's own User-Agent with 403 (the first autoship, 2026-10-16)
    req = urllib.request.Request(url, headers={"User-Agent": "kitcut-autoship/1"})
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            return json.load(r)
    except (OSError, ValueError):
        return None


def lock_holder():
    """Who holds deploy.lock, or "" when it is free (the same flock serve.sh takes)."""
    try:
        fd = os.open(LOCK, os.O_RDONLY | os.O_CREAT, 0o644)
    except OSError as e:
        return "unreadable: %s" % e
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(fd, fcntl.LOCK_UN)
        return ""
    except OSError:
        with open(LOCK, encoding="utf-8", errors="replace") as fh:
            return fh.read().strip() or "held"
    finally:
        os.close(fd)


def facts():
    f = {"head": "", "leader": "", "ff": False, "changed": [], "cpu_busy": False, "locked": ""}
    try:
        out = sh("git", "ls-remote", URL, "refs/heads/" + BRANCH)
        f["head"] = out.split()[0] if out else ""
    except RuntimeError:
        return f | {"paused": paused()}
    h = health("http://127.0.0.1:%d/api/health" % PORT)
    if h:
        f["leader"] = h.get("release") or ""
        cpu = (h.get("slots") or {}).get("cpu") or {}
        f["cpu_busy"] = (cpu.get("used") or 0) + (cpu.get("peers") or 0) > 0
    f["paused"] = paused()
    f["locked"] = lock_holder()
    if f["head"] and f["leader"] and not f["head"].startswith(f["leader"]):
        # GitHub's head, fetched beside the machine's branch (never over it), to compare
        sh(
            "git",
            "-C",
            BARE,
            "fetch",
            "-q",
            URL,
            "+refs/heads/%s:refs/github/%s" % (BRANCH, BRANCH),
        )
        mine = sh("git", "-C", BARE, "rev-parse", "refs/heads/" + BRANCH, check=False)
        f["ff"] = (
            subprocess.run(
                ["git", "-C", BARE, "merge-base", "--is-ancestor", mine or f["head"], f["head"]]
            ).returncode
            == 0
        )
        full = sh(
            "git", "-C", BARE, "rev-parse", "--verify", "-q", f["leader"] + "^{commit}", check=False
        )
        if full:
            f["changed"] = sh(
                "git", "-C", BARE, "diff", "--name-only", full, f["head"]
            ).splitlines()
        else:
            f["changed"] = ["(the leader %s is not in %s)" % (f["leader"], BARE)]
    return f


def paused():
    try:
        with open(PAUSED, encoding="utf-8") as fh:
            return fh.read().strip() or "paused"
    except OSError:
        return ""


def load():
    try:
        with open(STATE, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def save(st):
    with open(STATE + ".tmp", "w", encoding="utf-8") as fh:
        json.dump(st, fh, indent=1)
    os.replace(STATE + ".tmp", STATE)


def note():
    """Tell the site (machine_note.py), so a ship that failed or waits for a person is emailed."""
    py = os.path.join(REPO, ".venv", "bin", "python")
    if os.path.exists(py):
        subprocess.run(
            [py, "-X", "utf8", os.path.join(REPO, "studio", "machine_note.py")], capture_output=True
        )


def ship(head, log):
    def step(*cmd, cwd=None):
        log.write("$ %s\n" % " ".join(cmd))
        log.flush()
        r = subprocess.run(cmd, cwd=cwd, stdout=log, stderr=subprocess.STDOUT)
        if r.returncode:
            raise RuntimeError("%s exited %d" % (" ".join(cmd[:4]), r.returncode))

    mine = sh("git", "-C", BARE, "rev-parse", "refs/heads/" + BRANCH, check=False)
    # the branch moves forward only (update-ref checks the old value), and the tag release.py builds
    step("git", "-C", BARE, "update-ref", "refs/heads/" + BRANCH, head, *([mine] if mine else []))
    step("git", "-C", BARE, "tag", "-f", "studio-stable", head)
    # the checkout as push.sh moves it: it only mirrors the bare repo (.env, .venv are untracked)
    step("git", "fetch", "-q", "--force", "--tags", "origin", cwd=REPO)
    step("git", "checkout", "-q", "-f", "-B", BRANCH, "origin/" + BRANCH, cwd=REPO)
    got = sh("git", "rev-parse", "HEAD", cwd=REPO)
    if got != head:
        raise RuntimeError("the checkout is at %s, not %s" % (got[:12], head[:12]))
    step("bash", os.path.join(REPO, "studio", "serve.sh"), "release", cwd=REPO)
    h = health("http://127.0.0.1:%d/api/health" % PORT) or {}
    if h.get("release") != head[:12]:
        raise RuntimeError("the studio reports %s, expected %s" % (h.get("release"), head[:12]))
    pub = (health(PUBLIC) or {}).get("release")
    log.write("live: %s   studio.kitcut.ai: %s\n" % (h["release"], pub or "NOT REACHABLE"))
    return pub


def look(plan=False):
    st = load()
    now = int(time.time())
    f = facts()
    if f["head"]:
        st["seen"] = {f["head"]: (st.get("seen") or {}).get(f["head"], now)}  # only the head's
    action, why = decide(st, f, now)
    print("%s: %s" % (action, why))
    if plan:
        print(
            json.dumps(
                {k: v for k, v in f.items() if k != "changed"} | {"changed": len(f["changed"])}
            )
        )
        return action, 0
    before = (st.get("state"), st.get("why"))
    st.update(state=action, why=why, at=now, head=f["head"], leader=f["leader"])
    if action != "ship":
        save(st)
        if action in PROBLEMS and before != (action, why):
            note()
        return action, 0
    os.makedirs(LOGS, exist_ok=True)
    path = os.path.join(LOGS, "%s-%s.log" % (f["head"][:12], time.strftime("%Y%m%d-%H%M%S")))
    st.update(state="shipping", log=path)
    save(st)
    try:
        with open(path, "w", encoding="utf-8") as log:
            log.write("autoship %s: %s\n" % (time.strftime("%F %T"), why))
            log.write("%s\n" % sh("git", "-C", BARE, "log", "--format=%h %s", "-1", f["head"]))
            log.flush()
            pub = ship(f["head"], log)
        st.update(
            state="shipped",
            why="%s leads%s"
            % (
                f["head"][:12],
                "" if pub == f["head"][:12] else "; studio.kitcut.ai reports %s" % pub,
            ),
            failed=None,
        )
        code = 0
    except Exception as e:  # noqa: BLE001 -- whatever stopped it is the news
        st.update(state="failed", why=str(e)[:400], failed=f["head"], failed_why=str(e)[:200])
        code = 1
    st["at"] = int(time.time())
    save(st)
    print("%s: %s  (log: %s)" % (st["state"], st["why"], path))
    logs = sorted(os.listdir(LOGS), key=lambda n: os.path.getmtime(os.path.join(LOGS, n)))
    for old in logs[:-KEEP_LOGS]:
        os.remove(os.path.join(LOGS, old))
    note()
    return st["state"], code


def poked():
    try:
        return os.path.getmtime(POKE)
    except OSError:
        return 0


def run(sleep=time.sleep):
    """Look until there is nothing to wait for. The hook arrives the moment GitHub has the push,
    so the settle (and the sound machine, and the lock) is waited out here rather than until the
    next poll; and a hook that came while this was shipping is looked at before it stops (the
    path unit cannot start a unit that is already running)."""
    end = time.time() + LOOK_FOR
    while True:
        seen = poked()  # not compared with a clock: the kernel stamps files a little coarsely
        action, code = look()
        if time.time() > end or (action != "wait" and poked() == seen):
            return code
        sleep(LOOK_AGAIN if action == "wait" else 1)


def status():
    st = load()
    if not st:
        print("autoship: no look yet")
        return 0
    when = time.strftime("%F %T", time.localtime(st.get("at", 0)))
    print(
        "autoship: %s at %s: %s%s"
        % (st.get("state"), when, st.get("why"), "  (PAUSED: %s)" % paused() if paused() else "")
    )
    p = poked()
    print(
        "last hook from GitHub: %s"
        % (time.strftime("%F %T", time.localtime(p)) if p else "none yet")
    )
    if st.get("log") and os.path.exists(st["log"]):
        print("last ship's log: %s" % st["log"])
        with open(st["log"], encoding="utf-8", errors="replace") as fh:
            print("".join(fh.readlines()[-15:]).rstrip())
    return 1 if st.get("state") in PROBLEMS else 0


def summary():
    """The note's field (machine_note.py): what the site emails the owner about."""
    st = load()
    return {k: st.get(k) for k in ("state", "why", "at", "head", "leader")} | {
        "paused": paused() or None
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--plan", action="store_true", help="what a look would do now; changes nothing")
    ap.add_argument(
        "--status", action="store_true", help="the last decision and the last ship's log"
    )
    ap.add_argument("--forget", action="store_true", help="forget that the head failed")
    a = ap.parse_args()
    if a.forget:
        st = load()
        st.pop("failed", None)
        save(st)
        sys.exit(0)
    if a.plan:
        sys.exit(look(plan=True)[1])
    sys.exit(status() if a.status else run())
