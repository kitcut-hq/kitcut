"""What a run is doing right now, in the database: a film being made, or a round of changes.

The page a person watches asks the site, and the site asks this studio. But the studio is one
machine behind a tunnel: while it restarts, ships a release or loses its connection, the site
has only the run's document in kitcut.studio_runs to go by -- and that said "running" and
nothing more, so the page went blind exactly when its person most wanted to know. So every run
keeps there, as it goes:

    now      the sentence the page shows under the film: its stage ("Mixing the soundtrack"), or
             what it is waiting for ("Waiting for a free studio: 2 films ahead")
    now_at   when that was last true (a Date): written again every BEAT_S while the run lives,
             so a reader can tell a run that is thinking from one whose server is gone
    stage    the stage's name (queue, claude, sound, render, online ...), for a film
    ahead    the films ahead of it in the line for Claude, while it waits there; else None

The log itself (every tool, every line Claude says) stays the studio's: this is the one line.

A change is written at once; nothing is written twice. One write is in flight per run at a
time, and what changed meanwhile goes in the next, so the database never sees an older line
after a newer one. A write that fails is dropped (the next carries everything): a status is
never the reason a film fails.
"""

import time
import asyncio
import contextlib

import store

BEAT_S = 30  # how often a living run says it still is
RUNS = {}  # run id -> Now


class Now:
    def __init__(self, run_id, save):
        self.id, self._save = run_id, save  # save(run_id, fields): the store's, off the loop
        self.fields = {"now": None, "stage": None, "ahead": None}
        self._stage_text, self._wait = None, None
        self._dirty, self._task, self._over = False, None, False
        self._sent = 0.0

    # ---------------------------------------------------------------- what the run reports
    def event(self, ev):
        """One of a film's events (server.start's emit): the stage it names, or its wait."""
        kind = ev.get("type")
        if kind == "stage":
            self._stage_text, self._wait = ev.get("text"), None
            self.set(stage=ev.get("name"), ahead=None)
        elif kind == "wait":
            self._wait = ev.get("text")
            self.set(ahead=ev.get("ahead") if ev.get("pool") == "claude" else None)
        elif kind in ("tool", "say") and self._wait:  # it has its slot again: back to its stage
            self._wait = None
            self.set(ahead=None)

    def say(self, text, **more):
        """The line as a sentence of the caller's own (a round's)."""
        self._stage_text, self._wait = text, None
        self.set(**more)

    def set(self, **more):
        was = dict(self.fields)
        self.fields.update(more)
        self.fields["now"] = self._wait or self._stage_text
        if self.fields != was:
            self._kick()

    def end(self):
        """The run is over: its line goes (its record's final state says the rest)."""
        self._over = True
        self.fields = {"now": None, "stage": None, "ahead": None}
        self._kick()
        RUNS.pop(self.id, None)

    # ---------------------------------------------------------------- writing
    def _kick(self):
        self._dirty = True
        if self._task is None or self._task.done():
            with contextlib.suppress(RuntimeError):  # no loop (a script): nothing to tell
                self._task = asyncio.get_running_loop().create_task(self._run())

    async def _run(self):
        while True:
            if self._dirty or (not self._over and time.time() - self._sent >= BEAT_S):
                self._dirty = False
                doc = dict(self.fields, now_at=None if self._over else store.now())
                with contextlib.suppress(Exception):
                    await asyncio.to_thread(self._save, self.id, doc)
                self._sent = time.time()
                continue
            if self._over:
                return
            await asyncio.sleep(1)


def of(run_id, save):
    """This run's line (made on first use)."""
    if run_id not in RUNS:
        RUNS[run_id] = Now(run_id, save)
    return RUNS[run_id]


async def stop_all():
    """The server is stopping: nothing more is said for its runs (their records say where they
    stand; the next server's own lines follow)."""
    tasks = [n._task for n in RUNS.values() if n._task is not None and not n._task.done()]
    for t in tasks:
        t.cancel()
    RUNS.clear()
    if tasks:
        await asyncio.wait(tasks, timeout=5)
