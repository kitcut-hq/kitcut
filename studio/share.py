#!/usr/bin/env python
"""A finished film's share page: its title, a one-line description and a picture in its own look.

kitcut.ai gives every finished film a page of its own (kitcut.ai/v/<short>/<slug>) and reads what
to put on it from the film's record, `share`. It is written here when the film finishes, from the
same things the YouTube draft is written from (ytdraft.material: the narration with its times,
who it was made for, what Claude said, the pages its facts came from, the sheet of its moments),
in one Claude call with no tools: a title a person would click (at most 70 characters), a meta
description (at most 155), the film's language, and two thumbnail concepts. The picture is then
made by the YouTube thumbnail machinery (thumbs.py, scripts/_thumb.py: the film draws its own
frame and words in its own look), and cut to the page's two sizes (media.make_share):

    outputs/share.jpg   1200x628, the link preview (pillarboxed like card.jpg)
    outputs/thumb.jpg   1280x720, the thumbnail
    share/draft.json    the words and concepts, keyed by everything they were written from

Both pictures go online beside the film (media.py) as share-<v>.jpg and thumb-<v>.jpg, <v> a
hash of their bytes, so a remade picture gets a new URL. The record gets
    share = {title, description, language, image, thumb, at, key}
-- image and thumb only when they were made and copied. Nothing here ever fails a film: premake()
runs after the film is done, and a failure is logged (SHARE) and noted as share_error.

    python studio/share.py --film <id>              write (or remake) one film's share
    python studio/share.py --missing [--limit N]    every finished film without one, newest first
    python studio/share.py --missing --dry-run      which films, and what it would cost; no call

A draft costs about $0.05-0.13 on the key (one call, occasionally two); on the login it is counted
but not charged. Asking again costs nothing until the film changes.
"""

import os
import re
import sys
import json
import time
import asyncio
import hashlib
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "scripts"))
import agent  # noqa: E402 -- imports _env first
import film as films  # noqa: E402
import media  # noqa: E402
import thumbs  # noqa: E402
import ytdraft  # noqa: E402

MODEL = ytdraft.MODEL
EFFORT = ytdraft.EFFORT
TITLE_MAX = 70  # what a search result and a link preview show whole
DESC_MAX = 155  # a meta description, the same
CONCEPTS = 2  # thumbnail concepts asked for: the first is the one used, the second its fallback
LAYOUTS = ("headline", "card")  # the two that read at a link preview's size
CHANNEL = "share"  # thumbs.py's folder for the options: outputs/youtube/share/
GENERATED = re.compile(
    r"\b(ai[- ]generated|generated (by|with)|made (by|with) (ai|kitcut|claude)|"
    r"created (by|with) (ai|kitcut|claude))\b",
    re.IGNORECASE,
)
LANGUAGES = {
    "english": "en", "ukrainian": "uk", "ua": "uk", "spanish": "es", "russian": "ru",
    "german": "de", "french": "fr", "italian": "it", "portuguese": "pt", "polish": "pl",
    "dutch": "nl", "japanese": "ja", "chinese": "zh", "korean": "ko", "turkish": "tr",
    "arabic": "ar", "hindi": "hi", "czech": "cs", "swedish": "sv", "hebrew": "he",
    "greek": "el", "romanian": "ro", "hungarian": "hu", "finnish": "fi", "danish": "da",
    "norwegian": "no", "indonesian": "id", "vietnamese": "vi", "thai": "th",
}  # fmt: skip

WRITER = (
    "You write the title and the one-line description a finished film is shared with on its own "
    "web page, and choose the picture its link shows. You are given the film -- its narration as "
    "spoken, with times; who it was made for; what its maker said about it; the pages its facts "
    "came from; a sheet of its frames. Answer only with the JSON object asked for."
)

