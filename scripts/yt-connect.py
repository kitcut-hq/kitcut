#!/usr/bin/env python
"""Connect this checkout to a YouTube channel, and prove which one it got.

The grant itself has always been created as a side effect of the first real
command -- yt-set-chapters.py patching a description, yt-upload.py sending a
file. That is a bad place to discover that the consent screen handed you your
personal account instead of the brand account that owns the videos: the fix is
a re-consent, and you are finding out mid-publish.

This is the same OAuth flow with nothing else attached. It answers two
questions and answers them separately:

  * "Am I connected?"    -- --check, which spends no consent and no upload
  * "Connect me to X"    -- --channel @handle, which refuses to file the grant
                            anywhere unless the channel that came back IS X

A channel is asserted by handle AND reported by id, because a handle can be
changed by its owner and an id cannot. The id is what belongs in a project
file.

THE BRAND-ACCOUNT TRAP, which cost an hour here. A YouTube channel is often a
*brand account* the login merely manages, and OAuth authenticates the LOGIN --
so `channels.list(mine=True)` returns the login's own channel unless the brand
account is picked at the chooser. Two things suppress that chooser:

  * an `Internal` consent screen -- a brand account is not an org account, so
    Google refuses it outright with `Error 403: org_internal`. The audience
    must be External.
  * a browser already signed in -- Google silently reuses the session and the
    chooser never renders, even with prompt=consent. Revoke the app at
    myaccount.google.com/connections and use --no-browser to paste the URL
    into a private window.

WHAT YOU NEED BEFORE THE FIRST RUN (once per machine):

  1. Google Cloud Console -> a project (any) -> "Enable APIs and services" ->
     enable "YouTube Data API v3".
  2. "OAuth consent screen": User type External. Add the Google account that
     owns the channel as a Test user.
     TRAP: while the consent screen is in "Testing", Google expires every
     refresh token after SEVEN DAYS, so publishing stops working each week
     with an invalid_grant. Press "Publish app" to move it to Production. It
     will warn that the app is unverified; that warning is about other
     people's data, and this grant only ever touches your own channel.
  3. "Credentials" -> Create credentials -> OAuth client ID -> Application
     type "Desktop app" -> download the JSON.
  4. Save it as .yt-oauth/client_secret.json in this repo (gitignored).
  5. Run this script with --channel. A browser opens; pick the BRAND account
     that owns the channel, not the personal login it sits under.

Invoke as:
  python scripts/yt-connect.py --check
  python scripts/yt-connect.py --channel @instafill_ai
  python scripts/yt-connect.py --channel @instafill_ai --reauth
  python scripts/yt-connect.py --channel @instafill_ai --reauth --no-browser
"""
import sys, os, argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import
from importlib import import_module  # noqa: E402

_yt = import_module("yt-set-chapters")

ENV_KEYS = ("YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET",
            "YOUTUBE_REFRESH_TOKEN")


def state():
    """What this machine holds, before anything is spent."""
    oauth = os.path.join(_env.ROOT, ".yt-oauth")
    tokens = []
    if os.path.isdir(oauth):
        tokens = sorted(f for f in os.listdir(oauth)
                        if f.startswith("token") and f.endswith(".json"))
    return {
        "client_secret": os.path.exists(_yt.CLIENT_SECRET),
        "env_grant": all(os.environ.get(k) for k in ENV_KEYS),
        "tokens": tokens,
    }


def describe(yt):
    """The channel a live credential actually points at."""
    r = yt.channels().list(part="snippet,statistics,contentDetails",
                           mine=True).execute()
    items = r.get("items") or []
    if not items:
        sys.exit("this grant owns no channel -- you consented as an account "
                 "that has never created one. Re-run with --reauth and pick "
                 "the brand account.")
    it = items[0]
    sn, st = it["snippet"], it.get("statistics", {})
    return {
        "id": it["id"],
        "title": sn.get("title", ""),
        "handle": (sn.get("customUrl") or "").lstrip("@").lower(),
        "videos": st.get("videoCount", "?"),
        "subscribers": ("hidden" if st.get("hiddenSubscriberCount")
                        else st.get("subscriberCount", "?")),
    }


def service(creds):
    from googleapiclient.discovery import build
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def report(ch):
    print("  channel:     %s" % ch["title"])
    print("  handle:      @%s" % (ch["handle"] or "(none set)"))
    print("  id:          %s   <- this is what a project file should carry"
          % ch["id"])
    print("  videos:      %s" % ch["videos"])
    print("  subscribers: %s" % ch["subscribers"])


