"""Where Sketch Studio records what every run cost: kitcut's MongoDB, collection studio_runs.

The database is the one kitcut-web uses (MONGODB_URI in .env, Atlas). Its name is always
"kitcut", whatever the URI's path says, exactly as kitcut-web's lib/db.ts and
scripts/process-queue.py hard-code it, so a URI copied from another project cannot write into
that project's data.

One document per run, snake_case, real UTC datetimes (the kitcut-web conventions):

    _id                 the film id (studio-20260925-131102-k3f9qa), or "smoke:<session>"
    kind                "film" | "smoke"
    source              "web" | "cli" | "smoke" | "backfill"
    state               "queued" | "running" | "finishing" | "done" | "failed" | "cancelled" |
                        "interrupted" (the server stopped while Claude was working)
    prompt, model, ok, error, turns, seconds, session_id, host, release (the code it ran on)
    stages              {claude, waited (for the machine, inside Claude's part), sound, render}
    auth, via           "api"/"sdk" (billed per token) or "login" (the machine's Claude Code plan)
    engine_changed      lines Claude changed in its copy of the engine (outputs/engine.diff)
    cost_usd            the Claude API cost: the SDK's own total, or the meter's if the run
                        never reached its end
    cost_metered_usd    the same, priced here from the token counts (a cross-check)
    client              who asked: "u:<account>" through the public site (X-Client-Ip), else
                        the visitor's IP as Cloudflare saw it, or "local"
    tokens              {input, output, cache_read, cache_write_5m, cache_write_1h, web_search}
    calls               one entry per Claude API response: {message_id, at, model, tokens...,
                        cost_usd}
    created_at, updated_at, finished_at

A second collection, studio_hosts, holds one document ("studio"): the tunnel URL the studio can be
reached at now, which the public site (kitcut-hq/sketch-studio on Vercel) looks up per request.

The document is written when a film is asked for (state queued, so it counts toward the day's
limits at once), when it starts, as its cost grows and at the end, so a run that dies half-way (a
crash, a power cut) still shows what it spent. If the database cannot be reached the final record
goes to the outbox (STUDIO_HOME/outbox.jsonl), and `python studio/agent.py --sync` sends it later.
During a ship two servers share the home (peers.py, KI-031) and may both append while a sync
rewrites the file, so every append and every rewrite happens under outbox.jsonl.lock (locks.py),
and a row appended while a sync is sending is still there after it.
"""

import os
import json
import socket
import contextlib
from datetime import UTC, datetime

import locks

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
                row = {"_id": run_id, "created_at": created, **doc}
                try:
                    self._append(json.dumps(row, default=str))
                    kept = "kept in %s" % self.outbox
                except OSError as err:
                    kept = "and could not keep it in %s either (%s)" % (self.outbox, err)
                print("  cost log: could not write to MongoDB (%s); %s" % (e, kept))
            return False

    def _append(self, line):
        """One row onto the outbox. Two servers may finish films at once during a ship (peers.py,
        KI-031), and sync() rewrites the file: so the row goes on in ONE write to an O_APPEND
        descriptor (never interleaved with another row), under the outbox's lock (never between
        sync's read and its rewrite). A lock that cannot be had (its file cannot be made, or a
        stalled peer holds it) does not lose the row: it is appended without the lock."""
        os.makedirs(os.path.dirname(self.outbox) or ".", exist_ok=True)
        data = (line + "\n").encode("utf-8")
        flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_BINARY", 0)
        with contextlib.ExitStack() as held:
            with contextlib.suppress(OSError):  # locks.LockTimeout is one too
                held.enter_context(locks.locked(self.outbox + ".lock"))
            fd = os.open(self.outbox, flags, 0o644)
            try:
                os.write(fd, data)
            finally:
                os.close(fd)

    def get(self, run_id):
        """One run's document, per-call detail included; None when there is none or the database
        cannot be reached (a caller that must not overwrite what it could not read checks)."""
        try:
            return self.col().find_one({"_id": run_id})
        except Exception:  # noqa: BLE001 -- as save(): the record must never fail a film
            return None

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

    def note_login(self, ok, why=None):
        """The daily check of the studio machine's Claude login (agent.py --check-login), beside
        where the site finds the studio: kitcut.studio_hosts, document "studio", field "login"."""
        self.col().database["studio_hosts"].update_one(
            {"_id": "studio"},
            {"$set": {"login": {"ok": ok, "why": why, "host": HOST, "checked_at": now()}}},
            upsert=True,
        )

    def _rows(self):
        """The outbox's rows as written, one string each (none when there is no outbox)."""
        try:
            with open(self.outbox, encoding="utf-8") as f:
                return [x.strip() for x in f if x.strip()]
        except FileNotFoundError:
            return []

    def sync(self):
        """Send what the outbox holds; returns (sent, left).

        The rows are read under the outbox's lock and sent without it (the database may take
        seconds a row to refuse, and a server finishing a film must not wait on that to append).
        Then, under the lock again, the file is rewritten as it is NOW less one copy of each row
        sent: a row another server appended meanwhile stays, and a row a second sync sent too is
        taken out once (a run's document is an upsert, so sending it twice does no harm)."""
        if not self.outbox or not os.path.exists(self.outbox):
            return 0, 0
        with locks.locked(self.outbox + ".lock"):
            pending = self._rows()
        sent = []
        for line in pending:
            d = json.loads(line)
            run_id = d.pop("_id")
            for k in ("created_at", "updated_at", "finished_at"):
                if isinstance(d.get(k), str):
                    d[k] = datetime.fromisoformat(d[k])
            if self.save(run_id, d):
                sent.append(line)
        with locks.locked(self.outbox + ".lock"):
            now = self._rows()
            for line in sent:
                if line in now:
                    now.remove(line)
            if now:
                tmp = "%s.%d.tmp" % (self.outbox, os.getpid())
                with open(tmp, "w", encoding="utf-8", newline="\n") as f:
                    f.writelines(x + "\n" for x in now)
                os.replace(tmp, self.outbox)
            elif os.path.exists(self.outbox):
                os.remove(self.outbox)
        return len(sent), len(pending) - len(sent)


class MemoryStore:
    """The same interface in memory, for tests."""

    def __init__(self):
        self.docs = {}

    def save(self, run_id, fields, final=False):
        d = self.docs.setdefault(run_id, {"_id": run_id, "created_at": now()})
        d.update(fields, updated_at=now())
        return True

    def get(self, run_id):
        return self.docs.get(run_id)

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

    def note_login(self, ok, why=None):
        self.login = {"ok": ok, "why": why, "host": HOST, "checked_at": now()}

    def sync(self):
        return 0, 0


HOST = socket.gethostname()
