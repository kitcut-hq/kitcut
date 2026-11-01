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
version is being made (round), one told in the person's own ElevenLabs voice (own_voice: its pass
to their account was for the making of that film), one already in that language (same), one that
has a film in that language done or being made (exists, with its id), and, not yet supported, a
film made from a template (template), made scene by scene (long) or with people drawn from photos
(people). 400 for a language that is not one of LANGUAGES (never Russian). 404 for a film that is
not the asker's.

Asking twice with one key is one film: a film whose record has that key is answered again (the
site asks once more when it got no answer, and finds the film by its key before giving the
credits back).

After Claude's part (agent.make_film): a narration left as the original's (untranslated) fails the
film, so its credits go back; words of the original still in film.js get one short turn to go
(leftovers), never a failure -- names and brands rightly stay.
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
    "web", "notes", "drafts", "link", "stills", "shots", "audio", "localize", "rigs", "template",
    "scenes", "project.json", "journal.md",
}  # fmt: skip
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


def check(spec, client, films=None):
    """The original and the language asked for, checked: (source Film, language, key, version).
    Raises Refused. client: the asker (the site sends the original's own client).
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
    if (rec.get("narrator") or {}).get("source") == "elevenlabs":
        raise Refused(409, "own_voice", "the film is told in its person's own ElevenLabs voice")
    if rec.get("template"):
        raise Refused(409, "template", "A film made from a template cannot be translated yet.")
    if rec.get("mode") == "scenes" or os.path.isdir(src.path("scenes")):
        raise Refused(409, "long", "A film made scene by scene cannot be translated yet.")
    if rec.get("people"):
        raise Refused(
            409, "people", "A film with people drawn from photos cannot be translated yet."
        )
    if rec.get("narration") is False or not (_read(src.path("vo.json"), {}) or {}).get("lines"):
        raise Refused(409, "no_voice", "A film with no narration has nothing to translate yet.")
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
            shutil.copytree(a, b, symlinks=False)
        elif os.path.isfile(a):
            shutil.copyfile(a, b)
    # the manifest: the original's, at this film's own frame rate (the plan's)
    m = _read(film.manifest, {}) or {}
    if m and fps:
        m["fps"] = fps
        _write_json(film.manifest, m)
    # the narration: the same voice, its style and characters' voices; its language the new one;
    # its lines the original's, for Claude to translate and record
    vo = _read(src.path("vo.json"), {}) or {}
    os.makedirs(film.path(SOURCE), exist_ok=True)
    _write_json(film.path(SOURCE, "vo.json"), vo)
    tl = src.path("audio", "vo", "timeline.json")
    if os.path.exists(tl):
        shutil.copyfile(tl, film.path(SOURCE, "timeline.json"))
    _write_json(film.path("vo.json"), {**vo, "language": lang})
    rec = src.record()
    film.update(
        localized={"from": src.id, "version": version, "language": lang, "key": key},
        caps=rec.get("caps") or film.record().get("caps"),
        **({"narrator": rec["narrator"]} if rec.get("narrator") else {}),
        **({"paint_quality": rec["paint_quality"]} if rec.get("paint_quality") else {}),
        **({"music": "none"} if rec.get("music") == "none" else {}),
    )


def ask(film):
    """Claude's first message for a translation: what to change (every word said and shown), and
    what to keep (everything else).
    """
    from film import limits  # noqa: PLC0415

    loc = film.record().get("localized") or {}
    lang = LANGUAGES.get(loc.get("language"), loc.get("language"))
    n = film.length
    lines = len((_read(film.path("vo.json"), {}) or {}).get("lines") or [])
    return "\n\n".join(
        [
            "Translate the film into %s. It is a finished film; make it again in %s and change "
            "nothing else." % (lang, lang),
            "Length: about %d seconds, the original's: a translation may come out a little longer "
            "or shorter; let it, and do not pad or rush the voice to match. Your working time: "
            "about %d minutes (waiting for the machine is not counted)."
            % (n, limits(n)["claude_s"] // 60),
            "What you have: the original's own code (film.js, its cast in cast/, its engine), its "
            "pictures and its music, all yours. vo.json is its narration -- the voice, the way it "
            "is read (style), the characters' voices and its %d lines, still in the original "
            "language; vo.json's language is %s already. localize/vo.json and localize/timeline.json "
            "are the original's narration and its word times, to read." % (lines, lang),
            "Do this:\n"
            "1. Translate every narration line in vo.json into natural, spoken %s -- what a native "
            "narrator would say, not word for word -- keeping the number of lines, what each says "
            "and about its length, and the same tone. Keep names, brands and numbers as they are "
            "unless %s writes them differently.\n"
            "2. Translate every word the film shows on screen (titles, labels, captions, lists, "
            "numbers' units, anything written in film.js or the cast) into %s. Keep the type, the "
            "sizes and the layout; where a translation is longer, fit it the way the film already "
            "fits text (a smaller size, a second line), never by cutting words.\n"
            "3. Record the narration with the voice tool, in the same voice.\n"
            "4. Fit what moves to the new recording: cues placed on words (SK.w(line, 'word')) "
            "point at the translated word that carries the same meaning; times written in seconds "
            "on the old narration (sfx.json, and any in film.js) move with their line "
            "(localize/timeline.json has where each line and word was)." % (lang, lang, lang),
            "Keep everything else as it is: the scenes and their order, the pictures (never paint "
            "or draw new ones; words inside a picture stay as they are), the characters, the "
            "camera, the motion, the colours, the music and the sounds. Do not improve, shorten or "
            "rewrite the story: it is a translation.",
        ]
    )


def _lines(vo):
    return [
        " ".join(str(x.get("text") if isinstance(x, dict) else x).split())
        for x in vo.get("lines") or []
    ]


def untranslated(film):
    """Whether the narration is still the original's: at least a third of its lines of four or
    more words word for word the same. Such a film fails (its credits go back).
    """
    if not (film.record().get("localized") or {}).get("from"):
        return False
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


def leftovers(film):
    """Words the original showed that film.js still shows word for word: at most eight."""
    if not (film.record().get("localized") or {}).get("from"):
        return []
    src = Film.open(film.record()["localized"]["from"])
    if src is None:
        return []
    try:
        with open(src.path("film.js"), encoding="utf-8") as f:
            was = _strings(f.read())
        with open(film.path("film.js"), encoding="utf-8") as f:
            now = _strings(f.read())
    except OSError:
        return []
    return sorted(was & now)[:8]


LEFTOVERS = (
    "These words are still in the original's language on screen: %s. Translate each one in "
    "film.js (keep a name or a brand as it is), call check, and stop with one sentence."
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
