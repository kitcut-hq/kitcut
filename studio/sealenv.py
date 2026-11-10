#!/usr/bin/env python
"""The studio machine's keys, sealed so that only the key vault can open them.

    python studio/sealenv.py --plan          what would be sealed, and whether it changed; writes nothing
    python studio/sealenv.py                 seal (before every pass of the mirror: kitcut-backup.service)
    python studio/sealenv.py --names FILE    what a sealed file holds: names, sizes, when, by which key
    python studio/sealenv.py --open FILE     (the laptop) open one; the unwrapped key is read from
        [--file NAME | --out DIR | --tar]    stdin as base64, never from a command line. Prints one
                                             file (default .env), writes them all into DIR, or
                                             sends them all on as a tar
    (from the laptop: ops.sh secrets seal | check | names; deploy/unseal.sh opens one)

Why: the machine's .env is the one file that holds every key the studio uses -- the films' storage,
the Claude login, the database, the site's token -- and with the tunnel's credential it was on one
disk and nowhere else (KI-064, KI-065). Storing them as key vault secrets needs a role this
session may not give itself; sealing needs none, and is better in one way: it is always current.

How. What is sealed: REPO/.env, and ~/.cloudflared/<uuid>.json and cert.pem. They are packed into
one tar and encrypted with a key made for that one sealing (AES-256-GCM); that key is wrapped with
the public half of an RSA key that lives in Azure Key Vault (kitcut-kv-prod, studio-env-kek:
wrapKey and unwrapKey only, deploy/studio-env-kek.pub.pem and .json here). The public half can
only seal. Opening needs the vault to unwrap the key (its unwrapKey operation), so it needs an
Azure sign-in allowed to use that key -- and nothing on the machine, in the repository or in the
bucket can open a sealed file by itself.

Where: STUDIO_HOME/sealed/studio-secrets.json, so the mirror carries it with the rest of the home
(and keeps the one before it for 30 days). It is written again only when one of the files
changed, so a pass that finds nothing new uploads nothing.

A rehearsal (STUDIO_DRILL=1) seals nothing: its .env is a cut-down copy, not the studio's.
"""

import io
import os
import sys
import glob
import json
import time
import base64
import socket
import hashlib
import tarfile
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import backup  # noqa: E402 -- the stdlib only: the studio's home, repo and .env

PUB = os.path.join(HERE, "deploy", "studio-env-kek.pub.pem")
KEY = os.path.join(
    HERE, "deploy", "studio-env-kek.json"
)  # which vault key that is: vault, name, version
OUT = os.path.join(backup.HOME, "sealed", "studio-secrets.json")
ALG = "RSA-OAEP-256+A256GCM"


def sources(env_file=None, tunnel_dir=None):
    """{name in the sealed file: path} of what there is to seal."""
    env_file = env_file or backup.ENV_FILE
    tunnel_dir = tunnel_dir or os.path.join(os.path.expanduser("~"), ".cloudflared")
    out = {}
    if os.path.isfile(env_file):
        out[".env"] = env_file
    for p in sorted(glob.glob(os.path.join(tunnel_dir, "*.json"))) + [
        os.path.join(tunnel_dir, "cert.pem")
    ]:
        if os.path.isfile(p):
            out["cloudflared/" + os.path.basename(p)] = p
    return out


