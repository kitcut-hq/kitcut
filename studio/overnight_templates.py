#!/usr/bin/env python3
r"""A night of template work on the studio VM with nobody watching: wait for source films already
being made, start the ones the account's two-at-once limit refused, turn each finished film into
a DRAFT template (never published) and make test films from each draft.

It has no Claude of its own. The films are made by the studio as any film is; the template by
studio/template_from_film.py (pull, prove, check, spec) and studio/templates.py (make), run in a
clone of the release the studio runs. Everything it does and every failure goes to overnight.log
and REPORT.md beside the jobs file. First run: 2026-10-03, three event templates (a trade show
booth invitation, an open house invitation, a webinar promo); studio/deploy/overnight.example/
is that night's jobs file and prompts.

What it cannot do, so a person does it the next morning (the film-to-template skill):
  - judge the films: look at every one before anything is published;
  - write the real spec: a spec written before its film exists is a rough draft. Rewrite the
    description, the brief and the generic words from the film, choose the frames it holds up in,
    and make the next version before publishing;
  - the site's page (sketch-studio specs/templates/), and the source films' place in an account
    (studio/import_film.py) when they were started here and not on the site.

The jobs file (JSON), with its prompts beside it:
  {"wait": ["studio-..."],                      films already in the making, to wait for first
   "jobs": [{"slug": "open-house-invitation",
             "film": "studio-...",              its source film, or
             "prompt_file": "open-house.md",    a prompt to start one from (30 s, drawn, link-only)
             "spec": {"title": ..., "description": ..., "example": ..., "brief": ...},
             "tests": ["one sentence a stranger would type", ...]}]}

Invoke as (on the VM, from the laptop; a memory cap and low priority, as every job beside films):
    bash studio/deploy/vm.sh ssh kitcut-studio-1 'B=/srv/kitcut/overnight && mkdir -p $B && \
      [ -d $B/kitcut ] || git clone -q /srv/kitcut/repo $B/kitcut; \
      ln -sfn /srv/kitcut/repo/.venv $B/kitcut/.venv; \
      ln -sfn /srv/kitcut/repo/models $B/kitcut/models'
    (copy this file, the jobs file and its prompts into /srv/kitcut/overnight)
    sudo systemd-run --unit=kitcut-overnight-<date> --uid=kitcut --gid=kitcut \
      --working-directory=/srv/kitcut/overnight -p MemoryHigh=3G -p MemoryMax=4G -p Nice=10 \
      --setenv=TZ=America/Los_Angeles --setenv=PYTHONUNBUFFERED=1 --setenv=HF_HOME=/srv/kitcut/hf \
      /usr/bin/python3 overnight_templates.py --jobs /srv/kitcut/overnight/jobs.json
    python3 overnight_templates.py --jobs jobs.json --plan      what it would do; nothing started

Stdlib only: it runs on the VM's own python, outside the studio's environment.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import time
import traceback
import urllib.request

HOME = "/srv/kitcut/studio"
REPO = "/srv/kitcut/repo"
PY = REPO + "/.venv/bin/python"
API = "http://127.0.0.1:8765"
FINAL = ("done", "error", "cancelled", "interrupted", "lost", "failed")
OURS = 2  # films of ours at once: the studio makes 3, one slot stays free for customers

BASE = KIT = LOG = REPORT = ""  # set from --jobs: its folder, the clone in it, the two records
ROWS = []  # the report, a line per thing that happened


def log(*a):
    line = time.strftime("%m-%d %H:%M:%S ") + " ".join(str(x) for x in a)
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def note(line):
    ROWS.append(line)
    log("REPORT:", line)
    with open(REPORT, "w", encoding="utf-8") as f:
        f.write("# Overnight templates\n\n" + "\n".join(ROWS) + "\n")


def token():
    for line in open(REPO + "/.env", encoding="utf-8"):
        if line.startswith("STUDIO_TOKEN="):
            return line.split("=", 1)[1].strip().strip("\"'")
    raise RuntimeError("no STUDIO_TOKEN")


def call(path, body=None):
    req = urllib.request.Request(API + path, method="POST" if body is not None else "GET")
    req.add_header("Authorization", "Bearer " + token())
    data = None
    if body is not None:
        req.add_header("Content-Type", "application/json")
        data = json.dumps(body).encode()
    with urllib.request.urlopen(req, data, timeout=60) as r:
        return json.loads(r.read().decode() or "{}")


def record(fid):
    try:
        with open(os.path.join(HOME, "projects", fid, "studio.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def wait(fids, hours=4):
    """Until every film has ended (or the hours pass). Returns {id: state}."""
    end = time.time() + hours * 3600
    while True:
        st = {f: record(f).get("state") for f in fids}
        if all(s in FINAL for s in st.values()) or time.time() > end:
            log("films:", st)
            return st
        time.sleep(60)


def post_film(body, label):
    """A film on the studio once fewer than OURS are in the making; its id, or None."""
    for _ in range(600):
        try:
            h = call("/api/health")
            if (h.get("running") or 0) + (h.get("queued") or 0) < OURS:
                break
        except Exception as e:  # noqa: BLE001 -- the studio may be restarting; ask again
            log("health:", e)
        time.sleep(60)
    try:
        r = call("/api/films", body)
    except Exception as e:  # noqa: BLE001
        note("- %s: NOT started (%s)" % (label, e))
        return None
    fid = r.get("id")
    log(label, "->", fid or r)
    if not fid:
        note("- %s: NOT started (%s)" % (label, json.dumps(r)[:300]))
    return fid


def how(fid):
    """A finished film's link, or why it is not one."""
    rec = record(fid)
    if rec.get("state") != "done":
        return "(%s)" % str(rec.get("error") or rec.get("state"))[:200]
    urls = sorted(set(re.findall(r"https://[^\"\\ ]+?\.mp4[^\"\\ ]*", json.dumps(rec))))
    return urls[0] if urls else "(no link in its record: %s/projects/%s)" % (HOME, fid)


