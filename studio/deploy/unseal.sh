#!/usr/bin/env bash
# Open a sealed file of the studio machine's keys (studio/sealenv.py), from the laptop, through
# the key vault: the vault unwraps the file's key (this Azure sign-in must be allowed to use the
# key the file names -- kitcut-kv-prod, studio-env-kek), and the key goes straight into the
# opener's stdin. What is opened comes out on stdout to be piped on; nothing is written here
# but the request to the vault, in a private folder that is removed.
#
#   bash studio/deploy/unseal.sh <sealed.json>                  its .env, on stdout
#   bash studio/deploy/unseal.sh <sealed.json> --file <name>    another of its files
#   bash studio/deploy/unseal.sh <sealed.json> --tar            all of them, as a tar
#
# Used by `ops.sh secrets check` and by provision.sh for a machine that has no .env.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_LOCAL="$(cd "$HERE/../.." && pwd)"
sealed="${1:?a sealed file}"; shift
[ -s "$sealed" ] || { echo "unseal.sh: no such sealed file: $sealed" >&2; exit 1; }
# a python with `cryptography` here: the main checkout's venv (a worktree has none)
pyl="$(git -C "$REPO_LOCAL" worktree list 2>/dev/null | head -1 | cut -d' ' -f1)/.venv/Scripts/python.exe"
[ -x "$pyl" ] || pyl="$REPO_LOCAL/.venv/bin/python"
[ -x "$pyl" ] || pyl=python
tmp="$(mktemp -d)"; chmod 700 "$tmp"; trap 'rm -rf "$tmp"' EXIT
url="$(python - "$HERE/studio-env-kek.json" "$sealed" "$tmp/body.json" <<'PY'
import json, sys
want, sealed = json.load(open(sys.argv[1], encoding="utf-8")), json.load(open(sys.argv[2], encoding="utf-8"))
k = sealed.get("key") or want
w = sealed["wrapped"].replace("+", "-").replace("/", "_").rstrip("=")
json.dump({"alg": "RSA-OAEP-256", "value": w}, open(sys.argv[3], "w", encoding="utf-8"))
print("https://%s.vault.azure.net/keys/%s/%s/unwrapkey?api-version=7.4" % (k["vault"], k["name"], k["version"]))
PY
)"
# az is a Windows program on the laptop: it needs the file's Windows path, and is told the type
body="$tmp/body.json"; command -v cygpath >/dev/null 2>&1 && body="$(cygpath -w "$body")"
MSYS_NO_PATHCONV=1 az rest --method post --url "$url" --resource "https://vault.azure.net" \
  --headers "Content-Type=application/json" --body "@$body" --query value -o tsv |
  PYTHONPATH= "$pyl" -X utf8 "$REPO_LOCAL/studio/sealenv.py" --open "$sealed" "$@"
