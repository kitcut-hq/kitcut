#!/usr/bin/env python
"""The site's database exported to files: every collection of `kitcut`, as mongodump writes them.

    python studio/dbdump.py --plan               the collections, their documents and sizes;
                                                 writes nothing
    python studio/dbdump.py --out <dir>          <dir>/kitcut/<collection>.bson.gz and
                                                 <collection>.metadata.json (its indexes)
    python studio/dbdump.py --upload             the same, then into the mirror bucket under
                                                 db/<day>/ (nightly, kitcut-backup-full.timer)
    python studio/dbdump.py --restore <dir> --uri <mongodb uri> [--db NAME] [--drop]
                                                 a dump back into a database

Why: accounts, credits, every film's record, the YouTube grants and the queue live in one MongoDB
Atlas database (store.py: `kitcut`, on a cluster another site shares), and nothing in either
repository exported it. Atlas's own backups are the first line and are not ours to see from
here; this is the copy that does not depend on them. The bucket's own rule keeps 30 days.

The files are mongodump's: `mongorestore --gzip --dir <dir>` reads them, and so does --restore
here (no MongoDB tools on the machine). Collections are read one after another, so a dump is
not one instant of the database: a film that finished while it ran may be in `studio_runs` and
not yet in `credit_spends`. A restore is a last resort, and says so before it writes.

--restore never writes the database the studio's own MONGODB_URI names under the name `kitcut`
unless --live is given: that is production.
"""

import os
import sys
import gzip
import json
import time
import shutil
import argparse
import tempfile
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backup  # noqa: E402 -- the stdlib only; the bucket's key and the studio's .env
from store import DB  # noqa: E402

BATCH = 500


def client(uri):
    from pymongo import MongoClient  # noqa: PLC0415 -- the venv's, only when a database is read

    return MongoClient(uri, appname="kitcut-dbdump", serverSelectionTimeoutMS=15000)


def live_uri():
    uri = os.environ.get("MONGODB_URI") or backup.setting("MONGODB_URI")
    if not uri:
        sys.exit("MONGODB_URI is not set (the studio's .env)")
    return uri


def plan(db):
    rows = []
    for name in sorted(db.list_collection_names()):
        if name.startswith("system."):
            continue
        st = db.command("collStats", name)
        rows.append((name, st.get("count", 0), st.get("size", 0)))
    return rows


def dump(db, out):
    """Every collection into out/<db>/: [(name, documents, bytes written)]."""
    from bson import json_util  # noqa: PLC0415

    d = os.path.join(out, db.name)
    os.makedirs(d, exist_ok=True)
    done = []
    for name in sorted(db.list_collection_names()):
        if name.startswith("system."):
            continue
        col, n = db[name], 0
        path = os.path.join(d, name + ".bson.gz")
        with gzip.open(path + ".tmp", "wb", compresslevel=6) as f:
            # raw batches: the documents' own bytes, never decoded -- what mongodump writes
            for batch in col.find_raw_batches({}, batch_size=BATCH):
                f.write(batch)
                n += _count(batch)
        os.replace(path + ".tmp", path)
        meta = {
            "options": col.options(),
            "indexes": list(col.list_indexes()),
            "collectionName": name,
        }
        with open(os.path.join(d, name + ".metadata.json"), "w", encoding="utf-8") as f:
            f.write(json_util.dumps(meta))
        done.append((name, n, os.path.getsize(path)))
    return done


def _count(batch):
    """How many BSON documents a raw batch holds (each starts with its own length)."""
    n, i = 0, 0
    while i + 4 <= len(batch):
        i += int.from_bytes(batch[i : i + 4], "little")
        n += 1
    return n


