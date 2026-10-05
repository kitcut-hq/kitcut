"""Several studio servers on one STUDIO_HOME: who is alive, who leads, who owns a film.

A ship starts the new release as a server of its own (systemd kitcut-studio@<instance>) beside the
one already running. The new one takes the new films; the old one finishes the films it is making,
then exits. Nothing waits and nothing is killed (a ship on 2026-09-28 killed a paying film 28
minutes in: docs/known-issues.md KI-031). The two share the home and nothing else, so what each
needs to know about the other is on disk, under HOME/servers/:

    <id>.lock        held (locks.try_lock) by the live process <id> for its whole life. The kernel
                     lets go when the process dies, however it dies, so "alive" is "that lock is
                     taken" -- never a timestamp, which a stalled event loop would fail
    <id>.json        its heartbeat, rewritten every tick (heartbeat() documents the fields); only
                     written once <id>.lock is held
    current          the instance that should serve: the intent (serve.sh switch writes it)
    leader.lock      held by the one server that admits films and adopts what others left: the
                     fact. current names who should take it; the old leader lets go when it sees
                     the instance current names serving
    cancel/<film>    a Stop for a film another server is making; its owner picks it up

A server's id is "<instance>.<pid>": an instance name comes back after a crash restart or a
reboot, a pid does not within a boot, so a server never mistakes a dead one's films for its own.
A film's record (studio.json "server") names the id of the server making it.

With no `current` file (the laptop, a dev server, one server alone) every server is current and
the first one leads: nothing changes for a single server.
"""

import os
import json
import time
import contextlib
from datetime import datetime

import locks
from film import HOME, RELEASE

DIR = os.path.join(HOME, "servers")
CANCELS = os.path.join(DIR, "cancel")
CURRENT = os.path.join(DIR, "current")
LEADER = os.path.join(DIR, "leader.lock")

# kitcut-studio@<instance> (the unit) sets it; a server started by hand is "dev"
INSTANCE = os.environ.get("STUDIO_INSTANCE", "").strip() or "dev"
SERVER_ID = "%s.%d" % (INSTANCE, os.getpid())
STARTED = datetime.now().isoformat(timespec="seconds")
MODES = ("starting", "serving", "handed_off", "stopping")

_own = [None]  # this process's <id>.lock handle, held for its whole life
_lead = [None]  # leader.lock's handle while this process leads


def _lock_path(sid):
    return os.path.join(DIR, sid + ".lock")


def _beat_path(sid):
    return os.path.join(DIR, sid + ".json")


def _write(path, data):
    """Atomically (a reader never sees half a file); one temp file per writer."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = "%s.%d.tmp" % (path, os.getpid())
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, default=str)
    for i in range(20):  # Windows refuses the rename for a moment while a reader has it open
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            time.sleep(0.02 * (i + 1))
    os.replace(tmp, path)


def _read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


# ------------------------------------------------------------------ this process
def hold_own():
    """Take this process's own lock: from now on it is alive to every other server. Once, first
    thing, before any heartbeat."""
    if _own[0] is None:
        for _ in range(100):  # another server's alive() may hold it for an instant
            _own[0] = locks.try_lock(_lock_path(SERVER_ID))
            if _own[0] is not None:
                break
            time.sleep(0.02)
        else:
            raise RuntimeError("%s is held by another process" % _lock_path(SERVER_ID))
    return SERVER_ID


def heartbeat(
    mode,
    leader=False,
    jobs=(),
    slots=None,
    sends=(),
    drafts=(),
    transcribing=(),
    unbrands=(),
    rounds=(),
):
    """Tell the other servers what this one is doing, in <id>.json:

    id, instance, pid, release, started, updated (epoch s),
    mode          starting | serving (listening on the port) | handed_off (another serves; this
                  one only finishes its films) | stopping
    leader        whether it holds leader.lock
    jobs          [{"id", "client", "status": "queued"|"running", "reserve", "cost_usd"}]: the
                  films it is making (server.JOBS), for the others' per-account, queue and budget
                  limits
    slots         {pool: {"used": n, "want": n}}: machine slots held, and the weight its first
                  waiting step wants (0: none waiting) -- sched.Pool counts both (peer capacity)
    sends         YouTube sends in flight (youtube.SENDS keys); drafts: ytdraft.JOBS keys;
    transcribing  upload ids whose voice note is being transcribed (uploads.TASKS)
    unbrands      the films it is drawing again without their branding (unbrand.JOBS)
    rounds        the films whose next version it is making from their maker's notes (rounds.JOBS)
    """
    assert mode in MODES, mode
    hold_own()
    _write(
        _beat_path(SERVER_ID),
        {
            "id": SERVER_ID,
            "instance": INSTANCE,
            "pid": os.getpid(),
            "release": RELEASE,
            "started": STARTED,
            "updated": time.time(),
            "mode": mode,
            "leader": bool(leader),
            "jobs": list(jobs),
            "slots": slots or {},
            "sends": list(sends),
            "drafts": list(drafts),
            "transcribing": list(transcribing),
            "unbrands": list(unbrands),
            "rounds": list(rounds),
        },
    )


def leave():
    """This process is exiting: its heartbeat goes, then its locks (the kernel would free them)."""
    resign()
    with contextlib.suppress(OSError):
        os.remove(_beat_path(SERVER_ID))
    locks.unlock(_own[0])
    _own[0] = None
    with contextlib.suppress(OSError):
        os.remove(_lock_path(SERVER_ID))


# ------------------------------------------------------------------ the others
def alive(sid):
    """Is server `sid` running? Its lock is held. A missing lock file, or one this process can
    take, is a dead server."""
    if not sid:
        return False
    if sid == SERVER_ID:
        return True
    path = _lock_path(sid)
    if not os.path.exists(path):
        return False
    h = locks.try_lock(path)
    if h is None:
        return True
    locks.unlock(h)
    return False


def peers():
    """The other live servers' heartbeats, oldest first (by the time each started)."""
    out = []
    with contextlib.suppress(OSError):
        for name in os.listdir(DIR):
            if not name.endswith(".json") or name[:-5] == SERVER_ID:
                continue
            b = _read(os.path.join(DIR, name))
            if b and alive(b.get("id")):
                out.append(b)
    return sorted(out, key=lambda b: (b.get("started") or "", b.get("pid") or 0))


