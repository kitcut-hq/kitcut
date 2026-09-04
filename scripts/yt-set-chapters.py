#!/usr/bin/env python
"""Put a chapter list into a YouTube video's description.

Reads a chapters file (one `MM:SS Title` per line, `config/chapters/<id>.txt`),
checks it, then patches the video's description through the Data API --
replacing a previous chapter block if one exists, appending otherwise. The rest
of the description is preserved byte for byte; `videos.update` replaces the
WHOLE snippet, so every other snippet field is sent back exactly as fetched.

Only a count below three is refused. The other rules everyone quotes -- first
mark at 0:00, ten seconds apart, in order -- are printed as notes, because
measuring the published videos on this channel showed YouTube does not enforce
them; see `_ytchapters.py` for what it actually does. Chapters already in a
description are never overwritten without --replace.

Auth is the channel owner's OAuth consent, and the owner is the CHANNEL that
holds the videos, not the person's own account -- consenting as a personal
account yields a token that can read the videos and not write them. The script
compares the two up front and says so.

  1. Google Cloud Console: enable "YouTube Data API v3", configure the OAuth
     consent screen (External; add yourself as a test user), create an OAuth
     client ID of type "Desktop app", save the JSON to
     .yt-oauth/client_secret.json (gitignored).
  2. The first run opens a browser. Pick the channel that owns the videos.
  3. The resulting grant is written to .env as YOUTUBE_CLIENT_ID /
     YOUTUBE_CLIENT_SECRET / YOUTUBE_REFRESH_TOKEN, which is where this repo
     keeps its secrets and what later runs read. .yt-oauth/token.json is kept
     as a fallback, so deleting that directory no longer costs the grant.

Invoke as:
  python scripts/yt-set-chapters.py <video-id-or-url> --chapters config/chapters/<id>.txt
  python scripts/yt-set-chapters.py <video-id-or-url> --chapters ... --dry-run
  python scripts/yt-set-chapters.py --video=-qKcpLSk0iU --chapters ...   # id starting with '-'
"""

import sys
import os
import re
import json
import time
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import
import _ytchapters as ch  # noqa: E402

SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]
OAUTH_DIR = os.path.join(_env.ROOT, ".yt-oauth")
CLIENT_SECRET = os.path.join(OAUTH_DIR, "client_secret.json")
TOKEN = os.path.join(OAUTH_DIR, "token.json")

DESCRIPTION_LIMIT = 5000


def video_id(arg):
    m = re.search(r"(?:youtu\.be/|[?&]v=|/shorts/)([\w-]{11})", arg)
    if m:
        return m.group(1)
    if re.fullmatch(r"[\w-]{11}", arg):
        return arg
    sys.exit(f"cannot parse a video id out of {arg!r}")


def load_chapters(path):
    """Parse and validate; returns the block exactly as it should be pasted."""
    lines = []
    for raw in open(path, encoding="utf-8"):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if not ch.CHAPTER_LINE.match(line):
            sys.exit(f"not a 'MM:SS Title' line: {line!r}")
        lines.append(line)

    marks = ch.parse_marks("\n".join(lines))
    errs = ch.fatal(marks)
    if errs:
        sys.exit("refusing:\n  - " + "\n  - ".join(errs))
    for note in ch.advisories(marks):
        print(f"note: {note}")
    return "\n".join(l for _, l in marks)


ENV_KEYS = ("YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN")


def _env_credentials():
    """Credentials from .env, or None if it does not carry all three keys.

    A refresh token plus the client pair is the whole of a long-lived grant --
    the access token is derived and short-lived, so there is nothing else worth
    storing. `_env.py` has already loaded .env into the environment.
    """
    got = {k: os.environ.get(k) for k in ENV_KEYS}
    if not all(got.values()):
        return None
    from google.oauth2.credentials import Credentials

    return Credentials(
        token=None,
        refresh_token=got["YOUTUBE_REFRESH_TOKEN"],
        client_id=got["YOUTUBE_CLIENT_ID"],
        client_secret=got["YOUTUBE_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token",
        scopes=SCOPES,
    )


def _save_to_env(creds):
    """Upsert the grant into .env, rewriting only its own three keys."""
    path = os.path.join(_env.ROOT, ".env")
    lines = []
    if os.path.exists(path):
        lines = open(path, encoding="utf-8").read().split("\n")
    values = {
        "YOUTUBE_CLIENT_ID": creds.client_id,
        "YOUTUBE_CLIENT_SECRET": creds.client_secret,
        "YOUTUBE_REFRESH_TOKEN": creds.refresh_token,
    }
    if not all(values.values()):
        return  # nothing durable to save; keep token.json
    out, seen = [], set()
    for line in lines:
        key = line.split("=", 1)[0].strip() if "=" in line else ""
        if key in values:
            out.append(f"{key}={values[key]}")
            seen.add(key)
        else:
            out.append(line)
    missing = [k for k in ENV_KEYS if k not in seen]
    if missing:
        if out and out[-1].strip():
            out.append("")
        out.append("# YouTube Data API, for yt-set-chapters.py. Gitignored.")
        out += [f"{k}={values[k]}" for k in missing]
        out.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out))


