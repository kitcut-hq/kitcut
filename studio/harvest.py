#!/usr/bin/env python
"""Harvest: read the films the studio made -- their code and Claude's sessions -- and find the work
Claude keeps re-doing, so it can become a library component instead of a fresh invention per film.

    python studio/harvest.py --plan --since 2026-09-28            which homes and how many films;
                                                                  reads nothing big, writes nothing
    python studio/harvest.py --pull --since 2026-09-28            the films' code and a digest of
                                                                  every session, from the VM and
                                                                  this machine's homes, into
                                                                  temp/harvest/<since>/
    python studio/harvest.py --report temp/harvest/2026-09-28     where Claude's time went, the
                                                                  tools' errors, the helpers films
                                                                  keep re-writing, what the kit is
                                                                  used for; report.md + report.json
    python studio/harvest.py --timelines temp/harvest/2026-09-28  one condensed timeline per
                                                                  session, for the reading pass

The studio already keeps the raw material (every film's folder and its Claude transcript); nothing
read it. This does, on a schedule a person keeps: pull, report, then read -- the reading pass hands
the films' code and the timelines to agents with the two briefs beside this file
(harvest/inventory.md: what each film builds; harvest/process.md: where each session's time went)
-- and the components that recur across unrelated films go into sketch/kit.js, proven with
studio/bakeoff.py before they ship. The `video-sketch` skill's "Harvest" section is the procedure.

Where films are. The VM (`--vm`, default kitcut-studio-1, through studio/deploy/vm.sh): this file
streams itself to the VM's python3 and digests there, so only code and text cross the wire (a
day's transcripts are ~200 MB, mostly the stills Claude looked at; the digest is ~2%). This
machine: STUDIO_HOME (default kitcut-studio beside the main checkout) and every bakeoff home under
STUDIO_BAKEOFF (default kitcut-studio-bakeoff). A bakeoff film's session sits in ~/.claude/projects
under its folder's mangled path, not in the home's claude\\ folder; both are read.

Stdlib only: the digest runs on a machine with no venv.
"""

import argparse
import collections
import datetime as dt
import glob
import hashlib
import io
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tarfile

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.dirname(HERE)
VM = "kitcut-studio-1"
VM_HOME = "/srv/kitcut/studio"
# what a film's folder holds that says what it is and what it built (outputs/ is renders, skipped)
FILES = [
    "film.js",
    "scenes.json",
    "sketch.json",
    "vo.json",
    "paint.json",
    "score.json",
    "sfx.json",
    "studio.json",
    "events.jsonl",
    "journal.md",
    "outputs/engine.diff",
    "audio/vo/timeline.json",  # how fast each voice really spoke (--pace)
]
CODE_DIRS = ("scenes", "cast", "engine")
ID = re.compile(r"^studio-(\d{8})-\d{6}-[a-z2-7]{6}$")
STUDIO_TOOL = "mcp__studio__"


# ------------------------------------------------------------------------------------ the digest
def _cut(s, n):
    s = s if isinstance(s, str) else json.dumps(s, ensure_ascii=False)
    return s if len(s) <= n else s[:n] + "...[%d more]" % (len(s) - n)


def digest_session(path):
    """One Claude Code transcript (JSONL) as a list of small events: prompts, Claude's words, tool
    calls with their inputs (code kept, up to 12k a field), results without their images, usage."""
    ev = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                d = json.loads(line)
            except ValueError:
                continue
            t, typ = d.get("timestamp"), d.get("type")
            if typ == "queue-operation" and d.get("content"):
                ev.append({"t": t, "k": "prompt", "s": _cut(d["content"], 20000)})
                continue
            if typ not in ("assistant", "user"):
                continue
            m = d.get("message") or {}
            c = m.get("content")
            mid = m.get("id") if typ == "assistant" else None  # the reply a block belongs to
            if isinstance(c, str):
                ev.append(
                    {"t": t, "k": "user_text" if typ == "user" else "text", "s": _cut(c, 20000)}
                )
                continue
            for b in c or []:
                bt = b.get("type")
                if bt == "thinking":
                    ev.append(
                        {"t": t, "k": "thinking", "mid": mid, "n": len(b.get("thinking") or "")}
                    )
                elif bt == "text":
                    k = "text" if typ == "assistant" else "user_text"
                    ev.append({"t": t, "k": k, "mid": mid, "s": _cut(b.get("text") or "", 6000)})
                elif bt == "tool_use":
                    inp = dict(b.get("input") or {})
                    for key in ("content", "new_string", "old_string", "command"):
                        if isinstance(inp.get(key), str):
                            inp[key + "_len"] = len(inp[key])  # the code itself is kept up to 12k
                            inp[key] = _cut(inp[key], 12000)
                    ev.append(
                        {
                            "t": t,
                            "k": "tool",
                            "mid": mid,
                            "id": b.get("id"),
                            "name": b.get("name"),
                            "input": inp,
                        }
                    )
                elif bt == "tool_result":
                    rc, img, txt = b.get("content"), 0, ""
                    if isinstance(rc, list):
                        for x in rc:
                            if x.get("type") == "image":
                                img += 1
                            elif x.get("type") == "text":
                                txt += x.get("text") or ""
                    else:
                        txt = rc or ""
                    ev.append(
                        {
                            "t": t,
                            "k": "result",
                            "id": b.get("tool_use_id"),
                            "err": bool(b.get("is_error")),
                            "img": img,
                            "s": _cut(txt, 4000),
                        }
                    )
            if typ == "assistant" and m.get("usage"):
                u = m["usage"]
                ev.append({"t": t, "k": "usage", "mid": mid, "out": u.get("output_tokens") or 0})
    return ev


