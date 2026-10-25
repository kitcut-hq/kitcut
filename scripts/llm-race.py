#!/usr/bin/env python
r"""Race language models on the same tasks and keep every token's arrival time.

A benchmark film needs what a leaderboard does not publish: the race itself. Each run sends
one task to every model at the same moment through OpenRouter, streams the answers, and writes
down when each piece of text arrived, which provider served it, what the hidden thinking cost
in tokens, what OpenRouter billed, and whether the answer was right. The film then replays the
race from those timestamps instead of from a guess.

A race is a manifest (projects/<id>/race.json):

    {"id": "kimi-race",
     "models": [{"key": "kimi", "id": "moonshotai/kimi-k3.1-pro", "label": "Kimi K3.1 Pro"},
                {"key": "kimi-high", "id": "moonshotai/kimi-k3.1-pro", "label": "...",
                 "reasoning": {"effort": "high"}}],
     "tasks": [{"id": "quick", "label": "The quick question", "prompt": "...",
                "check": {"type": "regex", "any": ["3\\s*h\\w*\\s*(and\\s*)?18"]}},
               {"id": "code", "prompt": "...",
                "check": {"type": "python", "tests": "tasks/code_tests.py"}},
               {"id": "hard", "prompt": "...",
                "check": {"type": "answer", "expect": "3004"}}],
     "runs": 3, "max_tokens": 64000, "timeout_s": 900, "out": "data/race"}

A model with no "reasoning" is called at its OpenRouter default, which is what a person who
just calls it gets; the default effort is read from OpenRouter's model list and written into
every run, because it differs by model and it is most of the story.

Checks: "regex" (any pattern matches the answer), "answer" (the last integer in the answer, or
the one after "ANSWER:", equals expect), "python" (the last ```python block is saved as
solution.py beside the tests file's copy and the tests file is run with a time limit; it prints
one JSON line {"passed": n, "total": m, "failed": [...]}). The model's code runs locally in a
temporary folder with -E -s and a timeout: write prompts whose code needs nothing else.

    --plan      the matrix, the price list and the worst case; nothing is sent (the free mode)
    --summary   rebuild <out>/race.json from the runs already on disk; nothing is sent
    --only K    only these model keys (repeatable); --task T only these tasks
    --runs N    override the manifest's runs; runs already on disk are kept unless --force

Each run is <out>/<task>/<model-key>/run<N>.json: the request, the provider, every streamed
piece as [seconds since send, "r" (thinking) or "c" (answer), text], the usage OpenRouter
reported (prompt, completion, reasoning tokens, cost in USD) and the check. race.json is what a
film reads: per model and task the median run's numbers and its compacted stream.

Invoke as:
    python scripts/llm-race.py --manifest projects/<id>/race.json --plan
    python scripts/llm-race.py --manifest projects/<id>/race.json --runs 1 --only kimi
    python scripts/llm-race.py --manifest projects/<id>/race.json
    python scripts/llm-race.py --manifest projects/<id>/race.json --summary
"""

import argparse
import concurrent.futures as cf
import json
import os
import re
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import

import _gpulock  # noqa: E402
import _project  # noqa: E402

API = "https://openrouter.ai/api/v1"
UA = "kitcut-llm-race/1"
_print_lock = threading.Lock()


def say(*a):
    with _print_lock:
        print(*a, flush=True)


def load_manifest(path):
    path = _env.resolve(path)
    with open(path, encoding="utf-8") as f:
        m = json.load(f)
    m["_path"] = path
    m["_dir"] = os.path.dirname(path)
    m.setdefault("runs", 3)
    m.setdefault("max_tokens", 64000)
    m.setdefault("timeout_s", 900)
    m.setdefault("out", "data/race")
    keys = [x["key"] for x in m["models"]]
    if len(keys) != len(set(keys)):
        sys.exit("model keys must be unique: %s" % keys)
    return m


