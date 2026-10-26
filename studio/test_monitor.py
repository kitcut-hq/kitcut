#!/usr/bin/env python
"""deploy/monitor.py without a machine to watch: the rules' hold and let-go lines, what each alert
says, the disk's fill rate, the kernel lines that become events, the minutes the page draws, the
units systemd reports, and the page's key. Seconds, no root, no Elasticsearch.

    python studio/test_monitor.py

A rule must hold for its time before it is told and fall past a lower line before it is let go,
so a reading that hovers around a line is one email; a level only rises while it stands. A unit
nobody enabled is not told when it stops. A failed hand job (run-u*.service) is not told; a failed
kitcut unit is. The note carries what to tell and the site keys each alert by its own name.
"""

import os
import sys
import json
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
os.environ["STUDIO_HOME"] = tempfile.mkdtemp(prefix="studio-monitor-test-")
sys.path.insert(0, os.path.join(HERE, "deploy"))
import monitor  # noqa: E402 -- the stdlib only

bad = []


def check(ok, what, got=None):
    print("%s  %s%s" % ("ok   " if ok else "FAIL ", what, "" if ok else "  -- %r" % (got,)))
    if not ok:
        bad.append(what)


CFG = monitor.config()


def look(avail_pct=60.0, swap_pct=10.0, root_pct=60.0, mem_full=0.0, cpu_some=0.0, temp=50.0):
    total = 32000
    return {
        "mem": {
            "total_mb": total,
            "avail_mb": total * avail_pct / 100,
            "avail_gb": round(total * avail_pct / 102400, 1),
            "avail_pct": avail_pct,
            "used_pct": 100 - avail_pct,
        },
        "swap": {
            "total_mb": 8192,
            "used_mb": 8192 * swap_pct / 100,
            "used_gb": 1.0,
            "used_pct": swap_pct,
        },
        "psi": {"memory_full_avg60": mem_full, "cpu_some_avg300": cpu_some},
        "disk": {
            "root": {
                "path": "/",
                "pct": root_pct,
                "free_gb": 400.0,
                "total_gb": 981.0,
                "inodes_pct": 2.0,
            },
            "boot": {
                "path": "/boot",
                "pct": 6.0,
                "free_gb": 1.8,
                "total_gb": 2.0,
                "inodes_pct": 0.1,
            },
        },
        "temp": {"cpu": temp, "nvme": 40.0},
        "gpu": {"temp": 40.0},
        "cpu": {"pct": 10.0},
        "load": {"1": 1, "5": 1},
    }


def keys(alerts):
    return {a["key"]: a["level"] for a in alerts}


def hold_and_let_go():
    r = monitor.Rules(CFG)
    c = CFG["rules"]["memory"]
    t = 1000.0
    check("memory" not in keys(r.judge(look(avail_pct=8), {}, t)), "low memory is not told at once")
    check(
        "memory" not in keys(r.judge(look(avail_pct=8), {}, t + c["for_s"] - 1)),
        "nor a second before its time",
    )
    a = keys(r.judge(look(avail_pct=8), {}, t + c["for_s"]))
    check(a.get("memory") == "warn", "but once it held for_s: warn", a)
    a = keys(r.judge(look(avail_pct=12), {}, t + 200))
    check(
        a.get("memory") == "warn",
        "back above the warn line but under the clear line: still stands",
        a,
    )
    a = keys(r.judge(look(avail_pct=4), {}, t + 210))
    check(a.get("memory") == "crit", "below the crit line: it rises to crit", a)
    a = keys(r.judge(look(avail_pct=8), {}, t + 220))
    check(a.get("memory") == "crit", "and does not fall back to warn while it stands", a)
    a = keys(r.judge(look(avail_pct=c["clear_above_pct"] + 1), {}, t + 230))
    check("memory" not in a, "above the clear line: let go", a)
    r.judge(look(avail_pct=8), {}, t + 300)
    a = keys(r.judge(look(avail_pct=50), {}, t + 310))
    a = keys(r.judge(look(avail_pct=8), {}, t + 320))
    check("memory" not in a, "a dip that came back before its time starts the clock again", a)

    r = monitor.Rules(CFG)
    a = keys(r.judge(look(root_pct=96), {}, t))
    check(a.get("disk") == "crit", "a nearly full disk is told at once (no hold)", a)
    al = [x for x in r.judge(look(root_pct=96), {}, t) if x["key"] == "disk"][0]
    check(
        "400.0 GB" in al["subject"] and al["rows"][-1][0] == "Page",
        "the subject has the numbers; the rows end with the page",
        al,
    )
    check(
        json.loads(json.dumps(al)) == al,
        "an alert is plain JSON (it rides in the note to the site)",
    )


