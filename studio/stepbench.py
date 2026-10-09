#!/usr/bin/env python
"""Which model may do the studio's small steps: the same films' words by each, timed and read blind.

    python studio/stepbench.py --films <folder> ... --plan              what would run; no call
    python studio/stepbench.py --films <folder> ... --models a,b,c      write each film's share
                                                                        words and log entry by each
    python studio/stepbench.py --judge                                  each answer read blind
                                                                        beside the first model's
    python studio/stepbench.py --report                                 the table

The author of a film is Opus (agent.MODEL), and that is measured elsewhere (bakeoff.py). Around the
author the studio asks single questions with no tools: the words a film is shared with (share.py),
a series' episode-log entry (canon.py), the YouTube draft (ytdraft.py), the second reader
(review.py; its own bench is defects.py --part review --model). "A smaller model is enough for
those" is a proposal, and this measures it on films already made: the same material to every
model, each call's seconds, what the step's own rules refused (a retry, a thumbnail put right),
and a blind read of every answer beside the baseline's -- which states something the film does
not, and which one a publisher would run. The baseline is the first of --models, and naming it
twice (a tag after a colon: claude-opus-5-5:again) measures the judge's own noise.

A model named with its provider (openai/gpt-6-luna) is asked through OpenRouter (llm.py); any
other through Claude Code on this machine's login. --films takes films' folders, or folders of
bake-off results (every finished film under them). Nothing is written into a film: its share
draft is put back as it was. Results: --out (default temp/stepbench in the main checkout).
"""

import os
import sys
import json
import time
import random
import asyncio
import argparse
import statistics
import contextvars

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(KIT, "scripts"))
import agent  # noqa: E402, F401 -- imports _env first
import canon  # noqa: E402
import film as films  # noqa: E402
import share  # noqa: E402
import thumbs  # noqa: E402
import ytdraft  # noqa: E402

STEPS = ("share", "canon")
JUDGE_MODEL, JUDGE_EFFORT = ytdraft.MODEL, "high"
JUDGE = (
    "You compare two answers to the same writing task about one short film, given everything the "
    "writers were given. You do not know who wrote which. Answer only with the JSON object asked "
    "for."
)
JUDGE_ASK = """\
Two writers were given the task below about the same film. Read the film, then both answers.

1. For each answer, list every statement in it that the film (its narration, its maker's words, \
the pages listed) does not support: an invented number, feature, name, date or claim. An empty \
list when there is none. Wording or emphasis is not an invention.
2. Which answer would a careful publisher run: "A", "B", or "same" when a reader would not care \
which. Judge what a viewer reads -- is it true to the film, specific, in the film's language, \
would the right person click -- not length or style alone.

Answer with one JSON object and nothing else:
{{"invented_a": ["..."], "invented_b": ["..."], "better": "A" | "B" | "same", "why": "one sentence"}}

# The task the writers were given
{task}

# Answer A
{a}

# Answer B
{b}"""


def arm(spec):
    """'model[@effort][:tag]' -> (name, model, effort or None)."""
    name = spec
    body, _, _tag = spec.partition(":")
    model, _, effort = body.partition("@")
    return name, model, effort or None


def slug(name):
    return "".join(c if c.isalnum() or c in "-." else "_" for c in name)


def find_films(paths):
    """Finished films under the folders given: a film's own folder, or bake-off results."""
    out, seen = [], set()
    for p in paths:
        p = os.path.abspath(p)
        cands = [p] if os.path.isfile(os.path.join(p, "studio.json")) else []
        for root, dirs, names in os.walk(p):
            if "result.json" in names:
                try:
                    with open(os.path.join(root, "result.json"), encoding="utf-8") as f:
                        r = json.load(f)
                except (OSError, ValueError):
                    r = {}
                if r.get("ok") and r.get("film"):
                    cands.append(r["film"])
                dirs[:] = []
        for d in cands:
            if d in seen or not os.path.isdir(d):
                continue
            seen.add(d)
            f = films.Film(d)
            if share.finished(f):
                out.append(f)
    return out


CALLS = contextvars.ContextVar("calls", default=None)
_ask = ytdraft.ask_json


async def _counted(*a, **k):
    """ytdraft.ask_json, each call's seconds noted for the task that asked (share.py asks through
    the module, so the count is taken here and not in its code)."""
    t = time.time()
    try:
        return await _ask(*a, **k)
    finally:
        if CALLS.get() is not None:
            CALLS.get().append(round(time.time() - t, 1))


ytdraft.ask_json = _counted


