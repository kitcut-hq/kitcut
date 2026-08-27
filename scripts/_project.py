"""Per-video project state: the memory that outlives the session.

`projects/<id>/` holds everything about one video: `project.json` (current
state -- what renders exist, what is burned onto each, which manifest controls
it, where it was published), `journal.md` (append-only history addressed to
the NEXT session working on this video), the pipeline manifests, and the
gitignored content dirs (sources/ audio/ transcripts/ outputs/ temp/).

Why a module and not a convention: config/video-specs.template.json was a
hand-authored per-video document once. No script ever read or wrote it, so it
rotted. Metadata stays true only if the scripts that render also record --
which is what record() is for. The finishing scripts call it right after
moving an output into place; everything a script cannot know (intent, why a
render is superseded) is prose the AI adds and this module must never clobber.

record() is deliberately non-fatal, unlike everything else in this repo: it
runs after a render that may have cost 20 minutes of GPU time, and exiting
non-zero there would report failure for a success. It prints loudly instead so
the state can be recorded by hand.
"""
import os
import sys
import json
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402,F401 -- re-execs into .venv; before any 3rd-party import

ROOT = _env.ROOT
PROJECTS = os.path.join(ROOT, "projects")

_PROSE_KEYS = ("_comment", "_why", "intent", "notes")


def norm(path):
    """A path as project files store it: repo-relative, forward slashes.

    Existing shorts sidecars contain mixed separators ("outputs/dub\\x.wav"),
    so comparisons must normalize -- but nothing new is ever written that way.
    """
    p = os.path.abspath(path) if not os.path.isabs(path) else path
    p = os.path.normpath(p)
    root = os.path.normpath(ROOT)
    if os.path.normcase(p).startswith(os.path.normcase(root + os.sep)):
        p = p[len(root) + 1:]
    return p.replace("\\", "/")


def find_project_dir(path):
    """Walk up from any file to its projects/<id>/ root, or None."""
    p = os.path.abspath(path)
    stop = os.path.normcase(os.path.normpath(PROJECTS))
    while True:
        parent = os.path.dirname(p)
        if os.path.normcase(os.path.normpath(parent)) == stop:
            return p
        if parent == p:
            return None
        p = parent


def path_for(pid):
    return os.path.join(PROJECTS, pid, "project.json")


def journal_for(pid):
    return os.path.join(PROJECTS, pid, "journal.md")


def load(pid):
    p = path_for(pid)
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def project_id(manifest, manifest_path):
    """The project a manifest belongs to.

    Inside projects/ the folder IS the id; the fallbacks keep legacy manifests
    under config/ working (their "project"/"id" key, else the filename stem).
    """
    d = find_project_dir(manifest_path)
    if d:
        return os.path.basename(d)
    return (manifest.get("project") or manifest.get("id")
            or os.path.splitext(os.path.basename(manifest_path))[0])


def find_by_output(path):
    """(pid, doc) for the project that owns an output, or (None, None).

    Walk-up answers it for anything already under projects/; the scan catches
    legacy-layout outputs that a project file claims in its deliverables.
    """
    d = find_project_dir(path)
    if d:
        pid = os.path.basename(d)
        return pid, load(pid)
    want = norm(path).casefold()
    if os.path.isdir(PROJECTS):
        for pid in sorted(os.listdir(PROJECTS)):
            doc = load(pid)
            for key in (doc or {}).get("deliverables", {}):
                if norm(os.path.join(ROOT, key)).casefold() == want:
                    return pid, doc
    return None, None


def _atomic_write(path, doc):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def _journal_append(pid, line, when):
    """Append one event line, opening today's `## date` section as needed."""
    p = journal_for(pid)
    day = time.strftime("%Y-%m-%d", when)
    head = ""
    if not os.path.exists(p):
        head = ("# %s -- edit journal\n"
                "AI notes for future sessions. Scripts append the `- HH:MM` "
                "event lines;\nafter each editing session, append a short "
                "prose note: what was asked,\nwhich knob changed, why, and "
                "anything the next session should not rediscover.\n" % pid)
        need_day = True
    else:
        with open(p, encoding="utf-8") as f:
            need_day = ("## " + day) not in f.read()
    with open(p, "a", encoding="utf-8") as f:
        if head:
            f.write(head)
        if need_day:
            f.write("\n## %s\n" % day)
        f.write(line + "\n")


def record(pid, action, out=None, script=None, argv=None, kind=None,
           manifest=None, sidecars=None, burned=None, published=None,
           note=None):
    """Record one pipeline event: a journal line, and (if `out` is given) a
    deliverable upsert in project.json with status "current".

    Merging, not replacing: fields the caller does not pass survive, and the
    prose keys survive unconditionally -- they are the AI's notes, and a
    re-render does not invalidate why something was done.
    """
    try:
        when = time.gmtime()
        os.makedirs(os.path.join(PROJECTS, pid), exist_ok=True)
        doc = load(pid) or {"v": 1, "id": pid, "inputs": {}, "controls": {},
                            "deliverables": {}}
        doc["updated_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", when)
        if out is not None:
            key = norm(out)
            d = doc.setdefault("deliverables", {}).setdefault(key, {})
            d["status"] = "current"
            d["built_utc"] = doc["updated_utc"]
            for field, val in (("kind", kind), ("script", script and norm(script)),
                               ("manifest", manifest and norm(manifest)),
                               ("burned", burned), ("published", published)):
                if val is not None:
                    d[field] = val
            if sidecars:
                d.setdefault("sidecars", {}).update(
                    {k: norm(v) for k, v in sidecars.items() if v})
        _atomic_write(path_for(pid), doc)

        bits = [time.strftime("- %H:%M", when), action]
        if script:
            bits.append(norm(script))
        if out is not None:
            bits.append("-> " + norm(out))
        if argv:
            bits.append("(" + " ".join(argv)[:200] + ")")
        if published and published.get("url"):
            bits.append(published["url"])
        if note:
            bits.append("-- " + note)
        _journal_append(pid, " ".join(bits), when)
    except Exception as e:  # noqa: BLE001 -- see module docstring
        print("!! PROJECT FILE NOT UPDATED (%s: %s) -- record this %s in "
              "projects/%s/ by hand" % (type(e).__name__, e, action, pid))
