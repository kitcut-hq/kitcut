"""Shared plumbing for the sketch-film scripts (sketch-vo, sketch-audio, sketch-render).

A sketch film is one manifest, `projects/<id>/sketch.json`, next to the film's own code
(`film.js`), score (`score.json`) and sound cues (`sfx.json`). This module loads it, resolves
its paths, times every stage into the project's run log (`_runlog`), and holds the small
formats the three scripts hand each other: float WAV, the VO timeline, and captions.

Not an entry script: imported by the sketch-*.py scripts after `_env`.
"""

import json
import os
import re
import struct
import subprocess
import time

import numpy as np

import _env
import _project
import _runlog

SR = 48000
# A name that becomes part of a file path (a painting, an instrument): a plain word, so nothing
# a film's author writes can point outside the film's own folders
SAFE_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,40}$")


def safe_name(name, what="name"):
    """The name, if it is one a path may be built from; else a ValueError saying why."""
    if not isinstance(name, str) or not SAFE_NAME.match(name):
        raise ValueError(
            "%s %r: use lowercase letters, digits, - and _ (at most 41, starting with a letter "
            "or digit)" % (what, name)
        )
    return name


# ------------------------------------------------------------------ manifest
def load(path):
    """Read a sketch manifest and resolve everything it names relative to its folder."""
    path = _env.resolve(path)
    with open(path, encoding="utf-8") as f:
        m = json.load(f)
    d = os.path.dirname(path)
    m["_path"], m["_dir"] = path, d
    m["_id"] = _project.project_id(m, path)
    for sub in ("audio", "outputs", "temp"):
        m["_" + sub] = os.path.join(d, sub)
        os.makedirs(m["_" + sub], exist_ok=True)
    m.setdefault("duration", 30.0)
    m.setdefault("fps", 60)
    # "vo": "vo.json" keeps the voice-over in its own file, so a writer can be allowed to edit
    # the narration without being able to touch the rest of the manifest (Sketch Studio does this)
    if isinstance(m.get("vo"), str):
        with open(rel(m, m["vo"]), encoding="utf-8") as f:
            m["_vo_file"], m["vo"] = rel(m, m["vo"]), json.load(f)
    # "paint": "paint.json" -- scenes painted by an image model (sketch-paint.py). Each one that
    # has been painted joins "images", so the film draws it with SK.image(name, ...)
    if m.get("paint"):
        if isinstance(m["paint"], str):
            with open(rel(m, m["paint"]), encoding="utf-8") as f:
                m["_paint_file"], m["paint"] = rel(m, m["paint"]), json.load(f)
        m["images"] = dict(m.get("images") or {})
        for im in m["paint"].get("images", []):
            p = os.path.join("images", safe_name(im.get("name"), "paint image name") + ".jpg")
            if os.path.exists(rel(m, p)):
                m["images"].setdefault(im["name"], p)
    # "engine": "engine" -- a folder holding the film's own engine.js and props.js (Sketch Studio
    # gives every film a copy it may extend); the repo's sketch/ otherwise
    m["_engine"] = rel(m, m["engine"]) if m.get("engine") else os.path.join(_env.ROOT, "sketch")
    return m


def rel(m, p):
    """A manifest-relative path, resolved."""
    return p if os.path.isabs(p) else os.path.join(m["_dir"], p)


def slug(m):
    return re.sub(r"[^a-z0-9]+", "-", (m.get("slug") or m["_id"]).lower()).strip("-")


# ------------------------------------------------------------------ stage timing
class Stages:
    """Time each stage into `<project>/temp/pipeline/runs/*.jsonl` and print a table at the end.

    with Stages(m, "sketch-audio", ["music", "mix"]) as st:
        with st("music"): ...
    """

    def __init__(self, m, tool, names, argv=None):
        self.m, self.tool, self.rows = m, tool, []
        self.log = _runlog.RunLog(m["_dir"], argv=argv, stages=names, tool=tool)
        self.t0 = time.time()

    def __enter__(self):
        return self

    def __call__(self, name, note=""):
        st = self

        class _Stage:
            def __enter__(self_):
                self_.t = time.time()
                print("[%s] %s ..." % (st.tool, name), flush=True)
                return self_

            def __exit__(self_, et, ev, tb):
                secs = time.time() - self_.t
                state = "ran" if et is None else "failed"
                st.rows.append((name, secs, state))
                st.log.stage(name, state, round(secs, 2), note)
                print("[%s] %s %s in %.1fs" % (st.tool, name, state, secs), flush=True)
                return False

        return _Stage()

    def __exit__(self, et, ev, tb):
        total = time.time() - self.t0
        self.log.end("ok" if et is None else "failed")
        if self.rows:
            print("\n  %-14s %8s" % ("stage", "seconds"))
            for n, s, state in self.rows:
                print("  %-14s %8.1f%s" % (n, s, "" if state == "ran" else "  (" + state + ")"))
            print("  %-14s %8.1f" % ("total", total))
        return False


