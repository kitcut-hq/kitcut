#!/usr/bin/env python
"""Export the tester repo WITH its commit history, filtered so the history is
as shareable as the tree.

make-tester-repo.py copies a working tree; this one keeps the 79 commits that
show how the tooling was built. A plain clone cannot: every excluded file is
still present in the commits that added it, so the strategy docs and the
manifests quoting card fragments would ship inside the history even though
`git status` looked clean. So the history is REWRITTEN with git-filter-repo,
keeping only the allowlisted paths -- the same allowlist the tree export
uses, so neither can drift from the other -- and redacting the text that
points at what stayed behind.

    python scripts/make-tester-history.py --list       # the plan, no work
    python scripts/make-tester-history.py --out <dir>

The result is a git repo whose every commit is checked: no excluded path in
any tree, no forbidden string in any blob, no commit message mentioning what
was dropped. HEAD is then made byte-identical to what make-tester-repo.py
produces, so the two exports agree by construction rather than by review.

Push it yourself once you have looked at it -- this script never touches a
remote.

Invoke as:  python scripts/make-tester-history.py --out <dir>
"""
import sys, os, argparse, subprocess, shutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import
from importlib import import_module  # noqa: E402

_tester = import_module("make-tester-repo")   # hyphen: not importable by name

ROOT = _env.ROOT

# Paths kept across ALL of history. Built from the tree export's allowlist so
# the two cannot disagree, plus the entries history needs that a tree copy
# does not: files that were deleted or renamed along the way.
HISTORY_KEEP = sorted(set(
    _tester.SHIP_DIRS + _tester.SHIP_FILES + list(_tester.SHIP_AS) + [
        ".claude/settings.json",
        "audio/.gitkeep", "outputs/.gitkeep", "sources/.gitkeep",
        "temp/.gitkeep", "transcripts/.gitkeep", "projects/.gitkeep",
    ]))

# Dropped in a second, inverting pass: they are inside a kept directory, and
# both name the excluded documents in their own constants -- which is the
# very thing the forbidden-string scan looks for. The tree export skips them
# at HEAD; history needs them gone from the commits that added them.
DROP_FROM_HISTORY = ["scripts/make-tester-repo.py",
                     "scripts/make-tester-history.py"]

# The one path under an excluded directory that may exist: an empty
# placeholder keeping the tester's own projects/ in git.
ALLOWED_EXACT = {"projects/.gitkeep"}

# Literal text redacted from every blob in history. The files these name are
# filtered out by path; what remains is prose in CLAUDE.md and the README
# pointing at them, and a table row summarising each -- which is the business
# content, not just a filename. Replacement is empty: the sentence reads fine
# without the aside, and a redaction marker would only advertise the gap.
# Redacting the FILENAME alone is not enough and that mistake shipped once in
# testing: CLAUDE.md's map gives each excluded doc a row summarising it, so
# blanking the path left "how this repo becomes a product: the audience, the
# licensed-plugin model..." sitting in history with a blank first column. The
# whole row goes, reusing the tree export's scrub strings so the two agree.
REDACT = ([row.rstrip("\n").encode() for row, _ in _tester.SCRUB_CLAUDE_MD
           if row.startswith("|")] +
          [b"`docs/product-strategy.md`", b"`docs/market-shorts-2026.md`",
           b"`docs/shorts-strategy.md`", b"`docs/shorts-gtm-playbooks.md`",
           b"`docs/claude-native-channel.md`",
           b"docs/product-strategy.md", b"docs/market-shorts-2026.md",
           b"docs/shorts-strategy.md", b"docs/shorts-gtm-playbooks.md",
           b"docs/claude-native-channel.md",
           b"(see ``).",   # leftover when the filename went first
           # Real values that lived in check-screen.py's fixtures and the
           # README until they were made synthetic. They are gone from the
           # tree; history is where they would otherwise survive.
           b"4149 4390 2701 0499", b"4149439027010499", b"4149439027010949",
           b"4441 **** **** 7789", b"2527428", b"agamanuk@gmail.com",
           b"+38 (066) 317-3125", b"+380664134978", b"066 431 4978",
           b"0939589090", b"\xd0\xa1\xd1\x82\xd1\x80\xd0\xb5\xd0\xbb\xd1"
           b"\x8c\xd1\x87\xd0\xb5\xd0\xbd\xd0\xba\xd0\xbe"])  # the recipient's surname

