#!/usr/bin/env python
"""Export the shareable half of this repo into a tester copy.

The dev repo cannot be invited into: it carries the business docs, every
project journal with our publish history, and manifests that quote fragments
of the very secrets the redaction pipelines exist to blur. This builds the
copy that CAN be handed out — the tooling, the skills, the reference docs —
from an allowlist, scrubs the map of references to what stayed behind, and
refuses to finish if any reference to an excluded file survives anywhere in
the copy.

    python scripts/make-tester-repo.py --list        # what ships, what never does
    python scripts/make-tester-repo.py --out <dir>   # build the copy

The copy is a working repo: QUICKSTART.md at the root (from
docs/tester-quickstart.md), .claude/settings.json from config/tester/ with
the permission allow-list pre-seeded so a first session is not forty
prompts, and empty content dirs with .gitkeep. It is not a git repo —
inspect it, then `git init` and push it yourself.

This script does not ship in the copy: its own constants name the excluded
docs, which is exactly what the reference scan hunts for.

Invoke as:  python scripts/make-tester-repo.py --out <dir>
"""
import sys, os, argparse, shutil, fnmatch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import

ROOT = _env.ROOT

# Directories copied whole (minus SKIP patterns) and single files, all
# repo-relative. Everything not named here stays behind by construction --
# an allowlist cannot leak what it never read.
# config/ is listed subdirectory by subdirectory, NOT whole: config/chapters
# holds the chapter lists of our own published videos (ids, titles, the lot),
# and config/clips + config/screencast were per-video manifests before
# projects/ existed. A blanket "config" shipped all three.
SHIP_DIRS = ["scripts", "fonts", ".claude/skills",
             "config/cards", "config/handles", "config/labels",
             "config/overlays", "config/presets"]
SHIP_FILES = [
    "requirements.txt", ".env.template", ".gitignore",
    "README.md", "CLAUDE.md",
    "config/caption-style.json", "config/elevenlabs-voices.json",
    "docs/known-issues.md", "docs/ffmpeg-recipes.md",
    "docs/karaoke-captions.md", "docs/retro-books-giveaway.md",
]
# source -> destination renames
SHIP_AS = {
    "docs/tester-quickstart.md": "QUICKSTART.md",
    "config/tester/settings.json": ".claude/settings.json",
}
# recreated empty: the tester's own work lives here
EMPTY_DIRS = ["projects", "sources", "audio", "transcripts", "outputs", "temp"]
SKIP = ["__pycache__", "*.pyc",
        # both exporters name the excluded docs in their own constants,
        # which is exactly what the forbidden-string scan hunts for
        "make-tester-repo.py", "make-tester-history.py",
        "config/tester"]  # tester/ lands via SHIP_AS, not as itself

# Strings that must not survive anywhere in the copy: the business docs stay
# behind, so nothing shipped may point a reader at them. The last three were
# deleted from the dev repo before the export existed and are here because
# HISTORY still carries them -- an export that keeps commits must scan for
# what the working tree no longer has.
FORBIDDEN = ["product-strategy", "market-shorts", "shorts-strategy",
             "shorts-gtm-playbooks", "claude-native-channel"]

# Paths that must never appear in ANY commit of a history-preserving export.
# Deleted files still live in old commits, so this list is longer than what
# a working-tree copy would need; make-tester-history.py consumes it.
NEVER_IN_HISTORY = [
    "docs/product-strategy.md", "docs/market-shorts-2026.md",
    "docs/shorts-strategy.md", "docs/shorts-gtm-playbooks.md",
    "docs/claude-native-channel.md",
    "projects", "config/chapters", "config/clips", "config/screencast",
    "config/video-specs.template.json",
]

# CLAUDE.md is the map, and the map names the excluded docs. Each entry is
# (exact old text, replacement); a pattern that stops matching is a build
# FAIL, not a silent skip, so a rewrite of CLAUDE.md cannot rot the scrub.
SCRUB_CLAUDE_MD = [
    ("a move rather than a rewrite\n(see `docs/product-strategy.md`).",
     "a move rather than a rewrite."),
    ("| `docs/product-strategy.md` | how this repo becomes a product: the "
     "audience, the licensed-plugin model, install/update/routing mechanics, "
     "the learning flywheel. Read it before designing anything "
     "customer-facing |\n", ""),
    ("| `docs/market-shorts-2026.md` | what the AI shorts/clipping market "
     "actually looks like, researched 2026-09-01 with sources: who died, who "
     "is healthy, the GTM playbooks and what each produces, who pays, and "
     "where local-first does and does not matter. Findings only, no "
     "recommendation — read it before re-arguing the shorts question from "
     "priors |\n", ""),
]

TEXT_EXT = (".md", ".py", ".json", ".txt", ".ps1", ".html", ".css", ".template")

# Regions a shipped markdown file keeps to itself: anything between these
# markers documents the dev side (this script included) and is dropped from
# the copy. An opening marker without its close is a build FAIL.
MARK_OPEN, MARK_CLOSE = "<!-- dev-only", "<!-- /dev-only -->"


def skipped(rel):
    parts = rel.replace("\\", "/")
    return any(fnmatch.fnmatch(os.path.basename(parts), pat) or
               parts == pat or parts.startswith(pat + "/")
               for pat in SKIP)


