#!/usr/bin/env python
"""filmgit.py with real git, on films made of small files in a home of its own: no network, seconds.

    python studio/test_filmgit.py

A finished film's code goes into its project's repository under films/<id>/, with what it is and
a list of everything that is not code; nothing but code is committed, and nothing of another
film is touched. A second sync commits nothing. A changed film is a second commit and a second
tag; versions still on disk go in first, in order. A film outside a project goes to its
workspace's repository, and one with no signed-in maker to w-other. A film that is not finished
is left alone. A plan writes nothing. A deleted film is rewritten out of its repository -- its
folder, its tags, its bytes -- while the film beside it keeps its whole history; and that is
refused when too many are missing at once.
"""

import os
import sys
import json
import shutil
import tempfile
import subprocess

HOME = tempfile.mkdtemp(prefix="studio-filmgit-test-")
os.environ["STUDIO_HOME"] = HOME
os.environ["STUDIO_REPO"] = os.path.join(HOME, "repo")
os.environ["STUDIO_ENV_FILE"] = os.path.join(HOME, "repo", ".env")
# the machine's own keys for its repositories live under the home of whoever runs it
os.environ["HOME"] = os.environ["USERPROFILE"] = os.path.join(HOME, "user")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import film as films  # noqa: E402
import filmgit  # noqa: E402

bad = []
ALICE = "u:" + "a" * 24
PROJECT = {"id": "p-abcdefghij", "name": "Duchess"}
N = [0]


def check(ok, what, got=None):
    print("%s  %s%s" % ("ok   " if ok else "FAIL ", what, "" if ok else "  -- %r" % (got,)))
    if not ok:
        bad.append(what)


def put(d, rel, body="x"):
    p = os.path.join(d, *rel.split("/"))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(body)
    return p


def film(state="done", client=ALICE, project=PROJECT, **rec):
    N[0] += 1
    fid = "studio-20261001-0000%02d-%s" % (N[0], "abcdef"[N[0] % 6] * 6)
    d = os.path.join(HOME, "projects", fid)
    put(d, "film.js", "SK.film(function () { /* %s */ });\n" % fid)
    put(d, "sketch.json", '{"duration": 5}\n')
    put(d, "vo.json", '{"lines": []}\n')
    put(d, "cast/pip.js", "SK.cast.pip = 1;\n")
    put(d, "engine/engine.js", "var SK = {};\n")
    put(d, "scenes/01-open.js", "SK.scene('open');\n")
    put(d, "audio/vo/L01_T0_ab12.wav", "RIFF")
    put(d, "images/scene-1.png", "PNG")
    put(d, "inputs/upload1.jpg", "JPG")
    put(d, "outputs/film.mp4", "MP4")
    put(d, "temp/motion/000.50.png", "PNG")
    put(d, "events.jsonl", "{}\n")
    full = {
        "state": state,
        "title": "Pip bakes bread",
        "prompt": "a cat bakes",
        "look": "drawn",
        "length": 5,
    }
    full.update(
        {
            "client": client,
            "project": project,
            "cost_usd": 3.2,
            "claude_session": "secret-session",
            **rec,
        }
    )
    put(d, "studio.json", json.dumps({k: v for k, v in full.items() if v is not None}))
    return films.Film(d)


def tree(repo, ref="refs/heads/main"):
    return filmgit.git(repo, "ls-tree", "-r", "--name-only", ref).split("\n")


def show(repo, path, ref="refs/heads/main"):
    return filmgit.git(repo, "show", "%s:%s" % (ref, path))


def tags(repo):
    return sorted(filmgit.git(repo, "tag").split())