def rules_that_need_time():
    r = monitor.Rules(CFG)
    t = 0.0
    for i in range(0, 4000, 15):
        a = keys(r.judge(look(cpu_some=95), {}, t + i))
    check(a.get("cpu_stall") == "warn", "an hour short of CPU is told", a)
    r = monitor.Rules(CFG)
    for i in range(0, 1000, 15):
        a = keys(r.judge(look(cpu_some=95), {}, t + i))
    check("cpu_stall" not in a, "a busy quarter of an hour is not (renders are busy)", a)
    r = monitor.Rules(CFG)
    for i in range(0, 400, 15):
        a = keys(r.judge(look(temp=99), {}, t + i))
    check(a.get("cpu_temp") == "warn", "a hot CPU held for minutes is told", a)


def units():
    r = monitor.Rules(CFG)
    slow = {
        "units": {
            "elasticsearch": {
                "active": "failed",
                "sub": "failed",
                "loaded": "loaded",
                "enabled": "enabled",
            },
            "mongod-kc": {
                "active": "inactive",
                "sub": "dead",
                "loaded": "loaded",
                "enabled": "disabled",
            },
            "kitcut-monitor-tunnel": {"active": "inactive", "sub": "dead", "loaded": "not-found"},
        },
        "failed": [
            "run-u587.service",
            "h3test3.service",
            "kitcut-prune.service",
            "elasticsearch.service",
        ],
        "last_run": {
            "kitcut-filmgit": {"result": "exit-code", "status": "1", "active": "inactive"}
        },
    }
    t = 0.0
    r.judge(look(), slow, t)
    a = keys(r.judge(look(), slow, t + CFG["units"]["for_s"]))
    check(
        a.get("unit_elasticsearch") == "warn", "an enabled unit that stopped is told after for_s", a
    )
    check("unit_mongod-kc" not in a, "a unit nobody enabled is not (started by hand)", a)
    check("unit_kitcut-monitor-tunnel" not in a, "nor one this machine does not have", a)
    check("failed_kitcut-prune.service" in a, "a failed kitcut unit is told", a)
    check(
        "failed_run-u587.service" not in a and "failed_h3test3.service" not in a,
        "a failed hand job is not (it is on the page)",
        a,
    )
    check("failed_elasticsearch.service" not in a, "and a watched unit is told once, not twice", a)
    check(a.get("lastrun_kitcut-filmgit") == "warn", "a oneshot whose last run failed is told", a)


def show_parses_by_id():
    real = monitor.run
    out = (
        "Id=elasticsearch.service\nActiveState=active\nSubState=running\nUnitFileState=enabled\n\n"
        "Id=instafill-detector.socket\nActiveState=active\nSubState=listening\nUnitFileState=enabled\n"
    )
    monitor.run = lambda cmd, timeout=10: (0, out)
    try:
        got = monitor.unit_states(["elasticsearch", "no such thing!", "instafill-detector.socket"])
    finally:
        monitor.run = real
    check(
        got.get("elasticsearch", {}).get("active") == "active",
        "systemctl show is read back by Id",
        got,
    )
    check(
        got.get("instafill-detector.socket", {}).get("sub") == "listening",
        "a socket keeps its own suffix",
        got,
    )
    check(
        "no such thing!" not in got,
        "a name systemd left out is left out, not shifted onto the next",
        got,
    )


