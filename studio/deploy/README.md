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
bash studio/deploy/ops.sh status          # health, the servers and their films, disks, errors
bash studio/deploy/ops.sh logs studio -f  # every server unit; or tunnel | login
bash studio/deploy/ops.sh ship            # origin/studio-poc -> tagged, built, its server leading
bash studio/deploy/ops.sh film "<idea>"   # a film made on the VM itself, followed to the end
                                          # (--no-watch: print its id; `watch <id>...` follows several)
bash studio/deploy/ops.sh forward         # the VM's studio on this laptop's 127.0.0.1:8765
bash studio/deploy/ops.sh snapshot        # the data disk, incremental; keeps the newest 7
```

`ops.sh` is the everyday entry point (its header lists every command; the `studio-vm` skill
teaches it), `vm.sh` the machine itself, `provision.sh` a rebuild. The VM has no public IP: the
laptop's WireGuard VPN must be up.

## Shipping a release

The same model as the laptop (studio/README.md, Releases): a server runs a frozen `git archive`
of a commit, never the working tree. What differs is that a ship on the VM never restarts
anything: **one server per release**. The new release's server starts beside the running one and
takes the new films; the old one finishes the films it is making, then exits by itself.

```bash
bash studio/deploy/ops.sh --dry-run ship      # what it would do
bash studio/deploy/ops.sh ship [<commit>]     # default origin/studio-poc's head
bash studio/deploy/ops.sh rollback <sha12>    # any release still built (ops.sh releases)
```

What a ship does:

1. **On the laptop** (`ops.sh`): refuses a commit that is not on origin/studio-poc, tags it
   `studio-stable`, and `push.sh` pushes that commit into a bare repo on the VM
   (`/srv/kitcut/git`) and moves the checkout to it. Code reaches the VM only from the laptop:
   kitcut-hq/kitcut has deploy keys disabled, and a VM with no GitHub credentials cannot leak any.
2. **`serve.sh release`** on the VM: `release.py` snapshots the tag into
   `STUDIO_HOME/releases/<sha12>` and runs the release's tests inside it, then `serve.sh switch`.
   A sha that already leads is left alone.
3. **`serve.sh switch <sha12>`** names a new instance, `<sha12>-<YYYYmmddHHMMSS>`, writes it to
   `STUDIO_HOME/servers/current` and starts `kitcut-studio@<instance>`. It binds 127.0.0.1:8765
   beside the running server (both set `SO_REUSEPORT`), so the tunnel never moves. The old leader
   sees the current instance serving and hands off: it lets go of `leader.lock`, stops listening,
   takes no new films, finishes its own and exits 0 -- in a minute or in two hours; nobody waits.
   `switch` returns as soon as the new server's heartbeat says *serving*, *leader* and the right
   release, and prints the older servers still finishing films. If it does not lead within 120 s,
   `current` goes back, the new unit is stopped, its journal is printed and the ship fails (and
   if the old one had already handed off, a fresh server of the old release is started).
4. **The check**: `/api/health`'s `release` is the leader's, whichever server answers; `ops.sh`
   reads it on the VM and through studio.kitcut.ai, and lists the servers.

| word | what it is |
|---|---|
| instance | one server unit, `kitcut-studio@<sha12>-<timestamp>` (`kitcut-studio@.service`). A fresh server of the same code is a new instance |
| `servers/current` | the intent: the instance that should serve. `serve.sh` writes it; a server of another instance that starts exits 0 at once |
| leader | the fact: the one server holding `servers/leader.lock`. It admits films and adopts what a dead server left; `/api/health`'s `release` is its |
| handed off | an old server finishing its films: not listening, taking nothing new. It exits 0 when done, and `Restart=on-failure` leaves it down (a crash brings it back) |
| heartbeat | `servers/<instance>.<pid>.json` (mode, leader, release, films), beside the `.lock` the server holds for its whole life (`studio/peers.py`) |

- **Rollback** is a switch to an older built release: `ops.sh rollback <sha12>` (`serve.sh use`).
  Nothing is stopped either way.
- **Restart** (`serve.sh restart`) is a switch to the leader's own release: a fresh server of the
  same code, e.g. after an `.env` change. The old server keeps the settings it started with until
  its films are done.
- **The shared venv.** Every release runs on `/srv/kitcut/repo/.venv` (and shares `models/`), so
  installing a changed requirement changes the steps of the films the old server is still making.
  `ops.sh ship` warns when `requirements*.txt` changed between the leader's release and the one
  shipped: install and ship at a quiet moment (`ops.sh status` shows no films).
- **Only maintenance stops a film.** `serve.sh stop` drains (no new films; up to 20 min for the
  running ones), then stops every server and the tunnel. `serve.sh start` brings back the tunnel
  and the current instance, and enables both at boot. Never `systemctl restart` or `stop` a
  `kitcut-studio@...` unit by hand: its films stop with it.
- **A reboot** starts `servers/current`'s instance (`kitcut-studio-boot.service`, the one studio
  unit that is enabled). Older servers were ended by the reboot; the leader adopts their films as
  it would a crashed server's.
- **Offline is said once.** Each instance runs `announce.sh up` when it starts; `announce.sh off`
  does nothing while any other studio server unit is up, so an old server leaving never marks the
  public studio offline.
- **The kernel setting.** `install.sh` puts `net.ipv4.tcp_migrate_req = 1` in
  `/etc/sysctl.d/60-kitcut.conf`: when the old server closes its listener, the connections already
  queued on it move to the new one instead of being reset.
- **The guards from before stay.** Releases are built where the servers read them (`serve.sh`
  takes `STUDIO_HOME` from the units, or refuses). One deploy at a time: every command but
  `status` takes `STUDIO_HOME/deploy.lock` (`flock`); a second one stops at once and prints who
  holds it. A stopped server says what it did (`server.shutdown()`: a film Claude was writing is
  *interrupted*, one being mixed or rendered stays *finishing* for the leader, a queued one stays
  queued), under `KillMode=mixed` and `TimeoutStopSec=60`. A change to a unit file needs
  `bash studio/deploy/install.sh` on the VM; a running server keeps its unit as it started, and
  the next ship's server gets the new one.

**Why (KI-031).** Until the migration below the VM ran one server, `kitcut-studio.service`, and a
ship drained it for up to 20 minutes and then restarted it. On 2026-09-28 three overlapping ships did
that; the first one's drain ran out while a paying 150 s film (`rts664`) was 28 minutes in, the
restart killed it -- recorded *cancelled* -- and, the release having been built outside
`STUDIO_HOME`, the studio came back on its old code. The lock, the `STUDIO_HOME` check and the
*interrupted* record came that night; one server per release is the end of it: a ship no longer
waits on a film or stops one.

### The migration, once per machine

The legacy unit does not set `SO_REUSEPORT` and restarts on every ship, so the first move to one
server per release is a step of its own. `ops.sh ship` refuses while the legacy unit is installed.

```bash
bash studio/deploy/ops.sh --dry-run migrate   # the plan (the VM's own dry run, once it has the scripts)
bash studio/deploy/ops.sh migrate [<commit>]  # at a quiet moment
```

`ops.sh migrate` pushes the commit like a ship, runs `install.sh` on the VM (the template, the
boot unit, the sysctl; the legacy unit is left as it is), then runs `serve.sh migrate` there in a
unit of its own (`kitcut-migrate-<time>`) and follows it: it waits for films with no timeout, and
must not depend on the laptop staying awake. Ctrl+C stops the following, not the migration
(`vm.sh ssh kitcut-studio-1 "journalctl -u 'kitcut-migrate-*' -f"` picks it up again).
`serve.sh migrate`:

1. builds and tests the release, then puts `releases/current` back to the legacy server's, so a
   legacy server restarted by a crash meanwhile comes back on its own code;
2. starts `kitcut-studio@<instance>` with `servers/current` naming it. The legacy server holds
   the port without `SO_REUSEPORT`, so the new one retries the bind every 0.2 s, and it cannot
   lead or adopt a film until it has the port: the legacy server keeps every film meanwhile;
3. waits, **with no timeout**, until the legacy server has nothing running or queued (progress
   every minute). A studio that keeps receiving films keeps it waiting: it never cuts one;
4. drains the legacy server (`/api/admin/drain`), so a film asked for in the gap stays queued for
   the new server, and waits until nothing runs;
5. empties the legacy unit's `ExecStopPost` (a drop-in: stopping it must not announce the studio
   offline) and `systemctl disable --now kitcut-studio` -- the new server gets the port within
   0.2 s of the old one letting go;
6. waits up to 60 s for the new server to serve and lead; if it does not, stops it, puts the
   legacy server back and exits 1;
7. enables `kitcut-studio-boot`, and `releases/current` names the new release;
8. removes the legacy unit file and the drop-in;
9. announces the studio once more, and prints where it stands: health, servers, units, the
   legacy unit (`not-found`), `net.ipv4.tcp_migrate_req`.

Run it again after any failure: each step checks what is already done (a server of the release
already running is kept, a legacy server already stopped is not waited on).

## A film Claude stops answering on

The studio watches every film's Claude part (agent.py `Pulse`, `talk_to_claude`): 20 minutes with
no message from Claude Code, no event and no tool at work, and it cuts the reply off and picks the
same session up again, telling Claude to work in shorter replies -- at most twice, then the film
fails (and kitcut.ai refunds it) instead of waiting hours. The journal says `STALL` with the film's
id (`ops.sh logs studio | grep STALL`), the film's page says what happened, the record counts
`stalls`, and `ops.sh claude-log <film>` shows the replies and their waits. The case it was built
for: an 8-minute film whose picture, written in one reply, took longer than Claude Code waits,
retried from scratch every 5 minutes for an hour (docs/known-issues.md KI-034). A film over 90 s
is now told to write its picture in parts; the redesign for much longer films is docs/todo.md #7.

## Nothing moves the VM backwards

The VM's repo (`/srv/kitcut/git`) refuses any push that would move a branch or a tag back
(`receive.denyNonFastForwards`), `--force` or not. A clone that had not pulled once pushed an older
studio-poc from its own old scripts and drained the live studio; a check in the scripts could not
stop that, since the stale clone runs its own copies. To go back to an earlier release, use
`ops.sh rollback <sha12>`; a ship refused this way means: pull origin, then ship.

## A film the studio stopped half-way

A restart while Claude is working stops the film (up to 2026-09-29 it was even recorded as
*cancelled*, exactly as if its person had pressed Stop). Its work is not lost: `film.js`, the
narration and Claude's own session (`STUDIO_HOME/claude/<film>/`, the transcript Claude Code
resumes) stay on the data disk. `studio/resume.py` picks it up in the same film -- the same page
and link -- with one more turn of that session, then the mix and the render as usual:

```bash
bash studio/deploy/ops.sh claude-log <film-id>      # what Claude did, how long each reply took, the
                                                    # API errors, Claude Code's debug log: read first
