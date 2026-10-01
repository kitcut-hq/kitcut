#!/usr/bin/env python3
"""Who uses the studio VM's CPU and memory: a sampler that runs all the time, and the report.

    python3 studio/deploy/usage.py sample [--every 15] [--keep-days 14]   (kitcut-usage.service)
    python3 studio/deploy/usage.py report [--hours 24] [--at "HH:MM" | --at "YYYY-MM-DD HH:MM"]
                                          [--film ID] [--top N]
    bash studio/deploy/ops.sh usage ...   (the same report, from the laptop)

Two sources, because neither is enough alone:

  samples   every 15 s, STUDIO_HOME/usage/<day>.jsonl: the machine (CPU busy, memory available,
            pressure stall), every cgroup that matters -- each server, each film's step (its
            cgroup is named after the film and the step: procs.Job), the server's own leaf (the
            server and its films' Claude Code), ops.sh jobs, ssh sessions -- with its CPU and
            memory, and the top processes with the film each belongs to. This is the timeline:
            who held the memory at 20:40.
  steps     one line per finished step, STUDIO_HOME/usage/steps-<day>.jsonl, written by the
            server (procs.record_step) off the step's own cgroup: exact CPU seconds and memory
            peak, even for a step shorter than a sample. This is the bill: what a film cost.

sar (sysstat, every 10 minutes) stays: it is the machine alone, and it averages a spike away.

Stdlib only, no repo imports: it runs on the system python3, beside the servers, capped
(MemoryMax) and niced in its unit.
"""

import os
import re
import sys
import glob
import json
import time
import argparse
from datetime import datetime, timedelta

CG = os.environ.get("USAGE_CGROUP_ROOT", "/sys/fs/cgroup")
PROC = os.environ.get("USAGE_PROC", "/proc")
HOME = os.environ.get("STUDIO_HOME", "/srv/kitcut/studio")
FILM = re.compile(r"studio-\d{8}-\d{6}-([a-z0-9]{6})")
STEP = re.compile(r"^step-\d+-\d+(?:-(.+))?$")
TICK = os.sysconf("SC_CLK_TCK") if hasattr(os, "sysconf") else 100
PAGE = os.sysconf("SC_PAGE_SIZE") if hasattr(os, "sysconf") else 4096
MB = 1 << 20
# a group below both is left out of a sample: the line stays small, nothing that matters is lost
MIN_MB, MIN_CPU = 40, 0.05


def read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def num(path):
    s = read(path).strip()
    return int(s) if s.isdigit() else None


def mem(d):
    """(memory.current, its anonymous part) in bytes: the current figure counts file cache the
    kernel takes back at need; anonymous memory is what runs a machine out (KI-045)."""
    m = re.search(r"^anon (\d+)", read(os.path.join(d, "memory.stat")), re.MULTILINE)
    return num(os.path.join(d, "memory.current")), (int(m.group(1)) if m else None)


def cpu_usec(d):
    m = re.search(r"^usage_usec (\d+)", read(os.path.join(d, "cpu.stat")), re.M)
    return int(m.group(1)) if m else None


def short_unit(name):
    """kitcut-studio@0f3c3128a2ce-20261001115014.2094412.service -> studio@0f3c3128a2ce, and
    kitcut-resume-20261001-012901-3mx2e4.service -> resume 3mx2e4."""
    name = re.sub(r"\.(service|scope|slice)$", "", name)
    m = re.match(r"kitcut-studio@([0-9a-f]{12})", name)
    if m:
        return "studio@" + m.group(1)
    m = re.match(r"kitcut-(resume|share|migrate)\S*?-([a-z0-9]{6})$", name)
    return "%s %s" % m.groups() if m else name


def film_of(d):
    """A step cgroup's film and what runs in it, read off its first process: for a step whose
    name does not say (one started by a server older than the named steps)."""
    for pid in read(os.path.join(d, "cgroup.procs")).split()[:1]:
        line = " ".join(read(os.path.join(PROC, pid, "cmdline")).split("\0"))
        m = FILM.search(line)
        py = re.search(r"([\w.-]+)\.(?:py|js) ", line + " ")
        return (m.group(1) if m else "?"), (py.group(1) if py else "?")
    return "?", "?"