def disk_fill_rate():
    h = monitor.History(7)
    i = h.col("free")
    now = 1_800_000_000
    for m in range(24 * 60):  # 24 h losing 2 GB an hour from 100 GB
        row = [now - (24 * 60 - m) * 60] + [None] * len(h.cols)
        row[i] = 100 - 2 * m / 60
        h.rows.append(row)
    hours = monitor.fill_hours(h, 24, 6)
    check(
        hours is not None and 25 < hours < 29,
        "52 GB left at 2 GB an hour: full in about 26 h",
        hours,
    )
    r = monitor.Rules(CFG)
    s = look()
    s["disk"]["root"]["free_gb"] = 52.0
    a = [x for x in r.judge(s, {}, now, h) if x["key"] == "disk_trend"]
    check(bool(a) and "full in about" in a[0]["subject"], "and the rule says so", a)
    flat = monitor.History(7)
    for m in range(24 * 60):
        row = [now - (24 * 60 - m) * 60] + [None] * len(flat.cols)
        row[i] = 300.0 + (m % 7)
        flat.rows.append(row)
    check(
        monitor.fill_hours(flat, 24, 6) is None,
        "a disk that is not filling has no date",
        monitor.fill_hours(flat, 24, 6),
    )
    short = monitor.History(7)
    for row in list(h.rows)[-120:]:
        short.rows.append(row)
    check(monitor.fill_hours(short, 24, 6) is None, "two hours of history are too few to tell")


def kernel_lines():
    j = monitor.Journal.__new__(monitor.Journal)
    j.pats = [dict(p, rx=monitor.re.compile(p["re"])) for p in CFG["journal"]]

    def hit(msg, transport="kernel"):
        return j.match({"_TRANSPORT": transport, "MESSAGE": msg})

    h = hit(
        "oom-kill:constraint=CONSTRAINT_NONE,nodemask=(null),cpuset=/,mems_allowed=0,global_oom,"
        "task_memcg=/system.slice/kitcut-studio@x.service,task=python3,pid=4242,uid=1000"
    )
    check(
        h and h["kind"] == "oom_global" and "python3" in h["subject"] and h["tell"],
        "a global OOM kill is told, with the process",
        h,
    )
    h = hit(
        "oom-kill:constraint=CONSTRAINT_MEMCG,nodemask=(null),cpuset=/,mems_allowed=0,"
        "oom_memcg=/system.slice/run-u12.service,task_memcg=/system.slice/run-u12.service,task=msedge,pid=7,uid=1000"
    )
    check(
        h and h["kind"] == "oom_capped" and "run-u12" in h["subject"],
        "a job killed at its own cap names the cap",
        h,
    )
    h = hit("nvme nvme0: I/O 123 QID 4 timeout, aborting")
    check(
        h and h["kind"] == "disk_error" and h["level"] == "crit",
        "an NVMe timeout is a disk error",
        h,
    )
    h = hit("NVRM: Xid (PCI:0000:01:00): 79, pid=1234, GPU has fallen off the bus.")
    check(
        h and h["kind"] == "gpu_xid" and "79" in h["subject"],
        "a GPU Xid is told with its number",
        h,
    )
    h = hit("INFO: task kworker/3:1:123 blocked for more than 122 seconds.")
    check(h and h["kind"] == "hung_task", "a hung task is told", h)
    check(
        hit("mce: CPU0: Thermal monitoring enabled (TM1)") is None,
        "the boot's own mce line is not a hardware error",
    )
    check(hit("[UFW BLOCK] IN=enp5s0 OUT= SRC=192.168.4.124") is None, "a firewall drop is nothing")
    check(
        hit("oom-kill:constraint=CONSTRAINT_NONE task=x,pid=1", transport="stdout") is None,
        "a program that prints a kernel-looking line is not the kernel",
    )
    e = monitor.entry(
        {
            "__REALTIME_TIMESTAMP": "1793037727011000",
            "PRIORITY": "3",
            "_SYSTEMD_UNIT": "x.service",
            "MESSAGE": [104, 105],
        }
    )
    check(
        e["msg"] == "hi" and e["level"] == "err" and e["@timestamp"].startswith("2026-10-26"),
        "a journal line becomes a document (binary messages decoded)",
        e,
    )
    r = monitor.Rules(CFG)
    r.event("oom_global_1", "crit", "x", [], 100.0)
    r.event("oom_global_1", "crit", "x", [], 110.0)
    ev = [x for x in r.judge(look(), {}, 120.0) if x["kind"] == "event"]
    check(
        len(ev) == 1 and ev[0]["count"] == 2,
        "the same event again in its window is counted, not repeated",
        ev,
    )
    ev = [x for x in r.judge(look(), {}, 110.0 + CFG["event_keep_s"] + 1) if x["kind"] == "event"]
    check(not ev, "and after event_keep_s it goes (the note has carried it)", ev)


