# The studio on an Azure VM

The public studio (kitcut.ai's film maker, `studio/server.py`) runs on an always-on Ubuntu VM in
Azure instead of the laptop. Nobody logs into it by hand: every action is `az` + `ssh` from the
laptop, through the scripts in this folder.

| | |
|---|---|
| VM | `kitcut-studio-1`, Standard_D4ads_v5 (4 vCPU AMD EPYC, 16 GB) since 2026-09-28 16:05 (D8ads_v5 before), Ubuntu 24.04 |
| where | resource group `kitcut-PROD`, southcentralus -- beside the films' blob account `kitcutst` |
| disks | 32 GB OS + 512 GB data at `/srv/kitcut`, both Standard HDD (disk speed is not the bottleneck). The OS disk goes with the machine; the data disk is kept, and carries a delete-lock |
| copies | Azure Backup nightly (the whole machine, 30 days), the home mirrored to R2 every 15 minutes, the database exported nightly: "Where the copies are". The machine gone: "If the machine is gone" |
| code | `/srv/kitcut/repo`, pushed from the laptop (`push.sh`); the VM holds no GitHub credentials |
| films | `/srv/kitcut/studio` (`STUDIO_HOME`) |
| copies online | Cloudflare R2 bucket `kitcut-media`, public at `https://media.kitcut.ai/films/<id>/<file>`, since 2026-10-07 (downloads are free there; Azure billed them per GB). The `.env` holds `STUDIO_MEDIA_BASE` and the three `STUDIO_R2_` settings; `.env.bak-before-r2` is the file from before. Azure's `kitcutst/films` still holds the films copied before the move (`STUDIO_MEDIA_OLD_BASE`: a deleted film goes from there too); take that setting out when the container is removed |
| reach | SSH from the VPN only (no public IP), plus one locked address for Claude cloud sessions, `ssh.kitcut.ai` ("SSH for Claude cloud sessions"); the studio leaves through the Cloudflare named tunnel (outbound), `studio.kitcut.ai`; `vm.sh network` also denies outbound to the VNet (`no-network-outbound`: films fetch from the web) |
| cost | ~$180/month for the VM on D4ads_v5 ($361 on D8) + ~$22 the data disk (list prices, 2026-09-28) |

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

### A push to GitHub ships itself (autoship)

```bash
bash studio/deploy/ops.sh autoship on        # install and start the hook's path unit and the poll (lifts a pause)
bash studio/deploy/ops.sh autoship           # its last decision, and the last ship's log
bash studio/deploy/ops.sh autoship --plan    # what a look would do now; changes nothing
bash studio/deploy/ops.sh autoship now [--retry]   # one look now, followed (--retry: a failed head)
bash studio/deploy/ops.sh autoship off       # stop it; ops.sh ship still works as before
bash studio/deploy/ops.sh autoship hook      # the hook's secret (machine .env) and GitHub's webhook
bash studio/deploy/ops.sh autoship hook --check   # the webhook's last deliveries, and the lock probed
node --env-file=<CLOUDFLARE_API_TOKEN file> studio/deploy/hook-lock.mjs [--check]   # the Cloudflare lock
```

When GitHub's `studio-poc` moves past the release that leads, the machine ships it
(`studio/deploy/autoship.py`), and a push needs nobody at a laptop. **GitHub's push hook starts a
look at once**; a poll every 15 minutes (`kitcut-autoship.timer`) catches a push whose hook did
not arrive, since GitHub does not send one again by itself. **The machine still pulls the code**:
kitcut-hq/kitcut is public, so `git ls-remote https://github.com/...` needs no key, and the
machine holds no GitHub credentials. The hook carries no code and decides nothing -- it says
"look now".

**Only GitHub can call the hook**, `https://studio.kitcut.ai/hooks/github`, and it is locked
twice:

1. **At Cloudflare** (`hook-lock.mjs`): one firewall rule blocks any path of studio.kitcut.ai
   containing `/hooks`, in any case, from every address outside GitHub's published webhook ranges
   (`api.github.com/meta`, `hooks`). Nothing else reaches the machine; `ops.sh autoship hook
   --check` POSTs from the laptop and expects 403. GitHub says it changes the ranges rarely;
   `hook-lock.mjs --check` says STALE when it has, and until the rule is made again a hook is
   blocked and the poll ships the push.
2. **On the machine** (`server.py github_hook`): GitHub signs every delivery with
   `X-Hub-Signature-256`, an HMAC-SHA256 of the body under a secret only GitHub and the machine's
   `.env` hold (`AUTOSHIP_HOOK_SECRET`, made on the machine by `ops.sh autoship hook` and piped
   straight into GitHub's API, never printed or saved on a laptop). Checked in constant time over
   the whole body (at most 4 MB, read past the app's 64 KB cap); unsigned, wrongly signed or too
   large is refused (401/413) and logged with the caller's address. No secret, no hook (404). It
   sits outside `/api/`, so the studio token does not guard it: GitHub cannot send that token.

A signed request does one thing: for a `push` to `refs/heads/studio-poc` it writes
`STUDIO_HOME/autoship.poke`, and `kitcut-autoship.path` starts a look. A ping is answered; any
other branch, tag or event is acknowledged and ignored. `studio/test_hook.py` holds each of these
to the real handler. A replayed delivery can only ask for a look that finds nothing new.

A look ships exactly what step 1 above would put there, and the same way: GitHub's head, a
fast-forward of the bare repo's branch (`update-ref` with the old value), the `studio-stable` tag
there, the checkout moved as `push.sh` moves it, then `serve.sh release` -- built, tested, a
server of its own -- and `/api/health` asked which release leads. The decisions, each tested by
`studio/test_autoship.py` against local repositories and a stub studio. Each wait is looked at
again every 30 s by the same run (for at most 45 minutes, then the poll), and a hook that arrived
while a look was shipping gets one more look before it stops:

| it finds | it does |
|---|---|
| the head leads already, or `autoship.paused` exists | nothing |
| a head under 30 s old | waits: pushes in a row are one ship |
| the `cpu` pool busy (a voice being recorded, a film's sound) | waits, at most 40 min from the head's first look, then ships: a ship's tests take the cores those steps time words on (KI-043), and a ship slows a film but never stops one |
| `deploy.lock` held (a ship from the laptop), or the studio not answering | waits |
| only `docs/`, `projects/`, `market/`, `.github/` or the root's `*.md` changed | skips; the next real commit takes them. The studio's own prompts (`studio/*.md`) and the skills do ship |
| a `requirements*.txt` changed | **holds**: the venv is shared (above), so a person ships it at a quiet moment with `ops.sh ship` |
| GitHub's branch rewritten (not a fast-forward) | **refuses** |
| a release that fails its tests | **failed**, once per commit: the next commit is tried, or `now --retry` |

The three in bold are written into the machine's note at once (`machine_note.py`, field
`autoship`), and the site's watch emails the owner from it (sketch-studio `lib/studiowatch.js`), so
a push that did not go live is not found days later. `ops.sh status` prints the last decision on
its own line. Each ship's log is `STUDIO_HOME/autoship/<sha12>-<time>.log` (the last 30).

- **`ops.sh rollback` pauses it** (`STUDIO_HOME/autoship.paused`): otherwise the next look would
  ship GitHub's head straight back. `ops.sh autoship on` lifts the pause once the fix is pushed.
- **`ops.sh ship` from a laptop still works**, and both take the same `deploy.lock`. A hand ship
  is also how a requirements change goes out.
- **GitHub's `studio-stable` tag** moves only when a laptop ships; the machine's own tag is the
  truth. `provision.sh` reads GitHub's tag when building a machine again, so a new machine may
  start one release behind -- and its first look ships the head.
- **The script is Python on the system `python3`**, not bash in the venv: it moves the checkout
  it was started from, and bash goes on reading a script as it changes (ops.sh, 2026-10-12).

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
bash studio/deploy/ops.sh drafts [--days 7]         # YouTube drafts: seconds to the words, the
                                                    # thumbnail picks and pictures, cost (reads only)
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
of its price, so it went into production.

**Then it went down to 4 vCPU (D4ads_v5, $180 a month against $361).** On its first day the D8
averaged under 10 % CPU, peaked at 80-85 % only while rendering, and used 1 GB of its 32. Measured
after the resize, 2026-09-28, a 30 s line-art film at 60 fps:

| | D8ads_v5 | D4ads_v5 |
|---|---|---|
| render | 32.7 frames/s (a 30 fps film, 6 browsers) | **17.7 frames/s** (4 browsers): 1.85x slower |
| web copy, 30 s of film | 10-11 s | 24 s |
| peak memory, whole machine | | 2.9 GB of 16 |

Claude's writing is most of a film's time (17 of this film's 19 minutes), so a film is about 10 %
slower end to end; the render of an 8-minute Pro film goes from ~14 to ~27 minutes. The settings
for 4 vCPU are in `machine.env`. `vm.sh resize kitcut-studio-1 Standard_D8ads_v5` goes back in
five minutes (drain first: `serve.sh stop`), with the D8 values beside them.

All of the above sit in `machine.env`, each with its number: `STUDIO_RENDER_ENCODE=browser`,
`VIDEDIT_WEBCODECS=software`, `VIDEDIT_WEBCODECS_BITRATE=12M`, `STUDIO_RENDER_JOBS=4`,
`STUDIO_BROWSERS=4`, `STUDIO_WEB_PRESET=p2`, `STUDIO_MACHINE_SLOWDOWN=3` (on D8: 6, 6 and 2).

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

## Who uses the machine

```bash
bash studio/deploy/ops.sh usage                    # the last 24 h: by hour, memory's low points,
                                                   # by film and by step
bash studio/deploy/ops.sh usage --hours 6 --top 20
bash studio/deploy/ops.sh usage --at "20:40"       # one moment in full: every group, the top processes
bash studio/deploy/ops.sh usage --film 3mx2e4      # one film's steps
bash studio/deploy/ops.sh usage install            # install and (re)start the sampler
```

Two records, because neither is enough alone (`studio/deploy/usage.py`):

- **The timeline**: `kitcut-usage.service` samples every 15 s into `STUDIO_HOME/usage/<day>.jsonl`
  (14 days kept, ~1.4 KB a sample, ~8 MB a day): CPU busy, memory available, the pressure-stall
  averages (`/proc/pressure`: how long work waited for a CPU or for memory), and every cgroup that
  matters with its cores, its memory and the part of it that is **held** (anonymous: the kernel
  cannot take it back the way it takes file cache) -- each film's step, each server's own leaf
  (the server and its films' Claude Code), each `ops.sh` job, the ssh sessions -- plus the twelve
  biggest processes by CPU and by memory, each tied to its film off its command line. It runs on
  the system python3 with the stdlib only (a release's venv cannot break it), niced, `MemoryMax=128M`.
- **The bill**: every step a server (or a `resume`) runs leaves a line in
  `STUDIO_HOME/usage/steps-<day>.jsonl` (`procs.record_step`): its film, what it was
  (`sketch-render --stills`), its time, its exact CPU seconds and memory peak read off its own
  cgroup just before it is removed, how often the cap killed something in it, its exit code. Exact
  even for a step shorter than a sample.

Each step's cgroup is named after its film and step (`step-<pid>-<n>-3mx2e4-sketch-render`), so a
sample needs no lookup; a step started by an older server (`step-<pid>-<n>`) is named off its first
process instead. sar (sysstat, every 10 minutes) stays for the machine as a whole, but a
10-minute average hid the 14.8 GB moment at 2026-09-30 20:40 that this was built to explain.

First reading, 2026-10-01 12:40: two films rendering at once (one a `resume`, which has pools of
its own -- KI-043) ran 4 browsers each on the 4 cores, CPU pressure 90 %: each waited for a CPU
almost all the time.

## The data disk, and what fills it

```bash
bash studio/deploy/ops.sh prune --plan             # what would go, by kind; removes nothing
bash studio/deploy/ops.sh prune                    # the plan, then the removal (capped, idle I/O)
bash studio/deploy/ops.sh prune --older-than 0 --film <id>   # one film's, however new
bash studio/deploy/ops.sh prune install            # install and start the hourly timer
```

A film is read a frame or two a second before it is called done, and its thumbnails are cut from
stills of it. Those frames are full-size PNGs of about 3 MB and nothing removed them: on
2026-10-12 they were 222 GB of the 399 on the disk, in 61,659 files, and had grown 48 GB a day
since the review went live on 2026-10-07 -- two days from a full disk, and a full disk stops every
film (KI-063). `studio/prune.py` removes them from films that are over, every hour
(`kitcut-prune.timer`), once nothing has written to them for six hours:

| in the film's `temp/` | what it is | when it is needed again |
|---|---|---|
| `motion/` | the film a few times a second, and the probe's report | `ops.sh review` and a resumed film render it again |
| `motion-before/`, `motion-after/` | the review's fix: the frames before and after | never: read only inside that one fix |
| `strip/` | a close look's frames | never: every call renders its own |
| `thumbs/**/*.png` | the thumbnail stills | the missing ones are rendered when options are made (~0.1 s each) |
| `*_silent.mp4`, `*_silent_segments/` | the render before its sound | never: the film is `outputs/film.mp4` |

Never touched: `temp/brand/` (the Free plan's closing, which the film's manifest loads),
`temp/record.lock`, `temp/lines/`, the thumbnails' moments sheet and recorded look
(`style.json`, `boxes.json`), and a film that is being made, waiting for its voice, changed by a
round or drawn again. A round never takes `temp/` into a version (`rounds.OWN`), so nothing a
later version needs can go. `ops.sh status` warns when the data disk passes 80 %.

What still grows after this: each film's master, web copy and narration takes (about 0.3-0.8 GB
a film). At 30 films a day that is weeks, not months, on 512 GB.

## Where the copies are

Until 2026-10-12 everything needed to work on a film again -- its code, its narration takes, its
maker's uploads, the project's cast and voice lines, the templates -- was on the data disk and
nowhere else, with one snapshot fourteen days old (KI-064). Finished films as they play were
already on R2, and records in MongoDB. Now there are three copies, each for a different failure:

| copy | what | how often | kept | survives |
|---|---|---|---|---|
| **Azure Backup** (vault `kitcut-backup-rsv`, resource group `kitcut-backup`, policy `kitcut-daily-30`) | the whole machine, both disks | nightly, 03:00 Pacific | 30 days | a lost or spoiled disk, a wrong delete, a bad release, a break-in on the machine (it holds no Azure identity and cannot touch the vault) |
| **The mirror** (R2 bucket `kitcut-backup`, private) | the studio's home by `deploy/backup-filter.txt`, `models/`, the usage logs | every 15 minutes; by checksum nightly | what a pass replaced or removed: 30 days, under `_history/<day>/` | the Azure account, region or resource group going |
| **The database export** (same bucket, `db/<day>/`) | every collection of `kitcut`, as mongodump writes them | nightly, 02:10 Pacific | 30 days | Atlas losing or spoiling the database |

```bash
bash studio/deploy/ops.sh status                   # "azure backup:" its last job; "mirror:" the
                                                   # last pass, and STALE when it is behind
bash studio/deploy/ops.sh backup --plan            # what a pass would send and remove; sends nothing
bash studio/deploy/ops.sh backup                   # a pass now (capped, beside the films)
bash studio/deploy/ops.sh backup --full            # the nightly pass now: every file by checksum
bash studio/deploy/ops.sh backup verify            # every mirrored file against the bucket
bash studio/deploy/ops.sh backup db --plan         # the database's collections and sizes
bash studio/deploy/ops.sh backup install           # install and start the two timers
bash studio/deploy/ops.sh secrets check            # the machine's sealed keys: do they open through
                                                   # the key vault, and are they the .env as it is now
bash studio/deploy/ops.sh secrets seal | names     # seal now | what the sealed file holds
bash studio/deploy/ops.sh snapshot                 # before a risky change: the data disk, now
```

**What is mirrored is one file**, `studio/deploy/backup-filter.txt`: the first rule that matches
a path decides, and a path no rule matches is mirrored, so a folder nobody thought about is kept.
`studio/test_backup.py` fails a release when the code makes a folder in the home that no rule
decides. Left out: a film's `temp/` (but not `temp/brand/`), `releases/`, `servers/`, `cache/`,
`tmp/`, locks. Not in the mirror at all: the machine's `.env` in the clear.

**The machine's keys are in the mirror sealed.** The `.env` is the one file that holds every key
the studio uses, and with the tunnel's credential it was on one disk. `studio/sealenv.py` packs
the `.env`, `~/.cloudflared/<uuid>.json` and `cert.pem`, encrypts them under a key made for that
one sealing (AES-256-GCM), and wraps that key with the public half of an RSA key that lives in
Azure Key Vault (`kitcut-kv-prod`, `studio-env-kek`, wrap and unwrap only; its public half and
its name are `deploy/studio-env-kek.pub.pem` and `.json`). The result,
`STUDIO_HOME/sealed/studio-secrets.json`, is written before every pass of the mirror when one of
the files changed, so the copy is never older than the last pass and nobody has to remember to
push it. Nothing on the machine, in this repository or in the bucket can open it: opening asks
the vault to unwrap the key (`deploy/unseal.sh`), which takes an Azure sign-in allowed to use
that key. `ops.sh secrets check` does exactly that and compares what opens with the machine's
`.env`, setting by setting, as checksums -- a value never crosses the wire or the screen. First
sealed and checked 2026-10-12: 30 settings, the same; and the copy fetched from the bucket with
the laptop's Cloudflare sign-in (`wrangler r2 object get`) opened the same way.

Why sealed and not stored as key vault secrets: that needs a role on the vault given by hand in
the portal, a copy somebody must remember to refresh after every change of the `.env`, and it
would sit beside the machine in Azure. Sealing needs only the right to use one key, is always
current, and puts the copy on Cloudflare while the key that opens it stays in Azure.

**How a pass compares.** S3 keeps a file's own time in metadata that only a request per object
returns: 85,000 requests a pass, 96 passes a day. So a pass compares names and sizes from one
listing (new, resized, removed), then asks about the files changed in the last six hours one by
one; the nightly pass compares checksums, which a listing also gives because nothing is uploaded
in parts (`--s3-upload-cutoff 4G`). Only the nightly pass sees a file put back with an old time
and the very same size.

**Three guards**, because a mirror that follows the disk faithfully also follows a mistake: what
a pass replaces or removes moves to `_history/<day>/` in the bucket instead of going; a pass
refuses a home with no `projects/` or no film in it (a data disk that did not mount would read as
"everything was deleted"); and it stops at 5,000 removals (`backup.MAX_DELETE`).

The key is the films' own R2 key until `STUDIO_BACKUP_R2_KEY_ID` / `_SECRET` are in the VM's
`.env`: a key allowed to write `kitcut-backup` and nothing else. Delete-locks (`kitcut-keep`) sit
on the data disk, the key vault and the backup vault: removing one of those is two deliberate
steps. The locks are on the resources, not the resource group, or `ops.sh snapshot` could not
prune its old snapshots.

## Films' code in git

```bash
bash studio/deploy/ops.sh filmgit --plan           # what a sync would commit and forget; writes nothing
bash studio/deploy/ops.sh filmgit                  # the sync now (hourly by kitcut-filmgit.timer)
bash studio/deploy/ops.sh filmgit --log <film-id>  # a film's versions, as commits
bash studio/deploy/ops.sh filmgit install          # install and start the hourly timer
bash studio/deploy/ops.sh filmgit publish          # the repositories GitHub does not have yet:
                                                   # made there, each with a key of its own
```

A film is code, and `studio/filmgit.py` keeps each project's films in one bare git repository,
`STUDIO_HOME/git/<project>.git` (a film outside a project: its workspace's, `w-<name>.git`; one
with no signed-in maker: `w-other.git`). On `main`, `films/<film id>/` holds the film's code
(`film.js`, `cast/`, `scenes/`, `engine/`, the `*.json` it is made of), `film.json` (what it is)
and `assets.json` (every file of the film that is not code, with its size: what a checkout
fetches from the mirror); `library/` holds the project's cast and episode log. A version is a
commit, tagged `<film id>/v<n>`. Measured 2026-10-12: all 490 films' code is 110 MB, 80 MB of it
32 engine files copied 1,440 times, which git stores once; the pictures, takes, uploads and
masters (136 GB) are not in git and never will be.

It is kept by looking, not by being told: a sync compares every finished film with what its
repository holds and commits the difference, so nothing in the making of a film can fail on it,
and the first sync is the back-fill (versions still on disk go in first, in order). Two
versions made within the hour are one commit. A film that was deleted is rewritten out of its
repository by the next sync -- its folder, its tags, the bytes -- and that is refused on a home
that is not whole and past 20 films at once.

The repositories ride the mirror with the rest of the home, and each has a copy on GitHub:
private, in an organisation of its own, `github.com/kitcut-films` (never `kitcut-hq`: the
machine runs people's prompts and must hold no key that reaches the product's code). The
machine holds no key to that organisation either. Every repository is pushed with a key made
for it alone (`~/.ssh/filmgit/<name>` on the VM), registered on GitHub as a deploy key that may
write that one repository and nothing else. Making a repository there and registering its key
takes a GitHub sign-in that may do so, which is this laptop's: `ops.sh filmgit publish` does it
for every repository GitHub does not have yet (a new project waits for the next time it is
run). From then on each hourly sync pushes with `--mirror`, so a film forgotten here goes from
there too, and GitHub being down is tried again an hour later. A machine built again has new
keys: `filmgit publish` registers them (the old ones stay on GitHub until removed there).

Working on a film by hand through git (clone, change, push a branch, the studio renders it as
the next version) is the step after that; until then it is `ops.sh take` / `put`.

## SSH for Claude cloud sessions

A Claude cloud session (claude.ai/code) cannot join the VPN, so it has one address of its own,
`ssh.kitcut.ai`. In a session whose environment carries the setup script below,
`ssh kitcut-studio-1 '<command>'` works, and with it `vm.sh ssh`, `push.sh` and everything in
`ops.sh` that is not an `az` call (`vm.sh` returns the VM's name as its address when
`CLAUDE_CODE_REMOTE=true`, and says so when the session has no route).

What a cloud session's network lets out, measured 2026-10-12 in a session with Full access:

| tried | result |
|---|---|
| SSH on port 22 | the connection never opens |
| SSH on port 443 | intercepted: the server's reply never comes back |
| SSH through the session's proxy (`CONNECT`) | `200`, then reset. The proxy decrypts TLS and drops anything else |
| UDP | DNS to 1.1.1.1 passes; no other port was tried, so a VPN client is unproven |
| a WebSocket over HTTPS | works: 64 KB binary frames intact, one connection held 180 s |
| `cloudflared` | downloads from GitHub's releases; its request reaches Cloudflare |
| an `ssh` client | not in the image (`apt-get install openssh-client` in the setup script) |

So SSH rides inside a WebSocket: `cloudflared access ssh` on the session's side, a second
Cloudflare tunnel on the VM's. Four pieces, each with its script:

| piece | what it is | made by |
|---|---|---|
| the lock | a firewall rule on the `kitcut.ai` zone, first in the list: a request for `ssh.kitcut.ai` without the header `x-kitcut-gate: <secret>` is blocked at Cloudflare (403) and never reaches the VM | `ssh-lock.mjs` |
| the tunnel | the unit `kitcut-ssh-tunnel` (256 MB cap), tunnel `kitcut-ssh`, everything it owns in `/srv/kitcut/ssh-tunnel/`: `ssh.kitcut.ai` -> `ssh://127.0.0.1:22` | `ssh-tunnel.sh` |
| the key | the cloud's own ed25519 key, in `authorized_keys` with `from="127.0.0.1,::1"`: it works only for a connection that arrives through the tunnel, never from the VPN | `cloud-env.sh`, `ssh-tunnel.sh key` |
| the session's side | a setup script for the environment's dialog: the ssh client, `cloudflared`, the key, the VM's host key pinned, the host alias `kitcut-studio-1` | `cloud-env.sh` |

The order is the safety: **lock, closed, probe, key, up.** An address with a tunnel and no lock
is the VM's SSH port on the internet.

```bash
P=~/Documents/kitcut-access-cloud       # the private folder: the secret, the key pair, the script
node --env-file=<file with CLOUDFLARE_API_TOKEN> studio/deploy/ssh-lock.mjs --out $P     # the lock
bash studio/deploy/vm.sh ssh kitcut-studio-1 'bash -s -- closed' < studio/deploy/ssh-tunnel.sh
node --env-file=<...> studio/deploy/ssh-lock.mjs --probe --out $P    # 403 without, 404 with: go on
bash studio/deploy/vm.sh ssh kitcut-studio-1 "bash -s -- key \"$(bash studio/deploy/cloud-env.sh $P --pub)\"" < studio/deploy/ssh-tunnel.sh
bash studio/deploy/vm.sh ssh kitcut-studio-1 'bash -s -- up' < studio/deploy/ssh-tunnel.sh
bash studio/deploy/cloud-env.sh $P --test    # a real connection through Cloudflare, from here
bash studio/deploy/cloud-env.sh $P           # $P/setup-script.sh: paste into the environment
```

The setup script goes into the environment's **Setup script** field at claude.ai/code (the
environment's network access on Full, or Custom with `ssh.kitcut.ai` and GitHub's release hosts).
It runs once as root, the result is kept as a snapshot, and every later session starts from it;
Anthropic rebuilds the snapshot when the script changes and about every seven days. A setup
script that fails stops the session from starting, so this one always exits 0 and leaves
`/var/log/kitcut-setup.log`.

Checked on 2026-10-12, from the laptop through Cloudflare (not the VPN):

| | |
|---|---|
| the address without the header, and with a wrong value | 403 |
| the address with the header, tunnel closed | 404 |
| the cloud's key through the tunnel | in, as `kitcut`, from 127.0.0.1 |
| the cloud's key over the VPN | refused |
| through Cloudflare without the header | refused before sshd (`websocket: bad handshake`) |
| through Cloudflare with the header and another key | refused by sshd |
| `vm.sh ssh`, `ops.sh status`, `git ls-remote` on the VM's repo as a cloud session runs them | work |

What that does not cover is the session's own proxy carrying `cloudflared`'s WebSocket all the
way: the table of measurements says it should, and the first thing to ask a new session is
`ssh kitcut-studio-1 hostname`.

Things to know:

- **It is the `kitcut` login**: a session that has it can ship, restart and read the `.env`.
  Anyone who can use the environment can read its setup script, key and secret included, so the
  environment stays personal, never shared.
- **`ops.sh status` watches the lock**: it asks the address without the header and prints
  `NOT LOCKED` on anything but a refusal. The rule lives in Cloudflare's dashboard (Security,
  WAF, Custom rules), where somebody can delete it.
- **Taking the access away**: `ssh-tunnel.sh down` closes the address at once; deleting the
  `claude-cloud@kitcut-studio` line from `~/.ssh/authorized_keys` ends the key. A new secret:
  delete `gate.env`, `ssh-lock.mjs --out`, `cloud-env.sh`, paste the new script.
- **After a rebuild of the VM** the tunnel's credentials are still on the data disk, but the unit,
  the key's line and the machine's host key are new: `ssh-tunnel.sh up`, `ssh-tunnel.sh key`,
  delete `host-key.pub`, `cloud-env.sh`, paste the new script.
- **Never a `config.yml` in `~/.cloudflared`**: the studio's own tunnel (`run-tunnel.sh`) would
  read it at its next start. This tunnel's config is passed with `--config`.
- **Why a firewall rule and not Cloudflare Access**: Access with a service token is the stronger
  lock (it expires, and it keeps a log), but it needs an API token with Zero Trust permissions;
  ours answered `403` on creating the application. The rule needs "Zone WAF: Edit", which it has.

## Remote Control

`claude rc` on the machine lists it at claude.ai/code, so a Claude session can be started on it
from a phone or a browser. It is a service, `kitcut-claude-rc.service`: `claude rc` in a tmux
session (`tmux -L claude-rc`, session `rc`, folder `/srv/kitcut/repo`), started with the machine
and again a minute after it ends. `install.sh` installs it; nothing enables it but the command
below -- a machine is given Remote Control on purpose.

```bash
bash studio/deploy/ops.sh rc                  # at boot or not, who is signed in, its screen
bash studio/deploy/ops.sh rc login            # starts the sign-in and prints its link
bash studio/deploy/ops.sh rc code <code>      # the code the page shows after Authorize
bash studio/deploy/ops.sh rc install          # start it now and with the machine
bash studio/deploy/ops.sh rc stop             # take it off
```

- **The sign-in is a person's, once per machine.** The films' `CLAUDE_CODE_OAUTH_TOKEN` is an
  inference-only token and Remote Control refuses it, so the machine's user gets a full
  `claude auth login`. The account is whichever one the browser that opens the link is signed in
  to, and the machine shows only under that account: on 2026-10-12 a first sign-in on the VM
  landed on the films' account, where the owner could not see it. Films keep their own token
  (the unit unsets it and any API key), so nothing a film costs moves to that account.
- **Its cap is a share of the machine** (`MemoryMax=20%`: 3.2 GB of the VM's 16, 6.4 of 32),
  on every session started through it together. Heavy work still goes through `ops.sh`, whose
  jobs are units of their own.
- `claude rc --help` over ssh without a terminal hangs; run `claude rc` only inside tmux.
- Until 2026-10-12 it was started by hand in a scope on the VM and did not survive a reboot.

## Building it again

```bash
bash studio/deploy/provision.sh kitcut-studio-1 Standard_D4ads_v5 --dry-run   # what it would do
bash studio/deploy/provision.sh kitcut-studio-1 Standard_D4ads_v5              # idempotent
```

The VM, the data disk, the timezone (America/Los_Angeles: the studio's daily caps count local
days, as on the laptop), the checkout, `scripts/setup-linux.sh --studio`, the `.env`, the
tunnel's credentials and the systemd units. Three rules it follows since 2026-10-12 (KI-065):

- **The machine's own `.env` is kept.** It is the one file that holds every key the studio uses,
  and writing it again from a laptop would have dropped the films' storage keys. Only a machine
  with none gets one: from the sealed file of the machine's keys -- the mirror's, fetched with
  this laptop's Cloudflare sign-in, or `--sealed <file>` -- opened by the key vault
  (`deploy/unseal.sh`); or `--env-file <path>`, or `--env-from-vm <another studio VM>`.
- **The tunnel's credentials** come from the VM itself when it has them, else the same sealed
  file, else this laptop's copy wherever under
  `~/.cloudflared` it sits (since the move: `backup-20260928-moved-to-vm/`).
- **What is safe on any machine is enabled** (the usage sampler, the cleanup, the login check).
  The tunnel, the boot unit and the mirror's timers are the cutover's, never before: the tunnel
  may run on one machine only, a studio that came up at boot would announce itself, and a
  machine whose home is not whole yet would mirror its gaps.

`--attach <disk>` takes a data disk restored from Azure Backup. With neither that nor a disk
named `<vm>-data`, the machine gets a new empty one and its home comes from the mirror.

**A machine of our own** (the PC at home, `kc-local`, 2026-10-12: i7-12700, 32 GB,
RTX 3070, Ubuntu Server 24.04) is built by the same command. `vm.sh` takes its address from
`~/.ssh/kitcut-hosts` on the laptop -- `<name> <address>` a line, never committed -- and from
there on `vm.sh ssh`, `push.sh`, `serve.sh` and `ops.sh` treat it as they treat a VM: same key,
same `kitcut` user (with passwordless sudo), same `/srv/kitcut`, which on such a machine is a
folder on its one disk and not a data disk.

```bash
printf 'kc-local 192.168.5.45\n' > ~/.ssh/kitcut-hosts
bash studio/deploy/provision.sh kc-local own --dry-run    # <size> is not read
```

What az does to a VM -- create, resize, stop, start, delete -- is refused for it, and nothing
of Azure's stands behind it: no Azure Backup, no boot diagnostics, no forced restart of a frozen
guest. A home address changes with the router and is reachable from the home network only.

## If the machine is gone

What is where is in "Where the copies are". Finished films play throughout: they are on R2 and
the site answers a film's page from its record (`lib/films.js`). The site emails the owner after
five minutes without an answer and puts down the films the studio left after fifteen
(sketch-studio `lib/studiowatch.js`), so nobody's credits wait on the rebuild.

| what happened | what is lost | do |
|---|---|---|
| The machine is gone or will not boot; the data disk is whole | nothing | **A** |
| The data disk is lost, spoiled, or something was deleted from it | at most the last 15 minutes | **B** |
| One film was deleted or spoiled | nothing | `ops.sh restore --film <id>`; or `--from-history <day>` for what a pass replaced that day |
| Azure itself is gone (account, region, resource group) | at most 15 minutes; YouTube and ElevenLabs connections must be made again by their owners (their key is in the vault) | **C** |
| The laptop is gone | nothing | any machine with `az`, the repo and a VPN peer; a new SSH key goes in with `az vm user update -g kitcut-PROD -n kitcut-studio-1 -u kitcut --ssh-key-value "$(cat new.pub)"` |
| The VPN machine (`wg-vm`, `tarta-wireguard`) is gone | nothing; the studio keeps working, only SSH is cut | `az vm run-command invoke -g kitcut-PROD -n kitcut-studio-1 --command-id RunShellScript --scripts "<command>"` runs anything without the VPN |
| The disk is filling | nothing yet | `ops.sh prune --plan`, "The data disk, and what fills it" |

**A. The machine, with its disk.** About 45 minutes, most of it the toolchain.

```bash
bash studio/deploy/vm.sh delete kitcut-studio-1          # only if a broken one is still there; the data disk is kept
bash studio/deploy/provision.sh kitcut-studio-1 Standard_D4ads_v5
bash studio/deploy/vm.sh ssh kitcut-studio-1 "cd /srv/kitcut/repo && STUDIO_HOME=/srv/kitcut/studio bash studio/serve.sh start"
bash studio/deploy/ops.sh status                         # the studio answers, studio.kitcut.ai the same release
bash studio/deploy/ops.sh backup --plan                  # little to send, nothing to remove
bash studio/deploy/ops.sh backup install                 # the mirror's timers again
```

The data disk still holds `servers/current`, so `serve.sh start` brings back the server that
served; the films it was making are adopted by it (queued ones start again, one Claude was writing
is marked interrupted -- the site has already put those down). Then make one short film and
check it has a voice (`ops.sh film "..." --seconds 10`), and give it Remote Control again if it is
wanted (`ops.sh rc login`, `rc install`: the sign-in lives in the machine's user folder, which a
rebuilt machine does not have).

**B. The disk.** Two sources, used together: last night's Azure Backup brings the whole disk
back fast, the mirror brings what was made since.

```bash
C="iaasvmcontainerv2;kitcut-prod;kitcut-studio-1"
MSYS_NO_PATHCONV=1 az backup recoverypoint list -g kitcut-backup -v kitcut-backup-rsv -c "$C" -i kitcut-studio-1 \
  --query "[].{name:name, at:properties.recoveryPointTime, kind:properties.recoveryPointType}" -o table
MSYS_NO_PATHCONV=1 az backup restore restore-disks -g kitcut-backup -v kitcut-backup-rsv -c "$C" -i kitcut-studio-1 \
  --rp-name <name> --storage-account kitcutst --target-resource-group kitcut-PROD   # managed disks, named by Azure
az disk list -g kitcut-PROD --query "[?diskSizeGb>=\`500\`].{name:name, state:diskState}" -o table
bash studio/deploy/vm.sh delete kitcut-studio-1                         # if it is still there
bash studio/deploy/provision.sh kitcut-studio-1 Standard_D4ads_v5 --attach <the restored 512 GB disk>
bash studio/deploy/ops.sh restore --all                  # what the mirror has that is newer: minutes
```

then `serve.sh start`, `status`, `backup --plan`, `backup install` as in A. The old disk
`kitcut-studio-1-data` carries a delete-lock (`kitcut-keep`): keep it until the new one has
served for a day. `provision.sh` looks for a disk named `<vm>-data` first, so from then on either
pass `--attach` again or copy the restored disk into one of that name (`az disk create --source`).

With no Azure Backup to restore from, leave `--attach` out: the machine gets an empty disk and
`ops.sh restore --all` brings the whole home (about 165 GB) and `models/` from the mirror. The
`.env` and the tunnel's credential then come from the sealed file in the mirror, opened by the
key vault. **Restore before `serve.sh release`**: a release's tests
refuse to go current without every ensemble's instrument samples, and only the mirror (or the old
disk) has them all -- `provision.sh` copies the laptop's cache, which held 11 of the 24 on the
first rehearsal (2026-10-12), and that release stopped at `test_direction`.

**C. Azure itself.** The mirror and the database export are on Cloudflare; the code is on
GitHub. Any Ubuntu 24.04 machine with 4 cores, 16 GB and 500 GB will do:
`scripts/setup-linux.sh --studio`, `studio/deploy/install.sh`, a `.env`, `studio/restore.py
--all`, `studio/serve.sh release` and `start`. What Azure held and must be made again: the
`.env` (each key from the service that issued it -- the names are `procs.py`'s; the Claude
login with `claude setup-token`), and the vault key that seals the site's YouTube grants and
ElevenLabs keys, without which each owner connects again. The site's own settings live in Vercel
and are not affected. The database, if Atlas lost it too: `studio/dbdump.py --restore`.

**What the first rehearsal measured** (2026-10-12, `kitcut-studio-2`, D4ads_v5, built with
`provision.sh --drill` and the mirror alone, about a fifth of the home in it at the time):

| step | took | note |
|---|---|---|
| the machine from nothing: VM, disk, checkout, toolchain, `.env`, units | 12 min | `provision.sh`, one command |
| the home back from the mirror | 579 s for 9,163 files, 20.5 GB: 35 MB/s | so about 80 minutes for the whole home (165 GB) |
| one film restored and compared with production's | 48 files, one checksum over all of them, equal; file times kept | `ops.sh restore --film` |
| the release built and its 29 tests | 10.5 min | `serve.sh release`, after the restore |
| a new film on it, 10 s, narrated | 631 s; video, a voice take with its word times, subtitles | on the Claude login; nothing left the machine |
| a restart of the machine | serving again by itself 80 s later | the boot unit, the data disk by its label |

It found three faults before they were needed, all fixed: the instrument samples came from the
laptop's cache (11 of 29; a release's tests refuse), the machine was built from the branch's head
while the release was the older tag (its tests could not start), and the rebuild would have
pushed this clone's stale branch. Production's own restart the same afternoon (KI-066) then took
26 seconds from boot to a studio that answered.

**Never build a second machine from the mirror and start it as it is.** A server on a restored
home adopts every film that was being made when the home was mirrored, and writes that into the
live database: their makers are refunded and emailed. A machine made only to prove the mirror is
a rehearsal: `provision.sh <vm> <size> --drill --env-from-vm kitcut-studio-1`, then
`KITCUT_VM=<vm> ops.sh restore --all --drill` and `restore --settle`. Its `.env` has no
database, no announcement, no tunnel and no key to the films' bucket (`restore.py
--check-drill` names what is still there), and `backup.py` refuses to write the mirror from it.

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

### From one Linux machine to another (the VM to a machine of our own)

The steps above are from before the machine had anything that writes somewhere else. Since
2026-10-12 it has four: the mirror (`kitcut-backup.timer`, `kitcut-backup-full.timer`), the
films' code (`kitcut-filmgit.timer`, a `git push --mirror` to GitHub), the cleanup
(`kitcut-prune.timer`) and the boot unit. Two machines running them is worse than two tunnel
connectors: every mirror pass of one moves what the other made into `_history/`, and every push
of one rewinds GitHub to its own repositories. And `serve.sh stop` stops the servers and the
tunnel but leaves both **enabled**, so the old machine's next boot would bring a second studio
back. So the old machine is silenced before the new one writes anything, in this order:

1. **The new machine, privately.** `provision.sh`, then the home from the mirror
   (`KITCUT_VM=<new> ops.sh restore --all`; the mirror must have a completed pass first --
   `ops.sh status` says STALE when it has not), then `serve.sh release` **on that machine**: its
   tests draw every template, and a machine with a graphics card has not been shown to draw them
   as the VM does. A film made there before the move is a rehearsal's (`--drill`, see "Never
   build a second machine from the mirror and start it as it is" above): its server must not see
   the database or the tunnel.
2. **A quiet window**: `ops.sh status` on the old machine shows no film and nothing queued.
3. **Old machine**: `serve.sh stop` (drains, stops the servers and the tunnel, says offline).
4. **Old machine, its last copies**: `ops.sh backup` (one pass, followed to its end) and
   `ops.sh filmgit` (commits and pushes what is left).
5. **Old machine, for good**: `sudo systemctl disable --now kitcut-backup.timer
   kitcut-backup-full.timer kitcut-filmgit.timer kitcut-prune.timer kitcut-login-check.timer
   kitcut-studio-boot.service kitcut-tunnel.service` -- or `vm.sh stop <old>`, which is the same
   and surer: a deallocated VM runs nothing, costs its disks only, keeps its Azure Backup points
   for their 30 days, and is the way back for as long as it is kept.
6. **New machine**: `KITCUT_VM=<new> ops.sh restore --all` again (what step 4 sent: minutes), the
   real `.env` and the tunnel's credential (the sealed file, `ops.sh secrets check`).
7. **New machine**: `serve.sh start` (the tunnel, the server, and both at every boot). It adopts
   what the old one left, which is wanted now.
8. **New machine, its own copies**: `ops.sh backup --plan` -- little to send and nothing to
   remove; thousands to remove means its home is not whole: stop and find out why -- then
   `ops.sh backup install`. `ops.sh filmgit publish`, then `ops.sh filmgit install`: a
   repository's GitHub key never leaves the machine it was made on (`~/.ssh/filmgit/`, not in the
   mirror), so the new machine makes its own and `publish` registers them; until then its sync
   says "N not there yet". The old machine's keys stay on GitHub under its name until removed.
9. One short narrated film (`ops.sh film "..." --seconds 10`), one old film opened and changed.

What came over in the `.env` that is the old machine's measurement, not the new one's:
`STUDIO_FILM_MEM_GB`, `STUDIO_RENDER_JOBS`, `STUDIO_MACHINE_SLOWDOWN`, `VIDEDIT_WEBCODECS`
(`deploy/machine.env` says how each was measured). They are safe to start with and wrong to keep.

**What a machine at home does not have**, each of which the VM was relied on for:

- **No second whole copy.** Azure Backup covered the VM's disks nightly; at home the mirror is
  the only one, so a STALE mirror there is an emergency, not a warning.
- **Nobody to force a restart.** The freeze of 2026-10-12 (KI-066) was ended by Azure restarting
  a guest that answered nothing. At home that is a hand on the power button, unless the machine
  restarts itself (a hardware watchdog) and comes back after a power cut (a firmware setting).
- **No way in from outside the house.** The VM was reached over the VPN from anywhere; a home
  address answers on the home network only. `ssh.kitcut.ai` ("SSH for Claude cloud sessions",
  above) is the one route that would work from elsewhere, and it has to be moved with the studio.
- **No network of its own.** The VM sat alone in a subnet that let in SSH from the VPN and
  nothing else. The studio runs what people's prompts and uploads lead Claude to run; at home it
  shares a network with the household's devices unless the machine's firewall, or the router,
  keeps it apart.

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
