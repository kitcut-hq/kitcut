#!/usr/bin/env python
"""A finished film in another language: kitcut.ai's Translate (the site's lib/localize.js).

    python studio/localize.py --plan <film id> <language>   what a translation of that film would be,
                                                             or why it would be refused; writes nothing

The site asks POST /api/films {"localize": {"from", "version", "language", "key"}, "listed"?} as
the original's own client, with a film's usual headers. The studio makes it as a FILM OF ITS OWN
(a new id, its own page and record): the original's code, pictures, cast, engine, music and voice
are laid into the new film's folder (seed), its narration's words are the original's, to be
translated, and Claude's first message (ask) is to translate the narration and every word the film
writes on screen into that language -- keeping everything else -- record the narration again in
the same voice, and fit what moves on screen to the new recording. Nothing is painted again.

What is never carried: the original's narration takes and its mix (audio/), its renders
(outputs/, web/), its YouTube drafts and thumbnails (youtube/), its share block, card and stills,
its notes, versions and records. The translated film writes all of those anew, in its language --
so its YouTube words and thumbnails are written for it, never copied (the site sends `language`
and `fresh` with the draft ask too: ytdraft.py).

Refused, before anything is made (409 {reason}): a film that is not finished (state), one whose next
version is being made (round), one told in the person's own ElevenLabs voice asked without a
fresh pass to that same voice (own_voice: the site mints one, lib/narrator.js prepare, and sends it
as `voice`), one already in that language (same), one that
has a film in that language done or being made (exists, with its id), and, not yet supported, a
film made scene by scene (long). 400 for a language that is not one of LANGUAGES (never Russian).
404 for a film that is not the asker's.

Taken as they are: a film made from a template (its words are in content.json, translated with
film.js; its template/ pictures carried), one with people drawn from photos (their rigs carried,
never drawn again; their mouths move to the new recording), and one with no narration (only the
words on screen are translated, and it fails if none of its words changed). The pictures it
brought in from the web (web/) are carried too: they are its own, SK.image('web_...').

Asking twice with one key is one film: a film whose record has that key is answered again (the
site asks once more when it got no answer, and finds the film by its key before giving the
credits back).

After Claude's part (agent.make_film): a narration left as the original's (untranslated) fails the
film, so its credits go back; words of the original still in film.js get one short turn to go
(leftovers), never a failure -- names and brands rightly stay. A film with no narration whose
film.js and content.json are both the original's word for word fails the same way (unchanged).
"""

import os
import re
import sys
import json
import shutil
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import clients  # noqa: E402
from film import Film, _write_json  # noqa: E402

# The languages kitcut.ai offers (its lib/languages.js): Latin and Cyrillic alphabets, the ones every
# typeface on screen carries. Never Russian.
LANGUAGES = {
    "en": "English", "es": "Spanish", "fr": "French", "de": "German", "it": "Italian",
    "pt": "Portuguese", "uk": "Ukrainian", "pl": "Polish", "nl": "Dutch", "sv": "Swedish",
    "da": "Danish", "no": "Norwegian", "fi": "Finnish", "cs": "Czech", "ro": "Romanian",
    "hu": "Hungarian", "tr": "Turkish", "id": "Indonesian", "bg": "Bulgarian",
}  # fmt: skip
KEY = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
FILM_ID = re.compile(r"^studio-\d{8}-\d{6}(?:-[a-z0-9]{6})?$")
MAKING = ("queued", "running", "finishing", "waiting")
SCAN = 400  # the newest films looked through for a key or a language already made

# What of the original's folder the new film is given. Everything else is the original's own
# record of its making, or something the translation makes again in its language.
NOT_CARRIED = {
    "studio.json", "events.jsonl", "temp", "versions", "library", "youtube", "share", "outputs",
    "notes", "drafts", "link", "stills", "shots", "audio", "localize", "project.json",
    "journal.md",
}  # fmt: skip
# Inside what is carried, what is still the original's own record: what drawing its people cost
# (agent counts rigs/spend.jsonl into the film's cost) and any video a folder holds.
NOT_CARRIED_FILES = {"spend.jsonl"}
NOT_CARRIED_EXT = (".mp4", ".webm", ".mov")
WORDS_IN = ("film.js", "content.json", "words.json")  # where a film writes the words it shows
SOURCE = "localize"  # in the new film: the original's narration, as it was, read-only


class Refused(Exception):
    def __init__(self, status, reason, error, **extra):
        super().__init__(error)
        self.status, self.reason, self.error, self.extra = status, reason, error, extra

    def body(self):
        return {"reason": self.reason, "error": self.error, **self.extra}