def who(unit, child, d=None):
    """The name a cgroup is reported under: a film's step, a server, a job, a service."""
    if child:
        m = STEP.match(child)
        if m:
            label = m.group(1)
            if label:
                film, _, step = label.partition("-")
            else:
                film, step = film_of(d) if d else ("?", "?")
            return "film %s: %s" % (film, step or "?")
        if child == "server":
            return "%s (server + Claude Code)" % unit
        return "%s/%s" % (unit, child)
    return unit


# ---------------------------------------------------------------------------------- sampling
def units():
    """Every service and scope under system.slice, also those in a sub-slice (a template's
    instances: system-kitcut\x2dstudio.slice/kitcut-studio@...service)."""
    base = os.path.join(CG, "system.slice")
    found = []
    for d in sorted(
        glob.glob(os.path.join(base, "*")) + glob.glob(os.path.join(base, "*.slice", "*"))
    ):
        if os.path.isdir(d) and d.endswith((".service", ".scope")):
            found.append(d)
    return found


def groups():
    """{name: ((memory bytes, anonymous bytes), cpu usec)} for each service (its children, when it delegates them:
    a server's films' steps) and for the ssh sessions as one."""
    out = {}
    for d in units():
        unit = short_unit(os.path.basename(d))
        kids = [
            k
            for k in sorted(os.listdir(d))
            if not k.startswith(".") and os.path.isdir(os.path.join(d, k))
        ]
        if kids:
            for k in kids:
                out[who(unit, k, os.path.join(d, k))] = (
                    mem(os.path.join(d, k)),
                    cpu_usec(os.path.join(d, k)),
                )
        else:
            out[unit] = (mem(d), cpu_usec(d))
    u = os.path.join(CG, "user.slice")
    if os.path.isdir(u):
        out["ssh sessions (user.slice)"] = (mem(u), cpu_usec(u))
    return out


def machine():
    """CPU ticks (busy, total), memory and the pressure-stall averages."""
    first = read(os.path.join(PROC, "stat")).splitlines()[:1]
    v = [int(x) for x in first[0].split()[1:]] if first else [0] * 8
    idle = v[3] + (v[4] if len(v) > 4 else 0)
    mem = dict(
        (ln.split(":")[0], int(ln.split()[1]))
        for ln in read(os.path.join(PROC, "meminfo")).splitlines()
        if ln.count(" ") and ln.split()[1].isdigit()
    )
    psi = {}
    for k in ("cpu", "memory", "io"):
        for ln in read(os.path.join(PROC, "pressure", k)).splitlines():
            m = re.match(r"(some|full) avg10=([\d.]+)", ln)
            if m:
                psi["%s_%s" % (k, m.group(1))] = float(m.group(2))
    load = read(os.path.join(PROC, "loadavg")).split()[:1]
    return {
        "busy": sum(v) - idle,
        "total": sum(v),
        "avail_mb": mem.get("MemAvailable", 0) // 1024,
        "total_mb": mem.get("MemTotal", 0) // 1024,
        "load1": float(load[0]) if load else None,
        "psi": psi,
    }


def processes():
    """{pid: (comm, cpu ticks, rss bytes)} for every process."""
    out = {}
    for p in os.listdir(PROC):
        if not p.isdigit():
            continue
        s = read(os.path.join(PROC, p, "stat"))
        r = s.rfind(")")
        if r < 0:
            continue
        f = s[r + 2 :].split()
        try:
            out[int(p)] = (s[s.find("(") + 1 : r], int(f[11]) + int(f[12]), int(f[21]) * PAGE)
        except (IndexError, ValueError):
            continue
    return out


def describe(pid, comm):
    """What a process is and whose: (what, film or None, unit)."""
    cmd = read(os.path.join(PROC, str(pid), "cmdline")).split("\0")
    line = " ".join(cmd)
    m = FILM.search(line)
    film = m.group(1) if m else None
    what = comm
    if comm.startswith(("python", "python3")):
        py = next((os.path.basename(a) for a in cmd[1:] if a.endswith(".py")), None)
        what = py or comm
    elif comm in ("msedge", "microsoft-edge") or "msedge" in comm:
        t = re.search(r"--type=([\w-]+)", line)
        what = "edge " + (t.group(1) if t else "browser")
    elif "claude" in comm or "/claude" in line.split(" ")[0]:
        what = "claude code"
    cg = read(os.path.join(PROC, str(pid), "cgroup")).strip().rpartition("::")[2]
    parts = cg.strip("/").split("/")
    unit = short_unit(
        next((x for x in parts if x.endswith((".service", ".scope"))), parts[-1] or "?")
    )
    if parts[0] == "user.slice":
        unit = "ssh session"
    if parts and STEP.match(parts[-1]) and not film:
        film = (STEP.match(parts[-1]).group(1) or "").partition("-")[0] or None
    return what, film, unit


