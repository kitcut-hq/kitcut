#!/usr/bin/env python
"""Bring a film made outside the studio into kitcut.ai: an account's film, an episode of one of
its projects, with a film page, a web copy, a card, Download and Publish to YouTube.

A sketch film rendered by hand with scripts/sketch-render.py (a projects/<id>/ folder: sketch.json,
film.js, its pictures, outputs/<slug>.mp4 and friends) is not a studio film: no record says whose
it is, nothing is online, and the studio's pages cannot find it. This makes it one, the way
agent.make_film leaves a finished film:

  1. a new id and folder, STUDIO_HOME/projects/studio-<stamp>-<6>/: the manifest (slug "film"),
     the film's code, score, cues and pictures, the engine it ran on (engine/, so a later stills or
     share run draws it as it was), outputs/film.mp4 (the master), film_poster.png, film.html and
     film.vtt when there are captions, and a done studio.json (source "import");
  2. its record in kitcut.studio_runs -- owner, project, state done -- written BEFORE anything goes
     online, since media's save is an upsert and would otherwise make a record with no owner;
  3. media.publish: the web copy, the card and the files in blob storage; their URLs in both
     records, as a made film's are.

Then the folder has to live where the studio serves from: --vm copies it into the VM's home
(tar over studio/deploy/vm.sh ssh; the VPN must be up), where the film page, Download and Publish
read it. Run on the laptop with STUDIO_HOME pointing at a scratch home (the default) and the
studio's .env (STUDIO_ENV_FILE) for MONGODB_URI and the media SAS.

No credits are spent, so the film is not in the account's credit table; it is in its project, on
its film page, in its creator page when listed, and in the sitemap when listed. --unlisted keeps
it link-only. No Claude call is made.

Invoke as:
    python studio/import_film.py --folder projects/<id> --as <email> --project p-xxxxxxxxxx --plan
    python studio/import_film.py --folder projects/<id> --as <email> --project p-xxxxxxxxxx \\
        --title "..." --prompt "..." --unlisted --vm kitcut-studio-1
    python studio/import_film.py --film studio-<id> --vm kitcut-studio-1   (copy a made import)
"""

import os
import re
import sys
import json
import shutil
import asyncio
import tarfile
import argparse
import secrets
import subprocess
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.dirname(HERE)
os.environ.setdefault("STUDIO_HOME", os.path.join(KIT, "temp", "import-home"))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(KIT, "scripts"))
import agent  # noqa: E402 -- loads the studio's .env (the SAS, MONGODB_URI) and the record store
import film as films  # noqa: E402
import media  # noqa: E402
import store  # noqa: E402

VM_HOME = "/srv/kitcut/studio"  # the studio's home on the VM (studio/deploy/ops.sh HOME_DIR)
# what of the source folder the film keeps: its code and what its code reads, never its scratch
# content.json: a template film's words and people; web/, inputs/, template/: the pictures its
# manifest names (brought in, attached, the template's own) -- a later redraw needs them
KEEP = (
    "film.js",
    "score.json",
    "sfx.json",
    "score.py",
    "sfx.py",
    "description.txt",
    "content.json",
)
KEEP_DIRS = ("images", "assets", "scenes", "cast", "web", "inputs", "template")


def say(*a):
    print(*a, flush=True)


def account(email):
    """(client, user id) of the kitcut.ai account with this email; exits when there is none."""
    db = agent.STORE.col().database
    u = db["users"].find_one({"email": email.strip().lower()})
    if not u:
        sys.exit("no kitcut.ai account %r" % email)
    return "u:%s" % u["_id"], str(u["_id"])


def project_of(pid, user_id):
    """The project, when it is this account's and not archived; exits otherwise."""
    db = agent.STORE.col().database
    p = db["projects"].find_one({"_id": pid})
    if not p or str(p.get("user_id")) != user_id:
        sys.exit("project %s is not this account's" % pid)
    if p.get("archived_at"):
        sys.exit("project %s is archived" % pid)
    return p


def new_id():
    """A studio film id no film has: the site finds a film by its last six letters."""
    col = agent.STORE.col()
    for _ in range(50):
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        tail = "".join(secrets.choice(films._B32) for _ in range(6))
        fid = "studio-%s-%s" % (stamp, tail)
        if not col.find_one({"_id": {"$regex": "-%s$" % tail}}, {"_id": 1}):
            return fid
    sys.exit("could not find a free film id")


