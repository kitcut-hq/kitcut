#!/usr/bin/env python
"""The scheduler's pools, checked in a few seconds: python studio/test_sched.py

First come, first served with weights (a big request is never starved by small ones behind it),
waiters told where they stand, a cancelled waiter leaving the line, a cancelled holder giving its
slots back, and waiting time kept off a film's clock.
"""

import os
import sys
import asyncio

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sched import Clock, Pool, Sched  # noqa: E402


async def main():
    bad = []

    def expect(what, ok):
        print("%s  %s" % ("ok  " if ok else "FAIL", what))
        if not ok:
            bad.append(what)

    order = []
    p = Pool("browser", 4)

    async def job(name, weight, hold_for, told=None):
        async with p.hold(
            weight, name, (lambda pool, n: told.append(n)) if told is not None else None
        ):
            order.append(name)
            await asyncio.sleep(hold_for)

    # a still holds 1; a render asks for 4 and waits; a second still arrives after the render and
    # must NOT slip past it even though one slot is free
    told = []
    a = asyncio.create_task(job("still-1", 1, 0.3))
    await asyncio.sleep(0.02)
    b = asyncio.create_task(job("render", 4, 0.2))
    await asyncio.sleep(0.02)
    c = asyncio.create_task(job("still-2", 1, 0.05, told))
    await asyncio.sleep(0.02)
    expect("the render waits behind the still", order == ["still-1"])
    expect("the second still is told it is 1 behind", told == [1])
    await asyncio.gather(a, b, c)
    expect("first come, first served: %s" % order, order == ["still-1", "render", "still-2"])
    expect("every slot is back", p.used == 0 and not p.waiting)

    # a waiter that is cancelled leaves the line, and the one behind it moves up
    order.clear()
    a = asyncio.create_task(job("holder", 4, 0.2))
    await asyncio.sleep(0.02)
    b = asyncio.create_task(job("gives-up", 2, 0.01))
    await asyncio.sleep(0.02)
    c = asyncio.create_task(job("patient", 2, 0.01))
    await asyncio.sleep(0.02)
    expect("two wait", len(p.waiting) == 2 and p.ahead("patient") == 1)
    b.cancel()
    await asyncio.sleep(0.02)
    expect(
        "the cancelled waiter left the line",
        p.ahead("gives-up") is None and p.ahead("patient") == 0,
    )
    await asyncio.gather(a, c, return_exceptions=True)
    expect("the patient one ran: %s" % order, order == ["holder", "patient"])

    # a holder that is cancelled gives its slots back
    a = asyncio.create_task(job("doomed", 3, 10))
    await asyncio.sleep(0.02)
    expect("it holds 3", p.used == 3)
    a.cancel()
    await asyncio.gather(a, return_exceptions=True)
    await asyncio.sleep(0.02)
    expect("cancelled, it gave them back", p.used == 0)

    # waiting for the machine is not the film's time
    clock = Clock()
    q = Pool("cpu", 1)

    async def hog():
        async with q.hold(1, "hog"):
            await asyncio.sleep(0.4)

    h = asyncio.create_task(hog())
    await asyncio.sleep(0.02)
    async with q.hold(1, "film", clock=clock):
        pass
    await h
    expect(
        "the wait was kept off the clock (%.2f s paused)" % clock.paused,
        clock.paused > 0.3 and clock.active() < clock.wall() - 0.3,
    )

    s = Sched(claude=2, browser=4, cpu=2)
    expect(
        "the default pools",
        sorted(s.snapshot()) == ["browser", "claude", "cpu"] and s["claude"].capacity == 2,
    )
    print("%d failed" % len(bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
