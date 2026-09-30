#!/usr/bin/env python
"""What keeps one film out of another's way, checked without Claude: python studio/test_isolation.py

    names      a painting or an instrument can never name a path (the studio's check, and the
               scripts' own)
    the gate   the studio's tools refuse to run on a film whose files are wrong
    secrets    each step sees only the keys it needs; the render and the mix see none
    the page   a film's code, in the renderer, reaches neither the network, nor another
               film's render, nor the studio
    processes  a step's whole tree dies with it, on a cancel and on a timeout
    cgroups    on Linux under systemd (the VM), also a grandchild that left the process group,
               and a step past its memory cap

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
    expect(
        "the voice's takes are scored by the service, and only the voice is told to",
        voice.get("SKETCH_SCORER") == procs.SCORER
        and "SKETCH_SCORER" not in render
        and ("OPENROUTER_API_KEY" in voice) == bool(procs.SECRETS.get("OPENROUTER_API_KEY")),
    )
    os.environ["STUDIO_SCORER"] = "local"
    try:
        expect(
            "STUDIO_SCORER=local puts Whisper back",
            "SKETCH_SCORER" not in procs.step_env(D, "voice"),
        )
    finally:
        os.environ.pop("STUDIO_SCORER")
    expect("TEMP is inside the film", render["TEMP"].startswith(D.dir))

    # a person's own ElevenLabs voice: its voice step gets the relay's pass and none of our voice
    # keys; the pass is in no record; and whatever a step prints, a secret it was given (the pass
    # among them) comes back redacted -- to Claude, the film's events and the logs alike
    grant = "Gq7" * 14 + "x"
    O = films.Film.create(
        "an own voice",
        5,
        "drawn",
        narrator={
            "source": "elevenlabs",
            "voice": "a1B2c3D4e5F6g7H8i9J0",
            "model": "eleven_v3",
            "jobs": 2,
            "chars": 900,
            "grant": grant,
        },
    )
    own = procs.step_env(O, "voice")
    expect(
        "an own-voice film's voice step gets the relay and its pass, and no voice key of ours",
        own.get("ELEVENLABS_GRANT") == grant
        and own.get("ELEVENLABS_FILM") == O.id
        and not any(
            k in own for k in ("GEMINI_API_KEY", "ELEVENLABS_API_KEY", "GOOGLE_SERVICE_ACCOUNT_KEY")
        ),
    )
    kept_files = []
    for root, _, names in os.walk(O.dir):
        for n in names:
            with open(os.path.join(root, n), "rb") as fh:
                if grant.encode() in fh.read():
                    kept_files.append(os.path.relpath(os.path.join(root, n), O.dir))
    expect(
        "the pass is kept in temp/voice.json only (%s)" % kept_files,
        kept_files == [os.path.join("temp", "voice.json")],
    )
    leak = (
        "import os; print('grant=' + os.environ['ELEVENLABS_GRANT']); "
        "print('key=' + os.environ.get('OPENROUTER_API_KEY', 'none'))"
    )
    code, tail = await procs.run([sys.executable, "-c", leak], O.dir, own, 60)
    expect(
        "a step that prints its pass and a key: both redacted in what comes back (%s)" % tail,
        code == 0
        and tail[0] == "grant=[redacted]"
        and (tail[1] == "key=none" or tail[1] == "key=[redacted]"),
    )

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

    # ------------------------------------------------- cgroups (Linux under systemd: the VM)
    if procs.cgroup_root():
        # a grandchild in a session of its own is out of the step's process group -- the cgroup
        # still has it
        pids = []

        def on(line, pids=pids):
            if line.startswith("pids"):
                pids.extend(int(x) for x in line.split()[1:])

        escape = CHILD.replace('time.sleep(120)"])', 'time.sleep(120)"], start_new_session=True)')
        task = asyncio.create_task(
            procs.run([sys.executable, "-c", escape], D.dir, procs.step_env(D), 60, on)
        )
        for _ in range(100):
            if len(pids) >= 2:
                break
            await asyncio.sleep(0.1)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        await asyncio.sleep(0.5)
        expect(
            "a cancel takes a grandchild that left the process group %s" % pids,
            len(pids) == 2 and not any(_gpulock.alive(p) for p in pids),
        )
        was = os.environ.get("STUDIO_FILM_MEM_GB")
        os.environ["STUDIO_FILM_MEM_GB"] = "0.25"
        try:
            hog = "b = b'x' * (1 << 30); print('survived', flush=True)"
            code, tail = await procs.run([sys.executable, "-c", hog], D.dir, procs.step_env(D), 60)
        finally:
            if was is None:
                os.environ.pop("STUDIO_FILM_MEM_GB")
            else:
                os.environ["STUDIO_FILM_MEM_GB"] = was
        expect(
            "a step past STUDIO_FILM_MEM_GB is killed (exit %s)" % code,
            code != 0 and "survived" not in tail,
        )
        left = [d for d in os.listdir(procs.cgroup_root()) if d.startswith("step-")]
        expect("no step cgroup is left behind %s" % left, not left)
    else:
        print("skip  cgroups: not a systemd service with a delegated cgroup")

    print("%d failed" % len(bad))
    return 1 if bad else 0


if __name__ == "__main__":
    try:
        code = asyncio.run(main())
    finally:
        shutil.rmtree(HOME, ignore_errors=True)
    sys.exit(code)
