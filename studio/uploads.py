"""Pictures, voice notes and documents a visitor attaches to a film request, kept until a film
takes them.

    STUDIO_HOME\\uploads\\<client key>\\up-<12 chars>.<ext>    the file as it came
                                     up-<12 chars>.json     what it is (below)
                                     up-<12 chars>.flac     a voice note, as every engine hears it
                                     ledger.jsonl           what this client sent today (the quota)

The page sends each picture, recording or document on its own request (POST /api/uploads, the
raw bytes) as soon as it is attached, so a film request only names ids. The bytes are streamed to
disk against the kind's own cap -- the server's 64 KB body limit stays for everything else -- and
the kind is read off the file's first bytes, never off its name or Content-Type. A picture must
open in Pillow and stay under MAX_PIXELS; a recording must decode, and last at most MAX_AUDIO_S.

A document (a .txt or .md: a script, notes, facts about what the film is for) has no magic bytes,
so it is whatever is left that reads as text -- UTF-8 (a BOM or not) or UTF-16 with its BOM, no
control characters but whitespace -- and it is re-written as plain UTF-8, at most MAX_TEXT_CHARS.
Only its extension comes from outside (a text/markdown Content-Type, or a ?name= ending .md);
the name the page sends is kept, cleaned, for Claude to see, and never names a path.

A voice note is written out in the background (_stt.py, the engines in order of STUDIO_STT; the
first that answers wins) and the page polls GET /api/uploads/<id> for the words. A film asked for
while one is still being written out waits for it (take()).

During a ship two servers share the home (peers.py, KI-031), and the film may be asked of the new
one while the old one is still writing its note out. The work is in the old one's memory (TASKS),
so the meta names the server doing it: take() on another server waits for that one (polling the
meta) instead of paying for a second transcription, and starts its own only when nobody is at it
-- that server is gone, or the note has been "transcribing" for longer than any engine takes
(FRESH_S). A server names what it is writing out in its heartbeat (in_flight()), so an old one
does not exit halfway through.

Only the client that uploaded a file can see it or put it in a film; an id is unguessable and
checked before it names a path. Anything a film did not take is deleted after KEEP_S.

meta: {id, kind: image|audio|text, mime, ext, bytes, created, w, h (image), secs (audio),
       name, chars, words (text),
       state: ready|transcribing|failed, transcript, lang, engine, stt_seconds, stt_cost_usd, error,
       server, stt_started (who is writing it out, since when: peers.SERVER_ID, epoch s)}
"""

import os
import re
import sys
import json
import time
import codecs
import shutil
import asyncio
import hashlib
import secrets
import contextlib

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
)
import _stt  # noqa: E402

import locks  # noqa: E402
import peers  # noqa: E402
import procs  # noqa: E402
from film import HOME  # noqa: E402

ROOT = os.path.join(HOME, "uploads")
ID = re.compile(r"^up-[a-z2-7]{12}$")
_B32 = "abcdefghijklmnopqrstuvwxyz234567"
MAX_BYTES = {"image": 8 * 1024 * 1024, "audio": 10 * 1024 * 1024, "text": 400 * 1024}
MAX_TEXT_CHARS = 100_000  # about 25k tokens: a brief, not a book
MAX_PIXELS = 40_000_000  # a 12000 x 12000 PNG is a decompression bomb, not a logo
MAX_AUDIO_S = 185  # the page stops at 3:00
KEEP_S = 24 * 3600  # an upload no film took
DAY_FILES, DAY_BYTES = 60, 120 * 1024 * 1024  # per client, per 24 h
MAX_IMAGES, MAX_NOTES, MAX_DOCS = 6, 3, 3  # per film
# a control character that is not whitespace: binary, not a document
CONTROL = re.compile(r"[\x00-\x08\x0b\x0e-\x1f\x7f]")
TYPES = "Only pictures (JPG, PNG, WebP), voice notes and text files (.txt, .md) work here."
# the engines that write a voice note out, in order: the first that answers wins
# (scripts/stt-compare.py measured them; STUDIO_STT overrides, comma-separated)
STT = ("vertex:gemini-3.1-flash-lite", "whisper:large-v3-turbo")
STT_KEYS = (
    "GOOGLE_SERVICE_ACCOUNT_KEY",
    "GOOGLE_CLOUD_PROJECT",
    "GOOGLE_CLOUD_LOCATION",
    "GEMINI_API_KEY",
    "OPENROUTER_API_KEY",
)
TASKS = {}  # id -> the task writing that voice note out
# a note "transcribing" this long after it was started is one nobody is writing out any more:
# each engine gives up after 90 s, and there are two
FRESH_S = 300
WAIT_S = 120  # how long take() waits for a note, here or on another server
POLL_S = 1.0  # how often it looks at the meta of a note another server is writing out