def gather():
    """[(src_rel, dst_rel)] for everything that ships."""
    out = []
    for d in SHIP_DIRS:
        base = os.path.join(ROOT, d)
        for cur, dirs, files in os.walk(base):
            rel_cur = os.path.relpath(cur, ROOT).replace("\\", "/")
            dirs[:] = [x for x in dirs if not skipped(rel_cur + "/" + x)]
            for f in files:
                rel = rel_cur + "/" + f
                if not skipped(rel):
                    out.append((rel, rel))
    for f in SHIP_FILES:
        out.append((f, f))
    for src, dst in SHIP_AS.items():
        out.append((src, dst))
    return out


def scrub_claude_md(text):
    for old, new in SCRUB_CLAUDE_MD:
        if old not in text:
            sys.exit("SCRUB FAIL: CLAUDE.md no longer contains the expected "
                     "text %r -- update SCRUB_CLAUDE_MD to match the current "
                     "map" % old[:60])
        text = text.replace(old, new)
    return text


def drop_dev_only(text, name):
    """Remove <!-- dev-only -->…<!-- /dev-only --> regions from a page."""
    while True:
        a = text.find(MARK_OPEN)
        if a < 0:
            return text
        b = text.find(MARK_CLOSE, a)
        if b < 0:
            sys.exit("SCRUB FAIL: %s opens a dev-only region and never "
                     "closes it" % name)
        text = text[:a] + text[b + len(MARK_CLOSE):]


def build(outdir, pairs):
    # .venv and .git may stay: a rebuild into a working copy is the natural
    # way to iterate, and neither is shipped by a push (.gitignore covers the
    # venv). Anything else pre-existing means an unknown state -- refuse.
    if os.path.exists(outdir):
        extra = [x for x in os.listdir(outdir) if x not in (".venv", ".git")]
        if extra:
            sys.exit("refusing to build into non-empty %s (found %s) -- "
                     "delete it first, or point --out somewhere fresh"
                     % (outdir, ", ".join(extra[:5])))
    for src_rel, dst_rel in pairs:
        src = os.path.join(ROOT, src_rel)
        dst = os.path.join(outdir, dst_rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if dst_rel.endswith(".md") or src_rel == "CLAUDE.md":
            with open(src, encoding="utf-8", newline="") as f:
                text = f.read()
            if src_rel == "CLAUDE.md":
                text = scrub_claude_md(text)
            text = drop_dev_only(text, src_rel)
            with open(dst, "w", encoding="utf-8", newline="") as f:
                f.write(text)
        else:
            shutil.copy2(src, dst)
    for d in EMPTY_DIRS:
        os.makedirs(os.path.join(outdir, d), exist_ok=True)
        open(os.path.join(outdir, d, ".gitkeep"), "w").close()


def verify(outdir):
    """The copy proves itself: nothing excluded exists, nothing points at it."""
    problems = []
    for rel in NEVER_IN_HISTORY + [".env", ".yt-oauth", "models",
                                   "scripts/make-tester-repo.py",
                                   "scripts/make-tester-history.py"]:
        p = os.path.join(outdir, rel)
        if os.path.exists(p) and (rel != "projects" or
                                  [x for x in os.listdir(p) if x != ".gitkeep"]):
            problems.append("excluded path shipped: %s" % rel)
    for cur, dirs, files in os.walk(outdir):
        dirs[:] = [x for x in dirs if x not in (".venv", ".git")]
        for f in files:
            if not f.endswith(TEXT_EXT):
                continue
            p = os.path.join(cur, f)
            try:
                text = open(p, encoding="utf-8").read()
            except UnicodeDecodeError:
                continue
            for bad in FORBIDDEN:
                if bad in text:
                    problems.append("%s mentions %r"
                                    % (os.path.relpath(p, outdir), bad))
            # a marker that survived means a region was cut short (an inner
            # literal closed it early) or never opened -- either way, prose
            # meant for the dev repo may have shipped
            if f.endswith(".md") and "dev-only" in text:
                problems.append("%s still carries a dev-only marker"
                                % os.path.relpath(p, outdir))
    # the tester's projects/ must start empty: journals are ours, not theirs
    pj = os.path.join(outdir, "projects")
    extra = [x for x in os.listdir(pj) if x != ".gitkeep"]
    if extra:
        problems.append("projects/ is not empty: %s" % ", ".join(extra))
    return problems


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", help="directory to build the copy into")
    ap.add_argument("--list", action="store_true",
                    help="print what would ship and what never does; build nothing")
    args = ap.parse_args()

    pairs = gather()
    if args.list or not args.out:
        total = 0
        for src_rel, dst_rel in sorted(pairs):
            note = "  -> " + dst_rel if dst_rel != src_rel else ""
            total += os.path.getsize(os.path.join(ROOT, src_rel))
            print("  %s%s" % (src_rel, note))
        print("\n%d files, %.1f MB; CLAUDE.md scrubbed of %d references; "
              "empty: %s" % (len(pairs), total / 1e6, len(SCRUB_CLAUDE_MD),
                             " ".join(EMPTY_DIRS)))
        print("never ships: docs/product-strategy.md docs/market-shorts-2026.md "
              "projects/* models/ .env .yt-oauth/")
        if not args.out:
            print("\n(--out <dir> builds it)")
        return

    outdir = os.path.abspath(args.out)
    build(outdir, pairs)
    problems = verify(outdir)
    if problems:
        for p in problems:
            print("FAIL  %s" % p)
        sys.exit("the copy is NOT shareable -- fix the allowlist or the scrub")
    n = 0
    for cur, dirs, fs in os.walk(outdir):
        dirs[:] = [x for x in dirs if x not in (".venv", ".git")]
        n += len(fs)
    print("built %s: %d files, verified clean of excluded references" % (outdir, n))
    print("next: git init + commit there, run its setup-python.ps1, "
          "render something small")


if __name__ == "__main__":
    main()
