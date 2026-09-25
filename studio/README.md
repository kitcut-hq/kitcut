# Sketch Studio

A proof of concept: one prompt in, and Claude writes, reviews and scores a **5-second
hand-drawn film** on the kitcut sketch engine. It's a JSON API for an app backend, plus a page
with one prompt box. It runs on this machine and is reachable from outside through a Cloudflare
quick tunnel.

```powershell
pip install -r requirements-studio.txt       # once: the Claude Agent SDK (bundles Claude Code), pymongo
# .env: ANTHROPIC_API_KEY=sk-ant-api...  MONGODB_URI=mongodb+srv://...  (STUDIO_TOKEN is made on first start)
powershell -ExecutionPolicy Bypass -File studio\serve.ps1                # server + tunnel; prints the public URL
powershell -ExecutionPolicy Bypass -File studio\serve.ps1 -ServerOnly    # restart after a code change, same URL
powershell -ExecutionPolicy Bypass -File studio\serve.ps1 -Stop
python studio/agent.py --costs                  # what the runs have cost (from MongoDB)
python studio/agent.py --smoke                  # API check: key source, model, cost
python studio/agent.py "a paper plane delivers a coffee"   # one film from the command line
python studio/test_guard.py                     # the permission model, no API calls
python studio/test_server.py                    # the API end to end with Claude stubbed out, no cost
```

`serve.ps1` writes the tunnel URL to `temp/studio-url.txt` and to MongoDB `kitcut.studio_hosts`.
A quick tunnel gets a **new random URL each time the tunnel starts**, and it has no uptime
guarantee. The machine must stay on and awake.