class Sampler:
    def __init__(self, every):
        self.every = every
        self.prev = None  # (monotonic, machine, groups, processes)

    def sample(self):
        now, mach, grp, procs = time.monotonic(), machine(), groups(), processes()
        row = None
        if self.prev:
            t0, m0, g0, p0 = self.prev
            dt = max(now - t0, 1e-3)
            busy = (mach["busy"] - m0["busy"]) / max(mach["total"] - m0["total"], 1)
            ncpu = os.cpu_count() or 1
            row = {
                "t": datetime.now().astimezone().isoformat(timespec="seconds"),
                "dt": round(dt, 1),
                "cpu": round(100 * busy, 1),  # % of the whole machine
                "ncpu": ncpu,
                "avail_mb": mach["avail_mb"],
                "total_mb": mach["total_mb"],
                "load1": mach["load1"],
                "psi": mach["psi"],
                "groups": [],
                "procs": [],
            }
            for name, ((current, anon), usec) in grp.items():
                before = g0.get(name, (None, None))[1]
                cores = (
                    (usec - before) / 1e6 / dt if usec is not None and before is not None else None
                )
                mb = (current or 0) / MB
                if mb >= MIN_MB or (cores or 0) >= MIN_CPU:
                    row["groups"].append(
                        {
                            "who": name,
                            "mb": round(mb),  # with the file cache
                            "anon": None if anon is None else round(anon / MB),  # held
                            "cores": None if cores is None else round(cores, 2),
                        }
                    )
            row["groups"].sort(key=lambda g: -(g["cores"] or 0))
            rate = {}
            for pid, (comm, ticks, _rss) in procs.items():
                if pid in p0 and p0[pid][0] == comm:
                    rate[pid] = max(ticks - p0[pid][1], 0) / TICK / dt
            top = sorted(rate, key=lambda p: -rate[p])[:6]
            top += [p for p in sorted(procs, key=lambda p: -procs[p][2])[:6] if p not in top]
            for pid in top:
                comm, _, rss = procs[pid]
                what, film, unit = describe(pid, comm)
                row["procs"].append(
                    {
                        "pid": pid,
                        "what": what,
                        "film": film,
                        "unit": unit,
                        "cores": round(rate.get(pid, 0), 2),
                        "mb": round(rss / MB),
                    }
                )
        self.prev = (now, mach, grp, procs)
        return row


def day_file(stamp=None, kind=""):
    return os.path.join(
        HOME, "usage", "%s%s.jsonl" % (kind, (stamp or datetime.now()).strftime("%Y-%m-%d"))
    )


def prune(keep_days):
    cut = time.time() - keep_days * 86400
    for p in glob.glob(os.path.join(HOME, "usage", "*.jsonl")):
        if os.path.getmtime(p) < cut:
            os.remove(p)


def sample_forever(every, keep_days):
    os.makedirs(os.path.join(HOME, "usage"), exist_ok=True)
    s, last_prune = Sampler(every), 0
    print("usage: sampling every %d s into %s" % (every, os.path.join(HOME, "usage")), flush=True)
    while True:
        t = time.monotonic()
        try:
            row = s.sample()
            if row:
                with open(day_file(), "a", encoding="utf-8") as f:
                    f.write(json.dumps(row, separators=(",", ":")) + "\n")
            if t - last_prune > 3600:
                prune(keep_days)
                last_prune = t
        except Exception as e:  # noqa: BLE001 -- a bad sample is skipped, the sampler goes on
            print("usage: sample failed: %r" % e, file=sys.stderr, flush=True)
        time.sleep(max(every - (time.monotonic() - t), 1))


# ---------------------------------------------------------------------------------- the report
def load(kind, since, until):
    rows, day = [], since.date()
    while day <= until.date():
        p = day_file(datetime.combine(day, datetime.min.time()), kind)
        for ln in read(p).splitlines():
            try:
                r = json.loads(ln)
                t = datetime.fromisoformat(r["t"]).replace(tzinfo=None)
            except (ValueError, KeyError):
                continue
            if since <= t <= until:
                r["_t"] = t
                rows.append(r)
        day += timedelta(days=1)
    return rows


