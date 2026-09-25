"""Where Sketch Studio records what every run cost: kitcut's MongoDB, collection studio_runs.

The database is the one kitcut-web uses (MONGODB_URI in .env, Atlas). Its name is always
"kitcut", whatever the URI's path says, exactly as kitcut-web's lib/db.ts and
scripts/process-queue.py hard-code it, so a URI copied from another project cannot write into
that project's data.

One document per run, snake_case, real UTC datetimes (the kitcut-web conventions):

    _id                 the job id (studio-20260925-131102), or "smoke:<session>" for --smoke
    kind                "film" | "smoke"
    source              "web" | "cli" | "smoke" | "backfill"
    state               "running" | "done" | "failed"
    prompt, model, ok, error, turns, seconds, stages{claude, sound, render}, session_id, host
    cost_usd            the Claude API cost: the SDK's own total, or the meter's if the run
                        never reached its end
    cost_metered_usd    the same, priced here from the token counts (a cross-check)
    client              who asked: the visitor's IP (forwarded by the public site as X-Client-Ip,
                        or as Cloudflare saw it), or "local"
    tokens              {input, output, cache_read, cache_write_5m, cache_write_1h}
    calls               one entry per Claude API response: {message_id, at, model, tokens...,
                        cost_usd}
    created_at, updated_at, finished_at

A second collection, studio_hosts, holds one document ("studio"): the tunnel URL the studio can be
reached at now, which the public site (kitcut-hq/sketch-studio on Vercel) looks up per request.

The document is written when a run starts and again as its cost grows, so a run that dies
half-way (a crash, a power cut) still shows what it spent. If the database cannot be reached
the final record goes to projects/studio-runs-outbox.jsonl, and `python studio/agent.py --sync`
sends it later.
"""

import os
import json
import socket
from datetime import UTC, datetime

COLLECTION = "studio_runs"
DB = "kitcut"


def now():
    return datetime.now(UTC)


class MongoStore:
    def __init__(self, uri=None, outbox=None):
        self.uri = uri or os.environ.get("MONGODB_URI", "")
        self.outbox = outbox
        self._col = None

    def col(self):
        if self._col is None:
            if not self.uri:
                raise RuntimeError("MONGODB_URI is not set (put it in .env)")
            from pymongo import MongoClient

            # tz_aware: dates come back as UTC-aware, so "today" is worked out in local time
            client = MongoClient(
                self.uri, appname="kitcut-studio", serverSelectionTimeoutMS=8000, tz_aware=True
            )
            col = client[DB][COLLECTION]
            col.create_index([("created_at", -1)])
            col.create_index([("state", 1), ("created_at", -1)])
            self._col = col
        return self._col

    def save(self, run_id, fields, final=False):
        """Upsert the run's document. A final save that cannot reach the database is kept in the
        outbox; an interim one is simply skipped (the final one carries everything)."""
        doc = {**fields, "updated_at": now()}
        created = doc.pop("created_at", None) or now()  # set once, on insert
        try:
            self.col().update_one(
                {"_id": run_id},
                {"$set": doc, "$setOnInsert": {"created_at": created}},
                upsert=True,
            )
            return True
        except Exception as e:  # noqa: BLE001 -- a logging failure must never fail a film
            if final and self.outbox:
                os.makedirs(os.path.dirname(self.outbox), exist_ok=True)
                with open(self.outbox, "a", encoding="utf-8") as f:
                    row = {"_id": run_id, "created_at": created, **doc}
                    f.write(json.dumps(row, default=str) + "\n")
                print("  cost log: could not write to MongoDB (%s); kept in %s" % (e, self.outbox))
            return False

    def runs(self, limit=None, since=None):
        """Every run (or those created since a datetime), oldest first, without the per-call detail."""
        q = {"created_at": {"$gte": since}} if since else {}
        rows = list(self.col().find(q, {"calls": 0}).sort("created_at", 1))
        return rows[-limit:] if limit else rows

    def announce(self, url):
        """Where the studio can be reached now (its tunnel URL; None when it stops), for the public
        site to find: kitcut.studio_hosts, document "studio"."""
        self.col().database["studio_hosts"].update_one(
            {"_id": "studio"},
            {"$set": {"url": url, "host": HOST, "updated_at": now()}},
            upsert=True,
        )

    def sync(self):
        """Send what the outbox holds; returns (sent, left)."""
        if not self.outbox or not os.path.exists(self.outbox):
            return 0, 0
        with open(self.outbox, encoding="utf-8") as f:
            pending = [json.loads(x) for x in f if x.strip()]
        left = []
        for d in pending:
            run_id = d.pop("_id")
            for k in ("created_at", "updated_at", "finished_at"):
                if isinstance(d.get(k), str):
                    d[k] = datetime.fromisoformat(d[k])
            if not self.save(run_id, d):
                left.append({"_id": run_id, **d})
        if left:
            with open(self.outbox, "w", encoding="utf-8") as f:
                for d in left:
                    f.write(json.dumps(d, default=str) + "\n")
        else:
            os.remove(self.outbox)
        return len(pending) - len(left), len(left)


class MemoryStore:
    """The same interface in memory, for tests."""

    def __init__(self):
        self.docs = {}

    def save(self, run_id, fields, final=False):
        d = self.docs.setdefault(run_id, {"_id": run_id, "created_at": now()})
        d.update(fields, updated_at=now())
        return True

    def runs(self, limit=None, since=None):
        rows = sorted(
            (
                {k: v for k, v in d.items() if k != "calls"}
                for d in self.docs.values()
                if not since or d["created_at"] >= since
            ),
            key=lambda d: d["created_at"],
        )
        return rows[-limit:] if limit else rows

    def announce(self, url):
        self.url = url

    def sync(self):
        return 0, 0


HOST = socket.gethostname()
