#!/usr/bin/env python
"""Run one real edit of a scene or character (edits.py), with Claude, from the command line:
to see what an asking makes, and to measure what an edit costs (the site's price for one is set
from these numbers: lib/plans.js ASSET_EDIT).

    python studio/edit_try.py --project p-4atnpdejpq --name hedgehog --ask "A red scarf." \
        [--mark 0.5,0.3[,0.2,0.1]:"here"] [-n 2] [--model claude-fable-5-2] [--effort high] \
        [--auth login|api] [--out DIR] [--use a]

It works on STUDIO_HOME as it is (point STUDIO_HOME at a copy to leave a library untouched): the
edit is kept with the member as any edit is, nothing is chosen unless --use names a variation.
Prints the state, what each variation changed, Claude's time and cost, and copies the pictures
to --out. No record is written to the database (a memory store stands in).
"""

import os
import sys
import glob
import json
import time
import shutil
import asyncio
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agent  # noqa: E402 -- imports _env first
import edits  # noqa: E402
import library  # noqa: E402
import server  # noqa: E402
import store  # noqa: E402
from film import Film  # noqa: E402


def client_of(project):
    dirs = glob.glob(os.path.join(library.ROOT, "*", project))
    if len(dirs) != 1:
        sys.exit("project %s: %d libraries found" % (project, len(dirs)))
    idx = json.load(open(os.path.join(dirs[0], "index.json"), encoding="utf-8"))
    for fid in idx.get("films") or []:
        f = Film.open(fid)
        if f and f.record().get("client"):
            return f.record()["client"]
    sys.exit("project %s: no episode names its client" % project)


def mark(s):
    at, _, text = s.partition(":")
    v = [float(x) for x in at.split(",")]
    if len(v) not in (2, 4):
        raise argparse.ArgumentTypeError("a mark is x,y or x,y,w,h then :its note")
    return dict(zip(("x", "y", "w", "h"), v)) | {"text": text}


async def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--project", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--ask", default="")
    ap.add_argument("--mark", type=mark, action="append", default=[])
    ap.add_argument("-n", type=int, default=2)
    ap.add_argument("--model")
    ap.add_argument("--effort")
    ap.add_argument("--auth", default=os.environ.get("STUDIO_LOCAL_AUTH") or "login")
    ap.add_argument("--out")
    ap.add_argument("--use", help="make this variation the member's next version")
    a = ap.parse_args()
    agent.STORE = mem = store.MemoryStore()
    client = client_of(a.project)
    claude = {k: v for k, v in (("model", a.model), ("effort", a.effort)) if v}
    t0 = time.time()
    try:
        job = edits.start(
            client, a.project, a.name, server.SCHED, a.ask, a.mark, a.n, auth=a.auth, claude=claude
        )
    except edits.EditError as e:
        sys.exit("refused: %s" % e.text)
    last = None
    while not job["task"].done():
        await asyncio.sleep(3)
        now = (mem.docs.get(job["id"]) or {}).get("now")
        if now and now != last:
            print("  %4ds  %s" % (time.time() - t0, now), flush=True)
            last = now
    e = edits.get(client, a.project, a.name, job["k"])
    doc = mem.docs.get(job["id"]) or {}
    print("\n%s: %s%s" % (e["id"], e["state"], " -- %s" % e["error"] if e.get("error") else ""))
    for v in e["variations"]:
        print("  %s: %s" % (v["letter"].upper(), v["what"]))
    if e.get("summary"):
        print("  summary: %s" % e["summary"])
    print(
        "  asked %d, delivered %s; %s at %s effort; %.0f s; Claude $%.3f, pictures $%.3f; %s tokens"
        % (
            e["n"],
            doc.get("delivered"),
            doc.get("model"),
            doc.get("effort"),
            doc.get("seconds") or 0,
            doc.get("claude_cost_usd") or 0,
            doc.get("image_cost_usd") or 0,
            doc.get("tokens"),
        )
    )
    if a.out:
        os.makedirs(a.out, exist_ok=True)
        for letter in [v["letter"] for v in e["variations"]] + ["marks"]:
            p = edits.picture(client, a.project, a.name, job["k"], letter)
            if p:
                shutil.copyfile(p, os.path.join(a.out, "%s-%d-%s.png" % (a.name, job["k"], letter)))
        print("  pictures in %s" % a.out)
    if a.use and e["state"] == "done":
        got = edits.use(client, a.project, a.name, job["k"], a.use, force=True)
        print("  %s is now version %d" % (a.name, got["version"]))


if __name__ == "__main__":
    asyncio.run(main())
