#!/usr/bin/env python
"""Build, refresh and doctor the project files under projects/<id>/.

The scan is mechanical: it reads the manifests and sidecars a project's folder
already contains and fills project.json's inputs / controls / deliverables
from them. It never touches prose (_comment, _why, intent, notes) or a burned
list it did not write -- those are the AI's memory, not the filesystem's.
Scan-seeded burned lines are marked "(scanned)" so a later session knows they
were inferred, not witnessed.

Modes, cheapest first:
    --id <id> --list     what a scan would change, without writing
    --id <id>            scan and write projects/<id>/project.json
    --init <id>          new project skeleton (folders + minimal files)
    --all [--check]      every project under projects/
    --check              doctor: missing files, stale manifests, unrecorded
                         uploads, two currents of one kind; exit 1 on findings

Invoke as:  python scripts/project-scan.py --id claude-demo --list
"""
import sys, os, json, glob, time, argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import
import _project

ROOT = _env.ROOT
norm = _project.norm

CONTENT_DIRS = ("sources", "audio", "transcripts", "outputs", "temp")


def utc(ts):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))


def jload(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def classify_manifest(doc):
    if not isinstance(doc, dict):
        return None
    if "screen" in doc and "camera" in doc:
        return "screencast"
    if "clips" in doc:
        return "clips"
    return None


def scan(pid):
    """A fresh mechanical view of one project folder."""
    pdir = os.path.join(_project.projects_dir(), pid)
    inputs, controls, deliverables = {}, {}, {}
    manifests = []                      # (path, kind, doc)

    for p in sorted(glob.glob(os.path.join(pdir, "*.json"))):
        base = os.path.basename(p)
        if base == "project.json":
            continue
        doc = jload(p)
        if base.endswith(".sync.json"):
            controls["sync"] = norm(p)
        elif base.endswith(".cuts.json"):
            controls["cuts"] = norm(p)
        elif base.endswith(".reframe.json"):
            controls["reframe"] = norm(p)
        elif classify_manifest(doc):
            manifests.append((p, classify_manifest(doc), doc))
    for p, _, _ in manifests:
        role = "manifest" if len(manifests) == 1 else \
            "manifest-" + os.path.splitext(os.path.basename(p))[0]
        controls[role] = norm(p)
    for name, role in (("chapters.txt", "chapters"),
                       ("description.txt", "description")):
        p = os.path.join(pdir, name)
        if os.path.exists(p):
            controls[role] = norm(p)

    outdirs = {os.path.join(pdir, "outputs")}
    for _, kind, m in manifests:
        for key, role in (("screen", "screen"), ("camera", "camera"),
                          ("source", "source"), ("words", "words")):
            if m.get(key):
                inputs.setdefault(role, norm(m[key]))
        for be in (m.get("bookends") or {}).get("open", []) + \
                  (m.get("bookends") or {}).get("close", []):
            if be.get("source"):
                inputs["bookend-" + be.get("id", "clip")] = norm(be["source"])
            for i, br in enumerate(be.get("broll") or []):
                if br.get("source"):
                    inputs["broll-%d" % (i + 1)] = norm(br["source"])
        if m.get("outdir"):
            outdirs.add(os.path.join(ROOT, m["outdir"]))
        if (m.get("captions") or {}).get("style"):
            controls.setdefault("caption-style", norm(m["captions"]["style"]))
        if m.get("label_preset") or m.get("name_labels"):
            controls.setdefault("label-style",
                                norm(m.get("label_preset",
                                           "config/labels/lower-third.json")))
        if (m.get("handle") or {}).get("preset"):
            controls.setdefault("handle-style", norm(m["handle"]["preset"]))
        img_specs = list(m.get("image_overlays") or [])
        for c in m.get("clips") or []:
            img_specs += list(c.get("image_overlays") or [])
        if m.get("overlay_preset") or img_specs:
            controls.setdefault("overlay-style",
                                norm(m.get("overlay_preset",
                                           "config/overlays/end-card.json")))
        for i, spec in enumerate(img_specs):
            # The page or spec an overlay is drawn from is a CONTROL, not an
            # input: editing it is how the card is changed, and the PNG
            # regenerates from it. A supplied image has no such source, so it
            # is an input like any other piece of footage.
            src = spec.get("card") or spec.get("html")
            if src:
                controls.setdefault("overlay-%d" % (i + 1), norm(src))
            elif spec.get("image"):
                inputs.setdefault("overlay-%d" % (i + 1), norm(spec["image"]))

    for od in sorted(outdirs):
        for p in sorted(glob.glob(os.path.join(od, "**", "*.*"),
                                  recursive=True)):
            ext = os.path.splitext(p)[1].lower()
            if ext == ".mp4":
                deliverables[norm(p)] = deliverable_for(p, pid, manifests)
            elif ext == ".wav":
                deliverables[norm(p)] = dub_deliverable_for(p)
    return inputs, controls, deliverables, manifests


def deliverable_for(p, pid, manifests):
    stem = os.path.splitext(p)[0]
    base = os.path.basename(stem)
    d = {"status": "current", "built_utc": utc(os.path.getmtime(p))}
    burned = []
    # Two manifests can both prefix-match one file (the vertical prefix
    # "x-v" starts with the horizontal prefix "x"), so the owner is the
    # longest matching prefix, with an outdir match trumping everything.
    owner = None
    best = -1
    for mp, kind, m in manifests:
        pre = m.get("id", "") if kind == "screencast" else \
            (m["prefix"] + "-" if m.get("prefix") else "")
        if not pre or not base.startswith(pre):
            continue
        if kind == "clips":
            # the remainder must be a clip id (a dub tag may follow it) --
            # the captioned MASTER also starts with the prefix and is not a clip
            rest = base[len(pre):]
            if not any(rest == c["id"] or rest.startswith(c["id"] + "-")
                       for c in m.get("clips", []) if c.get("id")):
                continue
        score = len(pre)
        od = m.get("outdir")
        if od and os.path.normcase(os.path.normpath(os.path.join(ROOT, od))) \
                == os.path.normcase(os.path.normpath(os.path.dirname(p))):
            score += 1000
        if score > best:
            best, owner = score, (mp, kind, m)
    if owner:
        mp, kind, m = owner
        d["kind"] = "screencast" if kind == "screencast" else "short"
        d["manifest"] = norm(mp)
        burned = screencast_burned(m) if kind == "screencast" else clips_burned(m)
    if owner is None and "-captioned" in base:
        d["kind"] = "captioned"
        burned = ["word-synced captions (scanned)"]
    side = stem + ".json"
    if os.path.exists(side):
        d.setdefault("sidecars", {})["clip"] = norm(side)
        sd = jload(side) or {}
        if sd.get("dub"):
            d["kind"] = "short-dubbed"
            d.setdefault("sidecars", {})["dub-words"] = norm(sd.get("dub_words", ""))
            burned = burned + ["dubbed audio: %s (scanned)"
                               % os.path.basename(sd["dub"])]
    yt = stem + ".youtube.json"
    if os.path.exists(yt):
        y = jload(yt) or {}
        d["published"] = {"url": y.get("url"), "privacy": y.get("privacy"),
                          "sidecar": norm(yt)}
    runman = os.path.join(ROOT, "outputs", "%s.manifest.json" % pid)
    if d.get("kind") == "captioned":
        for cand in (stem + ".manifest.json", runman):
            if os.path.exists(cand):
                d.setdefault("sidecars", {})["render-manifest"] = norm(cand)
                break
    if burned:
        d["burned"] = burned
    return d


def dub_deliverable_for(p):
    stem = os.path.splitext(p)[0]
    d = {"status": "current", "kind": "dub-audio",
         "built_utc": utc(os.path.getmtime(p))}
    sc = {}
    for suff, role in ((".plan.json", "plan"), (".translation.json", "translation"),
                       (".dub.json", "report"), (".words.json", "words")):
        if os.path.exists(stem + suff):
            sc[role] = norm(stem + suff)
    if sc:
        d["sidecars"] = sc
    return d


def screencast_burned(m):
    out = []
    cut = m.get("cut") or {}
    if cut.get("min_silence") is not None:
        out.append("pause cut per cuts.json (min_silence %s) (scanned)"
                   % cut["min_silence"])
    pip = m.get("pip") or {}
    if pip:
        out.append("camera PiP %s %spx (scanned)"
                   % (pip.get("corner", "?"), pip.get("size_px", "?")))
    for be in (m.get("bookends") or {}).get("open", []):
        out.append("opening bookend %s%s (scanned)"
                   % (be.get("id", "clip"),
                      " + b-roll" if be.get("broll") else ""))
    for lb in m.get("name_labels") or []:
        out.append("name label '%s' at %ss film time for %ss (scanned)"
                   % (lb.get("name"), lb.get("at"), lb.get("dur")))
    out += image_overlay_burned(m)
    return out


def image_overlay_burned(m, specs=None):
    """Scanned burn lines for image overlays.

    A scan cannot resolve a negative `at` -- that needs the film's runtime,
    which only the render knows -- so it says "before the end" rather than
    inventing a timecode. The render's own recorded line carries the real
    number and wins, because merge() only ever fills a gap.
    """
    out = []
    for spec in (m.get("image_overlays") or []) if specs is None else specs:
        at = float(spec.get("at", 0))
        when = ("%.1fs before the end" % -at) if at < 0 else ("%.1fs" % at)
        out.append("image overlay '%s' at %s%s (scanned)"
                   % (os.path.basename(spec.get("image") or spec.get("html")
                                       or spec.get("card") or "?"), when,
                      ", over a treated background"
                      if spec.get("background") is not None else ""))
    return out


def clips_burned(m):
    out = []
    if m.get("vertical"):
        out.append("9:16 crop per reframe sidecar (scanned)")
    if m.get("captions"):
        out.append("word-synced captions, style %s (scanned)"
                   % m["captions"].get("style", "?"))
    if (m.get("handle") or {}).get("text"):
        out.append("handle badge %s (scanned)" % m["handle"]["text"])
    out += image_overlay_burned(m)
    return out


def merge(old, pid, inputs, controls, deliverables):
    """Scan results layered under what the file already says.

    Existing values win everywhere: a scan may only add facts and refresh
    build times, never overwrite an editorial decision (status, burned, prose).
    """
    doc = old or {"v": 1, "id": pid}
    doc.setdefault("v", 1)
    doc.setdefault("id", pid)
    for section, fresh in (("inputs", inputs), ("controls", controls)):
        cur = doc.setdefault(section, {})
        for k, v in fresh.items():
            cur.setdefault(k, v)
    cur = doc.setdefault("deliverables", {})
    for key, fresh in deliverables.items():
        if key not in cur:
            cur[key] = fresh
            continue
        d = cur[key]
        d.setdefault("built_utc", fresh.get("built_utc"))
        for k, v in fresh.items():
            if k in ("status", "burned") or k in _project._PROSE_KEYS:
                d.setdefault(k, v)
            elif k == "sidecars":
                d.setdefault("sidecars", {})
                for rk, rv in v.items():
                    d["sidecars"].setdefault(rk, rv)
            else:
                d.setdefault(k, v)
    doc["updated_utc"] = utc(time.time())
    return doc


def check(pid, doc):
    """Findings that mean the file and the filesystem disagree."""
    finds = []
    currents = {}
    for key, d in (doc.get("deliverables") or {}).items():
        p = os.path.join(ROOT, key)
        if d.get("status") != "deleted" and not os.path.exists(p):
            finds.append("MISSING %s -- file is gone; set status: deleted" % key)
        if "\\" in key or os.path.isabs(key):
            finds.append("BADPATH %s -- store repo-relative, forward slashes" % key)
        if d.get("status") == "current":
            currents.setdefault(d.get("kind"), []).append(key)
            man = d.get("manifest")
            if man and d.get("built_utc"):
                # checked_utc acknowledges a manifest edit as non-material
                # (e.g. a path-only rewrite proven by a --list plan diff)
                ok = max(d["built_utc"], d.get("checked_utc", ""))
                mp = os.path.join(ROOT, man)
                if os.path.exists(mp) and utc(os.path.getmtime(mp)) > ok:
                    finds.append("STALE %s -- %s edited after this render"
                                 % (key, man))
        yt = os.path.join(ROOT, os.path.splitext(key)[0] + ".youtube.json")
        if os.path.exists(yt) and not d.get("published"):
            finds.append("UNRECORDED UPLOAD %s -- %s exists but no published "
                         "block" % (key, norm(yt)))
    for kind, keys in currents.items():
        if kind in ("screencast", "captioned") and len(keys) > 1:
            finds.append("AMBIGUOUS %d current %s renders (%s) -- mark the "
                         "superseded ones" % (len(keys), kind, ", ".join(keys)))
    return finds


def init(pid):
    pdir = os.path.join(_project.projects_dir(), pid)
    for d in CONTENT_DIRS:
        os.makedirs(os.path.join(pdir, d), exist_ok=True)
    if not os.path.exists(_project.path_for(pid)):
        _project._atomic_write(_project.path_for(pid),
                               {"v": 1, "id": pid, "intent": "",
                                "pipelines": [], "inputs": {}, "controls": {},
                                "deliverables": {}, "notes": [],
                                "updated_utc": utc(time.time())})
    _project._journal_append(pid, "- %s project created"
                             % time.strftime("%H:%M", time.gmtime()),
                             time.gmtime())
    print("projects/%s/ ready" % pid)


def all_ids():
    if not os.path.isdir(_project.projects_dir()):
        return []
    return sorted(d for d in os.listdir(_project.projects_dir())
                  if os.path.isdir(os.path.join(_project.projects_dir(), d)))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--id", help="project id (folder name under projects/)")
    ap.add_argument("--init", metavar="ID", help="create a new project skeleton")
    ap.add_argument("--all", action="store_true", help="every project")
    ap.add_argument("--list", action="store_true",
                    help="print what a scan would change; write nothing")
    ap.add_argument("--check", action="store_true",
                    help="doctor the file(s) against the filesystem")
    _env.add_workspace_arg(ap)
    args = ap.parse_args()
    _env.set_workspace(args.workspace)

    if args.init:
        init(args.init)
        return
    if args.all:
        ids = all_ids()
        if not ids:
            print("no projects yet -- start one with --init <id>")
            return
    elif args.id:
        ids = [args.id]
    else:
        ap.error("need --id, --all or --init")

    bad = 0
    for pid in ids:
        if not os.path.isdir(os.path.join(_project.projects_dir(), pid)):
            sys.exit("no such project: projects/%s" % pid)
        old = _project.load(pid)
        if args.check:
            doc = old
            if doc is None:
                print("%s: no project.json -- run --id %s first" % (pid, pid))
                bad += 1
                continue
            finds = check(pid, doc)
            for f in finds:
                print("%s: %s" % (pid, f))
            bad += len(finds)
            if not finds:
                print("%s: ok" % pid)
            continue
        inputs, controls, deliverables, _ = scan(pid)
        doc = merge(json.loads(json.dumps(old)) if old else None,
                    pid, inputs, controls, deliverables)
        if args.list:
            before = json.dumps(old, ensure_ascii=False, indent=2,
                                sort_keys=True) if old else "(none)"
            after = json.dumps(doc, ensure_ascii=False, indent=2,
                               sort_keys=True)
            if before == after:
                print("%s: no changes" % pid)
            else:
                for sec in ("inputs", "controls", "deliverables"):
                    o = (old or {}).get(sec, {})
                    n = doc.get(sec, {})
                    for k in sorted(set(n) - set(o)):
                        print("%s: + %s.%s = %s" % (pid, sec, k,
                                                    json.dumps(n[k], ensure_ascii=False)[:120]))
                    for k in sorted(set(o) & set(n)):
                        if o[k] != n[k]:
                            print("%s: ~ %s.%s" % (pid, sec, k))
            continue
        _project._atomic_write(_project.path_for(pid), doc)
        print("projects/%s/project.json: %d inputs, %d controls, "
              "%d deliverables" % (pid, len(doc.get("inputs", {})),
                                   len(doc.get("controls", {})),
                                   len(doc.get("deliverables", {}))))
    if bad:
        sys.exit(1)


if __name__ == "__main__":
    main()
