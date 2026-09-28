---
name: studio-vm
description: Operate the production Sketch Studio (kitcut.ai's film maker) on its Azure VM, kitcut-studio-1 -- check its health, read its logs, ship a release, roll back, make or follow a film, pull a film's files, hide a film from the gallery, forward the studio to this laptop, snapshot its disk, or rebuild the machine. Use when asked about the studio's status or errors, "is kitcut.ai working", to deploy/ship/release studio code, to look at the VM or its logs, to make a test film on the studio, to back up or rebuild the studio machine, or when a session used to reach the studio on 127.0.0.1:8765 on the laptop (it now lives on the VM).
---

# The studio VM

kitcut.ai's studio runs on **kitcut-studio-1** (Azure, `kitcut-PROD`, D8ads_v5, Ubuntu) since
2026-09-28 -- not on the laptop. It has no public IP: the laptop reaches it over the WireGuard VPN
(10.0.13.4). Nobody logs in by hand; everything below runs from the laptop's checkout.
`studio/deploy/README.md` is the runbook and holds the measurements.

```bash
bash studio/deploy/ops.sh status                    # start here: health, release, films in progress,
                                                    # disks, login check, errors in the last day
bash studio/deploy/ops.sh logs [studio|tunnel|login] [-n 200] [-f]
bash studio/deploy/ops.sh --dry-run ship [<commit>] # what a ship would do
bash studio/deploy/ops.sh ship [<commit>]           # default: origin/studio-poc's head
bash studio/deploy/ops.sh releases                  # built releases, current marked *
bash studio/deploy/ops.sh rollback <sha12>          # back to one already built, no rebuild
bash studio/deploy/ops.sh film "<idea>" [--seconds 30] [--api]   # on the Claude login unless --api
bash studio/deploy/ops.sh watch <film-id>
bash studio/deploy/ops.sh pull <film-id> [dest] [--all]
bash studio/deploy/ops.sh hide|show <film-id>       # public gallery
bash studio/deploy/ops.sh forward [8765]            # the VM's studio on this laptop's 127.0.0.1:8765
bash studio/deploy/ops.sh snapshot [--keep 7]       # data disk: films, checkout, .env, models
bash studio/deploy/vm.sh ssh kitcut-studio-1 '<command>'   # anything else
```

## Rules

- **Never start the tunnel on the laptop.** cloudflared load-balances every connector of a tunnel,
  so a second one sends half the films to the other disk. The laptop's tunnel settings are gone
  from its `.env` on purpose; `serve.ps1 -Dev` is for local development only.
- **Ship only what is on origin/studio-poc.** `ops.sh ship` refuses anything else. It tags
  `studio-stable`, pushes the code to the VM (`push.sh`: the VM holds no GitHub credentials),
  builds and tests the release there, drains the running films (up to 20 min) and restarts, then
  proves the studio reports the new release.
- **Read the film's own events, not only the journal.** A step's failure lands in
  `projects/<film>/events.jsonl` as `{"type": "fail"}` and Claude works around it -- the first
  films on the VM went out *silent* because `google-genai` was missing and the narration step
  failed every time, while the journal showed nothing. After any environment change, make one
  film (`ops.sh film`) and check it has a voice (`audio/vo/*.wav`, and listen), not just a picture.
- **Where things live on the VM:** code `/srv/kitcut/repo` (the checkout releases are cut from),
  films `/srv/kitcut/studio` (`STUDIO_HOME`), models `/srv/kitcut/hf`, all on the data disk, which
  a rebuild keeps. Units: `kitcut-studio`, `kitcut-tunnel`, `kitcut-login-check.timer`.
- **Films made on the VM itself** (`ops.sh film`, `forward`) run on the Claude login
  (`CLAUDE_CODE_OAUTH_TOKEN`, info@instafill.ai, renew by 2027-09-28 -- a person must press
  Authorize); a sign-in failure falls back to the API key. kitcut.ai's films always use the key.

## When something is wrong

1. `ops.sh status` -- is the studio answering, is studio.kitcut.ai the same release, any errors?
2. `ops.sh logs studio -n 300` and the film's `events.jsonl` (`vm.sh ssh ... 'tail
   /srv/kitcut/studio/projects/<id>/events.jsonl'`).
3. A step that fails on the VM and not on the laptop is usually the environment: compare
   `uv pip list` there with the laptop's venv, and look for imports inside functions.
4. Fix in the repo (worktree, commit, merge to studio-poc), then `ops.sh ship`. A missing package
   can be installed into `/srv/kitcut/repo/.venv` at once (`~/.local/bin/uv pip install --python
   .venv/bin/python ...`) -- the release shares that venv -- but add it to the requirements too.
5. The machine itself: `vm.sh` (resize, stop/start); rebuild with `provision.sh` (idempotent,
   reattaches the data disk).