def mangled(path):
    """Claude Code's folder name for a working directory: every non-alphanumeric character a dash."""
    return re.sub(r"[^A-Za-z0-9]", "-", os.path.abspath(path))


def sessions_of(home, fid):
    """The transcripts of one film: the home's own claude\\<film>\\ config folder, else the user's."""
    found = glob.glob(os.path.join(home, "claude", fid, "projects", "*", "*.jsonl"))
    if not found:
        user = os.path.join(os.path.expanduser("~"), ".claude", "projects")
        found = glob.glob(
            os.path.join(user, mangled(os.path.join(home, "projects", fid)), "*.jsonl")
        )
    return sorted(found)


def digest_home(home, since, out):
    """Every film in one studio home made on or after `since` (YYYYMMDD): its files and sessions."""
    n = 0
    pdir = os.path.join(home, "projects")
    for fid in sorted(os.listdir(pdir)) if os.path.isdir(pdir) else []:
        m = ID.match(fid)
        if not m or m.group(1) < since:
            continue
        src, dst = os.path.join(pdir, fid), os.path.join(out, fid)
        os.makedirs(dst, exist_ok=True)
        for rel in FILES:
            p = os.path.join(src, *rel.split("/"))
            if os.path.isfile(p):
                os.makedirs(os.path.dirname(os.path.join(dst, rel)), exist_ok=True)
                shutil.copy(p, os.path.join(dst, *rel.split("/")))
        for sub in CODE_DIRS:
            for p in glob.glob(os.path.join(src, sub, "*.js")):
                if sub == "engine":  # the film's engine copy: only its diff says anything
                    continue
                os.makedirs(os.path.join(dst, sub), exist_ok=True)
                shutil.copy(p, os.path.join(dst, sub, os.path.basename(p)))
        sessions = []
        for p in sessions_of(home, fid):
            ev = digest_session(p)
            sessions.append(
                {"file": os.path.basename(p), "start": ev[0]["t"] if ev else None, "events": ev}
            )
        sessions.sort(key=lambda s: s["start"] or "")
        with open(os.path.join(dst, "transcript.json"), "w", encoding="utf-8") as f:
            json.dump(sessions, f, ensure_ascii=False)
        n += 1
    return n


def local_homes(repo):
    """This machine's studio homes: STUDIO_HOME and every bakeoff film's home."""
    parent = os.path.dirname(repo)
    homes = [os.environ.get("STUDIO_HOME") or os.path.join(parent, "kitcut-studio")]
    bake = os.environ.get("STUDIO_BAKEOFF") or os.path.join(parent, "kitcut-studio-bakeoff")
    for root, dirs, _ in os.walk(bake):
        if "projects" in dirs:
            homes.append(root)
            dirs[:] = []  # a home's own folders hold no further homes
        elif root.count(os.sep) - bake.count(os.sep) >= 5:
            dirs[:] = []
    return [h for h in homes if os.path.isdir(os.path.join(h, "projects"))]


def main_checkout():
    common = subprocess.run(
        ["git", "-C", KIT, "rev-parse", "--path-format=absolute", "--git-common-dir"],
        capture_output=True,
        text=True,
    ).stdout.strip()
    return os.path.normpath(os.path.dirname(common)) if common else KIT


