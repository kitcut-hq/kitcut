"""Pictures and voice notes a visitor attaches to a film request, kept until a film takes them.

    STUDIO_HOME\\uploads\\<client key>\\up-<12 chars>.<ext>    the file as it came
                                     up-<12 chars>.json     what it is (below)
                                     up-<12 chars>.flac     a voice note, as every engine hears it
                                     ledger.jsonl           what this client sent today (the quota)

The page sends each picture or recording on its own request (POST /api/uploads, the raw bytes)
as soon as it is attached, so a film request only names ids. The bytes are streamed to disk
against the kind's own cap -- the server's 64 KB body limit stays for everything else -- and the
kind is read off the file's first bytes, never off its name or Content-Type. A picture must open
in Pillow and stay under MAX_PIXELS; a recording must decode, and last at most MAX_AUDIO_S.

A voice note is written out in the background (_stt.py, the engines in order of STUDIO_STT; the
first that answers wins) and the page polls GET /api/uploads/<id> for the words. A film asked for
while one is still being written out waits for it (take()).

Only the client that uploaded a file can see it or put it in a film; an id is unguessable and
checked before it names a path. Anything a film did not take is deleted after KEEP_S.

meta: {id, kind: image|audio, mime, ext, bytes, created, w, h (image), secs (audio),
       state: ready|transcribing|failed, transcript, lang, engine, stt_seconds, stt_cost_usd, error}
"""

import os
import re
import sys
import json
import time
import shutil
import asyncio
import hashlib
import secrets

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
)
import _stt  # noqa: E402

import procs  # noqa: E402
from film import HOME  # noqa: E402

ROOT = os.path.join(HOME, "uploads")
ID = re.compile(r"^up-[a-z2-7]{12}$")
_B32 = "abcdefghijklmnopqrstuvwxyz234567"
MAX_BYTES = {"image": 8 * 1024 * 1024, "audio": 10 * 1024 * 1024}
MAX_PIXELS = 40_000_000  # a 12000 x 12000 PNG is a decompression bomb, not a logo
MAX_AUDIO_S = 185  # the page stops at 3:00
KEEP_S = 24 * 3600  # an upload no film took
DAY_FILES, DAY_BYTES = 60, 120 * 1024 * 1024  # per client, per 24 h
MAX_IMAGES, MAX_NOTES = 6, 3  # per film
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


def client_dir(client):
    """The client's own folder: a hash of who they are, so no id or IP becomes a path."""
    return os.path.join(ROOT, hashlib.sha256(client.encode()).hexdigest()[:20])


def _meta_path(client, uid):
    return os.path.join(client_dir(client), uid + ".json")


def _write(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
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
    keys = ("id", "kind", "state", "w", "h", "secs", "transcript", "lang", "error")
    return {k: meta[k] for k in keys if meta.get(k) is not None}


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


async def receive(req, client, stt=None):
    """One upload from the request body: stored, checked, and (a voice note) sent to be written
    out. Returns its meta; raises UploadError."""
    d = client_dir(client)
    os.makedirs(d, exist_ok=True)
    n, spent, keep = _spent_today(d)
    if n >= DAY_FILES or spent >= DAY_BYTES:
        raise UploadError(429, "quota", "That is a lot of uploads for one day. Try again tomorrow.")
    uid = "up-" + "".join(secrets.choice(_B32) for _ in range(12))
    part = os.path.join(d, uid + ".part")
    size, kind = 0, None
    try:
        with open(part, "wb") as f:
            async for chunk in req.content.iter_chunked(64 * 1024):
                if kind is None:
                    found = sniff(chunk[:16])
                    if not found:
                        raise UploadError(
                            415, "type", "Only pictures (JPG, PNG, WebP) and voice notes work here."
                        )
                    kind, mime, ext = found
                size += len(chunk)
                if size > MAX_BYTES[kind]:
                    raise UploadError(
                        413,
                        "size",
                        "That file is too big (up to %d MB)." % (MAX_BYTES[kind] // 2**20),
                    )
                f.write(chunk)
        if kind is None:
            raise UploadError(400, "empty", "The file was empty.")
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
        else:
            flac = os.path.join(d, uid + ".flac")
            secs = await asyncio.to_thread(_stt.normalise, path, flac)
            if secs > MAX_AUDIO_S:
                raise UploadError(413, "long", "Voice notes can be up to 3 minutes long.")
            meta.update(secs=round(secs, 1), state="transcribing")
    except UploadError:
        _remove(d, uid)
        raise
    except (_stt.SttError, OSError, ValueError) as e:
        _remove(d, uid)
        what = "picture" if kind == "image" else "recording"
        raise UploadError(400, "unreadable", "That %s could not be opened." % what) from e
    _write(_meta_path(client, uid), meta)
    with open(os.path.join(d, "ledger.jsonl"), "w", encoding="utf-8") as f:
        f.writelines(keep + [json.dumps({"t": time.time(), "bytes": size}) + "\n"])
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
    TASKS.pop(uid, None)


def _remove(d, uid):
    for fn in os.listdir(d):
        if fn.startswith(uid + "."):
            try:
                os.remove(os.path.join(d, fn))
            except OSError:
                pass


async def take(client, ids):
    """The metas of the uploads a film names, in order, once every voice note is written out.
    Raises UploadError naming the first that is missing, foreign, failed or silent."""
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
            task = TASKS.get(uid)
            if task is None:  # a restart lost the task: write it out now
                task = TASKS[uid] = asyncio.create_task(_transcribe(client, uid))
            try:
                await asyncio.wait_for(asyncio.shield(task), 120)
            except TimeoutError as e:
                raise UploadError(
                    503, "voice", "Still writing out a voice note; try again in a minute.", uid
                ) from e
            meta = get(client, uid)
        if meta["state"] == "failed":
            raise UploadError(
                422, "voice", "A voice note could not be written out; record it again.", uid
            )
        if meta["kind"] == "audio" and not (meta.get("transcript") or "").strip():
            raise UploadError(
                422, "silent", "A voice note has no words in it; record it again.", uid
            )
        metas.append(meta)
    if sum(m["kind"] == "image" for m in metas) > MAX_IMAGES:
        raise UploadError(400, "attachments", "Up to %d pictures a film." % MAX_IMAGES)
    if sum(m["kind"] == "audio" for m in metas) > MAX_NOTES:
        raise UploadError(400, "attachments", "Up to %d voice notes a film." % MAX_NOTES)
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
        if not [f for f in os.listdir(d) if f != "ledger.jsonl"]:
            shutil.rmtree(d, ignore_errors=True)
    return gone
