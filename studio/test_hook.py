#!/usr/bin/env python
"""The studio's GitHub hook (server.py github_hook) against requests signed and not: no network,
seconds.

    python studio/test_hook.py

Only a request signed with the machine's secret gets anything done, and what it gets done is a
nudge: STUDIO_HOME/autoship.poke is written for a push to studio-poc and for nothing else. No
secret in the .env, no hook (404). Unsigned, wrongly signed, signed with another secret, signed
over another body, a signature that is only a prefix: 401 and no nudge. Too large: refused. A ping
is answered; another branch, a tag, another event are acknowledged and ignored. The secret is
read per request, so setting it needs no restart. And the path stays outside the token's guard
(GitHub cannot send our token), which is why it is the signature that guards it.
"""

import os
import sys
import hmac
import json
import shutil
import asyncio
import hashlib
import tempfile

T = tempfile.mkdtemp(prefix="studio-hook-test-")
os.environ["STUDIO_HOME"] = os.path.join(T, "home")
os.makedirs(os.environ["STUDIO_HOME"])
ENV = os.path.join(T, ".env")
os.environ["STUDIO_ENV_FILE"] = ENV
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server  # noqa: E402 -- imports agent, which imports _env first

from aiohttp.test_utils import TestClient, TestServer  # noqa: E402

SECRET = "s3cret-" + "x" * 40
POKE = os.path.join(os.environ["STUDIO_HOME"], "autoship.poke")
bad = []


def check(ok, what, got=None):
    print("%s  %s%s" % ("ok   " if ok else "FAIL ", what, "" if ok else "  -- %r" % (got,)))
    if not ok:
        bad.append(what)


def sign(body, secret=SECRET):
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def set_secret(s):
    with open(ENV, "w", encoding="utf-8") as f:
        f.write("STUDIO_TOKEN=t\n" + ("AUTOSHIP_HOOK_SECRET=%s\n" % s if s else ""))


def poked():
    p = os.path.exists(POKE)
    if p:
        os.remove(POKE)
    return p


async def main():
    push = json.dumps({"ref": "refs/heads/studio-poc", "after": "a" * 40}).encode()
    async with TestClient(TestServer(server.make_app("tok"))) as c:

        async def post(body, sig=None, event="push", **h):
            headers = {"X-GitHub-Event": event, "Content-Type": "application/json"} | h
            if sig is not None:
                headers["X-Hub-Signature-256"] = sig
            return await c.post(server.HOOK_PATH, data=body, headers=headers)

        set_secret("")
        r = await post(push, sign(push))
        check(r.status == 404 and not poked(), "no secret in the .env: there is no hook", r.status)

        set_secret(SECRET)  # read per request: no restart
        r = await post(push, sign(push))
        check(r.status == 202 and poked(), "a signed push to studio-poc: a nudge", r.status)
        r = await post(push)
        check(r.status == 401 and not poked(), "unsigned: refused", r.status)
        r = await post(push, "sha256=" + "0" * 64)
        check(r.status == 401 and not poked(), "a wrong signature: refused", r.status)
        r = await post(push, sign(push, "another-secret"))
        check(r.status == 401 and not poked(), "signed with another secret: refused", r.status)
        other = json.dumps({"ref": "refs/heads/studio-poc", "after": "b" * 40}).encode()
        r = await post(other, sign(push))
        check(r.status == 401 and not poked(), "a signature over another body: refused", r.status)
        r = await post(push, sign(push)[:20])
        check(r.status == 401 and not poked(), "a prefix of the signature: refused", r.status)
        r = await post(push, "sha1=" + hmac.new(SECRET.encode(), push, hashlib.sha1).hexdigest())
        check(r.status == 401 and not poked(), "the old sha1 header alone: refused", r.status)
        big = b"{" + b" " * (server.HOOK_MAX + 10) + b"}"
        r = await post(big, sign(big))
        check(r.status in (401, 413) and not poked(), "over HOOK_MAX: refused", r.status)

        ping = b'{"zen": "Keep it logically awesome."}'
        r = await post(ping, sign(ping), event="ping")
        check(r.status == 200 and not poked(), "a ping is answered, nothing else", r.status)
        for ref in ("refs/heads/main", "refs/tags/studio-stable", "refs/heads/studio-poc-x"):
            b = json.dumps({"ref": ref}).encode()
            r = await post(b, sign(b))
            check(r.status == 202 and not poked(), "a push to %s: ignored" % ref, r.status)
        r = await post(push, sign(push), event="issues")
        check(r.status == 202 and not poked(), "another event, even with the branch: ignored")
        junk = b"not json"
        r = await post(junk, sign(junk))
        check(r.status == 202 and not poked(), "a signed body that is not JSON: ignored", r.status)

        r = await c.get(server.HOOK_PATH)
        check(r.status == 405, "a GET is not the hook", r.status)
        r = await c.get("/api/costs")
        check(r.status == 401, "the token still guards /api/ (the hook is outside it)", r.status)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        shutil.rmtree(T, ignore_errors=True)
    print("all passed" if not bad else "%d FAILED: %s" % (len(bad), "; ".join(bad)))
    sys.exit(1 if bad else 0)
