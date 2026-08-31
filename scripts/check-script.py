#!/usr/bin/env python
"""Check that scripts follow this repo's conventions before they get trusted.

The AI is the only author and the only caller of everything in scripts/, and a
new script that quietly skips a convention (no _env bootstrap, no free mode, a
render nobody records) works today and costs a debugging session months later.
This is the mechanical half of that review; the judgement half lives in the
check-script skill.

What it enforces (FAIL) and what it flags (warn):
    FAIL  entry script without a module docstring
    FAIL  entry script that never imports _env, or imports third-party first
    FAIL  os.execve anywhere (spawns-not-replaces on Windows; exit code lost)
    FAIL  writing PYTHONPATH (the variable this repo spent a day exorcising)
    FAIL  an absolute machine path in a string literal (or, under --all, in a
          skill or the README) -- it is wrong everywhere but one machine
    FAIL  a platform file importing something outside the platform, or one of
          the three stdlib-only files importing anything third-party
    warn  docstring without an "Invoke as:" line
    warn  entry script without argparse
    warn  a script that encodes/uploads but has no free mode
          (--list/--plan/--dry-run/--plan-only/--frame/--card-only/--check)
    warn  a script that produces deliverables but never calls _project.record
    warn  backslashes in path literals (the ass filter eats them)
    warn  script not mentioned in README.md

Known deliberate exceptions are listed in EXCEPTIONS with the reason printed,
so a skipped check is a documented decision, not a blind spot.

Invoke as:  python scripts/check-script.py --changed     (what git sees as new)
            python scripts/check-script.py --all         (the whole corpus)
            python scripts/check-script.py scripts/x.py  (one file)
"""
import sys, os, re, ast, glob, argparse, subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import

ROOT = _env.ROOT

# checks a script is allowed to skip, each with the reason it may
EXCEPTIONS = {
    "statusline.py": {
        "env": "status-line reader; must NOT import _env -- a re-exec per "
               "refresh would spawn a subprocess every second",
        "argparse": "the status line feeds it JSON on stdin; it takes no flags",
    },
    "render-status.py": {
        "env": "stdlib on purpose: it needs nothing from the venv, and a "
               "dependency-free watch tool starts instantly",
        "argparse": "one job, no options: print what is rendering",
    },
    "name-label.py": {
        "record": "standalone --video burn is the lost-source fallback; the "
                  "pipeline path records when screencast-cut.py renders",
    },
    "handle-overlay.py": {
        "record": "standalone burn is a preview path; cut-clips.py records "
                  "the real render",
        "free": "preview tool; the costed path is cut-clips --list",
    },
    "image-overlay.py": {
        "record": "standalone --video burn is the lost-source fallback, the "
                  "same bargain as name-label.py; screencast-cut.py and "
                  "cut-clips.py record when the overlay rides a real render",
    },
    "generate-voiceover.py": {
        "record": "legacy, predates the pipelines (see README ## Legacy)",
        "free": "legacy",
        "invoke": "legacy",
    },
    "transcribe-audio.py": {
        "record": "legacy, predates the pipelines (see README ## Legacy)",
        "invoke": "legacy",
    },
    "transcribe-words.py": {
        "free": "its cost IS the product (minutes of ASR); run-captions.py "
                "skips it whenever the transcript already exists",
    },
    "check-dub.py": {
        "record": "self-test harness; writes only scratch under %TEMP%",
        "argparse": "takes no arguments by design -- it is one button",
    },
    "check-multicam.py": {
        "argparse": "same bargain as check-dub.py: one button, no files, no "
                    "GPU -- it tests the round-trip arithmetic in memory",
    },
    "check-screen.py": {
        "argparse": "same bargain as check-dub.py: one button, no files, no "
                    "GPU, no OCR -- it tests the PII rules and the cut "
                    "arithmetic in memory",
    },
    "make-proxies.py": {
        "record": "a proxy is an intermediate, not a deliverable: it lives "
                  "under temp/, is regenerated from the source on demand, and "
                  "is recorded where it belongs -- as the `proxy` key on the "
                  "manifest source it was built from. screen-cut.py records "
                  "the film that comes out the other end",
    },
    "check-env.py": {
        "argparse": "takes no arguments by design -- it is one button",
        "pythonpath": "it is the doctor for that variable; reading and "
                      "repairing it is its job",
        "free": "diagnoses the spend without spending; the whole script is "
                "the free mode",
    },
}

STDLIB = set(sys.stdlib_module_names) | {"__future__"}

# The files that are *platform* rather than video: nothing here should ever
# need to know what a caption or a camera is. The boundary is enforced by
# imports -- a platform file may import the standard library, third-party
# packages, and other platform files, but nothing else from this repo. That is
# what keeps "lift the platform out" a move rather than a rewrite, and it gets
# checked at commit time instead of discovered on extraction day.
PLATFORM = {
    "_env.py": "interpreter bootstrap, .env, path and workspace resolution",
    "_progress.py": "render progress plumbing",
    "_project.py": "project record writer",
    "check-env.py": "the doctor",
    "check-script.py": "this checker",
    "project-scan.py": "project scaffolder and doctor",
    "render-status.py": "the render watch tool",
    "statusline.py": "the status line reader",
}

