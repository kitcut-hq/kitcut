# The studio on an Azure VM

The public studio (kitcut.ai's film maker, `studio/server.py`) runs on an always-on Ubuntu VM in
Azure instead of the laptop. Nobody logs into it by hand: every action is `az` + `ssh` from the
laptop, through the scripts in this folder.

| | |
|---|---|
| VM | `kitcut-studio-1`, Standard_D8ads_v5 (8 vCPU AMD EPYC, 32 GB), Ubuntu 24.04 |
| where | resource group `kitcut-PROD`, southcentralus -- beside the films' blob account `kitcutst` |
| disks | 128 GB OS + 512 GB data at `/srv/kitcut`, both Standard HDD (disk speed is not the bottleneck) |
| code | `/srv/kitcut/repo`, pushed from the laptop (`push.sh`); the VM holds no GitHub credentials |
| films | `/srv/kitcut/studio` (`STUDIO_HOME`) |
| reach | SSH from the laptop's IP only; the studio leaves through the Cloudflare named tunnel (outbound), `studio.kitcut.ai` |
| cost | ~$361/month for the VM + ~$22 the data disk (list prices, 2026-09-28) |

```bash
bash studio/deploy/vm.sh ssh kitcut-studio-1 'bash /srv/kitcut/repo/studio/serve.sh status'
bash studio/deploy/vm.sh ssh kitcut-studio-1 'journalctl -u kitcut-studio -n 100 --no-pager'
bash studio/deploy/vm.sh open-ssh kitcut-studio-1     # the laptop's IP changed: re-point the SSH rule
```

## Shipping a release

The same model as the laptop (studio/README.md, Releases): the server runs a frozen `git archive`
of a tag, never the working tree.

```bash
git tag -f studio-stable <commit>                                   # on the laptop: the decision to ship
bash studio/deploy/push.sh kitcut-studio-1 studio-poc                # the branch + the tag, over SSH
bash studio/deploy/vm.sh ssh kitcut-studio-1 'bash /srv/kitcut/repo/studio/serve.sh release'
```

Code reaches the VM only from the laptop: `push.sh` pushes into a bare repo on the VM
(`/srv/kitcut/git`) and moves the checkout to it. kitcut-hq/kitcut has deploy keys disabled, and
a VM with no GitHub credentials cannot leak any.

`serve.sh release` snapshots the tag, runs the release's tests inside it, drains the running
server (no new films; the ones being made finish, up to 20 min) and restarts it. systemd brings
the server and the tunnel back after a crash or a reboot (`Restart=always`); the laptop never had
that.

## What is different from the laptop, and why

**The render encodes in software, in the page.** There is no GPU. The browser refuses its
hardware H.264 (`prefer-hardware`), and the render would fall back to the ffmpeg pipe. Measured
2026-09-28, 48 s of the 8-minute Dell/HP film (2,880 frames, 1080p60), quality as VMAF against a
lossless render of the same frames:

| path | D8ads_v5 (8 vCPU) | F16s_v2 (16 vCPU) | quality | peak RAM |
|---|---|---|---|---|
| browser, software H.264 (OpenH264), 12 Mbps | **35.0 fps** (6 browsers) | 45.5 fps (12) | 99.99 | 4.0 GB |
| ffmpeg pipe, libx264 medium crf 18 | 18.8 fps (6) | 21.0 fps (9) | 95.5 | 6.5-12.5 GB |
| ffmpeg pipe, libx264 veryfast | 24.9 fps (6) | 24.9 fps (9) | 94.6 | 5.4 GB |
| the laptop: browser, NVENC (today's studio) | 54 fps | | | |
| the laptop: pipe, NVENC | 13 fps | | | |

The browser's software encoder refuses `bitrateMode: "quantizer"` (Edge 154 on Ubuntu 24.04
offers only variable and constant for H.264), so it gets a bitrate. The bitrate was picked on the
hardest film there is, a painted one (60 s, 60 fps; the line-art film scores 99.99+ at any rate):

| bitrate | painted film VMAF | size, 48 s |
|---|---|---|
| 5 Mbps | 91.6 | 30 MB |
| 8 Mbps | 97.4 | 47 MB |
| **12 Mbps** | **99.1** | 70 MB |

12 Mbps is also YouTube's own upload recommendation for 1080p60, which is where a published master
goes. The master is ~0.7 GB for 8 minutes instead of 2.2-3.8 GB.

**The web copy costs time here.** It is a libx264 encode on the CPU (NVENC on the laptop). At the
same 5 Mbps cap, `veryfast` took 16 s per 48 s of film against `medium`'s 39 s, VMAF 99.99 both,
so the VM sets `STUDIO_WEB_PRESET=p2`: ~2.7 min for an 8-minute film.

**Everything else is faster than on the laptop.**

| step (the 8-minute film) | laptop | D8ads_v5 | F16s_v2 |
|---|---|---|---|
| Whisper word timing, 8 min of narration (small.en, CPU int8) | 2.5-4 min | **46 s** | 51 s |
| Whisper large-v3, 1 min (non-English films) | | 36 s | 41 s |
| soundtrack `sketch-audio` (all stages / master) | - / 66 s | **52 s / 35 s** | 75 s / 47 s |
| motion-check stills, one browser | ~0.4 s a still | **0.22 s** | 0.29 s |

The 8 vCPU AMD machine beats the 16 vCPU Intel one on every step but the widest render, at 60 %
of its price, so it is the one in production. `vm.sh resize` moves it to a bigger size in minutes
if the queue says so.

All of the above sit in `machine.env`, each with its number: `STUDIO_RENDER_ENCODE=browser`,
`VIDEDIT_WEBCODECS=software`, `VIDEDIT_WEBCODECS_BITRATE=12M`, `STUDIO_RENDER_JOBS=6`,
`STUDIO_BROWSERS=6`, `STUDIO_WEB_PRESET=p2`, `STUDIO_MACHINE_SLOWDOWN=2`.

**Process containment is a cgroup.** On Windows each step is a Job Object. Here the unit is
`Delegate=yes`, and `procs.Job` gives every step a cgroup v2 of its own: `memory.max` is the
`STUDIO_FILM_MEM_GB` cap, `cgroup.kill` takes everything the step started (a browser that left
its process group included), and stopping the service takes every step with it.
`studio/test_isolation.py` checks all three on the VM.

**Only the production studio may announce itself.** `agent.py --announce` (which writes where
kitcut.ai finds the studio) does nothing unless the `.env` has `STUDIO_ANNOUNCE=1`, and only the
VM's does. Before the move the laptop's does.

## Building it again

```bash
bash studio/deploy/provision.sh kitcut-studio-1 Standard_D8ads_v5 --dry-run   # what it would do
bash studio/deploy/provision.sh kitcut-studio-1 Standard_D8ads_v5              # idempotent
```

The VM, the data disk, the timezone (America/Los_Angeles: the studio's daily caps count local
days, as on the laptop), the checkout, `scripts/setup-linux.sh --studio`, a `.env` holding only
the keys the studio reads plus `machine.env`, the tunnel's credentials, and the systemd units --
installed, not enabled. The units are enabled at the move, never before: the tunnel may run on
one machine only, and a studio that came up at boot would announce itself.

## The move (cutover), and back

1. Copy the laptop's studio home (films, library, uploads, Claude sessions): `azcopy` through a
   temporary container in `kitcutst`, or `tar | ssh`.
2. Test privately: `ssh -L 8765:127.0.0.1:8765`, run the server by hand (`serve.sh` is not
   needed), make one short film end to end, open an old one.
3. In an idle window, on the laptop: `serve.ps1 -Stop` (drains, stops the tunnel connector,
   marks the studio offline). **Never run the tunnel on both machines**: cloudflared
   load-balances between every connector of a tunnel, which would send half the films to the
   other disk.
4. Copy the films made since step 1 (`rsync`/`azcopy sync`).
5. On the VM: add `STUDIO_ANNOUNCE=1` to `/srv/kitcut/repo/.env`, then `bash studio/serve.sh start`.
6. On the laptop: remove `STUDIO_ANNOUNCE`, `STUDIO_TUNNEL` and `STUDIO_TUNNEL_HOST` from `.env`.

Back: `serve.sh stop` on the VM, restore those three lines on the laptop, `serve.ps1`, and copy
back what the VM made.

## Known differences

- A Claude session transcript from the laptop records Windows paths, so resuming a timed-out
  laptop film's Claude session (`resume_film.py`) works only for films made on the VM.
- Films asked for on the VM itself run on the Claude subscription (`auth=login`), as on the
  laptop; films from kitcut.ai always use the API key. Claude Code is installed natively
  (`curl -fsSL https://claude.ai/install.sh | bash`, `~/.local/bin/claude`) and signed in by
  `CLAUDE_CODE_OAUTH_TOKEN` in the VM's `.env` -- a 1-year token from `claude setup-token`
  (made 2026-09-28 for info@instafill.ai; renew before 2027-09-28). `provision.sh` keeps it.
  To renew: run `claude setup-token` on the VM in tmux, open its URL wherever you are signed in
  to claude.ai, press Authorize (a person must; the button refuses automation) and paste the
  code back within a few minutes -- the waiting CLI times out.
- If that login stops working, nothing is lost: a login film that cannot sign in is made on the
  API key instead, billed, with `fallback: {"from": "login", "why": ...}` on its record
  (studio/README.md, Paying for Claude). Every morning at 07:00 Pacific
  `kitcut-login-check.timer` runs `agent.py --check-login`; the result is in
  `kitcut.studio_hosts` (`login.ok`, `login.why`, `login.checked_at`) and the journal
  (`journalctl -u kitcut-login-check`), and a failed check shows in `systemctl --failed`.
  `install.sh` installs the timer; the move enables it:
  `sudo systemctl enable --now kitcut-login-check.timer`. No email yet: the site sends the owner
  mail (sketch-studio `lib/notify.js`) but has no endpoint the studio can call.