def vm_cmd(vm, remote):
    return ["bash", os.path.join(HERE, "deploy", "vm.sh"), "ssh", vm, remote]


def count_since(home, since):
    pdir = os.path.join(home, "projects")
    return sum(1 for f in os.listdir(pdir) if (m := ID.match(f)) and m.group(1) >= since)


def plan(args):
    since = args.since.replace("-", "")
    repo = main_checkout()
    print("films made on or after %s:" % args.since)
    if not args.no_vm:
        r = subprocess.run(
            vm_cmd(args.vm, "ls %s/projects" % VM_HOME), capture_output=True, text=True
        )
        n = sum(1 for f in r.stdout.split() if (m := ID.match(f)) and m.group(1) >= since)
        print("  VM %s: %s" % (args.vm, n if r.returncode == 0 else r.stderr.strip()[:200]))
    for h in local_homes(repo):
        n = count_since(h, since)
        if n:
            print("  %-70s %d" % (h, n))


def pull(args):
    since = args.since.replace("-", "")
    out = os.path.abspath(args.out or os.path.join(main_checkout(), "temp", "harvest", args.since))
    os.makedirs(out, exist_ok=True)
    total = 0
    if not args.no_vm:
        with open(os.path.abspath(__file__), "rb") as f:
            me = f.read()
        remote = (
            "cat > /tmp/harvest.py && rm -rf /tmp/harvest-out && "
            "python3 /tmp/harvest.py --digest %s %s /tmp/harvest-out >&2 && "
            "tar -C /tmp/harvest-out -czf - . && rm -rf /tmp/harvest-out" % (VM_HOME, since)
        )
        r = subprocess.run(vm_cmd(args.vm, remote), input=me, capture_output=True)
        if r.returncode:
            sys.exit("the VM's digest failed: %s" % r.stderr.decode(errors="replace")[-600:])
        dst = os.path.join(out, "vm")
        os.makedirs(dst, exist_ok=True)
        with tarfile.open(fileobj=io.BytesIO(r.stdout), mode="r:gz") as tf:
            tf.extractall(dst, filter="data")
        n = len([d for d in os.listdir(dst) if ID.match(d)])
        print(
            "VM %s: %d films (%s)"
            % (args.vm, n, r.stderr.decode(errors="replace").strip().splitlines()[-1])
        )
        total += n
    for h in local_homes(main_checkout()):
        if not count_since(h, since):
            continue
        tag = re.sub(r"[^A-Za-z0-9]+", "_", os.path.relpath(h, os.path.dirname(main_checkout())))
        n = digest_home(h, since, os.path.join(out, "local", tag))
        print("%s: %d films" % (h, n))
        total += n
    print("%d films -> %s" % (total, out))