# These three run on every status-line refresh, or as a watch tool that must
# start instantly, so they import nothing outside the standard library -- an
# _env re-exec would spawn a subprocess per refresh. CLAUDE.md says so; this
# makes it a check rather than a promise.
STDLIB_ONLY = ("_progress.py", "render-status.py", "statusline.py")

# An absolute path belonging to one machine. Two segments are required so the
# drive-letter gotcha both this file's neighbours and the README explain
# ("ass=filename=C:/x.ass" parses as an option C) is not mistaken for one.
ABSPATH = re.compile(r"(?<![\w:])(?:[A-Za-z]:[\\/]{1,2}[\w.$-]+[\\/][\w.$-]"
                     r"|/(?:Users|home|Volumes)/\w)")

FREE_FLAGS = ("--list", "--plan", "--dry-run", "--plan-only", "--frame",
              "--card-only", "--check", "--verify", "--stop-after")

# things only a script that spends money or minutes contains
SPEND = re.compile(r"h264_nvenc|videos\(\)\s*\.insert|elevenlabs|"
                   r"MediaFileUpload|faster_whisper|WhisperModel")
DELIVER = re.compile(r'\.mp4"|\.mp4\'|shutil\.move|MediaFileUpload')


def is_entry(path):
    return not os.path.basename(path).startswith("_") \
        and path.endswith(".py")


