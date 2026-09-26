"""One film's sandbox: a folder of its own under STUDIO_HOME, and everything it may touch.

    STUDIO_HOME\\projects\\studio-20260925-181500-k3f9qa\\
        sketch.json  studio.json  events.jsonl           the studio's (Claude reads, never writes)
        film.js score.json sfx.json vo.json [paint.json] Claude's
        engine\\engine.js engine\\props.js                 the film's own copy of the engine
        audio\\ images\\ outputs\\ temp\\                    what the pipeline makes

Several films are made at once, each by its own Claude session, so nothing a film does may reach
outside its folder: Claude's cwd is the folder, it may read only inside it (readable) and write
only its own files there (writable), and every pipeline step runs on its manifest with TEMP
pointed into it. The film's id is unguessable, so one film's page cannot be found from another's.

STUDIO_HOME defaults to a folder next to the code (C:\\instafill\\kitcut-studio beside the
kitcut checkout); a release snapshot lives inside it (releases\\<sha>), and then its parent's
parent is the home. It must be on the same drive as the code: the scripts write paths relative
to their own root.
"""

import os
import re
import json
import time
import shutil
import secrets
import difflib
import subprocess
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
# the code this studio runs: a release snapshot (STUDIO_HOME\releases\<sha>), or the working tree
KIT = os.path.dirname(HERE)


def _home():
    env = os.environ.get("STUDIO_HOME", "").strip()
    if env:
        return os.path.abspath(env)
    parent = os.path.dirname(KIT)
    if os.path.basename(parent) == "releases":
        return os.path.dirname(parent)
    return os.path.join(parent, "kitcut-studio")


HOME = _home()
# films made before the studio had a home of its own, in the working tree's projects/ (served
# read-only, never moved): STUDIO_REPO names the checkout when this runs from a release
REPO = os.path.abspath(os.environ.get("STUDIO_REPO") or KIT)
LEGACY = os.path.join(REPO, "projects")

# seconds a visitor may ask for: the site sells them by the second, and decides who may have
# what (films over a minute are for its Pro plan)
LENGTHS = tuple(range(5, 125, 5))
# drawn: everything drawn in code; painted: an image model paints the scenes, the code animates
LOOKS = ("drawn", "painted")
EDITABLE = ("film.js", "score.json", "sfx.json", "vo.json")
MADE = ("film.js", "score.json", "sfx.json")  # what a finished film must have
ENGINE = ("engine.js", "props.js")  # the film's own copy, in engine\; Claude may extend it
# what Claude may not change in paint.json: the painter, and how many paintings a film may cost
# (8 up to a minute, more for a longer film: paint_pins)
PAINT_PINNED = {"backend": "muse", "model": "meta/muse-image", "max_images": 8}
# the voice: Google's Gemini text-to-speech. 3.8 needs the Gemini API enabled in the service
# account's project; STUDIO_TTS_MODEL overrides it (e.g. gemini-3.1-flash-tts-preview)
TTS_MODEL = "gemini-3.8-flash-tts"
# what Claude may not change in vo.json: the studio decides the backend, model and take count
VO_PINNED = {"tts": "gemini", "takes": 1, "lead": 0.5, "gap": 0.35}
STATES = ("queued", "claude", "finishing", "done", "error", "cancelled", "interrupted")
ACTIVE = ("queued", "claude", "finishing")
ID = re.compile(r"^studio-\d{8}-\d{6}(-[a-z2-7]{6})?$")
_B32 = "abcdefghijklmnopqrstuvwxyz234567"


def tts_model():
    return os.environ.get("STUDIO_TTS_MODEL", "").strip() or TTS_MODEL