# Business prose that must not survive in ANY blob. This is the check that
# catches a row whose wording changed between commits -- a filename list
# cannot, because the filename is exactly what redaction removes.
BLOB_TERMS = [b"licensed-plugin", b"learning flywheel", b"go-to-market",
              b"GTM playbook", b"shorts/clipping market", b"paying ICP",
              b"customer-facing", b"logo churn",
              # the fixture values, checked the same way
              b"4149", b"2527428", b"agamanuk", b"0939589090"]

# A commit whose message mentions the business work is rewritten wholesale:
# the subject is what a reader sees in `git log`, and half a sentence about
# pricing is worse than an honest "this commit's content is not in this repo".
DROPPED_MSG = (b"Internal research\n\nThis commit's content is not part of "
               b"this repository.\n")

# Explicit, reviewed rewrites: subject substring -> the whole new message.
# Checking only the SUBJECT missed the worst one in testing -- a commit
# called "Write down how the repo becomes a product" whose BODY listed the
# distribution model, the licence mechanics and the flywheel. Messages are
# matched and replaced whole.
MSG_REPLACE = [
    (b"Price the shorts market", DROPPED_MSG),
    (b"becomes a product", DROPPED_MSG),
    (b"repeat-marketing engine", DROPPED_MSG),
    (b"which plays our install permits", DROPPED_MSG),
    (b"research the shorts-only market", DROPPED_MSG),
    (b"Build the copy of this repo a stranger can be handed",
     b"Add the quickstart, the permission allow-list and the export notes\n"
     b"\nQUICKSTART.md for a first run, .claude/settings.json with the "
     b"script\npermissions pre-allowed, and the README section describing "
     b"how this\nrepository is produced.\n"),
]

# Terms that make a message worth a second look. A commit that trips one and
# is in neither list above FAILS the build: new history must be reviewed, not
# silently shipped.
MSG_TERMS = [b"market", b"strategy", b"gtm", b"playbook", b"pricing",
             b"competitor", b"business", b"licens", b"revenue", b"monetiz",
             b"flywheel", b"customer", b"subscription"]

# Reviewed and deliberately kept: engineering commits whose wording happens
# to trip a term above.
MSG_REVIEWED = [
    b"Take a channel we want as a customer",   # the multicam round-trip test
    b"Catch the docs up with the code",        # edge-tts redistribution note
    b"Add the quickstart, the permission",     # the replacement written above
]


def git(args, cwd, check=True, capture=True):
    r = subprocess.run(["git"] + args, cwd=cwd, env=_env.clean_env(),
                       capture_output=capture, text=True)
    if check and r.returncode:
        sys.exit("git %s failed in %s\n%s" % (" ".join(args[:2]), cwd,
                                              (r.stderr or "").strip()))
    return (r.stdout or "").strip()


def filter_repo_cmd():
    """git-filter-repo lives in the venv's Scripts dir, not on PATH."""
    exe = os.path.join(os.path.dirname(_env.venv_python()), "git-filter-repo")
    for cand in (exe + ".exe", exe):
        if os.path.exists(cand):
            return [cand]
    sys.exit("git-filter-repo is not installed in .venv -- "
             "run: .venv/Scripts/python.exe -m pip install git-filter-repo")


def verify(outdir):
    """Every commit, not just HEAD: paths, blobs and messages."""
    problems = []
    revs = git(["rev-list", "--all"], outdir).split()
    for rev in revs:
        for path in git(["ls-tree", "-r", "--name-only", rev], outdir).splitlines():
            if path in ALLOWED_EXACT:
                continue
            for bad in _tester.NEVER_IN_HISTORY + DROP_FROM_HISTORY:
                if path == bad or path.startswith(bad + "/"):
                    problems.append("%s: excluded path %s" % (rev[:8], path))
    # one grep over the whole object database beats a walk per blob
    for bad in _tester.FORBIDDEN:
        hit = subprocess.run(["git", "grep", "-l", bad] + revs,
                             cwd=outdir, env=_env.clean_env(),
                             capture_output=True, text=True)
        if hit.stdout.strip():
            first = hit.stdout.strip().splitlines()[0]
            problems.append("forbidden string %r survives at %s"
                            % (bad, first[:70]))
    for bad in BLOB_TERMS:
        hit = subprocess.run(["git", "grep", "-l", bad.decode()] + revs,
                             cwd=outdir, env=_env.clean_env(),
                             capture_output=True, text=True)
        if hit.stdout.strip():
            first = hit.stdout.strip().splitlines()[0]
            problems.append("business prose %r survives at %s"
                            % (bad.decode(), first[:70]))
    # full messages, not just subjects
    for rev in revs:
        msg = git(["log", "-1", "--format=%B", rev], outdir).lower().encode()
        if any(ok.lower() in msg for ok in MSG_REVIEWED):
            continue
        for t in MSG_TERMS:
            if t in msg:
                subj = git(["log", "-1", "--format=%s", rev], outdir)
                problems.append("unreviewed message mentions %r: %s %s"
                                % (t.decode(), rev[:8], subj[:60]))
                break
    return problems, len(revs)