def run(args, env=None, timeout=5400):
    log("$", " ".join(args))
    e = dict(os.environ, **(env or {}))
    try:
        r = subprocess.run(
            args, cwd=KIT, env=e, capture_output=True, text=True, timeout=timeout, check=False
        )
    except subprocess.TimeoutExpired:
        log("  timed out")
        return 124, "timed out"
    out = (r.stdout or "") + (r.stderr or "")
    log("  rc=%s\n%s" % (r.returncode, out[-2500:]))
    return r.returncode, out


def template(fid, slug, spec, tests):
    """A finished film -> a draft template in the studio's home -> its test films."""
    tid = "t-" + slug
    if record(fid).get("state") != "done":
        note("- **%s**: its source film %s is not done %s: no template." % (slug, fid, how(fid)))
        return
    src = os.path.join(KIT, "temp", "vm-films", fid)
    if not os.path.isdir(src):  # where `pull` looks before it reaches for the VM
        shutil.copytree(os.path.join(HOME, "projects", fid), src, symlinks=True)
    tool = [PY, "studio/template_from_film.py"]
    rc, out = run(tool + ["pull", fid, "--slug", slug, "--force"])
    if rc != 0:
        note("- **%s**: pull failed: %s" % (slug, out[-300:].strip()))
        return
    proj = os.path.join(KIT, "projects", slug)
    try:
        with open(os.path.join(proj, "content.json"), encoding="utf-8") as f:
            content = json.load(f)
    except (OSError, ValueError):
        content = {}
    if len(content) < 2:
        note(
            "- **%s**: the film keeps its facts in its code (no FACTS object): it needs the hand "
            "refactor; no draft made." % slug
        )
        return
    rc, out = run(tool + ["prove", "--slug", slug])
    proved = "same pixels as the film" if rc == 0 else "NOT proved (%s)" % out[-200:].strip()
    rc, out = run(tool + ["check", "--slug", slug])
    checked = "the code says nothing of the sample" if rc == 0 else out[-300:].strip()
    rc, out = run(tool + ["spec", "--slug", slug, "--site", BASE + "/no-site"])
    sp = os.path.join(KIT, "config", "templates", slug + ".json")
    try:
        with open(sp, encoding="utf-8") as f:
            s = json.load(f)
    except (OSError, ValueError):
        note(
            "- **%s**: no spec written (%s); %s; %s." % (slug, out[-200:].strip(), proved, checked)
        )
        return
    s.update(spec)
    with open(sp, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=1)
    rc, out = run(
        [PY, "studio/templates.py", "make", "--folder", proj, "--id", tid, "--spec", sp],
        env={"STUDIO_HOME": HOME},
    )
    if rc != 0:
        note("- **%s**: no draft: %s; %s; %s." % (slug, out[-400:].strip(), proved, checked))
        return
    v = max(int(n[1:]) for n in os.listdir(os.path.join(HOME, "templates", tid)) if n[1:].isdigit())
    note(
        "- **%s**: draft template %s v%d from %s (%s; %s). Preview: %s/templates/%s/v%d/preview/"
        % (slug, tid, v, fid, proved, checked, HOME, tid, v)
    )
    made = []
    for i, prompt in enumerate(tests):
        t = post_film(
            {"template": {"id": tid, "version": v}, "prompt": prompt, "listed": False},
            "%s test %d" % (slug, i + 1),
        )
        if t:
            made.append((t, prompt))
    st = wait([t for t, _ in made], hours=3)
    for t, prompt in made:
        note('  - test film %s (%s): "%s" %s' % (t, st.get(t), prompt, how(t)))


