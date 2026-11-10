#!/usr/bin/env python
"""sealenv.py with a key pair made here standing in for the key vault's: no Azure, no network.

    python studio/test_sealenv.py

What is sealed opens again, byte for byte, with the key only the private half can unwrap -- and
with nothing else: a sealed file holds no line of what it seals, a changed file does not open, nor
does one whose list of names was edited, nor one opened with another key. It is written again
only when a file changed. A rehearsal seals nothing. And what is committed here is what it claims
to be: the public half of an RSA key of 3072 bits, with the vault, name and version it belongs to.
"""

import os
import sys
import json
import base64
import shutil
import tempfile

ROOT = tempfile.mkdtemp(prefix="studio-seal-test-")
os.environ["STUDIO_HOME"] = os.path.join(ROOT, "studio")
os.environ["STUDIO_REPO"] = os.path.join(ROOT, "repo")
os.environ["STUDIO_ENV_FILE"] = os.path.join(ROOT, "repo", ".env")
os.environ["HOME"] = os.environ["USERPROFILE"] = os.path.join(ROOT, "home")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backup  # noqa: E402
import sealenv  # noqa: E402
from cryptography.hazmat.primitives import hashes, serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import padding, rsa  # noqa: E402

bad = []
SECRET = "sk-test-0123456789-not-a-real-key"
ENV = "ANTHROPIC_API_KEY=%s\nSTUDIO_R2_SECRET=r2-secret-value\nSTUDIO_BROWSERS=4\n" % SECRET
TUNNEL = '{"AccountTag":"acct","TunnelSecret":"tunnel-secret-value","TunnelID":"23646b24"}'


def check(ok, what, got=None):
    print("%s  %s%s" % ("ok   " if ok else "FAIL ", what, "" if ok else "  -- %r" % (got,)))
    if not ok:
        bad.append(what)


def put(path, body):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(body)


def vault():
    """A key pair standing in for the vault's: (public PEM, unwrap(wrapped b64) -> key bytes)."""
    priv = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    pem = priv.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    oaep = padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
    return pem, lambda wrapped: priv.decrypt(base64.b64decode(wrapped), oaep)


def opens(sealed, key):
    try:
        return sealenv.unseal(sealed, key)
    except Exception as e:  # noqa: BLE001 -- what is asked is only whether it opens
        return type(e).__name__


def seals_and_opens():
    tunnel = os.path.join(os.environ["HOME"], ".cloudflared")
    put(backup.ENV_FILE, ENV)
    put(os.path.join(tunnel, "23646b24-7489-4f62-b86b-6ede85ea0357.json"), TUNNEL)
    put(os.path.join(tunnel, "cert.pem"), "-----BEGIN ARGO TUNNEL TOKEN-----\ncert-secret\n")
    src = sealenv.sources()
    want = [".env", "cloudflared/23646b24-7489-4f62-b86b-6ede85ea0357.json", "cloudflared/cert.pem"]
    check(
        sorted(src) == want, "the .env and the tunnel's two files are what is sealed", sorted(src)
    )

    pem, unwrap = vault()
    sealed = sealenv.seal(src, pem, {"vault": "v", "name": "n", "version": "1"})
    text = json.dumps(sealed)
    leaked = [
        s for s in (SECRET, "r2-secret-value", "tunnel-secret-value", "cert-secret") if s in text
    ]
    check(not leaked, "a sealed file holds no line of what it seals", leaked)
    check(
        sealed["alg"] == sealenv.ALG and len(base64.b64decode(sealed["wrapped"])) == 384,
        "its key is wrapped for a 3072-bit RSA key",
    )

    got = opens(sealed, unwrap(sealed["wrapped"]))
    check(
        isinstance(got, dict) and got[".env"].decode() == ENV,
        "with the key the vault unwraps it opens, byte for byte",
        got,
    )
    check(isinstance(got, dict) and got[want[1]].decode() == TUNNEL, "the tunnel's credential too")

    check(
        opens(sealed, os.urandom(32)) == "InvalidTag",
        "another key does not open it",
        opens(sealed, os.urandom(32)),
    )
    _, other = vault()
    try:
        other(sealed["wrapped"])
        unwrapped = True
    except ValueError:
        unwrapped = False
    check(not unwrapped, "and another key pair cannot unwrap its key")
    key = unwrap(sealed["wrapped"])
    ct = bytearray(base64.b64decode(sealed["ct"]))
    ct[10] ^= 1
    check(
        opens(dict(sealed, ct=base64.b64encode(bytes(ct)).decode()), key) == "InvalidTag",
        "a changed file does not open",
    )
    renamed = dict(sealed, files=[dict(sealed["files"][0], name="other")] + sealed["files"][1:])
    check(opens(renamed, key) == "InvalidTag", "nor one whose list of names was edited")
    check(
        opens(dict(sealed, host="elsewhere"), key) == "InvalidTag",
        "nor one that says it came from another machine",
    )
    return pem, unwrap


