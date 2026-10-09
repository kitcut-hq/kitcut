#!/usr/bin/env python
"""Bake-off: the same prompts made by two versions of the studio, graded blind, side by side.

    python studio/bakeoff.py --set audience --plan                    what runs and roughly what it
                                                                      costs; makes nothing
    python studio/bakeoff.py --set audience --arm A --tree <checkout> make the set's films with
                                                                      that checkout's studio code
    python studio/bakeoff.py --set collage --arm painted --tree <checkout> --look painted
                                                                      every film of the arm in
                                                                      one look (two looks, one tree)
    python studio/bakeoff.py --set audience --grade                   a blind read of each film
    python studio/bakeoff.py --set audience --compare A B             the side-by-side page

A change to how films are made -- the brief (prompt.md, looks/), a limit, a tool -- is a proposal,
and this measures it before it ships. A set (studio/bakeoff/<set>.json) is a few prompts, each with
the audience it is meant for. An arm is one version of the studio: a checkout (usually a worktree
at the commit to compare against) whose own studio code makes every film of the set.

Each film is made the way a release makes one: STUDIO_REPO and STUDIO_ENV_FILE name the main
checkout (its keys, and the machine's locks shared with the served studio), and the tree gets a
models\\ junction to the main checkout's, as release.py gives a snapshot. A film lives in a home of
its own, link-only (listed false, source "bakeoff"), is not copied online, and gets no "recent
films chose" note, so the films of a set cannot steer each other. Films already made are kept:
run an arm again to finish it (--redo makes them afresh).

--grade renders eight frames spread over each finished film and has Claude read them blind -- no
prompt, no arm -- for what it is about, how much its look belongs in children's animation (0-1,
whatever the subject), how well the look fits the subject, and how professionally made it looks
(1-5 each), and whatever else the set asks ("grade_extra": "newspaper" -- does it look like a
newspaper; "legible" -- do its words read at a glance). --compare writes compare.html: per prompt, each arm's frames, choices, grade, cost and
time; and prints the tallies: per arm, the means, and how many films' look fits their subject (4
or 5 of 5). Calibrated on the Dell documentary this was built for: its googly-eyed first minutes
read childish 0.40, fits 3 -- a mild grader, so compare the arms, never one number to a bar.

Templates (studio/templates.py): a set whose prompts carry a "template" compares two ways of
making the same film from one tree, with the same words and the same attached files ("attach",
or a "form" -- a local JSON of an event's details and pictures -- written out as a prompt): --mode
template remakes the template as asked (agent.template_film), --mode prompt makes a plain film of
the same length (with the six pictures a plain film may take). --templates names the folder of
templates the films are made from (STUDIO_TEMPLATES). A set with "grade_extra": ["fidelity"]
also has each template film read beside its template's preview at the template's moments: does
it keep the template's scenes, layouts and finish (1-5)?

Results: <results>\\<set>\\<arm>\\<prompt id>\\ -- the film's home, result.json, grade\\
    <results> is STUDIO_BAKEOFF, else kitcut-studio-bakeoff beside the main checkout.

Before removing a tree that ran an arm, remove its junction on its own (cmd /c rmdir
<tree>\\models): a recursive delete through a junction empties the main checkout's models\\.
"""

import os
import re
import sys
import json
import html
import time
import base64

import argparse
import subprocess
import concurrent.futures
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.dirname(HERE)
SETS = os.path.join(HERE, "bakeoff")
FRAMES = 8  # frames per film for the blind read, spread evenly (4 x 2 on one sheet)
# a film's rough price and time before a set has any of its own: the 30 s films of 2026-09-26
# (046f663) took $2.31-2.87 of Claude and 15-17 min at effort xhigh
EST_USD_PER_S, EST_MIN, EST_MIN_PER_S = 0.09, 10, 0.25

GRADER = (
    "You judge short animated films from their frames alone: no brief, no title, no sound. "
    "Answer only with the JSON object asked for."
)
# the look, not the subject: a film about revenue reads "for adults" however it is drawn (the
# Dell film's own frames scored 0.1 on "made for children"), so the question is about the drawing
GRADE_ASK = (
    "These are %d frames from one short narrated animated film, in order (left to right, then "
    "the second row). Judge how it looks. Answer with one JSON object and nothing else:\n"
    '{"subject": "what it is about, in a few words", '
    '"childish": <0-1: how much its look belongs in animation for young children, whatever '
    "its subject -- 0 = not at all, 1 = entirely>, "
    '"fits_subject": <1-5: how well the look suits the subject and its seriousness>, '
    '"professional": <1-5: how professionally made it looks>, '
    '%s"why": "one sentence"}'
)
# what a set may ask besides (its "grade_extra"): a collage look can turn every film into a
# newspaper, and a page of print can be unreadable at a glance
GRADE_EXTRA = {
    "newspaper": '"newspaper": <true or false: does it look like a newspaper -- a masthead, '
    "columns of small print, a front page>, ",
    "legible": '"legible": <1-5: how easily its words can be read at a glance>, ',
}