def source(folder):
    """The source film: its manifest, its master and the files the render wrote beside it."""
    man = os.path.join(folder, "sketch.json")
    if not os.path.isfile(man):
        sys.exit("%s has no sketch.json" % folder)
    with open(man, encoding="utf-8") as f:
        m = json.load(f)
    slug = re.sub(r"[^a-z0-9]+", "-", (m.get("slug") or os.path.basename(folder)).lower()).strip(
        "-"
    )
    out = os.path.join(folder, "outputs")
    files = {
        "film.mp4": os.path.join(out, slug + ".mp4"),
        "film_poster.png": os.path.join(out, slug + "_poster.png"),
        "film.html": os.path.join(out, slug + ".html"),
        "film.vtt": os.path.join(out, slug + ".vtt"),
        "film.srt": os.path.join(out, slug + ".srt"),
    }
    for need in ("film.mp4", "film_poster.png"):
        if not os.path.isfile(files[need]):
            sys.exit("no %s -- render the film first (scripts/sketch-render.py)" % files[need])
    return m, {k: v for k, v in files.items() if os.path.isfile(v)}


def build(folder, fid, m, files, rec):
    """The studio folder for the film, its studio.json written last and whole."""
    film = films.Film(os.path.join(films.HOME, "projects", fid))
    os.makedirs(film.path("outputs"))
    os.makedirs(film.path("temp", "tmp"))
    for name in KEEP:
        if os.path.isfile(os.path.join(folder, name)):
            shutil.copyfile(os.path.join(folder, name), film.path(name))
    for d in KEEP_DIRS:
        if os.path.isdir(os.path.join(folder, d)):
            shutil.copytree(os.path.join(folder, d), film.path(d))
    # the engine the film was drawn with, beside it (a studio film's own copy): the release on the
    # VM may not have a module it uses yet
    engine = m.get("engine")
    src = os.path.join(folder, engine) if engine else os.path.join(KIT, "sketch")
    os.makedirs(film.path("engine"))
    for js in ["engine.js", "props.js"] + [n + ".js" for n in m.get("modules") or []]:
        shutil.copyfile(os.path.join(src, js), film.path("engine", js))
    for name, p in files.items():
        shutil.copyfile(p, film.path("outputs", name))
    m = dict(m, slug="film", engine="engine")
    m["title"] = rec["title"]
    films._write_json(film.manifest, m)
    films._write_json(film.path("studio.json"), rec)
    return film


def to_vm(film, vm):
    """Copy the film's folder into the VM's studio home (tar over vm.sh ssh), then check it."""
    dest = "%s/projects/%s" % (VM_HOME, film.id)
    vm_sh = os.path.join(HERE, "deploy", "vm.sh")
    cmd = ["bash", vm_sh, "ssh", vm, "mkdir -p %s && tar -xf - -C %s && echo copied" % (dest, dest)]
    say("  copying %s to %s:%s ..." % (film.id, vm, dest))
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    with tarfile.open(fileobj=p.stdin, mode="w|") as tar:
        for name in sorted(os.listdir(film.dir)):
            if name != "temp":
                tar.add(film.path(name), arcname=name)
        tar.add(film.path("temp"), arcname="temp", recursive=False)
    p.stdin.close()
    out = p.stdout.read().decode(errors="replace")
    if p.wait() != 0 or "copied" not in out:
        sys.exit("copying to the VM failed (%s): is the VPN up?" % out.strip()[-200:])
    check = subprocess.run(
        [
            "bash",
            vm_sh,
            "ssh",
            vm,
            "python3 -c \"import json;print(json.load(open('%s/studio.json'))['state'])\"" % dest,
        ],
        capture_output=True,
        text=True,
    )
    if check.stdout.strip() != "done":
        sys.exit("the copy on the VM does not read as a done film: %r" % check.stdout.strip())
    say("  on the VM: %s (state done)" % dest)


