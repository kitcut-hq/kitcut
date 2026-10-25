#!/usr/bin/env python
r"""Race video models on the same prompts: every job's timeline, its bill, its file, and checks.

The video counterpart of llm-race.py. Each wave sends one prompt to every model at the same
moment through OpenRouter's video API (POST /api/v1/videos), polls each job every couple of
seconds and writes down when its status changed (pending, in progress, completed), downloads the
clip, reads what was actually delivered (size, frame rate, length, whether it has sound) and the
cost OpenRouter billed, then runs the prompt's checks on the file. A film replays the race from
those timelines and shows the clips themselves.

A race is a manifest (projects/<id>/race.json):

    {"id": "video-race",
     "defaults": {"duration": 8, "resolution": "720p", "aspect_ratio": "16:9",
                  "generate_audio": true},
     "models": [{"key": "seedance", "id": "bytedance/seedance-2.5", "label": "Seedance 2.5"},
                {"key": "veo", "id": "google/veo-3.1", "label": "Veo 3.1"}],
     "tasks": [{"id": "sign", "label": "The sign", "prompt": "...",
                "checks": [{"type": "ocr", "expect": "KITCUT"}]},
               {"id": "line", "prompt": "...",
                "checks": [{"type": "speech", "expect": ["flat white"]}]}],
     "runs": 2, "poll_s": 2, "timeout_s": 1800, "out": "data/race"}

A model may override any default ("resolution": "480p"). Checks: "ocr" reads frames every
`every` seconds (0.25) with RapidOCR and passes when the expected word appears in any frame (letters
only, case ignored), keeping the best reading and its second; "speech" transcribes the clip's
sound with faster-whisper and passes when every expected phrase is heard.

    --plan      the matrix and the price of each job from the model's own price list; sends nothing
    --summary   rebuild <out>/race.json from the jobs on disk; sends nothing
    --check     re-run the checks on the clips on disk; sends nothing
    --only K / --task T / --runs N / --force   as in llm-race.py

Each job is <out>/<task>/<model-key>/run<N>.json beside run<N>.mp4. An account's OpenRouter
allowed-providers setting refuses some models at submit (no cost); `--plan` cannot see it, so a
first wave of one run is the cheap way to learn which models answer.

Invoke as:
    python scripts/video-race.py --manifest projects/<id>/race.json --plan
    python scripts/video-race.py --manifest projects/<id>/race.json --runs 1 --task sign
    python scripts/video-race.py --manifest projects/<id>/race.json
    python scripts/video-race.py --manifest projects/<id>/race.json --summary
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

import _project  # noqa: E402

API = "https://openrouter.ai/api/v1"
UA = "kitcut-video-race/1"
SIZES = {"480p": (854, 480), "720p": (1280, 720), "1080p": (1920, 1080), "4K": (3840, 2160)}
_lock = threading.Lock()


def say(*a):
    with _lock:
        print(*a, flush=True)


def load_manifest(path):
    path = _env.resolve(path)
    with open(path, encoding="utf-8") as f:
        m = json.load(f)
    m["_path"], m["_dir"] = path, os.path.dirname(path)
    for k, v in (("runs", 1), ("poll_s", 2), ("timeout_s", 1800), ("out", "data/race")):
        m.setdefault(k, v)
    m.setdefault("defaults", {})
    return m


def catalogue():
    req = urllib.request.Request(API + "/videos/models", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:  # noqa: S310 -- fixed https URL
        return {x["id"]: x for x in json.load(r)["data"]}


def params(m, model):
    p = dict(m["defaults"])
    for k in ("duration", "resolution", "aspect_ratio", "generate_audio"):
        if k in model:
            p[k] = model[k]
    return p


def price(cat, model, p):
    """The job's list price from the model's own SKUs (USD), or None when they do not say."""
    sku = (cat.get(model["id"]) or {}).get("pricing_skus") or {}
    dur, res, audio = p.get("duration", 8), p.get("resolution", "720p"), p.get("generate_audio")
    if "video_tokens" in sku:  # ByteDance: width x height x frames / 1024
        w, h = SIZES.get(res, (1280, 720))
        key = (
            "video_tokens_" + res.lower()
            if "video_tokens_" + res.lower() in sku
            else "video_tokens"
        )
        return w * h * 24 * dur / 1024 * float(sku[key])
    side = "with" if audio else "without"
    for key in (
        "duration_seconds_%s_audio_%s" % (side, res),
        "duration_seconds_%s_audio" % side,
        "text_to_video_duration_seconds_%s" % res,
        "duration_seconds_%s" % res,
        "duration_seconds",
    ):
        if key in sku:
            return float(sku[key]) * dur
    key = "cents_per_video_output_second_%s" % res
    if key in sku:
        return float(sku[key]) / 100 * dur
    return None


def job_dir(m, task, model):
    return os.path.join(m["_dir"], m["out"], task["id"], model["key"])


# --------------------------------------------------------------------------- one job


def api(path, key, body=None, timeout=60):
    req = urllib.request.Request(
        path if path.startswith("http") else API + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "Authorization": "Bearer " + key,
            "Content-Type": "application/json",
            "User-Agent": UA,
            "HTTP-Referer": "https://kitcut.ai",
            "X-Title": "KitCut video-race",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 -- OpenRouter only
        return r.read()


def probe(path):
    out = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "stream=codec_type,width,height,r_frame_rate:format=duration",
            "-of",
            "json",
            path,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    d = json.loads(out.stdout or "{}")
    v = next((s for s in d.get("streams", []) if s.get("codec_type") == "video"), {})
    num, _, den = (v.get("r_frame_rate") or "0/1").partition("/")
    return {
        "width": v.get("width"),
        "height": v.get("height"),
        "fps": round(float(num) / float(den or 1), 3) if float(den or 1) else None,
        "duration": round(float((d.get("format") or {}).get("duration") or 0), 3),
        "audio": any(s.get("codec_type") == "audio" for s in d.get("streams", [])),
    }


def run_job(m, cat, task, model, n, key):
    p = params(m, model)
    body = {"model": model["id"], "prompt": task["prompt"], **p}
    rec = {"model": model, "task": task["id"], "run": n, "params": p, "timeline": [], "error": None}
    rec["list_price"] = price(cat, model, p)
    t0 = time.perf_counter()
    rec["sent_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    try:
        job = json.loads(api("/videos", key, body))
        rec["job_id"] = job.get("id")
        rec["timeline"].append([round(time.perf_counter() - t0, 3), job.get("status", "submitted")])
        poll = job.get("polling_url") or API + "/videos/" + job["id"]
        status = job
        while True:
            st = status.get("status")
            if st in ("completed", "failed", "cancelled", "expired"):
                break
            if time.perf_counter() - t0 > m["timeout_s"]:
                rec["error"] = {"timeout": m["timeout_s"]}
                break
            time.sleep(m["poll_s"])
            try:
                status = json.loads(api(poll, key))
            except (urllib.error.URLError, TimeoutError) as e:
                rec.setdefault("poll_errors", []).append(str(e)[:200])
                continue
            if status.get("status") != rec["timeline"][-1][1]:
                rec["timeline"].append([round(time.perf_counter() - t0, 3), status.get("status")])
        rec["t_done"] = rec["timeline"][-1][0]
        rec["status"] = status.get("status")
        rec["cost_usd"] = (status.get("usage") or {}).get("cost")
        if status.get("status") == "completed":
            d = job_dir(m, task, model)
            os.makedirs(d, exist_ok=True)
            clip = os.path.join(d, "run%d.mp4" % n)
            data = api("/videos/%s/content?index=0" % rec["job_id"], key, timeout=300)
            with open(clip, "wb") as f:
                f.write(data)
            rec["clip"] = os.path.relpath(clip, m["_dir"])
            rec["probe"] = probe(clip)
        else:
            rec["error"] = rec["error"] or {
                "status": status.get("status"),
                "detail": status.get("error"),
            }
    except urllib.error.HTTPError as e:
        rec["error"] = {"http": e.code, "body": e.read().decode("utf-8", "replace")[:1500]}
    except Exception as e:  # noqa: BLE001 -- a lane that dies is a result, not a crash
        rec["error"] = {"exception": "%s: %s" % (type(e).__name__, e)}
    rec["t_end"] = round(time.perf_counter() - t0, 3)
    rec["checks"] = run_checks(m, task, rec) if rec.get("clip") else []
    d = job_dir(m, task, model)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "run%d.json" % n), "w", encoding="utf-8") as f:
        json.dump(rec, f, indent=1)
    pr = rec.get("probe") or {}
    say(
        "  %-6s %-12s run%d  %7.1fs  $%-7s %sx%s %ss %s  %s"
        % (
            task["id"],
            model["key"],
            n,
            rec.get("t_done") or rec["t_end"],
            "%.3f" % rec["cost_usd"] if rec.get("cost_usd") is not None else "?",
            pr.get("width"),
            pr.get("height"),
            pr.get("duration"),
            "audio" if pr.get("audio") else "silent",
            " ".join(
                "%s:%s" % (c["type"], {True: "PASS", False: "FAIL"}.get(c.get("pass"), "-"))
                for c in rec["checks"]
            )
            or ("ERROR " + json.dumps(rec["error"])[:220] if rec["error"] else ""),
        )
    )
    return rec


# --------------------------------------------------------------------------- checks

_OCR, _WHISPER = None, None


def letters(s):
    return re.sub(r"[^A-Z0-9]", "", s.upper())


def check_ocr(clip, c):
    global _OCR
    if _OCR is None:
        from rapidocr_onnxruntime import RapidOCR

        _OCR = RapidOCR()
    want = letters(c["expect"])
    every = c.get("every", 0.25)
    best = {"text": "", "t": None, "score": 0.0}
    frames, read = 0, 0
    with tempfile.TemporaryDirectory(prefix="vrace-ocr-") as tmp:
        subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-i",
                clip,
                "-vf",
                "fps=%s" % (1 / every),
                os.path.join(tmp, "f%04d.png"),
            ],
            check=True,
        )
        for fn in sorted(os.listdir(tmp)):
            t = (int(fn[1:5]) - 1) * every
            res, _ = _OCR(os.path.join(tmp, fn))
            frames += 1
            read += any(want in letters(x[1]) for x in res or [])
            for _box, text, score in res or []:
                got = letters(text)
                # closeness to the expected word: shared letters in order (a crude edit similarity)
                sim = _similar(got, want)
                if sim > best["score"] or (
                    sim == best["score"] and float(score) > best.get("conf", 0)
                ):
                    best = {
                        "text": text,
                        "t": round(t, 2),
                        "score": round(sim, 3),
                        "conf": float(score),
                    }
    return {
        "type": "ocr",
        "expect": c["expect"],
        "pass": best["score"] >= 0.999,
        "best": best,
        "share": round(read / frames, 3) if frames else 0.0,
    }


def _similar(a, b):
    if not a or not b:
        return 0.0
    if b in a:
        return 1.0
    import difflib

    return difflib.SequenceMatcher(None, a, b).ratio()


def check_speech(clip, c):
    global _WHISPER
    if _WHISPER is None:
        from faster_whisper import WhisperModel

        _WHISPER = WhisperModel(c.get("model", "small.en"), device="cpu", compute_type="int8")
    segs, _info = _WHISPER.transcribe(clip, language="en", vad_filter=False, word_timestamps=True)
    words, text = [], ""
    for s in segs:
        text += s.text
        words += [[round(w.start, 2), round(w.end, 2), w.word] for w in (s.words or [])]
    norm = lambda s: re.sub(r"[^a-z0-9 ]", "", s.lower())  # noqa: E731
    heard = norm(text)
    hits = {e: norm(e) in heard for e in c["expect"]}
    return {
        "type": "speech",
        "expect": c["expect"],
        "pass": all(hits.values()),
        "hits": hits,
        "text": text.strip(),
        "words": words,
    }


def run_checks(m, task, rec):
    clip = os.path.join(m["_dir"], rec["clip"])
    out = []
    for c in task.get("checks") or []:
        try:
            if c["type"] == "ocr":
                out.append(check_ocr(clip, c))
            elif c["type"] == "speech":
                out.append(check_speech(clip, c))
        except Exception as e:  # noqa: BLE001 -- a check that cannot run says so
            out.append({"type": c["type"], "pass": None, "error": "%s: %s" % (type(e).__name__, e)})
    return out


# --------------------------------------------------------------------------- summary


def summarise(m, cat):
    race = {
        "id": m.get("id"),
        "built_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "models": [],
        "tasks": [],
    }
    for model in m["models"]:
        p = params(m, model)
        race["models"].append(
            {
                "key": model["key"],
                "id": model["id"],
                "label": model.get("label", model["id"]),
                "params": p,
                "list_price": price(cat, model, p) if cat else None,
            }
        )
    for task in m["tasks"]:
        tt = {
            "id": task["id"],
            "label": task.get("label", task["id"]),
            "prompt": task["prompt"],
            "checks": task.get("checks") or [],
            "lanes": {},
        }
        for model in m["models"]:
            d = job_dir(m, task, model)
            runs = []
            if os.path.isdir(d):
                for fn in sorted(os.listdir(d)):
                    if re.match(r"run\d+\.json$", fn):
                        with open(os.path.join(d, fn), encoding="utf-8") as f:
                            runs.append(json.load(f))
            ok = [r for r in runs if r.get("clip")]
            lane = {"runs": len(runs), "errors": len(runs) - len(ok)}
            bad = [r for r in runs if not r.get("clip")]
            if bad:  # a refusal is a result: when it came, and what the model said
                lane["failed"] = [
                    {
                        "run": r["run"],
                        "t_done": r.get("t_done") or r.get("t_end"),
                        "error": r.get("error"),
                    }
                    for r in bad
                ]
                med_f = statistics.median(f["t_done"] for f in lane["failed"])
                lane["fail_pick"] = min(
                    lane["failed"], key=lambda f: (abs(f["t_done"] - med_f), f["run"])
                )
            if ok:
                med_t = statistics.median(r["t_done"] for r in ok)
                pick = min(ok, key=lambda r: (abs(r["t_done"] - med_t), r["run"]))
                costs = [r["cost_usd"] for r in ok if r.get("cost_usd") is not None]
                lane.update(
                    {
                        "median": {
                            "t_done": med_t,
                            "cost_usd": statistics.median(costs) if costs else None,
                        },
                        "all": [
                            {k: r.get(k) for k in ("run", "t_done", "cost_usd", "clip", "probe")}
                            | {
                                "checks": [
                                    {k: c.get(k) for k in ("type", "pass")}
                                    for c in r.get("checks", [])
                                ]
                            }
                            for r in ok
                        ],
                        "pick": {
                            k: pick.get(k)
                            for k in (
                                "run",
                                "t_done",
                                "cost_usd",
                                "clip",
                                "probe",
                                "timeline",
                                "checks",
                                "job_id",
                            )
                        },
                    }
                )
            else:
                lane["error"] = runs[-1].get("error") if runs else None
            tt["lanes"][model["key"]] = lane
        race["tasks"].append(tt)
    p = os.path.join(m["_dir"], m["out"], "race.json")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(race, f, ensure_ascii=False, indent=1)
    return p, race


def board(race):
    for t in race["tasks"]:
        say("\n%s -- %s" % (t["id"], t["label"]))
        for k, ln in t["lanes"].items():
            md = ln.get("median")
            if not md:
                say("  %-12s no clip (%s)" % (k, json.dumps(ln.get("error"))[:160]))
                continue
            ck = " ".join(
                "%s:%s" % (c["type"], {True: "PASS", False: "FAIL"}.get(c.get("pass"), "-"))
                for c in ln["pick"].get("checks") or []
            )
            say(
                "  %-12s %d/%d  median %6.1fs  $%s  %s"
                % (
                    k,
                    len(ln["all"]),
                    ln["runs"],
                    md["t_done"],
                    "%.3f" % md["cost_usd"] if md["cost_usd"] is not None else "?",
                    ck,
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
    ap.add_argument("--check", action="store_true", help="re-run the checks on the clips on disk")
    ap.add_argument("--only", action="append", help="model key (repeatable)")
    ap.add_argument("--task", action="append", help="task id (repeatable)")
    ap.add_argument("--runs", type=int)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()

    m = load_manifest(a.manifest)
    cat = catalogue()
    models = [x for x in m["models"] if not a.only or x["key"] in a.only]
    tasks = [x for x in m["tasks"] if not a.task or x["id"] in a.task]
    for x in models:
        if x["id"] not in cat:
            sys.exit("not an OpenRouter video model: %s" % x["id"])

    if a.summary:
        p, race = summarise(m, cat)
        board(race)
        say("\nwrote %s" % os.path.relpath(p, _env.ROOT))
        return 0
    if a.check:
        for task in tasks:
            for model in models:
                d = job_dir(m, task, model)
                for fn in sorted(os.listdir(d)) if os.path.isdir(d) else []:
                    if re.match(r"run\d+\.json$", fn):
                        p = os.path.join(d, fn)
                        with open(p, encoding="utf-8") as f:
                            rec = json.load(f)
                        if rec.get("clip"):
                            rec["checks"] = run_checks(m, task, rec)
                            with open(p, "w", encoding="utf-8") as f:
                                json.dump(rec, f, indent=1)
                            say(
                                "  %s %s %s %s"
                                % (
                                    task["id"],
                                    model["key"],
                                    fn,
                                    [
                                        (
                                            c["type"],
                                            c.get("pass"),
                                            (c.get("best") or {}).get("text") or c.get("text"),
                                        )
                                        for c in rec["checks"]
                                    ],
                                )
                            )
        summarise(m, cat)
        return 0

    runs = a.runs or m["runs"]
    todo = [
        (t, mo, n)
        for n in range(1, runs + 1)
        for t in tasks
        for mo in models
        if a.force or not os.path.exists(os.path.join(job_dir(m, t, mo), "run%d.json" % n))
    ]
    total = 0.0
    say("%-12s %-36s %-6s %-5s %-5s %8s" % ("key", "model", "res", "secs", "audio", "$/job"))
    for x in models:
        p = params(m, x)
        pr = price(cat, x, p)
        say(
            "%-12s %-36s %-6s %-5s %-5s %8s"
            % (
                x["key"],
                x["id"],
                p.get("resolution"),
                p.get("duration"),
                p.get("generate_audio"),
                "%.3f" % pr if pr is not None else "?",
            )
        )
    for _t, mo, _n in todo:
        total += price(cat, mo, params(m, mo)) or 0
    say(
        "\n%d jobs to send (%d prompts x %d models x %d runs, minus those on disk); list price $%.2f"
        % (len(todo), len(tasks), len(models), runs, total)
    )
    if a.plan or not todo:
        if not todo:
            board(summarise(m, cat)[1])
        return 0
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not key:
        sys.exit("OPENROUTER_API_KEY is not set (put it in .env)")
    waves = {}
    for t, mo, n in todo:
        waves.setdefault((n, t["id"]), []).append((t, mo, n))
    spent = 0.0
    for (n, tid), lanes in waves.items():
        say("\nrun %d, prompt %s: %d models at once" % (n, tid, len(lanes)))
        with cf.ThreadPoolExecutor(max_workers=len(lanes)) as ex:
            for fu in cf.as_completed(
                [ex.submit(run_job, m, cat, t, mo, k, key) for t, mo, k in lanes]
            ):
                spent += fu.result().get("cost_usd") or 0
    p, race = summarise(m, cat)
    board(race)
    say("\nspent $%.2f" % spent)
    _project.record(
        os.path.basename(m["_dir"]),
        "video-race",
        script=__file__,
        argv=sys.argv[1:],
        note="%d jobs, $%.2f; race data in %s" % (len(todo), spent, os.path.relpath(p, m["_dir"])),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