async def material(f):
    """What every model is given for this film, made once."""
    mat = await asyncio.to_thread(ytdraft.material, f)
    got = await thumbs.sheet(f)
    mat = (
        dict(mat, sheet=got, moments_sheet=True) if got else dict(mat, sheet=ytdraft._sheet(f))  # noqa: SLF001
    )
    return mat, canon.material(f)


async def one_share(f, mat, model, effort):
    """share.write as the studio runs it, uncached, the film's own draft put back after."""
    p = share.cache_path(f)
    try:
        with open(p, "rb") as fh:
            before = fh.read()
    except OSError:
        before = None
    if before is not None:
        os.remove(p)
    calls = []
    CALLS.set(calls)  # this task's own: asyncio gives every task its context
    t0 = time.time()
    try:
        d = await share.write(f, "login", model, effort or share.EFFORT, mat, record=False)
        out = {k: d.get(k) for k in ("title", "description", "language", "thumbnails", "notes")}
        out |= {"ok": True, "cost_usd": d.get("cost_usd")}
    except Exception as e:  # noqa: BLE001 -- a model that cannot do the step is a row
        out = {"ok": False, "error": str(e)[:300]}
    finally:
        if os.path.exists(p):
            os.remove(p)
        if before is not None:
            with open(p, "wb") as fh:
                fh.write(before)
    return out | {"seconds": round(time.time() - t0, 1), "call_s": calls}


async def one_canon(f, cmat, model, effort):
    t0 = time.time()
    try:
        d, cost = await ytdraft.ask_json(
            canon.ask_text(cmat),
            None,
            "login",
            None,
            model,
            effort or canon.EFFORT,
            canon.WRITER,
            "canon",
        )
        e = canon.clean(d, cmat, f.id)
        out = {k: e[k] for k in ("title", "story", "catchphrases", "twist", "fact", "new")}
        out |= {"callbacks": e["callbacks"], "ok": True, "cost_usd": round(cost, 4)}
    except Exception as e:  # noqa: BLE001
        out = {"ok": False, "error": str(e)[:300]}
    s = round(time.time() - t0, 1)
    return out | {"seconds": s, "call_s": [s]}


def kept(out, step, name, fid):
    return os.path.join(out, step, slug(name), fid + ".json")


def read_json(p):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def write_json(p, d):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=1, ensure_ascii=False)


async def run(a, todo, arms):
    sem = asyncio.Semaphore(a.jobs)
    mats = {}

    async def mat_of(f):
        if f.id not in mats:
            mats[f.id] = await material(f)
        return mats[f.id]

    for f in todo:  # one at a time: a sheet not made yet takes the browser
        await mat_of(f)
    index = {f.id: {"dir": f.dir, "title": f.record().get("title")} for f in todo}
    write_json(os.path.join(a.out, "films.json"), index)

    async def one(f, step, name, model, effort):
        p = kept(a.out, step, name, f.id)
        if os.path.exists(p) and not a.redo:
            return
        async with sem:
            mat, cmat = await mat_of(f)
            got = await (
                one_share(f, mat, model, effort)
                if step == "share"
                else one_canon(f, cmat, model, effort)
            )
        write_json(p, got | {"model": model, "effort": effort})
        print(
            "%-6s %-34s %s  %5.1f s  %s"
            % (step, name, f.id[-6:], got["seconds"], "ok" if got["ok"] else got["error"][:80]),
            flush=True,
        )

    for name, model, effort in arms:  # an arm at a time: one arm's films share the machine
        for step in a.steps:
            await asyncio.gather(*(one(f, step, name, model, effort) for f in todo))


def answer_text(step, d):
    if step == "share":
        th = "; ".join(
            '%s "%s"' % (t.get("layout"), t.get("words")) for t in d.get("thumbnails") or []
        )
        return "Title: %s\nDescription: %s\nThumbnail words: %s" % (
            d.get("title"),
            d.get("description"),
            th,
        )
    keys = ("title", "story", "catchphrases", "twist", "fact", "new", "callbacks")
    return json.dumps({k: d.get(k) for k in keys}, ensure_ascii=False, indent=1)