FIDELITY_ASK = (
    "Each row of this image holds two pairs of frames from two short motion-design films, taken "
    "at the same moments: in each pair the LEFT frame is from the original (a template) and the "
    "RIGHT frame from a remake of it made for other content -- another event, other people, logo "
    "and colours. Ignore that the content differs; that is the point of the remake. Answer with "
    "one JSON object and nothing else:\n"
    '{"fidelity": <1-5: how closely the remake keeps the original\'s scenes and their order, its '
    "layouts, its motion-design devices and its finish>, "
    '"craft": "worse" | "same" | "better" (the remake\'s finish against the original\'s), '
    '"why": "one sentence"}'
)


def grade_ask(s):
    """The grader's question for a set: the same for every set, plus what the set asks besides."""
    extra = [
        k for k in s.get("grade_extra", []) if k in GRADE_EXTRA
    ]  # fidelity is a read of its own
    return GRADE_ASK % (FRAMES, "".join(GRADE_EXTRA[k] for k in extra))


def main_checkout():
    """The repository's main working tree (a worktree's .git names it): its .env, its models\\
    and its temp\\locks are the machine's, shared with the served studio."""
    if os.environ.get("STUDIO_REPO"):
        return os.path.abspath(os.environ["STUDIO_REPO"])
    common = subprocess.run(
        ["git", "-C", KIT, "rev-parse", "--path-format=absolute", "--git-common-dir"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    return os.path.dirname(os.path.abspath(common))


def results_root(repo):
    return os.path.abspath(
        os.environ.get("STUDIO_BAKEOFF")
        or os.path.join(os.path.dirname(repo), "kitcut-studio-bakeoff")
    )


def load_set(name):
    path = os.path.join(SETS, name + ".json")
    if not os.path.isfile(path):
        have = sorted(f[:-5] for f in os.listdir(SETS) if f.endswith(".json"))
        sys.exit("no set %r; the sets: %s" % (name, ", ".join(have)))
    with open(path, encoding="utf-8") as f:
        s = json.load(f)
    ids = [p["id"] for p in s["prompts"]]
    if len(set(ids)) != len(ids):
        sys.exit("%s: prompt ids repeat" % path)
    return s


def read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(path + ".tmp", path)


def git(tree, *args):
    r = subprocess.run(["git", "-C", tree, *args], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


def arms(root, name):
    d = os.path.join(root, name)
    return (
        sorted(a for a in os.listdir(d) if os.path.isdir(os.path.join(d, a)))
        if os.path.isdir(d)
        else []
    )


def result(root, name, arm, pid):
    return read_json(os.path.join(root, name, arm, pid, "result.json"))


# ------------------------------------------------------------------ one film (a process of its own)
def worker(spec_path):
    """Make one film with the tree's own studio code. Runs in a process of its own, so the tree's
    modules (and its _env) are the ones imported -- never this file's checkout's."""
    spec = read_json(spec_path)
    tree = spec["tree"]
    os.environ.update(
        STUDIO_HOME=spec["home"],
        STUDIO_REPO=spec["repo"],
        STUDIO_ENV_FILE=os.path.join(spec["repo"], ".env"),
    )
    if spec.get("templates"):  # the templates the films are made from (templates.root)
        os.environ["STUDIO_TEMPLATES"] = spec["templates"]
    if spec.get("effort"):  # how hard the arm's author thinks (agent.EFFORT reads it)
        os.environ["STUDIO_EFFORT"] = spec["effort"]
    sys.path.insert(0, os.path.join(tree, "studio"))
    import asyncio

    import agent
    import media

    import film as films

    here = os.path.dirname(os.path.abspath(agent.__file__))
    if os.path.normcase(here) != os.path.normcase(os.path.join(tree, "studio")):
        sys.exit("imported the studio from %s, not from %s" % (here, tree))
    agent.recent_films = (
        lambda film, n=8: []
    )  # no note: the films of a set must not steer each other
    media.enabled = lambda: False  # a bake-off film stays on this machine
    if spec.get("mode") == "template":  # a remake of the template, as asked
        film = agent.template_film(
            spec["template"],
            spec["prompt"],
            spec.get("attach") or (),
            spec.get("frame"),
            listed=False,
            client="bakeoff",
            source="bakeoff",
            auth=spec["auth"],
        )
    else:
        film = films.Film.create(
            spec["prompt"],
            spec["seconds"],
            spec["look"],
            client="bakeoff",
            source="bakeoff",
            auth=spec["auth"],
            listed=False,
            **({"attachments": pictures(spec["attach"][:6])} if spec.get("attach") else {}),
        )
    print("film %s" % film.dir, flush=True)
    events = os.path.join(spec["home"], "events.log")

    def emit(ev):
        with open(events, "a", encoding="utf-8") as log:
            log.write(json.dumps(ev, ensure_ascii=False) + "\n")
        if ev.get("type") in ("stage", "fail", "error", "done"):
            print("  %s %s" % (ev["type"], ev.get("text") or ev.get("name") or ""), flush=True)

    async def go():
        await agent.save(film.id, agent.first_record(film, "bakeoff", "bakeoff"))
        return await agent.make_film(film, emit, agent.Sched(), auth=spec["auth"])

    t0 = time.time()
    asyncio.run(go())
    rec = film.record()
    # what the film was given: its capabilities too, in a tree that has them (film.CAPS)
    caps = getattr(film, "caps", None)
    brief = agent.system_prompt(spec["look"], caps) if caps else agent.system_prompt(spec["look"])
    try:
        with open(film.path("temp", "system-prompt.md"), encoding="utf-8") as f:
            used = f.read() == brief
    except OSError:
        used = None  # the film's temp\ is gone: nothing to check it against
    write_json(
        os.path.join(spec["home"], "result.json"),
        {
            "prompt_id": spec["id"],
            "arm": spec["arm"],
            "mode": spec.get("mode", "prompt"),
            "length": film.length,
            "tree": tree,
            "commit": spec["commit"],
            "dirty": spec["dirty"],
            "film": film.dir,
            "look": spec["look"],
            "effort": agent.EFFORT,
            "stages": rec.get("stages"),
            "ok": bool(rec.get("ok")),
            "error": rec.get("error"),
            "minutes": round((time.time() - t0) / 60, 1),
            "claude_cost_usd": rec.get("claude_cost_usd"),
            "cost_usd": rec.get("cost_usd"),
            "turns": rec.get("turns"),
            "direction": rec.get("direction") or film.direction(),
            "brief_is_the_trees": used,
            "made": datetime.now().isoformat(timespec="seconds"),
        },
    )
    return 0 if rec.get("ok") else 1


def pictures(paths):
    """Picture files as the uploads a plain film takes (uploads.take's metas)."""
    from PIL import Image

    out = []
    for p in paths:
        with Image.open(p) as im:
            w, h = im.size
        out.append({"kind": "image", "src": p, "ext": p.rsplit(".", 1)[-1].lower(), "w": w, "h": h})
    return out


def form_prompt(form_path, seconds, language=None):
    """An event's details (a local form.json, its pictures beside it) written out as the prompt a
    person would type, and the pictures they would attach (the logo, then the featured speakers'
    photos) -- the same for both arms."""
    form = read_json(form_path)
    base = os.path.dirname(os.path.abspath(form_path))
    d = form.get("dates") or {}
    people = form.get("speakers") or []
    featured = [x for x in people if x.get("name")][:5]
    lines = [
        "A %d-second speaker promo video for %s, %s to %s, at %s in %s."
        % (seconds, form["event_name"], d.get("from"), d.get("to"), form["venue"], form["city"]),
        "Tagline: %s." % " ".join(form.get("tagline") or []),
        "Featured speakers: %s."
        % "; ".join(
            "%s (%s, %s)" % (x["name"], x.get("role", ""), x.get("org", "")) for x in featured
        ),
        "%d more speakers in the line-up." % max(0, len(people) - len(featured)),
        "Website: %s. Button: %s." % (form["url"], form.get("cta") or "Book tickets"),
        "Brand colours: %s, %s, %s." % (form["ground"], form["accent"], form["second"]),
        "Music only, no narration. Attached: the event's logo, then the featured speakers' photos"
        " in the order above.",
    ]
    if language and language != "en":
        lines.append("Every word on screen in the event's own language (%s)." % language)
    files = [os.path.join(base, form["logo"])] + [os.path.join(base, x["photo"]) for x in featured]
    return " ".join(lines), files[:6]


# ------------------------------------------------------------------ an arm
def link_models(tree, repo):
    """The tree reaches the main checkout's models\\ (soundfonts) through a junction, as a release
    does (release.py); without it every tree would download its own instruments mid-film."""
    link = os.path.join(tree, "models")
    if os.path.normcase(os.path.abspath(tree)) == os.path.normcase(repo) or os.path.exists(link):
        return
    os.makedirs(os.path.join(repo, "models"), exist_ok=True)
    if os.name == "nt":
        r = subprocess.run(
            ["cmd", "/c", "mklink", "/J", link, os.path.join(repo, "models")],
            capture_output=True,
            text=True,
        )
        if r.returncode:
            sys.exit("could not link models\\: %s" % (r.stdout + r.stderr).strip())
    else:
        os.symlink(os.path.join(repo, "models"), link)
    print("linked %s -> %s" % (link, os.path.join(repo, "models")))


def run_arm(args, s, root, repo):
    tree = os.path.abspath(args.tree)
    if not os.path.isfile(os.path.join(tree, "studio", "agent.py")):
        sys.exit("%s has no studio\\agent.py" % tree)
    link_models(tree, repo)
    commit = git(tree, "rev-parse", "--short=12", "HEAD")
    dirty = bool(git(tree, "status", "--porcelain", "--", "studio", "sketch", "scripts"))
    todo = []
    for p in chosen(s, args.only):
        home = os.path.join(root, args.set, args.arm, p["id"])
        done = read_json(os.path.join(home, "result.json"))
        if done and done.get("ok") and not args.redo:
            print("%-16s made already (%s)" % (p["id"], done["film"]))
            continue
        if os.path.isdir(home):  # a failed or unfinished try: kept beside, never reused
            os.rename(home, "%s.old-%s" % (home, datetime.now().strftime("%H%M%S")))
        os.makedirs(home)
        spec = {
            "id": p["id"],
            "arm": args.arm,
            "tree": tree,
            "repo": repo,
            "home": home,
            "prompt": p.get("prompt", ""),
            "seconds": p.get("seconds") or s["seconds"],
            "look": args.look or p.get("look", "drawn"),
            "auth": args.auth,
            "commit": commit,
            "dirty": dirty,
            "mode": args.mode,
            **({"effort": args.effort} if args.effort else {}),
            **({"templates": os.path.abspath(args.templates)} if args.templates else {}),
        }

        def here(x):
            return x if os.path.isabs(x) else os.path.join(tree, x)

        if p.get("form"):  # an event's details: the prompt and pictures a person would send
            spec["prompt"], spec["attach"] = form_prompt(
                here(p["form"]), spec["seconds"], p.get("language")
            )
        elif p.get("attach"):
            spec["attach"] = [here(x) for x in p["attach"]]
        if p.get("template") and args.mode == "template":  # the same words, the template's film
            spec.update(template=p["template"], frame=p.get("frame"))
        write_json(os.path.join(home, "spec.json"), spec)
        todo.append(spec)
    if not todo:
        return 0
    print(
        "arm %s: %d film(s) from %s (%s%s), %d at a time"
        % (args.arm, len(todo), tree, commit, ", uncommitted changes" if dirty else "", args.jobs)
    )

    def one(spec):
        with open(os.path.join(spec["home"], "worker.log"), "w", encoding="utf-8") as out:
            code = subprocess.run(
                [
                    sys.executable,
                    os.path.abspath(__file__),
                    "--worker",
                    os.path.join(spec["home"], "spec.json"),
                ],
                stdout=out,
                stderr=subprocess.STDOUT,
                cwd=tree,
            ).returncode
        r = read_json(os.path.join(spec["home"], "result.json")) or {}
        print(
            "%-16s %s  %s min  Claude $%.2f  %s turns%s"
            % (
                spec["id"],
                "made" if r.get("ok") else "FAILED",
                r.get("minutes", "?"),
                r.get("claude_cost_usd") or 0,
                r.get("turns", "?"),
                ""
                if r.get("ok")
                else "  (%s; see worker.log)" % (r.get("error") or "exit %d" % code),
            ),
            flush=True,
        )
        return bool(r.get("ok"))

    with concurrent.futures.ThreadPoolExecutor(args.jobs) as pool:
        ok = list(pool.map(one, todo))
    return 0 if all(ok) else 1


def chosen(s, only):
    if not only:
        return s["prompts"]
    want = set(only.split(","))
    unknown = want - {p["id"] for p in s["prompts"]}
    if unknown:
        sys.exit("not in the set: %s" % ", ".join(sorted(unknown)))
    return [p for p in s["prompts"] if p["id"] in want]


# ------------------------------------------------------------------ what a run would cost
def plan(args, s, root):
    known = arms(root, args.set)
    if args.arm and args.arm not in known:
        known.append(args.arm)
    print("set %s: %d prompts, %d s each" % (args.set, len(s["prompts"]), s["seconds"]))
    print("results in %s" % os.path.join(root, args.set))
    left = 0
    for p in chosen(s, args.only):
        row = []
        for a in known:
            r = result(root, args.set, a, p["id"])
            row.append(
                "%s: %s" % (a, "made" if r and r.get("ok") else "failed" if r else "to make")
            )
            left += 0 if r and r.get("ok") else 1
        look = args.look or p.get("look", "drawn")
        print("  %-16s %-8s %s" % (p["id"], look, "   ".join(row) or "-"))
    per = [
        r
        for a in known
        for p in s["prompts"]
        if (r := result(root, args.set, a, p["id"])) and r.get("ok")
    ]
    if per:
        usd = sum(r.get("claude_cost_usd") or 0 for r in per) / len(per)
        mins = sum(r.get("minutes") or 0 for r in per) / len(per)
        basis = "this set's %d finished films" % len(per)
    else:
        usd = EST_USD_PER_S * s["seconds"]
        mins = EST_MIN + EST_MIN_PER_S * s["seconds"]
        basis = "the 30 s films of 2026-09-26"
    n = left if known else len(chosen(s, args.only)) * 2
    print(
        "\n%d film(s) to make%s: about $%.0f of Claude and %.0f min at %d at a time (%s)"
        % (
            n,
            "" if known else " for two arms",
            n * usd,
            -(-n // args.jobs) * mins,
            args.jobs,
            basis,
        )
    )
    print("--auth login runs on this machine's Claude Code login: recorded, not billed")


# ------------------------------------------------------------------ the blind read
def frames_sheet(film_dir, seconds, out, stills=False):
    """FRAMES frames spread over the finished film.mp4, tiled 4 x 2 into out. stills: drawn from
    the film's own code instead (sketch-render.py --stills), the same for every arm -- a set
    whose renders did not all finish is still read, and nothing is rendered in full."""
    from PIL import Image

    mp4 = os.path.join(film_dir, "outputs", "film.mp4")
    tmp = os.path.join(os.path.dirname(out), "frames")
    os.makedirs(tmp, exist_ok=True)
    times = [(i + 0.5) * seconds / FRAMES for i in range(FRAMES)]
    tiles = []
    if stills:
        into = os.path.join(film_dir, "temp", "grade")
        subprocess.run(
            [sys.executable, "-X", "utf8", os.path.join(KIT, "scripts", "sketch-render.py")]
            + ["--manifest", os.path.join(film_dir, "sketch.json")]
            + [
                "--stills",
                ",".join("%g" % t for t in times),
                "--into",
                os.path.join("temp", "grade"),
            ],
            cwd=film_dir,
            check=True,
            capture_output=True,
        )
        for f in sorted(os.listdir(into)):
            im = Image.open(os.path.join(into, f)).convert("RGB")
            tiles.append(im.resize((640, round(im.height * 640 / im.width)), Image.LANCZOS))
    for i, t in enumerate(times if not stills else []):
        png = os.path.join(tmp, "%02d.png" % i)
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-ss", "%.3f" % t, "-i", mp4, "-frames:v", "1"]
            + ["-vf", "scale=640:-2", png],
            check=True,
        )
        tiles.append(Image.open(png).convert("RGB"))
    w, h = tiles[0].size
    sheet = Image.new("RGB", (w * 4, h * 2), "white")
    for i, im in enumerate(tiles):
        sheet.paste(im, ((i % 4) * w, (i // 4) * h))
    sheet.save(out)


def pairs_sheet(film_dir, p, args, out):
    """The template's preview stills beside the remake's frames at the same moments: eight pairs,
    two to a row. False when the template's preview cannot be found."""
    from PIL import Image

    rec = read_json(os.path.join(film_dir, "studio.json"), {})
    t = rec.get("template") or {}
    root = os.environ.get("STUDIO_TEMPLATES") or (
        args.templates and os.path.abspath(args.templates)
    )
    fr = (rec.get("frame") or "16:9").replace(":", "x")
    prev = os.path.join(root or "", t.get("id", ""), "v%s" % t.get("version"), "preview", fr)
    tj = read_json(os.path.join(os.path.dirname(os.path.dirname(prev)), "template.json"), {})
    moments = tj.get("moments") or []
    if not os.path.isdir(prev) or not moments:
        print("  no template preview at %s: no fidelity read" % prev)
        return False
    step = max(1, len(moments) // 8)
    moments = moments[::step][:8]
    mp4 = os.path.join(film_dir, "outputs", "film.mp4")
    tmp = os.path.join(os.path.dirname(out), "pairs")
    os.makedirs(tmp, exist_ok=True)
    tiles = []
    for m in moments:
        png = os.path.join(tmp, "%06.2f.png" % m)
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-ss", "%.3f" % m, "-i", mp4, "-frames:v", "1"]
            + ["-vf", "scale=480:-2", png],
            check=True,
        )
        left = Image.open(os.path.join(prev, "%06.2f.png" % m)).convert("RGB")
        right = Image.open(png).convert("RGB")
        left = left.resize((480, round(480 * left.height / left.width)))
        right = right.resize(left.size)
        tiles.append((left, right))
    w, h = tiles[0][0].size
    sheet = Image.new("RGB", (w * 4 + 24, h * ((len(tiles) + 1) // 2)), "white")
    for i, (a, b) in enumerate(tiles):
        x, y = (i % 2) * (w * 2 + 24), (i // 2) * h
        sheet.paste(a, (x, y))
        sheet.paste(b, (x + w, y))
    sheet.save(out)
    return True


async def ask_blind(png, question):
    """Claude's read of the sheet, shown nothing but the frames."""
    import agent
    from claude_agent_sdk import (
        AssistantMessage,
        ClaudeAgentOptions,
        ResultMessage,
        TextBlock,
        query,
    )

    with open(png, "rb") as f:
        data = base64.b64encode(f.read()).decode("ascii")

    async def ask():
        yield {
            "type": "user",
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": "image/png", "data": data},
                    },
                    {"type": "text", "text": question},
                ],
            },
            "parent_tool_use_id": None,
            "session_id": "bakeoff-grade",
        }

    opts = ClaudeAgentOptions(
        model=agent.MODEL,
        effort="high",
        system_prompt=GRADER,
        tools=[],
        strict_mcp_config=True,
        setting_sources=[],
        max_turns=1,
        env=agent.claude_env(None, "login"),
        cli_path=agent.claude_cli(),
    )
    text, cost, err = "", 0.0, None
    async for m in query(prompt=ask(), options=opts):
        if isinstance(m, AssistantMessage):
            text += "".join(b.text for b in m.content if isinstance(b, TextBlock))
        elif isinstance(m, ResultMessage):
            cost = m.total_cost_usd or 0.0
            err = m.result if m.is_error else None
    j = re.search(r"\{.*\}", text, re.DOTALL)
    try:
        g = json.loads(j.group(0)) if j else None
    except ValueError:
        g = None
    if not isinstance(g, dict) or err:
        raise RuntimeError("no grade: %s" % (err or text[:300]))
    return g | {"model": agent.MODEL, "cost_usd": round(cost, 4)}


def grade(args, s, root):
    import asyncio

    sys.path.insert(0, HERE)
    todo = []
    for a in arms(root, args.set):
        for p in chosen(s, args.only):
            r = result(root, args.set, a, p["id"])
            whole = r and r.get("film") and os.path.isfile(os.path.join(r["film"], "film.js"))
            if not (r and (r.get("ok") or (args.stills and whole))):
                continue
            d = os.path.join(root, args.set, a, p["id"], "grade")
            if os.path.isfile(os.path.join(d, "grade.json")) and not args.redo:
                continue
            todo.append((a, p, r, d))
    print("grading %d film(s) blind" % len(todo))
    for a, p, r, d in todo:
        sheet = os.path.join(d, "sheet.png")
        frames_sheet(
            r["film"], r.get("length") or p.get("seconds") or s["seconds"], sheet, args.stills
        )
        g = asyncio.run(ask_blind(sheet, grade_ask(s)))
        if "fidelity" in s.get("grade_extra", []) and r.get("mode") == "template":
            pairs = os.path.join(d, "pairs.png")
            if pairs_sheet(r["film"], p, args, pairs):
                g["fidelity"] = asyncio.run(ask_blind(pairs, FIDELITY_ASK))
        write_json(os.path.join(d, "grade.json"), g)
        print(
            "%-8s %-16s childish %.2f  fits %s  professional %s  (%s)"
            % (
                a,
                p["id"],
                num(g, "childish"),
                g.get("fits_subject"),
                g.get("professional"),
                g.get("subject"),
            )
        )


def num(g, key):
    try:
        return float(g.get(key))
    except (TypeError, ValueError):
        return 0.0


# ------------------------------------------------------------------ side by side
def counts(film_dir):
    """What the film used, counted (never a rule): faces and the doodle people, pops and boings."""
    js = ""
    cast = os.path.join(film_dir, "cast")
    names = sorted(os.listdir(cast)) if os.path.isdir(cast) else []
    for path in [os.path.join(film_dir, "film.js")] + [os.path.join(cast, n) for n in names]:
        try:
            with open(path, encoding="utf-8") as f:
                js += f.read()
        except OSError:
            pass
    sfx = read_json(os.path.join(film_dir, "sfx.json"), [])
    fx = [e.get("fx") for e in sfx if isinstance(e, dict)] if isinstance(sfx, list) else []
    images = os.path.join(film_dir, "images")
    webp = [n for n in os.listdir(images) if n.endswith(".webp")] if os.path.isdir(images) else []
    return {
        "faces": len(re.findall(r"\bP\.face\.(?:eyes|mouth)\b|\bface\s*:", js)),
        "kid_or_person": len(re.findall(r"\bP\.(?:kid|person)\s*\(", js)),
        "pop_boing": sum(1 for f in fx if f in ("pop", "boing")),
        "sfx": len(fx),
        # a collage film's: its cut-outs, stamps, and the newspaper under it (sketch/collage.js)
        "cutouts": len(webp),
        "stamps": js.count("SK.stamp("),
        "newsprint": "SK.newsprint(" in js,
    }


def tallies(root, name, arm, prompts):
    rows = []
    for p in prompts:
        r = result(root, name, arm, p["id"])
        g = read_json(os.path.join(root, name, arm, p["id"], "grade", "grade.json"))
        if r and r.get("ok"):
            rows.append((p, r, g))
    out = {"made": len(rows), "asked": len(prompts)}
    for label, group in (
        ("serious", [x for x in rows if not x[0].get("control")]),
        ("controls", [x for x in rows if x[0].get("control")]),
    ):
        graded = [x[2] for x in group if x[2]]
        if graded:
            out[label] = {"graded": len(graded)} | {
                k: round(sum(num(g, k) for g in graded) / len(graded), 2)
                for k in ("childish", "fits_subject", "professional")
            }
            out[label]["fit"] = sum(1 for g in graded if num(g, "fits_subject") >= 4)
            if any("legible" in g for g in graded):
                out[label]["legible"] = round(
                    sum(num(g, "legible") for g in graded) / len(graded), 2
                )
    # a newspaper where the set says one is wrong (its prompts' "newspaper_wrong")
    wrong = [x[2] for x in rows if x[0].get("newspaper_wrong") and x[2]]
    if any("newspaper" in g for g in wrong):
        out["newspaper_where_wrong"] = "%d of %d" % (
            sum(1 for g in wrong if g.get("newspaper") is True),
            len(wrong),
        )
    if rows:
        out["claude_usd"] = round(
            sum(x[1].get("claude_cost_usd") or 0 for x in rows) / len(rows), 2
        )
        out["minutes"] = round(sum(x[1].get("minutes") or 0 for x in rows) / len(rows), 1)
    return out


def compare(args, s, root):
    a, b = args.compare
    prompts = chosen(s, args.only)
    base = os.path.join(root, args.set)
    t = {x: tallies(root, args.set, x, prompts) for x in (a, b)}
    for x in (a, b):
        print("%-8s %s" % (x, json.dumps(t[x])))

    def cell(arm, p):
        r = result(root, args.set, arm, p["id"])
        if not r:
            return "<td class=none>not made</td>"
        if not r.get("ok"):
            return "<td class=none>failed: %s</td>" % html.escape(str(r.get("error")))
        d = r.get("direction") or {}
        g = read_json(os.path.join(base, arm, p["id"], "grade", "grade.json"))
        c = counts(r["film"])
        img = "%s/%s/grade/sheet.png" % (arm, p["id"])
        grade_line = (
            "childish <b>%.2f</b> &middot; fits the subject <b>%s</b>/5 &middot; professional "
            "<b>%s</b>/5 <span class=subj>(%s)</span><div class=why>%s</div>"
            % (
                num(g, "childish"),
                g.get("fits_subject"),
                g.get("professional"),
                html.escape(str(g.get("subject"))),
                html.escape(str(g.get("why"))),
            )
            if g
            else "<i>not graded</i>"
        )
        return (
            "<td><img src='%s' loading=lazy>%s<div class=facts>For: %s<br>%s %s &middot; %s, "
            "&ldquo;%s&rdquo; &middot; %s &middot; %s bpm<br>faces %d &middot; kid/person %d "
            "&middot; pop/boing %d of %d cues%s<br>Claude $%.2f &middot; %s min &middot; %s turns"
            "</div></td>"
            % (
                img,
                grade_line,
                html.escape(d.get("audience") or "-"),
                html.escape(str(d.get("style", "-"))),
                html.escape(str(d.get("ground", d.get("paint_style", "")))),
                html.escape(str(d.get("voice"))),
                html.escape(d.get("voice_style") or ""),
                html.escape(", ".join(d.get("instruments") or [])),
                d.get("bpm"),
                c["faces"],
                c["kid_or_person"],
                c["pop_boing"],
                c["sfx"],
                (
                    "<br>cut-outs %d &middot; stamps %d &middot; newsprint %s &middot; faces %s%s"
                    % (
                        c["cutouts"],
                        c["stamps"],
                        "yes" if c["newsprint"] else "no",
                        html.escape(", ".join(d.get("faces") or []) or "-"),
                        " &middot; <b>looks like a newspaper</b>"
                        if g and g.get("newspaper")
                        else "",
                    )
                    if c["cutouts"] or "faces" in d
                    else ""
                ),
                r.get("claude_cost_usd") or 0,
                r.get("minutes"),
                r.get("turns"),
            )
        )

    def summary(x):
        v = t[x]
        parts = ["%d of %d made" % (v["made"], v["asked"])]
        for k in ("serious", "controls"):
            if k in v:
                parts.append(
                    "%s: %d/%d fit their subject, childish %.2f, fits %.2f, professional %.2f"
                    % (
                        k,
                        v[k]["fit"],
                        v[k]["graded"],
                        v[k]["childish"],
                        v[k]["fits_subject"],
                        v[k]["professional"],
                    )
                )
        if "newspaper_where_wrong" in v:
            parts.append("a newspaper where one is wrong: %s" % v["newspaper_where_wrong"])
        if "claude_usd" in v:
            parts.append("Claude $%.2f and %.1f min a film" % (v["claude_usd"], v["minutes"]))
        return "<li><b>%s</b>: %s</li>" % (html.escape(x), "; ".join(parts))

    rows = "".join(
        "<tr><th colspan=2>%s%s <span>&mdash; for %s</span><div class=prompt>%s</div></th></tr>"
        "<tr>%s%s</tr>"
        % (
            html.escape(p["id"]),
            " (control)" if p.get("control") else "",
            html.escape(p["audience"]),
            html.escape(p["prompt"]),
            cell(a, p),
            cell(b, p),
        )
        for p in prompts
    )
    page = """<!doctype html><meta charset=utf-8><title>Bake-off: %(set)s</title>
<style>
body{font:14px/1.45 system-ui,sans-serif;margin:24px;color:#1d2330;background:#fbfaf7}
h1{font-size:20px;margin:0 0 4px} p.about{max-width:900px;color:#5d6677}
table{border-collapse:collapse;width:100%%;table-layout:fixed}
th{text-align:left;padding:18px 8px 6px;font-size:15px;border-top:1px solid #d8d1c5}
th span{font-weight:400;color:#5d6677} .prompt{font-weight:400;color:#5d6677;font-size:13px}
td{vertical-align:top;padding:6px 8px;width:50%%} td img{width:100%%;border:1px solid #d8d1c5}
.facts{color:#5d6677;font-size:12.5px;margin-top:4px} .why,.subj{color:#5d6677;font-style:italic}
td.none{color:#b8432e} .arms th{border:0;padding-top:4px;font-size:16px}
</style>
<h1>Bake-off: %(set)s</h1><p class=about>%(about)s</p>
<ul>%(summary)s</ul>
<table><tr class=arms><th>%(a)s</th><th>%(b)s</th></tr>%(rows)s</table>
""" % {
        "set": html.escape(args.set),
        "about": html.escape(s.get("about", "")),
        "summary": summary(a) + summary(b),
        "a": html.escape(a),
        "b": html.escape(b),
        "rows": rows,
    }
    out = os.path.join(base, "compare.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(page)
    print(out)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--set", required=True, help="a prompt set: studio/bakeoff/<set>.json")
    ap.add_argument("--plan", action="store_true", help="what would run, and its rough cost")
    ap.add_argument("--arm", help="the arm's name, e.g. before or after")
    ap.add_argument("--tree", help="the checkout whose studio code makes the arm's films")
    ap.add_argument(
        "--look",
        choices=("drawn", "painted", "collage"),
        help="make every film of the arm in this look (else each prompt's own, default drawn)",
    )
    ap.add_argument("--grade", action="store_true", help="read every finished film blind")
    ap.add_argument("--compare", nargs=2, metavar=("A", "B"), help="two arms side by side")
    ap.add_argument(
        "--stills",
        action="store_true",
        help="with --grade: read frames drawn from each film's code, not its video -- also the "
        "films whose final render failed",
    )
    ap.add_argument("--only", help="some of the set's prompt ids, comma-separated")
    ap.add_argument("--jobs", type=int, default=3, help="films made at once (default 3)")
    ap.add_argument("--auth", default="login", choices=("login", "api"))
    ap.add_argument("--redo", action="store_true", help="make or grade again what is done")
    ap.add_argument(
        "--mode",
        default="prompt",
        choices=("prompt", "template"),
        help="for a set with template forms: remake the template, or the same content as a prompt",
    )
    ap.add_argument("--templates", help="the templates folder the films are made from")
    ap.add_argument(
        "--effort",
        choices=("low", "medium", "high", "xhigh"),
        help="how hard the arm's author thinks (else the tree's agent.EFFORT): one tree, two efforts",
    )
    args = ap.parse_args()
    s = load_set(args.set)
    repo = main_checkout()
    root = results_root(repo)
    # the grader imports this checkout's agent: the machine's keys, a home of its own
    os.environ.setdefault("STUDIO_REPO", repo)
    os.environ.setdefault("STUDIO_ENV_FILE", os.path.join(repo, ".env"))
    os.environ.setdefault("STUDIO_HOME", os.path.join(root, "_grader"))
    if args.plan:
        return plan(args, s, root)
    if args.tree:
        if not args.arm:
            ap.error("--tree needs --arm")
        return run_arm(args, s, root, repo)
    if args.grade:
        return grade(args, s, root)
    if args.compare:
        return compare(args, s, root)
    ap.error("give --plan, --arm with --tree, --grade or --compare")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--worker":
        sys.exit(worker(sys.argv[2]))  # imports the tree's own studio code, its _env included
    sys.path.insert(0, os.path.join(KIT, "scripts"))
    import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import

    _env.utf8_stdio()
    sys.exit(main())