ASK = """\
Write the title and description this film is shared with: on its own page, and in the preview a \
link to it shows wherever it is posted. The film is the subject: say what it shows and says, for \
the people it was made for, so the right person clicks and knows what they will get.

- "title": at most 70 characters, no full stop at the end. A real title a person would click, \
the way a good publisher titles a film like this -- not a label, not the request restated, not \
"a video about".
- "description": at most 155 characters, one or two sentences saying what the film shows.
- "language": the film's language, as a short code ({language}). Write both in it.

Hold it to the film:
- Every fact comes from the narration, the pages listed, or what the maker said. Name no number, \
feature, date or claim the film does not make, and where the maker says something is unconfirmed, \
do not state more than the film does. Do not say the film was asked for, generated or made with AI.

Then choose two pictures for its link, made the way YouTube thumbnails are: one moment of the \
film, its subject pushed in large on one side, and a few big words on the other -- the only \
words on the picture (the film's own titles and labels are left out of it), set in the film's \
own title type and colours:
- "at": the moment, in seconds, from the sheet of its moments (the time is printed on every \
frame) -- one where the film's subject is on screen, large and fully drawn: a character, an \
object, a chart. Two different moments.
- "layout": one each of "headline" (the words large over the picture) and "card" (the words on \
the film's own label or card).
- "words": at most 4 words and 32 characters, in the film's language: the film's main message, \
the title's question or promise in fewer words, that makes the right person want to watch, held \
to the film like everything above. Star one word to colour it (write it as *word*).
- "place": the side the words go on, so they leave the subject clear: left, right, top or bottom.
Put first the one you would choose yourself.

Answer with one JSON object and nothing else:
{{"title": "...", "description": "...", "language": "en", "thumbnails": [{{"at": 0.0, \
"layout": "headline", "words": "...", "place": "top"}}, {{"at": 0.0, "layout": "card", \
"words": "...", "place": "left"}}]}}"""

TASKS = set()  # the premake tasks running: kept, so none is collected half-way


# ------------------------------------------------------------------ the ask
def ask_text(mat):
    """The one message Claude gets (the sheet goes with it as an image)."""
    lang = language(mat.get("language"))
    parts = ytdraft.film_text(mat) + ["", "# What to write", ASK.format(language=lang)]
    return "\n".join(parts)


def key_of(mat, model, effort):
    """What a draft was written from: a changed film or model is a new one."""
    h = hashlib.sha256()
    rest = {k: v for k, v in mat.items() if k not in ("sheet", "moments_sheet")}
    for part in (WRITER, ASK, model, effort, json.dumps(rest, sort_keys=True, default=str)):
        h.update(part.encode("utf-8") + b"\0")
    return h.hexdigest()[:24]


# ------------------------------------------------------------------ holding it to the film
def language(s, default="en"):
    """A short BCP-47 primary code ("en", "uk", "es") from what a film or a writer says: "en-US",
    "uk_UA", "Ukrainian", "UA" all come out as the code; anything unreadable as the default."""
    s = str(s or "").strip().lower().replace("_", "-")
    if s in LANGUAGES:
        return LANGUAGES[s]
    head = s.split("-")[0]
    head = LANGUAGES.get(head, head)
    return head if re.fullmatch(r"[a-z]{2,3}", head) else default


def _cut(s, n, ellipsis):
    """At most n characters, cut at a word (a sentence's end when one is near enough)."""
    if len(s) <= n:
        return s
    room = n - (1 if ellipsis else 0)
    cut = s[:room]
    end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    if end >= n // 2:
        return cut[: end + 1]
    sp = cut.rfind(" ")
    if sp >= n // 2:
        cut = cut[:sp]
    cut = cut.rstrip(" ,.;:-|–—")
    return cut + ("…" if ellipsis else "")


def title_clean(t):
    """ytdraft's cleaning (one line, no angle brackets), then at most TITLE_MAX characters cut
    at a word, and no full stop at the end."""
    t = ytdraft.title_clean(t).rstrip("…")
    t = _cut(t, TITLE_MAX, ellipsis=False)
    return t.rstrip(" .").rstrip(" ,;:-|–—")


def desc_clean(d):
    d = " ".join(ytdraft.URL.sub("", str(d or "")).replace("<", "").replace(">", "").split())
    return _cut(d, DESC_MAX, ellipsis=True)