def a_finished_film():
    f, other = film(), film()
    plan = filmgit.sync(plan=True)
    check(
        not os.path.isdir(filmgit.ROOT) and len(plan["films"]) == 2,
        "a plan names the films and writes nothing",
        plan,
    )

    res = filmgit.sync()
    repo = filmgit.repo_of("p-abcdefghij")
    check(
        os.path.isdir(repo) and not res["errors"],
        "a project's films go into the project's repository",
        res,
    )
    names = tree(repo)
    mine = sorted(n for n in names if n.startswith("films/%s/" % f.id))
    want = sorted("films/%s/%s" % (f.id, n) for n in (
        "film.js", "sketch.json", "vo.json", "cast/pip.js", "engine/engine.js", "scenes/01-open.js", "film.json", "assets.json"))  # fmt: skip
    check(mine == want, "the film's code, what it is, and its list of the rest", mine)
    check(not [n for n in names if n.endswith((".wav", ".png", ".jpg", ".mp4", "studio.json", "events.jsonl"))],
          "no picture, sound, video or studio record is committed")  # fmt: skip
    about = json.loads(show(repo, "films/%s/film.json" % f.id))
    check(about == {"id": f.id, "version": 1, "title": "Pip bakes bread", "prompt": "a cat bakes", "look": "drawn",
                    "length": 5, "project": PROJECT}, "film.json says what it is, and nothing about cost or sessions", about)  # fmt: skip
    assets = {a["path"]: a["bytes"] for a in json.loads(show(repo, "films/%s/assets.json" % f.id))}
    check(assets == {"audio/vo/L01_T0_ab12.wav": 4, "images/scene-1.png": 3, "inputs/upload1.jpg": 3, "outputs/film.mp4": 3},
          "assets.json lists what a checkout fetches from the mirror, without temp/", assets)  # fmt: skip
    check(
        tags(repo) == sorted(["%s/v1" % f.id, "%s/v1" % other.id]),
        "each version is tagged",
        tags(repo),
    )
    check(show(repo, "films/%s/film.js" % f.id) + "\n" == open(f.path("film.js"), encoding="utf-8").read(),
          "what is committed is the file, byte for byte")  # fmt: skip

    again = filmgit.sync()
    check(again["films"] == [] and not again["errors"], "a second sync commits nothing", again)
    n = int(filmgit.git(repo, "rev-list", "--count", "refs/heads/main"))
    check(n == 2, "one commit a film", n)
    return f, other, repo


def a_new_version(f, other, repo):
    # a round made version 2: the film's files changed, version 1's kept beside it
    v1 = f.path("versions", "v1")
    put(v1, "film.js", open(f.path("film.js"), encoding="utf-8").read())
    put(v1, "sketch.json", '{"duration": 5}\n')
    put(f.dir, "film.js", "SK.film(function () { /* version two */ });\n")
    rec = f.record()
    rec["version"] = 2
    put(f.dir, "studio.json", json.dumps(rec))
    res = filmgit.sync()
    check(
        [(x[0], x[1]) for x in res["films"]] == [(f.id, 2)], "a changed film is one new commit", res
    )
    check("%s/v2" % f.id in tags(repo), "tagged with its version", tags(repo))
    check(
        "version two" in show(repo, "films/%s/film.js" % f.id), "main holds the film as it stands"
    )
    check(
        "version two" not in show(repo, "films/%s/film.js" % f.id, "refs/tags/%s/v1" % f.id),
        "and the tag holds version 1",
    )
    check(
        json.loads(show(repo, "films/%s/film.json" % f.id))["version"] == 2,
        "film.json says version 2",
    )
    check("films/%s/film.js" % other.id in tree(repo), "the film beside it is as it was")


def versions_on_disk_go_in_first():
    f = film(version=3)
    for n in (1, 2):
        put(f.path("versions", "v%d" % n), "film.js", "// version %d\n" % n)
    filmgit.sync()
    repo = filmgit.repo_of("p-abcdefghij")
    log = filmgit.git(repo, "log", "--format=%s", "refs/heads/main", "--", "films/" + f.id).split(
        "\n"
    )
    check(
        [s.rsplit(" ", 1)[-1] for s in log] == ["3", "2", "1"],
        "a film's history starts as far back as its files do",
        log,
    )
    check(
        show(repo, "films/%s/film.js" % f.id, "refs/tags/%s/v1" % f.id) == "// version 1",
        "each at its own tag",
    )
    check(
        {"%s/v%d" % (f.id, n) for n in (1, 2, 3)} <= set(tags(repo)), "all three tagged", tags(repo)
    )
    return f


def where_a_film_goes():
    loose = film(project=None)
    anon = film(client="203.0.113.9", project=None)
    making = film(state="claude")
    failed = film(state="error")
    res = filmgit.sync()
    names = sorted(n[:-4] for n in os.listdir(filmgit.ROOT))
    ws = [n for n in names if n.startswith("w-") and n != "w-other"]
    check(
        len(ws) == 1 and len(ws[0]) == 22,
        "a film outside a project goes to its workspace's repository",
        names,
    )
    check("films/%s/film.js" % loose.id in tree(filmgit.repo_of(ws[0])), "under its own id")
    check(
        "films/%s/film.js" % anon.id in tree(filmgit.repo_of("w-other")),
        "one with no signed-in maker goes to w-other",
    )
    everything = "\n".join("\n".join(tree(filmgit.repo_of(n))) for n in names)
    check(
        making.id not in everything and failed.id not in everything,
        "a film that is not finished is not committed",
        res,
    )
    check(filmgit.repo_name({"client": ALICE}) == filmgit.repo_name({"client": "o:" + "a" * 24}),
          "a person and their own workspace are one repository")  # fmt: skip
    for x in (making, failed):
        shutil.rmtree(x.dir)