def main():
    global BASE, KIT, LOG, REPORT  # noqa: PLW0603 -- the night's folder, named once
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--jobs", required=True, help="the night's jobs file (JSON)")
    ap.add_argument("--plan", action="store_true", help="say what it would do; start nothing")
    a = ap.parse_args()
    with open(a.jobs, encoding="utf-8") as f:
        night = json.load(f)
    BASE = os.path.dirname(os.path.abspath(a.jobs))
    KIT, LOG, REPORT = BASE + "/kitcut", BASE + "/overnight.log", BASE + "/REPORT.md"
    first, jobs = night.get("wait") or [], night.get("jobs") or []
    if a.plan:
        print("would wait for %d film(s): %s" % (len(first), ", ".join(first) or "-"))
        for j in jobs:
            src = j.get("film") or "a new film from %s" % j.get("prompt_file")
            print(
                "would make draft t-%s from %s, then %d test film(s)"
                % (j["slug"], src, len(j.get("tests") or []))
            )
        return
    note(
        "Started %s. Nothing here is published: every template is a draft, every film link-only.\n"
        % time.strftime("%Y-%m-%d %H:%M %Z")
    )
    for fid, s in wait(first, hours=3).items():
        note("- film %s is %s. %s" % (fid, s, how(fid)))
    # the source films the account's two-at-once limit refused: made on the studio itself
    for j in jobs:
        if not j.get("film") and j.get("prompt_file"):
            with open(os.path.join(BASE, "prompts", j["prompt_file"]), encoding="utf-8") as f:
                prompt = f.read().strip()
            j["film"] = post_film(
                {"prompt": prompt, "seconds": 30, "look": "drawn", "listed": False},
                j["slug"] + " source",
            )
            j["started"] = True
    for j in jobs:
        try:
            if not j.get("film"):
                note("- **%s**: its source film never started." % j["slug"])
                continue
            s = wait([j["film"]], hours=3)[j["film"]]
            if j.get("started"):
                note(
                    "- **%s** source: film %s is %s. %s" % (j["slug"], j["film"], s, how(j["film"]))
                )
            template(j["film"], j["slug"], j.get("spec") or {}, j.get("tests") or [])
        except Exception:  # noqa: BLE001 -- one template's failure must not stop the others
            note(
                "- **%s**: stopped by an error:\n```\n%s\n```"
                % (j["slug"], traceback.format_exc()[-1200:])
            )
    note("\nFinished %s." % time.strftime("%Y-%m-%d %H:%M %Z"))


if __name__ == "__main__":
    main()
