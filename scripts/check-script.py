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
    "check-env.py": {
        "argparse": "takes no arguments by design -- it is one button",
        "pythonpath": "it is the doctor for that variable; reading and "
                      "repairing it is its job",
        "free": "diagnoses the spend without spending; the whole script is "
                "the free mode",
    },
}

STDLIB = set(sys.stdlib_module_names) | {"__future__"}

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
    print("\n%d checked, %d FAIL, %d warn" % (len(paths), fails, warns))
    if fails or (args.strict and warns):
        sys.exit(1)


if __name__ == "__main__":
    main()