async def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--folder", help="the sketch film's folder (its sketch.json and outputs/)")
    ap.add_argument("--as", dest="email", help="the kitcut.ai account it becomes a film of")
    ap.add_argument("--project", help="the account's project it is an episode of (p-...)")
    ap.add_argument("--title", help="its title (default: the manifest's)")
    ap.add_argument(
        "--prompt",
        help="what it is, as the page shows a film's idea (default: the manifest's description)",
    )
    ap.add_argument(
        "--look", default="drawn", choices=films.LOOKS, help="the look it is filed under"
    )
    ap.add_argument(
        "--unlisted", action="store_true", help="link-only: out of the gallery and the sitemap"
    )
    ap.add_argument(
        "--template",
        help="the template it was made from, t-<slug>:<version> (a bake-off's remake): counted as "
        "one of its films, and its page says so",
    )
    ap.add_argument("--vm", help="also copy it into this VM's studio home (e.g. kitcut-studio-1)")
    ap.add_argument("--film", help="with --vm: copy a film this made earlier (its id) instead")
    ap.add_argument("--plan", action="store_true", help="say what would be made; change nothing")
    args = ap.parse_args()

    if args.film:
        f = films.Film(os.path.join(films.HOME, "projects", args.film))
        if f.record().get("source") != "import":
            sys.exit("%s is not an import in %s" % (args.film, films.HOME))
        if not args.vm:
            sys.exit("--film needs --vm")
        return to_vm(f, args.vm)
    if not (args.folder and args.email and args.project):
        sys.exit("--folder, --as and --project")
    folder = os.path.abspath(args.folder)
    m, files = source(folder)
    client, uid = account(args.email)
    proj = project_of(args.project, uid)
    title = args.title or m.get("title") or os.path.basename(folder)
    prompt = args.prompt or m.get("description") or title
    length = int(round(float(m.get("duration", 0))))
    say(
        "film:     %s  (%d s, %s fps, %s)"
        % (title, length, m.get("fps", 60), "x".join(map(str, m.get("frame") or [1920, 1080])))
    )
    say("from:     %s" % folder)
    say(
        "files:    %s"
        % ", ".join("%s (%.1f MB)" % (k, os.path.getsize(v) / 1e6) for k, v in files.items())
    )
    say("owner:    %s  (%s)" % (args.email, client))
    say("project:  %s  %s" % (proj["_id"], proj.get("name")))
    say("listed:   %s" % ("no, link-only" if args.unlisted else "yes"))
    tpl = None
    if args.template:
        tid, _, v = args.template.partition(":")
        t = (
            json.load(open(os.path.join(folder, "template", "template.json"), encoding="utf-8"))
            if os.path.isfile(os.path.join(folder, "template", "template.json"))
            else {}
        )
        if t.get("id") and t["id"] != tid:
            sys.exit("the film was made from %s, not %s" % (t["id"], tid))
        tpl = {
            "id": tid,
            "version": int(v or t.get("version") or 0),
            "title": t.get("title") or tid,
        }
        if not tpl["version"]:
            sys.exit("--template t-<slug>:<version>")
        say("template: %s v%d (%s)" % (tpl["id"], tpl["version"], tpl["title"]))
    frame = next(
        (k for k, wh in films.FRAMES.items() if list(wh) == list(m.get("frame") or [])), None
    )
    say(
        "online:   %s"
        % (
            "blob storage (%s)" % media.base()
            if media.enabled()
            else "OFF -- no STUDIO_MEDIA_BASE/SAS"
        )
    )
    say("home:     %s" % films.HOME)
    if args.plan:
        say("\n--plan: nothing made")
        return
    if not media.enabled():
        sys.exit("media is off: run with the studio's .env (STUDIO_ENV_FILE)")

    fid = new_id()
    now = datetime.now().isoformat(timespec="seconds")
    project = {
        "id": proj["_id"],
        "name": proj.get("name"),
        "brief": proj.get("brief") or "",
        "from_account_cast": bool(proj.get("from_account_cast")),
    }
    rec = {
        "id": fid,
        "prompt": prompt,
        "title": title,
        "look": args.look,
        "caps": list(films.RECIPES[args.look]),
        "length": length,
        "client": client,
        "source": "import",
        "priority": 0,
        "auth": "api",
        "branding": False,
        "fps": int(m.get("fps", 60)),
        "mode": "single",
        "attachments": [],
        "project": project,
        "listed": not args.unlisted,
        "release": films.RELEASE,
        "state": "done",
        "ok": True,
        "video": "film.mp4",
        "poster": "film_poster.png",
        "created": now,
        "finished": now,
        "imported": {"from": os.path.basename(folder), "at": now},
        **({"template": tpl, "frame": frame or "16:9", "narration": False} if tpl else {}),
    }
    film = build(folder, fid, m, files, rec)
    say("\nmade:     %s" % film.dir)
    # the record first, whole and owned: media's own save below is an upsert
    first = {
        "kind": "film",
        "source": "import",
        "client": client,
        "host": store.HOST,
        "prompt": prompt,
        "title": title,
        "job": fid,
        "length": length,
        "look": args.look,
        "release": films.RELEASE,
        "priority": 0,
        "auth": "api",
        "branding": False,
        "listed": not args.unlisted,
        "attachments": [],
        "project_id": proj["_id"],
        "state": "done",
        "ok": True,
        "cost_usd": 0.0,
        "finished_at": store.now(),
        "imported": {"from": os.path.basename(folder)},
        **({"template": tpl, "frame": frame or "16:9"} if tpl else {}),
    }
    if not await agent.save(fid, first, final=True):
        sys.exit(
            "the record did not reach kitcut.studio_runs (it is in the outbox); not going online"
        )
    say("recorded: kitcut.studio_runs %s" % fid)
    urls = await media.publish(film)
    if not urls:
        sys.exit("the files did not go online; the record is there -- run media.py --film %s" % fid)
    film.update(media=urls)
    await agent.save(fid, {"media": urls}, final=True)
    say("online:   %s" % ", ".join(sorted(urls)))
    if args.vm:
        to_vm(film, args.vm)
    say("\nfilm page:    https://kitcut.ai/film/%s" % fid)
    say("project page: https://kitcut.ai/studio/%s" % proj["_id"])


if __name__ == "__main__":
    asyncio.run(main())
