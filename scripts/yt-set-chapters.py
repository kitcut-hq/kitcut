#!/usr/bin/env python
"""Put a chapter list into a YouTube video's description.

Reads a chapters file (one `MM:SS Title` per line, `config/chapters/<id>.txt`),
validates it against YouTube's rules for chapter markers to actually activate
(first at 00:00, ascending, each >= 10 s, at least 3 of them), then patches the
video's description through the Data API -- replacing a previous chapter block
if one exists, appending otherwise. The rest of the description is preserved
byte for byte; `videos.update` replaces the WHOLE snippet, so every other
snippet field is sent back exactly as fetched.

Auth is a one-time browser consent by the channel owner:

  1. In Google Cloud Console: create/pick a project, enable "YouTube Data API
     v3", configure the OAuth consent screen (External; add yourself as a test
     user), create an OAuth client ID of type "Desktop app", download the JSON
     to .yt-oauth/client_secret.json (gitignored).
  2. First run opens the browser for consent and caches the refresh token at
     .yt-oauth/token.json. Later runs are non-interactive.

Invoke as:
  python scripts/yt-set-chapters.py <video-id-or-url> --chapters config/chapters/<id>.txt
  python scripts/yt-set-chapters.py <video-id-or-url> --chapters ... --dry-run
"""
import sys, os, re, json, argparse

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


def credentials():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    creds = None
    if os.path.exists(TOKEN):
        creds = Credentials.from_authorized_user_file(TOKEN, SCOPES)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    elif not creds or not creds.valid:
        if not os.path.exists(CLIENT_SECRET):
            sys.exit(f"no {os.path.relpath(CLIENT_SECRET, _env.ROOT)} -- "
                     "download an OAuth 'Desktop app' client JSON there "
                     "(see this script's docstring for the console steps)")
        from google_auth_oauthlib.flow import InstalledAppFlow
        flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET, SCOPES)
        creds = flow.run_local_server(port=0)
    os.makedirs(OAUTH_DIR, exist_ok=True)
    with open(TOKEN, "w", encoding="utf-8") as f:
        f.write(creds.to_json())
    return creds


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("video", help="video id or any YouTube URL form")
    ap.add_argument("--chapters", required=True,
                    help="config/chapters/<id>.txt, one 'MM:SS Title' per line")
    ap.add_argument("--dry-run", action="store_true",
                    help="fetch and show the resulting description; no write")
    ap.add_argument("--replace", action="store_true",
                    help="allow overwriting chapters the description already "
                         "has; without this, an existing block is refused")
    args = ap.parse_args()

    vid = video_id(args.video)
    block = load_chapters(args.chapters)

    from googleapiclient.discovery import build
    yt = build("youtube", "v3", credentials=credentials())

    r = yt.videos().list(part="snippet", id=vid).execute()
    if not r.get("items"):
        sys.exit(f"video {vid} not found or not visible to this account")
    snippet = r["items"][0]["snippet"]

    new_desc, replaced = ch.splice(snippet.get("description", ""), block)
    if len(new_desc) > DESCRIPTION_LIMIT:
        sys.exit(f"resulting description is {len(new_desc)} chars; "
                 f"YouTube's limit is {DESCRIPTION_LIMIT}")

    print(f"video: {snippet['title']!r}")

    # Chapters already up there were written by a person and are not
    # recoverable from the API once overwritten. Show them and stop.
    if replaced is not None and replaced != block:
        print("\n!! this video ALREADY has chapters; the write would replace "
              f"{len(replaced.splitlines())} of them with "
              f"{len(block.splitlines())}:\n")
        for line in replaced.splitlines():
            print("  - " + line)
        print()
        for line in block.splitlines():
            print("  + " + line)
        if not args.replace:
            print("\nrefusing to overwrite. Compare them, and pass --replace "
                  "if the new list really is better.")
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
    yt.videos().update(part="snippet",
                       body={"id": vid, "snippet": snippet}).execute()

    check = yt.videos().list(part="snippet", id=vid).execute()
    got = check["items"][0]["snippet"]["description"]
    if block not in got:
        sys.exit("update call succeeded but the re-fetched description does "
                 "not contain the chapter block -- inspect it on YouTube")
    print(f"updated https://youtu.be/{vid} -- chapters verified in re-fetch")


if __name__ == "__main__":
    main()
