#!/usr/bin/env python
"""Films' code under version control: one git repository per project, kept beside the films.

    python studio/filmgit.py --plan [--film <id>]   what a sync would commit and forget; writes nothing
    python studio/filmgit.py --sync [--film <id>]   commit every finished film whose code is not in
                                                    its repository as it stands, and forget the
                                                    films that are gone (hourly, kitcut-filmgit.timer)
    python studio/filmgit.py --log <id>             a film's history: its versions, as commits
    python studio/filmgit.py --push                 push the published repositories to GitHub
    python studio/filmgit.py --unpublished          name and public key of each one not there yet
    python studio/filmgit.py --set-remote NAME...   these are there now: point at them
    (on the VM: ops.sh filmgit [--plan | --log <id> | publish])

Why: a film is code -- film.js, its cast, its score -- and the studio kept each film's code as
loose files, the last three versions beside it (rounds.KEEP). A hand fix sent back over a newer
version once erased it (KI-061), and what a film was two versions ago is gone for good after the
third. Measured on 2026-10-12: the code of all 490 films is 110 MB, 80 MB of it the same 32 engine
files copied 1,440 times. Pictures, narration takes, uploads and masters are 136 GB and are NOT
here: they are in the mirror (backup.py), and each film's folder in the repository lists them.

Where: STUDIO_HOME/git/<name>.git, bare. <name> is the film's project (p-...); for a film made
outside a project, its workspace (w-<the library's own name for the client>); w-other for films
with no signed-in maker. In a repository, on one branch (main):

    films/<film id>/film.js, cast/, scenes/, engine/, *.json ...   the film's code (CODE below)
    films/<film id>/film.json     what it is: title, prompt, look, length, version
    films/<film id>/assets.json   every file of the film that is not here: path, bytes
    library/...                   the project's cast, index and episode log

A version is a commit, tagged <film id>/v<n>. Earlier versions still on disk (versions/v<n>/) go
in first, in order, so a film's history starts as far back as its files do.

How it is kept: by looking, not by being told. A sync compares each finished film with what its
repository holds and commits the difference; nothing in the making of a film calls this, so
nothing here can fail a film, and running it over everything is also the back-fill. The price is
that two versions made within one hour of each other are one commit.

A film that was deleted (delete_film.py) is forgotten: a sync that finds films/<id> in a
repository and no such film on the machine rewrites that repository without it, tags and all.
That is refused on a machine whose home is not whole (backup.there), on a rehearsal, and past
MAX_FORGET films in one run -- a disk that did not mount must not read as "every film was deleted".

Their copy on GitHub: private repositories in an organisation of their own (kitcut-films, never
the one the product's code is in). Each repository is pushed with a key of its own, registered
there as a deploy key that may write that one repository and nothing else -- so the machine,
which runs people's prompts, holds no key to the organisation. Making a repository there and
registering its key is done from the laptop (`ops.sh filmgit publish`, with a GitHub sign-in);
from then on every sync pushes it (--mirror: what was forgotten here goes from there too), and
GitHub being down is tried again at the next sync. Needs git and ssh-keygen on PATH.

As a film finishes, the server runs `--sync --film <id> --and-push` for it (on_finish, where
STUDIO_FILMGIT_ON_FINISH=1), so its repository and GitHub are minutes behind it, not an hour. An
episode that started from an earlier one's code (episode.py) says which in film.json
(carried_from) and in its commit ("Started-from: <film>/v<n>"): versions are named by tag, never
by commit, because forgetting a film rewrites a repository's history.
"""

import os
import re
import sys
import json
import asyncio
import hashlib
import argparse
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backup  # noqa: E402 -- the stdlib only: whether the home is whole, the studio's .env
import clients  # noqa: E402
import film as films  # noqa: E402
import locks  # noqa: E402

