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

    async def acquire(self, weight=1, who="", on_wait=None, priority=0):
        """Wait for `weight` slots. Returns the seconds spent waiting."""
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
                while not (self.waiting[0] is ticket and self.used + weight <= self.capacity):
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
        return {"capacity": self.capacity, "used": self.used, "waiting": len(self.waiting)}


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
