---
name: studio-vm
description: Operate the production Sketch Studio (kitcut.ai's film maker) on its Azure VM, kitcut-studio-1 -- check its health, read its logs, ship a release (one server per release, films carry on), roll back, migrate the machine to one server per release (once), make or follow a film, finish (resume) a film that was cancelled or interrupted half-way, pull a film's files, hide a film from the gallery, forward the studio to this laptop, snapshot its disk, or rebuild the machine. Use when asked about the studio's status or errors, "is kitcut.ai working", to deploy/ship/release studio code, to look at the VM or its logs, to make a test film on the studio, to back up or rebuild the studio machine, or when a session used to reach the studio on 127.0.0.1:8765 on the laptop (it now lives on the VM).
---

# The studio VM

kitcut.ai's studio runs on **kitcut-studio-1** (Azure, `kitcut-PROD`, D4ads_v5 -- 4 vCPU, 16 GB,
down from D8ads_v5 the same evening -- Ubuntu) since 2026-09-28 -- not on the laptop. It has no public IP: the laptop reaches it over the WireGuard VPN
(10.0.13.4). Nobody logs in by hand; everything below runs from the laptop's checkout.
`studio/deploy/README.md` is the runbook and holds the measurements.

```bash
bash studio/deploy/ops.sh status                    # start here: health, the servers and their films,
                                                    # disks, login check, errors in the last day
bash studio/deploy/ops.sh logs [studio|tunnel|login] [-n 200] [-f]   # studio: every server unit
bash studio/deploy/ops.sh --dry-run ship [<commit>] # what a ship would do
bash studio/deploy/ops.sh ship [<commit>]           # default: origin/studio-poc's head
bash studio/deploy/ops.sh releases                  # built releases, the leader's marked *
bash studio/deploy/ops.sh rollback <sha12>          # back to one already built, no rebuild
bash studio/deploy/ops.sh migrate [<commit>]        # ONCE per machine (see the rules)
bash studio/deploy/ops.sh film "<idea>" [--seconds 30] [--look collage] [--unlisted] [--api] [--no-watch]
                                                    # on the Claude login unless --api
bash studio/deploy/ops.sh watch <film-id>...        # one or several, a line per change
bash studio/deploy/ops.sh resume <film-id> [--plan] [--finish]  # finish a film the studio stopped
bash studio/deploy/ops.sh resume <film-id> --finish --patched  # a DONE film changed by hand: re-mix, re-render, new URLs
bash studio/deploy/ops.sh pull <film-id> [dest] [--all]
bash studio/deploy/ops.sh hide|show <film-id>       # public gallery
bash studio/deploy/ops.sh replace <film-id> <folder>   # a remade film takes its place: same id
                                                    # and page, old one to backups/, new URLs
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
  builds and tests the release there, starts the release's own server beside the running one and
  returns once it leads, then proves the studio (and studio.kitcut.ai) reports the new release.
- **A ship does not stop films.** One server per release (`kitcut-studio@<sha12>-<timestamp>`,
  all on port 8765): the new one takes new films; the old one hands off, finishes its own and
  exits by itself -- `ops.sh status` shows it, `handed_off`, until then. Rollback (`ops.sh
  rollback`) and `serve.sh restart` (a fresh server of the same code, e.g. after an `.env`
  change) are the same switch. Only `serve.sh stop` (maintenance) stops films; never `systemctl
  restart|stop` a `kitcut-studio@...` unit by hand.
- **Except through the shared venv.** Every release runs on `/srv/kitcut/repo/.venv`: a changed
  `requirements*.txt`, once installed, changes the old server's films mid-film. `ops.sh ship`
  warns; then ship at a quiet moment (`ops.sh status` shows no films).
- **One deploy at a time** (`deploy.lock`): if a ship says another is running, wait for it --
  never start a second one to hurry it. On 2026-09-28 three overlapping ships killed a paying
  film 28 minutes in and restarted onto the old code (KI-031); that is why ships no longer
  restart.
- **Migrate once.** A machine still on the legacy one-server unit (`kitcut-studio.service`) makes
  `ops.sh ship` refuse: run `ops.sh --dry-run migrate`, then `ops.sh migrate` at a quiet moment.
  It runs on the VM in its own unit, waits with no timeout for the legacy server's films, and is
  safe to run again after a failure. Runbook: `studio/deploy/README.md`, "The migration".
- **A film the studio stopped is not lost.** `ops.sh resume <id> --plan`, then without `--plan`:
  one more turn of Claude's own saved session, in the same film (same page and link), its earlier
  cost carried into the record. Check the film's `credit_spends` first -- a spend already released
  stays free; only a still-*held* one is charged when the film comes out done.
- **Read the film's own events, not only the journal.** A step's failure lands in
  `projects/<film>/events.jsonl` as `{"type": "fail"}` and Claude works around it -- the first
  films on the VM went out *silent* because `google-genai` was missing and the narration step
  failed every time, while the journal showed nothing. After any environment change, make one
  film (`ops.sh film`) and check it has a voice (`audio/vo/*.wav`, and listen), not just a picture.
- **Where things live on the VM:** code `/srv/kitcut/repo` (the checkout releases are cut from),
  films `/srv/kitcut/studio` (`STUDIO_HOME`), models `/srv/kitcut/hf`, all on the data disk, which
  a rebuild keeps. Units: `kitcut-studio@<instance>` (one per release; `STUDIO_HOME/servers/current`
  names the one that should serve, `kitcut-studio-boot` starts it at boot), `kitcut-tunnel`,
  `kitcut-login-check.timer`. `ops.sh logs studio` reads every `kitcut-studio@*` unit, each line
  prefixed with its unit.
- **Films made on the VM itself** (`ops.sh film`, `forward`) run on the Claude login
  (`CLAUDE_CODE_OAUTH_TOKEN`, info@instafill.ai, renew by 2027-09-28 -- a person must press
  Authorize); a sign-in failure falls back to the API key. kitcut.ai's films use the same login
  too unless `STUDIO_SITE_AUTH=api` (a film that runs out of the plan carries on on the key).
- **Several films at once:** start each with `ops.sh film ... --no-watch` in the foreground, then
  `ops.sh watch <id> <id> ...`. Never background a following `film` in a shell that exits: the
  POST can already have gone when the shell kills it, and a retry makes the film twice (two
  Apollo 13s, 2026-09-29). The VM makes 3 at once (`pools: claude`); the rest queue by themselves.
  Leave a slot for customers: a queued film of ours waits in front of theirs. `/api/health`'s
  `slots.claude.used` is this server's only -- add `peers` (a handing-over server's films).
- **So are its 16 GB, and a batch job can take them all.** An uncapped `share --missing` held
  15 GB and two customers' films failed at Claude's start (KI-045). Every job `ops.sh` starts runs
  under `MemoryMax`, and `studio/test_memory.py` fails a release whose deploy scripts start one
  without it -- a new job gets a cap, or `# memory: uncapped -- <why>` on the line above. Before
  and while a batch runs, `ops.sh status`: under 2 GB available it prints a WARNING and names the
  biggest process. Stop the batch, never the films.
- **The 4 vCPUs are shared by every unit** -- each server and each `resume` has its own pools, so a
  ship or a `resume --finish` during another film's narration starves its word timing (KI-043: a
  Spanish film lost 17 of its 38 minutes). Do them when no non-English film is recording its voice.

## Replacing a film

When a person's film should be remade (a studio fix made it better), make the new one with
`studio/bakeoff.py` on the laptop (its `--only`, one prompt), review it, then
`ops.sh replace <id> <bakeoff home>/<set>/<arm>/<prompt>/projects/<film>`. The page replays
the film's log, so the log, review images and source files go with the video; the record keeps
its person, project, prompt and cost. Check a figure the new film states against the page text
it read (`web/<name>.txt`) before replacing: the person's name is on it.

## When something is wrong

1. `ops.sh status` -- is the studio answering, is studio.kitcut.ai the same release, any errors?
2. `ops.sh logs studio -n 300` and the film's `events.jsonl` (`vm.sh ssh ... 'tail
   /srv/kitcut/studio/projects/<id>/events.jsonl'`).
   A film that is slow or stuck in Claude's part: `ops.sh claude-log <film-id>` -- one page of
   every reply (when, how long it waited, context size, output tokens, what it did), the API
   errors Claude Code retried, whether it is waiting for a reply right now, and Claude Code's own
   debug log (`--grep TEXT` to search it). A reply that never comes after a long one (writing a
   long film's picture) is a timeout, not a dead CLI: 2026-09-28, film llwtme. Since 2026-09-29 the
   studio catches that itself: 20 silent minutes and it picks the session up again (at most
   twice, `STALL` in `ops.sh logs studio`), so a stuck film fails in about an hour, refunded,
   instead of never. A film made in scenes (past `STUDIO_SCENES_OVER_S`) has a conversation per
   pass: `claude-log` prints a line per pass and details the one under way (`--pass <id>`); a
   restart carries it on from that pass by itself, and `ops.sh resume` does the same by hand.
3. A step that fails on the VM and not on the laptop is usually the environment: compare
   `uv pip list` there with the laptop's venv, and look for imports inside functions.
4. Fix in the repo (worktree, commit, merge to studio-poc), then `ops.sh ship`. A missing package
   can be installed into `/srv/kitcut/repo/.venv` at once (`~/.local/bin/uv pip install --python
   .venv/bin/python ...`) -- every release shares that venv, the films being made included -- but
   add it to the requirements too.
5. The machine itself: `vm.sh` (resize, stop/start); rebuild with `provision.sh` (idempotent,
   reattaches the data disk).

## Resizing

`vm.sh resize <name> <size>` deallocates, resizes and starts (about 3 minutes). Stop the studio
first so nothing is cut off and the site shows it offline: `vm.sh ssh <name> 'bash
/srv/kitcut/repo/studio/serve.sh stop'` (it drains). The units start with the machine. Then set
the pools for the new size in the VM's `.env` (`STUDIO_RENDER_JOBS`, `STUDIO_BROWSERS`: the core
count; `STUDIO_MACHINE_SLOWDOWN`), `serve.sh restart`, and make one `ops.sh film ... --unlisted`
to measure it: compare frames per second (length x fps / `stages.render`), not seconds, because
Free films render at 30 fps. The numbers per size are in `studio/deploy/README.md`.