class UploadError(Exception):
    """Why an upload or a film's attachments were refused: status, a reason for the page, the
    upload's id when one is at fault, and words for a person."""

    def __init__(self, status, reason, text, uid=None):
        super().__init__(text)
        self.status, self.reason, self.text, self.uid = status, reason, text, uid

    def body(self):
        return {"error": self.text, "reason": self.reason} | ({"id": self.uid} if self.uid else {})


def sniff(head):
    """(kind, mime, ext) from a file's first bytes, or None."""
    if head.startswith(b"\xff\xd8\xff"):
        return "image", "image/jpeg", "jpg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image", "image/png", "png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image", "image/webp", "webp"
    if head.startswith(b"\x1a\x45\xdf\xa3"):
        return "audio", "audio/webm", "webm"
    if head.startswith(b"OggS"):
        return "audio", "audio/ogg", "ogg"
    if head[4:8] == b"ftyp":
        return "audio", "audio/mp4", "m4a"
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return "audio", "audio/wav", "wav"
    if head.startswith(b"ID3") or head[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
        return "audio", "audio/mpeg", "mp3"
    return None


def sniff_text(head):
    """("text", mime, ext) when a file's first chunk reads as text, or None. The whole file is
    decoded again once it is all here (read_text): a chunk may end inside a character."""
    if head.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return "text", "text/plain", "txt"
    try:
        start = codecs.getincrementaldecoder("utf-8-sig")().decode(head, final=False)
    except UnicodeDecodeError:
        return None
    if CONTROL.search(start):  # an empty one is read_text's to refuse
        return None
    return "text", "text/plain", "txt"


def read_text(path):
    """A document's words: UTF-8 (a BOM or not) or UTF-16 (its BOM), line endings made \\n, the
    ends trimmed. Raises UploadError when it is not text after all, empty, or too long."""
    with open(path, "rb") as f:
        raw = f.read()
    bom16 = raw.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE))
    try:
        text = raw.decode("utf-16" if bom16 else "utf-8-sig")
    except UnicodeDecodeError as e:
        raise UploadError(415, "type", "Save the text file as UTF-8 and add it again.") from e
    if CONTROL.search(text):
        raise UploadError(415, "type", TYPES)
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        raise UploadError(400, "empty", "That text file has no words in it.")
    if len(text) > MAX_TEXT_CHARS:
        raise UploadError(
            413,
            "long",
            "That text file is too long (up to %d characters, about %d pages)."
            % (MAX_TEXT_CHARS, MAX_TEXT_CHARS // 3000),
        )
    return text


def clean_name(name):
    """The file name the page sent, for Claude to see: its last part, no control characters,
    at most 80 characters; "" when there is none."""
    name = re.split(r"[\\/]", str(name or ""))[-1]
    return " ".join(CONTROL.sub(" ", name).split())[:80]


def client_dir(client):
    """The client's own folder: a hash of who they are, so no id or IP becomes a path."""
    return os.path.join(ROOT, hashlib.sha256(client.encode()).hexdigest()[:20])


def _meta_path(client, uid):
    return os.path.join(client_dir(client), uid + ".json")


def _write(path, data):
    """Atomically, through a temp file of this process's own (two servers may write one meta)."""
    tmp = "%s.%d.tmp" % (path, os.getpid())
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    _replace(tmp, path)


def _replace(tmp, path):
    for i in range(20):  # Windows refuses the rename for a moment while a reader has it open
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            time.sleep(0.02 * (i + 1))
    os.replace(tmp, path)


def get(client, uid):
    """The upload's meta, if this client made it; else None."""
    if not isinstance(uid, str) or not ID.match(uid):
        return None
    try:
        with open(_meta_path(client, uid), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def public(meta):
    """What the page is told about an upload."""
    keys = ("id", "kind", "state", "w", "h", "secs", "transcript", "lang")
    keys += ("name", "chars", "words", "error")
    return {k: meta[k] for k in keys if meta.get(k) is not None}


def listing(client, now=None):
    """The client's uploads still waiting for a film, newest first: each as public() says, with
    how many seconds it has left before prune() deletes it. A film that took one released it, so
    only unused ones are here."""
    now = now or time.time()
    d = client_dir(client)
    out = []
    try:
        names = os.listdir(d)
    except OSError:
        return out
    for fn in names:
        if not fn.endswith(".json") or not ID.match(fn[:-5]):
            continue
        meta = get(client, fn[:-5])
        if meta is None:
            continue
        left = KEEP_S - (now - (meta.get("created") or 0))
        if left > 0:
            out.append(public(meta) | {"expires_in": round(left), "created": meta.get("created")})
    out.sort(key=lambda m: m.get("created") or 0, reverse=True)
    return [{k: v for k, v in m.items() if k != "created"} for m in out]


def _spent_today(d):
    n, total, keep = 0, 0, []
    now = time.time()
    try:
        with open(os.path.join(d, "ledger.jsonl"), encoding="utf-8") as f:
            for line in f:
                with_time = json.loads(line)
                if now - with_time["t"] < 86400:
                    n, total = n + 1, total + with_time["bytes"]
                    keep.append(line)
    except (OSError, ValueError):
        pass
    return n, total, keep


def _spend(d, size):
    """Put an upload on the client's ledger (ledger.jsonl, a line a file: the day's quota). The
    ledger is read again and rewritten under ledger.lock: two uploads of one client stored at the
    same moment -- on one server, or on two during a ship -- would otherwise each write it as it
    was before the other's line. A lock that cannot be had costs the quota a line, never the
    upload."""
    with contextlib.ExitStack() as held:
        with contextlib.suppress(OSError):  # locks.LockTimeout is one too
            held.enter_context(locks.locked(os.path.join(d, "ledger.lock"), timeout=10))
        _, _, keep = _spent_today(d)
        path = os.path.join(d, "ledger.jsonl")
        tmp = "%s.%d.tmp" % (path, os.getpid())
        with open(tmp, "w", encoding="utf-8") as f:
            f.writelines(keep + [json.dumps({"t": time.time(), "bytes": size}) + "\n"])
        _replace(tmp, path)


async def receive(req, client, stt=None):
    """One upload from the request body: stored, checked, and (a voice note) sent to be written
    out. Returns its meta; raises UploadError. A document may carry its file name (?name=)."""
    d = client_dir(client)
    os.makedirs(d, exist_ok=True)
    n, spent, _ = _spent_today(d)
    if n >= DAY_FILES or spent >= DAY_BYTES:
        raise UploadError(429, "quota", "That is a lot of uploads for one day. Try again tomorrow.")
    uid = "up-" + "".join(secrets.choice(_B32) for _ in range(12))
    part = os.path.join(d, uid + ".part")
    size, kind = 0, None
    ctype = req.headers.get("Content-Type", "").lower()
    try:
        with open(part, "wb") as f:
            async for chunk in req.content.iter_chunked(64 * 1024):
                if kind is None:
                    # text has no magic bytes, so it is only text when it is not sent as
                    # something else: a page called a picture stays refused
                    found = sniff(chunk[:16]) or (
                        None if ctype.startswith(("image/", "audio/")) else sniff_text(chunk)
                    )
                    if not found:
                        raise UploadError(415, "type", TYPES)
                    kind, mime, ext = found
                size += len(chunk)
                if size > MAX_BYTES[kind]:
                    cap = MAX_BYTES[kind]
                    cap = "%d MB" % (cap // 2**20) if cap >= 2**20 else "%d KB" % (cap // 1024)
                    raise UploadError(413, "size", "That file is too big (up to %s)." % cap)
                f.write(chunk)
        if kind is None:
            raise UploadError(400, "empty", "The file was empty.")
        name = clean_name(req.query.get("name")) if kind == "text" else ""
        if kind == "text" and (
            ctype.startswith(("text/markdown", "text/x-markdown"))
            or re.search(r"\.(md|markdown)$", name, re.I)
        ):
            mime, ext = "text/markdown", "md"
        path = os.path.join(d, "%s.%s" % (uid, ext))
        os.replace(part, path)
    finally:
        if os.path.exists(part):
            os.remove(part)
    meta = {
        "id": uid,
        "kind": kind,
        "mime": mime,
        "ext": ext,
        "bytes": size,
        "created": time.time(),
        "client": client,
    }
    try:
        if kind == "image":
            meta.update(await asyncio.to_thread(_check_image, path), state="ready")
        elif kind == "text":
            text = await asyncio.to_thread(read_text, path)
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(text + "\n")
            meta.update(name=name, chars=len(text), words=len(text.split()), state="ready")
        else:
            flac = os.path.join(d, uid + ".flac")
            secs = await asyncio.to_thread(_stt.normalise, path, flac)
            if secs > MAX_AUDIO_S:
                raise UploadError(413, "long", "Voice notes can be up to 3 minutes long.")
            # this server writes it out: another one's take() waits for it (_elsewhere)
            meta.update(secs=round(secs, 1), state="transcribing", server=peers.SERVER_ID)
            meta["stt_started"] = time.time()
    except UploadError:
        _remove(d, uid)
        raise
    except (_stt.SttError, OSError, ValueError) as e:
        _remove(d, uid)
        what = {"image": "picture", "audio": "recording"}.get(kind, "file")
        raise UploadError(400, "unreadable", "That %s could not be opened." % what) from e
    _write(_meta_path(client, uid), meta)
    await asyncio.to_thread(_spend, d, size)  # it may wait for the ledger's lock
    if kind == "audio":
        TASKS[uid] = asyncio.create_task(_transcribe(client, uid, stt))
    return meta


def _check_image(path):
    from PIL import Image

    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    try:
        with Image.open(path) as im:
            im.verify()
        with Image.open(path) as im:
            w, h = im.size
    except Image.DecompressionBombError as e:
        raise UploadError(413, "size", "That picture is too large to use.") from e
    return {"w": w, "h": h}


def engines():
    env = os.environ.get("STUDIO_STT", "").strip()
    return tuple(e.strip() for e in env.split(",") if e.strip()) or STT


async def _transcribe(client, uid, stt=None):
    """Write a voice note out: each engine in turn until one answers. The meta says how it went."""
    try:
        d = client_dir(client)
        flac = os.path.join(d, uid + ".flac")
        keys = {k: procs.secret(k) for k in STT_KEYS if procs.secret(k)}
        errors = []
        result = None
        for eng in stt or engines():
            try:
                result = await asyncio.to_thread(_stt.transcribe, flac, eng, (), keys)
                break
            except _stt.SttError as e:
                errors.append(str(e))
                print("upload %s: %s" % (uid, e), file=sys.stderr, flush=True)
        meta = get(client, uid)
        if meta is None:  # removed meanwhile
            return
        if result is None:
            meta.update(state="failed", error="The voice note could not be written out.")
            meta["errors"] = errors
        else:
            meta.update(
                state="ready",
                transcript=result["text"],
                lang=result.get("lang"),
                engine=result["engine"],
                stt_seconds=result["seconds"],
                stt_cost_usd=result.get("cost_usd"),
                no_speech=bool(result.get("no_speech")),
            )
        _write(_meta_path(client, uid), meta)
    finally:  # however it ended, this server is no longer writing it out (in_flight)
        TASKS.pop(uid, None)


def in_flight():
    """The upload ids whose voice note this process is writing out now. The server names them in
    its heartbeat (peers.heartbeat transcribing), so an old server handing over does not exit
    halfway through one (KI-031)."""
    return sorted(uid for uid, t in TASKS.items() if not t.done())


def _elsewhere(meta, now=None):
    """Is another server writing this voice note out? The one its meta names, while that one is
    alive (peers.alive: its lock is held) and the note is fresh. A note from a release before
    servers were named has no name: fresh is all there is to go on."""
    started = meta.get("stt_started") or meta.get("created") or 0
    if (now or time.time()) - started >= FRESH_S:
        return False  # no engine takes this long: whoever had it lost it
    sid = meta.get("server")
    return not sid or (sid != peers.SERVER_ID and peers.alive(sid))


def _start(client, uid, meta):
    """Write a voice note out here, saying so in its meta first, so another server's take()
    waits for this one rather than starting a third."""
    meta.update(server=peers.SERVER_ID, stt_started=time.time())
    _write(_meta_path(client, uid), meta)
    task = TASKS[uid] = asyncio.create_task(_transcribe(client, uid))
    return task


async def _written_out(client, uid, meta, wait_s=None):
    """A voice note's meta once it is written out, waiting up to WAIT_S s: for this process's
    task when it has one, for another server's work while that server is at it (_elsewhere; its
    meta read every POLL_S s), and otherwise for a task of its own, started once (a restart lost
    the one that was writing it out). Returns the meta as it is then: None if it was removed,
    still "transcribing" if the wait ran out."""
    deadline = time.monotonic() + (WAIT_S if wait_s is None else wait_s)
    started = False
    while meta is not None and meta.get("state") == "transcribing":
        left = deadline - time.monotonic()
        if left <= 0:
            break
        task = TASKS.get(uid)
        if task is None and not started and not _elsewhere(meta):
            task, started = _start(client, uid, meta), True
        if task is None:
            await asyncio.sleep(min(POLL_S, left))
        else:
            try:
                await asyncio.wait_for(asyncio.shield(task), left)
            except TimeoutError:
                pass
            except Exception as e:  # noqa: BLE001 -- the meta says what became of it
                print("upload %s: %r" % (uid, e), file=sys.stderr, flush=True)
                await asyncio.sleep(min(POLL_S, max(0, deadline - time.monotonic())))
        meta = get(client, uid)
    return meta


def _remove(d, uid):
    for fn in os.listdir(d):
        if fn.startswith(uid + "."):
            try:
                os.remove(os.path.join(d, fn))
            except OSError:
                pass


async def take(client, ids, max_images=None):
    """The metas of the uploads a film names, in order, once every voice note is written out --
    here, or by the server that took the note in (_written_out). Raises UploadError naming the
    first that is missing, foreign, failed, silent or still being written out after WAIT_S.
    max_images: a template's own cap on pictures (a line-up of speakers), else MAX_IMAGES."""
    if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
        raise UploadError(400, "attachments", "attachments must be a list of upload ids")
    ids = list(dict.fromkeys(ids))
    metas = []
    for uid in ids:
        meta = get(client, uid)
        if meta is None:
            raise UploadError(
                409, "attachment", "An attachment is no longer here; add it again.", uid
            )
        if meta["state"] == "transcribing":
            meta = await _written_out(client, uid, meta)
            if meta is None:
                raise UploadError(
                    409, "attachment", "An attachment is no longer here; add it again.", uid
                )
            if meta["state"] == "transcribing":
                raise UploadError(
                    503, "voice", "Still writing out a voice note; try again in a minute.", uid
                )
        if meta["state"] == "failed":
            raise UploadError(
                422, "voice", "A voice note could not be written out; record it again.", uid
            )
        if meta["kind"] == "audio" and not (meta.get("transcript") or "").strip():
            raise UploadError(
                422, "silent", "A voice note has no words in it; record it again.", uid
            )
        metas.append(meta)
    cap = int(max_images or MAX_IMAGES)
    if sum(m["kind"] == "image" for m in metas) > cap:
        raise UploadError(400, "attachments", "Up to %d pictures a film." % cap)
    if sum(m["kind"] == "audio" for m in metas) > MAX_NOTES:
        raise UploadError(400, "attachments", "Up to %d voice notes a film." % MAX_NOTES)
    if sum(m["kind"] == "text" for m in metas) > MAX_DOCS:
        raise UploadError(400, "attachments", "Up to %d text files a film." % MAX_DOCS)
    return metas


def file_of(client, meta):
    return os.path.join(client_dir(client), "%s.%s" % (meta["id"], meta["ext"]))


def release(client, metas):
    """A film has copied these into its folder: their uploads go."""
    d = client_dir(client)
    for m in metas:
        _remove(d, m["id"])


def prune(now=None):
    """Delete every upload no film took within KEEP_S. Returns how many went."""
    now = now or time.time()
    gone = 0
    if not os.path.isdir(ROOT):
        return 0
    for c in os.listdir(ROOT):
        d = os.path.join(ROOT, c)
        if not os.path.isdir(d):
            continue
        for fn in os.listdir(d):
            if not fn.endswith(".json") or not ID.match(fn[:-5]):
                continue
            try:
                old = now - os.path.getmtime(os.path.join(d, fn)) > KEEP_S
            except OSError:
                continue
            if old and fn[:-5] not in TASKS:
                _remove(d, fn[:-5])
                gone += 1
        if not [f for f in os.listdir(d) if f not in ("ledger.jsonl", "ledger.lock")]:
            shutil.rmtree(d, ignore_errors=True)
    return gone
