#!/usr/bin/env python
"""The scheduler's pools, checked in a few seconds: python studio/test_sched.py

First come, first served with weights (a big request is never starved by small ones behind it),
waiters told where they stand, a cancelled waiter leaving the line, a cancelled holder giving its
slots back, and waiting time kept off a film's clock. Then two servers on one machine (KI-031):
the peers' slots counted, a waiter woken when they free up, an older server's want respected,
and the old server's final render getting through while a new one takes stills.
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

    # priority: ahead of everyone without it, first come first served among its own
    order.clear()
    one = Pool("claude", 1)

    async def film(name, prio, hold_for=0.02):
        async with one.hold(1, name, priority=prio):
            order.append(name)
            await asyncio.sleep(hold_for)

    busy = asyncio.create_task(film("running", 0, 0.3))  # holds the slot while the others line up
    await asyncio.sleep(0.01)
    tasks = []
    for name, prio in (("free-1", 0), ("free-2", 0), ("pro-1", 1), ("pro-2", 1), ("free-3", 0)):
        tasks.append(asyncio.create_task(film(name, prio)))
        await asyncio.sleep(0.005)
    expect("a pro film is told it is 1 ahead of the others' line", one.ahead("pro-2") == 1)
    await asyncio.gather(busy, *tasks)
    expect(
        "priority first, then first come first served: %s" % order,
        order == ["running", "pro-1", "pro-2", "free-1", "free-2", "free-3"],
    )

    s = Sched(claude=2, browser=4, cpu=2)
    expect(
        "the default pools",
        sorted(s.snapshot()) == ["browser", "claude", "cpu"] and s["claude"].capacity == 2,
    )

    await peers(expect)
    print("%d failed" % len(bad))
    return 1 if bad else 0


async def peers(expect):
    """Two servers on one machine (KI-031): a pool counts what the others hold, and what the
    older ones' first waiters want."""
    order = []
    p = Pool("browser", 4)

    async def job(name, weight, hold_for=0.02, pool=None):
        async with (pool or p).hold(weight, name):
            order.append(name)
            await asyncio.sleep(hold_for)

    # the peers hold 3 of the 4 browsers: a request for 2 waits, and goes in when they let go
    await p.set_peers(3, 0)
    a = asyncio.create_task(job("render-2", 2))
    await asyncio.sleep(0.03)
    expect("the peers' slots are not this server's to take", order == [] and p.head_want() == 2)
    expect(
        "the snapshot says what the peers hold",
        p.snapshot() == {"capacity": 4, "used": 0, "waiting": 1, "peers": 3},
    )
    await p.set_peers(1, 0)
    await asyncio.wait_for(a, 1)
    expect("when the peers let go, the waiter goes in", order == ["render-2"] and p.used == 0)

    # a waiter that fell asleep while the machine was full is woken by the peers alone: no local
    # release ever comes, only set_peers
    order.clear()
    await p.set_peers(4, 0)
    a = asyncio.create_task(job("still", 1))
    await asyncio.sleep(0.03)
    expect("a full machine: even one slot waits", order == [])
    await p.set_peers(0, 0)
    await asyncio.wait_for(a, 1)
    expect("and is not stranded when it frees up", order == ["still"])

    # an older server's first waiter wants 3: a new take of 2 would leave it short, so it waits
    order.clear()
    await p.set_peers(0, 3)
    a = asyncio.create_task(job("new-2", 2))
    await asyncio.sleep(0.03)
    expect("an older server's want blocks a new take", order == [])
    q = Pool("browser", 4)  # the want reserves what it wants, no more: 3 + 1 fits in 4
    await q.set_peers(0, 3)
    await asyncio.wait_for(job("new-1", 1, pool=q), 1)
    await p.set_peers(0, 0)
    await asyncio.wait_for(a, 1)
    expect("clearing it lets the take through", order == ["new-1", "new-2"])

    # more than the pool has is the whole pool, peers or not
    order.clear()
    await p.set_peers(1, 0)
    a = asyncio.create_task(job("huge", 9))
    await asyncio.sleep(0.03)
    expect("an oversized request waits for the whole machine", order == [] and p.head_want() == 4)
    await p.set_peers(0, 0)
    await asyncio.wait_for(a, 1)
    expect("and goes in once nothing else holds any", order == ["huge"] and p.used == 0)

    # the whole scheduler: usage for the heartbeat, set_peers with pools missing
    s = Sched(claude=2, browser=4, cpu=2)
    hold = asyncio.create_task(job("holder", 1, 0.2, pool=s["browser"]))
    await asyncio.sleep(0.01)
    await s.set_peers({"browser": {"used": 3, "want": 0}})
    wait = asyncio.create_task(job("waiter", 2, pool=s["browser"]))
    await asyncio.sleep(0.01)
    expect(
        "usage: what it holds and its first waiter wants (%s)" % s.usage(),
        s.usage()
        == {
            "claude": {"used": 0, "want": 0},
            "browser": {"used": 1, "want": 2},
            "cpu": {"used": 0, "want": 0},
        },
    )
    expect(
        "a pool missing from set_peers has none",
        s["cpu"].peer_used == 0 and s.snapshot()["browser"]["peers"] == 3,
    )
    await s.set_peers({})
    await asyncio.wait_for(asyncio.gather(hold, wait), 2)
    expect("and set_peers({}) clears them all", s["browser"].peer_used == 0)

    # two servers side by side, their counts carried across as the server does it: the old one's
    # final render (3 browsers) against a new one taking a browser at a time for its stills
    old, new = Sched(browser=4), Sched(browser=4)
    stop = asyncio.Event()

    async def bridge():  # the heartbeat, every 10 ms: used both ways, want from older to newer
        while not stop.is_set():
            o, n = old.usage(), new.usage()
            await old.set_peers({k: {"used": n[k]["used"], "want": 0} for k in n})
            await new.set_peers({k: {"used": o[k]["used"], "want": o[k]["want"]} for k in o})
            await asyncio.sleep(0.01)

    async def stills(name):
        while not stop.is_set():
            async with new["browser"].hold(1, name):
                await asyncio.sleep(0.03)

    b = asyncio.create_task(bridge())
    busy = [asyncio.create_task(stills("still-%d" % i)) for i in range(3)]
    await asyncio.sleep(0.1)
    t0 = asyncio.get_running_loop().time()
    async with old["browser"].hold(3, "final render"):
        waited = asyncio.get_running_loop().time() - t0
        await asyncio.sleep(0.05)
    expect(
        "the old server's render is not starved by the new one's stills (%.2f s)" % waited,
        waited < 0.5,
    )
    stop.set()
    await asyncio.wait_for(asyncio.gather(b, *busy), 2)
    expect("and the new one's stills went on", new["browser"].used == 0)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
