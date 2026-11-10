#!/usr/bin/env python
"""A series' episode log: one entry per finished episode, so the next episode knows them all.

An episode sees its last five episodes' files (library.MEMORY): at episode twelve, one to seven
are gone, and a twist or a catchphrase comes round again with nobody noticing. The log is short
enough to carry every episode instead. It lives in the project's library,

    <project library>/canon.json   {"episodes": [entry, ...]}, oldest first (library.put_canon)
    entry = {film, made, length, title, story, catchphrases, twist, fact, new, callbacks,
             at, key}

and library.note() gives every next episode the whole of it (library.canon_note). An entry is
written when an episode finishes (premake, from server.py, beside the share), in one Claude call
with no tools, from what the episode was asked (its prompt: the log is the project's own and is
never shown publicly) and what it is (its narration as spoken, what Claude said it made). Nothing
here ever fails a film: a failure is logged (CANON) and noted as canon_error.

    python studio/canon.py --film <id>                       write (or rewrite) one entry
    python studio/canon.py --project <p-id> --missing        back-fill a project's log, oldest
                                                             first (--dry-run: which, no call)
    python studio/canon.py --project <p-id> --show           the log as an episode reads it

An entry costs about $0.02-0.05 on the key; on the login it is counted but not charged. Asking
again costs nothing until the episode changes (key).
"""

import os
import sys
import json
import asyncio
import hashlib
import argparse
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "scripts"))
import agent  # noqa: E402 -- imports _env first
import library  # noqa: E402
import share  # noqa: E402
import ytdraft  # noqa: E402
from film import Film  # noqa: E402

MODEL = ytdraft.MODEL
EFFORT = "low"  # a summary of something already made: nothing to think through
LIMITS = {  # characters of each field, and items of the lists
    "title": 80,
    "story": 240,
    "twist": 200,
    "fact": 200,
    "item": 120,
    "catchphrases": 4,
    "new": 6,
    "callbacks": 4,
}
TASKS = set()  # the premake tasks running: kept, so none is collected half-way

WRITER = (
    "You keep the episode log of an animated series: a short record of what each episode was, "
    "which every later episode reads so the series stays consistent, never repeats itself by "
    "accident, and can bring things back. Answer with one JSON object and nothing else."
)


def project_of(film):
    """(library, project id) of an episode, or (None, None) for any other film."""
    rec = film.record()
    pid = (rec.get("project") or {}).get("id")
    lib = library.lib_of(rec)
    return (lib, pid) if pid and lib and lib[1] else (None, None)


def material(film):
    """What the entry is written from."""
    rec = film.record()
    lines = [t for _, _, t in ytdraft._narration(film) if t.strip()]
    try:
        length = film.length
    except (OSError, ValueError, KeyError):
        length = rec.get("length") or 0
    return {
        "title": rec.get("title") or (rec.get("share") or {}).get("title") or "",
        "made": rec.get("created") or "",
        "length": length,
        "prompt": (rec.get("prompt") or "").strip()[:8000],
        "narration": "\n".join(lines)[:10000],
        "said": (rec.get("claude_said") or "").strip()[:4000],
        "cast": (rec.get("direction") or {}).get("cast") or [],
    }


def key_of(mat):
    return hashlib.sha256(json.dumps(mat, sort_keys=True).encode("utf-8")).hexdigest()[:16]


def ask_text(mat, before=()):
    """The ask, with the log of the episodes made before this one, so "new" means new to the
    series (written without it, every Duchess entry called her sad trombone new)."""
    so_far = library.canon_note(list(before)) or "This is the series' first episode."
    return (
        "One finished episode. Write its entry in the series' episode log.\n\n"
        + so_far
        + "\n\nThis episode.\n\n"
    ) + (
        "What it was asked for (the person's prompt):\n<<<\n%s\n>>>\n\n"
        "Its narration, as spoken:\n<<<\n%s\n>>>\n\n"
        "What its maker said it made:\n<<<\n%s\n>>>\n\n"
        "Characters and places drawn from the series' cast: %s\n\n"
        "The JSON, every field in the episode's own language, short and concrete (what happens, "
        "not how it was made):\n"
        '{"title": the episode\'s title, at most %d characters,\n'
        ' "story": what happens, one or two sentences, at most %d characters,\n'
        ' "catchphrases": the lines this episode made its own and repeats (word for word; not '
        "the series' fixed lines), at most %d,\n"
        ' "twist": how it ends, at most %d characters,\n'
        ' "fact": the true thing it teaches, or "" if none, at most %d characters,\n'
        ' "new": what it brought into the series for the first time -- a character, a place, a '
        "prop, a sound no earlier episode above had -- at most %d items,\n"
        ' "callbacks": jokes, objects or lines from it that a later episode could bring back, at '
        "most %d items}\n"
        "Each list item at most %d characters."
        % (
            mat["prompt"] or "(none)",
            mat["narration"] or "(no narration)",
            mat["said"] or "(nothing)",
            ", ".join(mat["cast"]) or "(none)",
            LIMITS["title"],
            LIMITS["story"],
            LIMITS["catchphrases"],
            LIMITS["twist"],
            LIMITS["fact"],
            LIMITS["new"],
            LIMITS["callbacks"],
            LIMITS["item"],
        )
    )


def _text(v, n):
    return " ".join(str(v or "").split())[:n]