def parse_at(s):
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%H:%M"):
        try:
            t = datetime.strptime(s, fmt)
        except ValueError:
            continue
        if fmt == "%H:%M":
            now = datetime.now()
            t = now.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)
            if t > now:
                t -= timedelta(days=1)
        return t
    raise SystemExit("--at: HH:MM or YYYY-MM-DD HH:MM, not %r" % s)


def bucket(name):
    """A film's steps sum by film in the hourly view; everything else by its own name."""
    return name.split(":")[0] if name.startswith("film ") else name


def held(g):
    """A group's memory that the kernel cannot take back (anonymous), in MB; the total where an
    older sample did not record it."""
    return g["anon"] if g.get("anon") is not None else g["mb"]


def show_sample(r, top):
    print(
        "%s  cpu %3.0f%%  load %s  memory available %.1f of %.0f GB  pressure cpu %s mem %s io %s"
        % (
            r["_t"].strftime("%m-%d %H:%M:%S"),
            r["cpu"],
            r.get("load1"),
            r["avail_mb"] / 1024,
            r["total_mb"] / 1024,
            r["psi"].get("cpu_some"),
            r["psi"].get("memory_some"),
            r["psi"].get("io_some"),
        )
    )
    print("  %-52s %9s %10s %7s" % ("group", "held", "with cache", "cores"))
    for g in sorted(r["groups"], key=lambda g: -held(g))[:top]:
        print("  %-52s %6d MB %7d MB %7s" % (g["who"][:52], held(g), g["mb"], g["cores"]))
    print("  %-7s %-26s %-8s %-22s %8s %6s" % ("pid", "process", "film", "unit", "memory", "cores"))
    for p in r["procs"]:
        print(
            "  %-7s %-26s %-8s %-22s %5d MB %6.2f"
            % (p["pid"], p["what"][:26], p["film"] or "", p["unit"][:22], p["mb"], p["cores"])
        )


