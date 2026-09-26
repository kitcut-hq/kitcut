#!/usr/bin/env python
"""What keeps one film out of another's way, checked without Claude: python studio/test_isolation.py

    names      a painting or an instrument can never name a path (the studio's check, and the
               scripts' own)
    the gate   the studio's tools refuse to run on a film whose files are wrong
    secrets    each step sees only the keys it needs; the render and the mix see none
    the page   a film's code, in the renderer, reaches neither the network, nor another
               film's render, nor the studio
    processes  a step's whole tree dies with it, on a cancel and on a timeout

About half a minute (it starts headless browsers).
"""

import os
import sys
import json
import shutil
import asyncio
import tempfile
from importlib import import_module

HOME = tempfile.mkdtemp(prefix="studio-test-")
os.environ["STUDIO_HOME"] = HOME
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import agent  # noqa: E402, F401 -- the secrets are loaded (and out of the environment) from here on
import film as films  # noqa: E402
import procs  # noqa: E402
import validate  # noqa: E402
from sched import Sched  # noqa: E402
from tools import ToolError, Tools  # noqa: E402

import _gpulock  # noqa: E402
import _sketch  # noqa: E402
import _sketchaudio  # noqa: E402

CHILD = r"""
import subprocess, sys, os, time
g = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
print("pids", os.getpid(), g.pid, flush=True)
time.sleep(120)
"""


def write(film, name, data):
    with open(film.path(name), "w", encoding="utf-8") as f:
        json.dump(data, f)


async def main():
    bad = []

    def expect(what, ok):
        print("%s  %s" % ("ok  " if ok else "FAIL", what))
        if not ok:
            bad.append(what)

    P = films.Film.create("a painted test", 5, "painted")
    D = films.Film.create("a drawn test", 5, "drawn")

    # ---------------------------------------------------------------- names
    for name in ("../../other/images/x", "C:/x", "Kitchen", "a b", "", "x" * 50):
        write(
            P,
            "paint.json",
            films.PAINT_PINNED | {"style": "", "images": [{"name": name, "prompt": "a cat"}]},
        )
        expect(
            "paint name %r refused by the studio" % name[:20],
            any("name" in p for p in validate.problems(P, "paint.json")),
        )
    try:
        _sketch.load(P.manifest)
        expect("paint name refused by the scripts (_sketch.load)", False)
    except ValueError:
        expect("paint name refused by the scripts (_sketch.load)", True)
    write(
        P,
        "paint.json",
        films.PAINT_PINNED
        | {
            "style": "ink",
            "images": [
                {"name": "kitchen", "prompt": "a cat"},
                {"name": "hall", "prompt": "a dog", "ref": "kitchen"},
            ],
        },
    )
    expect("good paintings pass", validate.problems(P, "paint.json") == [])

    write(D, "score.json", {"bpm": 120, "events": [{"inst": "../../../x", "notes": "0 C4 1"}]})
    expect(
        "an instrument off the General MIDI list is refused",
        any("General MIDI" in p for p in validate.problems(D, "score.json")),
    )
    try:
        _sketchaudio.sample_path("../../x", 60)
        expect("and refused by the scripts (sample_path)", False)
    except ValueError:
        expect("and refused by the scripts (sample_path)", True)
    write(
        D,
        "sfx.json",
        [
            {"t": 1, "fx": "sample", "inst": "..\\x", "note": "C5"},
            {"t": 0, "fx": "scribble", "times": list(range(100))},
            {"t": 1, "fx": "whoosh", "args": {"sec": 600}},
        ],
    )
    sfx = validate.problems(D, "sfx.json")
    expect("sfx: a bad sample, too many repeats, a 10-minute sound (%d)" % len(sfx), len(sfx) >= 3)
    write(
        D,
        "vo.json",
        {
            "tts": "gemini",
            "voice": "Nobody",
            "language": "../x",
            "lines": [{"text": "hi", "file": "C:/x.wav"}],
            "whisper": "C:/models",
        },
    )
    vo = validate.problems(D, "vo.json")
    expect("vo: unknown voice, language, line keys, foreign keys (%d)" % len(vo), len(vo) >= 4)

    # ---------------------------------------------------------------- the gate
    t = Tools(D, Sched(), lambda ev: None)
    try:
        t.gate()
        expect("the tools refuse a film with bad files", False)
    except ToolError as e:
        expect("the tools refuse a film with bad files", "Fix these first" in str(e))

    # ---------------------------------------------------------------- secrets
    kept = set(procs.SECRETS)
    expect(
        "the studio holds its keys (%d), none in its environment" % len(kept),
        kept and not any(k in os.environ for k in kept),
    )
    render = procs.step_env(D, "render")
    voice = procs.step_env(D, "voice")
    expect(
        "the render's environment has no key at all",
        not any(k in render for k in kept) and render["KITCUT_DOTENV"] == "0",
    )
    expect(
        "the voice gets the Google keys and nothing else of ours",
        {k for k in voice if k in kept} <= set(procs.NEEDS["voice"]),
    )
    expect("TEMP is inside the film", render["TEMP"].startswith(D.dir))

    # ---------------------------------------------------------------- the page
    os.environ["SKETCH_RENDER_OFFLINE"] = "1"
    R = import_module("sketch-render")
    victim = R.Session("<html><body>victim</body></html>")
    hit = []
    victim.on_frame = lambda i, b: hit.append(i)
    port = victim.server.server_address[1]
    page = """<html><body><script>
    const tries = {internet: 'https://example.com/', other: 'http://127.0.0.1:%d/done',
                   guessed: 'http://127.0.0.1:%d%sframe?i=0', studio: 'http://127.0.0.1:8765/api/health'};
    (async () => {
      const out = {};
      for (const [k, u] of Object.entries(tries)) {
        try { await fetch(u, {method: 'POST', mode: 'no-cors', body: 'x'}); out[k] = 'REACHED'; }
        catch (e) { out[k] = 'blocked'; }
      }
      await fetch('automation', {method: 'POST', body: JSON.stringify(out)});
      await fetch('done', {method: 'POST', body: ''});
    })();
    </script></body></html>""" % (port, port, victim.key)
    s = R.Session(page)
    await asyncio.to_thread(s.run, "x=1", 30, False)
    got = s.automation or {}
    expect(
        "the page reaches nothing but its own server: %s" % got,
        got and all(v == "blocked" for v in got.values()),
    )
    expect("and the other render heard nothing", not victim.done.is_set() and not hit)
    victim.server.shutdown()

    # ---------------------------------------------------------------- processes
    for mode in ("cancel", "timeout"):
        pids = []

        def on(line, pids=pids):
            if line.startswith("pids"):
                pids.extend(int(x) for x in line.split()[1:])

        task = asyncio.create_task(
            procs.run(
                [sys.executable, "-c", CHILD],
                D.dir,
                procs.step_env(D),
                3 if mode == "timeout" else 60,
                on,
            )
        )
        for _ in range(100):
            if len(pids) >= 2:
                break
            await asyncio.sleep(0.1)
        if mode == "cancel":
            task.cancel()
        try:
            await task
        except (asyncio.CancelledError, procs.StepTimeout):
            pass
        await asyncio.sleep(0.5)
        expect(
            "a %s kills the step and what it started %s" % (mode, pids),
            len(pids) == 2 and not any(_gpulock.alive(p) for p in pids),
        )

    print("%d failed" % len(bad))
    return 1 if bad else 0


if __name__ == "__main__":
    try:
        code = asyncio.run(main())
    finally:
        shutil.rmtree(HOME, ignore_errors=True)
    sys.exit(code)
