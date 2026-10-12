#!/usr/bin/env python
"""restore.py without rclone or a bucket: what makes a machine a rehearsal, and what a rehearsal
does to its copy of the home. Seconds.

    python studio/test_restore.py

A second machine built from the mirror must not act as the studio: started on a restored home it
would adopt every film that was being made and write that into the live database. So a rehearsal
is a machine whose .env says so and has no database, no announcement, no tunnel and no key to the
films' bucket -- each one missing is named. On anything else --settle and --all --drill change
nothing. On a rehearsal, --settle puts down the films that were being made, in their own records
only, takes away the marks of rounds and unbrandings under way and the servers' folder, and
leaves a finished film as it was. A rehearsal never writes the mirror. A rehearsal's restore
leaves the marks out; a real one brings everything.
"""

import os
import sys
import json
import shutil
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = tempfile.mkdtemp(prefix="studio-restore-test-")
os.environ["STUDIO_HOME"] = os.path.join(ROOT, "studio")
os.environ["STUDIO_REPO"] = os.path.join(ROOT, "repo")
os.environ["STUDIO_ENV_FILE"] = os.path.join(ROOT, "repo", ".env")
os.environ.pop("MONGODB_URI", None)
sys.path.insert(0, HERE)
import backup  # noqa: E402 -- the stdlib only
import restore  # noqa: E402
import film as films  # noqa: E402
import rounds  # noqa: E402 -- imports the studio; only its names are read here
import unbrand  # noqa: E402

bad = []
DRILL = {"STUDIO_DRILL": "1", "STUDIO_BACKUP_R2_KEY_ID": "k", "STUDIO_BACKUP_R2_SECRET": "s"}
DRILL["STUDIO_BACKUP_R2_ENDPOINT"] = "https://acct.r2.cloudflarestorage.com"


def check(ok, what, got=None):
    print("%s  %s%s" % ("ok   " if ok else "FAIL ", what, "" if ok else "  -- %r" % (got,)))
    if not ok:
        bad.append(what)


def write_env(**kv):
    os.makedirs(os.path.dirname(backup.ENV_FILE), exist_ok=True)
    with open(backup.ENV_FILE, "w", encoding="utf-8") as f:
        for k, v in kv.items():
            f.write("%s=%s\n" % (k, v))


def put(rel, body="x"):
    p = os.path.join(backup.HOME, *rel.split("/"))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(body if isinstance(body, str) else json.dumps(body))
    return p


def rec(fid):
    with open(os.path.join(backup.HOME, "projects", fid, "studio.json"), encoding="utf-8") as f:
        return json.load(f)


def what_a_rehearsal_is():
    write_env(**DRILL)
    check(
        restore.not_a_drill() == [],
        "a .env that says so, with none of the four, is a rehearsal",
        restore.not_a_drill(),
    )
    for key, value, word in (
        ("MONGODB_URI", "mongodb+srv://x", "database"),
        ("STUDIO_ANNOUNCE", "1", "kitcut.ai"),
        ("STUDIO_TUNNEL", "kitcut-studio", "tunnel"),
        ("STUDIO_R2_KEY_ID", "films-key", "films' bucket"),
        ("STUDIO_MEDIA_SAS", "sv=1", "films' bucket"),
    ):
        write_env(**DRILL, **{key: value})
        why = restore.not_a_drill()
        check(len(why) == 1 and word in why[0], "with %s it is not, and says why" % key, why)
    write_env(
        STUDIO_R2_KEY_ID="k",
        STUDIO_R2_SECRET="s",
        STUDIO_R2_ENDPOINT="https://a.example/b",
        MONGODB_URI="m",
    )
    check(
        len(restore.not_a_drill()) == 3,
        "the production machine is not one, three times over",
        restore.not_a_drill(),
    )


