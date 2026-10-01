#!/usr/bin/env python
"""Who uses the machine, checked without the machine: python studio/test_usage.py

    labels    a step's film and name, from its command (procs.step_label), and its cgroup name
    steps     a finished step leaves its line in the steps log (procs.record_step via procs.run)
    sampler   deploy/usage.py on a fake cgroup and /proc tree: each film's step, the server, the
              ssh sessions, CPU from two samples, processes tied to their films
    report    the hourly table, the memory low points and the per-film / per-step bills render

Seconds; no root, no cgroups (test_isolation.py checks the real ones on the VM).
"""

import io
import os
import sys
import json
import shutil
import asyncio
import tempfile
import contextlib
from datetime import datetime

HOME = tempfile.mkdtemp(prefix="studio-usage-")
os.environ["STUDIO_HOME"] = HOME
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "deploy"))
import procs  # noqa: E402
import usage  # noqa: E402

bad = []


def check(ok, what, got=None):
    print("%s  %s%s" % ("ok  " if ok else "FAIL", what, "" if ok else "  (got %r)" % (got,)))
    if not ok:
        bad.append(what)


def put(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def labels():
    film = os.path.join("x", "projects", "studio-20261001-012901-3mx2e4")
    got = procs.step_label(
        [
            "/v/python",
            "-X",
            "utf8",
            "/r/scripts/sketch-render.py",
            "--manifest",
            "m",
            "--stills",
            "1,2",
        ],
        film,
    )
    check(
        got == ("3mx2e4", "sketch-render --stills"),
        "a script's step: the film, the script, its option",
        got,
    )
    got = procs.step_label(
        ["/v/python", "-X", "utf8", "/r/scripts/sketch-vo.py", "--manifest", "m"], film
    )
    check(got == ("3mx2e4", "sketch-vo"), "a script with only its manifest", got)
    got = procs.step_label(["/usr/bin/node", "--check", film + "/film.js"], film)
    check(got == ("3mx2e4", "film"), "node --check names the file it checks", got)
    got = procs.step_label(["ffmpeg", "-i", "a"], "/tmp/other")
    check(got == ("other", "ffmpeg"), "outside a film: the folder and the program", got)
    check(
        procs._slug("3mx2e4-sketch-render --stills") == "3mx2e4-sketch-render-stills",
        "a cgroup-safe name",
    )
    m = usage.STEP.match("step-2094412-17-3mx2e4-sketch-render-stills")
    check(
        m and usage.who("studio@0f3c3128a2ce", m.group(0)) == "film 3mx2e4: sketch-render-stills",
        "the sampler reads the name back",
    )
    check(
        usage.who("studio@0f3c3128a2ce", "step-1-2") == "film ?: ?",
        "an unnamed step (an older server) is still a step",
    )


async def steps():
    film = os.path.join(HOME, "projects", "studio-20261001-012901-abcdef")
    os.makedirs(film)
    code, _ = await procs.run(
        [sys.executable, "-c", "print(sum(range(3 * 10**7)))"], film, dict(os.environ), 30
    )
    day = os.path.join(HOME, "usage", datetime.now().strftime("steps-%Y-%m-%d.jsonl"))
    rows = [json.loads(ln) for ln in open(day, encoding="utf-8")] if os.path.exists(day) else []
    check(code == 0 and len(rows) == 1, "a finished step leaves one line", rows)
    if rows:
        r = rows[0]
        check(
            r["film"] == "abcdef" and r["code"] == 0 and r["wall_s"] >= 0,
            "with its film, exit code and time",
            r,
        )
        if os.name == "nt" or procs.cgroup_root():
            check(
                (r.get("cpu_s") or 0) > 0 and (r.get("peak_mb") or 0) > 5,
                "and its CPU and memory peak",
                r,
            )


def fake_tree(root, cpu_server, cpu_step, ticks):
    cg, proc = os.path.join(root, "cg"), os.path.join(root, "proc")
    unit = os.path.join(
        cg, "system.slice", "kitcut-studio@0f3c3128a2ce-20261001115014.2094412.service"
    )
    put(os.path.join(unit, "server", "memory.current"), str(300 << 20))
    put(os.path.join(unit, "server", "cpu.stat"), "usage_usec %d\nuser_usec 1\n" % cpu_server)
    step = os.path.join(unit, "step-2094412-17-3mx2e4-sketch-render")
    put(os.path.join(step, "memory.current"), str(3 << 30))
    put(os.path.join(step, "cpu.stat"), "usage_usec %d\n" % cpu_step)
    put(os.path.join(step, "memory.stat"), "anon %d\nfile 1\n" % (2 << 30))
    tun = os.path.join(cg, "system.slice", "kitcut-tunnel.service")
    put(os.path.join(tun, "memory.current"), str(1 << 20))  # small and idle: left out
    put(os.path.join(tun, "cpu.stat"), "usage_usec 5\n")
    put(os.path.join(cg, "user.slice", "memory.current"), str(200 << 20))
    put(os.path.join(cg, "user.slice", "cpu.stat"), "usage_usec 10\n")
    put(os.path.join(proc, "stat"), "cpu  %d 0 0 %d 0 0 0 0\n" % (ticks, 4000))
    put(os.path.join(proc, "meminfo"), "MemTotal:       16384000 kB\nMemAvailable:    9000000 kB\n")
    put(os.path.join(proc, "loadavg"), "6.30 6.05 7.71 3/400 1\n")
    put(os.path.join(proc, "pressure", "cpu"), "some avg10=42.50 avg60=30.00 avg300=1 total=1\n")
    put(
        os.path.join(proc, "pressure", "memory"),
        "some avg10=0.00 avg60=0 avg300=0 total=0\nfull avg10=0.00 avg60=0 avg300=0 total=0\n",
    )
    rel = "/system.slice/system-kitcut\x2dstudio.slice/kitcut-studio@0f3c3128a2ce-20261001115014.2094412.service/step-2094412-17-3mx2e4-sketch-render"
    pst = "%d (msedge) S 1 1 1 0 -1 0 0 0 0 0 %d 0 0 0 20 0 1 0 1 1 %d 0 0"
    put(os.path.join(proc, "4242", "stat"), pst % (4242, ticks // 2, 110000))
    put(
        os.path.join(proc, "4242", "cmdline"),
        "/opt/microsoft/msedge/msedge\0--type=renderer\0--user-data-dir=/srv/kitcut/studio/projects/studio-20261001-012901-3mx2e4/temp/x\0",
    )
    put(os.path.join(proc, "4242", "cgroup"), "0::" + rel + "\n")
    return cg, proc


def sampler():
    root = os.path.join(HOME, "fake")
    usage.CG, usage.PROC = fake_tree(root, 1_000_000, 10_000_000, 1000)
    s = usage.Sampler(15)
    check(s.sample() is None, "the first sample only sets the baseline")
    fake_tree(root, 1_300_000, 40_000_000, 4000)  # 30 s of CPU in the step, 0.3 s in the server
    s.prev = (s.prev[0] - 15,) + s.prev[1:]  # as if 15 s had passed
    r = s.sample()
    g = {x["who"]: x for x in r["groups"]}
    step = g.get("film 3mx2e4: sketch-render")
    check(
        step and step["mb"] == 3072 and step["anon"] == 2048 and abs(step["cores"] - 2.0) < 0.05,
        "a film's step: its memory, the part it holds, its cores",
        step,
    )
    srv = g.get("studio@0f3c3128a2ce (server + Claude Code)")
    check(srv and srv["mb"] == 300, "the server's own leaf", srv)
    check("kitcut-tunnel" not in g, "a small idle unit is left out", list(g))
    check("ssh sessions (user.slice)" in g, "the ssh sessions, as one", list(g))
    check(
        r["avail_mb"] == 8789 and r["psi"].get("cpu_some") == 42.5,
        "memory available and CPU pressure",
        r,
    )
    p = next((x for x in r["procs"] if x["pid"] == 4242), None)
    check(
        p
        and p["what"] == "edge renderer"
        and p["film"] == "3mx2e4"
        and p["unit"] == "studio@0f3c3128a2ce",
        "a process: what, whose film, which server",
        p,
    )
    return r


def report(sample):
    os.makedirs(os.path.join(HOME, "usage"), exist_ok=True)
    with open(usage.day_file(), "a", encoding="utf-8") as f:
        f.write(json.dumps(sample) + "\n")
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        usage.report(type("A", (), {"hours": 1, "at": None, "film": None, "top": 12})())
    text = out.getvalue()
    check(
        "by hour" in text and "film 3mx2e4" in text, "the hourly table names the film", text[:400]
    )
    check("lowest moments of memory" in text, "the memory low points")
    check("by film, from the steps log" in text and "abcdef" in text, "the per-film bill")
    check("by step:" in text, "the per-step bill")
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        usage.report(
            type(
                "A",
                (),
                {"hours": 1, "at": datetime.now().strftime("%H:%M"), "film": None, "top": 12},
            )()
        )
    check("edge renderer" in out.getvalue(), "--at shows one sample in full", out.getvalue()[:300])


if __name__ == "__main__":
    try:
        labels()
        asyncio.run(steps())
        report(sampler())
    finally:
        shutil.rmtree(HOME, ignore_errors=True)
    print("\n%d failed" % len(bad) if bad else "\nall passed")
    sys.exit(1 if bad else 0)