def _read(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def language_of(film):
    """The language a finished film speaks: its vo.json's, as the studio records it."""
    vo = _read(film.path("vo.json"), {}) or {}
    return str(vo.get("language") or "en").lower().split("-")[0]


def _round_making(film):
    try:
        import rounds  # noqa: PLC0415 -- it imports the agent, which imports this module

        return os.path.exists(rounds._mark(film.id))  # noqa: SLF001
    except Exception:  # noqa: BLE001 -- a check that cannot be made refuses nothing
        return False


def recent(n=SCAN):
    """The newest films on this machine, for a key or a language already asked for."""
    out = []
    for f in Film.all():
        out.append(f)
        if len(out) >= n:
            break
    return out


def by_key(key, films=None):
    """The film already made for this key (asked twice: one film), or None."""
    for f in films if films is not None else recent():
        if (f.record().get("localized") or {}).get("key") == key:
            return f
    return None


def made_in(src_id, lang, films=None):
    """A film of that original in that language, done or being made, or None."""
    for f in films if films is not None else recent():
        loc = f.record().get("localized") or {}
        if loc.get("from") == src_id and loc.get("language") == lang:
            if f.record().get("state") in MAKING + ("done",):
                return f
    return None


def check(spec, client, films=None, narrator=None):
    """The original and the language asked for, checked: (source Film, language, key, version).
    Raises Refused. client: the asker (the site sends the original's own client). narrator: the
    request's own voice (server.narrator_of) -- a film told in its person's own ElevenLabs voice
    is translated only with a fresh pass to that same voice.
    """
    if not isinstance(spec, dict):
        raise Refused(400, "localize", 'localize must be {"from", "version", "language", "key"}')
    src_id, lang = str(spec.get("from") or ""), str(spec.get("language") or "").lower()
    key = str(spec.get("key") or "")
    if not FILM_ID.match(src_id):
        raise Refused(400, "localize", "localize.from is not a film id")
    if lang not in LANGUAGES:  # never Russian, and nothing the site does not offer
        raise Refused(400, "language", "localize.language must be one of %s" % ", ".join(LANGUAGES))
    if not KEY.match(key):
        raise Refused(400, "localize", "localize.key must be the site's hold id")
    src = Film.open(src_id)
    if src is None or not clients.same(src.record().get("client"), client):
        raise Refused(404, "localize", "no such film")
    rec = src.record()
    if rec.get("state") != "done" or not os.path.exists(src.path("film.js")):
        raise Refused(409, "state", "the film is not finished")
    if _round_making(src):
        raise Refused(409, "round", "a new version of the film is being made")
    own = rec.get("narrator") or {}
    if own.get("source") == "elevenlabs":
        n = narrator or {}
        if n.get("source") != "elevenlabs" or not n.get("grant"):
            raise Refused(
                409,
                "own_voice",
                "the film is told in its person's own ElevenLabs voice: ask "
                "with a pass to it (voice)",
            )
        if n.get("voice") != own.get("voice"):
            raise Refused(
                409,
                "own_voice",
                "the voice asked with is not the one the film is told in",
                voice=own.get("voice"),
            )
    if language_of(src) == lang:
        raise Refused(409, "same", "the film is in that language already")
    there = made_in(src.id, lang, films)
    if there is not None:
        raise Refused(409, "exists", "the film has that language already", film=there.id)
    try:
        version = int(spec.get("version") or rec.get("version") or 1)
    except (TypeError, ValueError):
        version = int(rec.get("version") or 1)
    return src, lang, key, version


def create_args(src):
    """What Film.create is given for a translation of src: its idea, length, look, frame and the
    rest, as the original was made.
    """
    rec = src.record()
    caps = rec.get("caps") or []
    return {
        "prompt": rec.get("prompt") or "",
        "seconds": int(rec.get("length") or 30),
        "look": rec.get("look") or "drawn",
        "project": rec.get("project"),
        "frame": rec.get("frame"),
        "captions": "captions" in caps,
        "music": rec.get("music") != "none",
    }


def source_vo(src):
    """The original's narration: its vo.json, or the "vo" its manifest holds inline (a film built
    by hand and imported, such as a Short cut from a long film). {} when it has none."""
    vo = _read(src.path("vo.json"), None)
    if isinstance(vo, dict):
        return vo
    m = _read(src.manifest, {}) or {}
    return dict(m["vo"]) if isinstance(m.get("vo"), dict) else {}


def narrated(src):
    """Whether the original has a narration to translate (a template's is often music only)."""
    if src.record().get("narration") is False:
        return False
    return bool(source_vo(src).get("lines"))


GAP_S = 0.12  # the least quiet kept between one line's last word and the next line
FADE_S = 0.6  # the last line ends this far before the film does (the closing fade)


def slots(vo, timeline, duration):
    """Where each line of the original was said, and by when its translation must be done: the
    picture's clock is the original's, so line i starts where it did and ends before line i+1
    starts (or, the last, before the closing fade). [{i, start, end_by}]."""
    said = {int(L["i"]): L for L in (timeline or {}).get("lines") or [] if "i" in L}
    lines = vo.get("lines") or []
    starts = []
    for i, ln in enumerate(lines):
        L = said.get(i) or {}
        st = L.get("start", ln.get("start") if isinstance(ln, dict) else None)
        starts.append(None if st is None else float(st))
    out = []
    for i, st in enumerate(starts):
        if st is None:
            return []  # a narration that was never timed: nothing to hold it to
        nxt = next((x for x in starts[i + 1 :] if x is not None), None)
        was_end = float((said.get(i) or {}).get("end") or st)
        end_by = (nxt - GAP_S) if nxt is not None else (float(duration) - FADE_S)
        out.append({"i": i, "start": round(st, 3), "end_by": round(max(end_by, was_end), 3)})
    return out


def _ignore(_dir, names):
    return [n for n in names if n in NOT_CARRIED_FILES or n.lower().endswith(NOT_CARRIED_EXT)]


def seed(film, src, lang, version, key):
    """Lay the original into the new film's folder (Film.create made it): its code, pictures,
    cast, engine and music as the film's own, its narration's words to translate, and the
    original's narration in localize/ to read. The record says what it is (localized).
    """
    fps = (_read(film.manifest, {}) or {}).get(
        "fps"
    )  # this film's own (the plan's), before the copy
    for name in sorted(os.listdir(src.dir)):
        if name in NOT_CARRIED:
            continue
        a, b = src.path(name), film.path(name)
        if os.path.isdir(a):
            if os.path.isdir(b):
                shutil.rmtree(b)
            shutil.copytree(a, b, symlinks=False, ignore=_ignore)
        elif os.path.isfile(a) and not _ignore(src.dir, [name]):
            shutil.copyfile(a, b)
    # the manifest: the original's, at this film's own frame rate (the plan's)
    m = _read(film.manifest, {}) or {}
    if m and fps:
        m["fps"] = fps
        _write_json(film.manifest, m)
    # the narration: the same voice, its style and characters' voices; its language the new one;
    # its lines the original's, for Claude to translate and record. A film with none has none.
    os.makedirs(film.path(SOURCE), exist_ok=True)
    voiced = narrated(src)
    if voiced:
        vo = source_vo(src)
        _write_json(film.path(SOURCE, "vo.json"), vo)
        tl = src.path("audio", "vo", "timeline.json")
        if os.path.exists(tl):
            shutil.copyfile(tl, film.path(SOURCE, "timeline.json"))
        # every line starts where the original's did: the picture keeps the original's clock
        held = slots(vo, _read(tl, {}), (_read(src.manifest, {}) or {}).get("duration") or 0)
        lines = [dict(x) if isinstance(x, dict) else {"text": str(x)} for x in vo["lines"]]
        for sl in held:
            lines[sl["i"]]["start"] = sl["start"]
            lines[sl["i"]].pop("pause", None)
        _write_json(film.path(SOURCE, "slots.json"), held)
        _write_json(film.path("vo.json"), {**vo, "language": lang, "lines": lines})
        if isinstance(m.get("vo"), dict):  # inline in the manifest: the studio's own vo.json now
            m["vo"] = "vo.json"
            _write_json(film.manifest, m)
    elif os.path.exists(film.path("vo.json")):
        os.remove(film.path("vo.json"))  # Film.create's empty one: nothing is recorded
    if not os.path.exists(src.path("words.json")) and os.path.exists(film.path("words.json")):
        os.remove(
            film.path("words.json")
        )  # Film.create's empty one: the original has its words in code
    rec = src.record()
    film.update(
        localized={"from": src.id, "version": version, "language": lang, "key": key},
        # one conversation, whatever its length: a translation changes words in the code there
        # is, scenes/ included, and never writes a film a scene at a time (scenes.py)
        mode="single",
        # the original's length, exactly (Film.create keeps only multiples of 5: a 23 s Short was 5)
        **({"length": rec["length"]} if rec.get("length") else {}),
        caps=rec.get("caps") or film.record().get("caps"),
        # the original's narrator; a film asked with its own voice's pass keeps the one it was
        # created with (the pass is in temp/voice.json, never in the record)
        **(
            {"narrator": rec["narrator"]}
            if rec.get("narrator") and not film.record().get("narrator")
            else {}
        ),
        **({"paint_quality": rec["paint_quality"]} if rec.get("paint_quality") else {}),
        **({"music": "none"} if rec.get("music") == "none" else {}),
        **({} if voiced else {"narration": False}),
    )


def ask(film):
    """Claude's first message for a translation: the words said and shown change, and nothing
    else does -- not a number, a colour, a size, a position or a line of code (check_film holds
    it to that afterwards).
    """
    from film import limits  # noqa: PLC0415

    loc = film.record().get("localized") or {}
    lang = LANGUAGES.get(loc.get("language"), loc.get("language"))
    n = film.length
    data = (
        " Its facts -- names, dates, places, people, every word it shows -- are in content.json "
        "(SK.DATA.content), which film.js reads: translate the words there, never its keys, "
        "links or file names."
        if os.path.exists(film.path("content.json"))
        else ""
    )
    if os.path.exists(film.path("words.json")):
        data += (
            " The words it shows are in words.json (SK.DATA.words), by name: translate the "
            "values there, never the names; film.js should need no change but its cue words."
        )
    same = (
        "The rule: ONLY WORDS CHANGE. Change only the text inside quotes that the film shows on "
        "screen (titles, labels, captions, lists, units, the words in content.json and the "
        "cast). Never change a number, a colour, a font, a size, a weight, an opacity, a "
        "position, a time, a file name, a key or any code -- not even to fit a longer word. "
        "Where a translation does not fit the space its original had, choose a shorter %s "
        "wording (an abbreviation a native designer would use) instead. Keep names, brands and "
        "numbers as they are unless %s writes them differently. After you stop, the studio "
        "compares every file with the original's and sends back anything else that changed."
        % (lang, lang)
    )
    scenes = scene_files(film)
    if scenes:
        same += (
            " The picture is also written in scenes/ (%d files, one a scene, loaded after "
            "film.js): the words they show are translated there too, under the same rule."
            % len(scenes)
        )
    mods = own_modules(film)
    if mods:
        same += (
            " Words on screen may also be in the film's own engine modules (%s: a scene layer "
            "that pins labels on things): translate those strings there too, under the same rule. "
            "A string such code looks something up by -- a cue word of another film's timeline, a "
            "key, a name -- is not a word: leave it." % ", ".join(mods)
        )
    keep = (
        "Keep everything else exactly as it is: the scenes, the pictures (never paint or draw "
        "new ones; words inside a picture stay), the people, the camera, the motion, the "
        "colours, the music and the sounds. It is a translation, not a new version."
    )
    work = "Your working time: about %d minutes (waiting for the machine is not counted)." % (
        limits(n)["claude_s"] // 60
    )
    if film.record().get("narration") is False:
        return "\n\n".join(
            [
                "Translate the film into %s. It is a finished film with no narration -- its music "
                "carries it -- so the only thing that changes is the words it shows on screen."
                % lang,
                "What you have: the original's own code (film.js, its cast in cast/, its "
                "engine), its pictures and its music.%s Do not write a vo.json and do not record "
                "anything. %s" % (data, work),
                same + " Call check, look at stills where words changed length, and stop.",
                keep,
            ]
        )
    held = _read(film.path(SOURCE, "slots.json"), []) or []
    table = "\n".join(
        "  line %d: starts at %.2f s, must be said by %.2f s (%.1f s)"
        % (x["i"], x["start"], x["end_by"], x["end_by"] - x["start"])
        for x in held
    )
    return "\n\n".join(
        [
            "Translate the film into %s: the same film, said and written in %s. Only the words "
            "change; the picture, its timing and everything else stay the original's."
            % (lang, lang),
            "What you have: the original's own code (film.js, its cast in cast/, its engine), its "
            "pictures and its music. vo.json is its narration -- the voice, the way it is read "
            "(style), the characters' voices and its %d lines, still in the original language "
            "(vo.json's language is %s already). localize/vo.json and localize/timeline.json are "
            "the original's narration and its word times, to read.%s %s"
            % (
                len(held) or len((_read(film.path("vo.json"), {}) or {}).get("lines") or []),
                lang,
                data,
                work,
            ),
            "The picture keeps the original's clock: every line of vo.json carries its `start`, "
            "where the original said it -- never change it -- and its translation must be said "
            "before the next line starts:\n%s" % (table or "  (the lines as they are)"),
            "Do this:\n"
            "1. Translate every narration line in vo.json into natural, spoken %s -- what a native "
            "narrator would say -- keeping the number of lines, what each says and the tone, and "
            "short enough to be said comfortably in its time above (a %s line runs longer than "
            "English: say it more briefly rather than faster).\n"
            "2. Translate the words on screen, under the rule below.\n"
            "3. Record the narration with the voice tool, in the same voice. A line that runs past "
            "its time: say it more briefly in vo.json and record that line again.\n"
            "4. A cue placed on a word (SK.w(line, 'word')) now names the translated word that "
            "carries the same meaning; that is the one kind of quoted text that is not shown."
            % (lang, lang),
            same,
            keep,
        ]
    )


def _lines(vo):
    return [
        " ".join(str(x.get("text") if isinstance(x, dict) else x).split())
        for x in vo.get("lines") or []
    ]


def _text(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None


def unchanged(film):
    """A translation with no narration whose words on screen (film.js, content.json) are all the
    original's, as they were: nothing was translated. Such a film fails (its credits go back)."""
    loc = film.record().get("localized") or {}
    if not loc.get("from") or film.record().get("narration") is not False:
        return False
    src = Film.open(loc["from"])
    if src is None:
        return False
    return all(_text(src.path(n)) == _text(film.path(n)) for n in WORDS_IN)


def untranslated(film):
    """Whether the narration is still the original's: at least a third of its lines of four or
    more words word for word the same -- or, for a film with no narration, nothing it shows
    changed (unchanged). Such a film fails (its credits go back).
    """
    if not (film.record().get("localized") or {}).get("from"):
        return False
    if film.record().get("narration") is False:
        return unchanged(film)
    now = _lines(_read(film.path("vo.json"), {}) or {})
    was = _lines(_read(film.path(SOURCE, "vo.json"), {}) or {})
    long_was = {w.lower() for w in was if len(w.split()) >= 4}
    if not long_was:
        return False
    same = sum(1 for w in now if w.lower() in long_was)
    return same * 3 >= len(long_was)


WORDS = re.compile(r"""(['"`])((?:(?!\1)[^\\\n]|\\.){12,200})\1""")
CODEISH = re.compile(r"\d+px|\b(?:rgba?|hsla?)\(|#[0-9a-fA-F]{3,8}\b|\$\{|=>|\bfunction\b")


def _strings(code):
    return {s for _, s in WORDS.findall(code or "") if " " in s and not CODEISH.search(s)}


KIT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sketch")


def own_modules(film):
    """The film's own engine modules: engine/*.js that are not the kit's (sketch/) -- a scene
    layer built for this film or its series, which may pin words on things (engine/padel.js)."""
    d = film.path("engine")
    if not os.path.isdir(d):
        return []
    return sorted(
        "engine/" + x
        for x in os.listdir(d)
        if x.endswith(".js") and not os.path.exists(os.path.join(KIT, x))
    )


def scene_files(film):
    """A film made a scene at a time keeps part of its picture in scenes/<id>.js."""
    d = film.path("scenes")
    return (
        sorted("scenes/" + x for x in os.listdir(d) if x.endswith(".js"))
        if os.path.isdir(d)
        else []
    )


def leftovers(film):
    """Words the original showed that film.js or content.json still shows word for word: at most
    eight."""
    if not (film.record().get("localized") or {}).get("from"):
        return []
    src = Film.open(film.record()["localized"]["from"])
    if src is None:
        return []
    left = set()
    for name in WORDS_IN + tuple(own_modules(src)) + tuple(scene_files(src)):
        was, now = _text(src.path(*name.split("/"))), _text(film.path(*name.split("/")))
        if was is not None and now is not None:
            left |= _strings(was) & _strings(now)
    return sorted(left)[:8]


LEFTOVERS = (
    "These words are still in the original's language on screen: %s. Translate each one where "
    "it is written, in film.js or content.json (keep a name or a brand as it is), call check, "
    "and stop with one sentence."
)


# ---------------------------------------------------------------- only the words changed
# check_film compares the translation with its original, file by file, after Claude's part: any
# change that is not a word on screen or a word said is a problem, sent back once to be put back,
# and a film that still has one fails (its credits go back). Its report is localize/check.json.

CODE_FILES = ("film.js",)
SAME_FILES = ("score.json", "sfx.json", "paint.json")  # the same, as JSON
PAINT_PINS = {"backend", "model", "style_ref", "quality"}
SAME_DIRS = ("images", "web", "assets", "template", "rigs", "inputs", "music")
# words a film's code uses as settings, never shown: never translated
SETTINGS = set(
    """left right center centre middle top bottom start end top-left top-right bottom-left
    bottom-right bold bolder lighter normal italic oblique round butt square miter bevel
    source-over multiply screen overlay lighten darken destination-out destination-in
    lighter copy xor transparent white black red green blue yellow orange purple pink grey gray
    none auto alphabetic hanging ideographic ltr rtl inherit evenodd nonzero""".split()
)
WORDY = re.compile(r"[^\W\d_]", re.UNICODE)  # a letter
KEYISH = re.compile(r"^[A-Za-z0-9_$./:#@-]+$")
TS = re.compile(r"[ \t\r\n]+")


def _js_tokens(code):
    """film.js as tokens, comments dropped: [(kind, text, line)], kind in str|tpl|num|code."""
    out, i, n, line = [], 0, len(code), 1
    prev = ""

    def regex_ok():
        return (
            prev == ""
            or prev in set("(,=:[!&|?{};+-*%<>~^")
            or prev
            in (
                "return",
                "typeof",
                "case",
                "=>",
                "in",
                "of",
                "new",
                "delete",
                "void",
                "throw",
            )
        )

    while i < n:
        c = code[i]
        if c == "\n":
            line += 1
            i += 1
        elif c in " \t\r":
            i += 1
        elif code.startswith("//", i):
            j = code.find("\n", i)
            i = n if j < 0 else j
        elif code.startswith("/*", i):
            j = code.find("*/", i + 2)
            j = n if j < 0 else j + 2
            line += code.count("\n", i, j)
            i = j
        elif c in "'\"":
            j = i + 1
            while j < n and code[j] != c:
                j += 2 if code[j] == "\\" else 1
            out.append(("str", code[i + 1 : j], line))
            i, prev = j + 1, "str"
        elif c == "`":
            j, depth = i + 1, 0
            while j < n and not (code[j] == "`" and depth == 0):
                if code[j] == "\\":
                    j += 2
                    continue
                if code.startswith("${", j):
                    depth += 1
                    j += 2
                    continue
                if code[j] == "}" and depth:
                    depth -= 1
                elif code[j] == "\n":
                    line += 1
                j += 1
            out.append(("tpl", code[i + 1 : j], line))
            i, prev = j + 1, "str"
        elif c.isdigit() or (c == "." and i + 1 < n and code[i + 1].isdigit()):
            m = re.match(
                r"0[xX][0-9a-fA-F_]+|(?:\d[\d_]*\.?\d*|\.\d+)(?:[eE][+-]?\d+)?n?", code[i:]
            )
            out.append(("num", m.group(0), line))
            i, prev = i + len(m.group(0)), "num"
        elif c == "/" and regex_ok():
            j, cls = i + 1, False
            while j < n and code[j] != "\n":
                if code[j] == "\\":
                    j += 2
                    continue
                if code[j] == "[":
                    cls = True
                elif code[j] == "]":
                    cls = False
                elif code[j] == "/" and not cls:
                    break
                j += 1
            m = re.match(r"[a-z]*", code[j + 1 :])
            out.append(("code", code[i : j + 1 + len(m.group(0))], line))
            i, prev = j + 1 + len(m.group(0)), "re"
        elif c.isalpha() or c in "_$":
            m = re.match(r"[\w$]+", code[i:])
            out.append(("code", m.group(0), line))
            i, prev = i + len(m.group(0)), m.group(0)
        else:
            three = code[i : i + 3]
            tok = (
                three
                if three in ("===", "!==", "...", "**=", ">>>", "<<=", ">>=")
                else (
                    code[i : i + 2]
                    if code[i : i + 2]
                    in (
                        "=>",
                        "==",
                        "!=",
                        "<=",
                        ">=",
                        "&&",
                        "||",
                        "??",
                        "?.",
                        "++",
                        "--",
                        "+=",
                        "-=",
                        "*=",
                        "/=",
                        "**",
                    )
                    else c
                )
            )
            out.append(("code", tok, line))
            i, prev = i + len(tok), tok
    return out


def _tpl_parts(t):
    """A template literal's text and its ${...} expressions, apart."""
    texts, exprs, i, depth, cur = [], [], 0, 0, ""
    while i < len(t):
        if depth == 0 and t.startswith("${", i):
            texts.append(cur)
            cur, depth, i = "", 1, i + 2
            continue
        if depth:
            if t[i] == "{":
                depth += 1
            elif t[i] == "}":
                depth -= 1
                if depth == 0:
                    exprs.append(TS.sub(" ", cur).strip())
                    cur, i = "", i + 1
                    continue
        cur += t[i]
        i += 1
    texts.append(cur)
    return texts, exprs


def _reserved(film):
    """Strings a film uses as names, never shown: its pictures', fonts', cast's and sounds' keys."""
    m = _read(film.manifest, {}) or {}
    names = set((m.get("images") or {}).keys())
    names |= {str(f.get("family")) for f in m.get("fonts") or [] if isinstance(f, dict)}
    for d in ("cast", "actors"):
        if os.path.isdir(film.path(d)):
            names |= {os.path.splitext(x)[0] for x in os.listdir(film.path(d))}
    return names


def wordish(s, reserved=()):
    """Whether a quoted string is words a person reads or hears (it may be translated), not a
    setting, a key, a colour, a font or a file."""
    t = s.strip()
    if not t or not WORDY.search(t) or t in reserved or t.lower() in SETTINGS:
        return False
    if CODEISH.search(t) or re.search(
        r"\d(?:px|em|rem|pt|%)\b|\.(?:png|jpe?g|webp|svg|mp3|wav|json|js|ttf|otf)\b", t
    ):
        return False
    bare = t.rstrip(":;,.!?")  # "Source:" is a word with its colon
    if " " not in bare and KEYISH.match(bare) and re.search(r"[_./#:$@]|^[A-Za-z]+\d+$", bare):
        return False  # web_logo, p1, L01, assets/x.png, #fff and 12:30 stay; "21st" is a word
    return True


def _code_diff(name, was, now, reserved):
    """What changed in one code file beyond its words: [problem]."""
    a, b = _js_tokens(was), _js_tokens(now)
    probs = []
    if len(a) != len(b):
        k = next(
            (
                k
                for k, (x, y) in enumerate(zip(a, b))
                if x[0] != y[0] or (x[0] in ("code", "num") and x[1] != y[1])
            ),
            min(len(a), len(b)),
        )
        ln = b[k][2] if k < len(b) else (b[-1][2] if b else 0)
        return [
            "%s: the code changed near line %d (%d tokens, the original had %d)"
            % (name, ln, len(b), len(a))
        ]
    for x, y in zip(a, b):
        if x[0] != y[0]:
            probs.append("%s line %d: %s became %s" % (name, y[2], x[1][:40], y[1][:40]))
        elif x[0] in ("code", "num"):
            if x[1] != y[1]:
                probs.append("%s line %d: %s changed to %s" % (name, y[2], x[1][:40], y[1][:40]))
        elif x[0] == "str":
            if x[1] != y[1] and not wordish(x[1], reserved):
                probs.append(
                    "%s line %d: '%s' is not a word on screen; it changed to '%s'"
                    % (name, y[2], x[1][:40], y[1][:40])
                )
        else:  # a template literal: its ${...} parts are code
            (ta, ea), (tb, eb) = _tpl_parts(x[1]), _tpl_parts(y[1])
            if ea != eb:
                probs.append("%s line %d: the code inside `...${}` changed" % (name, y[2]))
            elif ta != tb and not any(wordish(t, reserved) for t in ta):
                probs.append(
                    "%s line %d: `%s` is not words on screen; it changed" % (name, y[2], x[1][:40])
                )
        if len(probs) >= 12:
            break
    return probs


def _json_diff(name, was, now, reserved, path=""):
    """What changed in a JSON file beyond its words (strings may change only where they are
    words): [problem]."""
    if type(was) is not type(now):
        return ["%s %s: changed from %r" % (name, path or "(whole)", str(was)[:40])]
    if isinstance(was, dict):
        if set(was) != set(now):
            return [
                "%s %s: keys changed (%s)"
                % (name, path or "(top)", ", ".join(sorted(set(was) ^ set(now)))[:80])
            ]
        out = []
        for k in was:
            out += _json_diff(name, was[k], now[k], reserved, "%s.%s" % (path, k) if path else k)
        return out
    if isinstance(was, list):
        if len(was) != len(now):
            return ["%s %s: %d items, the original had %d" % (name, path, len(now), len(was))]
        out = []
        for k, (x, y) in enumerate(zip(was, now)):
            out += _json_diff(name, x, y, reserved, "%s[%d]" % (path, k))
        return out
    if isinstance(was, str):
        return (
            []
            if was == now or wordish(was, reserved)
            else ["%s %s: '%s' changed to '%s'" % (name, path, was[:40], now[:40])]
        )
    return [] if was == now else ["%s %s: %r changed to %r" % (name, path, was, now)]


def _files(root):
    out = {}
    for dp, _dn, fn in os.walk(root):
        for f in fn:
            if f in NOT_CARRIED_FILES or f.lower().endswith(NOT_CARRIED_EXT):
                continue
            p = os.path.join(dp, f)
            out[os.path.relpath(p, root).replace(os.sep, "/")] = p
    return out


def _same_bytes(a, b):
    try:
        if os.path.getsize(a) != os.path.getsize(b):
            return False
        with open(a, "rb") as fa, open(b, "rb") as fb:
            return fa.read() == fb.read()
    except OSError:
        return False


VO_SAME = ("voice", "style", "cast")  # the narrator, as the original had it (tts, model and
# takes are the studio's own settings, pinned on every film: guard.pin_vo)


def overruns(film):
    """Lines of the translation's recording that run past their slot, or start elsewhere:
    [problem]."""
    held = _read(film.path(SOURCE, "slots.json"), []) or []
    tl = _read(film.path("audio", "vo", "timeline.json"), {}) or {}
    said = {int(L["i"]): L for L in tl.get("lines") or [] if "i" in L}
    out = []
    for sl in held:
        L = said.get(sl["i"])
        if L is None:
            out.append("line %d was not recorded" % sl["i"])
            continue
        if abs(float(L.get("start", 0)) - sl["start"]) > 0.02:
            out.append(
                "line %d starts at %.2f s; the original's started at %.2f s"
                % (sl["i"], float(L["start"]), sl["start"])
            )
        if float(L.get("end", 0)) > sl["end_by"] + 0.05:
            out.append(
                "line %d ends at %.2f s, %.2f s past its time (it must be said by %.2f s): say it more briefly"
                % (sl["i"], float(L["end"]), float(L["end"]) - sl["end_by"], sl["end_by"])
            )
    return out


def words_in_code(film, limit=10):
    """Words a film writes in film.js itself instead of words.json: quoted strings that read as
    words on screen (wordish, and a few words or a capital), never a cue word (SK.w(line, 'word'))."""
    code = _text(film.path("film.js"))
    if code is None:
        return []
    toks, reserved, out = _js_tokens(code), _reserved(film), []
    for i, (kind, s, _ln) in enumerate(toks):
        if kind != "str" or not wordish(s, reserved):
            continue
        if not (" " in s.strip() or s[:1].isupper()):
            continue
        cue = i >= 4 and toks[i - 1][1] == "," and toks[i - 3][1] == "(" and toks[i - 4][1] == "w"
        if not cue and s not in out:
            out.append(s)
        if len(out) >= limit:
            break
    return out


def check_film(film):
    """Everything in the translation that is not the original's words, translated: {"ok",
    "problems", "words", "files"}. Words said and shown may change; nothing else may."""
    loc = film.record().get("localized") or {}
    src = Film.open(loc.get("from") or "")
    if src is None:
        return {"ok": True, "problems": [], "words": 0, "files": 0, "note": "no original"}
    reserved = _reserved(src)
    probs, files, words = [], 0, 0
    # the code: film.js and the cast, token by token
    code = list(CODE_FILES) + [
        "%s/%s" % (d, x)
        for d in ("cast", "engine", "scenes")
        if os.path.isdir(src.path(d))
        for x in sorted(os.listdir(src.path(d)))
        if x.endswith(".js")
    ]
    for name in code:
        was, now = _text(src.path(*name.split("/"))), _text(film.path(*name.split("/")))
        if was is None:
            continue
        files += 1
        if now is None:
            probs.append("%s is gone" % name)
            continue
        probs += _code_diff(name, was, now, reserved)
        words += sum(
            1
            for x, y in zip(_js_tokens(was), _js_tokens(now))
            if x[0] in ("str", "tpl") and x[1] != y[1]
        )
    # the data, the manifest and the sound: as JSON, only words may change
    m_was, m_now = _read(src.manifest, {}) or {}, _read(film.manifest, {}) or {}
    for d in (m_was, m_now):
        for k in ("vo", "fps", "_from"):
            d.pop(k, None)
    files += 1
    probs += _json_diff("sketch.json", m_was, m_now, reserved)
    if os.path.exists(src.path("content.json")):
        files += 1
        probs += _json_diff(
            "content.json",
            _read(src.path("content.json")),
            _read(film.path("content.json")),
            reserved,
        )
    if os.path.exists(src.path("words.json")):
        files += 1
        probs += _json_diff(
            "words.json", _read(src.path("words.json")), _read(film.path("words.json")), reserved
        )
    for name in SAME_FILES:
        if os.path.exists(src.path(name)):
            files += 1
            a, b = _read(src.path(name)), _read(film.path(name))
            if name == "paint.json" and isinstance(a, dict) and isinstance(b, dict):
                # which service paints is the studio's setting (pin_paint), not the film's: the
                # pictures themselves are compared byte for byte below
                a, b = ({k: v for k, v in x.items() if k not in PAINT_PINS} for x in (a, b))
            if a != b:
                probs.append("%s changed: it must stay the original's" % name)
    for d in SAME_DIRS:
        a, b = _files(src.path(d)), _files(film.path(d))
        for rel, pa in a.items():
            files += 1
            if rel not in b or not _same_bytes(pa, b[rel]):
                probs.append("%s/%s changed or is gone" % (d, rel))
        for rel in sorted(set(b) - set(a)):
            if d != "rigs":
                probs.append(
                    "%s/%s is new: nothing is drawn or painted for a translation" % (d, rel)
                )
    # the narrator: the same voice and way of reading, the same number of lines
    if narrated(src):
        vw, vn = source_vo(src), _read(film.path("vo.json"), {}) or {}
        files += 1
        for k in VO_SAME:
            if vw.get(k) != vn.get(k):
                probs.append("vo.json %s changed: the narrator stays the original's" % k)
        if len(vw.get("lines") or []) != len(vn.get("lines") or []):
            probs.append(
                "vo.json has %d lines; the original had %d"
                % (len(vn.get("lines") or []), len(vw.get("lines") or []))
            )
        probs += overruns(film)
    return {"ok": not probs, "problems": probs[:40], "words": words, "files": files}


PUT_BACK = (
    "The studio compared the translation with the original. Only words may change, and these "
    "changed beyond that:\n%s\n\nPut each back exactly as the original has it (a line that runs "
    "long: say it more briefly in vo.json and record that line again), call check, and stop with "
    "one sentence."
)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--plan", nargs=2, metavar=("FILM", "LANGUAGE"), required=True)
    a = ap.parse_args()
    src = Film.open(a.plan[0])
    if src is None:
        sys.exit("no film %s" % a.plan[0])
    try:
        _, lang, _, v = check(
            {"from": src.id, "language": a.plan[1], "key": "plan"}, src.record().get("client")
        )
    except Refused as e:
        print("refused (%d %s): %s" % (e.status, e.reason, e.error))
        return
    carried = sorted(n for n in os.listdir(src.dir) if n not in NOT_CARRIED)
    print("%s v%d -> %s: carries %s" % (src.id, v, LANGUAGES[lang], ", ".join(carried)))


if __name__ == "__main__":
    main()
