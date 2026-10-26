#!/usr/bin/env python3
"""The studio machine, watched: what it is doing, what is wrong with it, and a page with both.

    python3 studio/deploy/monitor.py run             kitcut-monitor.service: every 15 s a look at
                                                     the machine, judged by the rules, sent to
                                                     Elasticsearch and kept for the page
    python3 studio/deploy/monitor.py once [--json]   one look and what the rules make of it,
                                                     printed; writes and sends nothing
    python3 studio/deploy/monitor.py rules           the rules as this machine has them
    python3 studio/deploy/monitor.py es-setup        Elasticsearch's side, made or checked: the
                                                     index templates and their lifecycle (deletion
                                                     after keep_days); safe to run again
    python3 studio/deploy/monitor.py link            the page's address with its key
    bash studio/deploy/ops.sh monitor [status|install|tunnel|link|once]   the same, from the laptop

What it looks at: CPU (busy, waiting on the disk, load), memory and swap, pressure stall (PSI: the
kernel's own count of time lost waiting for CPU, memory or the disk -- the one number that says a
machine is struggling rather than merely busy), every mount's space and inodes, the disk's
throughput and its own health (SMART: wear, spare, media errors, unsafe shutdowns), temperatures,
the graphics card, the network and whether the internet answers, the services that must run, the
units that failed, the studio's films, Elasticsearch's own health, the clock, reboots -- and every
line of the journal, which it reads as it is written for the kernel's alarms (an OOM kill, a disk
error, a hardware error, a GPU Xid, a hung task).

Where it goes:
  Elasticsearch  on this machine: machine-metrics-<week> (every look), machine-logs-<week> (the
                 whole journal), machine-events-<month> (each alert as it starts and ends). Deleted
                 by a lifecycle policy after monitor.json's keep_days. Its user may only write and
                 read those (`ops.sh monitor install` makes it in the file realm).
  the page       127.0.0.1:8770, published as machine.kitcut.ai by its own tunnel
                 (kitcut-monitor-tunnel), behind a key (STUDIO_HOME/monitor/secret.env): `link`
                 prints the address with it, and opening that once sets a cookie for a year. The
                 page does NOT read Elasticsearch: Elasticsearch is the heaviest thing on this
                 machine, and the page has to work when it is the problem. It reads this process's
                 own seven days of minutes (STUDIO_HOME/monitor/history.json.gz).
  you            STUDIO_HOME/monitor/health.json -> studio/machine_note.py -> kitcut.studio_hosts
                 -> the site's watch (sketch-studio lib/studiowatch.js), which emails the owner: once
                 when something starts, again if it gets worse or still stands a day later, and
                 "all clear" when it ends. Through the site, not from here, because the site already
                 tells when the studio stops answering or this note stops coming -- the two faults
                 a machine cannot report about itself.

Every rule holds for a while before it is told and must fall past a lower line before it is let
go (monitor.json, `rules`), so a reading that wobbles around a line is one email, not twenty.

Stdlib only, the system python3, no repo imports, capped and niced in its unit: like usage.py, it
must not depend on the venv a release changes, and must never become what it is looking for. It
restarts itself when this file or monitor.json changes (autoship pulls them).
"""

import os
import re
import sys
import glob
import gzip
import hmac
import json
import time
import socket
import base64
import fnmatch
import hashlib
import argparse
import threading
import subprocess
import urllib.error
import urllib.request
from datetime import datetime, timezone
from collections import deque
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
HOME = os.environ.get("STUDIO_HOME", "/srv/kitcut/studio")
DIR = os.path.join(HOME, "monitor")
PROC = os.environ.get("MONITOR_PROC", "/proc")
SYS = os.environ.get("MONITOR_SYS", "/sys")
HOST = socket.gethostname()
RANK = {None: 0, "info": 1, "warn": 2, "crit": 3}
COOKIE = "kcm"

# the page's charts: (column, where in a look, how a minute is summed up)
SERIES = [
    ("cpu", "cpu.pct", "avg"),
    ("iowait", "cpu.iowait", "avg"),
    ("load", "load.1", "max"),
    ("mem", "mem.used_pct", "max"),
    ("avail", "mem.avail_gb", "min"),
    ("swap", "swap.used_gb", "max"),
    ("psi_cpu", "psi.cpu_some_avg10", "max"),
    ("psi_mem", "psi.memory_full_avg10", "max"),
    ("psi_io", "psi.io_full_avg10", "max"),
    ("disk", "disk.root.pct", "max"),
    ("free", "disk.root.free_gb", "min"),
    ("rd", "io.read_mbs", "avg"),
    ("wr", "io.write_mbs", "avg"),
    ("util", "io.util_pct", "avg"),
    ("rx", "net.rx_mbit", "avg"),
    ("tx", "net.tx_mbit", "avg"),
    ("ping", "net.ping_ms", "avg"),
    ("t_cpu", "temp.cpu", "max"),
    ("t_nvme", "temp.nvme", "max"),
    ("t_gpu", "gpu.temp", "max"),
    ("gpu", "gpu.util", "avg"),
    ("vram", "gpu.mem_pct", "max"),
    ("watts", "gpu.power_w", "avg"),
    ("films", "studio.running", "max"),
    ("es_heap", "es.heap_pct", "max"),
]


# ------------------------------------------------------------------------------------ settings
def merge(a, b):
    for k, v in b.items():
        if isinstance(v, dict) and isinstance(a.get(k), dict):
            merge(a[k], v)
        else:
            a[k] = v
    return a


