#!/usr/bin/env python
"""Delete a film for good: its copy online, its record, its folder, and what else names it.

    POST /api/films/<id>/delete      {"plan": true} answers what would go and removes nothing
    python studio/delete_film.py <film-id> [--plan]      by hand, beside the server
                                                         (on the VM: ops.sh delete <film-id>)

There is no way back: nothing is kept, not even a backup (a film is deleted because somebody wants
it gone). So the order is the one that can always be finished by asking again, and that never
leaves a film half there for a watcher:

    1. the copy online (media.delete): every revision, every version a round left, the share
       pictures. First, because it is what the public can reach. Refused or unreachable storage
       stops here, with the film whole.
    2. the record in kitcut.studio_runs, and its rounds' (store.forget). The site lists and plays a
       film from it, so from here nobody finds the film. An unreachable database stops here: the
       film's folder is still there, so asking again finishes the job.
    3. what names the film outside its folder: its place in its library's index and its cast's
       (the next films learn from the last few), its entry in its project's episode log
       (canon.json: the next episode must not call back to it), the library's cached poster, its
       Claude sessions, a round's working copy and marks, and the backups ops.sh replace kept.
    4. the folder, moved out of projects/ in one rename (so no server finds half a film) and then
       removed.

A film still being made, changed by a round, drawn again without branding or on its way to YouTube
is refused (DeleteError 409): stop it, or wait. What a film cost stays in the site's credit table
(the site's own collections are the site's to clean: lib/films.js deleteFilm).
"""

import os
import re
import sys
import glob
import json
import shutil
import asyncio
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agent  # noqa: E402 -- imports _env first; the record store and the studio's .env
import film as films  # noqa: E402
import library  # noqa: E402
import media  # noqa: E402
import rounds  # noqa: E402
import unbrand  # noqa: E402
import youtube  # noqa: E402

BACKUPS = os.path.join(films.HOME, "backups")  # <film id>-<stamp>.tar.gz (ops.sh replace)
TRASH = os.path.join(films.HOME, "tmp")  # where a folder goes in one rename, to be removed


class DeleteError(Exception):
    """Why a film was not deleted: an HTTP status, a reason to act on, and words for a person."""

    def __init__(self, status, reason, message):
        super().__init__(message)
        self.status, self.reason = status, reason


def _alive(jobs, fid):
    j = jobs.get(fid)
    return bool(j and j.get("task") is not None and not j["task"].done())


def why_not(f):
    """(reason, words) when this film cannot be deleted now, else None."""
    rec = f.record()
    if f.state in films.ACTIVE or f.state == "waiting":
        return "making", "This film is still being made. Stop it first."
    if (
        (rec.get("round") or {}).get("state") in rounds.ACTIVE
        or _alive(rounds.JOBS, f.id)
        or os.path.exists(os.path.join(rounds.MARKS, f.id + ".json"))
    ):
        return "round", "This film is being changed; try again in a few minutes."
    if _alive(unbrand.JOBS, f.id) or os.path.exists(os.path.join(unbrand.MARKS, f.id + ".json")):
        return "unbrand", "This film is being drawn again; try again in a few minutes."
    if any(j["film"] == f.id and j["state"] == "sending" for j in youtube.SENDS.values()):
        return "youtube", "This film is being sent to YouTube; try again when that is over."
    return None


def online(f):
    """Every address in the film's record that is a file of its copy online: the film's own, each
    version's (a round's), the share pictures, the thumbnails."""
    mine, out = "%s/%s/" % (media.base(), f.id), []

    def walk(v):
        if isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)
        elif isinstance(v, str) and media.base() and v.startswith(mine) and v not in out:
            out.append(v)

    walk(f.record())
    return out


def sides(f):
    """What is the film's outside its folder, as paths that exist. The id is checked (Film.open),
    so it holds nothing a pattern would read."""
    rid = re.compile("^" + re.escape(f.id) + r"\.r\d+$")
    out = [f.claude_dir]
    for root in (os.path.join(films.HOME, "claude"), rounds.ROOT):
        if os.path.isdir(root):
            out += [os.path.join(root, n) for n in sorted(os.listdir(root)) if rid.match(n)]
    out += [os.path.join(rounds.MARKS, f.id + ".json"), os.path.join(unbrand.MARKS, f.id + ".json")]
    out += sorted(glob.glob(os.path.join(BACKUPS, f.id + "-*.tar.gz")))
    out += sorted(
        glob.glob(os.path.join(library.ROOT, "**", "films", f.id + ".jpg"), recursive=True)
    )
    return [p for p in out if os.path.lexists(p)]