def to_github(f):
    """A repository's copy elsewhere, here a bare repository standing in for GitHub's."""
    name = "p-abcdefghij"
    repo = filmgit.repo_of(name)
    p = filmgit.push()
    check(
        name in p["unpublished"] and not p["pushed"],
        "a repository with no copy set up is named, not pushed",
        p,
    )

    pub = filmgit.key_of(name)
    check(
        pub.startswith("ssh-ed25519 ") and os.path.isfile(filmgit.key_path(name)),
        "it gets a key of its own",
        pub[:20],
    )
    check(filmgit.key_of(name) == pub, "the same one when asked again")
    other_key = filmgit.key_of("w-other")
    check(other_key != pub, "and every repository another")
    url = filmgit.set_remote(name)
    check(
        url == "git@github.com:kitcut-films/p-abcdefghij.git",
        "its copy is in the films' own organisation",
        url,
    )
    ssh = filmgit.git(repo, "config", "core.sshCommand")
    check(
        filmgit.key_path(name) in ssh and "IdentitiesOnly=yes" in ssh,
        "pushed with that key and no other",
        ssh,
    )
    check(
        filmgit.published(name) and not filmgit.published("w-other"),
        "it counts as published; one with a key and no copy does not",
    )

    there = os.path.join(HOME, "github", name + ".git")
    subprocess.run(
        ["git", "init", "-q", "--bare", "--initial-branch=main", there],
        check=True,
        capture_output=True,
    )
    filmgit.git(
        repo, "remote", "set-url", filmgit.REMOTE, there
    )  # the stand-in, reached without ssh
    p = filmgit.push()
    check(name in p["pushed"] and not p["failed"], "a published repository is pushed", p)
    check("films/%s/film.js" % f.id in tree(there), "its copy holds the film")
    check(tags(there) == tags(repo), "and every version's tag", tags(there))
    check(
        filmgit.push(only="w-other")["unpublished"] == ["w-other"],
        "the others wait to be published",
    )

    put(os.path.dirname(os.environ["STUDIO_ENV_FILE"]), ".env", "STUDIO_DRILL=1" + chr(10))
    drill = filmgit.push()
    os.remove(os.environ["STUDIO_ENV_FILE"])
    check(not drill["pushed"] and not drill["unpublished"], "a rehearsal pushes nothing", drill)
    for rn in ("p-abcdefghij", "w-other", "w-" + "0" * 20):
        check(filmgit.NAME.match(rn), "%s is a repository's name" % rn)
    check(
        not filmgit.NAME.match("../x") and not filmgit.NAME.match("p-short"), "and nothing else is"
    )
    return there


def a_deleted_film_goes_from_github_too(f, there):
    p = filmgit.push()
    check(
        "p-abcdefghij" in p["pushed"],
        "after a film was forgotten the repository is pushed again",
        p,
    )
    every = filmgit.git(there, "rev-list", "--all").split()
    held = " ".join(filmgit.git(there, "ls-tree", "-r", "--name-only", c) for c in every)
    check(
        f.id not in held and not [t for t in tags(there) if t.startswith(f.id)],
        "and its copy no longer holds the film, nor its tags",
    )