def only_when_changed(pem, unwrap):
    real_pub, real_key = sealenv.PUB, sealenv.KEY
    sealenv.PUB = os.path.join(ROOT, "pub.pem")
    sealenv.KEY = os.path.join(ROOT, "key.json")
    with open(sealenv.PUB, "wb") as f:
        f.write(pem)
    put(sealenv.KEY, json.dumps({"vault": "v", "name": "n", "version": "1"}))
    try:
        what, names = sealenv.run(plan=True)
        check(
            "would seal" in what and not os.path.exists(sealenv.OUT),
            "a plan says what it would seal and writes nothing",
            what,
        )
        what, names = sealenv.run()
        check(
            "sealed into" in what and len(names) == 3 and os.path.isfile(sealenv.OUT),
            "the first run seals",
            what,
        )
        first = sealenv.last()
        what, _ = sealenv.run()
        check(
            "unchanged" in what and sealenv.last() == first,
            "a second run, nothing changed, writes nothing",
            what,
        )
        put(backup.ENV_FILE, ENV + "STUDIO_FILM_MEM_GB=6\n")
        what, _ = sealenv.run()
        second = sealenv.last()
        check(
            "sealed into" in what and second["ct"] != first["ct"],
            "a changed .env is sealed again",
            what,
        )
        got = opens(second, unwrap(second["wrapped"]))
        check(
            isinstance(got, dict) and b"STUDIO_FILM_MEM_GB=6" in got[".env"],
            "and what opens is the new one",
        )
        check(second["wrapped"] != first["wrapped"], "under a key of its own")
        if os.name != "nt":
            check(
                oct(os.stat(sealenv.OUT).st_mode & 0o777) == "0o600",
                "the sealed file is the owner's alone",
            )
        put(backup.ENV_FILE, ENV + "STUDIO_DRILL=1\n")
        what, names = sealenv.run()
        check(
            "rehearsal" in what and not names and sealenv.last() == second,
            "a rehearsal seals nothing",
            what,
        )
        os.remove(backup.ENV_FILE)
        check("nothing to seal" in sealenv.run()[0], "no .env, nothing to seal")
    finally:
        sealenv.PUB, sealenv.KEY = real_pub, real_key


def what_is_committed():
    with open(sealenv.PUB, "rb") as f:
        pub = serialization.load_pem_public_key(f.read())
    check(
        isinstance(pub, rsa.RSAPublicKey) and pub.key_size == 3072,
        "the committed key is the public half of a 3072-bit RSA key",
    )
    with open(sealenv.PUB, encoding="ascii") as f:
        check("PRIVATE" not in f.read(), "and nothing private is in the file")
    with open(sealenv.KEY, encoding="utf-8") as f:
        info = json.load(f)
    check(
        all(info.get(k) for k in ("vault", "name", "version")),
        "it says which vault key it is: vault, name, version",
        info,
    )
    check(
        info["kid"].endswith("/keys/%s/%s" % (info["name"], info["version"])),
        "and its key id agrees",
        info.get("kid"),
    )
    check(
        os.path.dirname(sealenv.OUT) == os.path.join(backup.HOME, "sealed"),
        "the sealed file is in the home, where the mirror takes it",
    )


if __name__ == "__main__":
    try:
        pem, unwrap = seals_and_opens()
        only_when_changed(pem, unwrap)
        what_is_committed()
    finally:
        shutil.rmtree(ROOT, ignore_errors=True)
    print("\n%d failed" % len(bad) if bad else "\nall passed")
    sys.exit(1 if bad else 0)
