"""A film's captions once it is made: the copies with them burned in, made when asked for.

Every film with narration is rendered clean, its captions beside it as captions.json
(sketch-render's "captions" stage), and the site's players draw them live over the video; the
film's page switches them on and off and picks their look, all on the site (kitcut.ai, the
film_captions collection) with nothing asked of the studio. Only a copy that leaves KitCut needs
them in its pixels:

  download   the master with them (Download, "Video with captions"; an assistant's link)
  youtube    the same, sent into YouTube's upload session (youtube.py)
  preview    the web copy with them, online, for the apps that play a link's video inside a chat
             (Telegram, Slack, iMessage, Discord: the share page's og:video)

A copy is named by everything it is made of -- the version's captions.json, its video, the look
asked for and the kind -- so asking again gives the same file, and a new version or a new look
another. It is made by scripts/captions-burn.py (the same drawing as the players'), one at a time,
in outputs/captioned/ of the version it is made from; it is kept CAPTIONED_DAYS after it was last
asked for, then deleted (prune). A preview copy also goes online beside the film's files and its
address is kept beside it (<name>.url), which outlives the local file.

    POST /api/films/<id>/captioned {"kind", "style", "version"} -> {"state": "ready", "url"} |
         {"state": "preparing"} | {"state": "none"} (no captions) | {"state": "failed", "error"}
"""

import os
import re
import sys
import json
import time
import asyncio
import hashlib
import subprocess

import media

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.dirname(HERE)
KINDS = {"download": "master", "youtube": "master", "preview": "web"}
CAPTIONED_DAYS = 3
DIR = "captioned"
PRESETS = ("brand", "classic", "plain", "light")
COLOUR = re.compile(
    r"^(#[0-9a-fA-F]{3,8}|rgba?\(\s*[\d.]+\s*,\s*[\d.]+\s*,\s*[\d.]+\s*(,\s*[\d.]+\s*)?\))$"
)
FAMILY = re.compile(r"^[\w .'-]{1,60}$", re.UNICODE)

JOBS = {}  # path -> {"state", "error", "t", "task"}
ONE = None  # one copy is made at a time (asyncio.Semaphore, made in the server's loop)


def clean_style(style):
    """The look a person chose ({preset, card, ink, said, font}), checked: None for the film's
    own; what is not a preset, a colour or a face's name is dropped."""
    if not isinstance(style, dict):
        return None
    out = {}
    if style.get("preset") in PRESETS:
        out["preset"] = style["preset"]
    for k in ("card", "ink", "said"):
        v = style.get(k)
        if isinstance(v, str) and COLOUR.match(v.strip()):
            out[k] = v.strip()
    if isinstance(style.get("font"), str) and FAMILY.match(style["font"].strip()):
        out["font"] = style["font"].strip()
    return out or None


def outputs(film, version=None):
    """The outputs/ folder of one of the film's versions: the film now, or a version kept in
    versions/v<n>/ (rounds.py). None when there is no such version."""
    now = film.record().get("version") or 1
    if version in (None, now):
        return film.path("outputs")
    try:
        d = film.path("versions", "v%d" % int(version), "outputs")
    except (TypeError, ValueError):
        return None
    return d if os.path.isdir(d) else None


def name_of(out, kind, style):
    """The copy's file name: what it is made of, hashed."""
    src = os.path.join(out, "film.mp4" if KINDS[kind] == "master" else "film_web.mp4")
    h = hashlib.sha256()
    with open(os.path.join(out, "captions.json"), "rb") as f:
        h.update(f.read())
    st = os.stat(src)
    h.update(("%s %d %d" % (KINDS[kind], st.st_size, int(st.st_mtime))).encode())
    h.update(json.dumps(style or {}, sort_keys=True).encode())
    return "%s-%s.mp4" % ("web" if KINDS[kind] == "web" else "film", h.hexdigest()[:16])