def clean(d, mat, film_id):
    """Claude's answer held to the log's shape and sizes, with the episode's own facts."""

    def items(k):
        got = d.get(k) if isinstance(d.get(k), list) else []
        return [x for x in (_text(v, LIMITS["item"]) for v in got) if x][: LIMITS[k]]

    return {
        "film": film_id,
        "made": mat["made"],
        "length": mat["length"],
        "title": _text(d.get("title") or mat["title"], LIMITS["title"]),
        "story": _text(d.get("story"), LIMITS["story"]),
        "catchphrases": items("catchphrases"),
        "twist": _text(d.get("twist"), LIMITS["twist"]),
        "fact": _text(d.get("fact"), LIMITS["fact"]),
        "new": items("new"),
        "callbacks": items("callbacks"),
        "at": datetime.now().isoformat(timespec="seconds"),
        "key": key_of(mat),
    }


async def write(film, auth=None, model=MODEL, effort=EFFORT, force=False):
    """The episode's entry, written into its project's log: the entry, or None for a film that
    is not an episode. Costs nothing when the log already has it from the same material."""
    lib, _ = project_of(film)
    if not lib:
        return None
    mat = material(film)
    if not force:
        for e in library.canon_of(lib):
            if e.get("film") == film.id and e.get("key") == key_of(mat):
                return e
    auth = auth or share.auth_of(film)
    before = [
        e
        for e in library.canon_of(lib)
        if e.get("film") != film.id and (e.get("made") or "") < (mat["made"] or "~")
    ]
    d, cost = await ytdraft.ask_json(
        ask_text(mat, before), None, auth, film, model, effort, WRITER, "canon"
    )
    entry = clean(d, mat, film.id)
    await asyncio.to_thread(library.put_canon, lib, entry)
    rec = film.record()
    fields = {"canon_cost_usd": round((rec.get("canon_cost_usd") or 0) + cost, 4)}
    if auth == "api":
        fields["cost_usd"] = round((rec.get("cost_usd") or 0) + cost, 4)
    fields["canon_error"] = None
    film.update(**fields)
    await agent.save(film.id, fields)
    return entry


async def _premake(film):
    try:
        e = await write(film)
        if e:
            print('CANON %s: "%s"' % (film.id, e["title"]), flush=True)
    # SystemExit too: claude_env() exits when the key is missing
    except (Exception, SystemExit) as e:  # noqa: BLE001 -- a film is never failed by its log
        print("CANON %s failed: %s" % (film.id, e or type(e).__name__), flush=True)
        try:
            film.update(canon_error=str(e)[:300])
            await agent.save(film.id, {"canon_error": str(e)[:300]})
        except Exception as e2:  # noqa: BLE001
            print("CANON %s: could not note the failure: %s" % (film.id, e2), flush=True)


def enabled():
    """Not when Claude is stood in for: the studio's tests make films with a stub, and their
    entry would be a real, paid call."""
    rc = agent.run_claude
    return getattr(rc, "__module__", None) == "agent" and rc.__name__ == "run_claude"


def premake(film):
    """Write a finished episode's log entry in the background (server.py, when a film is done).
    Never raises, never touches the film's state; does nothing for a film that is not an episode,
    nor when Claude is stood in for (enabled)."""
    try:
        if not enabled() or not project_of(film)[0]:
            return None
        t = asyncio.get_running_loop().create_task(_premake(film))
    except RuntimeError:  # no loop (a script): canon.py --missing picks it up
        return None
    except Exception as e:  # noqa: BLE001 -- the film is done; its entry can be written later
        print("CANON %s not started: %s" % (film.id, e), flush=True)
        return None
    TASKS.add(t)
    t.add_done_callback(TASKS.discard)
    return t


def in_flight():
    """The episodes whose entry is being written here (a retiring server waits for them)."""
    return [t for t in TASKS if not t.done()]


# ------------------------------------------------------------------ the command line
def episodes(project):
    """A project's finished episodes, oldest first: [Film]."""
    out = []
    for f in Film.all():
        rec = f.record()
        if f.state == "done" and (rec.get("project") or {}).get("id") == project:
            if project_of(f)[0]:
                out.append(f)
    return sorted(out, key=lambda f: (f.record().get("created") or "", f.id))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--film", help="one episode's id")
    ap.add_argument("--project", help="a project id (p-...)")
    ap.add_argument("--missing", action="store_true", help="every episode without an entry")
    ap.add_argument("--show", action="store_true", help="print the log as an episode reads it")
    ap.add_argument("--dry-run", action="store_true", help="say which episodes; call nothing")
    ap.add_argument("--force", action="store_true", help="rewrite entries that are up to date")
    ap.add_argument("--auth", choices=("login", "api"), help="default: what the film was made on")
    a = ap.parse_args()

    if a.film:
        f = Film.open(a.film)
        if f is None:
            sys.exit("no film %s" % a.film)
        todo = [f]
    elif a.project:
        todo = episodes(a.project)
        if a.show:
            libs = {project_of(f)[0] for f in todo}
            for lib in libs:
                print(library.canon_note(library.canon_of(lib)) or "(the log is empty)")
            if not libs:
                print("(no finished episodes of %s here)" % a.project)
            return
        if a.missing and not a.force:
            have = set()
            for lib in {project_of(f)[0] for f in todo}:
                have |= {e["film"] for e in library.canon_of(lib)}
            todo = [f for f in todo if f.id not in have]
    else:
        sys.exit("--film or --project")

    print("%d episode(s)%s" % (len(todo), " (dry run: nothing called)" if a.dry_run else ""))
    for f in todo:
        title = f.record().get("title") or f.record().get("prompt", "")[:60]
        if a.dry_run:
            print("  %s  %s" % (f.id, title))
            continue
        e = asyncio.run(write(f, a.auth, force=a.force))
        print("  %s  %s" % (f.id, json.dumps(e, ensure_ascii=False) if e else "not an episode"))


if __name__ == "__main__":
    main()
