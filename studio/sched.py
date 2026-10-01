"""Who gets the machine next: first-come, first-served pools with weights.

Several films are made at once. Their Claude sessions mostly wait on the API, but what they ask
the machine to do does not share well: a headless browser per still and three for a final render,
the Whisper model on the CPU, ffmpeg. So each of those holds a slot in a pool while it runs:

    claude    3   a film's whole Claude phase (the API; more at once only costs money faster)
    browser   4   review stills take 1, the final render 3 (sketch-render --jobs 3)
    cpu       2   the voice (Whisper) and the soundtrack mix

A pool is strictly first come, first served: a request that does not fit yet (the render's 3)
blocks the ones behind it, so small requests can never starve a big one. The one exception is
priority: a film of a plan with priority (the site's X-Priority: 1) joins the line ahead of every
film without it -- behind other priority films, first come first served among them. Whoever waits is told
where it stands (on_wait), and the page shows "waiting for the renderer -- 1 film ahead".
Pools are only ever taken in the order browser -> cpu, and nothing waits for a claude slot while
holding another, so no two films can deadlock.

Two servers, one machine. During a ship the new release runs beside the old one, which finishes
its films (peers.py; a ship that restarted the studio killed a paying film: docs/known-issues.md
KI-031). Each has its own pools, but the browsers and the CPU are the machine's, so a pool also
counts what the other servers hold (set_peers, fed from their heartbeats by the server):

    peer_used   slots the other live servers hold now
    peer_want   what the first waiter of each OLDER server wants (0: none waiting)

A request goes in when it is first in line and used + peer_used + peer_want + weight fits. Wants
count one way only, older first: the old server's final render (3 browsers) is never starved by
the new one taking a browser at a time, and since a server only ever waits on older ones' wants,
two servers can never wait on each other. The counts come from heartbeats, so for a moment after
a change both may take a slot the other has just taken: the machine is briefly over, never stuck.

Clock: time a film spends waiting for a pool does not count against its Claude time limit.
"""

import os
import time
import asyncio
import contextlib

LABELS = {"claude": "a free studio", "browser": "the renderer", "cpu": "the sound machine"}


class Pool:
    def __init__(self, name, capacity):
        self.name, self.capacity, self.used = name, max(1, int(capacity)), 0
        self.waiting = []  # tickets, in arrival order
        # the other servers on this machine (set_peers): what they hold, and what the first
        # waiter of each older one wants
        self.peer_used, self.peer_want = 0, 0
        self._cond = None

    @property
    def cond(self):
        if self._cond is None:  # made on first use, inside the running loop
            self._cond = asyncio.Condition()
        return self._cond

    def ahead(self, who):
        """How many are queued before `who` (0 when it is next, None when it is not waiting)."""
        for i, t in enumerate(self.waiting):
            if t[1] == who:
                return i
        return None

    def head_want(self):
        """The weight the first in line waits for (0 when nobody waits): what this server tells
        the newer ones to leave free."""
        return self.waiting[0][0] if self.waiting else 0

    def fits(self, weight):
        return self.used + self.peer_used + self.peer_want + weight <= self.capacity

    async def set_peers(self, used=0, want=0):
        """What the other servers hold and (the older ones) want, from their heartbeats. Every
        call wakes the line: slots a peer gives back must reach a waiter here at once, or a
        waiter that went to sleep while the machine was full would sleep until a local release."""
        used, want = max(0, int(used or 0)), max(0, int(want or 0))
        async with self.cond:
            self.peer_used, self.peer_want = used, want
            self.cond.notify_all()

    async def acquire(self, weight=1, who="", on_wait=None, priority=0):
        """Wait for `weight` slots, and for the machine to have them (the peers' counts). More
        than the pool has is the whole pool: it waits until nothing else holds any. Returns the
        seconds spent waiting."""
        weight = min(max(1, weight), self.capacity)
        ticket = (weight, who, object(), priority)
        t0, told = time.time(), None
        async with self.cond:
            # behind everyone of the same or a higher priority, ahead of everyone lower
            i = len(self.waiting)
            while i and self.waiting[i - 1][3] < priority:
                i -= 1
            self.waiting.insert(i, ticket)
            try:
                while not (self.waiting[0] is ticket and self.fits(weight)):
                    n = self.waiting.index(ticket)
                    if on_wait and n != told:
                        told = n
                        on_wait(self.name, n)
                    await self.cond.wait()
                self.waiting.pop(0)
                self.used += weight
            except BaseException:  # cancelled while waiting: leave the line, let others move up
                if ticket in self.waiting:
                    self.waiting.remove(ticket)
                self.cond.notify_all()
                raise
            self.cond.notify_all()  # the next in line may fit too
        return time.time() - t0

    async def release(self, weight=1):
        weight = min(max(1, weight), self.capacity)
        async with self.cond:
            self.used = max(0, self.used - weight)
            self.cond.notify_all()

    @contextlib.asynccontextmanager
    async def hold(self, weight=1, who="", on_wait=None, clock=None, priority=0):
        waited = await self.acquire(weight, who, on_wait, priority)
        if clock is not None:
            clock.paused += waited
        try:
            yield waited
        finally:
            # shielded: a cancelled film must still give its slot back
            await asyncio.shield(self.release(weight))

    def snapshot(self):
        return {
            "capacity": self.capacity,
            "used": self.used,
            "waiting": len(self.waiting),
            "peers": self.peer_used,  # held by the other servers on this machine
        }


class Sched:
    def __init__(self, claude=None, browser=None, cpu=None):
        env = lambda k, d: int(os.environ.get(k) or d)  # noqa: E731
        self.pools = {
            "claude": Pool("claude", claude or env("STUDIO_PARALLEL", 3)),
            "browser": Pool("browser", browser or env("STUDIO_BROWSERS", 4)),
            "cpu": Pool("cpu", cpu or env("STUDIO_CPU_SLOTS", 2)),
        }

    def __getitem__(self, name):
        return self.pools[name]

    def snapshot(self):
        return {k: p.snapshot() for k, p in self.pools.items()}

    def usage(self):
        """What this server holds and its first waiters want, pool by pool, for its heartbeat
        (peers.heartbeat slots): {pool: {"used": n, "want": n}}."""
        return {k: {"used": p.used, "want": p.head_want()} for k, p in self.pools.items()}

    async def set_peers(self, peers):
        """The other servers' counts, {pool: {"used": u, "want": w}}: used summed over every live
        peer, want over the peers that started before this one only (older first; the module
        docstring says why). A pool missing from it has no peers (0)."""
        peers = peers or {}
        for k, p in self.pools.items():
            got = peers.get(k) or {}
            await p.set_peers(got.get("used", 0), got.get("want", 0))


class Clock:
    """A film's Claude time: wall time minus what it spent waiting for the machine."""

    def __init__(self):
        self.t0, self.paused = time.time(), 0.0

    def active(self):
        return time.time() - self.t0 - self.paused

    def wall(self):
        return time.time() - self.t0


def waiting_text(pool, ahead):
    what = LABELS.get(pool, pool)
    if ahead:
        return "Waiting for %s -- %d film%s ahead" % (what, ahead, "" if ahead == 1 else "s")
    return "Waiting for %s" % what