def limits(length):
    """What one film may take, by its length in seconds. The 5-15 s figures are measured; past
    that they grow with the length (a minute of film is more work, not four times the thinking).
    STUDIO_MAX_USD caps Claude's spend on any one film when set."""
    extra = max(0, length - 15)
    cap = os.environ.get("STUDIO_MAX_USD")
    return {
        "claude_s": 15 * 60 + extra * 10,  # Claude's working time (waits for the machine excluded)
        "wall_s": 40 * 60 + extra * 20,  # its phase, waits included
        "budget_usd": float(cap) if cap else max(5.0, 0.12 * length),
        # what a film being made may still spend, held against the day's budget: from the films
        # so far, about $0.33 + $0.05 a second, with room
        "reserve_usd": max(
            float(os.environ.get("STUDIO_RESERVE_USD") or 1.5), 0.35 + 0.06 * length
        ),
        "render_s": 300 + 15 * length,
        "sound_s": max(300, 120 + 5 * length),
        "voice_s": max(300, 180 + 5 * length),
        "lines": 6 if length <= 15 else max(12, -(-length // 5)),  # narration sentences
        "tts_usd": max(0.30, 0.005 * length),  # what the narration may cost, retakes included
        "images": 8 if length <= 60 else 12,  # paintings, repaints included
    }


def paint_pins(length):
    """What the studio sets in a painted film's paint.json."""
    return PAINT_PINNED | {"max_images": limits(length)["images"]}


def _release():
    """What code this is: the snapshot's commit, or the working tree's (marked dev)."""
    try:
        with open(os.path.join(KIT, "RELEASE.json"), encoding="utf-8") as f:
            return json.load(f)["sha"][:12]
    except (OSError, ValueError, KeyError):
        pass
    try:
        out = subprocess.run(
            ["git", "-C", KIT, "rev-parse", "--short=12", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        out = ""
    return (out or "unknown") + "-dev"


RELEASE = _release()


def _write_json(path, data):
    """Atomically: a reader (the server answering a poll) never sees half a file. Windows refuses
    the rename for a moment while someone has the target open, so it retries briefly."""
    tmp = "%s.%d.tmp" % (path, os.getpid())
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)
    for i in range(20):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            time.sleep(0.05 * (i + 1))
    os.replace(tmp, path)


def _norm(p):
    return os.path.normcase(os.path.realpath(p))


class Film:
    def __init__(self, d):
        self.dir = os.path.abspath(d)
        self.id = os.path.basename(self.dir)

    def __repr__(self):
        return "Film(%s)" % self.id

    # ---------------------------------------------------------------- where things are
    def path(self, *parts):
        return os.path.join(self.dir, *parts)

    @property
    def manifest(self):
        return self.path("sketch.json")

    @property
    def claude_dir(self):
        """Claude Code's config folder for this film's session (its transcript): outside the
        film, so Claude cannot read it back."""
        return os.path.join(HOME, "claude", self.id)

    @property
    def legacy(self):
        return not _norm(self.dir).startswith(_norm(os.path.join(HOME, "projects")) + os.sep)

    # ---------------------------------------------------------------- the record (studio.json)
    def record(self):
        try:
            with open(self.path("studio.json"), encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def update(self, **fields):
        rec = self.record()
        rec.update(fields)
        _write_json(self.path("studio.json"), rec)
        return rec

    @property
    def state(self):
        rec = self.record()
        if "state" in rec:
            return rec["state"]
        # made before films had states
        return "done" if rec.get("ok") else ("error" if "finished" in rec else "interrupted")

    @property
    def look(self):
        return "painted" if os.path.exists(self.path("paint.json")) else "drawn"

    @property
    def length(self):
        with open(self.manifest, encoding="utf-8") as f:
            return round(float(json.load(f)["duration"]))

    # ---------------------------------------------------------------- what Claude may touch
    def editable(self):
        return EDITABLE + (("paint.json",) if self.look == "painted" else ())

    def readable(self, p):
        """Inside the film's own folder, except the studio's bookkeeping. Checked on the real
        path, so a link cannot lead out."""
        p, d = _norm(p), _norm(self.dir)
        if not p.startswith(d + os.sep):
            return False
        top = p[len(d) + 1 :].split(os.sep)[0]
        return top not in ("temp", "studio.json", "events.jsonl")

    def writable(self, p):
        p = _norm(p)
        parent, name = os.path.dirname(p), os.path.basename(p)
        if parent == _norm(self.dir):
            return name in self.editable()
        return parent == _norm(self.path("engine")) and name in ENGINE

    # ---------------------------------------------------------------- the engine copy
    def engine_diff(self):
        """What Claude changed in its copy of the engine, as a unified diff against the code this
        studio runs (the curator's raw material), written to outputs/engine.diff. Returns the
        number of changed lines."""
        out, n = [], 0
        for name in ENGINE:
            try:
                with open(os.path.join(KIT, "sketch", name), encoding="utf-8") as f:
                    a = f.read().splitlines(keepends=True)
                with open(self.path("engine", name), encoding="utf-8") as f:
                    b = f.read().splitlines(keepends=True)
            except OSError:
                continue
            d = list(difflib.unified_diff(a, b, "sketch/" + name, "engine/" + name))
            n += sum(1 for x in d if x[:1] in "+-" and not x.startswith(("+++", "---")))
            out += d
        if out:
            os.makedirs(self.path("outputs"), exist_ok=True)
            with open(self.path("outputs", "engine.diff"), "w", encoding="utf-8") as f:
                f.writelines(out)
        return n

    # ---------------------------------------------------------------- what the film chose
    def direction(self):
        """The choices the film made -- its ground and style, voice, music, painting style --
        read from its own files: the next films are told what recent ones chose (agent.recent),
        and the curator can see what films choose."""

        def load(name):
            try:
                with open(self.path(name), encoding="utf-8") as f:
                    return f.read() if name.endswith(".js") else json.load(f)
            except (OSError, ValueError):
                return None

        d = {"look": self.look}
        js = load("film.js") or ""
        if d["look"] == "drawn":
            g = re.search(r"setGround\(\s*['\"](\w+)", js)
            changes = re.search(r"\bground\s*:\s*\(?\s*\w+\s*\)?\s*=>", js)
            d["ground"] = "changing" if changes else (g.group(1) if g else "paper")
        st = re.search(r"setStyle\(\s*['\"](\w+)", js)
        d["style"] = st.group(1) if st else "crayon"
        vo = load("vo.json") or {}
        if isinstance(vo, dict):
            d["voice"], d["voice_style"] = vo.get("voice"), (vo.get("style") or "")[:120]
        score = load("score.json") or {}
        if isinstance(score, dict):
            ev = score.get("events") if isinstance(score.get("events"), list) else []
            inst = {
                e.get("inst") for e in ev if isinstance(e, dict) and isinstance(e.get("inst"), str)
            }
            drums = any(isinstance(e, dict) and e.get("type") == "drums" for e in ev)
            d["instruments"] = sorted(inst) + (["drums"] if drums else [])
            d["bpm"] = score.get("bpm")
        if d["look"] == "painted":
            paint = load("paint.json") or {}
            d["paint_style"] = (paint.get("style") or "")[:120] if isinstance(paint, dict) else ""
        return d

    # ---------------------------------------------------------------- making and finding films
    @classmethod
    def create(
        cls, prompt, seconds=5, look="drawn", client="local", source="web", priority=0, auth="api"
    ):
        """A new film's folder: the manifest (its length set), the engine copy, an empty
        narration, an empty list of paintings for a painted film, and its record."""
        seconds = seconds if seconds in LENGTHS else LENGTHS[0]
        look = look if look in LOOKS else LOOKS[0]
        projects = os.path.join(HOME, "projects")
        os.makedirs(projects, exist_ok=True)
        for _ in range(50):
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            fid = "studio-%s-%s" % (stamp, "".join(secrets.choice(_B32) for _ in range(6)))
            try:
                os.makedirs(os.path.join(projects, fid))
                break
            except FileExistsError:
                continue
        else:
            raise RuntimeError("could not make a unique film folder")
        film = cls(os.path.join(projects, fid))
        os.makedirs(film.path("engine"))
        os.makedirs(film.path("temp", "tmp"))
        for name in ENGINE:  # copyfile, not copy2: a release's files are read-only
            shutil.copyfile(os.path.join(KIT, "sketch", name), film.path("engine", name))
        with open(os.path.join(HERE, "template", "sketch.json"), encoding="utf-8") as f:
            m = json.load(f)
        words = re.sub(r"\s+", " ", prompt).strip()
        m["title"] = (words[:60] + "...") if len(words) > 60 else words
        m["duration"], m["poster_t"] = float(seconds), round(seconds - 0.4, 2)
        m["engine"] = "engine"
        if look == "painted":
            m["paint"] = "paint.json"
            _write_json(film.path("paint.json"), paint_pins(seconds) | {"style": "", "images": []})
        _write_json(film.manifest, m)
        vo = {**VO_PINNED, "model": tts_model(), "voice": "Kore", "style": "", "language": "en"}
        _write_json(film.path("vo.json"), vo | {"lines": []})
        _write_json(
            film.path("studio.json"),
            {
                "id": fid,
                "prompt": prompt,
                "look": look,
                "length": seconds,  # the film's; "seconds" is later how long making it took
                "client": client,
                "source": source,
                # 1: a plan whose films go ahead of the others in every queue (sched.py)
                "priority": 1 if priority else 0,
                # api: the public key (billed); login: this machine's Claude Code (local only)
                "auth": auth,
                "release": RELEASE,
                "state": "queued",
                "created": datetime.now().isoformat(timespec="seconds"),
            },
        )
        return film

    @classmethod
    def open(cls, fid):
        """The film with this id, in the studio's home or (made earlier) the working tree; None
        if there is none. The id is checked first, so it can never name a path."""
        if not isinstance(fid, str) or not ID.match(fid):
            return None
        for base in (os.path.join(HOME, "projects"), LEGACY):
            d = os.path.join(base, fid)
            if os.path.isfile(os.path.join(d, "studio.json")):
                return cls(d)
        return None

    @classmethod
    def all(cls):
        """Every film on this machine, newest first."""
        seen = {}
        for base in (LEGACY, os.path.join(HOME, "projects")):
            if os.path.isdir(base):
                for fid in os.listdir(base):
                    if ID.match(fid) and os.path.isfile(os.path.join(base, fid, "studio.json")):
                        seen[fid] = cls(os.path.join(base, fid))
        return [seen[k] for k in sorted(seen, reverse=True)]
