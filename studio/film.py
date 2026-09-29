"""One film's sandbox: a folder of its own under STUDIO_HOME, and everything it may touch.

    STUDIO_HOME\\projects\\studio-20260925-181500-k3f9qa\\
        sketch.json  studio.json  events.jsonl           the studio's (Claude reads, never writes)
        inputs\\upload1.jpg voice1.webm doc1.md         what the visitor attached (uploads.py)
        film.js score.json sfx.json vo.json [paint.json] Claude's
        engine\\engine.js engine\\props.js                 the film's own copy of the engine, and
        [engine\\collage.js]                             its capabilities' modules (CAPS)
        cast\\<name>.js                                   the person's cast (library.py): loaded
                                                         before film.js, kept for their next films
        library\\                                        their earlier films, the cast drawn (read)
        audio\\ images\\ outputs\\ temp\\                    what the pipeline makes

projects\\ is where films live (a name from before the site had projects). A film's "project" in
its record is the site's: a series or a channel the person makes it for, with its own library.

Several films are made at once, each by its own Claude session, so nothing a film does may reach
outside its folder: Claude's cwd is the folder, it may read only inside it (readable) and write
only its own files there (writable), and every pipeline step runs on its manifest with TEMP
pointed into it. The film's id is unguessable, so one film's page cannot be found from another's.

During a ship two servers share the home (peers.py): the one making a film writes its record while
the other may hide it or change its listing. So the record is changed under temp\\record.lock
(Film.update), and read without one (every write replaces the whole file).

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
import contextlib
import subprocess
from collections import Counter
from datetime import datetime

import locks

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
# what (films over a minute are for its Pro plan, up to 8 minutes)
LENGTHS = tuple(range(5, 485, 5))
# drawn: everything drawn in code; painted: an image model paints the scenes, the code animates;
# collage: an image model paints single objects cut out of paper, the code builds pages round them.
# The person's choice; each is a recipe of capabilities (RECIPES, below)
LOOKS = ("drawn", "painted", "collage")
EDITABLE = ("film.js", "score.json", "sfx.json", "vo.json")
MADE = ("film.js", "score.json", "sfx.json")  # what a finished film must have
# the film's own copy, in engine\; Claude may extend it. Its capabilities' modules join it
ENGINE = ("engine.js", "props.js")
# a member of the person's cast, cast\<name>.js (library.py), and one named in film code:
# SK.cast.pip, cast.pip, cast['pip']
CAST_FILE = re.compile(r"^[a-z][a-z0-9_]{0,30}\.js$")
CAST_USE = re.compile(r"\bcast\s*(?:\.\s*([a-z][a-z0-9_]*)|\[\s*['\"]([a-z][a-z0-9_]*)['\"]\s*\])")
# film.js's first line, `// For: <who it is for>; <its mood>`: the audience the film is made for
FOR_LINE = re.compile(
    r"^[ \t]*//[ \t]*for:[ \t]*(\S[^\r\n]*?)[ \t]*\r?$", re.MULTILINE | re.IGNORECASE
)
# what Claude may not change in paint.json: the painter, and how many paintings a film may cost
# (8 up to a minute, more for a longer film: limits()["images"], paint_pins)
PAINT_PINNED = {"backend": "muse", "model": "meta/muse-image", "max_images": 8}
# a collage film's cut-outs: a model that paints on a transparent background (sketch-paint.py)
CUTOUTS_PINNED = {
    "model": "openai/gpt-image-2.5-flare",
    "quality": "medium",
    "border": 12,
    "cut": "scissor",
}
# the print faces a collage film's pieces use (sketch/collage.js), on top of the template's
COLLAGE_FONTS = [
    {"file": "fonts/AbrilFatface-Regular.ttf", "family": "Abril Fatface", "weight": "400"},
    {"file": "fonts/UnifrakturMaguntia-Book.ttf", "family": "UnifrakturMaguntia", "weight": "400"},
    {"file": "fonts/Oswald-VF.ttf", "family": "Oswald", "weight": "200 700", "load": "500 600 700"},
    {"file": "fonts/OldStandard-Regular.ttf", "family": "Old Standard TT", "weight": "400"},
    {"file": "fonts/OldStandard-Bold.ttf", "family": "Old Standard TT", "weight": "700"},
    {
        "file": "fonts/OldStandard-Italic.ttf",
        "family": "Old Standard TT",
        "weight": "400",
        "style": "italic",
    },
    {
        "file": "fonts/PlayfairDisplay-VF.ttf",
        "family": "Playfair Display",
        "weight": "400 900",
        "load": "700 900",
    },
    {
        "file": "fonts/PlayfairDisplay-Italic-VF.ttf",
        "family": "Playfair Display",
        "weight": "400 900",
        "style": "italic",
        "load": "400 700",
    },
    {"file": "fonts/CourierPrime-Regular.ttf", "family": "Courier Prime", "weight": "400"},
    {"file": "fonts/CourierPrime-Bold.ttf", "family": "Courier Prime", "weight": "700"},
    {"file": "fonts/Anton-Regular.ttf", "family": "Anton", "weight": "400"},
    # sets a Cyrillic line where Courier Prime cannot (collage.js SK.face)
    {"file": "fonts/IBMPlexMono-Regular.ttf", "family": "IBM Plex Mono", "weight": "400"},
    {"file": "fonts/IBMPlexMono-Bold.ttf", "family": "IBM Plex Mono", "weight": "700"},
]
PRINT_FACES = tuple(dict.fromkeys(f["family"] for f in COLLAGE_FONTS))
# What a film may be made of beyond what every film has. A look is a recipe of these, and a
# capability is one kind of material with everything the studio does for it:
#   modules    sketch/<m>.js, copied into the film's engine\ beside engine.js and props.js
#   fonts      faces added to the film's manifest
#   paint      pictures it may paint: cap (a limits() key; a film's kinds add up), pins (set in
#              paint.json over PAINT_PINNED), keys (an image's own beyond name/prompt/ref),
#              label (the page's line while they paint), noun (what they are called)
#   fills      the system prompt's {PLACEHOLDERS} its looks' briefs use: files under KIT
#   direction  what Film.direction() records of the film's choices (agent.recent_note)
# Granting a capability to another look is a change to RECIPES -- a brief change, so it is
# proven with studio/bakeoff.py first.
CAPS = {
    "grounds": {"direction": ("ground",)},
    "paintings": {
        "paint": {
            "cap": "images",
            "pins": {},
            "keys": (),
            "label": "painting the scenes (Muse)",
            "noun": "paintings",
        },
        "direction": ("paint_style",),
    },
    "cutouts": {
        "paint": {
            "cap": "cutouts",
            "pins": {"cutouts": CUTOUTS_PINNED},
            "keys": ("cutout", "aspect"),
            "label": "painting the cut-outs",
            "noun": "cut-outs",
        },
        "direction": ("paint_style",),  # the medium they are painted in
    },
    "collage": {
        "modules": ("collage",),
        "fonts": COLLAGE_FONTS,
        "fills": {
            "COLLAGE": ("sketch", "collage.js"),
            "EXAMPLE_COLLAGE": ("config", "sketch", "collage-example", "film.js"),
        },
        # the print faces it names most, and whether a newspaper page lies under it
        "direction": ("faces", "newsprint"),
    },
}
RECIPES = {
    "drawn": ("grounds",),
    "painted": ("paintings",),
    "collage": ("cutouts", "collage"),
}
# the voice: Google's Gemini text-to-speech. 3.8 needs the Gemini API enabled in the service
# account's project; STUDIO_TTS_MODEL overrides it (e.g. gemini-3.1-flash-tts-preview)
TTS_MODEL = "gemini-3.8-flash-tts"
# what Claude may not change in vo.json: the studio decides the backend, model and take count
# a line Gemini refuses to read (its content filter: a name, a wine) is read by the backup
# voice, a low or a high one to go with the film's own narration (scripts/sketch-vo.py)
VO_BACKUP = {"tts": "elevenlabs", "model": "eleven_v3", "voices": {"low": "brian", "high": "sarah"}}
VO_PINNED = {"tts": "gemini", "takes": 1, "lead": 0.5, "gap": 0.35, "backup": VO_BACKUP}
STATES = ("queued", "claude", "finishing", "done", "error", "cancelled", "interrupted")
ACTIVE = ("queued", "claude", "finishing")
ID = re.compile(r"^studio-\d{8}-\d{6}(-[a-z2-7]{6})?$")
# a project on the site (a series, a channel): its id, and how long its brief may be
PROJECT_ID = re.compile(r"^p-[a-z2-7]{10}$")
BRIEF_MAX = 2000
_B32 = "abcdefghijklmnopqrstuvwxyz234567"


def tts_model():
    return os.environ.get("STUDIO_TTS_MODEL", "").strip() or TTS_MODEL


def limits(length):
    """What one film may take, by its length in seconds. The 5-15 s figures are measured; past
    that they grow with the length (a minute of film is more work, not four times the thinking).
    STUDIO_MAX_USD caps Claude's spend on any one film when set."""
    extra = max(0, length - 15)
    cap = os.environ.get("STUDIO_MAX_USD")
    # the machine steps' timeouts were measured on the laptop; a slower machine (a CPU-only VM)
    # scales them rather than failing films that are only taking longer (docs/studio-speed.md)
    slow = float(os.environ.get("STUDIO_MACHINE_SLOWDOWN") or 1)
    return {
        # Claude's working time (waits for the machine excluded): at effort xhigh a 10 s film
        # took 4.6-12 min and a 30 s one 14.5 (2026-09-26); a 60 s one ran past 22.5
        "claude_s": 20 * 60 + extra * 15,
        "wall_s": 60 * 60 + extra * 25,  # its phase, waits included
        "budget_usd": float(cap) if cap else max(5.0, 0.12 * length),
        # what a film being made may still spend, held against the day's budget: from the films
        # so far, about $0.33 + $0.05 a second, with room
        "reserve_usd": max(
            float(os.environ.get("STUDIO_RESERVE_USD") or 1.5), 0.35 + 0.06 * length
        ),
        "render_s": int(slow * (300 + 15 * length)),
        "sound_s": int(slow * max(300, 120 + 5 * length)),
        "voice_s": int(slow * max(300, 180 + 5 * length)),
        "lines": 6 if length <= 15 else max(12, -(-length // 5)),  # narration sentences
        "tts_usd": max(0.30, 0.005 * length),  # what the narration may cost, retakes included
        # recordings (voice runs), retakes included: 6 was plenty up to a minute; an 8-minute film
        # has ~96 lines, and a line the voice model refuses costs a run too
        "voice_runs": max(6, length // 30),
        # a drums event's bars: 64 covered a short film; 8 minutes at 120 bpm is 240 bars (a bar
        # is at least a second at the 240 bpm the score allows)
        "drum_bars": max(64, length),
        # paintings, repaints included: 12 up to 4 minutes, then one about every 20 s
        "images": 8 if length <= 60 else min(24, max(12, length // 20)),
        # a collage film's cut-outs, repaints included: pages hold several each (the reference
        # 60 s collage used ~19); ~$0.014 each
        "cutouts": 10 if length <= 15 else min(40, max(14, length // 3)),
        # the agent's turns: 60 was enough up to 2 minutes; a longer film writes and checks
        # more scenes (a turn is one of Claude's replies, its tool calls included)
        "turns": 60 + max(0, length - 120) // 6,
    }


def modules(caps):
    """The engine modules these capabilities bring (sketch/<name>.js)."""
    return tuple(m for c in caps for m in CAPS[c].get("modules", ()))


def fonts(caps):
    """The faces these capabilities add to the manifest."""
    return [f for c in caps for f in CAPS[c].get("fonts", ())]


def paint_kinds(caps):
    """The kinds of picture these capabilities paint ([] when the film paints nothing)."""
    return [CAPS[c]["paint"] for c in caps if "paint" in CAPS[c]]


def image_keys(caps):
    """What an image in paint.json may say besides its name, prompt and ref."""
    return {k for kind in paint_kinds(caps) for k in kind["keys"]}


def fills(caps):
    """The system prompt's placeholders these capabilities fill: {NAME: path parts}."""
    return {k: v for c in caps for k, v in CAPS[c].get("fills", {}).items()}


def direction_fields(caps):
    """The choices of a film with these capabilities that Film.direction() records."""
    return {f for c in caps for f in CAPS[c].get("direction", ())}


def paint_words(caps):
    """(label, noun) for its pictures: the page's line while they paint, and their name."""
    kinds = paint_kinds(caps)
    if len(kinds) == 1:
        return kinds[0]["label"], kinds[0]["noun"]
    return "painting the pictures", "pictures"


def paint_pins(length, caps):
    """What the studio sets in the paint.json of a film with these capabilities: the painter,
    each kind's own settings, and the cap on pictures (repaints included), its kinds' caps
    added up."""
    kinds = paint_kinds(caps)
    pins = dict(PAINT_PINNED)
    for kind in kinds:
        pins |= kind["pins"]
    return pins | {"max_images": sum(limits(length)[kind["cap"]] for kind in kinds)}


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
        """Change these fields of the record, keeping the rest. Read, changed and written under
        the film's record lock (temp/record.lock): during a ship two servers run on one home
        (peers.py, KI-031), and a person hiding a film on one must not undo the state its maker
        on the other has just written, nor be undone by it. Not reentrant: nothing may update
        inside an update. Reading (record) takes no lock: every write is a whole-file rename."""
        with contextlib.ExitStack() as held:
            try:
                if self._temp():
                    held.enter_context(locks.locked(self.path("temp", "record.lock")))
            except locks.LockTimeout as e:  # a peer stalled halfway through its write
                print("%s: %s; writing the record without it" % (self.id, e), flush=True)
            except OSError:
                pass  # no lock file can be made here: write as it always did
            rec = self.record()
            rec.update(fields)
            _write_json(self.path("studio.json"), rec)
            return rec

    def _temp(self):
        """Make sure temp/ is there, for the record lock; False when it cannot be -- a film from
        before the studio had a home, in a working tree this process may not write to, or a
        folder that is gone. Then a record is written without the lock, as it always was: a lock
        is never the reason a film fails. mkdir, not makedirs: a removed film stays removed."""
        try:
            os.mkdir(self.path("temp"))
        except FileExistsError:
            pass
        except OSError:
            return False
        return True

    @property
    def state(self):
        rec = self.record()
        if "state" in rec:
            return rec["state"]
        # made before films had states
        return "done" if rec.get("ok") else ("error" if "finished" in rec else "interrupted")

    @property
    def look(self):
        """Its record's (since 2026-09-25); an older film is painted if it has a paint.json."""
        look = self.record().get("look")
        if look in LOOKS:
            return look
        return "painted" if os.path.exists(self.path("paint.json")) else "drawn"

    @property
    def caps(self):
        """What it may be made of (CAPS): fixed in its record when it was made, so a later change
        to its look's recipe never reaches a film already made, or one picked up after a ship.
        A film from before capabilities has its look's recipe."""
        got = self.record().get("caps")
        if isinstance(got, list) and got and all(c in CAPS for c in got):
            return tuple(got)
        return RECIPES[self.look]

    def engine_files(self):
        """Its engine copy's files: every film's, and its capabilities' modules."""
        return ENGINE + tuple(m + ".js" for m in modules(self.caps))

    @property
    def length(self):
        with open(self.manifest, encoding="utf-8") as f:
            return round(float(json.load(f)["duration"]))

    # ---------------------------------------------------------------- what Claude may touch
    def editable(self):
        return EDITABLE + (("paint.json",) if paint_kinds(self.caps) else ())

    def readable(self, p):
        """Inside the film's own folder, except the studio's bookkeeping. Checked on the real
        path, so a link cannot lead out."""
        p, d = _norm(p), _norm(self.dir)
        if not p.startswith(d + os.sep):
            return False
        top = p[len(d) + 1 :].split(os.sep)[0]
        return top not in ("temp", "studio.json", "events.jsonl")

    def writable(self, p):
        raw, p = p, _norm(p)
        parent, name = os.path.dirname(p), os.path.basename(p)
        if parent == _norm(self.dir):
            return name in self.editable()
        if parent == _norm(self.path("cast")):  # a film made before casts has no such folder
            # the name as asked for: Windows would fold Pip.js into pip.js
            asked = os.path.basename(os.path.realpath(raw))
            return bool(CAST_FILE.match(asked)) and os.path.isdir(self.path("cast"))
        return parent == _norm(self.path("engine")) and name in self.engine_files()

    # ---------------------------------------------------------------- the engine copy
    def engine_diff(self):
        """What Claude changed in its copy of the engine, as a unified diff against the code this
        studio runs (the curator's raw material), written to outputs/engine.diff. Returns the
        number of changed lines."""
        out, n = [], 0
        for name in self.engine_files():
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
        fields = direction_fields(self.caps)
        js = load("film.js") or ""
        # who it is for and its mood, the film's first decision (prompt.md, "# Direction")
        m = FOR_LINE.search(js)
        d["audience"] = m.group(1)[:160] if m else ""
        if "ground" in fields:
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
        if "paint_style" in fields:
            paint = load("paint.json") or {}
            d["paint_style"] = (paint.get("style") or "")[:120] if isinstance(paint, dict) else ""
        if "faces" in fields:  # a face named in its code, most used first
            named = Counter({f: js.count("'%s'" % f) + js.count('"%s"' % f) for f in PRINT_FACES})
            d["faces"] = [f for f, n in named.most_common(3) if n]
        if "newsprint" in fields:
            d["newsprint"] = "SK.newsprint(" in js
        cast = sorted({a or b for a, b in CAST_USE.findall(js)})
        if cast:
            d["cast"] = cast
        return d

    # ---------------------------------------------------------------- making and finding films
    @classmethod
    def create(
        cls,
        prompt,
        seconds=5,
        look="drawn",
        client="local",
        source="web",
        priority=0,
        auth="api",
        branding=False,
        attachments=(),
        project=None,
        listed=True,
        app=None,
        fps=60,
    ):
        """A new film's folder: the manifest (its length set), the engine copy, an empty
        narration, an empty list of paintings for a painted film, and its record.

        attachments: what the visitor attached (uploads.take), each meta with its file as "src",
        copied into inputs/. A picture becomes upload1.jpg... and joins the manifest's images
        under that name, so film.js can draw it with SK.image('upload1', ...); a voice note
        becomes voice1..., with its words in the record; a document becomes doc1.txt (or .md),
        with the name it came with.

        project: the site's project the film is an episode of, {id, name, brief,
        from_account_cast}, checked by the caller; its library is the project's (library.py)."""
        seconds = seconds if seconds in LENGTHS else LENGTHS[0]
        look = look if look in LOOKS else LOOKS[0]
        caps = RECIPES[look]
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
        os.makedirs(film.path("cast"))  # the person's cast: library.seed fills it
        os.makedirs(film.path("temp", "tmp"))
        for name in ENGINE + tuple(m + ".js" for m in modules(caps)):
            # copyfile, not copy2: a release's files are read-only
            shutil.copyfile(os.path.join(KIT, "sketch", name), film.path("engine", name))
        with open(os.path.join(HERE, "template", "sketch.json"), encoding="utf-8") as f:
            m = json.load(f)
        words = re.sub(r"\s+", " ", prompt).strip()
        m["title"] = (words[:60] + "...") if len(words) > 60 else words
        attached = []
        if attachments:
            os.makedirs(film.path("inputs"))
            n = {"image": 0, "audio": 0, "text": 0}
            stems = {"image": "upload%d", "audio": "voice%d", "text": "doc%d"}
            for a in attachments:
                n[a["kind"]] += 1
                stem = stems[a["kind"]] % n[a["kind"]]
                rel = "inputs/%s.%s" % (stem, a["ext"])
                shutil.copyfile(a["src"], film.path("inputs", "%s.%s" % (stem, a["ext"])))
                item = {"kind": a["kind"], "file": rel}
                if a["kind"] == "image":
                    m.setdefault("images", {})[stem] = rel
                    item.update(name=stem, w=a.get("w"), h=a.get("h"))
                elif a["kind"] == "text":
                    item.update(name=a.get("name") or "", chars=a.get("chars"))
                    item.update(words=a.get("words"))
                else:
                    item.update(secs=a.get("secs"), transcript=a.get("transcript") or "")
                    item.update(lang=a.get("lang"))
                attached.append(item)
        m["duration"], m["poster_t"] = float(seconds), round(seconds - 0.4, 2)
        m["fps"] = 30 if fps == 30 else 60  # the plan's: Free films 30, paid ones 60
        m["engine"] = "engine"
        m["cast"] = "cast"  # every cast/*.js loads before film.js (sketch-render)
        if modules(caps):  # engine/<name>.js, its own copy, loaded after props.js
            m["modules"] = list(modules(caps))
        if paint_kinds(caps):
            m["paint"] = "paint.json"
            pins = paint_pins(seconds, caps)
            _write_json(film.path("paint.json"), pins | {"style": "", "images": []})
        if fonts(caps):
            m["fonts"] = list(m.get("fonts") or []) + fonts(caps)
        _write_json(film.manifest, m)
        vo = {**VO_PINNED, "model": tts_model(), "voice": "Kore", "style": "", "language": "en"}
        _write_json(film.path("vo.json"), vo | {"lines": []})
        _write_json(
            film.path("studio.json"),
            {
                "id": fid,
                "prompt": prompt,
                "look": look,
                "caps": list(caps),  # what its look was made of when it was made (CAPS)
                "length": seconds,  # the film's; "seconds" is later how long making it took
                "client": client,
                "source": source,
                # 1: a plan whose films go ahead of the others in every queue (sched.py)
                "priority": 1 if priority else 0,
                # api: the public key (billed); login: this machine's Claude Code (local only)
                "auth": auth,
                # a Free-plan film: KitCut's watermark and closing (agent.brand, studio/outro.js)
                "branding": bool(branding),
                "fps": 30 if fps == 30 else 60,
                # pictures, voice notes and documents the visitor attached (inputs/): never
                # shown publicly
                "attachments": attached,
                # the project it is an episode of (never shown publicly: the brief is theirs)
                **({"project": project} if project else {}),
                # false: link-only -- out of the gallery and the sitemap, watchable by its link
                "listed": bool(listed),
                # the assistant it was asked for through (source "mcp"), e.g. "Claude"
                **({"app": str(app)[:40]} if app else {}),
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