def listing(src):
    """[{"name", "bytes", "sha256"}]: enough to tell whether a file changed, nothing of what it says."""
    out = []
    for name, path in src.items():
        with open(path, "rb") as f:
            body = f.read()
        out.append({"name": name, "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()})
    return out


def _pack(src):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for name, path in src.items():
            info = tarfile.TarInfo(name)
            with open(path, "rb") as f:
                body = f.read()
            info.size, info.mode, info.mtime = len(body), 0o600, int(os.path.getmtime(path))
            tar.addfile(info, io.BytesIO(body))
    return buf.getvalue()


def seal(src, pub_pem, key_info=None):
    """The sealed form of these files: a dict that is safe to write anywhere."""
    from cryptography.hazmat.primitives import hashes, serialization  # noqa: PLC0415
    from cryptography.hazmat.primitives.asymmetric import padding  # noqa: PLC0415
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa: PLC0415

    key, nonce = AESGCM.generate_key(256), os.urandom(12)
    files = listing(src)
    head = {"v": 1, "alg": ALG, "key": key_info or {}, "files": files, "host": socket.gethostname()}
    head["at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    # what the file says about itself is bound to what it holds: a changed list fails to open
    aad = json.dumps(head, sort_keys=True).encode()
    ct = AESGCM(key).encrypt(nonce, _pack(src), aad)
    pub = serialization.load_pem_public_key(pub_pem)
    oaep = padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
    b64 = lambda b: base64.b64encode(b).decode()  # noqa: E731
    return dict(head, wrapped=b64(pub.encrypt(key, oaep)), nonce=b64(nonce), ct=b64(ct))


def unseal(sealed, key):
    """{name: bytes} of a sealed dict, given its key unwrapped (32 bytes). Raises when the file
    was changed in any way, or the key is not its key."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa: PLC0415

    head = {k: v for k, v in sealed.items() if k not in ("wrapped", "nonce", "ct")}
    aad = json.dumps(head, sort_keys=True).encode()
    plain = AESGCM(key).decrypt(
        base64.b64decode(sealed["nonce"]), base64.b64decode(sealed["ct"]), aad
    )
    out = {}
    with tarfile.open(fileobj=io.BytesIO(plain)) as tar:
        for m in tar.getmembers():
            out[m.name] = tar.extractfile(m).read()
    return out


def _b64(text):
    """A key as base64 or base64url, padded or not (the vault answers base64url, unpadded)."""
    t = text.strip().replace("-", "+").replace("_", "/")
    return base64.b64decode(t + "=" * (-len(t) % 4))


def last(path=None):
    try:
        with open(path or OUT, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def changed(src, sealed):
    """Whether these files are not what the sealed file holds (by name, size and checksum)."""
    key = lambda rows: sorted((r["name"], r["bytes"], r["sha256"]) for r in rows)  # noqa: E731
    return key(listing(src)) != key(sealed.get("files") or [])


def run(plan=False):
    """Seal when something changed. -> (what happened, the names)."""
    if backup.setting("STUDIO_DRILL") == "1":
        return "a rehearsal (STUDIO_DRILL=1): nothing is sealed", []
    src = sources()
    if ".env" not in src:
        return "no .env at %s: nothing to seal" % backup.ENV_FILE, []
    names = sorted(src)
    if not changed(src, last()):
        return "unchanged since %s" % last().get("at"), names
    if plan:
        return "would seal (changed, or never sealed)", names
    with open(PUB, "rb") as f:
        pub = f.read()
    with open(KEY, encoding="utf-8") as f:
        info = json.load(f)
    sealed = seal(src, pub, info)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    tmp = OUT + ".%d.tmp" % os.getpid()
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(sealed, f, indent=1)
    os.replace(tmp, OUT)
    return "sealed into %s" % OUT, names


def names_of(sealed):
    k = sealed.get("key") or {}
    lines = ["sealed %s on %s, for the key %s/%s (version %s)" % (
        sealed.get("at"), sealed.get("host"), k.get("vault"), k.get("name"), str(k.get("version"))[:8])]  # fmt: skip
    lines += ["  %-34s %6d bytes" % (r["name"], r["bytes"]) for r in sealed.get("files") or []]
    return "\n".join(lines)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--plan", action="store_true", help="what would be sealed; writes nothing")
    g.add_argument("--names", metavar="FILE", help="what a sealed file holds, without opening it")
    g.add_argument("--open", metavar="FILE", help="open a sealed file; its key (base64) on stdin")
    ap.add_argument("--file", default=".env", help="--open: the one file to print (default .env)")
    ap.add_argument("--out", metavar="DIR", help="--open: write every file into DIR instead")
    ap.add_argument(
        "--tar", action="store_true", help="--open: every file, as a tar on stdout (to pipe on)"
    )
    ap.add_argument(
        "--wrapped", action="store_true", help="--names: print only the wrapped key, for the vault"
    )
    a = ap.parse_args()
    if a.names:
        s = last(a.names)
        if not s:
            sys.exit("not a sealed file: %s" % a.names)
        # for the vault's unwrapKey, which takes and answers base64url without padding
        print(
            s["wrapped"].replace("+", "-").replace("/", "_").rstrip("=")
            if a.wrapped
            else names_of(s)
        )
    elif a.open:
        s = last(a.open)
        if not s:
            sys.exit("not a sealed file: %s" % a.open)
        try:
            got = unseal(s, _b64(sys.stdin.read()))
        except Exception as e:  # noqa: BLE001 -- a wrong key and a changed file fail the same way
            sys.exit(
                "it does not open: the key is not this file's, or the file was changed (%s)"
                % type(e).__name__
            )
        if a.tar:
            with tarfile.open(fileobj=sys.stdout.buffer, mode="w|") as tar:
                for name, body in sorted(got.items()):
                    info = tarfile.TarInfo(name)
                    info.size, info.mode = len(body), 0o600
                    tar.addfile(info, io.BytesIO(body))
        elif a.out:
            for name, body in got.items():
                p = os.path.join(a.out, *name.split("/"))
                os.makedirs(os.path.dirname(p), exist_ok=True)
                with os.fdopen(os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "wb") as f:
                    f.write(body)
            print("\n".join(sorted(got)), file=sys.stderr)
        elif a.file in got:
            sys.stdout.buffer.write(got[a.file])
        else:
            sys.exit("no %s in it: %s" % (a.file, ", ".join(sorted(got))))
    else:
        what, names = run(a.plan)
        print("%s%s" % (what, ": " + ", ".join(names) if names else ""))