def catalogue():
    """OpenRouter's public model list: prices and default reasoning settings, no key needed."""
    req = urllib.request.Request(API + "/models", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:  # noqa: S310 -- fixed https URL
        return {x["id"]: x for x in json.load(r)["data"]}


def price(cat, mid):
    p = (cat.get(mid) or {}).get("pricing") or {}
    return float(p.get("prompt") or 0), float(p.get("completion") or 0)


def default_effort(cat, mid):
    r = (cat.get(mid) or {}).get("reasoning") or {}
    return r.get("default_effort")


def run_path(m, task, model, n):
    return os.path.join(m["_dir"], m["out"], task["id"], model["key"], "run%d.json" % n)


# --------------------------------------------------------------------------- the race


def stream_one(m, model, task, key):
    """Send one task to one model and keep every streamed piece with its arrival time."""
    body = {
        "model": model["id"],
        "messages": [{"role": "user", "content": task["prompt"]}],
        "stream": True,
        "max_tokens": model.get("max_tokens", m["max_tokens"]),
    }
    if not model.get("base_url"):
        body["usage"] = {"include": True}
    body.update(model.get("body") or {})
    if model.get("reasoning") is not None:
        body["reasoning"] = model["reasoning"]
    if model.get("provider"):
        body["provider"] = model["provider"]
    data = json.dumps(body).encode("utf-8")
    headers = {"Content-Type": "application/json", "User-Agent": UA}
    if not model.get("base_url"):
        headers.update(
            {
                "Authorization": "Bearer " + key,
                "HTTP-Referer": "https://kitcut.ai",
                "X-Title": "KitCut llm-race",
            }
        )
    req = urllib.request.Request(
        (model.get("base_url") or API) + "/chat/completions", data=data, headers=headers
    )
    out = {
        "events": [],
        "content": "",
        "reasoning_text": "",
        "provider": None,
        "usage": None,
        "finish_reason": None,
        "error": None,
        "gen_id": None,
        "timings": None,
    }
    t0 = time.perf_counter()
    out["sent_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    try:
        with urllib.request.urlopen(req, timeout=m["timeout_s"]) as r:  # noqa: S310 -- OpenRouter or the manifest's own server
            for raw in r:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                try:
                    ev = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                t = round(time.perf_counter() - t0, 4)
                if ev.get("error"):
                    out["error"] = ev["error"]
                    break
                out["gen_id"] = out["gen_id"] or ev.get("id")
                out["provider"] = ev.get("provider") or out["provider"]
                if ev.get("usage"):
                    out["usage"] = ev["usage"]
                if ev.get("timings"):  # llama-server: its own decode clock and the drafter's counts
                    out["timings"] = ev["timings"]
                for ch in ev.get("choices") or []:
                    d = ch.get("delta") or {}
                    rt = d.get("reasoning") or d.get("reasoning_content")
                    if not rt and d.get("reasoning_details"):
                        rt = "".join(
                            x.get("text") or x.get("summary") or ""
                            for x in d["reasoning_details"]
                            if isinstance(x, dict)
                        )
                    if rt:
                        out["events"].append([t, "r", rt])
                        out["reasoning_text"] += rt
                    if d.get("content"):
                        out["events"].append([t, "c", d["content"]])
                        out["content"] += d["content"]
                    if ch.get("finish_reason"):
                        out["finish_reason"] = ch["finish_reason"]
    except urllib.error.HTTPError as e:
        out["error"] = {"http": e.code, "body": e.read().decode("utf-8", "replace")[:2000]}
    except Exception as e:  # noqa: BLE001 -- a lane that dies is a result, not a crash
        out["error"] = {"exception": "%s: %s" % (type(e).__name__, e)}
    out["t_end"] = round(time.perf_counter() - t0, 4)
    return out


# --------------------------------------------------------------------------- checks


def last_python_block(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.S)
    return blocks[-1] if blocks else None


def check(m, task, content):
    c = task.get("check") or {}
    kind = c.get("type")
    if kind == "regex":
        ok = any(re.search(p, content, re.I) for p in c["any"])
        return {"pass": ok, "score": 1 if ok else 0, "total": 1}
    if kind == "answer":
        hit = re.findall(r"ANSWER:\s*\**\s*(-?[\d,]+)", content, re.I)
        nums = hit or re.findall(r"-?\d[\d,]*", content)
        got = nums[-1].replace(",", "") if nums else None
        ok = got == str(c["expect"])
        return {"pass": ok, "score": 1 if ok else 0, "total": 1, "got": got}
    if kind == "python":
        code = last_python_block(content)
        if code is None:
            return {"pass": False, "score": 0, "total": None, "error": "no python block"}
        tests = os.path.join(m["_dir"], c["tests"])
        with tempfile.TemporaryDirectory(prefix="llm-race-") as tmp:
            with open(os.path.join(tmp, "solution.py"), "w", encoding="utf-8") as f:
                f.write(code)
            with open(tests, encoding="utf-8") as f:
                src = f.read()
            with open(os.path.join(tmp, "tests.py"), "w", encoding="utf-8") as f:
                f.write(src)
            try:
                p = subprocess.run(
                    [sys.executable, "-E", "-s", "tests.py"],
                    cwd=tmp,
                    capture_output=True,
                    text=True,
                    timeout=c.get("timeout_s", 30),
                )
            except subprocess.TimeoutExpired:
                return {"pass": False, "score": 0, "total": None, "error": "tests timed out"}
        last = (p.stdout.strip().splitlines() or [""])[-1]
        try:
            r = json.loads(last)
        except json.JSONDecodeError:
            return {
                "pass": False,
                "score": 0,
                "total": None,
                "error": (p.stderr or p.stdout)[-800:],
            }
        return {
            "pass": r["passed"] == r["total"],
            "score": r["passed"],
            "total": r["total"],
            "failed": r.get("failed", []),
        }
    return {"pass": None, "score": None, "total": None}


# --------------------------------------------------------------------------- one run


def do_run(m, cat, task, model, n, key):
    out = stream_one(m, model, task, key)
    u = out.get("usage") or {}
    det = u.get("completion_tokens_details") or {}
    first_any = next((e[0] for e in out["events"]), None)
    first_c = next((e[0] for e in out["events"] if e[1] == "c"), None)
    last_r = max((e[0] for e in out["events"] if e[1] == "r"), default=None)
    pin, pout = price(cat, model["id"])
    tm = out.get("timings") or {}
    rec = {
        "model": model,
        "task": task["id"],
        "run": n,
        "sent_utc": out["sent_utc"],
        "effort": (model.get("reasoning") or {}).get("effort")
        or ("local" if model.get("base_url") else "default:%s" % default_effort(cat, model["id"])),
        "list_price_per_m": [round(pin * 1e6, 4), round(pout * 1e6, 4)],
        "provider": out["provider"],
        "gen_id": out["gen_id"],
        "finish_reason": out["finish_reason"],
        "error": out["error"],
        "t_first_token": first_any,
        "t_first_answer": first_c,
        "t_last_thinking": last_r,
        "t_done": out["t_end"],
        "prompt_tokens": u.get("prompt_tokens"),
        "completion_tokens": u.get("completion_tokens"),
        "reasoning_tokens": det.get("reasoning_tokens"),
        "cost_usd": u.get("cost"),
        "usage": u,
        "timings": out.get("timings"),
        "decode_tok_s": tm.get("predicted_per_second"),
        "predicted_n": tm.get("predicted_n"),
        "draft_n": tm.get("draft_n"),
        "draft_n_accepted": tm.get("draft_n_accepted"),
        "content": out["content"],
        "reasoning_chars": len(out["reasoning_text"]),
        "events": out["events"],
    }
    rec["check"] = check(m, task, out["content"]) if not out["error"] else {"pass": False}
    p = run_path(m, task, model, n)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False, indent=1)
    say(
        "  %-6s %-14s run%d  %7.1fs  first %5s  out %6s tok (think %6s)  $%-8s %s %s"
        % (
            task["id"],
            model["key"],
            n,
            rec["t_done"],
            "%.1f" % first_c if first_c is not None else "-",
            rec["completion_tokens"],
            rec["reasoning_tokens"],
            "%.4f" % rec["cost_usd"]
            if rec["cost_usd"] is not None
            else (
                "%.1ft/s" % rec["decode_tok_s"]
                + (
                    " acc %d/%d" % (rec["draft_n_accepted"], rec["draft_n"])
                    if rec.get("draft_n")
                    else ""
                )
                if rec.get("decode_tok_s")
                else "?"
            ),
            {True: "PASS", False: "FAIL", None: "-"}[rec["check"].get("pass")],
            ("ERROR %s" % json.dumps(out["error"])[:200])
            if out["error"]
            else (out["provider"] or ""),
        )
    )
    return rec


# --------------------------------------------------------------------------- a local server


def gpu_now(pid=None):
    """The card as nvidia-smi sees it, and what one process holds (MiB); None without a card."""
    try:
        q = (
            subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=name,driver_version,memory.used,memory.total,utilization.gpu",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            .stdout.strip()
            .splitlines()[0]
        )
        name, drv, used, total, util = [x.strip() for x in q.split(",")]
        out = {
            "gpu": name,
            "driver": drv,
            "used_mib": int(used),
            "total_mib": int(total),
            "util": int(util),
        }
        if pid:
            apps = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-compute-apps=pid,used_memory",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            ).stdout
            for row in apps.strip().splitlines():
                a, b = [x.strip() for x in row.split(",")]
                if a == str(pid):
                    out["proc_mib"] = int(b)
        return out
    except Exception:  # noqa: BLE001 -- no card, no nvidia-smi: the race still runs
        return None


class Server:
    """A model's own server ("serve": {"cmd": [...], "ready_s", "warmup", "warmup_prompt"}), up for
    the length of the block, with the machine's GPU lock held and the card's memory sampled
    every half second; the peak and the loaded figure go into <out>/serve.json."""

    def __init__(self, m, model):
        self.m, self.model, self.p, self.peak, self.stop = m, model, None, {}, threading.Event()

    def _sample(self):
        while not self.stop.wait(0.5):
            g = gpu_now(self.p.pid)
            if g:
                for k in ("used_mib", "proc_mib", "util"):
                    if g.get(k) is not None:
                        self.peak[k] = max(self.peak.get(k, 0), g[k])

    def __enter__(self):
        sv, m = self.model["serve"], self.m
        self.lock = _gpulock.hold(
            "gpu",
            tool="llm-race",
            project=os.path.basename(m["_dir"]),
            wait=sv.get("lock_wait_s", 3600),
            on_wait=lambda rec, _waited: say("  waiting for the GPU: %s" % _gpulock.describe(rec)),
        ).__enter__()
        cmd = [os.path.expandvars(os.path.expanduser(x)) for x in sv["cmd"]]
        os.makedirs(os.path.join(m["_dir"], m["out"]), exist_ok=True)
        self.logf = open(os.path.join(m["_dir"], m["out"], "serve-%s.log" % self.model["key"]), "w")
        self.before = gpu_now()
        say("\nserving %s: %s" % (self.model["key"], " ".join(cmd)))
        self.p = subprocess.Popen(cmd, stdout=self.logf, stderr=subprocess.STDOUT)
        health = self.model["base_url"].rsplit("/v1", 1)[0] + "/health"
        deadline = time.time() + sv.get("ready_s", 600)
        while True:
            if self.p.poll() is not None:
                raise SystemExit(
                    "server for %s exited (%s); see %s"
                    % (self.model["key"], self.p.returncode, self.logf.name)
                )
            try:
                with urllib.request.urlopen(health, timeout=2) as r:  # noqa: S310 -- the manifest's own local server
                    if r.status == 200:
                        break
            except Exception:  # noqa: BLE001, S110 -- not up yet: the loop asks again in a second
                pass
            if time.time() > deadline:
                raise SystemExit(
                    "server for %s not ready in %ss" % (self.model["key"], sv.get("ready_s", 600))
                )
            time.sleep(1)
        for _ in range(sv.get("warmup", 1)):
            stream_one(
                self.m,
                self.model,
                {"prompt": sv.get("warmup_prompt", "Say hello in five words.")},
                None,
            )
        self.loaded = gpu_now(self.p.pid)
        self.th = threading.Thread(target=self._sample, daemon=True)
        self.th.start()
        return self

    def __exit__(self, *exc):
        self.stop.set()
        self.p.terminate()
        try:
            self.p.wait(30)
        except subprocess.TimeoutExpired:
            self.p.kill()
        self.logf.close()
        self.lock.__exit__(None, None, None)
        sp = os.path.join(self.m["_dir"], self.m["out"], "serve.json")
        doc = {}
        if os.path.exists(sp):
            with open(sp, encoding="utf-8") as f:
                doc = json.load(f)
        doc[self.model["key"]] = {
            "cmd": self.model["serve"]["cmd"],
            "gpu_before": self.before,
            "gpu_loaded": self.loaded,
            "peak": self.peak,
            "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        with open(sp, "w", encoding="utf-8") as f:
            json.dump(doc, f, indent=1)
        say(
            "  %s: card %s MiB before, %s loaded, peak %s"
            % (
                self.model["key"],
                (self.before or {}).get("used_mib"),
                (self.loaded or {}).get("used_mib"),
                self.peak,
            )
        )
        return False


# --------------------------------------------------------------------------- summary


def compact(events, step=0.05, thinking=False):
    """The stream as the film needs it: answer text with times, thinking as a count of characters
    over time (its words are a summary on most API models and are never shown; a local model's
    are its real thinking, kept with "replay_thinking": true), merged to `step` s."""
    out = []
    for t, kind, text in events:
        keep = kind == "c" or thinking
        if out and out[-1][1] == kind and t - out[-1][0] < step:
            out[-1][2] += text if keep else ""
            out[-1][3] += len(text)
            continue
        out.append([t, kind, text if keep else "", len(text)])
    return out


def summarise(m, cat):
    race = {"id": m.get("id"), "built_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    race["models"] = []
    serve = {}
    sp = os.path.join(m["_dir"], m["out"], "serve.json")
    if os.path.exists(sp):
        with open(sp, encoding="utf-8") as f:
            serve = json.load(f)
    for model in m["models"]:
        pin, pout = price(cat, model["id"]) if cat and not model.get("base_url") else (None, None)
        race["models"].append(
            {
                "key": model["key"],
                "id": model["id"],
                "label": model.get("label", model["id"]),
                "effort": (model.get("reasoning") or {}).get("effort")
                or (
                    "local"
                    if model.get("base_url")
                    else cat and "default:%s" % default_effort(cat, model["id"])
                ),
                "price_per_m": [pin and round(pin * 1e6, 4), pout and round(pout * 1e6, 4)],
                "serve": serve.get(model["key"]),
            }
        )
    race["tasks"] = []
    for task in m["tasks"]:
        tt = {"id": task["id"], "label": task.get("label", task["id"]), "prompt": task["prompt"]}
        tt["check"] = task.get("check")
        tt["lanes"] = {}
        for model in m["models"]:
            d = os.path.dirname(run_path(m, task, model, 1))
            runs = []
            if os.path.isdir(d):
                for fn in sorted(os.listdir(d)):
                    if re.match(r"run\d+\.json$", fn):
                        with open(os.path.join(d, fn), encoding="utf-8") as f:
                            runs.append(json.load(f))
            ok = [r for r in runs if not r.get("error") and r.get("t_done")]
            if not ok:
                tt["lanes"][model["key"]] = {"runs": len(runs), "errors": len(runs)}
                continue
            times = sorted(r["t_done"] for r in ok)
            med_t = statistics.median(times)
            pick = min(ok, key=lambda r: (abs(r["t_done"] - med_t), r["run"]))

            def med(field, rs=ok):
                v = [r[field] for r in rs if r.get(field) is not None]
                return statistics.median(v) if v else None

            tt["lanes"][model["key"]] = {
                "runs": len(runs),
                "errors": len(runs) - len(ok),
                "passed": sum(1 for r in ok if r["check"].get("pass")),
                "providers": sorted({r.get("provider") or "?" for r in ok}),
                "median": {
                    "t_done": med("t_done"),
                    "t_first_answer": med("t_first_answer"),
                    "t_first_token": med("t_first_token"),
                    "completion_tokens": med("completion_tokens"),
                    "reasoning_tokens": med("reasoning_tokens"),
                    "cost_usd": med("cost_usd"),
                    "decode_tok_s": med("decode_tok_s"),
                    "predicted_n": med("predicted_n"),
                    "accept": (
                        sum(r.get("draft_n_accepted") or 0 for r in ok)
                        / max(1, sum(r.get("draft_n") or 0 for r in ok))
                        if any(r.get("draft_n") for r in ok)
                        else None
                    ),
                },
                "all": [
                    {
                        k: r.get(k)
                        for k in (
                            "run",
                            "t_done",
                            "t_first_answer",
                            "completion_tokens",
                            "reasoning_tokens",
                            "cost_usd",
                            "provider",
                            "decode_tok_s",
                            "predicted_n",
                            "draft_n",
                            "draft_n_accepted",
                        )
                    }
                    | {"pass": r["check"].get("pass"), "score": r["check"].get("score")}
                    for r in ok
                ],
                "replay": {
                    "run": pick["run"],
                    "provider": pick.get("provider"),
                    "t_first_token": pick.get("t_first_token"),
                    "t_first_answer": pick.get("t_first_answer"),
                    "t_done": pick["t_done"],
                    "completion_tokens": pick.get("completion_tokens"),
                    "reasoning_tokens": pick.get("reasoning_tokens"),
                    "cost_usd": pick.get("cost_usd"),
                    "decode_tok_s": pick.get("decode_tok_s"),
                    "check": pick.get("check"),
                    "stream": compact(
                        pick["events"],
                        step=m.get("replay_step", 0.05),
                        thinking=m.get("replay_thinking", False),
                    ),
                },
            }
        race["tasks"].append(tt)
    p = os.path.join(m["_dir"], m["out"], "race.json")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(race, f, ensure_ascii=False)
    return p, race


def print_board(race):
    for t in race["tasks"]:
        say("\n%s -- %s" % (t["id"], t["label"]))
        say(
            "  %-14s %4s %8s %8s %9s %9s %9s  %s"
            % ("model", "ok", "done s", "first s", "out tok", "think", "cost $", "providers")
        )
        for key, ln in t["lanes"].items():
            md = ln.get("median")
            if not md:
                say("  %-14s  no good runs (%d errors)" % (key, ln.get("errors", 0)))
                continue

            def f(v, fmt):
                return fmt % v if v is not None else "-"

            say(
                "  %-14s %d/%d %8s %8s %9s %9s %9s  %s"
                % (
                    key,
                    ln["passed"],
                    ln["runs"] - ln["errors"],
                    f(md["t_done"], "%.1f"),
                    f(md["t_first_answer"], "%.1f"),
                    f(md["completion_tokens"], "%d"),
                    f(md["reasoning_tokens"], "%d"),
                    f(md["cost_usd"], "%.4f"),
                    ",".join(ln["providers"]),
                )
            )


# --------------------------------------------------------------------------- main


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--plan", action="store_true", help="price the race; send nothing")
    ap.add_argument(
        "--summary", action="store_true", help="rebuild race.json from disk; send nothing"
    )
    ap.add_argument("--only", action="append", help="model key (repeatable)")
    ap.add_argument("--task", action="append", help="task id (repeatable)")
    ap.add_argument("--runs", type=int)
    ap.add_argument("--force", action="store_true", help="re-run runs already on disk")
    ap.add_argument("--parallel", type=int, default=0, help="lanes at once (default: every model)")
    a = ap.parse_args()

    m = load_manifest(a.manifest)
    cat = catalogue()
    models = [x for x in m["models"] if not a.only or x["key"] in a.only]
    tasks = [x for x in m["tasks"] if not a.task or x["id"] in a.task]
    runs = a.runs or m["runs"]
    for x in models:
        if not x.get("base_url") and x["id"] not in cat:
            sys.exit("not on OpenRouter: %s" % x["id"])

    if a.summary:
        p, race = summarise(m, cat)
        print_board(race)
        say("\nwrote %s" % os.path.relpath(p, _env.ROOT))
        return 0

    todo = [
        (task, model, n)
        for n in range(1, runs + 1)
        for task in tasks
        for model in models
        if a.force or not os.path.exists(run_path(m, task, model, n))
    ]
    worst = 0.0
    say("%-14s %-34s %-12s %8s %8s" % ("key", "model", "effort", "$/M in", "$/M out"))
    for x in models:
        pin, pout = (0, 0) if x.get("base_url") else price(cat, x["id"])
        eff = (x.get("reasoning") or {}).get("effort") or (
            "local" if x.get("base_url") else "default:%s" % default_effort(cat, x["id"])
        )
        say("%-14s %-34s %-12s %8.2f %8.2f" % (x["key"], x["id"], eff, pin * 1e6, pout * 1e6))
    for task, model, _n in todo:
        pin, pout = (0, 0) if model.get("base_url") else price(cat, model["id"])
        worst += pin * (len(task["prompt"]) / 3.5) + pout * model.get("max_tokens", m["max_tokens"])
    say(
        "\n%d requests to send (%d tasks x %d models x %d runs, minus %d on disk); "
        "worst case if every one hit max_tokens: $%.2f"
        % (
            len(todo),
            len(tasks),
            len(models),
            runs,
            len(tasks) * len(models) * runs - len(todo),
            worst,
        )
    )
    if a.plan:
        return 0
    if not todo:
        p, race = summarise(m, cat)
        print_board(race)
        return 0

    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not key and any(not mo.get("base_url") for _t, mo, _n in todo):
        sys.exit("OPENROUTER_API_KEY is not set (put it in .env)")

    # a model on a local server runs alone, one request at a time: the card is the thing measured
    local = [x for x in todo if x[1].get("base_url")]
    todo = [x for x in todo if not x[1].get("base_url")]
    for model in models:
        mine = [x for x in local if x[1]["key"] == model["key"]]
        if not mine:
            continue
        if model.get("serve"):
            with Server(m, model):
                for t, mo, k in mine:
                    do_run(m, cat, t, mo, k, key)
        else:
            for t, mo, k in mine:
                do_run(m, cat, t, mo, k, key)

    # one wave per (run, task): every lane leaves at the same moment, which is the race
    waves = {}
    for task, model, n in todo:
        waves.setdefault((n, task["id"]), []).append((task, model, n))
    spent = 0.0
    for (n, tid), lanes in waves.items():
        say("\nrun %d, task %s: %d lanes" % (n, tid, len(lanes)))
        with cf.ThreadPoolExecutor(max_workers=a.parallel or len(lanes)) as ex:
            futs = [ex.submit(do_run, m, cat, t, mo, k, key) for t, mo, k in lanes]
            for fu in cf.as_completed(futs):
                spent += fu.result().get("cost_usd") or 0
    say("\nspent $%.4f this session" % spent)
    p, race = summarise(m, cat)
    print_board(race)
    pid = os.path.basename(m["_dir"])
    _project.record(
        pid,
        "llm-race",
        script=__file__,
        argv=sys.argv[1:],
        note="%d requests, $%.2f; race data in %s"
        % (len(todo), spent, os.path.relpath(p, m["_dir"])),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
