# Sketch Studio

One prompt in, and Claude writes, reviews and scores a **short hand-drawn (or painted) film** on
the kitcut sketch engine, narrated, 5-15 s. It's a JSON API for an app backend, plus a page with
one prompt box. It runs on this machine, is reachable from outside through a Cloudflare quick
tunnel, and **makes several films at once**, each in a sandbox of its own.

```powershell
pip install -r requirements-studio.txt       # once: the Claude Agent SDK (bundles Claude Code), pymongo, pywin32
# .env: ANTHROPIC_API_KEY=sk-ant-api...  MONGODB_URI=mongodb+srv://...  (STUDIO_TOKEN is made on first start)
git tag -f studio-stable HEAD                                            # choose the code to ship
powershell -ExecutionPolicy Bypass -File studio\serve.ps1 -Release       # snapshot + test it, (re)start the server on it
powershell -ExecutionPolicy Bypass -File studio\serve.ps1                # server + tunnel; prints the public URL
powershell -ExecutionPolicy Bypass -File studio\serve.ps1 -Restart       # restart the server only (drains first), same URL
powershell -ExecutionPolicy Bypass -File studio\serve.ps1 -Dev           # run this working tree instead of the release
powershell -ExecutionPolicy Bypass -File studio\serve.ps1 -Stop
python studio/agent.py --costs                  # what the runs have cost (from MongoDB)
python studio/agent.py --smoke [--auth login]   # one-turn check: key source, model, cost
python studio/agent.py "a paper plane delivers a coffee" [--auth login]   # one film from the command line
python studio/test_guard.py                     # the permission model, no API calls
python studio/test_sched.py                     # the scheduler's pools
python studio/test_isolation.py                 # names, the gate, secrets, the offline renderer, process kill
python studio/test_server.py                    # the API end to end, 3 films at once, Claude stubbed out, no cost
```

`serve.ps1` writes the tunnel URL to `STUDIO_HOME\url.txt` and to MongoDB `kitcut.studio_hosts`.
A quick tunnel gets a **new random URL each time the tunnel starts**, and it has no uptime
guarantee. The machine must stay on and awake.

## Where things live

`STUDIO_HOME` (default `C:\instafill\kitcut-studio`, next to this checkout; it must be on the
same drive):

```
releases\<sha12>\  current        the code the server runs (release.py), read-only
projects\studio-<stamp>-<rand6>\  one film each: its sandbox (below)
claude\<film-id>\                 Claude Code's config folder for that film's session (its transcript)
outbox.jsonl  server.log  url.txt
```

Films made before the studio had a home (`projects\studio-<stamp>` in this checkout) are still
served from there, read-only.

## Releases: films never run on half-edited code

