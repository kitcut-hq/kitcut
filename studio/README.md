# Sketch Studio

One prompt in, and Claude writes, reviews and scores a **short hand-drawn (or painted, or collage) film** on
the kitcut sketch engine, narrated, 5 s to 8 minutes. It's a JSON API for an app backend, plus a page with
one prompt box. The public one runs on an Azure VM (`kitcut-studio-1`, since 2026-09-28;
`studio/deploy/README.md`), is reachable from outside through a Cloudflare named tunnel
(studio.kitcut.ai), and **makes several films at once**, each in a sandbox of its own. The
Windows commands below still run a studio on a laptop, for development -- never with the tunnel.

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
python studio/agent.py --smoke [--auth api]   # one-turn check: key source, model, cost
python studio/agent.py "a paper plane delivers a coffee" [--auth api]   # one film from the command line
python studio/test_guard.py                     # the permission model, no API calls
python studio/test_sched.py                     # the scheduler's pools
python studio/test_isolation.py                 # names, the gate, secrets, the offline renderer, process kill
python studio/test_direction.py                 # one cached prompt per look, a film's choices, the recent note
python studio/test_server.py                    # the API end to end, 3 films at once, Claude stubbed out, no cost
python studio/test_media.py                     # the copy online, against a stand-in for Azure
```

`serve.ps1` writes the tunnel URL to `STUDIO_HOME\url.txt` and to MongoDB `kitcut.studio_hosts`.
A quick tunnel gets a **new random URL each time the tunnel starts**, and it has no uptime
guarantee (on 2026-09-27 one kept running while its host name stopped resolving, and the site
said "offline" until the tunnel was restarted). A **named tunnel** keeps one address: set
`STUDIO_TUNNEL` (the tunnel's UUID; its credentials in `~\.cloudflared\<uuid>.json`) and
`STUDIO_TUNNEL_HOST` (e.g. `studio.kitcut.ai`) in `.env`, and `serve.ps1` runs it instead. The
machine must stay on and awake.

## Where things live

`STUDIO_HOME` (default `C:\instafill\kitcut-studio`, next to this checkout; it must be on the
same drive):

```
releases\<sha12>\  current        the code the server runs (release.py), read-only
projects\studio-<stamp>-<rand6>\  one film each: its sandbox (below)
claude\<film-id>\                 Claude Code's config folder for that film's session (its transcript)
uploads\<sha20(client)>\          pictures and voice notes waiting for a film (uploads.py)
library\<sha20(client)>\          a signed-in person's cast and film memory (library.py, below)
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
| **Claude** | its working directory is the film's folder; it may Read only there (not `temp\`, `studio.json`), and Write/Edit only `film.js`, `score.json`, `sfx.json`, `vo.json`, `paint.json` (painted and collage films) and its own engine copy, `engine\engine.js`, `engine\props.js` and, in a collage film, `engine\collage.js` (`guard.py`). Paths are checked on their real path, so neither `..\` nor a link leads out. |
| **No shell** | Claude has no Bash. It drives the pipeline through the studio's own tools (`tools.py`, an in-process MCP server): `check`, `voice`, `paint`, `stills`, `sound`. Each runs one kitcut script on the film's manifest, and nothing else. |
| **Its files** | pinned and checked after every write and before every tool (`validate.py`): a painting's or an instrument's name can never name a path (the scripts refuse them too), and there are caps on lines, paintings, sounds and sizes. |
| **Secrets** | read into memory at start and taken out of the environment (`procs.py`). Claude Code gets only its auth; each step only what it needs (the voice the Google keys and ElevenLabs' for the backup voice, the painter OpenRouter's; the render and the mix none). |
| **The renderer** | the page a film's code runs in is served under a random key with a Content-Security-Policy that lets it reach only its own server, and Edge runs offline: no network, no other render, not this server. |
| **Processes** | every step runs in a Windows Job Object: a timeout or a cancel kills the step and all it started (Edge, ffmpeg) at once, and if the server dies, they die with it. |
| **Claude Code** | a config folder per film (`STUDIO_HOME\claude\<id>`), `setting_sources=[]`, `strict_mcp_config`, no claude.ai connectors. |

They share the machine through the scheduler (`sched.py`), first come, first served:

| Pool | Size | Who |
|---|---|---|
| `claude` | 3 (`STUDIO_PARALLEL`) | a film's Claude phase; the others queue (`STUDIO_MAX_QUEUE`, 5) |
| `browser` | 4 | review stills take 1, the final render 3 |
| `cpu` | 2 | the voice (Whisper, on the CPU: the GPU stays the renderer's) and the mix |

Time a film spends waiting for the machine does not count against its Claude time (20 minutes up
to 15 s of film, more for a longer one -- 136 minutes at 8 minutes: `film.limits()`). The page says what a film is waiting
for ("Waiting for the renderer: 1 film ahead"). A film sent with `X-Priority: 1` (the site's
plans with priority) joins every queue ahead of the films without it, first come first served
among its own.

## The public site

The public site is https://kitcut.ai (create.kitcut.ai redirects there), from
[kitcut-hq/sketch-studio](https://github.com/kitcut-hq/sketch-studio) on Vercel:
- It serves a copy of `index.html`; keep the two the same.
  - The page carries the site's sign-in UI and its credit line: what a film costs (one credit a
    second) and what is left this cycle, under the length slider.
  - Both appear only where `/api/me` answers, which is on the site and not here. On this
    server (token filled in) and through the bare tunnel (token form), the page works as it
    always has, and the slider is just a length from 5 to 60 s. On the site it runs to the
    plan's longest film (Pro: 8:00; `max_length` in the site's `lib/plans.js`, within `LENGTHS`
    here), and the rest of the track up to 8:00 is drawn but locked.
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
- **A day's spend:** `STUDIO_DAILY_USD`, default $100, counting a reserve for every film still
  being made: at least `STUDIO_RESERVE_USD` ($1.50), more for a longer film ($0.35 + $0.06 a
  second).
- **Lengths:** 5-480 s in 5 s steps. Who may ask for what (over a minute is Pro) is the site's
  business; so are its plans and credits.
- **One film in the making per client**, or as many as its plan allows (the site sends
  `X-At-Once: 2` for Pro, trusted like `X-Priority`; never more than `STUDIO_AT_ONCE_MAX`,
  default 2), and `STUDIO_PER_CLIENT_DAILY` (default 5) a day. Two films from one account each
  take a Claude slot. The same upload sent with both goes to the first; the second is told to
  add it again.

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
# {"status": "queued|running|done|error|cancelled|lost", "stage": "queue|claude|sound|render|cast|online",
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
server-sent events. A 10 s film takes about 8-12 minutes, a minute-long one about half an hour,
most of it Claude (the site's `estimateMinutes`). The prompt is capped at 12000 characters.
`GET /api/limits` (no token) lists the limits a person can meet, with no money in it: the
site's docs (kitcut.ai/docs) are built from it, so a change to a limit here means rebuilding
them (`npm run docs` in sketch-studio).

**Pictures and voice notes** (`uploads.py`). The page uploads each one as it is attached
(`POST /api/uploads`, the raw bytes), and a film request names them (`"attachments": [ids]`); a
film may then have no typed words at all. The kind is read off the file's first bytes (JPEG, PNG,
WebP pictures; WebM, Ogg, MP4, WAV, MP3 recordings), a picture must open in Pillow, a recording
may last 3 minutes. A voice note is written out in the background -- Gemini 3.1 Flash Lite on
Vertex, then Whisper large-v3-turbo on the CPU if that fails (`STUDIO_STT` overrides; measured by
`scripts/stt-compare.py`) -- and `GET /api/uploads/<id>` returns its words; a note with no speech
comes back empty without asking any engine, because every model tried invented words for
silence. Only the uploader's client (`X-Client-Ip`) can see or use an upload; what no film takes is
deleted after a day. A film copies its attachments into `inputs/` (Claude reads them, never
writes), pictures join the manifest's `images` as `upload1...`, and the first message lists them
with the instruction to look at each and say what it took it to be; a film nobody typed a word for
gets its title from Claude (`name_film`). Pictures film.js never draws leave the manifest before
the final render, so they never reach the film's files.

