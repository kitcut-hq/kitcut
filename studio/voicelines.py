#!/usr/bin/env python
"""A project's approved voice lines, from the command line (library.py; docs/studio-voice-lines.md).

    python studio/voicelines.py <client> <project> list
    python studio/voicelines.py <client> <project> add --film <id> --line N
    python studio/voicelines.py <client> <project> add --file take.wav --text "..." --like <id>
    python studio/voicelines.py <client> <project> delete <key>

The site approves a line of a finished episode (add --film --line does the same). --file puts in
a recording no episode has as a whole line -- a greeting cut from a longer take, a fixed one --
saying --text, in the voice (TTS, voice, model, language) of the episode --like names. Run it
where the studio's home is: on the VM, cd /srv/kitcut/repo && STUDIO_HOME=/srv/kitcut/studio
.venv/bin/python studio/voicelines.py ... Nothing here is paid for.
"""

import os
import sys
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import library  # noqa: E402
from film import Film  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("client", help='the person, "u:<id>"')
    ap.add_argument("project", help="the project, p-...")
    ap.add_argument("what", choices=["list", "add", "delete"])
    ap.add_argument("key", nargs="?", help="delete: the voice line's key")
    ap.add_argument("--film", help="add: the finished episode the line comes from")
    ap.add_argument("--line", type=int, help="add: which of its lines (0-based)")
    ap.add_argument("--file", help="add: a recording of just the line")
    ap.add_argument("--text", help="add --file: what the recording says, word for word")
    ap.add_argument("--like", help="add --file: an episode in the same voice")
    args = ap.parse_args()
    if not library.owner(args.client, args.project):
        sys.exit("not a person's project: %s %s" % (args.client, args.project))
    try:
        if args.what == "list":
            for v in library.listing(args.client, args.project)["voice"]:
                print(
                    "%s  %4.1f s  %s/%s  from %s line %s\n    %s"
                    % (v["key"], v["dur"], v["voice"], v["model"], v["film"], v["line"], v["text"])
                )
        elif args.what == "delete":
            if not library.delete_voice(args.client, args.project, args.key or ""):
                sys.exit("no such voice line: %s" % args.key)
            print("deleted", args.key)
        elif args.film is not None:
            e = library.add_voice_from_film(args.client, args.project, args.film, args.line)
            print(json.dumps(e, ensure_ascii=False, indent=1))
        else:
            if not (args.file and args.text and args.like):
                sys.exit("add needs --film and --line, or --file, --text and --like")
            like = Film.open(args.like)
            if like is None or like.record().get("client") != args.client:
                sys.exit("--like must be one of %s's films" % args.client)
            e = library.add_voice(
                args.client, args.project, args.text, args.file, library._vo_of(like)
            )
            print(json.dumps(e, ensure_ascii=False, indent=1))
    except library.VoiceError as e:
        sys.exit("%s (%d)" % (e.text, e.status))


if __name__ == "__main__":
    main()
