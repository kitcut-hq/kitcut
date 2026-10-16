#!/usr/bin/env python
"""deploy/autoship.py, the ship that follows GitHub, in a home of its own: local git repositories
for GitHub, the machine's bare repo and its checkout, a stub studio, no network, seconds.

    python studio/test_autoship.py

Covers what it decides for each state it can find -- the head already leading, a burst of pushes
settling, the sound machine busy (KI-043) and the wait that ends, a deploy holding the lock, a
changed requirements file, a branch GitHub rewrote, a commit that failed, a pause (a rollback),
docs alone -- and then two real looks end to end: a commit pushed "to GitHub" is fetched
fast-forward into the bare repo, the checkout follows it, serve.sh release is run, and the studio
is asked which release leads; and a release that fails its tests is not tried again.
"""

import os
import sys
import json
import shutil
import tempfile
import threading
import subprocess
import http.server

T = tempfile.mkdtemp(prefix="studio-autoship-test-")
os.environ["STUDIO_HOME"] = os.path.join(T, "studio")
os.environ["STUDIO_REPO"] = os.path.join(T, "repo")
os.environ["STUDIO_GIT"] = os.path.join(T, "git")
os.environ["AUTOSHIP_URL"] = os.path.join(T, "github")
os.environ["AUTOSHIP_SETTLE_S"] = "0"
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "deploy"))

bad = []


def check(ok, what, got=None):
    print("%s  %s%s" % ("ok   " if ok else "FAIL ", what, "" if ok else "  -- %r" % (got,)))
    if not ok:
        bad.append(what)


def git(*a, cwd=None):
    return subprocess.run(
        ["git", *a], cwd=cwd, capture_output=True, text=True, check=True
    ).stdout.strip()


def decisions(autoship):
    head = "a" * 40
    base = {
        "head": head,
        "leader": "b" * 12,
        "ff": True,
        "changed": ["studio/server.py"],
        "cpu_busy": False,
        "locked": "",
        "paused": "",
    }
    now = 10_000
    old = {"seen": {head: now - 600}}

    def d(st=old, **kw):
        return autoship.decide(st, dict(base, **kw), now)[0]

    check(d() == "ship", "a new head, settled, nothing busy: ship")
    check(d(leader=head[:12]) == "idle", "the head already leads: nothing")
    check(d(head="") == "wait", "GitHub not answering: wait")
    check(d(leader="") == "wait", "the studio not answering: wait (a ship could not be proved)")
    check(d(st={"seen": {head: now - 5}}) == "ship", "SETTLE 0 here: a fresh head ships")
    autoship.SETTLE = 120
    check(
        d(st={"seen": {head: now - 5}}) == "wait",
        "a head seconds old waits for the pushes to settle",
    )
    check(d(st={}) == "wait", "a head never seen before waits")
    autoship.SETTLE = 0
    check(d(cpu_busy=True) == "wait", "the sound machine busy: wait (KI-043)")
    long_ago = {"seen": {head: now - autoship.MAX_WAIT - 1}}
    check(d(st=long_ago, cpu_busy=True) == "ship", "busy past MAX_WAIT: ship anyway")
    check(d(locked="pid 1, 'release'") == "wait", "another deploy holds deploy.lock: wait")
    check(
        d(changed=["studio/server.py", "requirements-studio.txt"]) == "hold",
        "a changed requirements file: hold for a person",
    )
    check(d(ff=False) == "refuse", "a rewritten branch on GitHub: refuse")
    check(d(st=dict(old, failed=head)) == "failed", "a head that failed: not tried again")
    check(d(st=dict(old, failed="c" * 40)) == "ship", "a new head after a failure: tried")
    check(d(paused="ops.sh rollback") == "idle", "paused (a rollback): nothing")
    check(
        d(changed=["docs/x.md", "README.md", "projects/p/journal.md"]) == "skip", "docs alone: skip"
    )
    check(d(changed=["studio/brief.md"]) == "ship", "a prompt the studio reads (studio/*.md): ship")
    check(d(changed=[".claude/skills/x/SKILL.md"]) == "ship", "a skill: ship")
    check(not autoship.docs_only([]), "nothing changed is not 'docs only'")


class Stub(http.server.BaseHTTPRequestHandler):
    release = ""

    def do_GET(self):
        try:  # what the stub serve.sh made lead
            with open(os.path.join(T, "leader"), encoding="utf-8") as f:
                Stub.release = f.read().strip()
        except OSError:
            pass
        b = json.dumps(
            {"release": Stub.release, "slots": {"cpu": {"used": 0, "peers": 0}}}
        ).encode()
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b)

    def log_message(self, *a):
        pass


def commit(work, name, text):
    os.makedirs(os.path.dirname(os.path.join(work, name)), exist_ok=True)
    with open(os.path.join(work, name), "w", encoding="utf-8") as f:
        f.write(text)
    git("add", "-A", cwd=work)
    git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", name, cwd=work)
    git("push", "-q", "origin", "HEAD:studio-poc", cwd=work)
    return git("rev-parse", "HEAD", cwd=work)