bash studio/deploy/ops.sh resume <film-id> --plan   # session found? what is missing? spends nothing
bash studio/deploy/ops.sh resume <film-id>          # its own unit (kitcut-resume-...), followed
bash studio/deploy/ops.sh resume <film-id> --finish # Claude's part is whole: mix and render only
```

Claude gets what the film's limit has left of its working time (`--minutes N` to set it) and of its
budget. What the stopped attempt spent is carried into the record, not replaced, and both
attempts' calls stay in `kitcut.studio_runs`. On kitcut.ai a stopped film's credits were already
given back (cancelled, interrupted and failed are all refunded, and only a spend still *held* is
ever charged), so a film finished this way is free to its person: check `credit_spends` for the
film before running if it matters.

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

**Process containment is a cgroup.** On Windows each step is a Job Object. Here each server's
unit (`kitcut-studio@<instance>`) is `Delegate=yes`, and `procs.Job` gives every step a cgroup v2
of its own: `memory.max` is the `STUDIO_FILM_MEM_GB` cap, `cgroup.kill` takes everything the step
started (a browser that left its process group included), and stopping a server's unit takes
every step with it. One unit per server, never two in one: a server clears the step groups it
finds in its own unit's cgroup when it starts. `studio/test_isolation.py` checks all three on the
VM.

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
the server template, the boot unit, the tunnel, the login check (and `tcp_migrate_req`) --
installed, not enabled. The units are enabled at the move, never before: the tunnel may run on
one machine only, and a studio that came up at boot would announce itself. On a rebuild the data
disk still holds `servers/current`, so `serve.sh start` brings back the instance that served.

## The move (cutover), and back

Done 2026-09-28 at 13:37 PDT, with about 7 minutes offline (13:30-13:37). All 68 laptop
films came across, and the laptop's tunnel settings were taken out of its `.env`. Its
credentials were moved to `~/.cloudflared/backup-20260928-moved-to-vm`, so a laptop
`serve.ps1` can no longer start a second connector. The steps, kept for a rebuild or a move back:

1. Copy the laptop's studio home (films, library, uploads, Claude sessions): `azcopy` through a
   temporary container in `kitcutst`, or `tar | ssh`.
2. Test privately: `ssh -L 8765:127.0.0.1:8765`, run the server by hand (`serve.sh` is not
   needed), make one short film end to end, open an old one.
3. In an idle window, on the laptop: `serve.ps1 -Stop` (drains, stops the tunnel connector,
   marks the studio offline). **Never run the tunnel on both machines**: cloudflared
   load-balances between every connector of a tunnel, which would send half the films to the
   other disk.
4. Copy the films made since step 1 (`rsync`/`azcopy sync`).
5. On the VM: add `STUDIO_ANNOUNCE=1` to `/srv/kitcut/repo/.env`, then `bash studio/serve.sh start`
   (the tunnel and the current server, and both at every boot). A home with no server yet needs
   `bash studio/serve.sh release` first. (The 2026-09-28 move ran the legacy one-server unit;
   `serve.sh migrate` moved it to one server per release afterwards.)
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
