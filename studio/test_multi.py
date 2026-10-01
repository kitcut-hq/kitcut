#!/usr/bin/env python
"""Two studio servers on one home, in a few seconds: python studio/test_multi.py

What peers.py and locks.py promise, checked across real processes (a child is this file run with
--child): a live server's lock is held and a dead one's is not, however it died; heartbeats are
seen; one server leads at a time and the lead passes when the leader goes; `current` names the
successor once it serves; a Stop for another's film is taken once; a critical section under
locks.locked() loses no update when two processes race through it; and the dead's files are reaped
only when they are old. A throwaway STUDIO_HOME, removed at the end. release.py runs this before a
release goes current, so the VM proves it on its own kernel.
"""

import os
import sys
import json
import time
import shutil
import tempfile
import subprocess

if "--child" not in sys.argv:
    os.environ["STUDIO_HOME"] = tempfile.mkdtemp(prefix="studio-multi-")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import locks  # noqa: E402
import peers  # noqa: E402

HERE = os.path.abspath(__file__)


def child(what, arg):
    """A second server, as far as peers.py can tell: its own process, its own id."""
    if what == "serve":  # hold its lock, beat as `arg` mode, lead if it can, wait to be killed
        peers.hold_own()
        lead = peers.try_lead()
        peers.heartbeat(arg, leader=lead, jobs=[{"id": "f1", "client": "u:a", "status": "running"}])
        print(json.dumps({"id": peers.SERVER_ID, "leader": lead}), flush=True)
        while True:
            time.sleep(1)
    elif what == "count":  # add 1 to a counter file `arg` times, under the lock
        path = os.path.join(peers.HOME, "counter")
        for _ in range(int(arg)):
            with locks.locked(path + ".lock"):
                n = int(open(path).read()) if os.path.exists(path) else 0
                with open(path, "w") as f:
                    f.write(str(n + 1))
        print("{}", flush=True)


def spawn(what, arg, instance="old"):
    env = dict(os.environ, STUDIO_INSTANCE=instance)
    p = subprocess.Popen(
        [sys.executable, HERE, "--child", what, str(arg)],
        env=env,
        stdout=subprocess.PIPE,
        text=True,
    )
    return p, json.loads(p.stdout.readline())


def main():
    bad = []

    def expect(what, ok):
        print("%s  %s" % ("ok  " if ok else "FAIL", what))
        if not ok:
            bad.append(what)

    peers.hold_own()
    expect("this process is alive to itself", peers.alive(peers.SERVER_ID))
    expect("no one is dead by default: an unknown id is not alive", not peers.alive("x.1"))
    expect("with no current file every server is current", peers.is_current())

    old, said = spawn("serve", "serving", "old")
    expect("the other server's lock is held: alive", peers.alive(said["id"]))
    expect("it took the lead (nobody had it)", said["leader"] and not peers.try_lead())
    seen = peers.peers()
    expect(
        "its heartbeat is seen, with its films",
        [b["id"] for b in seen] == [said["id"]] and seen[0]["jobs"][0]["id"] == "f1",
    )
    expect("a film it owns has a live owner", peers.owner_alive({"server": said["id"]}))
    expect("a film with no owner has none", not peers.owner_alive({}))

    peers.set_current("new")
    expect("current names another instance: this one is not current", not peers.is_current())
    expect("no successor until it serves", peers.successor() is None)
    new, nsaid = spawn("serve", "serving", "new")
    expect(
        "the current instance serving is the successor",
        (peers.successor() or {}).get("id") == nsaid["id"] and not nsaid["leader"],
    )

    peers.request_cancel("f1", by="u:a")
    expect("a Stop for another's film is flagged", peers.cancel_requested("f1"))
    expect("its owner takes it once", peers.take_cancels(["f1", "f2"]) == ["f1"])
    expect("and then it is gone", peers.take_cancels(["f1"]) == [])

    old.kill()  # a hard kill: no leave(), no cleanup, as a crash or SIGKILL
    old.wait()
    time.sleep(0.2)
    expect("a killed server is dead, its files left behind", not peers.alive(said["id"]))
    expect("its heartbeat is no longer a peer's", [b["id"] for b in peers.peers()] == [nsaid["id"]])
    expect("the lead is free when the leader dies", peers.try_lead() and peers.leads())
    peers.resign()
    expect("and free again once let go", not peers.leads() and peers.try_lead())
    peers.resign()

    peers.reap()
    left = sorted(os.listdir(peers.DIR))
    expect(
        "a dead server's young files are not reaped yet (it may be starting)",
        said["id"] + ".json" in left,
    )
    for name in (said["id"] + ".json", said["id"] + ".lock"):
        p = os.path.join(peers.DIR, name)
        os.utime(p, (time.time() - 3600,) * 2)
    peers.reap()
    left = sorted(os.listdir(peers.DIR))
    expect(
        "old ones are, and the live servers' are kept",
        not any(n.startswith(said["id"]) for n in left)
        and nsaid["id"] + ".lock" in left
        and peers.SERVER_ID + ".lock" in left,
    )
    new.kill()
    new.wait()

    runs = [
        subprocess.Popen(
            [sys.executable, HERE, "--child", "count", "150"], stdout=subprocess.PIPE, text=True
        )
        for _ in range(3)
    ]
    for p in runs:
        p.communicate()
    with open(os.path.join(peers.HOME, "counter")) as f:
        n = int(f.read())
    expect("three processes, 150 locked updates each: none lost (%d)" % n, n == 450)

    t0 = time.monotonic()
    with locks.locked(os.path.join(peers.HOME, "held.lock")):
        try:
            with locks.locked(os.path.join(peers.HOME, "held.lock"), timeout=0.2):
                took = False
        except locks.LockTimeout:
            took = True
    expect("a lock held elsewhere times out, not forever", took and time.monotonic() - t0 < 2)

    peers.leave()
    expect(
        "leaving removes this server's files", not os.path.exists(peers._beat_path(peers.SERVER_ID))
    )
    print("%d failed" % len(bad))
    return 1 if bad else 0


if __name__ == "__main__":
    if "--child" in sys.argv:
        i = sys.argv.index("--child")
        child(sys.argv[i + 1], sys.argv[i + 2])
        sys.exit(0)
    try:
        code = main()
    finally:
        shutil.rmtree(os.environ["STUDIO_HOME"], ignore_errors=True)
    sys.exit(code)