def check(d, mat):
    """The answer held to the page's limits: (clean {title, description, language}, notes)."""
    notes = []
    raw_t, raw_d = " ".join(str(d.get("title") or "").split()), str(d.get("description") or "")
    out = {
        "title": title_clean(raw_t),
        "description": desc_clean(raw_d),
        # the film's own setting over what the writer says it wrote in
        "language": language(mat.get("language") or d.get("language")),
    }
    if len(raw_t) > TITLE_MAX:
        notes.append("cut the title to %d characters" % TITLE_MAX)
    if len(" ".join(raw_d.split())) > DESC_MAX:
        notes.append("cut the description to %d characters" % DESC_MAX)
    if not out["title"]:
        raise ValueError("no title")
    if not out["description"]:
        raise ValueError("no description")
    return out, notes


def problem(out, mat):
    """Why the words must be written again, or None: the film said to be generated."""
    m = GENERATED.search(out["title"] + " " + out["description"])
    if m:
        return 'it says how the film was made ("%s")' % m.group(0)
    return None


# ------------------------------------------------------------------ writing it
async def _call(mat, auth, film, model, effort, note=None):
    """One Claude call: (the parsed JSON, cost in USD)."""
    text = ask_text(mat) + ("\n\n" + note if note else "")
    return await ytdraft.ask_json(text, mat["sheet"], auth, film, model, effort, WRITER, "share")


def cache_path(film):
    return film.path("share", "draft.json")


def cached(film, key=None):
    d = ytdraft._read(cache_path(film), True)
    if isinstance(d, dict) and (key is None or d.get("key") == key):
        return d
    return None


def auth_of(film):
    """What the film was made on pays for its share: its key ("api") or this machine's login. A
    film that ran out of the plan and carried on on the key says "api" by then."""
    return "login" if film.record().get("auth") == "login" else "api"