def report(args):
    until = datetime.now()
    if args.at:
        at = parse_at(args.at)
        rows = load("", at - timedelta(minutes=2), at + timedelta(minutes=2))
        if not rows:
            raise SystemExit("no sample within 2 minutes of %s" % at)
        show_sample(min(rows, key=lambda r: abs((r["_t"] - at).total_seconds())), args.top)
        return
    since = until - timedelta(hours=args.hours)
    rows = load("", since, until)
    steps = load("steps-", since, until)
    if args.film:
        steps = [s for s in steps if s["film"] == args.film]
    print(
        "%s .. %s: %d samples, %d steps"
        % (since.strftime("%m-%d %H:%M"), until.strftime("%m-%d %H:%M"), len(rows), len(steps))
    )
    if not rows and not steps:
        print("nothing recorded yet: is kitcut-usage.service running? (ops.sh usage install)")
        return

    if rows and not args.film:
        print(
            "\nby hour: CPU %% of the machine, the lowest memory available, the CPU pressure, and"
        )
        print(
            "who used the most CPU (core-minutes) and held the most memory at the low point"
            " (anonymous memory: what the kernel cannot take back)"
        )
        hours = {}
        for r in rows:
            hours.setdefault(r["_t"].strftime("%m-%d %H:00"), []).append(r)
        for h, rs in sorted(hours.items()):
            cpu = sum(r["cpu"] for r in rs) / len(rs)
            low = min(rs, key=lambda r: r["avail_mb"])
            use = {}
            for r in rs:
                for g in r["groups"]:
                    use[bucket(g["who"])] = (
                        use.get(bucket(g["who"]), 0) + (g["cores"] or 0) * r.get("dt", 15) / 60
                    )
            top = sorted(use.items(), key=lambda kv: -kv[1])[:3]
            big = max(low["groups"], key=held, default=None)
            print(
                "  %s  cpu %3.0f%% (max %3.0f%%)  min avail %4.1f GB  cpu pressure max %5.1f  | %s | %s"
                % (
                    h,
                    cpu,
                    max(r["cpu"] for r in rs),
                    low["avail_mb"] / 1024,
                    max(r["psi"].get("cpu_some", 0) for r in rs),
                    ", ".join("%s %.0f" % (k, v) for k, v in top if v >= 0.5) or "idle",
                    "%s %.1f GB" % (big["who"], held(big) / 1024) if big else "",
                )
            )
        print(
            '\nthe %d lowest moments of memory (ops.sh usage --at "<time>" for one in full):'
            % min(5, len(rows))
        )
        seen = []
        for r in sorted(rows, key=lambda r: r["avail_mb"]):
            if any(abs((r["_t"] - s).total_seconds()) < 600 for s in seen):
                continue  # one moment per ten minutes, not five samples of the same one
            seen.append(r["_t"])
            gs = sorted(r["groups"], key=lambda g: -held(g))[:4]
            print(
                "  %s  avail %.1f GB  %s"
                % (
                    r["_t"].strftime("%m-%d %H:%M:%S"),
                    r["avail_mb"] / 1024,
                    ", ".join("%s %.1f GB" % (g["who"], held(g) / 1024) for g in gs),
                )
            )
            if len(seen) >= 5:
                break
        print("\nCPU outside the films' steps over the window (core-minutes):")
        other = {}
        for r in rows:
            for g in r["groups"]:
                if not g["who"].startswith("film "):
                    other[g["who"]] = (
                        other.get(g["who"], 0) + (g["cores"] or 0) * r.get("dt", 15) / 60
                    )
        for k, v in sorted(other.items(), key=lambda kv: -kv[1])[: args.top]:
            if v >= 0.5:
                print("  %-56s %7.0f" % (k[:56], v))

    if steps:
        films = {}
        for s in steps:
            f = films.setdefault(
                s["film"], {"n": 0, "cpu": 0.0, "wall": 0.0, "peak": 0, "big": ("", 0.0)}
            )
            f["n"] += 1
            f["cpu"] += s.get("cpu_s") or 0
            f["wall"] += s.get("wall_s") or 0
            f["peak"] = max(f["peak"], s.get("peak_mb") or 0)
            if (s.get("cpu_s") or 0) > f["big"][1]:
                f["big"] = (s["step"], s.get("cpu_s") or 0)
        print(
            "\nby film, from the steps log (exact): CPU minutes, step minutes, biggest memory peak"
        )
        print(
            "  %-8s %5s %8s %8s %9s  %s"
            % ("film", "steps", "cpu min", "wall min", "peak", "most CPU")
        )
        for k, f in sorted(films.items(), key=lambda kv: -kv[1]["cpu"])[: args.top]:
            print(
                "  %-8s %5d %8.1f %8.1f %6.1f GB  %s (%.0f min)"
                % (
                    k,
                    f["n"],
                    f["cpu"] / 60,
                    f["wall"] / 60,
                    f["peak"] / 1024,
                    f["big"][0],
                    f["big"][1] / 60,
                )
            )
        kinds = {}
        for s in steps:
            k = kinds.setdefault(s["step"], {"n": 0, "cpu": 0.0, "peak": 0, "oom": 0, "fail": 0})
            k["n"] += 1
            k["cpu"] += s.get("cpu_s") or 0
            k["peak"] = max(k["peak"], s.get("peak_mb") or 0)
            k["oom"] += s.get("oom") or 0
            k["fail"] += s.get("code") != 0  # an exit code, or None: cancelled, timed out
        print(
            "\nby step: how many, CPU minutes in all and per step, the biggest memory peak, killed by the cap, failed"
        )
        print(
            "  %-34s %5s %8s %8s %9s %4s %5s"
            % ("step", "n", "cpu min", "per step", "peak", "oom", "fail")
        )
        for k, v in sorted(kinds.items(), key=lambda kv: -kv[1]["cpu"])[: args.top]:
            print(
                "  %-34s %5d %8.1f %7.1fm %6.1f GB %4d %5d"
                % (
                    k[:34],
                    v["n"],
                    v["cpu"] / 60,
                    v["cpu"] / 60 / v["n"],
                    v["peak"] / 1024,
                    v["oom"],
                    v["fail"],
                )
            )


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sample", help="sample for ever (the unit's command)")
    s.add_argument("--every", type=int, default=15, help="seconds between samples (15)")
    s.add_argument("--keep-days", type=int, default=14, help="days of samples kept (14)")
    r = sub.add_parser("report", help="who used the machine")
    r.add_argument("--hours", type=float, default=24, help="the window, back from now (24)")
    r.add_argument("--at", help="one sample in full: HH:MM (the last one) or YYYY-MM-DD HH:MM")
    r.add_argument("--film", help="only this film's steps (its six letters)")
    r.add_argument("--top", type=int, default=12, help="rows per table (12)")
    a = ap.parse_args()
    if a.cmd == "sample":
        sample_forever(a.every, a.keep_days)
    else:
        report(a)


if __name__ == "__main__":
    main()