def end_to_end(autoship):
    srv = http.server.HTTPServer(("127.0.0.1", 0), Stub)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    autoship.PORT = srv.server_address[1]
    autoship.PUBLIC = "http://127.0.0.1:%d/api/health" % autoship.PORT
    gh, work = os.path.join(T, "github"), os.path.join(T, "work")
    git("init", "-q", "--bare", gh)
    git("clone", "-q", gh, work)
    os.makedirs(os.path.join(work, "studio"))
    # the stub serve.sh: "builds" the checkout's studio-stable and makes it lead, or fails
    with open(os.path.join(work, "studio", "serve.sh"), "w", newline="\n") as f:
        f.write(
            'set -e\n[ ! -f studio/FAIL ] || { echo "a test failed"; exit 1; }\n'
            "git rev-parse --short=12 studio-stable > %s/leader\n" % T.replace("\\", "/")
        )
    first = commit(work, "studio/server.py", "1")
    git("clone", "-q", "--bare", gh, os.environ["STUDIO_GIT"])
    git("clone", "-q", os.environ["STUDIO_GIT"], os.environ["STUDIO_REPO"])
    os.makedirs(os.environ["STUDIO_HOME"])
    Stub.release = first[:12]

    def look():
        return autoship.look()[1], autoship.load()

    code, st = look()
    check(st.get("state") == "idle", "the head leads already: idle", st)
    second = commit(work, "studio/server.py", "2")
    code, st = look()
    check(code == 0 and st.get("state") == "shipped", "a pushed commit is shipped", st)
    check(Stub.release == second[:12], "and it leads", Stub.release)
    bare = git("rev-parse", "refs/heads/studio-poc", cwd=os.environ["STUDIO_GIT"])
    check(bare == second, "the bare repo's branch moved to it", bare)
    check(
        git("rev-parse", "HEAD", cwd=os.environ["STUDIO_REPO"]) == second,
        "the checkout followed it",
    )
    check(os.path.exists(st.get("log") or ""), "the ship's log is kept", st.get("log"))
    commit(work, "docs/notes.md", "x")
    code, st = look()
    check(st.get("state") == "skip", "a docs-only commit is not shipped", st)
    third = commit(work, "studio/FAIL", "x")
    code, st = look()
    check(code == 1 and st.get("state") == "failed", "a release that fails its tests: failed", st)
    check(st.get("failed") == third, "and remembered", st.get("failed"))
    code, st = look()
    check(st.get("state") == "failed", "the next look does not try it again", st)
    with open(os.path.join(os.environ["STUDIO_HOME"], "autoship.paused"), "w") as f:
        f.write("ops.sh rollback")
    fourth = commit(work, "studio/server.py", "4")
    os.remove(os.path.join(work, "studio", "FAIL"))
    code, st = look()
    check(st.get("state") == "idle" and Stub.release != fourth[:12], "paused: nothing ships", st)
    os.remove(os.path.join(os.environ["STUDIO_HOME"], "autoship.paused"))
    git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qam", "unfail", cwd=work)
    git("push", "-q", "origin", "HEAD:studio-poc", cwd=work)
    code, st = look()
    check(st.get("state") == "shipped", "the pause lifted, a fixed commit ships", st)
    # GitHub's branch rewritten: never followed backwards
    git("push", "-q", "-f", "origin", first + ":refs/heads/studio-poc", cwd=work)
    code, st = look()
    check(st.get("state") == "refuse", "a rewritten branch is refused", st)
    srv.shutdown()


def looks_again(autoship):
    """run(): a hook arrives while the head is settling, so the wait is looked at again here
    rather than at the next poll; and a hook that came during a ship gets one more look."""
    seq, slept = [], []

    def fake(actions):
        it = iter(actions)

        def look():
            a = next(it)
            seq.append(a)
            if a == "ship-poked":  # a hook lands while this look ships
                with open(autoship.POKE, "w") as f:
                    f.write("x")
                return "shipped", 0
            return a, 1 if a == "failed" else 0

        return look

    real = autoship.look
    try:
        autoship.look = fake(["wait", "wait", "shipped"])
        code = autoship.run(sleep=slept.append)
        check(seq == ["wait", "wait", "shipped"] and code == 0, "waits are looked at again", seq)
        check(slept == [autoship.LOOK_AGAIN] * 2, "every LOOK_AGAIN seconds", slept)
        seq.clear()
        autoship.look = fake(["ship-poked", "idle"])
        autoship.run(sleep=slept.append)
        check(seq == ["ship-poked", "idle"], "a hook during a ship: one more look", seq)
        seq.clear()
        autoship.look = fake(["failed"])
        check(autoship.run(sleep=slept.append) == 1 and seq == ["failed"], "a failure ends it")
        seq.clear()
        autoship.LOOK_FOR = -1
        autoship.look = fake(["wait"])
        autoship.run(sleep=slept.append)
        check(seq == ["wait"], "never past LOOK_FOR: then the poll takes over", seq)
    finally:
        autoship.look = real


if __name__ == "__main__":
    try:
        import autoship  # noqa: E402

        decisions(autoship)
        end_to_end(autoship)
        looks_again(autoship)
    finally:
        shutil.rmtree(T, ignore_errors=True)
    print("%s" % ("all passed" if not bad else "%d FAILED: %s" % (len(bad), "; ".join(bad))))
    sys.exit(1 if bad else 0)
