"""A finished film, sent to YouTube: the bytes, and nothing else.

The public site (kitcut-hq/sketch-studio, api/youtube.js) owns everything Google-facing: the
person's channel grants, the video's title, description and privacy, and the upload session. It
opens a resumable upload session with YouTube and hands the studio only that session's address,
which lets exactly one video into exactly one channel and lapses within a week. So the studio
never holds a Google token, and a leaked session address can do no more than finish this upload.
The studio streams outputs/film.mp4 into it in 8 MiB pieces, picks up where YouTube says it
stopped after a dropped connection, and reports what YouTube answered.

    POST /api/films/<id>/youtube        {"to": <session address>, "key": <the site's post id>}
    GET  /api/films/<id>/youtube/<key>  {"state": "sending"|"done"|"failed", "sent", "size",
                                         "video": {"id", "privacy", "upload"}, "error"}

A send is keyed by the site's post id, so asking twice (a retry, a double click, the site
resuming after this server restarted) never uploads twice: a live send is answered as it stands,
a finished one with its result. Sends live in memory only. After a restart the site asks again,
and the session itself says how much of the file YouTube already has.
"""

import os
import re
import time
import asyncio

import aiohttp

# the only place a film may be sent: YouTube's own resumable upload endpoint
HOSTS = ("https://www.googleapis.com/upload/youtube/v3/videos?",)
KEY = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
CHUNK = 8 * 1024 * 1024  # a multiple of 256 KiB, as the resumable protocol requires
RETRIES = 6  # dropped connections and 5xx answers in a row before a send gives up
PAUSE = lambda tries: min(30, 2**tries)  # noqa: E731 -- seconds before retry n (tests shorten it)
KEEP_S = 24 * 3600  # a finished send is remembered this long, for the site's last look

# key -> {"key", "film", "client", "state", "sent", "size", "video", "error", "t", "task"}
SENDS = {}


class SendError(Exception):
    def __init__(self, status, text):
        super().__init__(text)
        self.status, self.text = status, text


class _AgainError(Exception):
    """A dropped connection or a 5xx: ask the session where it got to, then carry on."""


def public(job):
    return {
        k: job[k] for k in ("key", "film", "state", "sent", "size", "video", "error") if k in job
    }


def get(key):
    return SENDS.get(key)


def start(film, client, to, key):
    """Send a finished film into the upload session `to`, once per key."""
    if not isinstance(key, str) or not KEY.match(key):
        raise SendError(400, "a send needs a key")
    if not isinstance(to, str) or not to.startswith(HOSTS) or "upload_id=" not in to:
        raise SendError(400, "that is not a YouTube upload session")
    path = film.path("outputs", "film.mp4")
    if not os.path.isfile(path):
        raise SendError(409, "This film has no video to send.")
    job = SENDS.get(key)
    if job is not None:
        if job["film"] != film.id or job["client"] != client:
            raise SendError(409, "that key belongs to another send")
        if job["state"] != "failed":
            return job  # sending or done: the same answer as the first time
    prune()
    job = {"key": key, "film": film.id, "client": client, "state": "sending", "sent": 0}
    job["size"] = os.path.getsize(path)
    job["t"] = time.time()
    SENDS[key] = job
    job["task"] = asyncio.get_running_loop().create_task(_run(job, path, to))
    return job


def prune(now=None):
    now = now or time.time()
    for k in [k for k, j in SENDS.items() if j["state"] != "sending" and now - j["t"] > KEEP_S]:
        del SENDS[k]


async def _run(job, path, to):
    try:
        job["video"] = await _send(job, path, to)
        job["state"] = "done"
    except SendError as e:
        job["state"], job["error"] = "failed", e.text
    except Exception as e:  # noqa: BLE001 -- a send must end in a state the site can show
        job["state"], job["error"] = "failed", "The upload stopped: %s" % e
    job["t"] = time.time()


async def _send(job, path, to):
    size = job["size"]
    timeout = aiohttp.ClientTimeout(total=None, sock_connect=30, sock_read=180)
    tries = 0
    async with aiohttp.ClientSession(timeout=timeout) as s:
        at = None
        while True:
            try:
                if at is None:
                    at = await _where(s, to, size)
                if isinstance(at, dict):
                    return _video(at)
                job["sent"] = at
                end = min(at + CHUNK, size)
                with open(path, "rb") as f:
                    f.seek(at)
                    data = f.read(end - at)
                head = {"Content-Range": "bytes %d-%d/%d" % (at, end - 1, size)}
                async with s.put(to, data=data, headers=head) as r:
                    at = await _answer(r)
                    if isinstance(at, dict):
                        job["sent"] = size
                        return _video(at)
                tries = 0
            except (_AgainError, aiohttp.ClientError, TimeoutError) as e:
                tries += 1
                if tries > RETRIES:
                    raise SendError(502, "YouTube stopped answering the upload (%s)." % e) from e
                await asyncio.sleep(PAUSE(tries))
                at = None  # ask the session how much it has before sending more


async def _where(s, to, size):
    """How far YouTube got: the next byte it wants, or the video when it already has it all."""
    head = {"Content-Range": "bytes */%d" % size, "Content-Length": "0"}
    async with s.put(to, headers=head) as r:
        return await _answer(r)


async def _answer(r):
    """308: the next byte to send (Range names the last one YouTube kept). 200/201: the video."""
    if r.status == 308:
        m = re.match(r"bytes=0-(\d+)$", r.headers.get("Range", ""))
        return int(m.group(1)) + 1 if m else 0
    if r.status in (200, 201):
        return await r.json(content_type=None)
    if r.status >= 500 or r.status == 429:
        raise _AgainError("HTTP %d" % r.status)
    if r.status in (404, 410):
        raise SendError(410, "The upload session expired. Publish it again.")
    raise SendError(502, "YouTube refused the upload: %s" % await _why(r))


async def _why(r):
    try:
        j = await r.json(content_type=None)
        err = j.get("error") or {}
        reason = ((err.get("errors") or [{}])[0]).get("reason")
        said = err.get("message") or "HTTP %d" % r.status
        return "%s (%s)" % (said, reason) if reason else said
    except Exception:  # noqa: BLE001 -- the status alone then
        return "HTTP %d" % r.status


def _video(v):
    st = v.get("status") or {}
    return {"id": v.get("id"), "privacy": st.get("privacyStatus"), "upload": st.get("uploadStatus")}