ROOT = os.path.join(films.HOME, "git")
BRANCH = "refs/heads/main"
WHO = {"GIT_AUTHOR_NAME": "KitCut Studio", "GIT_AUTHOR_EMAIL": "studio@kitcut.ai"}
WHO.update(GIT_COMMITTER_NAME=WHO["GIT_AUTHOR_NAME"], GIT_COMMITTER_EMAIL=WHO["GIT_AUTHOR_EMAIL"])
# a film's code: these files, and text in these folders. Nothing else is committed.
CODE_FILES = (
    "film.js sketch.json vo.json score.json sfx.json sounds.json paint.json content.json "
    "place.json route.json scenes.json score.py sfx.py"
).split()
CODE_DIRS = ("cast", "scenes", "engine", "template")
TEXT = (".js", ".json", ".md", ".txt", ".html", ".css", ".py", ".svg")
MAX_BYTES = 1024 * 1024  # one file; a bigger one is listed in assets.json like a picture
# not listed as an asset either: scratch (prune.py), earlier versions (their own commits), what
# the film was given to read, and the studio's own records of it
NOT_ASSETS = (
    "temp",
    "versions",
    "library",
    "studio.json",
    "events.jsonl",
    "project.json",
    "journal.md",
)
DONE = "done"
MAX_FORGET = 20
REMOTE = "github"  # a repository's copy on GitHub: private, in an organisation of its own
PUSH_S = 600  # one repository's push; one that hangs past it is tried again at the next sync
ORG = os.environ.get("STUDIO_FILMS_ORG") or "kitcut-films"
NAME = re.compile(r"^(p-[a-z2-7]{10}|w-[0-9a-f]{20}|w-other)$")  # what repo_name gives
FILM_PATH = re.compile(r"^films/(studio-\d{8}-\d{6}(?:-[a-z2-7]{6})?)$")


def git(repo, *args, stdin=None, env=None, check=True):
    e = dict(os.environ, GIT_DIR=repo, **WHO, **(env or {}))
    # bytes in and out: in text mode Windows turns every \n of stdin into \r\n, and git then
    # files a path that ends in \r (the laptop runs this test too)
    r = subprocess.run(
        ["git", *args],
        input=None if stdin is None else stdin.encode("utf-8"),
        env=e,
        capture_output=True,
        check=False,
    )
    out, err = (x.decode("utf-8", "replace") for x in (r.stdout, r.stderr))
    if check and r.returncode != 0:
        raise RuntimeError("git %s: %s" % (" ".join(args[:2]), (err or out).strip()[-300:]))
    return out.strip()


def repo_name(rec):
    """Which repository a film's code goes to: its project's, else its workspace's."""
    pid = (rec.get("project") or {}).get("id")
    if isinstance(pid, str) and films.PROJECT_ID.match(pid):
        return pid
    client = rec.get("client")
    if isinstance(client, str) and clients.signed_in(client):
        return "w-" + hashlib.sha256(clients.canon(client).encode()).hexdigest()[:20]
    return "w-other"


def repo_of(name, make=False):
    path = os.path.join(ROOT, name + ".git")
    if make and not os.path.isdir(path):
        os.makedirs(ROOT, exist_ok=True)
        subprocess.run(
            ["git", "init", "-q", "--bare", "--initial-branch=main", path],
            check=True,
            capture_output=True,
        )
    return path


def _text(path):
    try:
        return os.path.getsize(path) <= MAX_BYTES and path.lower().endswith(TEXT)
    except OSError:
        return False


def code_of(d):
    """{path in the film: path on disk} of the code in a film's folder (or a version's)."""
    out = {}
    for name in CODE_FILES:
        p = os.path.join(d, name)
        if os.path.isfile(p) and _text(p):
            out[name] = p
    for sub in CODE_DIRS:
        for root, dirs, names in os.walk(os.path.join(d, sub)):
            dirs.sort()
            for n in sorted(names):
                p = os.path.join(root, n)
                if _text(p):
                    out[os.path.relpath(p, d).replace(os.sep, "/")] = p
    return out


def assets_of(d, code):
    """[{"path", "bytes"}] of everything in a film's folder that is not committed: what a
    checkout fetches from the mirror to render it."""
    out = []
    for root, dirs, names in os.walk(d):
        rel = os.path.relpath(root, d).replace(os.sep, "/")
        if rel == ".":
            dirs[:] = sorted(x for x in dirs if x not in NOT_ASSETS)
            names = [n for n in names if n not in NOT_ASSETS]
        else:
            dirs.sort()
        for n in sorted(names):
            p = n if rel == "." else "%s/%s" % (rel, n)
            if p in code or n.endswith(".lock"):
                continue
            try:
                out.append({"path": p, "bytes": os.path.getsize(os.path.join(root, n))})
            except OSError:
                pass
    return out


def about(rec, fid, version):
    keep = ("title", "prompt", "look", "length", "frame", "lang", "created", "template", "release")
    out = {"id": fid, "version": version}
    out.update({k: rec[k] for k in keep if rec.get(k) is not None})
    if (rec.get("project") or {}).get("id"):
        out["project"] = {k: rec["project"].get(k) for k in ("id", "name") if rec["project"].get(k)}
    if started_from(rec):
        out["carried_from"] = started_from(rec)
    return out