async def judge(a, arms):
    index = read_json(os.path.join(a.out, "films.json")) or {}
    base = arms[0][0]
    sem = asyncio.Semaphore(a.jobs)
    rnd = random.Random(7)

    async def one(step, name, fid, task):
        p = kept(a.out, step + "-judge", name, fid)
        mine, theirs = (
            read_json(kept(a.out, step, name, fid)),
            read_json(kept(a.out, step, base, fid)),
        )
        if (os.path.exists(p) and not a.redo) or not mine or not theirs:
            return
        if not (mine.get("ok") and theirs.get("ok")):
            return
        flip = rnd.random() < 0.5  # which side the baseline sits on
        A, B = (mine, theirs) if flip else (theirs, mine)
        text = JUDGE_ASK.format(task=task, a=answer_text(step, A), b=answer_text(step, B))
        async with sem:
            try:
                d, _ = await ytdraft.ask_json(
                    text, None, "login", None, a.judge, JUDGE_EFFORT, JUDGE, "stepbench"
                )
            except Exception as e:  # noqa: BLE001
                print("judge %s %s %s failed: %s" % (step, name, fid[-6:], str(e)[:120]))
                return
        side = {"A": "mine" if flip else "base", "B": "base" if flip else "mine"}
        write_json(
            p,
            {
                "better": side.get(str(d.get("better")).strip().upper(), "same"),
                "invented_mine": d.get("invented_a" if flip else "invented_b") or [],
                "invented_base": d.get("invented_b" if flip else "invented_a") or [],
                "why": d.get("why"),
            },
        )
        print("judged %-6s %-34s %s" % (step, name, fid[-6:]), flush=True)

    jobs = []
    for fid, meta in index.items():
        f = films.Film(meta["dir"])
        mat, cmat = await material(f)
        tasks = {"share": share.ask_text(mat), "canon": canon.ask_text(cmat)}
        for step in a.steps:
            for name, _, _ in arms[1:]:
                jobs.append(one(step, name, fid, tasks[step]))
    await asyncio.gather(*jobs)


def report(a, arms):
    index = read_json(os.path.join(a.out, "films.json")) or {}
    base = arms[0][0]
    for step in a.steps:
        print("\n%s -- %d film(s); baseline %s" % (step, len(index), base))
        print(
            "  %-34s %5s %9s %9s %6s %7s   %s"
            % ("model", "ok", "median s", "worst s", "2nd", "$/film", "blind vs baseline")
        )
        for name, _, _ in arms:
            rows = [read_json(kept(a.out, step, name, fid)) for fid in index]
            rows = [r for r in rows if r]
            if not rows:
                continue
            ok = [r for r in rows if r.get("ok")]
            secs = sorted(r["seconds"] for r in ok) or [0]
            again = sum(1 for r in ok if len(r.get("call_s") or []) > 1)
            usd = statistics.mean([r.get("cost_usd") or 0 for r in ok]) if ok else 0
            js = [read_json(kept(a.out, step + "-judge", name, fid)) for fid in index]
            js = [j for j in js if j]
            verdict = ""
            if js:
                verdict = "better %d, same %d, worse %d; invented: %d film(s) (baseline %d)" % (
                    sum(1 for j in js if j["better"] == "mine"),
                    sum(1 for j in js if j["better"] == "same"),
                    sum(1 for j in js if j["better"] == "base"),
                    sum(1 for j in js if j["invented_mine"]),
                    sum(1 for j in js if j["invented_base"]),
                )
            print(
                "  %-34s %2d/%-2d %9.1f %9.1f %6d %7.3f   %s"
                % (name, len(ok), len(rows), statistics.median(secs), secs[-1], again, usd, verdict)
            )
    print("\n2nd: films whose answer the step's own rules sent back for a second call.")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--films", nargs="*", default=[], help="films' folders, or bake-off results")
    ap.add_argument("--limit", type=int, help="at most this many films")
    ap.add_argument(
        "--models",
        default=ytdraft.MODEL,
        help="comma-separated model[@effort][:tag]; the first is the baseline",
    )
    ap.add_argument("--steps", default=",".join(STEPS), help="share,canon")
    ap.add_argument(
        "--out", default=os.path.join(os.environ.get("STUDIO_REPO") or KIT, "temp", "stepbench")
    )
    ap.add_argument("--plan", action="store_true", help="what would run; no call")
    ap.add_argument("--judge", nargs="?", const=JUDGE_MODEL, help="read the answers blind")
    ap.add_argument("--report", action="store_true", help="print the table")
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--redo", action="store_true", help="ask again what is kept")
    a = ap.parse_args()
    a.steps = [s for s in a.steps.split(",") if s in STEPS]
    arms = [arm(s) for s in a.models.split(",") if s]
    todo = find_films(a.films)[: a.limit] if a.films else []
    if a.plan:
        print("%d film(s), %d model(s), steps %s" % (len(todo), len(arms), ", ".join(a.steps)))
        for f in todo:
            print("  %s  %s" % (f.id, (f.record().get("title") or "")[:60]))
        n = len(todo) * len(arms) * len(a.steps)
        print("%d call(s) or a few more; a call is cents (a share on Opus: $0.05-0.13)" % n)
        return
    if todo:
        asyncio.run(run(a, todo, arms))
    if a.judge:
        asyncio.run(judge(a, arms))
    if a.report or a.judge or todo:
        report(a, arms)


if __name__ == "__main__":
    main()