def settle_changes_only_a_rehearsal():
    ids = {
        s: "studio-20261001-00000%d-abcdef" % i
        for i, s in enumerate(("done", "queued", "claude", "finishing", "waiting"))
    }
    for state, fid in ids.items():
        put("projects/%s/studio.json" % fid, {"state": state, "title": state})
    changing = "studio-20261001-000009-abcdef"
    put(
        "projects/%s/studio.json" % changing,
        {"state": "done", "round": {"state": "running", "id": "r2"}},
    )
    put("rounds/_asked/%s.json" % changing, "{}")
    put("unbrand/%s.json" % ids["done"], "{}")
    put("servers/current", "c994")

    write_env(
        STUDIO_R2_KEY_ID="k",
        STUDIO_R2_SECRET="s",
        STUDIO_R2_ENDPOINT="https://a.example/b",
        MONGODB_URI="m",
    )
    try:
        restore.settle()
        refused = False
    except SystemExit:
        refused = True
    check(
        refused and rec(ids["queued"])["state"] == "queued",
        "on the production machine --settle changes nothing",
    )
    check(os.path.exists(os.path.join(rounds.MARKS, changing + ".json")), "and leaves the marks")

    write_env(**DRILL)
    done = restore.settle()
    for state in ("queued", "claude", "finishing"):
        check(
            rec(ids[state])["state"] == "interrupted",
            "on a rehearsal a film that was %s is put down" % state,
            rec(ids[state]),
        )
    check(rec(ids["done"])["state"] == "done", "a finished film is left as it was")
    check(
        rec(ids["waiting"])["state"] == "waiting",
        "and one waiting for its voice (no server picks it up)",
    )
    check(
        rec(changing)["round"]["state"] == "failed",
        "a round under way is ended in the copy",
        rec(changing),
    )
    check(
        sorted(done) == sorted([ids["queued"], ids["claude"], ids["finishing"], changing]),
        "and each is named",
        done,
    )
    for what, d in (("rounds", rounds.MARKS), ("unbrandings", unbrand.MARKS)):
        check(not os.path.exists(d), "the marks of %s under way are gone" % what)
    check(
        not os.path.exists(os.path.join(backup.HOME, "servers")),
        "and the folder of the servers that were alive",
    )


def a_rehearsal_never_writes_the_mirror():
    write_env(**DRILL)
    check(
        "rehearsal" in (backup.there() or ""),
        "backup.py refuses a pass from a rehearsal",
        backup.there(),
    )
    res = backup.run()
    check(res["ok"] is False and not res.get("parts"), "and runs nothing", res)


def what_is_pulled():
    real = dict(restore.pulls("kitcut-backup"))
    drill = dict(restore.pulls("kitcut-backup", drill=True))
    check(
        real["home"][:4] == ["rclone", "copy", "kitcut:kitcut-backup/home", backup.HOME],
        "the mirror's home into the home",
    )
    check("--update" in real["home"], "a file that is newer here stays")
    check(
        "sync" not in real["home"] and "--delete-during" not in real["home"],
        "nothing here is ever removed",
    )
    check("--exclude" not in real["home"], "a real restore brings everything, the marks too")
    check(
        set(restore.DRILL_SKIP) <= set(drill["home"]),
        "a rehearsal's leaves out the marks of work under way",
    )
    check("usage" in real and "usage" not in drill, "and has no use for the usage log")
    check("models" in real and "models" in drill, "both bring the models")
    flat = " ".join(a for cmd in list(real.values()) + list(drill.values()) for a in cmd)
    check(
        "STUDIO_" not in flat and "SECRET" not in flat.upper().replace("--S3", ""),
        "no key is on a command line",
    )


def same_as_the_studio():
    check(restore.ACTIVE == films.ACTIVE, "a film being made is what film.py calls one")
    check(restore.PUT_DOWN in films.STATES, "and 'interrupted' is a state films have")
    marks = (os.path.join(backup.HOME, "rounds", "_asked"), os.path.join(backup.HOME, "unbrand"))
    check(
        marks == (rounds.MARKS, unbrand.MARKS),
        "the marks are where rounds.py and unbrand.py put them",
    )
    check(
        restore.DRILL_SKIP == ("/rounds/_asked/**", "/unbrand/**"),
        "and those are what a rehearsal leaves out",
    )


if __name__ == "__main__":
    try:
        what_a_rehearsal_is()
        settle_changes_only_a_rehearsal()
        a_rehearsal_never_writes_the_mirror()
        what_is_pulled()
        same_as_the_studio()
    finally:
        shutil.rmtree(ROOT, ignore_errors=True)
    print("\n%d failed" % len(bad) if bad else "\nall passed")
    sys.exit(1 if bad else 0)