async def write(film, auth=None, model=MODEL, effort=EFFORT, mat=None, record=True):
    """The share words for this film: from the cache, else one call (and one more if the first
    said the film was generated, or broke the pictures' rules)."""
    auth = auth or auth_of(film)
    mat = mat or await asyncio.to_thread(ytdraft.material, film)
    key = key_of(mat, model, effort)
    hit = cached(film, key)
    if hit:
        return hit
    t0, spent, note = time.time(), 0.0, None
    if mat.get("sheet") is None:  # the film's moments, else its review sheet or poster
        got = await thumbs.sheet(film)
        mat = (
            dict(mat, sheet=got, moments_sheet=True)
            if got
            else dict(mat, sheet=ytdraft._sheet(film))
        )
    for attempt in (1, 2):
        try:
            d, cost = await _call(mat, auth, film, model, effort, note)
        except RuntimeError:
            if attempt == 2:
                raise
            note = "Your last answer was not the JSON object asked for. Answer with it alone."
            continue
        spent += cost
        try:
            out, notes = check(d, mat)
        except ValueError as e:
            if attempt == 2:
                if record:
                    await _spent(film, spent, auth)
                raise RuntimeError("no share: %s" % e) from None
            note = "Your last answer had no %s. Answer with the whole JSON object." % str(e)[3:]
            continue
        concepts, tnotes, problems = ytdraft.check_thumbs(d, mat, out["title"], CONCEPTS, LAYOUTS)
        why = problem(out, mat)
        if not why and not problems:
            break
        if attempt == 2:
            if why:
                if record:
                    await _spent(film, spent, auth)
                raise RuntimeError("the share kept going wrong (%s)" % why)
            concepts, fixed = ytdraft.repair(concepts, problems, mat, n=CONCEPTS)
            tnotes.append(fixed)
            break
        asks = []
        if why:
            asks.append(
                "Your last answer broke a rule (%s). The film is not said to be generated: "
                "write the title and description from the film itself." % why
            )
        if problems:
            asks.append(
                "Your last answer's pictures broke the rules: %s. Answer with the whole JSON "
                "object again, the pictures put right." % "; ".join(p["text"] for p in problems)
            )
        note = " ".join(asks)
    draft = out | {
        "thumbnails": concepts,
        "notes": notes + tnotes,
        "model": model,
        "effort": effort,
        "key": key,
        "cost_usd": round(spent, 4),
        "seconds": round(time.time() - t0, 1),
        "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    os.makedirs(film.path("share"), exist_ok=True)
    films._write_json(cache_path(film), draft)
    if record:
        await _spent(film, spent, auth)
    return draft


async def _spent(film, usd, auth):
    """What the share cost, on the film's record and in the run log (the day's budget sees it):
    in cost_usd only when it was paid for on the key."""
    rec = film.record()
    fields = {
        "share_drafts": (rec.get("share_drafts") or 0) + 1,
        "share_cost_usd": round((rec.get("share_cost_usd") or 0) + usd, 4),
    }
    if auth == "api":
        fields["cost_usd"] = round((rec.get("cost_usd") or 0) + usd, 4)
    film.update(**fields)
    await agent.save(film.id, fields)


# ------------------------------------------------------------------ the pictures
def pick(rec):
    """The option the page shows: the first whose words survived its checks (an option that
    failed one falls back, in the end to the picture alone), else the first."""
    opts = (rec or {}).get("options") or []
    for o in opts:
        if o.get("layout") != "still" and o.get("words"):
            return o
    return opts[0] if opts else None


async def make(film, draft):
    """The share's pictures: the draft's concepts made in the film's look (thumbs.py), the first
    good one cut to share.jpg and thumb.jpg, and both copied online when copying is on. Returns
    {"image", "thumb"} as URLs (or {} when copying is off), and the option used as "option"."""
    want = max(1, min(CONCEPTS, len(draft.get("thumbnails") or [])))
    rec = await thumbs.make(film, CHANNEL, draft, want=want)
    o = pick(rec)
    if o is None:
        raise RuntimeError("no thumbnail was made")
    src = film.path("outputs", o["path"])
    await asyncio.to_thread(media.make_share, film.path("outputs"), src)
    urls = await media.publish_share(film)
    return urls | {"option": o["n"]}


def utc_now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


async def save(film, share):
    """The share on the film's record (studio.json) and in studio_runs: `share` alone is set, the
    rest of the record is left as it is."""
    fields = {"share": share}
    if film.record().get("share_error"):
        fields["share_error"] = None
    film.update(**fields)
    await agent.save(film.id, fields)


async def run(film, auth=None, log=print, model=MODEL):
    """Write the words, make the pictures, record the share. Pictures that could not be made
    leave the share without image and thumb (the page shows card.jpg). Raises only when the
    words could not be written."""
    t0 = time.time()
    draft = await write(film, auth, model)
    share = {k: draft[k] for k in ("title", "description", "language")}
    try:
        got = await make(film, draft)
        share.update({k: got[k] for k in ("image", "thumb") if got.get(k)})
    except Exception as e:  # noqa: BLE001 -- the words are worth having without the picture
        log("SHARE %s: no picture: %s" % (film.id, e))
    share.update(at=utc_now(), key=draft["key"])
    await save(film, share)
    log(
        "SHARE %s: %r, %s, %.1f s, $%.4f"
        % (
            film.id,
            share["title"],
            "with its picture" if share.get("image") else "no picture online",
            time.time() - t0,
            draft.get("cost_usd") or 0,
        )
    )
    return share


def enabled():
    """Whether a finished film has its share written: not when STUDIO_SHARE=0 (the switch), and
    not when Claude is stood in for (the studio's tests make films with a stub; their share would
    be a real, paid call)."""
    if os.environ.get("STUDIO_SHARE", "").strip() == "0":
        return False
    rc = agent.run_claude
    return getattr(rc, "__module__", None) == "agent" and rc.__name__ == "run_claude"


async def _premake(film):
    try:
        await run(film, log=lambda s: print(s, flush=True))
    # SystemExit too: claude_env() exits when the key is missing, and a task that raised it
    # would take the server down with it
    except (Exception, SystemExit) as e:  # noqa: BLE001 -- a film is never failed by its share
        print("SHARE %s failed: %s" % (film.id, e or type(e).__name__), flush=True)
        try:
            film.update(share_error=str(e)[:300])
            await agent.save(film.id, {"share_error": str(e)[:300]})
        except Exception as e2:  # noqa: BLE001
            print("SHARE %s: could not note the failure: %s" % (film.id, e2), flush=True)


def premake(film):
    """Write a finished film's share in the background (server.py, when a film is done). Never
    raises and never touches the film's state: a failure is logged and noted as share_error."""
    try:
        if not enabled():
            return None
        t = asyncio.get_running_loop().create_task(_premake(film))
    except RuntimeError:  # no loop (a script): share.py --missing picks it up
        return None
    except Exception as e:  # noqa: BLE001 -- the film is done; its share can be made later
        print("SHARE %s not started: %s" % (film.id, e), flush=True)
        return None
    TASKS.add(t)
    t.add_done_callback(TASKS.discard)
    return t


def in_flight():
    """The films whose share is being written here (a retiring server waits for them)."""
    return [t for t in TASKS if not t.done()]


def public(rec):
    """What GET /api/films/{id} says of the share: the words and the pictures, nothing else."""
    s = rec.get("share")
    if not isinstance(s, dict) or not s.get("title"):
        return None
    return {k: s[k] for k in ("title", "description", "language", "image", "thumb") if s.get(k)}


# ------------------------------------------------------------------ the command line
def finished(f):
    rec = f.record()
    return bool(rec.get("ok")) and rec.get("state", "done") == "done" and os.path.exists(f.manifest)


def missing(f):
    """No share yet -- or one whose pictures did not go online when they could have (made again
    from the kept draft, which costs nothing)."""
    s = f.record().get("share")
    return not isinstance(s, dict) or (media.enabled() and not s.get("image"))


def estimate(f, model=MODEL):
    """What one film's share costs, roughly (ytdraft.estimate on this ask, a sheet counted)."""
    mat = dict(ytdraft.material(f), sheet=b"sheet", moments_sheet=True)
    return ytdraft.estimate(mat, ask_text(mat), model)[1]


async def _main(a):
    if a.film:
        f = films.Film(a.film) if os.path.isdir(a.film) else films.Film.open(a.film)
        if f is None or not finished(f):
            sys.exit("%s: no such finished film" % a.film)
        todo = [f]
    else:
        todo = [f for f in films.Film.all() if finished(f) and missing(f)]
        todo = todo[: a.limit] if a.limit else todo
    if a.dry_run:
        total = 0.0
        for f in todo:
            usd = estimate(f, a.model) if not cached(f) else 0.0
            total += usd
            print("  %s  %s  ~$%.3f" % (f.id, (f.record().get("title") or "")[:50], usd))
        print(
            "%d films, ~$%.2f on the key (on the login: counted, not charged)" % (len(todo), total)
        )
        return
    print("%d films" % len(todo), flush=True)
    failed = 0
    for f in todo:
        try:
            await run(f, a.auth, log=lambda s: print(s, flush=True), model=a.model)
        except Exception as e:  # noqa: BLE001 -- say which, and carry on
            failed += 1
            print("SHARE %s failed: %s" % (f.id, e), flush=True)
    if failed:
        sys.exit("%d of %d failed" % (failed, len(todo)))


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--film", help="a film id, or a film's folder")
    g.add_argument("--missing", action="store_true", help="every finished film with no share")
    ap.add_argument("--limit", type=int, help="with --missing: at most this many, newest first")
    ap.add_argument("--dry-run", action="store_true", help="list the films and the cost; no call")
    ap.add_argument("--auth", choices=("login", "api"), help="default: what the film was made on")
    ap.add_argument("--model", default=MODEL)
    asyncio.run(_main(ap.parse_args()))


if __name__ == "__main__":
    main()