The server runs from a **release**: `git archive` of a commit (tag `studio-stable` by default)
unpacked into `releases\<sha12>` by `release.py`, which then runs the quick tests inside it and
makes it `current`. A release holds committed files only (no `.env`, no `projects\`, nobody's
uncommitted edits), so developers and their Claude sessions can edit this working tree freely:
nothing reaches a film being made until the next `serve.ps1 -Release`. Two things stay shared
with the working tree: `models\` (a junction: the soundfont cache) and the `.venv`. Every film,
and its record, names the release that made it.

A restart **drains**: the old server takes no new films (503 "restarting"), finishes the ones being
made, and leaves the queued ones for the new server, which picks them up. A server that starts
also finds what a crash left: queued films are made, films caught mixing or rendering are finished,
and films Claude was still writing are marked `interrupted`.

## Many films at once

Each film is a folder of its own (`film.py`), and nothing it does reaches outside it:

| | |
|---|---|
| **Claude** | its working directory is the film's folder; it may Read only there (not `temp\`, `studio.json`), and Write/Edit only `film.js`, `score.json`, `sfx.json`, `vo.json`, `paint.json` (painted films) and its own engine copy, `engine\engine.js` and `engine\props.js` (`guard.py`). Paths are checked on their real path, so neither `..\` nor a link leads out. |
| **No shell** | Claude has no Bash. It drives the pipeline through the studio's own tools (`tools.py`, an in-process MCP server): `check`, `voice`, `paint`, `stills`, `sound`. Each runs one kitcut script on the film's manifest, and nothing else. |
| **Its files** | pinned and checked after every write and before every tool (`validate.py`): a painting's or an instrument's name can never name a path (the scripts refuse them too), and there are caps on lines, paintings, sounds and sizes. |
| **Secrets** | read into memory at start and taken out of the environment (`procs.py`). Claude Code gets only its auth; each step only what it needs (the voice the Google keys, the painter OpenRouter's; the render and the mix none). |
| **The renderer** | the page a film's code runs in is served under a random key with a Content-Security-Policy that lets it reach only its own server, and Edge runs offline: no network, no other render, not this server. |
| **Processes** | every step runs in a Windows Job Object: a timeout or a cancel kills the step and all it started (Edge, ffmpeg) at once, and if the server dies, they die with it. |
| **Claude Code** | a config folder per film (`STUDIO_HOME\claude\<id>`), `setting_sources=[]`, `strict_mcp_config`, no claude.ai connectors. |

They share the machine through the scheduler (`sched.py`), first come, first served:

| Pool | Size | Who |
|---|---|---|
| `claude` | 3 (`STUDIO_PARALLEL`) | a film's Claude phase; the others queue (`STUDIO_MAX_QUEUE`, 5) |
| `browser` | 4 | review stills take 1, the final render 3 |
| `cpu` | 2 | the voice (Whisper, on the CPU: the GPU stays the renderer's) and the mix |

Time a film spends waiting for the machine does not count against its 15 minutes of Claude time.
The page says what a film is waiting for ("Waiting for the renderer: 1 film ahead").

## The public site

The public site is https://create.kitcut.ai, from
[kitcut-hq/sketch-studio](https://github.com/kitcut-hq/sketch-studio) on Vercel:
- It serves a copy of `index.html`; keep the two the same.
  - The page carries the site's sign-in UI and its credit line: what a film costs (one credit a
    second) and what is left this cycle, under the length slider.
  - Both appear only where `/api/me` answers, which is on the site and not here. On this
    server (token filled in) and through the bare tunnel (token form), the page works as it
    always has, and the slider is just a length from 5 to 60 s. The 1-5 min part of the track
    is drawn but locked; lifting it takes `LENGTHS` in `film.py` and the site's plan together.
- It looks the tunnel URL up in `kitcut.studio_hosts`, so a restart needs no redeploy.
- **Anyone may watch there, but making (or stopping) a film needs an account** (Google, or a
  one-time link by email, sent through SendGrid from `hello@kitcut.ai`).
  - The site owns the accounts (MongoDB `kitcut.users`); this server knows nothing of them.
  - It forwards the page's calls with the token added server-side, plus `X-Client-Ip`.
  - For a film request, `X-Client-Ip` is `u:<userId>`, the signed-in account, so the
    per-client limits below are per account and `studio_runs.client` records whose film it was.
  - For other calls it is the visitor's IP.
  - The sign-up wall and the credits live in the site's `api/studio.js` and `lib/credits.js`,
    not here. The site holds a film's seconds before forwarding it, and settles them from this
    server's `studio_runs` record of the run: `done` is charged; `failed`, `interrupted` and
    `cancelled` are given back. **Keep those `state` names stable.** See that repo's README.
- `serve.ps1 -Stop` marks the studio offline there.

Limits on everything that reaches the studio, checked and taken together under one lock:
- **A day's spend:** `STUDIO_DAILY_USD`, default $25, counting `STUDIO_RESERVE_USD` ($1.50) for
  every film still being made.
- **One film in the making per client**, and `STUDIO_PER_CLIENT_DAILY` (default 5) a day.

Past a limit, the request gets a 429 with a plain-English reason.

## The API (for the app backend)

Send the token (`STUDIO_TOKEN` in `.env`) with every call except `/api/health`. Any of these
works: `Authorization: Bearer <token>`, `X-Studio-Token: <token>`, or `?token=<token>`.

```bash
BASE=https://<name>.trycloudflare.com
curl -s -X POST $BASE/api/films -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" -d '{"prompt": "a paper plane delivers a coffee", "seconds": 10}'
# 202 {"id": "studio-20260925-131102-k3f9qa", "status": "queued|running", "position": 0, "status_url": "..."}

curl -s "$BASE/api/films/studio-20260925-131102-k3f9qa?since=0" -H "Authorization: Bearer $TOKEN"
# {"status": "queued|running|done|error|cancelled", "stage": "claude|sound|render",
#  "wait": "Waiting for the renderer -- 1 film ahead", "position" (queued), "elapsed_s", "cost_usd",
#  "events": [...new since `since`], "next": <pass as since next time>,
#  when done: "video_url", "poster_url", "seconds", "stages", "tokens", "turns"; on error: "error"}

curl -s -X POST $BASE/api/films/<id>/cancel -H "Authorization: Bearer $TOKEN" -H "X-Client-Ip: <the same client>"
curl -s -o film.mp4 "<video_url from the status>"    # signed for 12 h: no token needed
curl -s $BASE/api/costs -H "Authorization: Bearer $TOKEN"     # spend totals and the latest runs
curl -s $BASE/api/films -H "Authorization: Bearer $TOKEN"     # finished films, newest first
curl -s $BASE/api/health                                      # running, queued, the pools, the release
```

**Poll the status, every 2-5 s.** There is no push, because quick tunnels do not carry
server-sent events. A film takes about 3-6 minutes, most of it Claude. The prompt is capped at
600 characters.

## What it costs, and where that is recorded

Every run is a document in **MongoDB `kitcut.studio_runs`**. That's the database kitcut-web uses:
- `MONGODB_URI` is the Atlas `appmakers` cluster.
- The database name is always `kitcut`, as in kitcut-web's `lib/db.ts`.
- `store.py` documents every field.

When each document is written:
- **When the film is asked for** (`state: queued`), so it counts toward the day's limits at once.
- **When Claude starts** (`running`), **every ~5 s while it works** (the cost so far), when the
  studio takes over (`finishing`), and **once at the end** (`done | failed | cancelled`, or
  `interrupted` after a restart).

What each document holds: `cost_usd` (Claude + voice + paintings), `claude_cost_usd`,
`tts_cost_usd`, `image_cost_usd`, `tokens`, `turns`, `seconds`, `stages` (incl. `waited`, the
time spent queued for the machine), `calls` (one entry per Claude API response), `release`,
`engine_changed` (lines Claude changed in its engine copy; the diff is in the film's
`outputs\engine.diff`), `prompt` and `client`.

The Claude cost is the SDK's own figure, cross-checked by pricing the token counts at Opus 5.5
rates ($4 / $20 per million in / out; cache writes $5 (5 min) or $8 (1 h); cache reads $0.20).
The system prompt depends only on the look, so films made close together share Claude's prompt
cache. If the database can't be reached, the final record goes to `STUDIO_HOME\outbox.jsonl`,
and `python studio/agent.py --sync` sends it later. The authoritative bill is still the
Anthropic Console.

## How a film is made

1. `server.py` (aiohttp, 127.0.0.1 only) admits the request, makes the film's folder
   (`film.py`: the manifest from `template/sketch.json`, the engine copy, an empty narration)
   and starts it; it waits for a Claude slot.
2. `agent.py` runs Claude (**Opus 5.5 only**, `MODEL`) through the **Claude Agent SDK**, which
   is Claude Code's agent loop as a library. The system prompt is `prompt.md` and the look's
   `looks/<look>.md`, with the engine, the cast, the example film and the sound notation read
   fresh from the code (written to a file: at ~100 KB it is too long for a Windows command
   line). The film's length and the prompt come in the first message.
3. Claude writes the narration and records it (`voice`), writes `film.js` (and for a painted
   film, the paintings), renders review stills and looks at the sheet, fixes what it sees, writes
   the score and the cues, and checks the soundtrack (`sound`).
4. The studio then mixes the soundtrack and renders the video (three browsers at once), and the
   MP4 lands in the film's `outputs\film.mp4`.

## Paying for Claude

`--auth api` (the server always uses it) runs on `ANTHROPIC_API_KEY` from `.env` and a config
folder per film, with `setting_sources=[]`: it never uses a local Claude Code login, its
settings, its memory or its skills. `--auth login` (command line only) runs the newest installed
Claude Code on this machine's login instead; Claude's tokens are then covered by the plan and
recorded as not billed. Never serve the public from a login.

`CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS=1` is set because some organisations reject Claude
Code's default context-management beta with a 400 ("not available for HIPAA-regulated
organizations without Zero Data Retention").

## Other systems

Nothing here is Windows-only in principle, but it has only been run on Windows (the process
containment is a Job Object there, a process group elsewhere). Elsewhere it needs Python 3.13,
Node, ffmpeg and Chrome, Chromium or Edge (`html-to-image.py` finds them). `serve.ps1` is
Windows-only; elsewhere run `server.py` with `STUDIO_HOME` set, and `cloudflared tunnel --url
http://127.0.0.1:8765` yourself.