# ------------------------------------------------------------------------------------ the report
def _ts(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


def film_dirs(root):
    for dirpath, dirs, _ in os.walk(root):
        for d in list(dirs):
            if ID.match(d):
                yield os.path.join(dirpath, d)
        dirs[:] = [d for d in dirs if not ID.match(d)]


def load(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def brief_key(studio):
    """Films made from the same prompt (a bakeoff arm, a remake) count once in 'how many briefs',
    and so do a template's remakes: they copy the template's code by design."""
    tpl = studio.get("template")
    if isinstance(tpl, dict) and tpl.get("id"):
        return "template:" + tpl["id"]
    if isinstance(tpl, str) and "'id':" in tpl:  # studio.json flattens nested values to strings
        m = re.search(r"'id':\s*'([^']+)'", tpl)
        return "template:" + (m.group(1) if m else tpl)
    return re.sub(r"\W+", " ", (studio.get("prompt") or "").lower()).strip()[:80] or "?"


def code_of(fdir):
    files = [os.path.join(fdir, "film.js")]
    for sub in ("scenes", "cast"):
        files += sorted(glob.glob(os.path.join(fdir, sub, "*.js")))
    return [
        (p, open(p, encoding="utf-8", errors="replace").read()) for p in files if os.path.isfile(p)
    ]


DEF = re.compile(
    r"(?:^|[;\n{}])\s*(?:"
    r"function\s+(?P<f>[A-Za-z_$][\w$]*)\s*\("
    r"|(?:const|let|var)\s+(?P<a>[A-Za-z_$][\w$]*)\s*=\s*(?:function\s*\(|\([^()]*\)\s*=>|[A-Za-z_$][\w$]*\s*=>)"
    r"|(?P<o>(?:SK\.cast|SK\.L|SK\.P|L|P)\.[A-Za-z_$][\w$]*)\s*=\s*(?:\{|function|\(|[A-Za-z_$][\w$]*\s*=>)"
    r")",
    re.M,
)
TOK = re.compile(r"[A-Za-z_$][\w$]*|\d+(?:\.\d+)?|\S")


def _past_params(src, i):
    """Index just after the parameter list that starts at the first '(' from i -- so a default
    such as `o = {}` is not taken for the body's opening brace."""
    p, b = src.find("(", i), src.find("{", i)
    if p == -1 or (b != -1 and b < p):  # an object literal (SK.cast.x = {...}) has no parameters
        return i
    depth, q = 0, p
    while q < len(src):
        ch = src[q]
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
            if depth == 0:
                return q + 1
        q += 1
    return i


def _body(src, i):
    """The definition starting at i: brace-matched, or an expression arrow to its statement's end."""
    i0, i = i, _past_params(src, i)
    j, nl, arrow = src.find("{", i), src.find("\n", i), src.find("=>", i)
    if arrow != -1 and (j == -1 or arrow < j) and (nl == -1 or arrow < nl):
        k = arrow + 2
        while k < len(src) and src[k] in " \t":
            k += 1
        if k < len(src) and src[k] != "{":
            depth, q = 0, k
            while q < len(src):
                ch = src[q]
                if ch in "([{":
                    depth += 1
                elif ch in ")]}":
                    if depth == 0:
                        break
                    depth -= 1
                elif ch in ";\n" and depth == 0:
                    break
                q += 1
            return src[i0:q]
        j = k
    if j == -1:
        return src[i0 : i + 200]
    depth, q, quote = 0, j, None
    while q < len(src):
        ch = src[q]
        if quote:
            if ch == "\\":
                q += 2
                continue
            if ch == quote:
                quote = None
        elif ch in "'\"`":
            quote = ch
        elif src.startswith("//", q):
            q = src.find("\n", q)
            if q == -1:
                break
            continue
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return src[i0 : q + 1]
        q += 1
    return src[i0:q]


def helpers(fdir, studio):
    out = []
    for p, src in code_of(fdir):
        for m in DEF.finditer(src):
            name = m.group("f") or m.group("a") or m.group("o")
            if not name:
                continue
            start = m.start() + len(m.group(0)) - len(m.group(0).lstrip(";\n{} \t"))
            body = _body(src, start)
            if len(body) >= 40:
                out.append(
                    {
                        "film": os.path.basename(fdir),
                        "brief": brief_key(studio),
                        "name": name,
                        "code": body,
                    }
                )
    return out


def near_duplicates(defs, min_briefs=3):
    """Helpers re-written across unrelated films: Jaccard >= .5 on token 5-shingles, found by min-hash
    banding (64 hashes, 16 bands of 4), clusters kept when they span min_briefs distinct prompts."""
    rnd = random.Random(1)
    salts = [rnd.getrandbits(32) for _ in range(64)]
    sh, sig = [], []
    for d in defs:
        toks = [
            "N" if t[0].isdigit() else t for t in TOK.findall(re.sub(r"//[^\n]*", "", d["code"]))
        ]
        s = {" ".join(toks[i : i + 5]) for i in range(max(1, len(toks) - 4))}
        sh.append(s)
        hs = [int(hashlib.md5(x.encode()).hexdigest()[:8], 16) for x in s]
        sig.append([min(h ^ salt for h in hs) for salt in salts])
    parent = list(range(len(defs)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    bands = collections.defaultdict(list)
    for i, sg in enumerate(sig):
        if len(defs[i]["code"]) >= 120:
            for b in range(16):
                bands[(b, tuple(sg[b * 4 : b * 4 + 4]))].append(i)
    for members in bands.values():
        if 1 < len(members) < 400:
            a = members[0]
            for b in members[1:]:
                if find(a) != find(b) and len(sh[a] & sh[b]) / max(1, len(sh[a] | sh[b])) >= 0.5:
                    parent[find(b)] = find(a)
    groups = collections.defaultdict(list)
    for i in range(len(defs)):
        groups[find(i)].append(i)
    rows = []
    for mem in groups.values():
        briefs = {defs[i]["brief"] for i in mem}
        if len(briefs) >= min_briefs:
            rows.append(
                {
                    "briefs": len(briefs),
                    "defs": len(mem),
                    "chars": sum(len(defs[i]["code"]) for i in mem),
                    "names": collections.Counter(defs[i]["name"] for i in mem).most_common(4),
                    "example": defs[mem[0]]["code"][:600],
                }
            )
    return sorted(rows, key=lambda r: (-r["briefs"], -r["chars"]))


LIB_CALL = re.compile(r"\bSK\.(K|P|L)?\.?([A-Za-z_]\w*)\s*\(")
CODE_FILE = re.compile(r"(^|/)(film\.js|scenes/[^/]+\.js|cast/[^/]+\.js|engine/[^/]+\.js)$")
LOOK_FILE = re.compile(r"outputs/review/|images/sheet|library/cast\.png")


def _kind(tools):
    """What one of Claude's replies was for, from the calls it made: the most telling one wins."""
    files = [(n, (i.get("file_path") or "").replace("\\", "/")) for n, i in tools]
    if any(n in ("Write", "Edit") and CODE_FILE.search(f) for n, f in files):
        return "code"
    names = {n.replace(STUDIO_TOOL, "") for n, _ in tools}
    if names & {"voice"} or any(f.endswith("vo.json") for n, f in files if n in ("Write", "Edit")):
        return "narration"
    if names & {"sound"} or any(
        f.endswith(("score.json", "sfx.json")) for n, f in files if n in ("Write", "Edit")
    ):
        return "sound"
    if names & {"paint", "picture", "page", "font", "template_pictures"} or any(
        f.endswith(("paint.json", "content.json")) for n, f in files if n in ("Write", "Edit")
    ):
        return "pictures"
    if names & {"stills", "motion", "check"} or any(LOOK_FILE.search(f) for _, f in files):
        return "look"
    if tools:
        return "read"
    return "words"  # a reply with no call: the closing sentence, a note


def replies(events):
    """Claude's replies in one session, each with how long it took to come (from the answer it was
    replying to, through its last block), its output tokens, what it called and the code it wrote."""
    out, cur, last_result, start = [], None, None, None
    for e in events:
        t = _ts(e.get("t"))
        if not t:
            continue
        start = start or t
        if e["k"] in ("result", "prompt", "user_text"):  # what the next reply answers
            last_result = t
            continue
        mid = e.get("mid")
        if not mid or e["k"] not in ("tool", "text", "thinking", "usage"):
            continue
        if cur is None or cur["mid"] != mid:
            cur = {
                "mid": mid,
                "from": last_result or start,
                "to": t,
                "out": 0,
                "tools": [],
                "code_chars": 0,
            }
            out.append(cur)
        cur["to"] = max(cur["to"], t)
        if e["k"] == "usage":
            cur["out"] = max(cur["out"], e.get("out") or 0)
        elif e["k"] == "tool":
            inp = e.get("input") or {}
            cur["tools"].append((e.get("name") or "?", inp))
            if e.get("name") in ("Write", "Edit") and CODE_FILE.search(
                (inp.get("file_path") or "").replace("\\", "/")
            ):
                cur["code_chars"] += (
                    inp.get("content_len")
                    or inp.get("new_string_len")
                    or len(inp.get("content") or inp.get("new_string") or "")
                )
    for r in out:
        r["secs"] = max(0.0, min(1800.0, (r["to"] - r["from"]).total_seconds()))
        r["kind"] = _kind(r["tools"])
        r["looks"] = any(n.replace(STUDIO_TOOL, "") in ("stills", "motion") for n, _ in r["tools"])
    return out


def tool_runs(events):
    """Each tool call's run time (its call to its answer), whether it failed, and what it said."""
    pending = {}
    for e in events:
        t = _ts(e.get("t"))
        if e["k"] == "tool" and t:
            pending[e.get("id")] = (e.get("name") or "?", t)
        elif e["k"] == "result" and t:
            o = pending.pop(e.get("id"), None)
            if o and 0 <= (t - o[1]).total_seconds() < 7200:
                yield o[0], (t - o[1]).total_seconds(), bool(e.get("err")), e.get("s", "")


def report(args):
    root = os.path.abspath(args.report)
    films = list(film_dirs(root))
    tool_s, tool_n, tool_err = collections.Counter(), collections.Counter(), collections.Counter()
    errs = collections.defaultdict(collections.Counter)
    phase, phase_tok = collections.Counter(), collections.Counter()
    out_tokens, code_chars, sessions_n = 0, 0, 0
    defs, briefs, looks, lib_use, kit_films = (
        [],
        set(),
        collections.Counter(),
        collections.Counter(),
        0,
    )
    claude_s, done = 0.0, 0
    for fdir in films:
        studio = load(os.path.join(fdir, "studio.json"), {}) or {}
        briefs.add(brief_key(studio))
        looks[studio.get("look") or "?"] += 1
        if studio.get("state") == "done":
            done += 1
            stages = studio.get("stages") or {}
            if isinstance(stages, str):  # studio.json flattens nested values to strings
                m = re.search(r"'claude':\s*([\d.]+)", stages)
                claude_s += float(m.group(1)) if m else 0
            else:
                claude_s += float(stages.get("claude") or 0)
        if studio.get("source") != "import":  # an imported film was written elsewhere
            defs += helpers(fdir, studio)
        src = "\n".join(s for _, s in code_of(fdir))
        used = {".".join(x for x in m.groups() if x) for m in LIB_CALL.finditer(src)}
        lib_use.update(used)
        kit_films += any(u.startswith("K.") for u in used)
        for s in load(os.path.join(fdir, "transcript.json"), []) or []:
            sessions_n += 1
            seen_look = False
            for r in replies(s["events"]):
                kind = r["kind"]
                if kind == "code":
                    kind = "code: fix" if seen_look else "code: first write"
                seen_look = seen_look or r["looks"]
                phase[kind] += r["secs"]
                phase_tok[kind] += r["out"]
                out_tokens += r["out"]
                code_chars += r["code_chars"]
            for name, secs, err, msg in tool_runs(s["events"]):
                tool_s[name] += secs
                tool_n[name] += 1
                if err:
                    tool_err[name] += 1
                    errs[name][re.sub(r"\d+(\.\d+)?", "N", msg[:110]).replace("\n", " ")] += 1
    gen = sum(phase.values())
    tools_total = sum(tool_s.values())
    dups = near_duplicates(defs)
    names = collections.defaultdict(set)
    for d in defs:
        names[re.sub(r"^(SK\.cast|SK\.L|SK\.P|L|P)\.", "", d["name"]).lower()].add(d["brief"])
    common = [
        (n, len(b)) for n, b in sorted(names.items(), key=lambda x: -len(x[1])) if len(b) >= 4
    ]
    lines = [
        "# Harvest: %s" % os.path.basename(root),
        "",
        "%d films (%d done) from %d distinct prompts; looks %s; %d sessions."
        % (len(films), done, len(briefs), dict(looks), sessions_n),
        "Claude's phase on finished films: %.1f h (studio.json stages)." % (claude_s / 3600),
        "",
        "## Where a session's time goes",
        "",
        "Claude composing its replies (thinking and writing, from the answer it replies to until its "
        "last call): **%.1f h**; the tools running: **%.1f h**." % (gen / 3600, tools_total / 3600),
        "Output tokens %d; code written %d chars (~%d tokens, %.0f%% of output -- the rest is thinking)."
        % (out_tokens, code_chars, code_chars / 3.5, 100 * code_chars / 3.5 / max(1, out_tokens)),
        "",
        "What Claude's replies were for (a reply that writes code counts as code, before anything else):",
        "",
        "| reply | time | share | output tokens |",
        "|---|---|---|---|",
    ]
    for k, v in phase.most_common():
        lines.append(
            "| %s | %.1f h | %.0f%% | %d |" % (k, v / 3600, 100 * v / max(1, gen), phase_tok[k])
        )
    lines += ["", "| tool | calls | total | avg | errors |", "|---|---|---|---|---|"]
    for k, v in tool_s.most_common(14):
        lines.append(
            "| %s | %d | %.0f s | %.1f s | %d |"
            % (k.replace(STUDIO_TOOL, "studio."), tool_n[k], v, v / tool_n[k], tool_err[k])
        )
    lines += ["", "## Tool errors, grouped", ""]
    for k, c in errs.items():
        for msg, n in c.most_common(5):
            lines.append("- %s x%d: %s" % (k.replace(STUDIO_TOOL, "studio."), n, msg))
    lines += [
        "",
        "## Helpers re-written across unrelated prompts",
        "",
        "Names defined in 4+ prompts: ",
    ]
    lines.append(", ".join("%s %d" % x for x in common[:60]))
    lines += [
        "",
        "Near-copies across 3+ prompts (template remakes and series show up here too):",
        "",
    ]
    for r in dups[:30]:
        lines.append(
            "- %d prompts, %d copies, %d chars: %s"
            % (r["briefs"], r["defs"], r["chars"], r["names"])
        )
    lines += [
        "",
        "## Library use",
        "",
        "Films calling the kit (SK.K.*): %d of %d." % (kit_films, len(films)),
        "",
    ]
    lines.append(", ".join("%s %d" % x for x in lib_use.most_common(80)))
    text = "\n".join(lines) + "\n"
    with open(os.path.join(root, "report.md"), "w", encoding="utf-8") as f:
        f.write(text)
    with open(os.path.join(root, "report.json"), "w", encoding="utf-8") as f:
        json.dump(
            {
                "films": len(films),
                "done": done,
                "briefs": len(briefs),
                "generation_s": gen,
                "tools_s": tools_total,
                "phase_s": phase,
                "phase_output_tokens": phase_tok,
                "tools": {
                    k: {"n": tool_n[k], "s": v, "errors": tool_err[k]} for k, v in tool_s.items()
                },
                "output_tokens": out_tokens,
                "code_chars": code_chars,
                "common_names": common,
                "near_duplicates": dups,
                "library_use": lib_use,
                "kit_films": kit_films,
            },
            f,
            ensure_ascii=False,
            indent=1,
        )
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(text)


PACE_FILE = os.path.join(KIT, "config", "sketch", "voice-pace.json")
PACE_MIN_LINES = 12  # a voice's own pace is used once this many of its lines were measured


def pace(args):
    """How fast the narration really comes out: words per second of speech, per language and per
    language + voice, from every recorded timeline in a pull (each film once, its final take). The
    studio's word budget and the voice tool's free estimate read the table this writes."""
    root = os.path.abspath(args.pace)
    seen, lang_w, lang_s, voice_w, voice_s, films = (
        set(),
        collections.Counter(),
        collections.Counter(),
        collections.Counter(),
        collections.Counter(),
        collections.Counter(),
    )
    nlines = collections.Counter()
    for fdir in film_dirs(root):
        fid = os.path.basename(fdir)
        tl = load(os.path.join(fdir, "audio", "vo", "timeline.json"))
        vo = load(os.path.join(fdir, "vo.json"), {}) or {}
        if fid in seen or not tl or not tl.get("lines"):
            continue
        seen.add(fid)
        lang = (vo.get("language") or "en").lower()
        for L in tl["lines"]:
            if L.get("backup_voice") or L.get("approved") or (L.get("acc") or 0) < 0.85:
                continue  # another voice, a person's own recording, or a take that went wrong
            words = len(re.findall(r"\w+", L.get("text") or ""))
            dur = float(L.get("dur") or (L.get("end", 0) - L.get("start", 0)))
            if words < 3 or dur <= 0.5 or words / dur > 6:
                continue
            voice = (
                (L.get("who") and (vo.get("cast") or {}).get(L["who"], {}).get("voice"))
                or tl.get("voice")
                or vo.get("voice")
                or "?"
            )
            lang_w[lang] += words
            lang_s[lang] += dur
            voice_w[(lang, voice)] += words
            voice_s[(lang, voice)] += dur
            nlines[(lang, voice)] += 1
            films[lang] += 0
        films[lang] += 1
    table = {
        "_measured": {
            "from": os.path.basename(root),
            "films": len(seen),
            "how": "words / seconds of speech over each line (gaps between lines not counted), "
            "takes scoring under 0.85 and backup-voice lines left out (studio/harvest.py --pace)",
        },
        "languages": {
            k: {"wps": round(lang_w[k] / lang_s[k], 2), "words": lang_w[k], "films": films[k]}
            for k in sorted(lang_w)
            if lang_s[k] >= 20
        },
        "voices": {},
    }
    for (lang, voice), w in sorted(voice_w.items()):
        if nlines[(lang, voice)] >= PACE_MIN_LINES:
            table["voices"].setdefault(lang, {})[voice] = round(w / voice_s[(lang, voice)], 2)
    print(json.dumps(table, ensure_ascii=False, indent=1))
    if args.write:
        with open(PACE_FILE, "w", encoding="utf-8") as f:
            json.dump(table, f, ensure_ascii=False, indent=1)
            f.write("\n")
        print("->", PACE_FILE)


def timelines(args):
    """One readable timeline per film: seconds, what Claude said, each tool call and the studio
    tools' answers -- what the reading pass (harvest/process.md) is given."""
    root = os.path.abspath(args.timelines)
    dst = os.path.join(root, "timelines")
    os.makedirs(dst, exist_ok=True)
    n = 0
    for fdir in film_dirs(root):
        sess = load(os.path.join(fdir, "transcript.json"), []) or []
        if not sess:
            continue
        st = load(os.path.join(fdir, "studio.json"), {}) or {}
        out = [
            "# %s  look=%s length=%s  prompt: %s"
            % (
                os.path.basename(fdir),
                st.get("look"),
                st.get("length"),
                (st.get("prompt") or "")[:400].replace("\n", " "),
            )
        ]
        t0 = None
        for s in sess:
            out.append("## session %s" % s["file"][:8])
            names = {}
            for e in s["events"]:
                t = _ts(e.get("t"))
                if not t:
                    continue
                t0 = t0 or t
                at = "%6.0fs" % (t - t0).total_seconds()
                k = e["k"]
                if k in ("prompt", "user_text", "text"):
                    tag = {"prompt": "PROMPT", "user_text": "USER", "text": "SAY"}[k]
                    out.append(
                        "%s %s %s"
                        % (at, tag, e["s"][: 600 if k == "prompt" else 500].replace("\n", " | "))
                    )
                elif k == "tool":
                    i, nm = e.get("input") or {}, (e["name"] or "?").replace(STUDIO_TOOL, "studio.")
                    names[e["id"]] = nm
                    fp = (i.get("file_path") or "").replace("\\", "/").split("/projects/")[-1]
                    fp = fp.split("/", 1)[1] if fp.startswith("studio-") and "/" in fp else fp
                    if nm == "Edit":
                        new = i.get("new_string") or ""
                        d = "%s  -%d +%d  %s" % (
                            fp,
                            len(i.get("old_string") or ""),
                            len(new),
                            new[:160].replace("\n", " "),
                        )
                    elif nm == "Write":
                        d = "%s  %d chars" % (fp, len(i.get("content") or ""))
                    elif nm == "Read":
                        d = fp
                    else:
                        d = json.dumps(i, ensure_ascii=False)[:200]
                    out.append("%s TOOL %s %s" % (at, nm, d))
                elif k == "result":
                    nm = names.get(e.get("id"), "?")
                    if nm in ("Read", "Write", "Edit") and not e.get("err"):
                        continue
                    err = " ERR" if e.get("err") else ""
                    out.append(
                        "%s RESULT %s%s img=%d %s"
                        % (at, nm, err, e.get("img", 0), e["s"][:350].replace("\n", " | "))
                    )
        with open(os.path.join(dst, os.path.basename(fdir) + ".txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(out))
        n += 1
    print("%d timelines -> %s" % (n, dst))


def main():
    ap = argparse.ArgumentParser(
        description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter
    )
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument(
        "--plan", action="store_true", help="where the films are and how many; reads nothing big"
    )
    g.add_argument("--pull", action="store_true", help="digest the films into --out")
    g.add_argument("--report", metavar="DIR", help="the report over a pulled harvest")
    g.add_argument(
        "--timelines", metavar="DIR", help="condensed session timelines for the reading pass"
    )
    g.add_argument(
        "--pace", metavar="DIR", help="how fast each voice speaks, from a pull's timelines"
    )
    g.add_argument("--digest", nargs=3, metavar=("HOME", "SINCE", "OUT"), help=argparse.SUPPRESS)
    ap.add_argument(
        "--since",
        default=(dt.date.today() - dt.timedelta(days=3)).isoformat(),
        help="YYYY-MM-DD (default: three days ago)",
    )
    ap.add_argument("--vm", default=VM, help="the studio VM (default %(default)s)")
    ap.add_argument("--no-vm", action="store_true", help="this machine's homes only")
    ap.add_argument(
        "--out", help="where --pull writes (default temp/harvest/<since> in the main checkout)"
    )
    ap.add_argument(
        "--write", action="store_true", help="--pace: write config/sketch/voice-pace.json"
    )
    args = ap.parse_args()
    if args.digest:  # on the studio host: stdlib only, no venv
        home, since, out = args.digest
        print("%d films" % digest_home(home, since.replace("-", ""), out))
    elif args.plan:
        plan(args)
    elif args.pull:
        pull(args)
    elif args.report:
        report(args)
    elif args.pace:
        pace(args)
    else:
        timelines(args)


if __name__ == "__main__":
    main()
