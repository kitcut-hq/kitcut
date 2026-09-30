"""Who a request is for: the site's workspaces and the people in them.

kitcut.ai makes every film, upload and library belong to a workspace (the site's lib/orgs.js): a
person's personal one, or an organisation of several people. It sends

    X-Client-Ip  "o:<workspace id>"   whose film it is, whose credits paid, whose library it uses
    X-Member     "u:<person id>"      who asked (a member of that workspace)

A person's personal workspace has the person's own id, and before workspaces the site sent the
person as "u:<id>" -- so "u:<id>" and "o:<id>" are the same owner. Everything that keys on the
client (ownership, the libraries, the limits) compares canon() forms, which is what lets a film
made before the switch still be its owner's after it, with no record rewritten. A library kept
under the old name is moved to the new one the first time it is used (library.dir_of).
"""

import re

PRINCIPAL = re.compile(r"^[uo]:[A-Za-z0-9_-]{1,62}$")  # a signed-in person or a workspace
MEMBER = re.compile(r"^u:[A-Za-z0-9_-]{1,62}$")


def canon(client):
    """One name per owner: "u:<id>" (a person, as the site said before workspaces) is their
    personal workspace "o:<id>". Anything else (an address, "local") is itself."""
    if isinstance(client, str) and client.startswith("u:") and PRINCIPAL.match(client):
        return "o:" + client[2:]
    return client


def same(a, b):
    """Are these the same owner? Never for a missing one."""
    return bool(a) and bool(b) and canon(a) == canon(b)


def signed_in(client):
    """A person or a workspace (a library of its own, films of its own), not an address."""
    return isinstance(client, str) and bool(PRINCIPAL.match(client))


def legacy(client):
    """The name a workspace's library was kept under before workspaces: "u:<id>" for "o:<id>"
    (only a personal workspace had one; an organisation's id never names a person)."""
    c = canon(client)
    return "u:" + c[2:] if isinstance(c, str) and c.startswith("o:") else None


def member_of(headers):
    """Who asked, from the site's X-Member header (trusted like X-Client-Ip: the request carries
    the studio's token), or None."""
    m = str(headers.get("X-Member", "")).strip()[:64]
    return m if MEMBER.match(m) else None