**The public site** is https://create.kitcut.ai, from
[kitcut-hq/sketch-studio](https://github.com/kitcut-hq/sketch-studio) on Vercel:
- It serves a copy of `index.html`; keep the two the same.
  - The page carries the site's sign-in UI.
  - That UI appears only where `/api/me` answers, which is on the site and not here. On this
    server (token filled in) and through the bare tunnel (token form), the page works as it
    always has.
- It looks the tunnel URL up in `kitcut.studio_hosts`, so a restart needs no redeploy.
- **Anyone may watch there, but making a film needs an account** (Google, or a one-time
  link by email, sent through SendGrid from `hello@kitcut.ai`).
  - The site owns the accounts (MongoDB `kitcut.users`); this server knows nothing of them.
  - It forwards the page's calls with the token added server-side, plus `X-Client-Ip`.
  - For a film request, `X-Client-Ip` is `u:<userId>`, the signed-in account, so the
    per-visitor cap below is per account and `studio_runs.client` records whose film it was.
  - For other calls it is the visitor's IP.
  - The sign-up wall and the plan limits to come live in the site's `api/studio.js`, not here.
    See that repo's README.
- `serve.ps1 -Stop` marks the studio offline there.

Two limits apply to everything that reaches the studio:
- **A day's spend:** `STUDIO_DAILY_USD`, default $25.
- **A visitor's films per day:** `STUDIO_PER_CLIENT_DAILY`, default 5. Through the site, a
  visitor is an account.

Past either limit, the request gets a 429 with a plain-English reason.

## The API (for the app backend)

Send the token (`STUDIO_TOKEN` in `.env`) with every call except `/api/health`. Any of these
works: `Authorization: Bearer <token>`, `X-Studio-Token: <token>`, or `?token=<token>`.

```bash
BASE=https://<name>.trycloudflare.com
curl -s -X POST $BASE/api/films -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" -d '{"prompt": "a paper plane delivers a coffee"}'
# 202 {"id": "studio-20260925-131102", "status": "queued", "position": 0, "status_url": "..."}

curl -s "$BASE/api/films/studio-20260925-131102?since=0" -H "Authorization: Bearer $TOKEN"
# {"status": "queued|running|done|error", "stage": "claude|sound|render", "elapsed_s", "cost_usd",
#  "events": [...new since `since`], "next": <pass as since next time>,
#  when done: "video_url", "poster_url", "seconds", "stages", "tokens", "turns"; on error: "error"}

curl -s -o film.mp4 "<video_url from the status>"    # signed for 12 h: no token needed
curl -s $BASE/api/costs -H "Authorization: Bearer $TOKEN"     # spend totals and the latest runs
curl -s $BASE/api/films -H "Authorization: Bearer $TOKEN"     # finished films, newest first
```

**Poll the status, every 2-5 s.** There is no push, because quick tunnels do not carry
server-sent events. A film takes about 2-3 minutes:
- Claude takes about 110 s.
- The render takes about 30 s.

**One film is made at a time.** Up to `STUDIO_MAX_QUEUE` (default 5) more wait, and the next
request gets a 429. The prompt is capped at 600 characters.

## What it costs, and where that is recorded

Every run is a document in **MongoDB `kitcut.studio_runs`**. That's the database kitcut-web uses:
- `MONGODB_URI` is the Atlas `appmakers` cluster.
- The database name is always `kitcut`, as in kitcut-web's `lib/db.ts`.
- `store.py` documents every field.

When each document is written:
- **When the run starts.** The document shows `state: running`.
- **Every ~5 s while Claude works.** It carries the cost so far.
- **Once at the end.** It records `state: done | failed`.

A run that dies half-way still shows what it spent.

What each document holds:
- `cost_usd`, `tokens`, `turns`, `seconds` and `stages`.
- `calls`: one entry per Claude API response, with its tokens and cost.
- `prompt`, and `client`: the caller's IP as Cloudflare saw it.

The cost is the SDK's own figure, cross-checked by pricing the token counts at Opus 5.5 rates:
- Input: $4 per million tokens.
- Output: $20 per million tokens.
- Cache write: $5 per million tokens (5-minute cache) or $8 (1-hour cache).
- Cache read: $0.20 per million tokens.

On every run so far the two figures matched to the cent. About **$0.55 per film**.

If the database can't be reached, the final record goes to
`projects/studio-runs-outbox.jsonl`, and `python studio/agent.py --sync` sends it later. The
authoritative bill is still the Anthropic Console.

## How a film is made

1. `server.py` (aiohttp, 127.0.0.1 only) makes `projects/studio-<stamp>/` with a 5-second
   manifest (`template/sketch.json`).
2. `agent.py` runs Claude (**Opus 5.5 only**, `MODEL`) through the **Claude Agent SDK**, which
   is Claude Code's agent loop as a library.
3. The system prompt is `prompt.md`, with the engine, the cast, the example film and the sound
   notation read fresh from the repo. It is written to a file, because at ~80 KB it is too long
   for a Windows command line.
4. Claude writes `film.js`, `score.json` and `sfx.json`. It then renders review stills, looks at
   the contact sheet, fixes what it sees, and checks the soundtrack renders.
5. `agent.py` then runs `sketch-audio.py` and `sketch-render.py`, and the MP4 lands in
   `outputs/film.mp4`.

## What Claude can touch

`guard()` in `agent.py` decides every tool call through a `PreToolUse` hook. Claude can:

- **Read** anything in the repo except `.env*`, `.git` and `.venv`.
- **Write and Edit** only `film.js`, `score.json` and `sfx.json` in its own job folder.
- **Run** four exact commands:
  - `node --check`
  - `sketch-render.py --stills`
  - `sketch-render.py --automation`
  - `sketch-audio.py`

  No chaining, pipes, redirection or `$()`.

## API only

The run uses `ANTHROPIC_API_KEY` from `.env` and a private `CLAUDE_CONFIG_DIR`
(`temp/studio-claude/`), with `setting_sources=[]`. So it never uses a local Claude Code login,
its settings, its memory or its skills.

`CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS=1` is set because some organisations reject Claude
Code's default context-management beta with a 400. The error reads "not available for
HIPAA-regulated organizations without Zero Data Retention". A 5-second film never needs that
beta.

## Other systems

Nothing here is Windows-only, but it has only been run on Windows. On Linux or macOS it needs:
- Python 3.13, Node and ffmpeg.
- Chrome, Chromium or Edge, which `html-to-image.py` finds on PATH or in `/Applications`.

The prompt's `python` becomes `python3` where only that exists. `serve.ps1` is Windows-only;
elsewhere, run `server.py` and `cloudflared tunnel --url http://127.0.0.1:8765` yourself.