def minutes_for_the_page():
    h = monitor.History(7)
    t = 1_800_000_000 - 1_800_000_000 % 60
    for k, v in enumerate((10, 30, 20)):
        h.add({"cpu": {"pct": v}, "mem": {"used_pct": v, "avail_gb": v}}, t + k * 15)
    h.add({"cpu": {"pct": 99}, "mem": {"used_pct": 99, "avail_gb": 1}}, t + 60)
    row = h.rows[-1]
    check(row[h.col("cpu")] == 20.0, "a minute's CPU is its average", row[h.col("cpu")])
    check(
        row[h.col("mem")] == 30 and row[h.col("avail")] == 10,
        "its memory the worst of the minute",
        row,
    )
    check(
        row[h.col("disk")] is None, "and what was not read is empty, not zero", row[h.col("disk")]
    )
    h2 = monitor.History(7)
    now = int(monitor.time.time()) // 60 * 60
    for m in range(1440):
        r = [now - (1440 - m) * 60] + [0] * len(h2.cols)
        r[h2.col("mem")] = 95 if m == 700 else 20
        h2.rows.append(r)
    got = h2.since(24, points=100)
    check(len(got["rows"]) <= 100, "a day is thinned to the points asked for", len(got["rows"]))
    check(
        max(r[h2.col("mem")] for r in got["rows"]) == 95,
        "and a one-minute spike survives the thinning",
    )
    h2.save()
    h3 = monitor.History(7)
    h3.load()
    check(
        len(h3.rows) == 1440 and h3.rows[-1][h3.col("mem")] == 20,
        "seven days of minutes survive a restart",
    )


def the_key():
    a, b = monitor.cookie_value("one"), monitor.cookie_value("two")
    check(
        a != b and len(a) == 64 and "one" not in a,
        "the cookie is derived from the key, never the key itself",
    )


def the_note():
    sys.path.insert(0, HERE)
    import backup  # noqa: PLC0415 -- the stdlib only
    import machine_note  # noqa: PLC0415 -- pymongo only when it writes, which this never does

    os.makedirs(os.path.join(backup.HOME, "monitor"), exist_ok=True)
    health = {
        "at": "2026-10-26T12:00:00-07:00",
        "alerts": [{"key": "memory", "level": "warn", "subject": "low"}],
    }
    with open(os.path.join(backup.HOME, "monitor", "health.json"), "w") as f:
        json.dump(health, f)
    n = machine_note.note()
    check(
        n.get("health") == health,
        "the machine's note carries the watch's alerts to the site",
        n.get("health"),
    )


if __name__ == "__main__":
    hold_and_let_go()
    rules_that_need_time()
    units()
    show_parses_by_id()
    disk_fill_rate()
    kernel_lines()
    minutes_for_the_page()
    the_key()
    the_note()
    print("\n%d failed" % len(bad) if bad else "\nall passed")
    sys.exit(1 if bad else 0)