def do_check(args):
    """Report without consenting: cheap, and safe to run any time."""
    s = state()
    print("== what this checkout holds ==")
    print("  %s .yt-oauth/client_secret.json  %s"
          % ("OK " if s["client_secret"] else "-- ",
             "" if s["client_secret"]
             else "(missing: see this script's docstring, steps 1-4)"))
    print("  %s .env grant (%s)"
          % ("OK " if s["env_grant"] else "-- ", ", ".join(ENV_KEYS)))
    print("  %s per-channel tokens: %s"
          % ("OK " if s["tokens"] else "-- ",
             ", ".join(s["tokens"]) if s["tokens"] else "none"))

    if not (s["env_grant"] or s["tokens"]):
        print("\nNot connected. Nothing here can upload or write chapters.")
        print("Next: put the client JSON in place, then run")
        print("  python scripts/yt-connect.py --channel @your_handle")
        return 1

    print("\n== asking Google who this grant is ==")
    try:
        creds = _yt.credentials(handle=args.channel)
        ch = describe(service(creds))
    except Exception as e:                      # noqa: BLE001 -- report, not raise
        print("  refresh FAILED: %s" % e)
        print("\nA grant that will not refresh is usually one of two things:")
        print("  * the consent screen is still in Testing -- refresh tokens")
        print("    expire after 7 days there (docstring step 2), or")
        print("  * the grant was revoked in the Google account.")
        print("Fix either way: python scripts/yt-connect.py --channel "
              "@your_handle --reauth")
        return 1
    report(ch)
    if args.channel:
        want = args.channel.lstrip("@").lower()
        ok = want in (ch["handle"], ch["title"].lower())
        print("\n  %s grant points at %s"
              % ("OK  " if ok else "WRONG:", args.channel))
        if not ok:
            return 1
    print("\nConnected. Uploads and chapter writes will go to the channel "
          "above.")
    return 0


def do_connect(args):
    """Consent if needed, then refuse to keep a grant for the wrong channel."""
    want = args.channel.lstrip("@").lower()
    s = state()
    if not (s["client_secret"] or s["env_grant"] or s["tokens"]):
        sys.exit("no .yt-oauth/client_secret.json and no existing grant -- "
                 "there is nothing to connect with.\nSee this script's "
                 "docstring, steps 1-4 (python scripts/yt-connect.py --help).")

    print("Opening Google's consent screen..." if args.reauth
          else "Using the grant already on this machine (--reauth forces a "
               "new consent)...")
    creds = _yt.credentials(handle=args.channel, reauth=args.reauth,
                            open_browser=not args.no_browser)
    ch = describe(service(creds))
    print()
    report(ch)

    if want not in (ch["handle"], ch["title"].lower()):
        token = _yt.channel_token(args.channel)
        if os.path.exists(token):
            # The grant is for someone else; leaving it filed under this
            # handle would make every later run confidently wrong.
            os.remove(token)
        sys.exit("\nREFUSED: you asked for %s and Google handed back '%s' "
                 "(@%s).\nAt the chooser pick the BRAND account that owns the "
                 "channel -- and note the chooser lists the brand account's "
                 "own name, which a renamed channel no longer matches.\n"
                 "Re-run: python scripts/yt-connect.py --channel %s --reauth"
                 % (args.channel, ch["title"], ch["handle"], args.channel))

    print("\nConnected: the grant is filed as %s"
          % os.path.relpath(_yt.channel_token(args.channel), _env.ROOT))
    print("Verify any time with:  python scripts/yt-connect.py --check "
          "--channel %s" % args.channel)
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--channel",
                    help="handle or title the grant MUST point at, e.g. "
                         "@instafill_ai")
    ap.add_argument("--check", action="store_true",
                    help="report what this machine holds and who the grant "
                         "is, without consenting to anything")
    ap.add_argument("--no-browser", action="store_true",
                    help="print the consent URL instead of opening a browser, "
                         "so it can be pasted into a PRIVATE window -- the "
                         "only reliable way to reach a brand-account channel")
    ap.add_argument("--reauth", action="store_true",
                    help="force a fresh Google consent; use when adding a "
                         "channel or after a revoked grant")
    args = ap.parse_args()

    if args.check or not args.channel:
        return do_check(args)
    return do_connect(args)


if __name__ == "__main__":
    sys.exit(main())
