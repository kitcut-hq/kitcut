#!/usr/bin/env python
"""A bench of films whose glitches are known, and how many of them a check finds:

    python studio/defects.py --frames            render every bench film a few times a second
    python studio/defects.py --sheets            the whole film a frame a second (motion.sheets)
    python studio/defects.py --part motion       run one check over the bench and keep its findings
    python studio/defects.py --score             the table: known glitches found, alarms on clean films

"Never adopt a detector you have not measured": three two-minute episodes shipped on 2026-10-07 with
4-8 motion glitches each (a cat through her carrier's wall, a body flipped through a sliver, the
same cat twice, a hand hanging ten seconds), were fixed by hand, and both versions were kept. The
labels are studio/bakeoff/defects.json (film, window, kind, what the owner saw); the film folders
are somebody's films and stay outside the repo, under --home (default temp/defects, or
$STUDIO_DEFECTS): each is a film's own files (sketch.json, film.js, cast/, engine/,
audio/vo/timeline.json).

A check ("part") turns a film into findings [{t0, t1, kind, text, must}], kept in
<film>/temp/findings-<part>.json. A known glitch counts as found when a finding's window comes
within PAD seconds of its own. Because a check that flags the whole film finds everything, the
table also says how much of each film a part flagged, and what it raised on the clean versions.

    parts   motion   what tools.motion() says today (still stretches, cuts): the baseline
            probe    the drawing code as it runs (sketch/probe.js): twice, cut, into, sliver, wash, jumps, pops
            review   the reviewer (review.read): a fresh Claude reading the sheets and strips
"""

import os
import re
import sys
import json
import argparse
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(KIT, "scripts"))
import agent  # noqa: E402, F401 -- imports _env first
import motion  # noqa: E402
import review  # noqa: E402

LABELS = os.path.join(HERE, "bakeoff", "defects.json")
PAD = 1.0  # seconds: a finding this near a known glitch's window has found it
PARTS = ("motion", "probe", "review")


def labels():
    with open(LABELS, encoding="utf-8") as f:
        return json.load(f)["films"]


def home_of(arg):
    return os.path.abspath(
        arg or os.environ.get("STUDIO_DEFECTS") or os.path.join(KIT, "temp", "defects")
    )


def films(home, only=None):
    """[(name, folder)] of the bench films that are both labelled and on disk."""
    out = []
    for name in labels():
        d = os.path.join(home, name)
        if (not only or name in only) and os.path.isfile(os.path.join(d, "sketch.json")):
            out.append((name, d))
    return out


def length(d):
    with open(os.path.join(d, "sketch.json"), encoding="utf-8") as f:
        return float(json.load(f)["duration"])