def started_from(rec):
    """The tag of the episode whose code this one started from (episode.py), or None."""
    c = rec.get("carried") or {}
    if not c.get("film") or c.get("skipped"):
        return None
    return "%s/v%d" % (c["film"], int(c.get("version") or 1))


def _tree(repo, base, prefix, files, extra):
    """The tree of `base` (a commit or None) with everything under prefix/ replaced by `files`
    ({path: path on disk}) and `extra` ({path: text}): its id. Built in an index of its own, so
    two films of one project never share one."""
    index = os.path.join(repo, "kitcut-index-%d" % os.getpid())
    env = {"GIT_INDEX_FILE": index}
    try:
        if os.path.exists(index):
            os.remove(index)
        lines = []
        if base:  # everything the commit holds outside prefix/ (no work tree: `git rm` needs one)
            lines = [
                x
                for x in git(repo, "ls-tree", "-r", base).split("\n")
                if x and not x.split("\t", 1)[1].startswith(prefix + "/")
            ]
        if files:
            paths = list(files)
            ids = git(
                repo,
                "hash-object",
                "-w",
                "--stdin-paths",
                stdin="\n".join(files[p] for p in paths) + "\n",
            ).split("\n")
            lines += ["100644 %s\t%s/%s" % (i, prefix, p) for p, i in zip(paths, ids, strict=True)]
        for p, text in extra.items():
            lines.append(
                "100644 %s\t%s/%s"
                % (git(repo, "hash-object", "-w", "--stdin", stdin=text), prefix, p)
            )
        if lines:
            git(
                repo,
                "update-index",
                "--add",
                "--index-info",
                stdin="\n".join(lines) + "\n",
                env=env,
            )
        return git(repo, "write-tree", env=env)
    finally:
        if os.path.exists(index):
            os.remove(index)


def head(repo):
    return git(repo, "rev-parse", "-q", "--verify", BRANCH, check=False) or None