`GET /api/uploads` lists the asker's uploads no film has taken yet, newest first, each with
`expires_in` seconds (the assistants' `list_uploads`).

**Link-only films.** `"listed": false` in the film request keeps the film out of the gallery
(`GET /api/films`); the site also keeps it out of its sitemap and marks its page noindex. Its page
and link still work. `POST /api/films/<id>/listed {"listed": true|false}` lets the film's own
client switch it. `hidden` stays the operator's switch, separate from this. Films the site makes
for an assistant (its MCP server) come with `X-Source: mcp` and `X-App: <Claude|ChatGPT|...>`,
trusted like `X-Priority`, and are link-only unless the person asked for public; the record
keeps `source`, `app` and `listed`.

**Copies online** (`media.py`). A finished film's `film.mp4`, poster, link-preview card and
subtitles are copied to Azure blob storage (account `kitcutst`, container `films`, anonymous read,
`<id>/<file>`) as its last stage, "online", with a container SAS on the stored access policy
`studio-upload` (`STUDIO_MEDIA_BASE`, `STUDIO_MEDIA_SAS` in `.env`). The record keeps the URLs as
`media`; status and the gallery then hand those out instead of signed tunnel URLs, so a film plays
while this machine is off. A copy that fails leaves the film as it was. `python studio/media.py
--backfill` copies earlier films; `--film <id>` one; `--delete <id>` removes one. Never use the
container `media`: the catalog site's `upload-media.py` prunes it of anything not its own.

**Publishing to YouTube** (`youtube.py`). The public site holds each person's channel grants and
opens a resumable upload session with YouTube for the film. The studio gets only that session's
address:

```bash
curl -s -X POST $BASE/api/films/<id>/youtube -H "Authorization: Bearer $TOKEN" -H "X-Client-Ip: u:<account>" \
     -H "Content-Type: application/json" -d '{"to": "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&upload_id=...", "key": "<post id>"}'
# 202 {"key", "film", "state": "sending", "sent": 0, "size"}
curl -s $BASE/api/films/<id>/youtube/<post id> -H "Authorization: Bearer $TOKEN" -H "X-Client-Ip: u:<account>"
# {"state": "sending|done|failed", "sent", "size", "video": {"id", "privacy", "upload"}, "error"}
```

- **Who may send.** Only the film's own client, and only a finished film. The address must be
  YouTube's upload endpoint.
- **How it sends.** `outputs/film.mp4` goes up in 8 MiB pieces. After a dropped connection or a
  5xx, the studio asks the session how far it got and carries on from there.
- **Asking twice** with one key sends once.
- **Sends are kept in memory.** After a restart the site asks again, and the send picks up from
  what YouTube already has. The studio never holds a Google token.

**The title and description** (`ytdraft.py`) are written from the film, in the channel's voice.
The site reads the channel's latest uploads with its grant and sends them; the studio adds what
the film is (the narration with its times, who it is for, the pages its facts came from, what
Claude said it made) and asks Claude once:

```bash
curl -s -X POST $BASE/api/films/<id>/youtube/draft -H "Authorization: Bearer $TOKEN" -H "X-Client-Ip: u:<account>"      -H "Content-Type: application/json" -d '{"channel": {"id": "UC...", "title": "...", "handle": "@..."}, "recent": [{"title", "description", "tags"}]}'
# 202 {"state": "writing"}, or 200 with the draft when it is already written
curl -s $BASE/api/films/<id>/youtube/draft/<channel id> -H "Authorization: Bearer $TOKEN" -H "X-Client-Ip: u:<account>"
# {"state": "writing|done|failed", "title", "description", "tags", "language", "error"}
```

Only links it was given survive, chapters must fit the film, and a draft that pastes the prompt
back is refused. Try one by hand with `python studio/ytdraft.py --film <id> --sample-from @handle`
(`--plan` prints the ask and its price). Details: `docs/reference.md`.

**The thumbnail** (`thumbs.py`, `scripts/_thumb.py`): four options, each a still of the film itself
with a few words on it, offered in the publish dialog. The same Claude call chooses them: it sees
a sheet of the film's clean moments with their times (made first, ~12 stills; no Free-plan mark)
and answers four `{at, words, layout, place}` -- one each of headline, slab, panel and the picture
alone. Once the draft is written, the job makes the options: the settled frame near each moment,
the words where they hide nothing that matters, one browser shot for every layer, and checks
(legible at 168 px wide, 4.5:1 contrast, clear of YouTube's duration stamp, none of the film's own
words covered). An option that fails falls back (a scrim, a slab, the still alone) before anyone
sees it. The draft's answer carries them:

```bash
# ... "thumbs": {"state": "making"} while they are made (~10-15 s), then
# ... "thumbs": {"state": "done", "v": "<draft key>", "options": [{"n", "path", "layout", "words", "at", "t"}]}
curl -s $BASE/files/<id>/youtube/<channel id>/thumb-1.jpg -H "Authorization: Bearer $TOKEN" > thumb-1.jpg
```

The site shows them through its own owner-only relay and, once YouTube has the video, sets the
one picked with `thumbnails.set` on its own grant; a failure (most often an unverified channel)
never fails the publish. They cost no model time beyond the draft's (+~$0.01): CPU and a browser,
at most `STUDIO_THUMB_JOBS` (2) at once. Try them by hand with `python studio/ytdraft.py --film <id>
--thumbs`, or on hand-written concepts with `python scripts/thumb-options.py --film <folder>`.

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
2. `agent.py` runs Claude (**Opus 5.5 only**, `MODEL`, at effort `EFFORT` = xhigh) through the
   **Claude Agent SDK**, which is Claude Code's agent loop as a library. The system prompt is
   `prompt.md` and the look's `looks/<look>.md`, with the engine, the cast, the two example films
   (`examples/`) and the sound notation read fresh from the code (written to a file: at ~130 KB
   it is too long for a Windows command line). The **collage** look (`looks/collage.md`) also
   carries `sketch/collage.js` and the example `config/sketch/collage-example/film.js` (~195 KB
   in all): its `paint.json` asks for cut-outs (`"cutout": true`, painted on a transparent
   background by the pinned `cutouts` model, `limits()["cutouts"]` of them), its engine copy
   includes `collage.js`, and its manifest adds the print faces (`film.COLLAGE_FONTS`). It is the same for every film of a look, so it
   stays cached. The film's length, the prompt and what recent films chose come in the first
   message.

   **Who it is for, and one bar.** Before anything else Claude decides from the prompt who the
   film is for and its mood (never assuming children unless the prompt says so), writes it as
   film.js's first line -- `// For: <who it is for>; <its mood>`, read back as
   `direction.audience` -- and holds the whole film to one bar: professionally made for that
   audience. The review looks at the sheet against that line before any detail.

   **The brief carries no style.** Every sentence of `prompt.md` and `looks/*.md` is one of
   three kinds: *capability* -- what exists and how to call it (grounds, styles, props, fonts,
   instruments, voices, sound generators), described by what each thing is, never what it is
   for; *craft* -- faults in any style (text cut off, overlaps, a blank frame 0, a dead stretch,
   a scene waiting empty for its subject, levels); or *the bar* above. Nothing says what a film
   should look or sound like; that is the person's to say in the prompt, or Claude's to choose.
   The brief used to prescribe -- "characters give a film its charm... an object with a face",
   "a place, not a page", "pop/boing on appearances", a subject beside every menu entry -- and
   34 of 46 films drew faces or the cartoon kid, an 8-minute documentary about Dell and HP among
   them (studio-20260927-171047-mgkibw). A protective style rule ("watercolour is for children
   only", a checker refusing faces on serious films) is the same mistake pointing the other
   way. Measure a change to the brief with `bakeoff.py` (below) before it ships.

   **Films that don't all look alike.** Every film starts from the same instructions, so the
   prompt makes Claude choose a direction first -- what fills the frame, the ground
   (`SK.setGround`), the voice and its direction, an ensemble and a tempo, for a painted film the
   painting style -- from menus of choices tested together (`config/sketch/grounds/` renders
   every ground). The first message then lists what the last eight finished films chose
   (`recent_films`, counts only, never their prompts; never the audience), and Claude chooses
   freshly unless the prompt calls for a repeat. What each film chose is kept as `direction` in
   its record and in Mongo.
3. Claude writes the narration and records it (`voice`), writes `film.js` (for a painted film,
   the paintings first), renders review stills and looks at the sheet, runs `motion` -- the film a few
   times a second, reporting its cuts and any stretch where nothing moves for 4 s
   (`motion.py`) -- fixes what it sees, writes the score and the cues, and checks the
   soundtrack (`sound`). It is told its working time
   (`film.limits`). **When the time runs out,** a film that is whole and passes the checks is
   finished anyway (`overtime` on its record); one whose picture is written gets one short last
   turn in the same session to write what is missing (`wrap_up`, 4 minutes); only then does it
   fail.
4. The studio then mixes the soundtrack and renders the video (three browsers at once), and the
   MP4 lands in the film's `outputs\film.mp4`.

**Free-plan films** (the site sends `X-Branding: 1`; `branding` on the record) carry a small
"made with kitcut.ai" in the corner and end with a 3-second closing: the last frame as a tilted
snapshot beside the logo and kitcut.ai, with a chime and "Make yours at KitCut AI" (one recording,
`brand/closing.wav`). `studio/outro.js` draws both; `agent.brand` adds them to the manifest as a
`tail` at the final render only, so Claude's review stills never show them.

**A series: the person's cast and memory** (`library.py`). A signed-in person (the site's
`u:<id>` client) has a library that outlives their films, next to `projects\`, never in git:
- **What is kept.** Their cast is characters, places or things as small modules
  (`SK.cast.<name> = {about, draw(x, y, o)}`), plus the films they made.
- **What a new film gets.** Before Claude starts, a new film gets:
  - the latest version of every member in its `cast\`, which loads before film.js (the manifest's
    `cast` key; see sketch-render);
  - the members drawn on one sheet (`library\cast.png`);
  - their last five films, read-only, in `library\films\` (film.js, vo.json, score.json, the
    poster and the direction).
- **What Claude hears.** The first message lists them. Whether to bring anything back is
  Claude's call: a continuation keeps the cast, look, voice and music, and a new idea is its own
  film. The system prompt only explains the mechanism, so it stays the same for everyone and
  stays cached.
- **After an ok film.** `agent.keep_cast` takes in each new or changed member as a new version
  (the last five are kept), draws it alone for a thumbnail, and remembers which films used it.
  A failed film keeps nothing.
- **Routes** (the asker's own library): `GET /api/library`, `GET /api/library/<name>/thumb.png`
  and `DELETE /api/library/<name>`. A delete keeps the files, and later films leave the member
  out.

**Projects: a series or a channel with a library of its own.** The site keeps projects (a name,
a brief, defaults) in Mongo and sends `"project": {id, name, brief, from_account_cast}` with a
film it vouches is the person's. That film is an episode:
- **Its library is the project's**, `library\<sha20(client)>\<project id>\`, the same layout as
  the person's. It seeds from there and keeps into there, never into the person's own, and a film
  outside projects never sees a project's. A project made with "bring in my characters" starts
  with a copy of the person's own cast, once.
- **Pictures.** A project holds up to six (`pictures\<name>.*`), made from uploads with `POST
  /api/library/pictures`. Every episode gets them as `inputs\pic_<name>.*`, in the manifest as
  `pic_<name>`; the ones neither film.js nor the cast draws leave before the final render, like
  unused attachments.
- **What Claude hears.** The first message names the project and gives its brief (the person's
  words), then the pictures, the cast and the earlier episodes. The first episode hears that its
  choices are what the next ones keep.
- **Records.** `studio.json` keeps the project as it was asked for. `studio_runs` gets only
  `project_id` (and every run now has `title`, `name_film`'s when nothing was typed): the site
  lists a project's episodes from there. Limits stay per person, across projects.

## Bake-off: measure a change to the brief before it ships

`bakeoff.py` makes one set of prompts (`bakeoff/<set>.json`, each with the audience it is for)
with two versions of the studio -- two checkouts, usually a worktree at the base commit and one
with the change -- then grades every film blind and puts them side by side:

```powershell
python studio/bakeoff.py --set audience --plan                     # what runs, its rough cost
python studio/bakeoff.py --set audience --arm before --tree C:\instafill\kitcut-fit-base
python studio/bakeoff.py --set audience --arm after  --tree C:\instafill\kitcut-fit
python studio/bakeoff.py --set audience --grade                    # a blind read of each film
python studio/bakeoff.py --set audience --compare before after     # compare.html + the tallies
```

- **Made as a release makes a film:** `STUDIO_REPO`/`STUDIO_ENV_FILE` name the main checkout
  (its keys, the machine's locks) and the tree gets a `models\` junction, as `release.py` gives a
  snapshot. Remove that junction on its own (`cmd /c rmdir <tree>\models`) before removing the
  tree: a recursive delete through it empties the main checkout's `models\`.
- **Kept apart:** each film has a home of its own under `kitcut-studio-bakeoff\<set>\<arm>\`
  beside the checkout, is link-only (`source: bakeoff`), is not copied online, and gets no
  recent-films note, so the films of a set cannot steer each other. Each result records whether
  the film really ran on its tree's brief.
- **The grade** shows Claude eight frames of the finished film and nothing else -- no prompt, no
  arm -- and asks about the look, not the audience (a film about revenue reads "for adults"
  however cartoonish it is drawn): how much it belongs in children's animation (0-1), how well it
  fits its subject and how professionally made it looks (1-5 each). It is a mild grader -- the
  Dell film's googly-eyed first minutes scored childish 0.40, fits 3 -- so compare the arms, and
  look at the frames. The page also counts what each film used (faces, the doodle people, pops
  and boings): counts to read, never a rule.
- `--auth login` (the default) runs on this machine's Claude Code login. A 30 s film costs about
  $2.5 of Claude and 15-20 minutes; `--jobs 3` makes three at once.

**The first run** (set `audience`, 2026-09-27: 14 films of 30 s, before = b20966e, after = the
no-style brief): on the five serious prompts the old brief's films read childish 0.39 and fit
their subject 3.6 of 5 (3 of 5 films fit); the new brief's 0.17 and 4.4 (5 of 5). The controls
did not move (the bedtime story and the cat-cafe ad: childish 0.70, fit 4.5 in both). Claude
$2.41 -> $2.53 a film, 16.6 -> 17.2 min. The widest gap was the Pripyat evacuation: a sunlit
picture book with smiling families (0.70) became muted flat illustration ending at dusk on the
empty Ferris wheel (0.35) -- better, not solved, since the props' only trees and clouds are
cartoon ones. That is capability, not instruction.

## Paying for Claude

There are two ways to pay:
- **`--auth api`** runs on `ANTHROPIC_API_KEY` from `.env` and a config folder per film, with
  `setting_sources=[]`: it never uses a local Claude Code login, its settings, its memory or its
  skills. Every film through the tunnel, which means the public site, runs this way.
- **`--auth login`** runs the newest installed Claude Code on this machine's login instead.
  Claude's tokens are then covered by the plan and recorded as not billed, so they don't count
  against the day's budget. Films made on this machine run this way by default: the command
  line, and a POST from this machine itself. `{"auth": "api"}` in the POST puts one on the key.

Never serve the public from a login. Through the tunnel, the server ignores the switch.

**A login that fails falls back to the key.** When a login film cannot sign in -- logged out, a
`claude setup-token` expired or revoked, no Claude Code installed -- `run_claude` raises
`SignInError`, and `make_film` runs Claude's part again, once, on the key. The film is made
instead of lost, and its record tells the truth: `auth: "api"`, billed, and
`fallback: {"from": "login", "why": "..."}`; the log shows "This machine's Claude login failed";
the server holds it against the day's budget as a film on the key. The SDK does not raise on a
failed sign-in (measured 2026-09-28, Claude Code 2.1.284): the turn ends with an assistant
message whose `error` is `authentication_failed` ("Not logged in · Please run /login", "Failed to
authenticate. API Error: 401 ...") and an `is_error` result, and that is what is matched. A usage
limit (`rate_limit`), a billing error or an overloaded API is not a lost login and is never
retried on the key. `test_server.py` checks both, against the messages the CLI really sent.

**The login is checked every morning** on the Azure VM (`agent.py --check-login`, run by
`studio/deploy/kitcut-login-check.timer`): one turn on the login, recorded in
`kitcut.studio_hosts` as `login: {ok, why, host, checked_at}` and in the journal; a failure
leaves the unit failed, so a dead login is noticed before the key's bill is.

`CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS=1` is set because some organisations reject Claude
Code's default context-management beta with a 400 ("not available for HIPAA-regulated
organizations without Zero Data Retention").

## Other systems

The public studio runs on Linux: an Azure VM, Ubuntu 24.04 under systemd, with no GPU.
`studio/deploy/README.md` is its runbook: provisioning (`provision.sh`), releases
(`serve.sh`, the Linux `serve.ps1`), what the VM does differently and the measurements behind each
setting (the render encodes in the browser in software; a step's containment is a cgroup v2
instead of a Job Object). The biggest difference: the VM never restarts to ship. Each release runs
as a server of its own (systemd `kitcut-studio@<instance>`, all on one port); the new one takes
the new films while the old one finishes its own and exits, so a ship stops no film. `scripts/setup-linux.sh --studio` builds the toolchain on any Ubuntu
24.04. Outside systemd a step leads a process group of its own and has no memory cap.