def render(d, times, into, extra=()):
    """sketch-render.py --stills over a film folder; raises with the script's last lines."""
    argv = [sys.executable, "-X", "utf8", os.path.join(KIT, "scripts", "sketch-render.py")]
    argv += [
        "--manifest",
        os.path.join(d, "sketch.json"),
        "--stills",
        ",".join("%g" % t for t in times),
    ]
    argv += ["--into", into, *extra]
    r = subprocess.run(
        argv, cwd=d, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if r.returncode != 0:
        raise RuntimeError((r.stdout + r.stderr)[-1500:])
    return r.stdout


def frames(d, force=False):
    """The film's frames at motion's own rate, in <film>/temp/motion (kept while film.js is older)."""
    out = os.path.join(d, "temp", "motion")
    src = max(os.path.getmtime(os.path.join(d, f)) for f in ("film.js", "sketch.json"))
    have = [f for f in os.listdir(out)] if os.path.isdir(out) else []
    if have and not force and min(os.path.getmtime(os.path.join(out, f)) for f in have) > src:
        return out, False
    for f in have:
        os.remove(os.path.join(out, f))
    render(d, motion.times(length(d)), os.path.join("temp", "motion"))
    return out, True


def said(d):
    return motion.spoken(os.path.join(d, "audio", "vo", "timeline.json"))


# ------------------------------------------------------------------ the parts
def part_motion(d):
    """Today's check: what motion.analyse says, read back as findings."""
    fr, _ = frames(d)
    text, _ = motion.analyse(fr, os.path.join(d, "outputs", "review", "motion.png"))
    out = []
    for m in re.finditer(r"Still for [\d.]+ s, from ([\d.]+) to ([\d.]+) s", text):
        out.append(
            {"t0": float(m.group(1)), "t1": float(m.group(2)), "kind": "still", "text": m.group(0)}
        )
    return out


PROBE_STEP = 0.1


def probe(d, force=False):
    """sketch/probe.js's report for a film (kept in <film>/temp/probe while film.js is older)."""
    p = os.path.join(d, "temp", "probe", "report.json")
    src = max(os.path.getmtime(os.path.join(d, f)) for f in ("film.js", "sketch.json"))
    if force or not os.path.isfile(p) or os.path.getmtime(p) < src:
        render(d, [0], os.path.join("temp", "probe"), ["--probe", "%g" % PROBE_STEP])
    with open(p, encoding="utf-8") as f:
        return json.load(f).get("probe") or {}


def part_probe(d):
    """The drawing code as it runs: motion.events() over sketch/probe.js's report."""
    return motion.events(probe(d, force=True))


def view_of(d):
    """A bench film as review.read() takes one: its facts, and how to lay it out and look closer."""
    import asyncio  # noqa: PLC0415

    import tools  # noqa: PLC0415

    words = said(d)
    out_dir = os.path.join(d, "outputs", "review")

    async def sheets():
        fr, _ = await asyncio.to_thread(frames, d)
        return await asyncio.to_thread(motion.sheets, fr, out_dir, words)

    async def strips(want):
        n = length(d)
        groups = [tools.strip_times(t, 0, n - 0.02) for t, _ in want]
        every = sorted({x for g in groups for x in g})
        into = os.path.join(d, "temp", "strip")
        for f in os.listdir(into) if os.path.isdir(into) else []:
            os.remove(os.path.join(into, f))
        await asyncio.to_thread(render, d, every, os.path.join("temp", "strip"))
        return await asyncio.to_thread(
            tools.strips_of, into, out_dir, [t for t, _ in want], groups, words
        )

    return {
        "mat": review.material(d),
        "sheets": sheets,
        "events": motion.events(probe(d)),
        "strips": strips,
    }


def part_review(d, auth="login"):
    """The reviewer: review.read() on this machine's Claude login. Its findings carry `what`."""
    import asyncio  # noqa: PLC0415

    import ytdraft  # noqa: PLC0415

    async def ask(text, images):
        return await ytdraft.ask_json(
            text, images, auth, None, ytdraft.MODEL, review.EFFORT, review.system(), "review"
        )

    r = asyncio.run(review.read(view_of(d), ask, log=lambda s: print("    " + s, flush=True)))
    with open(os.path.join(d, "temp", "review-last.json"), "w", encoding="utf-8") as f:
        json.dump(r, f, indent=1, ensure_ascii=False)
    print(
        "    %d call(s), %.0f s, $%.2f, %d close-up(s)"
        % (r["calls"], r["seconds"], r["cost_usd"], len(r["closer"])),
        flush=True,
    )
    return [dict(f, text=f["what"]) for f in r["findings"]]


def run_part(part, d, tag=""):
    fn = globals().get("part_" + part)
    if fn is None:
        sys.exit("the %s part is not built yet" % part)
    found = fn(d)
    part += tag
    p = os.path.join(d, "temp", "findings-%s.json" % part)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(found, f, indent=1, ensure_ascii=False)
    return found


def findings(part, d):
    try:
        with open(os.path.join(d, "temp", "findings-%s.json" % part), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


# ------------------------------------------------------------------ the score
# what a mechanical finding can be a finding OF: one that merely happens near a glitch of
# another kind has not found it (a 22-second colour wash has something happening inside it).
# A kind not listed here (the reviewer's, in its own words) is matched by its time alone.
CAN = {
    "still": {"idle"},
    "quiet": {"idle", "untold"},
    "double": {"double"},
    "jump": {"double"},
    "pop": {"double"},
    "cut": {"through", "poke"},
    "wash": {"wash"},
    "into": {"through"},
    "sliver": {"sliver"},
    "squash": {"sliver"},
}


def hits(label, found, pad=PAD):
    return [
        f
        for f in found
        if f["t0"] - pad <= label["t1"]
        and f["t1"] + pad >= label["t0"]
        and label["kind"] in CAN.get(f.get("kind"), {label["kind"]})
    ]


def flagged(found, total):
    """Seconds of the film a part's findings cover (overlaps counted once)."""
    cover, end = 0.0, 0.0
    for a, b in sorted((max(0, f["t0"]), min(total, max(f["t1"], f["t0"] + 0.5))) for f in found):
        a = max(a, end)
        if b > a:
            cover += b - a
            end = b
    return cover


def kept(home, only=None):
    """Every part that has findings on the bench, a repeated one under each of its tags."""
    seen = []
    for _, d in films(home, only):
        t = os.path.join(d, "temp")
        for f in sorted(os.listdir(t)) if os.path.isdir(t) else []:
            m = re.fullmatch(r"findings-(.+)\.json", f)
            if m and m.group(1) not in seen:
                seen.append(m.group(1))
    return sorted(
        seen, key=lambda p: (next((i for i, q in enumerate(PARTS) if p.startswith(q)), 9), p)
    )


def score(home, parts=None, only=None):
    """{part: {found, known, by_kind, clean_alarms, clean_musts, clean_films, films: {...}}}."""
    lab, out = labels(), {}
    for part in parts or kept(home, only):
        s = {
            "found": 0,
            "known": 0,
            "by_kind": {},
            "clean_alarms": 0,
            "clean_musts": 0,
            "clean_films": 0,
            "films": {},
        }
        for name, d in films(home, only):
            found = findings(part, d)
            if found is None:
                continue
            known = lab[name].get("defects", [])
            got = [bool(hits(k, found)) for k in known]
            for k, g in zip(known, got):
                kk = s["by_kind"].setdefault(k["kind"], [0, 0])
                kk[0] += g
                kk[1] += 1
            s["found"] += sum(got)
            s["known"] += len(known)
            if lab[name].get("clean"):
                s["clean_films"] += 1
                s["clean_alarms"] += len(found)
                s["clean_musts"] += sum(1 for f in found if f.get("must"))
            s["films"][name] = {
                "found": sum(got),
                "known": len(known),
                "missed": [k["words"] for k, g in zip(known, got) if not g],
                "findings": len(found),
                "musts": sum(1 for f in found if f.get("must")),
                "flagged_s": round(flagged(found, length(d)), 1),
            }
        if s["films"]:
            out[part] = s
    return out


def table(sc):
    lines = []
    for part, s in sc.items():
        lines.append(
            "%-8s found %d of %d known glitches; on %d clean film(s): %d finding(s), %d must-fix"
            % (part, s["found"], s["known"], s["clean_films"], s["clean_alarms"], s["clean_musts"])
        )
        lines.append(
            "        by kind: "
            + ", ".join("%s %d/%d" % (k, a, b) for k, (a, b) in sorted(s["by_kind"].items()))
        )
        for name, f in s["films"].items():
            lines.append(
                "        %-8s %d/%d   %d finding(s), %d must, %.0f s flagged%s"
                % (
                    name,
                    f["found"],
                    f["known"],
                    f["findings"],
                    f["musts"],
                    f["flagged_s"],
                    ("   missed: " + "; ".join(f["missed"])) if f["missed"] else "",
                )
            )
    return "\n".join(lines) or "no findings kept yet: run --part <name> first"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument(
        "--home", help="the bench's film folders (default temp/defects, or $STUDIO_DEFECTS)"
    )
    ap.add_argument("--only", help="comma-separated bench films")
    ap.add_argument("--frames", action="store_true", help="render every film at motion's rate")
    ap.add_argument(
        "--sheets", action="store_true", help="the whole film a frame a second, into outputs/review"
    )
    ap.add_argument(
        "--part", choices=PARTS, help="run one check over the bench and keep its findings"
    )
    ap.add_argument("--score", action="store_true", help="print the table")
    ap.add_argument(
        "--tag", default="", help="with --part: keep this run's findings apart (review --tag 2)"
    )
    ap.add_argument(
        "--list",
        action="store_true",
        help="what is on the bench, and what a run would do; runs nothing",
    )
    ap.add_argument("--force", action="store_true", help="render frames again")
    a = ap.parse_args()
    home, only = home_of(a.home), set(a.only.split(",")) if a.only else None
    bench = films(home, only)
    if a.list or not (a.frames or a.sheets or a.part or a.score):
        lab = labels()
        print("bench at %s: %d of %d labelled films on disk" % (home, len(bench), len(lab)))
        for name, d in bench:
            n = len(motion.times(length(d)))
            print(
                "  %-8s %3.0f s  %s  %d known glitch(es); --frames renders %d stills (~%d s)"
                % (
                    name,
                    length(d),
                    "clean" if lab[name].get("clean") else "bad  ",
                    len(lab[name].get("defects", [])),
                    n,
                    n * 0.2,
                )
            )
        return
    for name, d in bench:
        if a.frames or a.sheets:
            _, fresh = frames(d, a.force)
            print("%s: frames %s" % (name, "rendered" if fresh else "kept"), flush=True)
        if a.sheets:
            got = motion.sheets(
                os.path.join(d, "temp", "motion"), os.path.join(d, "outputs", "review"), said(d)
            )
            print(
                "%s: %d sheet(s) in %s" % (name, len(got), os.path.join(d, "outputs", "review")),
                flush=True,
            )
        if a.part:
            print(
                "%s: %s -> %d finding(s)" % (name, a.part, len(run_part(a.part, d, a.tag))),
                flush=True,
            )
    if a.score:
        print(table(score(home, only=only)))


if __name__ == "__main__":
    main()