def commit(repo, prefix, files, extra, message, when=None, tag=None, plan=False):
    """Make prefix/ in the repository exactly these files. -> the new commit, or None when the
    repository already holds them (then only a missing tag is set)."""
    with locks.locked(os.path.join(repo, "kitcut.lock"), timeout=120):
        base = head(repo)
        tree = _tree(repo, base, prefix, files, extra)
        same = base and git(repo, "rev-parse", base + "^{tree}") == tree
        at = base if same else None
        if not same and not plan:
            env = {"GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when} if when else {}
            at = git(
                repo, "commit-tree", tree, *(["-p", base] if base else []), "-m", message, env=env
            )
            git(repo, "update-ref", BRANCH, at, *([base] if base else []))
        if (
            tag
            and at
            and not plan
            and not git(repo, "rev-parse", "-q", "--verify", "refs/tags/" + tag, check=False)
        ):
            git(repo, "update-ref", "refs/tags/" + tag, at)
        return None if same else (at or "(planned)")


def _when(rec, d):
    """A commit's date: when the film finished, else when its code was last written."""
    for k in ("finished", "finished_at", "updated"):
        v = rec.get(k)
        if isinstance(v, str) and re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", v):
            return v[:19]
    try:
        return "@%d +0000" % int(os.path.getmtime(os.path.join(d, "film.js")))
    except OSError:
        return None


def sync_film(f, plan=False):
    """One finished film into its repository: earlier versions still on disk first, then the
    film as it stands. -> [(version, commit)] of what was new."""
    rec = f.record()
    if f.state != DONE or f.legacy:
        return []
    repo = repo_of(repo_name(rec), make=not plan)
    if plan and not os.path.isdir(repo):
        return [(int(rec.get("version") or 1), "(planned: a new repository)")]
    title = (rec.get("title") or rec.get("prompt") or f.id).strip().splitlines()[0][:80]
    now = int(rec.get("version") or 1)
    prefix = "films/" + f.id
    made = []
    steps = []
    kept = f.path("versions")
    for name in sorted(
        os.listdir(kept) if os.path.isdir(kept) else [],
        key=lambda n: int(n[1:]) if n[1:].isdigit() else 0,
    ):
        if re.match(r"^v\d+$", name) and int(name[1:]) != now:
            steps.append((int(name[1:]), os.path.join(kept, name)))
    steps.append((now, f.dir))
    for n, d in steps:
        tag = "%s/v%d" % (f.id, n)
        if d != f.dir and git(repo, "rev-parse", "-q", "--verify", "refs/tags/" + tag, check=False):
            continue  # an earlier version, committed when it was the film
        code = code_of(d)
        if "film.js" not in code:
            continue
        extra = {"film.json": json.dumps(about(rec, f.id, n), indent=1, ensure_ascii=False) + "\n"}
        if d == f.dir:
            extra["assets.json"] = (
                json.dumps(assets_of(d, code), indent=0, ensure_ascii=False) + "\n"
            )
        c = commit(
            repo,
            prefix,
            code,
            extra,
            "%s: version %d\n\n%s%s"
            % (
                title,
                n,
                f.id,
                "\n\nStarted-from: %s" % started_from(rec) if started_from(rec) else "",
            ),
            _when(rec, d),
            tag,
            plan,
        )
        if c:
            made.append((n, c))
    return made


def sync_library(name, plan=False):
    """A project's library (its cast's code, index and episode log) into its repository."""
    if not films.PROJECT_ID.match(name):
        return None
    root = os.path.join(films.HOME, "library")
    hits = [os.path.join(root, c, name) for c in (os.listdir(root) if os.path.isdir(root) else [])]
    hits = [d for d in hits if os.path.isdir(d)]
    repo = repo_of(name)
    if not hits or not os.path.isdir(repo):
        return None
    d, files = hits[0], {}
    for base, dirs, names in os.walk(d):
        dirs.sort()
        for n in sorted(names):
            p = os.path.join(base, n)
            if _text(p):
                files[os.path.relpath(p, d).replace(os.sep, "/")] = p
    return (
        commit(repo, "library", files, {}, "The project's library", None, None, plan)
        if files
        else None
    )


def films_in(repo):
    """The film ids a repository holds on main."""
    if not head(repo):
        return []
    out = git(repo, "ls-tree", "--name-only", BRANCH, "films/", check=False)
    return [m.group(1) for m in (FILM_PATH.match(x) for x in out.split("\n")) if m]


def forget(repo, fid):
    """Rewrite a repository without one film: its folder out of every commit, its tags gone,
    and what only they held pruned."""
    with locks.locked(os.path.join(repo, "kitcut.lock"), timeout=300):
        for ref in git(repo, "for-each-ref", "--format=%(refname)", "refs/tags/%s/" % fid).split():
            git(repo, "update-ref", "-d", ref)
        env = {"FILTER_BRANCH_SQUELCH_WARNING": "1"}
        cmd = "git rm -r -q --cached --ignore-unmatch films/%s" % fid
        git(
            repo,
            "filter-branch",
            "-f",
            "--prune-empty",
            "--index-filter",
            cmd,
            "--tag-name-filter",
            "cat",
            "--",
            "--all",
            env=env,
        )
        for ref in git(repo, "for-each-ref", "--format=%(refname)", "refs/original/").split():
            git(repo, "update-ref", "-d", ref)
        git(repo, "reflog", "expire", "--expire=now", "--all")
        git(repo, "gc", "-q", "--prune=now")


def sync(only=None, plan=False):
    """Every finished film, every project's library, and the films to forget. -> {"films":
    [(id, version, commit)], "libraries": n, "forgotten": [ids], "refused": why or None}."""
    out = {"films": [], "libraries": 0, "forgotten": [], "refused": None, "errors": []}
    here = set()
    for f in reversed(films.Film.all()):  # oldest first: a repository's history reads in order
        here.add(f.id)
        if only and f.id != only:
            continue
        try:
            for n, c in sync_film(f, plan):
                out["films"].append((f.id, n, c))
        except Exception as e:  # noqa: BLE001 -- one film's trouble is not the next one's
            out["errors"].append("%s: %s" % (f.id, e))
    if only or not os.path.isdir(ROOT):
        return out
    gone = []
    for name in sorted(n[:-4] for n in os.listdir(ROOT) if n.endswith(".git")):
        repo = repo_of(name)
        try:
            if sync_library(name, plan):
                out["libraries"] += 1
            gone += [(repo, fid) for fid in films_in(repo) if fid not in here]
        except Exception as e:  # noqa: BLE001
            out["errors"].append("%s: %s" % (name, e))
    why = backup.there() if gone else None
    if gone and len(gone) > MAX_FORGET:
        why = (
            "%d films are in the repositories and not on the machine: more than %d is taken for a home that is not whole"
            % (len(gone), MAX_FORGET)
        )
    if why:
        out["refused"] = why
        return out
    for repo, fid in gone:
        if not plan:
            try:
                forget(repo, fid)
            except Exception as e:  # noqa: BLE001
                out["errors"].append("forget %s: %s" % (fid, e))
                continue
        out["forgotten"].append(fid)
    return out


def names():
    """Every repository here, by name."""
    return sorted(
        n[:-4] for n in (os.listdir(ROOT) if os.path.isdir(ROOT) else []) if n.endswith(".git")
    )


def key_path(name):
    return os.path.join(os.path.expanduser("~"), ".ssh", "filmgit", name)


def published(name):
    """Whether this repository has its copy on GitHub set up: the remote, and its own key here."""
    return bool(git(repo_of(name), "remote", "get-url", REMOTE, check=False)) and os.path.isfile(
        key_path(name)
    )


def key_of(name):
    """The public half of this repository's own key, made when there is none. One key per
    repository: on GitHub it is a deploy key that may write that one repository and nothing
    else, so the machine never holds a key to the whole organisation."""
    p = key_path(name)
    if not os.path.isfile(p):
        os.makedirs(os.path.dirname(p), mode=0o700, exist_ok=True)
        cmd = [
            "ssh-keygen",
            "-q",
            "-t",
            "ed25519",
            "-N",
            "",
            "-C",
            "kitcut-studio film repository %s" % name,
            "-f",
            p,
        ]
        subprocess.run(cmd, check=True, capture_output=True)
    with open(p + ".pub", encoding="ascii") as f:
        return f.read().strip()


def set_remote(name, org=None):
    """Point this repository at its GitHub copy, to be pushed with its own key."""
    repo, url = repo_of(name), "git@github.com:%s/%s.git" % (org or ORG, name)
    if git(repo, "remote", "get-url", REMOTE, check=False):
        git(repo, "remote", "set-url", REMOTE, url)
    else:
        git(repo, "remote", "add", REMOTE, url)
    ssh = (
        "ssh -i %s -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new -o BatchMode=yes"
        % key_path(name)
    )
    git(repo, "config", "core.sshCommand", ssh)
    return url


def push(only=None):
    """Every published repository to GitHub, exactly as it is here (--mirror: a film that was
    forgotten here goes from there too). -> {"pushed": [names], "failed": [(name, why)],
    "unpublished": [names]}. GitHub being down is never an error of the studio's: it is tried
    again at the next sync."""
    out = {"pushed": [], "failed": [], "unpublished": []}
    if backup.setting("STUDIO_DRILL") == "1":  # a rehearsal's copy of the repositories stays there
        return out
    for name in names():
        if only and name != only:
            continue
        repo = repo_of(name)
        if not head(repo):
            continue
        if not published(name):
            out["unpublished"].append(name)
            continue
        e = dict(os.environ, GIT_DIR=repo)
        try:
            r = subprocess.run(
                ["git", "push", "--mirror", "--quiet", REMOTE],
                env=e,
                capture_output=True,
                check=False,
                timeout=PUSH_S,
            )
        except subprocess.TimeoutExpired:  # GitHub hanging: this one waits for the next sync,
            out["failed"].append((name, "no answer in %d s" % PUSH_S))  # the rest go now
            continue
        if r.returncode == 0:
            out["pushed"].append(name)
        else:
            out["failed"].append((name, r.stderr.decode("utf-8", "replace").strip()[-200:]))
    return out


TASKS = set()  # on_finish's, held so they are not collected while they run
ON_FINISH = "STUDIO_FILMGIT_ON_FINISH"


def on_finish(film):
    """Commit a film that has just finished into its repository and push that one, in a process
    of its own (server.py, as a film is done), so the repository and GitHub are minutes behind
    it rather than up to an hour; the hourly sync stays the backstop. Only where the studio's .env
    says STUDIO_FILMGIT_ON_FINISH=1 (the VM's machine.env). Never raises, and nothing waits for
    it: a film is done whatever happens here."""
    try:
        on = backup.setting(ON_FINISH) or os.environ.get(ON_FINISH, "")  # the .env's, as it is now
        if on.strip() != "1":
            return None
        t = asyncio.get_running_loop().create_task(_on_finish(film.id))
    except RuntimeError:  # no loop (a script): the hourly sync takes it
        return None
    except Exception as e:  # noqa: BLE001
        print("FILMGIT %s not started: %s" % (film.id, e), flush=True)
        return None
    TASKS.add(t)
    t.add_done_callback(TASKS.discard)
    return t


async def _on_finish(fid):
    try:
        p = await asyncio.create_subprocess_exec(
            sys.executable,
            os.path.abspath(__file__),
            "--sync",
            "--film",
            fid,
            "--and-push",
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        out, _ = await asyncio.wait_for(p.communicate(), PUSH_S + 120)
        if p.returncode:
            said = out.decode("utf-8", "replace").strip()[-300:]
            print("FILMGIT %s: exit %s: %s" % (fid, p.returncode, said), flush=True)
    except Exception as e:  # noqa: BLE001 -- the hourly sync takes it
        print("FILMGIT %s: %s" % (fid, e), flush=True)


def log(fid):
    f = films.Film.open(fid)
    if f is None:
        sys.exit("no film %s on this machine" % fid)
    repo = repo_of(repo_name(f.record()))
    if not os.path.isdir(repo):
        sys.exit("%s has no repository yet (filmgit.py --sync)" % fid)
    print("%s, films/%s" % (repo, fid))
    print(
        git(
            repo,
            "log",
            "--date=short",
            "--format=%h %ad %s%d",
            BRANCH,
            "--",
            "films/" + fid,
            check=False,
        )
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--plan", action="store_true", help="what a sync would do; writes nothing")
    g.add_argument("--sync", action="store_true", help="commit what is new, forget what is gone")
    g.add_argument("--log", metavar="ID", help="a film's history")
    g.add_argument("--push", action="store_true", help="push the published repositories to GitHub")
    g.add_argument(
        "--unpublished",
        action="store_true",
        help="name<TAB>public key of each repository not on GitHub yet (makes its key)",
    )
    g.add_argument(
        "--set-remote",
        metavar="NAME",
        nargs="+",
        help="these repositories are on GitHub now: point at them",
    )
    ap.add_argument("--film", help="--plan/--sync: only this film")
    ap.add_argument(
        "--and-push",
        action="store_true",
        help="--sync --film: then push that film's repository (the studio, as a film finishes)",
    )
    a = ap.parse_args()
    if a.log:
        log(a.log)
        sys.exit(0)
    if a.unpublished:
        for name in names():
            if head(repo_of(name)) and not published(name):
                print("%s\t%s" % (name, key_of(name)))
        sys.exit(0)
    if a.set_remote:
        for name in a.set_remote:
            if not NAME.match(name) or not os.path.isdir(repo_of(name)):
                sys.exit("no such repository here: %s" % name)
            print("%s -> %s" % (name, set_remote(name)))
        sys.exit(0)
    if a.push:
        p = push()
        print(
            "pushed %d to GitHub; %d failed; %d not there yet (ops.sh filmgit publish)"
            % (len(p["pushed"]), len(p["failed"]), len(p["unpublished"]))
        )
        for name, why in p["failed"][:10]:
            print("FAILED %s: %s" % (name, why))
        sys.exit(0)
    res = sync(a.film, a.plan)
    if (
        not a.plan and not a.film
    ):  # then to GitHub: after the sync, so that what is forgotten goes too
        p = push()
        if p["pushed"] or p["failed"] or p["unpublished"]:
            print(
                "GitHub: pushed %d, %d failed, %d not there yet (ops.sh filmgit publish)"
                % (len(p["pushed"]), len(p["failed"]), len(p["unpublished"]))
            )
        for name, why in p["failed"][:5]:
            print("  push failed, tried again next time: %s: %s" % (name, why))
    elif a.film and a.and_push and not a.plan and res["films"]:
        f = films.Film.open(a.film)
        p = push(repo_name(f.record())) if f else {"failed": []}
        for name, why in p["failed"]:
            print("  push failed, tried again at the next sync: %s: %s" % (name, why))
    word = "would commit" if a.plan else "committed"
    for fid, n, c in res["films"][:40]:
        print("  %s v%d %s" % (fid, n, c[:12]))
    if len(res["films"]) > 40:
        print("  ... and %d more" % (len(res["films"]) - 40))
    print("%s %d version(s) of %d film(s); %d librar%s; %s %d film(s) that are gone" % (
        word, len(res["films"]), len({x[0] for x in res["films"]}), res["libraries"], "y" if res["libraries"] == 1 else "ies",
        "would forget" if a.plan else "forgot", len(res["forgotten"])))  # fmt: skip
    if res["refused"]:
        print("NOT forgetting: " + res["refused"])
    for e in res["errors"][:10]:
        print("ERROR: " + e)
    sys.exit(1 if res["errors"] else 0)