def imports_in_order(src):
    """[(lineno, module)] for every import statement, docstrings excluded.

    The line-scanning version of this flagged the word "from" inside a
    docstring as an import, which is why it parses instead.
    """
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return None
    got = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            got.extend((node.lineno, a.name.split(".")[0])
                       for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            got.append((node.lineno, node.module.split(".")[0]))
    return sorted(got)


def repo_modules():
    """Every module name that resolves to a file in scripts/.

    Hyphenated names are here too: they cannot be imported with a plain import
    statement, so the scripts reach them through import_module("image-overlay"),
    which the import walker above cannot see.
    """
    return {os.path.basename(p)[:-3]
            for p in glob.glob(os.path.join(ROOT, "scripts", "*.py"))}


def dynamic_imports(src):
    """Modules pulled in by import_module("..."), as calls and not as text.

    The regex version of this flagged the example in repo_modules()' own
    docstring, which is the same lesson imports_in_order() learned.
    """
    got = set()
    for node in ast.walk(ast.parse(src)):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        fn = node.func
        name = fn.attr if isinstance(fn, ast.Attribute) else \
            fn.id if isinstance(fn, ast.Name) else None
        if name == "import_module" and isinstance(node.args[0], ast.Constant) \
                and isinstance(node.args[0].value, str):
            got.add(node.args[0].value)
    return got


def abspath_hits(text, in_strings_only=False):
    """[(lineno, excerpt)] for absolute machine paths.

    For Python the search is confined to string literals, because the comment
    explaining the drive-letter trap is not itself a hardcoded path.
    """
    hits = []
    if in_strings_only:
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                    and ABSPATH.search(node.value):
                hits.append((node.lineno, node.value.strip()[:70]))
    else:
        for i, line in enumerate(text.splitlines(), 1):
            if ABSPATH.search(line):
                hits.append((i, line.strip()[:70]))
    return hits


def check(path):
    """[(level, message)] for one script."""
    base = os.path.basename(path)
    exc = EXCEPTIONS.get(base, {})
    src = open(path, encoding="utf-8").read()
    out = []

    def skip(name):
        if name in exc:
            out.append(("note", "%s check waived: %s" % (name, exc[name])))
            return True
        return False

    entry = is_entry(path)
    imports = imports_in_order(src)
    if imports is None:
        return [("FAIL", "does not parse")]
    if entry:
        doc = ast.get_docstring(ast.parse(src))
        if not doc:
            out.append(("FAIL", "no module docstring -- the docstring is the "
                                "spec the next session reads first"))
        elif "Invoke as" not in doc and not skip("invoke"):
            out.append(("warn", 'docstring has no "Invoke as:" line'))

        if not skip("env"):
            env_at = next((ln for ln, mod in imports if mod == "_env"), None)
            if env_at is None:
                out.append(("FAIL", "never imports _env -- it will run on the "
                                    "wrong interpreter with a poisoned path"))
            else:
                for ln, mod in imports:
                    if ln >= env_at:
                        break
                    if mod not in STDLIB and not mod.startswith("_"):
                        out.append(("FAIL", "imports %r before _env -- the "
                                            "re-exec must come first" % mod))
                        break
        elif any(mod == "_env" for _, mod in imports):
            out.append(("warn", "imports _env despite the waiver -- check "
                                "which is stale, the code or the exception"))

        if "argparse" not in src and not skip("argparse"):
            out.append(("warn", "no argparse -- even one-job scripts take "
                                "--help here"))

        if SPEND.search(src) and not skip("free"):
            if not any(f in src for f in FREE_FLAGS):
                out.append(("warn", "encodes or spends but ships no free mode "
                                    "(--list/--plan/--dry-run/...) -- a new "
                                    "tool is not finished until you can ask "
                                    "it what a choice costs"))

        if DELIVER.search(src) and "_project" not in src and not skip("record"):
            out.append(("warn", "looks like it produces a deliverable but "
                                "never calls _project.record() -- the render "
                                "will be invisible to the next session"))

    if re.search(r"os\.execve\s*\(", src):
        out.append(("FAIL", "os.execve spawns-not-replaces on Windows; use "
                            "subprocess.run + sys.exit(rc)"))
    if re.search(r'environ\[\s*.PYTHONPATH.\s*\]\s*=', src) \
            and not skip("pythonpath"):
        out.append(("FAIL", "writes PYTHONPATH -- see CLAUDE.md for the day "
                            "that variable cost"))
    for ln, excerpt in abspath_hits(src, in_strings_only=True):
        out.append(("FAIL", "line %d hardcodes an absolute path (%s) -- it is "
                            "wrong on every machine but one; resolve it "
                            "through _env.resolve() or _env.workspace()"
                            % (ln, excerpt)))

    if base in PLATFORM:
        local = {m for _, m in imports}
        local |= dynamic_imports(src)
        known = repo_modules()
        strays = sorted(m for m in local
                        if (m in known or m.replace("_", "-") in known)
                        and m + ".py" not in PLATFORM)
        if strays:
            out.append(("FAIL", "platform file (%s) imports %s from outside "
                                "the platform -- the platform must not depend "
                                "on the video pipeline, or lifting it out "
                                "stops being a move and becomes a rewrite"
                                % (PLATFORM[base], ", ".join(strays))))
        if base in STDLIB_ONLY:
            third = sorted({m for _, m in imports
                            if m not in STDLIB and not m.startswith("_")})
            if third:
                out.append(("FAIL", "%s must be stdlib-only but imports %s -- "
                                    "it runs on every refresh, and anything "
                                    "needing the venv would re-exec a "
                                    "subprocess each time"
                                    % (base, ", ".join(third))))

    if re.search(r'"(?:temp|outputs|projects|sources|audio|transcripts)\\\\',
                 src):
        out.append(("warn", "backslash in a path literal -- the ass filter "
                            "eats them; forward slashes everywhere"))

    readme = open(os.path.join(ROOT, "README.md"), encoding="utf-8").read()
    if entry and base not in readme:
        out.append(("warn", "not mentioned in README.md -- the SDK contract "
                            "says the change is not done until the docs say "
                            "what the code does"))
    return out


def changed_scripts():
    p = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT,
                       capture_output=True, text=True)
    got = []
    for line in p.stdout.splitlines():
        f = line[3:].split(" -> ")[-1].strip().strip('"')
        if f.startswith("scripts/") and f.endswith(".py"):
            got.append(os.path.join(ROOT, f))
    return got


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("paths", nargs="*", help="specific scripts to check")
    ap.add_argument("--all", action="store_true", help="the whole corpus")
    ap.add_argument("--changed", action="store_true",
                    help="scripts git sees as modified or untracked")
    ap.add_argument("--strict", action="store_true",
                    help="exit nonzero on warns too")
    args = ap.parse_args()

    if args.all:
        paths = sorted(glob.glob(os.path.join(ROOT, "scripts", "*.py")))
    elif args.paths:
        paths = [os.path.abspath(p) for p in args.paths]
    else:
        paths = changed_scripts()
        if not paths:
            print("nothing changed under scripts/ -- use --all for the corpus")
            return

    fails = warns = 0
    for p in paths:
        found = check(p)
        base = os.path.basename(p)
        if not [x for x in found if x[0] != "note"]:
            print("ok    %s" % base)
        for level, msg in found:
            if level == "FAIL":
                fails += 1
            elif level == "warn":
                warns += 1
            print("%-5s %s: %s" % (level, base, msg))
    if args.all:
        # The skills are read by an agent on somebody else's machine, so an
        # absolute path there is the same bug as one in a script -- and it is
        # the form the repo actually shipped ten of.
        docs = sorted(glob.glob(os.path.join(ROOT, ".claude", "skills", "*",
                                             "SKILL.md")))
        docs += [os.path.join(ROOT, f) for f in ("README.md", "CLAUDE.md")]
        for d in docs:
            if not os.path.exists(d):
                continue
            for ln, excerpt in abspath_hits(open(d, encoding="utf-8").read()):
                fails += 1
                print("FAIL  %s:%d: absolute path (%s) -- a skill runs on "
                      "machines that are not this one"
                      % (os.path.relpath(d, ROOT).replace("\\", "/"), ln,
                         excerpt))
        print("ok    %d skills and docs carry no absolute paths" % len(docs))

    print("\n%d checked, %d FAIL, %d warn" % (len(paths), fails, warns))
    if fails or (args.strict and warns):
        sys.exit(1)


if __name__ == "__main__":
    main()