def build(outdir):
    if os.path.exists(outdir):
        sys.exit("refusing to build into existing %s -- delete it first"
                 % outdir)
    print("== 1. clone (local, no remote) ==")
    git(["clone", "--no-local", "--quiet", ROOT, outdir], ROOT)
    git(["remote", "remove", "origin"], outdir)

    print("== 2. filter history to the allowlist ==")
    paths = []
    for p in HISTORY_KEEP:
        paths += ["--path", p]
    repl = os.path.join(outdir, ".redact.txt")
    with open(repl, "wb") as f:
        for lit in REDACT:
            f.write(b"literal:" + lit + b"==>\n")
    msg_cb = (
        "rules = %r\n"
        "low = message.lower()\n"
        "for needle, replacement in rules:\n"
        "    if needle.lower() in low:\n"
        "        return replacement\n"
        "return message\n" % (MSG_REPLACE,))
    subprocess.run(filter_repo_cmd() + paths +
                   ["--replace-text", repl,
                    "--message-callback", msg_cb, "--force"],
                   cwd=outdir, env=_env.clean_env(), check=True)
    os.remove(repl)

    print("== 2b. drop the exporters themselves ==")
    drop = []
    for p in DROP_FROM_HISTORY:
        drop += ["--path", p]
    subprocess.run(filter_repo_cmd() + drop + ["--invert-paths", "--force"],
                   cwd=outdir, env=_env.clean_env(), check=True)

    print("== 3. make HEAD the verified tree export ==")
    for name in os.listdir(outdir):
        if name != ".git":
            p = os.path.join(outdir, name)
            shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
    _tester.build(outdir, _tester.gather())
    tree_problems = _tester.verify(outdir)
    if tree_problems:
        for p in tree_problems:
            print("FAIL  %s" % p)
        sys.exit("the tree export is not clean -- fix it before the history one")
    git(["add", "-A"], outdir)
    git(["-c", "user.name=KitCut", "-c", "user.email=noreply@kitcut.dev",
         "commit", "-q", "-m", TREE_COMMIT_MSG], outdir)


TREE_COMMIT_MSG = """KitCut tester build

The tooling as shipped: captions, shorts, dubbing, multicam and screencast
editing, driven by Claude Code. Start at QUICKSTART.md.

The history before this commit is the real one, filtered to what ships --
our own projects, footage and internal documents were removed from every
commit, so some commits are smaller than they were and a few are gone.
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", help="directory to build the filtered repo into")
    ap.add_argument("--list", action="store_true",
                    help="print the plan -- paths kept, text redacted, "
                         "commits affected -- and do nothing")
    args = ap.parse_args()

    if args.list or not args.out:
        n = git(["rev-list", "--count", "HEAD"], ROOT)
        print("history: %s commits on HEAD" % n)
        print("\nkept paths (%d):" % len(HISTORY_KEEP))
        for p in HISTORY_KEEP:
            print("  %s" % p)
        print("\nremoved from every commit (%d):" % len(_tester.NEVER_IN_HISTORY))
        for p in _tester.NEVER_IN_HISTORY:
            print("  %s" % p)
        print("\nredacted text (%d literals), messages rewritten when the "
              "subject mentions: %s" % (len(REDACT),
                                        ", ".join(t.decode() for t in MSG_TRIGGERS)))
        subj = [l for l in git(["log", "--format=%s"], ROOT).splitlines()
                if any(t.decode() in l.lower() for t in MSG_TRIGGERS)]
        print("  %d commit message(s) would be replaced:" % len(subj))
        for s in subj:
            print("    %s" % s[:72])
        if not args.out:
            print("\n(--out <dir> builds it)")
        return

    outdir = os.path.abspath(args.out)
    build(outdir)
    problems, n = verify(outdir)
    if problems:
        for p in problems[:20]:
            print("FAIL  %s" % p)
        sys.exit("history is NOT shareable -- %d problem(s)" % len(problems))
    print("\nbuilt %s: %d commits, every tree and blob checked" % (outdir, n))
    print("next: inspect `git log`, then add a remote and push")


if __name__ == "__main__":
    main()