def owner_alive(rec):
    """Is the server named in a film's record (studio.json "server") still running -- this one
    included? A film with no owner, or a dead one's, is the leader's to adopt."""
    return alive((rec or {}).get("server"))


REAP_AFTER_S = 60  # a younger file may be a server that created its lock and has yet to take it


def reap():
    """Remove the files dead servers left (the leader, now and then). Never touches a live one's,
    nor one younger than REAP_AFTER_S."""
    now = time.time()
    with contextlib.suppress(OSError):
        for name in os.listdir(DIR):
            sid, ext = os.path.splitext(name)
            if ext not in (".json", ".lock") or sid == "leader" or sid == SERVER_ID:
                continue
            path = os.path.join(DIR, name)
            with contextlib.suppress(OSError):
                if now - os.path.getmtime(path) > REAP_AFTER_S and not alive(sid):
                    os.remove(path)


# ------------------------------------------------------------------ who serves, who leads
def current():
    """The instance serve.sh made current, or None (no file: every server is current)."""
    try:
        with open(CURRENT, encoding="utf-8") as f:
            return f.read().strip() or None
    except OSError:
        return None


def is_current():
    c = current()
    return c is None or c == INSTANCE


def set_current(instance):
    """Make `instance` the one that should serve (serve.sh switch does this from the shell)."""
    os.makedirs(DIR, exist_ok=True)
    tmp = "%s.%d.tmp" % (CURRENT, os.getpid())
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(instance + "\n")
    os.replace(tmp, CURRENT)


def successor():
    """The live server of the current instance, other than this one, once it is serving: the
    one this server hands over to. None while there is none (or this one is current)."""
    c = current()
    if c is None or c == INSTANCE:
        return None
    for b in peers():
        if b.get("instance") == c and b.get("mode") == "serving":
            return b
    return None


def try_lead():
    """Take leader.lock if nobody holds it. True while this process leads."""
    if _lead[0] is None:
        _lead[0] = locks.try_lock(LEADER)
    return _lead[0] is not None


def leads():
    return _lead[0] is not None


def resign():
    """Let go of leader.lock (a server handing over, or exiting)."""
    locks.unlock(_lead[0])
    _lead[0] = None


# ------------------------------------------------------------------ a Stop for another's film
def request_cancel(film_id, by=None):
    """Ask whichever server is making `film_id` to stop it (its person pressed Stop on a page
    another server answered). The asker has checked who may; the owner only obeys."""
    _write(os.path.join(CANCELS, film_id), {"by": by, "at": time.time(), "from": SERVER_ID})


def cancel_requested(film_id):
    return os.path.exists(os.path.join(CANCELS, film_id))


def take_cancels(film_ids):
    """Of `film_ids` (the films this server is making), those someone asked to stop -- each flag
    removed as it is taken, so it is obeyed once."""
    out = []
    for fid in film_ids:
        p = os.path.join(CANCELS, fid)
        if os.path.exists(p):
            with contextlib.suppress(OSError):
                os.remove(p)
            out.append(fid)
    return out


def drop_cancel(film_id):
    """Forget a flag for a film that is over anyway (the leader, adopting a dead server's film
    someone had asked to stop, records it cancelled and drops the flag)."""
    with contextlib.suppress(OSError):
        os.remove(os.path.join(CANCELS, film_id))