def a_deleted_film(f, other, kept):
    repo = filmgit.repo_of("p-abcdefghij")
    secret = "version two"
    before = int(filmgit.git(repo, "rev-list", "--count", "refs/heads/main"))
    shutil.rmtree(f.dir)
    plan = filmgit.sync(plan=True)
    check(
        plan["forgotten"] == [f.id] and f.id in "\n".join(tree(repo)),
        "a plan names the film to forget and keeps it",
        plan,
    )
    res = filmgit.sync()
    check(
        res["forgotten"] == [f.id] and not res["errors"],
        "a film that is gone from the machine is forgotten",
        res,
    )
    check(f.id not in "\n".join(tree(repo)), "its folder is out of main")
    check(not [t for t in tags(repo) if t.startswith(f.id)], "its tags are gone", tags(repo))
    every = filmgit.git(repo, "rev-list", "--all").split()
    held = "\n".join(filmgit.git(repo, "ls-tree", "-r", "--name-only", c) for c in every)
    check(f.id not in held, "no commit that is left holds it")
    blobs = subprocess.run(
        ["git", "grep", "-l", secret, *every],
        env=dict(os.environ, GIT_DIR=repo),
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    check(not blobs.strip(), "and its code is not found in any of them", blobs)
    loose = subprocess.run(
        ["git", "fsck", "--unreachable", "--no-reflogs"],
        env=dict(os.environ, GIT_DIR=repo),
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    check("unreachable" not in loose, "nor left behind unreachable", loose[:200])
    check(
        "films/%s/film.js" % other.id in tree(repo) and "%s/v1" % other.id in tags(repo),
        "the film beside it is whole, with its tag",
    )
    log = filmgit.git(
        repo, "log", "--format=%s", "refs/heads/main", "--", "films/" + kept.id
    ).split("\n")
    check(len(log) == 3, "and another film's three versions are still three commits", log)
    after = int(filmgit.git(repo, "rev-list", "--count", "refs/heads/main"))
    check(
        after == before - 2,
        "the forgotten film's own commits are gone, not emptied",
        (before, after),
    )


def too_many_missing_is_refused():
    many = [film(project=None) for _ in range(filmgit.MAX_FORGET + 1)]
    filmgit.sync()
    for x in many:
        shutil.rmtree(x.dir)
    res = filmgit.sync()
    check(
        res["refused"] and not res["forgotten"],
        "more films missing at once than the limit is taken for a broken home",
        res,
    )
    held = "\n".join(tree(filmgit.repo_of(filmgit.repo_name({"client": ALICE}))))
    check(all(x.id in held for x in many), "and nothing is forgotten")


def where_an_episode_started():
    """film.json says which release made a film and which episode's code it started from
    (episode.py), and the commit says so too -- by tag, which survives a forget's rewrite."""
    prev = film(release="0123456789ab")
    ep = film(release="0123456789ab", carried={"film": prev.id, "version": 2})
    fresh = film(carried={"skipped": "a collection"})
    filmgit.sync(ep.id)
    filmgit.sync(fresh.id)
    repo = filmgit.repo_of("p-abcdefghij")
    a = json.loads(show(repo, "films/%s/film.json" % ep.id))
    check(
        a.get("release") == "0123456789ab" and a.get("carried_from") == "%s/v2" % prev.id,
        "film.json names its release and the episode it started from",
        a,
    )
    said = filmgit.git(repo, "log", "-1", "--format=%B", "refs/tags/%s/v1" % ep.id)
    check("Started-from: %s/v2" % prev.id in said, "and so does its commit", said)
    plain = json.loads(show(repo, "films/%s/film.json" % fresh.id))
    check(
        "carried_from" not in plain
        and "Started-from" not in filmgit.git(repo, "log", "-1", "--format=%B", "refs/tags/%s/v1" % fresh.id),
        "an episode that started from nothing says nothing",
        plain,
    )  # fmt: skip


def a_push_that_hangs():
    """GitHub not answering: that repository waits for the next sync, and the run goes on."""
    real = subprocess.run

    def hang(args, **kw):
        if list(args[:2]) == ["git", "push"]:
            raise subprocess.TimeoutExpired(args, filmgit.PUSH_S)
        return real(args, **kw)

    filmgit.subprocess.run = hang
    try:
        p = filmgit.push()
    finally:
        filmgit.subprocess.run = real
    check(
        not p["pushed"]
        and [n for n, _ in p["failed"]] == ["p-abcdefghij"]
        and "no answer" in p["failed"][0][1],
        "a push that hangs is a failure of that repository's, not the end of the run",
        p,
    )


def committed_as_it_finishes(there):
    """The server's on_finish: off unless the studio's .env says so; on, the film is in its
    repository and on GitHub as soon as it is done, without waiting for the hour."""
    import asyncio

    ep = film()
    check(filmgit.on_finish(ep) is None, "off unless STUDIO_FILMGIT_ON_FINISH=1")
    os.environ["STUDIO_FILMGIT_ON_FINISH"] = "1"
    try:
        check(filmgit.on_finish(ep) is None, "and nothing without a running loop (a script)")

        async def finish():
            await filmgit.on_finish(ep)

        asyncio.run(finish())
    finally:
        del os.environ["STUDIO_FILMGIT_ON_FINISH"]
    repo = filmgit.repo_of("p-abcdefghij")
    check("%s/v1" % ep.id in tags(repo), "a finished film is committed as it finishes")
    check("%s/v1" % ep.id in tags(there), "and pushed to its copy")


if __name__ == "__main__":
    try:
        f, other, repo = a_finished_film()
        a_new_version(f, other, repo)
        kept = versions_on_disk_go_in_first()
        where_a_film_goes()
        there = to_github(f)
        a_deleted_film(f, other, kept)
        a_deleted_film_goes_from_github_too(f, there)
        too_many_missing_is_refused()
        where_an_episode_started()
        a_push_that_hangs()
        committed_as_it_finishes(there)
    finally:
        shutil.rmtree(HOME, ignore_errors=True)
    print("\n%d failed" % len(bad) if bad else "\nall passed")
    sys.exit(1 if bad else 0)