def timing_report(project_dir):
    """Latest run of each sketch tool for a project: {tool: [(stage, secs)], ...}."""
    out = {}
    runs = sorted(
        (
            os.path.join(_runlog.runs_dir(project_dir), f)
            for f in os.listdir(_runlog.runs_dir(project_dir))
        )
        if os.path.isdir(_runlog.runs_dir(project_dir))
        else []
    )
    for p in runs:
        recs = _runlog.read(p)
        head = next((r for r in recs if r.get("ev") == "run"), {})
        tool = head.get("tool", "?")
        if not tool.startswith("sketch-"):
            continue
        rows = [
            (r["stage"], r.get("secs", 0))
            for r in recs
            if r.get("ev") == "stage" and r.get("state") == "ran"
        ]
        if rows:
            out.setdefault(tool, {}).update(dict(rows))
    return out


# ------------------------------------------------------------------ audio IO
def decode(path, sr=SR, mono=True):
    """Any audio file -> float64 samples (mono, or (2, n) stereo), via ffmpeg."""
    raw = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            path,
            "-f",
            "f32le",
            "-ac",
            "1" if mono else "2",
            "-ar",
            str(sr),
            "-",
        ],
        capture_output=True,
        check=True,
    ).stdout
    x = np.frombuffer(raw, dtype=np.float32).astype(np.float64)
    return x if mono else x.reshape(-1, 2).T.copy()


def write_wav(path, x, sr=SR):
    """float32 WAV (IEEE float, format tag 3). x: (n,) or (channels, n)."""
    x = np.atleast_2d(np.asarray(x, dtype=np.float32))
    ch = x.shape[0]
    data = x.T.reshape(-1).tobytes()
    with open(path, "wb") as f:
        f.write(b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVE")
        f.write(b"fmt " + struct.pack("<IHHIIHH", 16, 3, ch, sr, sr * ch * 4, ch * 4, 32))
        f.write(b"data" + struct.pack("<I", len(data)) + data)


# ------------------------------------------------------------------ captions
def chunk_words(words, max_words=9):
    """Split a line's words into caption chunks at sentence/clause ends, else by length."""
    chunks, cur = [], []
    for w in words:
        cur.append(w)
        end = w["text"].rstrip()[-1:] in ".?!…"
        if (end and len(cur) >= 3) or len(cur) >= max_words:
            chunks.append(cur)
            cur = []
    if cur:
        if chunks and len(cur) < 3:
            chunks[-1] += cur
        else:
            chunks.append(cur)
    return chunks


def captions(timeline, max_words=9):
    """[(start, end, text)] from a VO timeline; a line may carry its own 'captions' split."""
    cues = []
    lines = timeline["lines"]
    for li, L in enumerate(lines):
        words = L["words"]
        if not words:
            continue
        chunks = chunk_words(words, max_words)
        nxt = (
            lines[li + 1]["start"]
            if li + 1 < len(lines)
            else timeline.get("duration", L["end"] + 1)
        )
        for ci, ch in enumerate(chunks):
            s = ch[0]["s"] - 0.05
            e = (
                chunks[ci + 1][0]["s"] - 0.08
                if ci + 1 < len(chunks)
                else min(ch[-1]["e"] + 0.6, nxt - 0.05)
            )
            cues.append((max(0.0, s), e, " ".join(w["text"] for w in ch).replace(" ,", ",")))
    return cues


LANG3 = {"en": "eng", "uk": "ukr", "pl": "pol", "de": "deu", "fr": "fra", "es": "spa"}


def language(m):
    """The film's spoken language, ISO 639-1 (vo.language; English when unset)."""
    return ((m.get("vo") or {}).get("language") or "en").lower()


def iso639_2(m):
    """The same, as the three-letter tag an MP4 subtitle track carries."""
    return LANG3.get(language(m), "und")


def write_captions(timeline, base, max_words=9):
    """Write <base>.srt and <base>.vtt; returns the two paths."""

    def ts(t, sep):
        ms = int(round(t * 1000))
        return "%02d:%02d:%02d%s%03d" % (
            ms // 3600000,
            ms // 60000 % 60,
            ms // 1000 % 60,
            sep,
            ms % 1000,
        )

    cues = captions(timeline, max_words)
    srt = "\n".join(
        "%d\n%s --> %s\n%s\n" % (i + 1, ts(s, ","), ts(e, ","), t)
        for i, (s, e, t) in enumerate(cues)
    )
    vtt = "WEBVTT\n\n" + "\n".join(
        "%s --> %s\n%s\n" % (ts(s, "."), ts(e, "."), t) for s, e, t in cues
    )
    for ext, body in ((".srt", srt), (".vtt", vtt)):
        with open(base + ext, "w", encoding="utf-8") as f:
            f.write(body)
    return base + ".srt", base + ".vtt"
