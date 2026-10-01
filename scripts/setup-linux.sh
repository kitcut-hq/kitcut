#!/usr/bin/env bash
# Build (or repair) this repo's toolchain on Ubuntu 24.04 -- the Linux half of
# scripts/setup-python.ps1. Idempotent: safe to re-run any time.
#
#   bash scripts/setup-linux.sh            # ffmpeg, Edge, node, uv, Python 3.13, .venv
#   bash scripts/setup-linux.sh --studio   # + requirements-studio.txt, cloudflared, Whisper models
#   bash scripts/setup-linux.sh --dry-run  # say what would be installed, install nothing
#
# Needs sudo for apt. Runs as the user who will own the checkout, never as root:
# Chromium refuses to start its sandbox as root, and a root-owned .venv is a trap.
#
# Why each piece is here:
# - ffmpeg is BtbN's static GPL build, not Ubuntu's 6.1: the repo is written against
#   the 8.x filter set (the laptop runs gyan.dev 8.0.1) and needs libass + rubberband.
# - Microsoft Edge, not Chromium: the studio's renders were measured in Edge, and the
#   snap-packaged chromium-browser cannot see /srv or /tmp from its confinement.
# - The Whisper models are fetched here because the studio runs every step with
#   HF_HUB_OFFLINE=1 -- a model that is not already cached is a failed film, not a download.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
[ -f "$ROOT/requirements.txt" ] || { echo "no requirements.txt in $ROOT" >&2; exit 1; }
cd "$ROOT"

STUDIO=0
DRY=0
for a in "$@"; do
  case "$a" in
    --studio) STUDIO=1 ;;
    --dry-run) DRY=1 ;;
    -h|--help) sed -n 2,19p "$0"; exit 0 ;;
    *) echo "unknown argument: $a" >&2; exit 2 ;;
  esac
done

FFMPEG_TAG="n8.1"   # BtbN release line; bump deliberately, then run check-encode.py
FFMPEG_URL="https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-${FFMPEG_TAG}-latest-linux64-gpl-${FFMPEG_TAG#n}.tar.xz"
WHISPER_MODELS="small.en large-v3 large-v3-turbo"

step() { printf '\n== %s ==\n' "$*"; }
run() { if [ "$DRY" = 1 ]; then echo "  would run: $*"; else "$@"; fi; }

if [ "$(id -u)" = 0 ]; then
  echo "run this as the checkout's owner, not root (it uses sudo where it must)" >&2
  exit 1
fi

step "1. apt packages"
PKGS="git curl ca-certificates gnupg xz-utils nodejs fonts-noto-core fonts-noto-color-emoji fontconfig"
run sudo apt-get update -qq
run sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq $PKGS

step "2. Microsoft Edge"
if command -v microsoft-edge >/dev/null 2>&1; then
  echo "  present: $(microsoft-edge --version)"
else
  run bash -c 'curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | sudo gpg --dearmor --yes -o /usr/share/keyrings/microsoft-edge.gpg'
  run bash -c 'echo "deb [arch=amd64 signed-by=/usr/share/keyrings/microsoft-edge.gpg] https://packages.microsoft.com/repos/edge stable main" | sudo tee /etc/apt/sources.list.d/microsoft-edge.list >/dev/null'
  run sudo apt-get update -qq
  run sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq microsoft-edge-stable
fi

step "3. ffmpeg ($FFMPEG_TAG static)"
if [ -x /opt/ffmpeg/bin/ffmpeg ] && /opt/ffmpeg/bin/ffmpeg -version | head -1 | grep -q "${FFMPEG_TAG}"; then
  echo "  present: $(/opt/ffmpeg/bin/ffmpeg -version | head -1)"
else
  tmp="$(mktemp -d)"
  run curl -fsSL -o "$tmp/ffmpeg.tar.xz" "$FFMPEG_URL"
  run sudo rm -rf /opt/ffmpeg
  run sudo mkdir -p /opt/ffmpeg
  run sudo tar -xJf "$tmp/ffmpeg.tar.xz" -C /opt/ffmpeg --strip-components=1
  rm -rf "$tmp"
fi
for t in ffmpeg ffprobe; do run sudo ln -sf "/opt/ffmpeg/bin/$t" "/usr/local/bin/$t"; done

if [ "$STUDIO" = 1 ]; then
  step "4. cloudflared"
  if command -v cloudflared >/dev/null 2>&1; then
    echo "  present: $(cloudflared --version | head -1)"
  else
    run bash -c 'curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg | sudo tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null'
    run bash -c 'echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main" | sudo tee /etc/apt/sources.list.d/cloudflared.list >/dev/null'
    run sudo apt-get update -qq
    run sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq cloudflared
  fi
fi

step "5. uv + Python 3.13 + .venv"
export PATH="$HOME/.local/bin:$PATH"
if ! command -v uv >/dev/null 2>&1; then
  run bash -c 'curl -LsSf https://astral.sh/uv/install.sh | sh'
fi
# The same trap setup-python.ps1 clears first: a PYTHONPATH aimed at another Python's
# site-packages makes the venv load foreign compiled extensions, and pip skip deps.
unset PYTHONPATH
run uv python install 3.13
if [ ! -x .venv/bin/python ]; then
  run uv venv --python 3.13 .venv
fi
REQS="-r requirements.txt"
[ "$STUDIO" = 1 ] && REQS="$REQS -r requirements-studio.txt"
run uv pip install --python .venv/bin/python $REQS
run uv pip check --python .venv/bin/python

if [ "$STUDIO" = 1 ]; then
  # into $HF_HOME when it is set -- the studio VM keeps them on its data disk, which outlives a
  # rebuild of the machine (7 GB that would otherwise download again)
  step "6. Whisper models (the studio runs offline) -> ${HF_HOME:-~/.cache/huggingface}"
  for m in $WHISPER_MODELS; do
    run .venv/bin/python -c "from faster_whisper import download_model; print('  ', '$m', download_model('$m'))"
  done

  # the studio's steps import these inside functions: prove them now, not on a customer's film
  run .venv/bin/python -c "from google import genai; import claude_agent_sdk, pymongo, aiohttp; print('  studio imports ok')"

  step "6b. Claude Code (films on the machine's own login)"
  if [ -x "$HOME/.local/bin/claude" ]; then
    echo "  present: $("$HOME/.local/bin/claude" --version)"
  else
    run bash -c 'curl -fsSL https://claude.ai/install.sh | bash'
  fi
fi

step "7. verify"
run .venv/bin/python scripts/check-env.py
echo
echo "done. The GPU and CUDA warnings above are expected on a CPU-only machine."