def config():
    """monitor.json beside this file, with this machine's STUDIO_HOME/monitor/monitor.local.json
    over it."""
    with open(os.path.join(HERE, "monitor.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    try:
        with open(os.path.join(DIR, "monitor.local.json"), encoding="utf-8") as f:
            merge(cfg, json.load(f))
    except (OSError, ValueError):
        pass
    return cfg


def secret(name):
    """NAME=value from STUDIO_HOME/monitor/secret.env (the page's key, Elasticsearch's user)."""
    out = ""
    for line in read(os.path.join(DIR, "secret.env")).splitlines():
        k, eq, v = line.partition("=")
        if eq and k.strip() == name:
            out = v.strip().strip("\"'")
    return out


def read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def run(cmd, timeout=10):
    """(exit status, stdout); -1 and the reason when it could not run."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout
    except (OSError, subprocess.TimeoutExpired) as e:
        return -1, str(e)


def save_json(path, obj, gz=False):
    tmp = path + ".tmp"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = json.dumps(obj, separators=(",", ":")).encode()
    with open(tmp, "wb") as f:
        f.write(gzip.compress(data) if gz else data)
    os.replace(tmp, path)


def load_json(path, gz=False):
    try:
        with open(path, "rb") as f:
            data = f.read()
        return json.loads(gzip.decompress(data) if gz else data)
    except (OSError, ValueError, EOFError):
        return None


def clock(t):
    """A moment for a person: '11:32' today, 'Oct 25 11:32' before."""
    d = datetime.fromtimestamp(t)
    return d.strftime("%H:%M" if d.date() == datetime.now().date() else "%b %d %H:%M")


def span(s):
    s = int(s)
    if s < 120:
        return "%d s" % s
    if s < 7200:
        return "%d min" % (s // 60)
    if s < 172800:
        return "%.1f h" % (s / 3600)
    return "%d days" % (s // 86400)


def gb(mb):
    return None if mb is None else round(mb / 1024, 1)


def dig(d, path):
    for k in path.split("."):
        if not isinstance(d, dict):
            return None
        d = d.get(k)
    return d


# ------------------------------------------------------------------------------------- readers
def cpu_ticks():
    f = read(os.path.join(PROC, "stat")).split("\n", 1)[0].split()[1:]
    v = [int(x) for x in f if x.isdigit()] + [0] * 8
    return {"total": sum(v[:8]), "idle": v[3] + v[4], "iowait": v[4], "steal": v[7]}


def meminfo():
    m = {}
    for ln in read(os.path.join(PROC, "meminfo")).splitlines():
        k, _, rest = ln.partition(":")
        p = rest.split()
        if p and p[0].isdigit():
            m[k] = int(p[0]) // 1024  # MB
    return m


def pressure():
    out = {}
    for k in ("cpu", "memory", "io"):
        for ln in read(os.path.join(PROC, "pressure", k)).splitlines():
            kind, *pairs = ln.split()
            d = dict(p.split("=", 1) for p in pairs if "=" in p)
            for w in ("avg10", "avg60", "avg300"):
                if w in d:
                    out["%s_%s_%s" % (k, kind, w)] = float(d[w])
    return out


def loadavg():
    p = read(os.path.join(PROC, "loadavg")).split()
    return {"1": float(p[0]), "5": float(p[1]), "15": float(p[2])} if len(p) > 2 else {}


def mounts(named):
    out = {}
    for name, path in named.items():
        try:
            s = os.statvfs(path)
        except OSError:
            continue
        total, free = s.f_blocks * s.f_frsize, s.f_bavail * s.f_frsize
        used = total - s.f_bfree * s.f_frsize
        out[name] = {
            "path": path,
            "pct": round(100 * used / max(used + free, 1), 1),
            "free_gb": round(free / 1e9, 1),
            "total_gb": round(total / 1e9, 1),
            "inodes_pct": round(100 * (s.f_files - s.f_ffree) / s.f_files, 1)
            if s.f_files
            else None,
        }
    return out


def diskstat(dev):
    for ln in read(os.path.join(PROC, "diskstats")).splitlines():
        p = ln.split()
        if len(p) > 13 and p[2] == dev:
            return {"rs": int(p[5]), "ws": int(p[9]), "io_ms": int(p[12])}
    return None


def default_iface():
    for ln in read(os.path.join(PROC, "net", "route")).splitlines()[1:]:
        p = ln.split()
        if len(p) > 2 and p[1] == "00000000":
            return p[0]
    return None


def netdev(iface):
    for ln in read(os.path.join(PROC, "net", "dev")).splitlines()[2:]:
        name, _, rest = ln.partition(":")
        p = rest.split()
        if name.strip() == iface and len(p) > 11:
            return {"rx": int(p[0]), "tx": int(p[8]), "err": int(p[2]) + int(p[3]) + int(p[10])}
    return None


def temps():
    """CPU package, the NVMe's composite, the first fan: from hwmon, no tools needed."""
    out = {}
    for d in sorted(glob.glob(os.path.join(SYS, "class", "hwmon", "hwmon*"))):
        name = read(os.path.join(d, "name")).strip()
        if name == "coretemp":
            vals = {}
            for lab in glob.glob(os.path.join(d, "temp*_label")):
                v = read(lab.replace("_label", "_input")).strip()
                if v.lstrip("-").isdigit():
                    vals[read(lab).strip()] = int(v) / 1000
            pkg = [v for k, v in vals.items() if k.startswith("Package")]
            if pkg or vals:
                out["cpu"] = max(pkg or vals.values())
        elif name == "nvme" and "nvme" not in out:
            v = read(os.path.join(d, "temp1_input")).strip()
            if v.lstrip("-").isdigit():
                out["nvme"] = int(v) / 1000
        fan = read(os.path.join(d, "fan1_input")).strip()
        if fan.isdigit() and "fan_rpm" not in out:
            out["fan_rpm"] = int(fan)
    return out


GPU_Q = (
    "name,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw,"
    "clocks_throttle_reasons.active,fan.speed,pstate"
)


def gpu():
    rc, out = run(["nvidia-smi", "--query-gpu=" + GPU_Q, "--format=csv,noheader,nounits"], 8)
    if rc != 0 or not out.strip():
        return {"error": (out.strip() or "nvidia-smi exited %d" % rc)[:200]}
    p = [x.strip() for x in out.splitlines()[0].split(",")] + [""] * 9

    def f(x):
        try:
            return float(x)
        except ValueError:
            return None

    used, total = f(p[2]), f(p[3])
    g = {
        "name": p[0],
        "util": f(p[1]),
        "mem_mb": used,
        "mem_total_mb": total,
        "mem_pct": round(100 * used / total, 1) if used is not None and total else None,
        "temp": f(p[4]),
        "power_w": f(p[5]),
        "throttle": p[6],
        "fan_pct": f(p[7]),
        "pstate": p[8],
        "procs": [],
    }
    rc, out = run(
        [
            "nvidia-smi",
            "--query-compute-apps=pid,process_name,used_memory",
            "--format=csv,noheader,nounits",
        ],
        8,
    )
    for ln in out.splitlines() if rc == 0 else []:
        q = [x.strip() for x in ln.split(",")]
        if len(q) == 3:
            g["procs"].append({"pid": q[0], "name": os.path.basename(q[1]), "mb": f(q[2])})
    return g


def smart(dev):
    """The NVMe's own health log (smartctl through sudo: the service's user has it)."""
    rc, out = run(["sudo", "-n", "smartctl", "-j", "-a", dev], 30)
    try:
        j = json.loads(out)
    except ValueError:
        return {"error": (out.strip() or "smartctl exited %d" % rc)[:200]}
    h = j.get("nvme_smart_health_information_log") or {}
    return {
        "model": j.get("model_name"),
        "passed": (j.get("smart_status") or {}).get("passed"),
        "critical_warning": h.get("critical_warning"),
        "temp": h.get("temperature"),
        "spare_pct": h.get("available_spare"),
        "spare_threshold": h.get("available_spare_threshold"),
        "used_pct": h.get("percentage_used"),
        "written_tb": round((h.get("data_units_written") or 0) * 512000 / 1e12, 1),
        "media_errors": h.get("media_errors"),
        "error_log": h.get("num_err_log_entries"),
        "unsafe_shutdowns": h.get("unsafe_shutdowns"),
        "power_on_hours": h.get("power_on_hours"),
    }


UNIT_PROPS = (
    "Description,UnitFileState,LoadState,ActiveState,SubState,Result,ActiveEnterTimestamp,NRestarts"
)


def unit_id(name):
    """A unit's full name: "elasticsearch" is elasticsearch.service."""
    kinds = (".service", ".socket", ".timer", ".path", ".mount", ".target", ".scope", ".slice")
    return name if name.endswith(kinds) else name + ".service"


def show(names, props):
    """systemctl show for several units in one call: {name as asked: {property: value}}. Matched
    back by Id, not by order: a name systemd cannot parse is left out of its answer."""
    if not names:
        return {}
    rc, txt = run(["systemctl", "show", "--no-pager", "-p", "Id," + props, *map(unit_id, names)])
    by_id = {}
    for b in txt.split("\n\n"):
        d = dict(ln.split("=", 1) for ln in b.splitlines() if "=" in ln)
        if d.get("Id"):
            by_id[d["Id"]] = d
    return {n: by_id[unit_id(n)] for n in names if unit_id(n) in by_id}


def unit_states(names):
    """{name: {active, sub, result, since, desc, restarts}} for exact names (systemctl show, one
    call) and globs (list-units: only the instances loaded now)."""
    out = {}
    globs = [n for n in names if "*" in n]
    if globs:
        rc, txt = run(
            ["systemctl", "list-units", "--all", "--plain", "--no-legend", "--no-pager", *globs]
        )
        for ln in txt.splitlines():
            p = ln.split(None, 4)
            if len(p) >= 4:
                out[p[0]] = {
                    "active": p[2],
                    "sub": p[3],
                    "desc": p[4] if len(p) > 4 else "",
                    "glob": True,
                }
    for name, d in show([n for n in names if "*" not in n], UNIT_PROPS).items():
        out[name] = {
            "active": d.get("ActiveState", "?"),
            "sub": d.get("SubState", "?"),
            "result": d.get("Result"),
            "loaded": d.get("LoadState"),
            "enabled": d.get("UnitFileState"),
            "since": d.get("ActiveEnterTimestamp") or None,
            "desc": d.get("Description", ""),
            "restarts": int(d["NRestarts"]) if d.get("NRestarts", "").isdigit() else None,
        }
    return out


def failed_units():
    rc, txt = run(["systemctl", "list-units", "--failed", "--plain", "--no-legend", "--no-pager"])
    return [ln.split()[0] for ln in txt.splitlines() if ln.strip()] if rc == 0 else []


def last_runs(names):
    """A oneshot's last run: {name: {result, status, at, active}}."""
    return {
        name: {
            "result": d.get("Result"),
            "status": d.get("ExecMainStatus"),
            "at": d.get("ExecMainExitTimestamp") or None,
            "active": d.get("ActiveState"),
        }
        for name, d in show(
            names, "Result,ExecMainStatus,ExecMainExitTimestamp,ActiveState"
        ).items()
    }


def http_json(url, timeout=3, auth=None):
    req = urllib.request.Request(url, headers={"Authorization": auth} if auth else {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read() or b"null")
    except (OSError, ValueError, urllib.error.URLError):
        return None


def internet(probes):
    """Does the outside world answer (a TCP connect to well-known resolvers), and how fast."""
    best = None
    for host, port in probes:
        t = time.monotonic()
        try:
            with socket.create_connection((host, port), timeout=3):
                best = (time.monotonic() - t) * 1000
                break
        except OSError:
            continue
    return {"ok": best is not None, "ms": None if best is None else round(best, 1)}


def ntp_synced():
    rc, out = run(["timedatectl", "show", "-p", "NTPSynchronized", "--value"], 5)
    return None if rc != 0 else out.strip() == "yes"


def boot_id():
    return read(os.path.join(PROC, "sys", "kernel", "random", "boot_id")).strip()


def uptime_s():
    p = read(os.path.join(PROC, "uptime")).split()
    return float(p[0]) if p else None


def usage_top(cfg, n=8):
    """Who holds the memory now: the last line usage.py wrote (kitcut-usage.service)."""
    path = os.path.join(HOME, cfg["usage_dir"], datetime.now().strftime("%Y-%m-%d") + ".jsonl")
    try:
        with open(path, "rb") as f:
            f.seek(max(os.path.getsize(path) - 65536, 0))
            last = f.read().splitlines()[-1]
        row = json.loads(last)
    except (OSError, ValueError, IndexError):
        return None
    groups = sorted(row.get("groups", []), key=lambda g: -(g.get("anon") or g.get("mb") or 0))
    return {
        "at": row.get("t"),
        "groups": groups[:n],
        "procs": sorted(row.get("procs", []), key=lambda p: -(p.get("mb") or 0))[:n],
    }


def last_boot_clean():
    """Did the boot before this one end in a shutdown (True), a power cut or a freeze (False)?"""
    rc, out = run(["journalctl", "-b", "-1", "-n", "400", "--no-pager", "-q", "-o", "cat"], 20)
    if rc != 0 or not out.strip():
        return None
    marks = (
        "Reached target reboot.target",
        "Reached target poweroff.target",
        "System Reboot",
        "System Power Off",
        "systemd-shutdown",
        "Reached target Power-Off",
        "Reached target Reboot",
    )
    return any(m in out for m in marks)


# ------------------------------------------------------------------------------------- a look
class Looker:
    """One look at the machine after another: rates (CPU, disk, network) come from the
    difference with the look before, the slow readings (GPU, units, SMART, ...) at their own
    pace and reused in between."""

    PACE = {
        "gpu": 30,
        "units": 60,
        "studio": 30,
        "es": 60,
        "net": 30,
        "clock": 600,
        "smart": 1800,
        "top": 60,
    }

    def __init__(self, cfg, es=None):
        self.cfg, self.es = cfg, es
        self.prev = None
        self.slow, self.when = {}, {}
        self.iface = default_iface()

    def due(self, what, now):
        if now - self.when.get(what, 0) >= self.PACE[what]:
            self.when[what] = now
            return True
        return False

    def look(self, now=None):
        now = now or time.time()
        cfg = self.cfg
        t, cpu, dk = time.monotonic(), cpu_ticks(), diskstat(cfg["disk_device"])
        nd = netdev(self.iface) if self.iface else None
        m = meminfo()
        s = {"@timestamp": datetime.fromtimestamp(now, timezone.utc).isoformat(timespec="seconds")}
        s["host"] = {"name": HOST}
        total = m.get("MemTotal") or 1
        avail = m.get("MemAvailable", 0)
        sw_t, sw_f = m.get("SwapTotal", 0), m.get("SwapFree", 0)
        s["mem"] = {
            "total_mb": total,
            "avail_mb": avail,
            "avail_gb": gb(avail),
            "avail_pct": round(100 * avail / total, 1),
            "used_pct": round(100 * (total - avail) / total, 1),
            "cached_mb": m.get("Cached"),
            "dirty_mb": m.get("Dirty"),
        }
        s["swap"] = {
            "total_mb": sw_t,
            "used_mb": sw_t - sw_f,
            "used_gb": gb(sw_t - sw_f),
            "used_pct": round(100 * (sw_t - sw_f) / sw_t, 1) if sw_t else 0,
        }
        s["psi"] = pressure()
        s["load"] = loadavg()
        s["disk"] = mounts(cfg["mounts"])
        s["temp"] = temps()
        if self.prev:
            t0, c0, d0, n0 = self.prev
            dt = max(t - t0, 1e-3)
            dtot = max(cpu["total"] - c0["total"], 1)
            s["cpu"] = {
                "pct": round(100 * (1 - (cpu["idle"] - c0["idle"]) / dtot), 1),
                "iowait": round(100 * (cpu["iowait"] - c0["iowait"]) / dtot, 1),
                "steal": round(100 * (cpu["steal"] - c0["steal"]) / dtot, 1),
                "cores": os.cpu_count(),
            }
            if dk and d0:
                s["io"] = {
                    "read_mbs": round((dk["rs"] - d0["rs"]) * 512 / 1e6 / dt, 2),
                    "write_mbs": round((dk["ws"] - d0["ws"]) * 512 / 1e6 / dt, 2),
                    "util_pct": round(min(100, (dk["io_ms"] - d0["io_ms"]) / 10 / dt), 1),
                }
            if nd and n0:
                s["net"] = {
                    "iface": self.iface,
                    "rx_mbit": round((nd["rx"] - n0["rx"]) * 8 / 1e6 / dt, 2),
                    "tx_mbit": round((nd["tx"] - n0["tx"]) * 8 / 1e6 / dt, 2),
                    "errors": nd["err"],
                }
        self.prev = (t, cpu, dk, nd)

        if self.due("gpu", now):
            self.slow["gpu"] = gpu()
        if self.due("net", now):
            self.slow["internet"] = internet(cfg["internet_probes"])
        if self.due("studio", now):
            h = http_json(cfg["studio_health"])
            self.slow["studio"] = (
                {
                    "up": True,
                    "running": h.get("running"),
                    "queued": h.get("queued"),
                    "release": h.get("release"),
                }
                if isinstance(h, dict)
                else {"up": False}
            )
        if self.due("units", now):
            u = cfg["units"]
            self.slow["units"] = unit_states(u["watch"] + u["page_only"])
            self.slow["failed"] = failed_units()
            self.slow["last_run"] = last_runs(u["last_run"])
        if self.due("es", now) and self.es:
            self.slow["es"] = self.es.health()
        if self.due("clock", now):
            self.slow["ntp"] = ntp_synced()
        if self.due("smart", now):
            self.slow["smart"] = smart(cfg["smart_device"])
        if self.due("top", now):
            self.slow["top"] = usage_top(cfg)
        g = self.slow.get("gpu") or {}
        s["gpu"] = {k: g.get(k) for k in ("util", "mem_pct", "mem_mb", "temp", "power_w", "error")}
        net = s.setdefault("net", {})
        net["ping_ms"] = (self.slow.get("internet") or {}).get("ms")
        net["online"] = (self.slow.get("internet") or {}).get("ok")
        s["studio"] = {k: v for k, v in (self.slow.get("studio") or {}).items() if k != "release"}
        s["es"] = {
            k: v for k, v in (self.slow.get("es") or {}).items() if k in ("heap_pct", "status_n")
        }
        s["uptime_s"] = uptime_s()
        return s


# ------------------------------------------------------------------------------------- the rules
class Rules:
    """What stands wrong, from one look after another. A condition must hold `for_s` before it
    counts and must fall past its clear line before it is let go; a level only rises while an
    alert stands (warn -> crit), so a reading that hovers near the crit line is not "better, then
    worse" every minute. Events (an OOM kill, a reboot, an outage that ended) stand for
    event_keep_s so that the note carries them to the site, then go."""

    def __init__(self, cfg, state=None):
        self.cfg = cfg
        self.st = (state or {}).get("rules", {})
        self.events = [e for e in (state or {}).get("events", []) if isinstance(e, dict)]
        self.baseline = (state or {}).get("baseline", {})
        self.alerts = []

    def state(self):
        return {"rules": self.st, "events": self.events, "baseline": self.baseline}

    def hold(self, key, now, value, warn, crit=None, clear=None, for_s=0, above=True):
        """The level that stands for `key` (None, "warn", "crit") after this reading."""
        s = self.st.setdefault(key, {})
        if value is None:
            return s.get("level") if s.get("on") else None

        def past(line):
            return line is not None and (value >= line if above else value <= line)

        lvl = "crit" if past(crit) else "warn" if past(warn) else None
        if s.get("on"):
            line = warn if clear is None else clear
            if (value < line) if above else (value > line):
                self.st.pop(key, None)
                return None
            if lvl == "crit":
                s["level"] = "crit"
            return s["level"]
        if lvl is None:
            self.st.pop(key, None)
            return None
        s.setdefault("since", now)
        if now - s["since"] >= for_s:
            s.update(on=True, level=lvl)
            return lvl
        return None

    def since(self, key):
        return (self.st.get(key) or {}).get("since")

    def add(self, key, level, subject, rows):
        if level:
            self.alerts.append(
                {
                    "key": key,
                    "level": level,
                    "subject": subject,
                    "rows": rows,
                    "since": self.since(key),
                    "kind": "state",
                    "tell": True,
                }
            )

    def event(self, key, level, subject, rows, now, tell=True):
        """An event: one key, counted when it comes again before it is let go."""
        for e in self.events:
            if e["key"] == key:
                e["count"] = e.get("count", 1) + 1
                e["last"] = now
                return e
        e = {
            "key": key,
            "level": level,
            "subject": subject,
            "rows": rows,
            "at": now,
            "last": now,
            "kind": "event",
            "tell": tell,
            "count": 1,
        }
        self.events.append(e)
        return e

    def judge(self, s, slow, now, hist=None):
        """Every rule against one look; returns the alerts and events that stand."""
        r, self.alerts = self.cfg["rules"], []
        page = self.cfg.get("page_url", "")
        top = holders(slow.get("top"))
        mem, swap, psi = s.get("mem", {}), s.get("swap", {}), s.get("psi", {})

        c = r["memory"]
        lvl = self.hold(
            "memory",
            now,
            mem.get("avail_pct"),
            c["warn_below_pct"],
            c["crit_below_pct"],
            c["clear_above_pct"],
            c["for_s"],
            above=False,
        )
        self.add(
            "memory",
            lvl,
            "kc-local is low on memory: %s GB free of %s GB"
            % (mem.get("avail_gb"), gb(mem.get("total_mb"))),
            [
                ["Free", "%s GB (%s%%)" % (mem.get("avail_gb"), mem.get("avail_pct"))],
                ["Swap in use", "%s of %s GB" % (swap.get("used_gb"), gb(swap.get("total_mb")))],
                ["Holding the most", top or "?"],
                [
                    "What happens next",
                    "past the end the kernel kills the biggest job; a film step dies first",
                ],
                ["Page", page],
            ],
        )

        c = r["mem_stall"]
        v = psi.get("memory_full_avg60")
        lvl = self.hold("mem_stall", now, v, c["warn_above"], None, c["clear_below"], c["for_s"])
        self.add(
            "mem_stall",
            lvl,
            "kc-local is thrashing: everything waited on memory %s%% of the last minute" % v,
            [
                ["Free memory", "%s GB" % mem.get("avail_gb")],
                ["Swap in use", "%s GB" % swap.get("used_gb")],
                ["Holding the most", top or "?"],
                ["Page", page],
            ],
        )

        c = r["swap"]
        lvl = self.hold(
            "swap",
            now,
            swap.get("used_pct"),
            c["warn_above_pct"],
            None,
            c["clear_below_pct"],
            c["for_s"],
        )
        self.add(
            "swap",
            lvl,
            "kc-local's swap is %s%% full" % swap.get("used_pct"),
            [
                ["Swap in use", "%s of %s GB" % (swap.get("used_gb"), gb(swap.get("total_mb")))],
                ["Free memory", "%s GB" % mem.get("avail_gb")],
                ["Holding the most", top or "?"],
                ["Page", page],
            ],
        )

        c = r["cpu_stall"]
        v = psi.get("cpu_some_avg300")
        lvl = self.hold("cpu_stall", now, v, c["warn_above"], None, c["clear_below"], c["for_s"])
        self.add(
            "cpu_stall",
            lvl,
            "kc-local has been short of CPU for over an hour",
            [
                ["Waiting for a CPU", "%s%% of the last 5 minutes" % v],
                ["Films being made", str((slow.get("studio") or {}).get("running"))],
                ["Load", str(s.get("load", {}).get("5"))],
                ["Page", page],
            ],
        )

        disks = s.get("disk", {})
        root = disks.get("root") or {}
        c = r["disk"]
        lvl = self.hold(
            "disk",
            now,
            root.get("pct"),
            c["warn_above_pct"],
            c["crit_above_pct"],
            c["clear_below_pct"],
        )
        self.add(
            "disk",
            lvl,
            "kc-local's disk is %s%% full: %s GB left" % (root.get("pct"), root.get("free_gb")),
            [
                ["Free", "%s GB of %s GB" % (root.get("free_gb"), root.get("total_gb"))],
                [
                    "What to do",
                    "ops.sh prune --plan says what can go; at 95% Elasticsearch stops taking writes, "
                    "and a full disk stops every film",
                ],
                ["Page", page],
            ],
        )
        if hist is not None:
            c = r["disk_trend"]
            hours = fill_hours(hist, c["window_h"], c["min_history_h"])
            key = "disk_trend"
            if hours is not None and hours < c["warn_hours"]:
                self.st.setdefault(key, {"since": now})
                self.st[key]["hours"] = hours
            elif hours is None or hours > c["warn_hours"] * 1.5:
                self.st.pop(key, None)
        if "disk_trend" in self.st and root.get("free_gb") is not None:
            h = self.st["disk_trend"].get("hours")
            self.add(
                "disk_trend",
                "warn",
                "At this rate kc-local's disk is full in about %s" % span(h * 3600),
                [
                    ["Free now", "%s GB" % root.get("free_gb")],
                    [
                        "Filling at",
                        "%.1f GB an hour (the last %d h)"
                        % (root["free_gb"] / max(h, 0.01), r["disk_trend"]["window_h"]),
                    ],
                    [
                        "What to do",
                        "ops.sh prune --plan; sudo du -xh --max-depth=2 /srv | sort -h | tail",
                    ],
                    ["Page", page],
                ],
            )
        boot = disks.get("boot") or {}
        lvl = self.hold("boot_disk", now, boot.get("pct"), r["boot_disk"]["warn_above_pct"])
        self.add(
            "boot_disk",
            lvl,
            "/boot is %s%% full: the next kernel update will fail" % boot.get("pct"),
            [["What to do", "sudo apt autoremove --purge (old kernels)"]],
        )
        for name, d in disks.items():
            lvl = self.hold(
                "inodes_" + name, now, d.get("inodes_pct"), r["inodes"]["warn_above_pct"]
            )
            self.add(
                "inodes_" + name,
                lvl,
                "%s has used %s%% of its inodes" % (d["path"], d.get("inodes_pct")),
                [
                    [
                        "What it means",
                        "millions of small files: no new file can be made once they run out",
                    ]
                ],
            )

        t, g = s.get("temp", {}), s.get("gpu", {})
        for key, val, name in (
            ("cpu_temp", t.get("cpu"), "CPU"),
            ("nvme_temp", t.get("nvme"), "disk"),
            ("gpu_temp", g.get("temp"), "graphics card"),
        ):
            c = r[key]
            lvl = self.hold(key, now, val, c["warn_above_c"], None, c["clear_below_c"], c["for_s"])
            self.add(
                key,
                lvl,
                "kc-local's %s is running hot: %s °C" % (name, val),
                [
                    ["Fan", "%s rpm" % t.get("fan_rpm")],
                    ["CPU busy", "%s%%" % s.get("cpu", {}).get("pct")],
                    [
                        "What to do",
                        "check the vents and the room; it slows itself down before it fails",
                    ],
                ],
            )

        sm = slow.get("smart") or {}
        if sm and "error" not in sm:
            if sm.get("critical_warning"):
                self.add(
                    "nvme_critical",
                    "crit",
                    "kc-local's disk raised its own critical warning (%s)" % sm["critical_warning"],
                    smart_rows(sm),
                )
            if (sm.get("used_pct") or 0) >= r["nvme_wear"]["warn_used_pct"]:
                self.add(
                    "nvme_wear",
                    "warn",
                    "kc-local's disk is %s%% worn" % sm["used_pct"],
                    smart_rows(sm),
                )
            if (
                sm.get("spare_pct") is not None
                and sm.get("spare_threshold") is not None
                and sm["spare_pct"] <= sm["spare_threshold"]
            ):
                self.add(
                    "nvme_spare",
                    "crit",
                    "kc-local's disk has run out of spare blocks",
                    smart_rows(sm),
                )
            me = sm.get("media_errors")
            if me is not None:
                was = self.baseline.setdefault("media_errors", me)
                if me > was:
                    self.event(
                        "nvme_media_%d" % me,
                        "crit",
                        "kc-local's disk found %d new media errors" % (me - was),
                        smart_rows(sm),
                        now,
                    )
                    self.baseline["media_errors"] = me
        gp = slow.get("gpu") or {}
        if gp and "error" not in gp:
            self.baseline["gpu_seen"] = True
        gone = 1 if gp.get("error") and self.baseline.get("gpu_seen") else 0
        lvl = self.hold("gpu_gone", now, gone, 1, for_s=120)
        self.add(
            "gpu_gone",
            lvl,
            "kc-local's graphics card stopped answering",
            [
                ["nvidia-smi says", str(gp.get("error"))],
                ["What to do", "a reboot usually brings it back; journalctl -k | grep -i xid"],
            ],
        )

        u = self.cfg["units"]
        units = slow.get("units") or {}
        for name in u["watch"]:
            st = units.get(name)
            if not st or st.get("loaded") == "not-found":
                continue
            # a unit nobody enabled (started by hand) is let be when it stops; one that should
            # start with the machine is not
            wanted = st.get("enabled") in ("enabled", "static", "alias", "indirect", "generated")
            v = 0 if not wanted or st["active"] in ("active", "reloading", "activating") else 1
            lvl = self.hold("unit_" + name, now, v, 1, for_s=u["for_s"])
            self.add(
                "unit_" + name,
                lvl,
                "%s is not running on kc-local" % name,
                [
                    ["State", "%s (%s)" % (st["active"], st["sub"])],
                    ["What it is", st.get("desc") or name],
                    ["Last result", str(st.get("result"))],
                    [
                        "What to do",
                        "sudo systemctl status %s; journalctl -u %s -n 50" % (name, name),
                    ],
                    ["Page", page],
                ],
            )
        watched = set(u["watch"]) | {n + ".service" for n in u["watch"]}
        for unit in slow.get("failed") or []:
            if unit in watched or not any(fnmatch.fnmatch(unit, g) for g in u["failed_tell"]):
                continue
            self.add(
                "failed_" + unit,
                "warn",
                "%s failed on kc-local" % unit,
                [
                    [
                        "What to do",
                        "journalctl -u %s -n 80; once fixed or no longer wanted: "
                        "sudo systemctl reset-failed %s" % (unit, unit),
                    ],
                    ["Page", page],
                ],
            )
        for name, lr in (slow.get("last_run") or {}).items():
            if lr.get("result") not in (None, "success") and lr.get("active") != "activating":
                self.add(
                    "lastrun_" + name,
                    "warn",
                    "%s failed its last run" % name,
                    [
                        ["Result", "%s (exit %s)" % (lr["result"], lr.get("status"))],
                        ["When", str(lr.get("at"))],
                        ["What to do", "journalctl -u %s -n 80" % name],
                    ],
                )

        es = slow.get("es") or {}
        if es.get("status") == "red":
            self.add(
                "es_red",
                "crit",
                "Elasticsearch on kc-local is red: some of its data cannot be read",
                [
                    ["Unassigned shards", str(es.get("unassigned"))],
                    ["What to do", "GET _cluster/allocation/explain"],
                ],
            )
        c = r["es_heap"]
        lvl = self.hold(
            "es_heap",
            now,
            es.get("heap_pct"),
            c["warn_above_pct"],
            None,
            c["clear_below_pct"],
            c["for_s"],
        )
        self.add(
            "es_heap",
            lvl,
            "Elasticsearch's memory is %s%% full" % es.get("heap_pct"),
            [
                ["Heap", "%s of %s GB" % (es.get("heap_used_gb"), es.get("heap_max_gb"))],
                [
                    "What happens next",
                    "it refuses writes (circuit breakers) or stalls in garbage collection",
                ],
            ],
        )
        ship = slow.get("ship") or {}
        if (
            ship.get("pending")
            and ship.get("since_ok") is not None
            and ship["since_ok"] > r["es_ship"]["warn_after_s"]
        ):
            self.add(
                "es_ship",
                "warn",
                "kc-local's readings have not reached Elasticsearch for %s"
                % span(ship["since_ok"]),
                [
                    ["Last error", str(ship.get("error"))],
                    ["Waiting to be sent", str(ship.get("pending"))],
                ],
            )

        lvl = self.hold(
            "clock", now, 1 if slow.get("ntp") is False else 0, 1, for_s=r["clock"]["for_s"]
        )
        self.add(
            "clock",
            lvl,
            "kc-local's clock is not synchronised",
            [
                [
                    "What to do",
                    "timedatectl timesync-status; signed requests (R2, Google) fail once it drifts",
                ]
            ],
        )

        keep = self.cfg["event_keep_s"]
        self.events = [e for e in self.events if now - e.get("last", e["at"]) < keep]
        return self.alerts + self.events


def holders(top):
    """'elasticsearch 4.5 GB, film abc123 render 2.0 GB, ...' from usage.py's last line."""
    if not top:
        return None
    out = []
    for g in top.get("groups", [])[:5]:
        mb = g.get("anon") if g.get("anon") is not None else g.get("mb")
        out.append("%s %.1f GB" % (g.get("who"), (mb or 0) / 1024))
    return ", ".join(out)


def smart_rows(sm):
    return [
        ["Model", str(sm.get("model"))],
        ["Worn", "%s%%" % sm.get("used_pct")],
        ["Spare", "%s%% (threshold %s%%)" % (sm.get("spare_pct"), sm.get("spare_threshold"))],
        ["Media errors", str(sm.get("media_errors"))],
        ["Written", "%s TB" % sm.get("written_tb")],
        ["What to do", "copy what matters off it now (ops.sh backup status), then replace it"],
    ]


def fill_hours(hist, window_h, min_h):
    """Hours until the root disk is full at the rate of the last `window_h` (least squares on the
    minutes' free space); None when it is not filling or there is too little history."""
    rows = hist.rows
    if not rows:
        return None
    i = hist.col("free")
    cut = rows[-1][0] - window_h * 3600
    pts = [(r[0], r[i]) for r in rows if r[0] >= cut and r[i] is not None]
    if len(pts) < 30 or pts[-1][0] - pts[0][0] < min_h * 3600:
        return None
    n = len(pts)
    mx = sum(p[0] for p in pts) / n
    my = sum(p[1] for p in pts) / n
    den = sum((p[0] - mx) ** 2 for p in pts)
    if not den:
        return None
    slope = sum((p[0] - mx) * (p[1] - my) for p in pts) / den * 3600  # GB an hour
    if slope >= -0.01:
        return None
    return round(pts[-1][1] / -slope, 1)


# ------------------------------------------------------------------------------------ the journal
class Journal(threading.Thread):
    """The journal as it is written (journalctl -f), from where the last run stopped (its cursor,
    so the lines written while this was down -- the OOM kill that took it, the end of the boot
    before -- are read too). Each line goes to Elasticsearch; the kernel's alarms become events."""

    def __init__(self, cfg, sink):
        super().__init__(daemon=True)
        self.cfg, self.sink = cfg, sink
        self.path = os.path.join(DIR, "journal.cursor")
        self.cursor = read(self.path).strip() or None
        self.pats = [dict(p, rx=re.compile(p["re"])) for p in cfg["journal"]]

    def save(self):
        if self.cursor:
            with open(self.path + ".tmp", "w") as f:
                f.write(self.cursor)
            os.replace(self.path + ".tmp", self.path)

    def run(self):
        while True:
            cmd = ["journalctl", "-f", "-o", "json", "--no-pager"]
            cmd += ["--after-cursor", self.cursor] if self.cursor else ["-n", "0"]
            started = time.monotonic()
            try:
                p = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    errors="replace",
                    bufsize=1,
                )
                for line in p.stdout:
                    try:
                        e = json.loads(line)
                    except ValueError:
                        continue
                    self.cursor = e.get("__CURSOR") or self.cursor
                    self.sink(entry(e), self.match(e))
                p.wait()
            except OSError as e:
                print("monitor: journalctl: %r" % e, file=sys.stderr, flush=True)
            if time.monotonic() - started < 5:
                self.cursor = None  # a cursor the journal no longer has: start from now
            time.sleep(5)

    def match(self, e):
        if e.get("_TRANSPORT") != "kernel":
            return None
        msg = text(e.get("MESSAGE"))
        for p in self.pats:
            m = p["rx"].search(msg)
            if m:
                g = [m.group(0)] + [x or "" for x in m.groups()]
                try:
                    subject = p["subject"].format(*g)
                except (IndexError, KeyError):
                    subject = p["subject"]
                return {
                    "kind": p["kind"],
                    "level": p["level"],
                    "tell": p["tell"],
                    "subject": subject[:200],
                    "line": msg[:500],
                }
        return None


def text(m):
    if isinstance(m, list):  # the journal hands binary messages over as bytes
        return bytes(x for x in m if isinstance(x, int) and 0 <= x < 256).decode("utf-8", "replace")
    return str(m or "")


PRIO = ["emerg", "alert", "crit", "err", "warning", "notice", "info", "debug"]


def entry(e):
    try:
        ts = int(e.get("__REALTIME_TIMESTAMP", "0")) / 1e6
    except ValueError:
        ts = time.time()
    prio = int(e["PRIORITY"]) if str(e.get("PRIORITY", "")).isdigit() else 6
    return {
        "@timestamp": datetime.fromtimestamp(ts, timezone.utc).isoformat(timespec="milliseconds"),
        "t": ts,
        "host": {"name": HOST},
        "unit": e.get("_SYSTEMD_UNIT") or e.get("UNIT") or "",
        "ident": e.get("SYSLOG_IDENTIFIER") or e.get("_COMM") or "",
        "prio": prio,
        "level": PRIO[prio] if prio < len(PRIO) else str(prio),
        "transport": e.get("_TRANSPORT", ""),
        "pid": e.get("_PID"),
        "msg": text(e.get("MESSAGE"))[:8000],
    }


# ---------------------------------------------------------------------------- Elasticsearch
class ES:
    """Elasticsearch on this machine, by plain HTTP (no client library): bulk writes, its health,
    and its side of the setup (index templates whose lifecycle deletes old days)."""

    def __init__(self, cfg):
        self.cfg = cfg["elasticsearch"]
        self.url = self.cfg["url"].rstrip("/")
        user, pw = secret("ES_USER"), secret("ES_PASSWORD")
        self.auth = (
            "Basic " + base64.b64encode(("%s:%s" % (user, pw)).encode()).decode() if user else None
        )
        self.error = None

    def call(self, method, path, body=None, ndjson=False, timeout=15):
        data = None
        if body is not None:
            data = body.encode() if isinstance(body, str) else json.dumps(body).encode()
        h = {"Content-Type": "application/x-ndjson" if ndjson else "application/json"}
        if self.auth:
            h["Authorization"] = self.auth
        req = urllib.request.Request(self.url + path, data=data, method=method, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, json.loads(r.read() or b"null")
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read() or b"null")
            except ValueError:
                return e.code, None
        except (OSError, ValueError) as e:
            return 0, {"error": str(e)[:200]}

    def index(self, kind, t=None):
        """machine-logs-2026.w43: one index a period (monitor.json `period`), so a year of events
        is twelve shards, not 365."""
        fmt = {"day": "%Y.%m.%d", "week": "%G.w%V", "month": "%Y.%m"}
        when = datetime.fromtimestamp(t or time.time(), timezone.utc)
        return "%s-%s" % (self.cfg["indices"][kind], when.strftime(fmt[self.cfg["period"][kind]]))

    def bulk(self, docs):
        """[(kind, doc)] -> True when every one was taken."""
        if not docs:
            return True
        lines = []
        for kind, doc in docs:
            t = doc.get("t") if isinstance(doc.get("t"), (int, float)) else None
            lines.append(json.dumps({"create": {"_index": self.index(kind, t)}}))
            lines.append(
                json.dumps({k: v for k, v in doc.items() if k != "t"}, separators=(",", ":"))
            )
        code, body = self.call("POST", "/_bulk", "\n".join(lines) + "\n", ndjson=True, timeout=30)
        if code != 200 or not isinstance(body, dict):
            self.error = "HTTP %s %s" % (code, json.dumps(body)[:200])
            return False
        if body.get("errors"):
            bad = [
                i
                for i in body.get("items", [])
                if (i.get("create") or {}).get("status", 200) >= 300
            ]
            self.error = "%d of %d refused: %s" % (
                len(bad),
                len(docs),
                json.dumps((bad[0].get("create") or {}).get("error"))[:200],
            )
            # a document Elasticsearch refuses (a mapping clash) would be refused for ever: drop it
            return True
        self.error = None
        return True

    def health(self):
        code, h = self.call("GET", "/_cluster/health?timeout=5s", timeout=8)
        if code != 200 or not isinstance(h, dict):
            return {"status": "unreachable", "status_n": 3, "error": "HTTP %s" % code}
        out = {
            "status": h.get("status"),
            "status_n": {"green": 0, "yellow": 1, "red": 2}.get(h.get("status"), 3),
            "unassigned": h.get("unassigned_shards"),
            "shards": h.get("active_shards"),
        }
        code, n = self.call("GET", "/_nodes/_local/stats/jvm,fs,indices/docs,store", timeout=8)
        if code == 200 and isinstance(n, dict):
            for node in (n.get("nodes") or {}).values():
                mem = node.get("jvm", {}).get("mem", {})
                out["heap_pct"] = mem.get("heap_used_percent")
                out["heap_used_gb"] = round(mem.get("heap_used_in_bytes", 0) / 2**30, 1)
                out["heap_max_gb"] = round(mem.get("heap_max_in_bytes", 0) / 2**30, 1)
                out["docs"] = node.get("indices", {}).get("docs", {}).get("count")
                out["store_gb"] = round(
                    node.get("indices", {}).get("store", {}).get("size_in_bytes", 0) / 1e9, 1
                )
        return out

    def setup(self):
        """The lifecycle policies and index templates, made or replaced: [(what, HTTP status)]."""
        done = []
        for kind, prefix in self.cfg["indices"].items():
            days = self.cfg["keep_days"][kind]
            policy = "%s-%dd" % (prefix, days)
            code, _ = self.call(
                "PUT",
                "/_ilm/policy/" + policy,
                {
                    "policy": {
                        "phases": {
                            "hot": {"actions": {}},
                            "delete": {"min_age": "%dd" % days, "actions": {"delete": {}}},
                        }
                    }
                },
            )
            done.append(("policy " + policy, code))
            props = {
                "@timestamp": {"type": "date"},
                "host": {"properties": {"name": {"type": "keyword"}}},
            }
            if kind == "logs":
                props.update(
                    msg={"type": "text"},
                    prio={"type": "byte"},
                    unit={"type": "keyword"},
                    ident={"type": "keyword"},
                    level={"type": "keyword"},
                )
            if kind == "events":
                props.update(subject={"type": "text"}, rows={"type": "object", "enabled": False})
            code, _ = self.call(
                "PUT",
                "/_index_template/" + prefix,
                {
                    "index_patterns": [prefix + "-*"],
                    "template": {
                        "settings": {
                            "number_of_shards": 1,
                            "number_of_replicas": 0,
                            "index.lifecycle.name": policy,
                            "index.refresh_interval": "30s",
                        },
                        "mappings": {
                            "dynamic_templates": [
                                {
                                    "numbers": {
                                        "match_mapping_type": "long",
                                        "mapping": {"type": "double"},
                                    }
                                },
                                {
                                    "strings": {
                                        "match_mapping_type": "string",
                                        "mapping": {"type": "keyword", "ignore_above": 1024},
                                    }
                                },
                            ],
                            "properties": props,
                        },
                    },
                },
            )
            done.append(("template " + prefix, code))
        return done


# ------------------------------------------------------------------------------------- history
class History:
    """Seven days of minutes for the page: one row a minute, [epoch, value per SERIES column]."""

    def __init__(self, days):
        self.cols = [c for c, _, _ in SERIES]
        self.rows = deque(maxlen=days * 1440)
        self.bucket, self.acc = None, []
        self.path = os.path.join(DIR, "history.json.gz")

    def col(self, name):
        return self.cols.index(name) + 1

    def load(self):
        d = load_json(self.path, gz=True) or {}
        old = d.get("cols") or []
        for r in d.get("rows") or []:
            m = dict(zip(old, r[1:], strict=False))
            self.rows.append([r[0]] + [m.get(c) for c in self.cols])

    def save(self):
        save_json(self.path, {"cols": self.cols, "rows": list(self.rows)}, gz=True)

    def add(self, s, now):
        b = int(now // 60) * 60
        if self.bucket is not None and b != self.bucket and self.acc:
            row = [self.bucket]
            for i, (_, _, how) in enumerate(SERIES):
                vals = [a[i] for a in self.acc if a[i] is not None]
                if not vals:
                    row.append(None)
                elif how == "max":
                    row.append(max(vals))
                elif how == "min":
                    row.append(min(vals))
                else:
                    row.append(round(sum(vals) / len(vals), 2))
            self.rows.append(row)
            self.acc = []
        self.bucket = b
        self.acc.append([dig(s, path) for _, path, _ in SERIES])

    def since(self, hours, points=720):
        cut = time.time() - hours * 3600
        rows = [r for r in self.rows if r[0] >= cut]
        step = max(1, -(-len(rows) // points))
        if step > 1:  # thinned the way a minute is summed up, so a spike survives
            out = []
            for i in range(0, len(rows), step):
                grp = rows[i : i + step]
                row = [grp[0][0]]
                for j, (_, _, how) in enumerate(SERIES, 1):
                    vals = [g[j] for g in grp if g[j] is not None]
                    if not vals:
                        row.append(None)
                    elif how == "avg":
                        row.append(round(sum(vals) / len(vals), 2))
                    else:
                        row.append(min(vals) if how == "min" else max(vals))
                out.append(row)
            rows = out
        return {"cols": self.cols, "rows": rows}


# ------------------------------------------------------------------------------------- the watch
class Monitor:
    def __init__(self, cfg):
        self.cfg = cfg
        os.makedirs(DIR, exist_ok=True)
        self.es = ES(cfg)
        self.looker = Looker(cfg, self.es)
        self.hist = History(cfg["history_days"])
        self.hist.load()
        st = load_json(os.path.join(DIR, "state.json")) or {}
        self.rules = Rules(cfg, st)
        self.recent = deque(st.get("recent", []), maxlen=300)  # warnings and worse, for the page
        self.past = deque(st.get("past", []), maxlen=200)  # alerts and events of the last days
        self.boot = st.get("boot")
        self.last_uptime = st.get("uptime_s")
        self.lock = threading.Lock()
        self.buf = deque(maxlen=cfg["elasticsearch"]["buffer_max"])
        self.dropped = 0
        self.ship = {"ok_at": time.time(), "error": None}
        self.now_doc, self.standing, self.told = {}, [], None
        self.note_at, self.note_proc, self.note_due = 0, None, False
        self.started = time.time()
        self.mtimes = self.code_mtimes()
        self.net_down = None

    @staticmethod
    def code_mtimes():
        return [os.path.getmtime(os.path.join(HERE, f)) for f in ("monitor.py", "monitor.json")]

    # the journal thread hands every line here
    def sink(self, e, hit):
        with self.lock:
            if len(self.buf) == self.buf.maxlen:
                self.dropped += 1
            self.buf.append(("logs", e))
            if e["prio"] <= 4 and not e["msg"].startswith("[UFW BLOCK]"):
                self.recent.append(
                    {k: e[k] for k in ("t", "unit", "ident", "prio", "level", "msg")}
                )
            if hit:
                t = e["t"]
                key = "%s_%d" % (hit["kind"], int(t // 600))
                ev = self.rules.event(
                    key,
                    hit["level"],
                    hit["subject"],
                    [
                        ["Kernel", hit["line"]],
                        ["At", clock(t)],
                        ["Page", self.cfg.get("page_url", "")],
                    ],
                    t,
                    tell=hit["tell"],
                )
                if ev["count"] == 1:
                    self.record(ev, "event")

    def record(self, a, what):
        """An alert's start or end, or an event: to Elasticsearch and the page's list."""
        doc = {
            "t": time.time(),
            "@timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "host": {"name": HOST},
            "key": a["key"],
            "level": a["level"],
            "subject": a["subject"],
            "state": what,
            "rows": a.get("rows"),
        }
        self.buf.append(("events", doc))
        self.past.append({k: doc[k] for k in ("t", "key", "level", "subject", "state")})

    def first_look(self):
        """At start: a reboot since the last run is an event (and whether it was clean)."""
        now = time.time()
        b = boot_id()
        if self.boot and b and b != self.boot:
            up = uptime_s() or 0
            clean = last_boot_clean()
            before = " (it had been up %s)" % span(self.last_uptime) if self.last_uptime else ""
            if clean is False:
                subj, lvl = (
                    "kc-local went down without shutting down -- a power cut or a freeze",
                    "crit",
                )
            else:
                subj, lvl = "kc-local was restarted", "warn"
            ev = self.rules.event(
                "reboot_" + b[:8],
                lvl,
                subj,
                [
                    ["Back up at", clock(now - up)],
                    ["Before", "the last look was%s" % before],
                    [
                        "What to do",
                        "ops.sh status: the studio, its tunnel and timers start by themselves",
                    ],
                    ["Page", self.cfg.get("page_url", "")],
                ],
                now,
            )
            self.record(ev, "event")
        self.boot = b

    def save_state(self):
        st = self.rules.state()
        st.update(
            recent=list(self.recent)[-300:],
            past=list(self.past),
            boot=self.boot,
            uptime_s=uptime_s(),
        )
        save_json(os.path.join(DIR, "state.json"), st)

    def flush(self):
        with self.lock:
            docs = list(self.buf)
        if not docs:
            self.ship["ok_at"] = time.time()
            return
        sent = 0
        for i in range(0, len(docs), 2000):
            if not self.es.bulk(docs[i : i + 2000]):
                break
            sent = i + len(docs[i : i + 2000])
        with self.lock:
            for _ in range(sent):
                self.buf.popleft()
        if sent == len(docs):
            self.ship["ok_at"] = time.time()
        self.ship["error"] = self.es.error

    def deliver(self, alerts, now):
        """health.json, and machine_note.py at once when what is to be told changed."""
        tell = [a for a in alerts if a.get("tell")]
        sig = sorted((a["key"], a["level"]) for a in tell)
        changed = sig != self.told
        self.told = sig
        health = {
            "at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "host": HOST,
            "page": self.cfg.get("page_url"),
            "alerts": [
                {k: a.get(k) for k in ("key", "level", "subject", "rows", "kind", "since", "at")}
                for a in tell
            ],
        }
        save_json(os.path.join(DIR, "health.json"), health)
        if changed:
            self.note_due = True
        busy = self.note_proc is not None and self.note_proc.poll() is None
        if self.note_due and not busy and now - self.note_at > 30:
            py = os.path.join(REPO, ".venv", "bin", "python")
            if os.path.exists(py):
                self.note_proc = subprocess.Popen(
                    [py, "-X", "utf8", os.path.join(REPO, "studio", "machine_note.py")],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            self.note_at, self.note_due = now, False

    def tick(self):
        now = time.time()
        s = self.looker.look(now)
        slow = self.looker.slow
        with self.lock:
            pending = len(self.buf)
        slow["ship"] = {
            "pending": pending,
            "since_ok": now - self.ship["ok_at"],
            "error": self.ship["error"],
        }
        # the internet: an outage is told when it ends (nothing can be sent while it lasts)
        online = (slow.get("internet") or {}).get("ok")
        r = self.cfg["rules"]["internet"]
        if online is False and self.net_down is None:
            self.net_down = now
        elif online and self.net_down is not None:
            gone = now - self.net_down
            if gone >= r["tell_after_s"]:
                ev = self.rules.event(
                    "internet_%d" % self.net_down,
                    "warn",
                    "The internet at kc-local's home was down for %s" % span(gone),
                    [
                        ["From", clock(self.net_down)],
                        ["To", clock(now)],
                        ["Meanwhile", "kitcut.ai could not reach the studio; films waited"],
                    ],
                    now,
                )
                self.record(ev, "event")
            self.net_down = None
        hist = self.hist if int(now) % 600 < self.cfg["every_s"] else None
        before = {a["key"]: a for a in self.standing if a["kind"] == "state"}
        with self.lock:
            alerts = self.rules.judge(s, slow, now, hist)
        after = {a["key"]: a for a in alerts if a["kind"] == "state"}
        for k, a in after.items():
            if k not in before or RANK[a["level"]] > RANK[before[k]["level"]]:
                self.record(a, "start")
        for k, a in before.items():
            if k not in after:
                self.record(a, "clear")
        self.standing = alerts
        if "cpu" in s:
            self.hist.add(s, now)
            doc = dict(s, t=now)
            if int(now) % 60 < self.cfg["every_s"]:  # who holds what, once a minute
                top = slow.get("top") or {}
                doc["usage"] = [
                    {k: g.get(k) for k in ("who", "mb", "anon", "cores")}
                    for g in top.get("groups", [])
                ]
            self.buf.append(("metrics", doc))
        self.now_doc = {"sample": s, "at": now}
        self.deliver(alerts, now)

    def run(self):
        cfg = self.cfg
        self.first_look()
        threading.Thread(target=serve, args=(self, cfg["port"]), daemon=True).start()
        j = Journal(cfg, self.sink)
        j.start()
        if self.es.auth:
            try:
                self.es.setup()
            except Exception as e:  # noqa: BLE001 -- a setup that fails is retried at the next start
                print("monitor: es setup: %r" % e, file=sys.stderr, flush=True)
        print(
            "monitor: every %d s, page on 127.0.0.1:%d, Elasticsearch %s"
            % (
                cfg["every_s"],
                cfg["port"],
                "on" if self.es.auth else "off (no ES_USER in secret.env)",
            ),
            flush=True,
        )
        last_flush = last_save = time.time()
        while True:
            t = time.monotonic()
            try:
                self.tick()
                now = time.time()
                if now - last_flush >= cfg["elasticsearch"]["flush_s"]:
                    if self.es.auth:
                        self.flush()
                    else:
                        with self.lock:
                            self.buf.clear()
                    last_flush = now
                if now - last_save >= 300:
                    j.save()
                    self.save_state()
                    self.hist.save()
                    last_save = now
                if self.code_mtimes() != self.mtimes:
                    print("monitor: its code changed: saving and restarting", flush=True)
                    j.save()
                    self.save_state()
                    self.hist.save()
                    if self.es.auth:
                        self.flush()
                    sys.exit(0)  # Restart=always brings up the new code
            except SystemExit:
                raise
            except Exception as e:  # noqa: BLE001 -- a bad look is skipped, the watch goes on
                print("monitor: tick failed: %r" % e, file=sys.stderr, flush=True)
            time.sleep(max(cfg["every_s"] - (time.monotonic() - t), 1))

    # what the page reads
    def now_json(self):
        slow = self.looker.slow
        with self.lock:
            recent = list(self.recent)[-150:]
            standing = list(self.standing)
        return {
            "host": HOST,
            "at": self.now_doc.get("at"),
            "sample": self.now_doc.get("sample"),
            "alerts": standing,
            "past": list(self.past)[-100:],
            "units": slow.get("units"),
            "failed": slow.get("failed"),
            "last_run": slow.get("last_run"),
            "smart": slow.get("smart"),
            "gpu": slow.get("gpu"),
            "top": slow.get("top"),
            "es": slow.get("es"),
            "ship": slow.get("ship"),
            "studio": slow.get("studio"),
            "internet": slow.get("internet"),
            "ntp": slow.get("ntp"),
            "reboot_required": os.path.exists("/var/run/reboot-required"),
            "kernel": os.uname().release,
            "boot": self.boot,
            "started": self.started,
            "recent": recent,
            "watch": self.cfg["units"]["watch"],
            "dropped": self.dropped,
            "indices": self.cfg["elasticsearch"]["indices"],
            "keep_days": self.cfg["elasticsearch"]["keep_days"],
        }


# ---------------------------------------------------------------------------------------- page
def cookie_value(key):
    return hmac.new(key.encode(), b"kitcut-monitor-page", hashlib.sha256).hexdigest()


class Page(BaseHTTPRequestHandler):
    mon = None
    server_version = "kitcut-monitor"

    def log_message(self, *a):
        pass

    def local(self):
        return self.client_address[0] in ("127.0.0.1", "::1") and not any(
            h in self.headers for h in ("Cf-Ray", "Cf-Connecting-Ip")
        )

    def allowed(self):
        key = secret("MONITOR_KEY")
        if self.local() and not key:
            return True
        if not key:
            return False
        jar = dict(
            p.strip().split("=", 1)
            for p in (self.headers.get("Cookie") or "").split(";")
            if "=" in p
        )
        return hmac.compare_digest(jar.get(COOKIE, ""), cookie_value(key)) or self.local()

    def send(self, code, body, ctype="application/json", extra=None):
        data = body if isinstance(body, bytes) else body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Robots-Tag", "noindex")
        self.send_header("Referrer-Policy", "no-referrer")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path, _, query = self.path.partition("?")
        q = dict(p.split("=", 1) for p in query.split("&") if "=" in p)
        key = secret("MONITOR_KEY")
        if "key" in q and key and hmac.compare_digest(q["key"], key):
            return self.send(
                303,
                "",
                "text/plain",
                {
                    "Location": "/",
                    "Set-Cookie": "%s=%s; Max-Age=31536000; Path=/; HttpOnly; Secure; SameSite=Lax"
                    % (COOKIE, cookie_value(key)),
                },
            )
        if path == "/healthz":
            return self.send(200, json.dumps({"ok": True, "at": self.mon.now_doc.get("at")}))
        if not self.allowed():
            return self.send(401, LOCKED, "text/html; charset=utf-8")
        try:
            if path == "/":
                return self.send(
                    200, read(os.path.join(HERE, "monitor.html")), "text/html; charset=utf-8"
                )
            if path == "/api/now":
                return self.send(200, json.dumps(self.mon.now_json(), default=str))
            if path == "/api/history":
                h = min(float(q.get("h", "24")), 24 * self.mon.cfg["history_days"])
                return self.send(200, json.dumps(self.mon.hist.since(h)))
            if path == "/api/rules":
                return self.send(
                    200,
                    json.dumps(
                        {k: self.mon.cfg[k] for k in ("rules", "units", "journal")}, indent=1
                    ),
                )
        except (BrokenPipeError, ConnectionResetError):
            return None
        return self.send(404, '{"error": "not found"}')


LOCKED = """<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width">
<title>kc-local</title><body style="font:16px system-ui;background:#0e1116;color:#c9d1d9;display:grid;
place-items:center;height:90vh;margin:0"><div style="max-width:28em;padding:16px">
<h1 style="font-size:20px">This page needs its key</h1><p>Open the link with <code>?key=</code> once on
this device; it is remembered for a year. Ask Claude for it (<code>ops.sh monitor link</code>).</p></div>"""


def serve(mon, port):
    Page.mon = mon
    srv = ThreadingHTTPServer(("127.0.0.1", port), Page)
    srv.daemon_threads = True
    srv.serve_forever()


# ------------------------------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("what", choices=["run", "once", "rules", "es-setup", "link"])
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    cfg = config()
    if a.what == "run":
        Monitor(cfg).run()
    elif a.what == "rules":
        print(json.dumps({k: cfg[k] for k in ("rules", "units", "journal")}, indent=1))
    elif a.what == "link":
        key = secret("MONITOR_KEY")
        sys.exit("no MONITOR_KEY in %s" % os.path.join(DIR, "secret.env")) if not key else print(
            "%s/?key=%s" % (cfg["page_url"], key)
        )
    elif a.what == "es-setup":
        es = ES(cfg)
        if not es.auth:
            sys.exit("no ES_USER in %s" % os.path.join(DIR, "secret.env"))
        for what, code in es.setup():
            print("%-40s HTTP %s" % (what, code))
    else:
        lk = Looker(cfg, ES(cfg) if secret("ES_USER") else None)
        lk.look()
        time.sleep(1)
        s = lk.look()
        st = load_json(os.path.join(DIR, "state.json")) or {}
        rules = Rules(cfg, {"baseline": st.get("baseline", {})})
        hist = History(cfg["history_days"])
        hist.load()
        alerts = rules.judge(s, lk.slow, time.time(), hist)
        if a.json:
            print(
                json.dumps({"sample": s, "slow": lk.slow, "alerts": alerts}, indent=1, default=str)
            )
        else:
            m, d = s["mem"], s["disk"].get("root", {})
            print(
                "cpu %s%%  load %s  memory %s GB free of %s  swap %s GB  disk %s%% (%s GB free)"
                % (
                    s.get("cpu", {}).get("pct"),
                    s["load"].get("1"),
                    m["avail_gb"],
                    gb(m["total_mb"]),
                    s["swap"]["used_gb"],
                    d.get("pct"),
                    d.get("free_gb"),
                )
            )
            print(
                "temps %s  gpu %s  internet %s  es %s"
                % (s["temp"], s["gpu"], lk.slow.get("internet"), lk.slow.get("es"))
            )
            down = [n for n, u in (lk.slow.get("units") or {}).items() if u["active"] != "active"]
            print("units not active: %s" % (", ".join(down) or "none"))
            print("failed units: %s" % (", ".join(lk.slow.get("failed") or []) or "none"))
            print("smart: %s" % lk.slow.get("smart"))
            print(
                "rules (without hold times): %s"
                % (
                    ", ".join("%s %s" % (x["level"], x["subject"]) for x in alerts)
                    or "nothing stands"
                )
            )


if __name__ == "__main__":
    main()