def restore(src, db, drop=False):
    """A dump's collections into db: [(name, documents)]. Indexes are made again."""
    from bson import decode_file_iter, json_util  # noqa: PLC0415

    done = []
    for name in sorted(os.listdir(src)):
        if not name.endswith(".bson.gz"):
            continue
        col = db[name[: -len(".bson.gz")]]
        if drop:
            col.drop()
        n, batch = 0, []
        with gzip.open(os.path.join(src, name), "rb") as f:
            for doc in decode_file_iter(f):
                batch.append(doc)
                if len(batch) >= BATCH:
                    col.insert_many(batch, ordered=False)
                    n, batch = n + len(batch), []
        if batch:
            col.insert_many(batch, ordered=False)
            n += len(batch)
        meta = os.path.join(src, col.name + ".metadata.json")
        if os.path.exists(meta):
            with open(meta, encoding="utf-8") as f:
                for ix in json_util.loads(f.read()).get("indexes") or []:
                    if ix.get("name") == "_id_":
                        continue
                    opts = {k: v for k, v in ix.items() if k not in ("key", "v", "ns")}
                    try:
                        col.create_index(list(ix["key"].items()), **opts)
                    except Exception as e:  # noqa: BLE001 -- the documents are in; say which index is not
                        print("  %s: index %s not made: %s" % (col.name, ix.get("name"), e))
        done.append((col.name, n))
    return done


def upload(out, day):
    """A dump folder into the mirror bucket, db/<day>/. -> rclone's exit code."""
    bucket, env = backup.account()
    dst = "%s:%s/db/%s" % (backup.REMOTE, bucket, day)
    cmd = ["rclone", "copy", out, dst, "--s3-no-check-bucket", "--transfers", "4"]
    r = subprocess.run(cmd, env=env, capture_output=True, text=True, errors="replace", check=False)
    if r.returncode != 0:
        print(r.stderr.strip()[-600:], file=sys.stderr)
    return r.returncode


def _mb(n):
    return "%.1f MB" % (n / 1e6)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--plan", action="store_true", help="the collections and their sizes")
    g.add_argument("--out", metavar="DIR", help="export into DIR/kitcut/")
    g.add_argument("--upload", action="store_true", help="export, then into the mirror bucket")
    g.add_argument("--restore", metavar="DIR", help="a dump's folder of .bson.gz files")
    ap.add_argument("--uri", help="--restore: the database to write (never taken from the .env)")
    ap.add_argument("--db", default=DB, help="--restore: its name (default %s)" % DB)
    ap.add_argument("--drop", action="store_true", help="--restore: empty each collection first")
    ap.add_argument("--live", action="store_true", help="--restore: yes, into production")
    a = ap.parse_args()

    if a.restore:
        if not a.uri:
            ap.error("--restore needs --uri: the database to write is never guessed")
        same = a.uri.split("@")[-1].split("/")[0] == live_uri().split("@")[-1].split("/")[0]
        if same and a.db == DB and not a.live:
            sys.exit(
                "that is the live database (%s on the studio's own cluster): --live to mean it" % DB
            )
        for name, n in restore(a.restore, client(a.uri)[a.db], a.drop):
            print("  %-22s %7d document(s)" % (name, n))
        sys.exit(0)

    db = client(live_uri())[DB]
    if a.plan:
        rows = plan(db)
        for name, n, size in rows:
            print("  %-22s %7d document(s) %10s" % (name, n, _mb(size)))
        print("%d collections, %s before compression" % (len(rows), _mb(sum(r[2] for r in rows))))
        sys.exit(0)
    t0 = time.time()
    out = a.out or tempfile.mkdtemp(prefix="kitcut-dbdump-")
    try:
        done = dump(db, out)
        total = sum(size for _, _, size in done)
        print(
            "%d collections, %d documents, %s compressed, %.0f s"
            % (len(done), sum(n for _, n, _ in done), _mb(total), time.time() - t0)
        )
        if a.upload:
            day = time.strftime("%Y-%m-%d")
            rc = upload(out, day)
            print("%s db/%s/" % ("uploaded to" if rc == 0 else "NOT uploaded to", day))
            sys.exit(rc)
    finally:
        if not a.out:
            shutil.rmtree(out, ignore_errors=True)
    print(json.dumps({"out": os.path.join(out, DB)}))