def channel_token(handle):
    """Where the grant for one channel lives.

    One Google login can own several channels, and a grant points at exactly
    one of them. Keeping them in a single token.json meant every switch between
    channels burned the previous grant and needed a fresh consent, so a token is
    filed under the handle it was proved to point at: `.yt-oauth/token-<h>.json`.
    The bare token.json stays as the unlabelled default, which is what an
    existing checkout already has.
    """
    h = (handle or "").lstrip("@").strip().lower()
    if not h:
        return TOKEN
    safe = "".join(c for c in h if c.isalnum() or c in "-_.")
    return os.path.join(OAUTH_DIR, "token-%s.json" % safe)


def credentials(handle=None, reauth=False):
    """A usable credential, preferring .env over the cached token file.

    .env is where this repo already keeps secrets, and a refresh token there
    survives deleting .yt-oauth/ -- which is the documented fix for a wrong
    channel, and used to throw away the grant along with the mistake.

    With `handle`, a per-channel token file is used and .env is consulted only
    when no such file exists -- otherwise the single .env refresh token would
    win for every channel and quietly send uploads to whichever one it belongs
    to. yt-upload.py asserts the channel afterwards regardless, so a mismatch
    refuses rather than misfiles.
    """
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    token_path = channel_token(handle)
    creds = None
    # `reauth` forces a fresh consent and files it under the handle. Without it
    # a named channel with no token of its own would fall back to .env, get a
    # perfectly valid grant for a DIFFERENT channel, and be refused by the
    # channel assertion -- correct, but with no way to ever authorise the new
    # one. This is that way.
    if not reauth:
        if not (handle and os.path.exists(token_path)):
            creds = _env_credentials()
    if creds:
        creds.refresh(Request())  # no access token is stored; mint one
        return creds

    if os.path.exists(token_path) and not reauth:
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    elif not creds or not creds.valid:
        if not os.path.exists(CLIENT_SECRET):
            sys.exit(
                f"no {os.path.relpath(CLIENT_SECRET, _env.ROOT)} -- "
                "download an OAuth 'Desktop app' client JSON there "
                "(see this script's docstring for the console steps)"
            )
        from google_auth_oauthlib.flow import InstalledAppFlow

        flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET, SCOPES)
        # offline + consent so Google actually returns a refresh token; it
        # withholds one on a repeat grant otherwise, leaving .env unfillable.
        creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
    os.makedirs(OAUTH_DIR, exist_ok=True)
    with open(token_path, "w", encoding="utf-8") as f:
        f.write(creds.to_json())
    # .env holds ONE refresh token and is the fallback for the unlabelled
    # default. Writing a per-channel grant there would make it the answer for
    # every channel, which is the bug this split exists to remove.
    if not handle:
        _save_to_env(creds)
    return creds


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    # nargs="?" plus --video, because plenty of YouTube ids begin with "-"
    # (e.g. -qKcpLSk0iU) and argparse reads those as flags. A bare "--" does
    # not save you either: it must come after every option, which is not how
    # anyone types it.
    ap.add_argument("video", nargs="?", help="video id or any YouTube URL form")
    ap.add_argument("--video", dest="video_opt", help="same thing, for ids that start with '-'")
    ap.add_argument(
        "--chapters", required=True, help="config/chapters/<id>.txt, one 'MM:SS Title' per line"
    )
    ap.add_argument(
        "--dry-run", action="store_true", help="fetch and show the resulting description; no write"
    )
    ap.add_argument(
        "--replace",
        action="store_true",
        help="allow overwriting chapters the description already "
        "has; without this, an existing block is refused",
    )
    ap.add_argument(
        "--lint", action="store_true", help="check the chapters file and stop; no network at all"
    )
    ap.add_argument(
        "--duration", type=int, help="with --lint, also flag marks past this many seconds"
    )
    args = ap.parse_args()

    if not (args.video or args.video_opt):
        ap.error("give a video id, positionally or with --video")
    vid = video_id(args.video_opt or args.video)
    block = load_chapters(args.chapters)

    if args.lint:
        marks = ch.parse_marks(block)
        print(f"{len(marks)} chapters, {ch.fmt_ts(marks[0][0])} .. {ch.fmt_ts(marks[-1][0])}")
        if args.duration:
            over = [l for t, l in marks if t >= args.duration]
            for l in over:
                print(f"!! past the end ({ch.fmt_ts(args.duration)}): {l}")
            if over:
                sys.exit(1)
        return

    from googleapiclient.discovery import build

    yt = build("youtube", "v3", credentials=credentials())

    r = yt.videos().list(part="snippet", id=vid).execute()
    if not r.get("items"):
        sys.exit(f"video {vid} not found or not visible to this account")
    snippet = r["items"][0]["snippet"]

    # Reading a video works for anyone; only its owner may write it. Checking
    # the token's channel here turns an opaque "403 Forbidden" from the update
    # into the actual problem, which is almost always that the consent screen's
    # channel picker chose a personal account over the brand channel.
    mine = yt.channels().list(part="snippet", mine=True).execute().get("items")
    owner = snippet.get("channelId")
    if mine and owner not in {c["id"] for c in mine}:
        sys.exit(
            f"signed in as {mine[0]['snippet']['title']!r} "
            f"({mine[0]['id']}), but this video belongs to "
            f"{snippet.get('channelTitle')!r} ({owner}).\n"
            f"Only the owning channel can edit it. Delete "
            f"{os.path.relpath(TOKEN, _env.ROOT)} and rerun; at the Google "
            f"consent screen pick the {snippet.get('channelTitle')!r} channel "
            f"rather than a personal account."
        )

    new_desc, replaced = ch.splice(snippet.get("description", ""), block)
    if len(new_desc) > DESCRIPTION_LIMIT:
        sys.exit(
            f"resulting description is {len(new_desc)} chars; "
            f"YouTube's limit is {DESCRIPTION_LIMIT}"
        )

    print(f"video: {snippet['title']!r}")

    # Chapters already up there were written by a person and are not
    # recoverable from the API once overwritten. Show them and stop.
    if replaced is not None and replaced != block:
        print(
            "\n!! this video ALREADY has chapters; the write would replace "
            f"{len(replaced.splitlines())} of them with "
            f"{len(block.splitlines())}:\n"
        )
        for line in replaced.splitlines():
            print("  - " + line)
        print()
        for line in block.splitlines():
            print("  + " + line)
        if not args.replace:
            print(
                "\nrefusing to overwrite. Compare them, and pass --replace "
                "if the new list really is better."
            )
            return
    print("--- resulting description " + "-" * 40)
    print(new_desc)
    print("-" * 66)

    if args.dry_run:
        print("dry run: nothing written")
        return
    if new_desc == snippet.get("description", ""):
        print("description already contains exactly this block; nothing to do")
        return

    snippet["description"] = new_desc
    # snippet.title and snippet.categoryId are REQUIRED on update; sending the
    # whole fetched snippet back keeps them and everything else intact.
    yt.videos().update(part="snippet", body={"id": vid, "snippet": snippet}).execute()

    # Read-after-write here is not immediately consistent: a re-fetch straight
    # after a successful update can still return the OLD description, which
    # made this check cry failure over a write that had in fact landed. Give
    # it a few tries before believing the bad news.
    for attempt in range(4):
        if attempt:
            time.sleep(2)
        check = yt.videos().list(part="snippet", id=vid).execute()
        got = check["items"][0]["snippet"]["description"]
        if block in got:
            print(
                f"updated https://youtu.be/{vid} -- verified in re-fetch"
                + (f" (after {attempt + 1} reads)" if attempt else "")
            )
            return
    sys.exit(
        "update call succeeded but the description still does not carry "
        "the chapter block after several reads -- inspect it on YouTube"
    )


if __name__ == "__main__":
    main()