def _size(d):
    n = 0
    for root, _, names in os.walk(d):
        for name in names:
            try:
                n += os.path.getsize(os.path.join(root, name))
            except OSError:
                pass
    return n


def named(f):
    """Where the film's library names it: {"index": in the films the next ones learn from,
    "cast": [members that list it], "canon": in its project's episode log}."""
    lib = library.lib_of(f.record())
    if not lib or not os.path.isdir(library.dir_of(lib)):
        return {"index": False, "cast": [], "canon": False}
    idx = library.load(lib)
    return {
        "index": f.id in (idx.get("films") or []),
        "cast": sorted(
            n for n, e in (idx.get("cast") or {}).items() if f.id in (e.get("films") or [])
        ),
        "canon": any(e.get("film") == f.id for e in library.canon_of(lib)),
    }


def unname(f):
    """Take the film out of its library's index, its cast's lists and its project's episode log.
    A member the film made stays (it is the library's now, and names where it came from)."""
    lib = library.lib_of(f.record())
    if not lib or not os.path.isdir(library.dir_of(lib)):
        return
    with library._lock(lib):
        idx = library.load(lib)
        had = json.dumps(idx, sort_keys=True)
        idx["films"] = [x for x in idx.get("films") or [] if x != f.id]
        for e in (idx.get("cast") or {}).values():
            if f.id in (e.get("films") or []):
                e["films"] = [x for x in e["films"] if x != f.id]
        if json.dumps(idx, sort_keys=True) != had:
            library._save(lib, idx)
        log = library.canon_of(lib)
        kept = [e for e in log if e.get("film") != f.id]
        if len(kept) != len(log):
            library._write_json(
                os.path.join(library.dir_of(lib), library.CANON), {"episodes": kept}
            )


def plan(f):
    """What deleting this film removes, with nothing removed."""
    rec = f.record()
    return {
        "id": f.id,
        "state": f.state,
        "title": rec.get("title"),
        "folder": f.dir,
        "bytes": _size(f.dir),
        "versions": len(rec.get("versions") or []),
        "online": len(online(f)),
        "sides": sides(f),
        "library": named(f),
    }


def _remove(p):
    if os.path.isdir(p) and not os.path.islink(p):
        shutil.rmtree(p, ignore_errors=True)
    else:
        try:
            os.remove(p)
        except FileNotFoundError:
            pass
    return not os.path.lexists(p)


async def delete(f, store=None):
    """Delete the film (see the top of this file for the order and why). Returns what went:
    {"id", "online", "records", "sides", "folder", "left"} -- "left" names what could not be
    removed from the disk (the film is gone all the same: nothing finds those files)."""
    no = why_not(f)
    if no:
        raise DeleteError(409, *no)
    store = store or agent.STORE
    urls = online(f)
    if urls and not media.enabled():
        raise DeleteError(
            503,
            "storage",
            "This film has a copy online and this machine cannot reach the storage to remove it.",
        )
    try:
        gone = await media.delete(f.id, urls=urls)
    except Exception as e:  # noqa: BLE001 -- MediaError, or the network: the film stays whole
        raise DeleteError(
            502, "storage", "The film's copy online could not be removed: %s" % e
        ) from e
    try:
        records = await asyncio.to_thread(store.forget, f.id)
    except Exception as e:  # noqa: BLE001 -- the database: ask again, the folder is still here
        raise DeleteError(
            503, "record", "The film's record could not be removed (%s); ask again." % e
        ) from e
    await asyncio.to_thread(unname, f)
    paths = sides(f)
    left = [p for p in paths if not await asyncio.to_thread(_remove, p)]
    os.makedirs(TRASH, exist_ok=True)
    trash = os.path.join(TRASH, "deleted-%s-%d" % (f.id, os.getpid()))
    os.rename(f.dir, trash)  # one rename: no server finds half a film
    if not await asyncio.to_thread(_remove, trash):
        left.append(trash)
    return {
        "id": f.id,
        "online": gone,
        "records": records,
        "sides": len(paths),
        "folder": f.dir,
        "left": left,
    }


async def _main(args):
    f = films.Film.open(args.film)
    if f is None:
        sys.exit("no film %s on this machine" % args.film)
    if args.plan:
        print(json.dumps(plan(f), indent=1, ensure_ascii=False))
        no = why_not(f)
        if no:
            print("it would be refused now: %s" % no[1])
        return
    try:
        print(json.dumps(await delete(f), indent=1, ensure_ascii=False))
    except DeleteError as e:
        sys.exit("%s: not deleted (%s): %s" % (f.id, e.reason, e))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("film", help="the film's id")
    ap.add_argument("--plan", action="store_true", help="say what would go; remove nothing")
    asyncio.run(_main(ap.parse_args()))