def want(film, kind, style=None, version=None):
    """The copy of this kind and look: ready ({"state", "path", "name"}, its address kept for a
    preview), being made, or started now. {"state": "none"} for a version with no captions."""
    if kind not in KINDS:
        raise ValueError("kind must be one of %s" % ", ".join(KINDS))
    out = outputs(film, version)
    if out is None or not os.path.isfile(os.path.join(out, "captions.json")):
        return {"state": "none"}
    if KINDS[kind] == "web" and not os.path.isfile(os.path.join(out, "film_web.mp4")):
        try:
            media.make_web(film, out)
        except Exception as e:  # noqa: BLE001 -- a film with no web copy has no preview copy
            return {"state": "failed", "error": "no web copy: %s" % e}
    style = clean_style(style)
    name = name_of(out, kind, style)
    path = os.path.join(out, DIR, name)
    prune(film)
    if kind == "preview":
        url = _read(path + ".url")
        if url:
            return {"state": "ready", "path": path, "name": name, "url": url}
    if os.path.isfile(path) and path not in JOBS:
        os.utime(path)  # asked for again: kept CAPTIONED_DAYS from now
        return {"state": "ready", "path": path, "name": name}
    job = JOBS.get(path)
    if job and job["state"] == "making":
        return {"state": "preparing", "name": name}
    if job and job["state"] == "failed" and time.time() - job["t"] < 600:
        return {"state": "failed", "error": job["error"], "name": name}
    job = {"state": "making", "t": time.time()}
    JOBS[path] = job
    job["task"] = asyncio.get_running_loop().create_task(_make(film, out, kind, style, path, job))
    return {"state": "preparing", "name": name}


async def burned(film, kind, style=None, version=None, poll=1.0):
    """The copy's path, waiting while it is made (youtube.py, before it sends). Raises
    RuntimeError when it cannot be made, LookupError when the version has no captions."""
    while True:
        got = want(film, kind, style, version)
        if got["state"] == "ready" and os.path.isfile(got["path"]):
            return got["path"]
        if got["state"] == "none":
            raise LookupError("this film has no captions")
        if got["state"] == "failed":
            raise RuntimeError(got["error"])
        job = JOBS.get(os.path.join(outputs(film, version), DIR, got["name"]))
        if job and job.get("task"):
            await asyncio.shield(job["task"])
        else:
            await asyncio.sleep(poll)


async def _make(film, out, kind, style, path, job):
    global ONE
    if ONE is None:
        ONE = asyncio.Semaphore(1)
    try:
        async with ONE:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            await asyncio.to_thread(burn, out, kind, style, path)
            if kind == "preview":
                rel = "%s/%s" % (DIR, os.path.basename(path))
                url = await media.publish_one(film, rel, "video/mp4", out=out)
                if url:
                    _write(path + ".url", url)
        job["state"] = "ready"
    except Exception as e:  # noqa: BLE001 -- the site is told, and may ask again in a while
        job["state"], job["error"] = "failed", str(e)[-300:]
        print("film %s: captions not burned: %s" % (film.id, e), file=sys.stderr, flush=True)
    job["t"] = time.time()
    if job["state"] == "ready":  # the file answers from now on; a failure is kept a while
        JOBS.pop(path, None)


def burn(out, kind, style, path):
    """scripts/captions-burn.py over the version's video, into `path`."""
    web = KINDS[kind] == "web"
    cmd = [
        sys.executable,
        os.path.join(KIT, "scripts", "captions-burn.py"),
        "--video",
        os.path.join(out, "film_web.mp4" if web else "film.mp4"),
        "--captions",
        os.path.join(out, "captions.json"),
        "--out",
        path,
    ]
    if style:
        cmd += ["--style", json.dumps(style)]
    if web:
        cmd += ["--encode", json.dumps(media.WEB)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=3600, check=False)
    if r.returncode or not os.path.isfile(path):
        raise RuntimeError((r.stderr or r.stdout or "captions-burn failed").strip()[-300:])


def prune(film, now=None):
    """Copies not asked for in CAPTIONED_DAYS go, from every version of the film (a preview's
    address is kept: its online copy still plays)."""
    now = now or time.time()
    dirs = [film.path("outputs", DIR)]
    kept = film.path("versions")
    if os.path.isdir(kept):
        dirs += [os.path.join(kept, v, "outputs", DIR) for v in os.listdir(kept)]
    for d in dirs:
        if not os.path.isdir(d):
            continue
        for n in os.listdir(d):
            p = os.path.join(d, n)
            if n.endswith(".mp4") and p not in JOBS:
                try:
                    if now - os.path.getmtime(p) > CAPTIONED_DAYS * 86400:
                        os.remove(p)
                except OSError:
                    pass


def _read(p):
    try:
        with open(p, encoding="utf-8") as f:
            return f.read().strip() or None
    except OSError:
        return None


def _write(p, text):
    tmp = "%s.%d.tmp" % (p, os.getpid())
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, p)
