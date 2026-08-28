# Product strategy: how this repo becomes a business

**Written** 2026-08-27, from a strategy session. **Status:** plan. Nothing in this
document is built yet — it is the reasoning and the execution detail, kept so the
next session (or the next person) does not have to re-derive it.

The product name is undecided. `InstaCut` appears below as a placeholder in paths
and commands; it is an example, not a decision. See *Open questions*.

---

## The one-page version

The tool is extremely time-saving and almost impossible to distribute the normal
way: not an app-store app, not a Chrome extension, not a web SaaS. The resolution:

> **Distribute the *outcome* to people who lack the environment. Distribute the
> *tool* only to people who already have it. Never ask a normal person to install
> Python.**

The people who already have the environment — Claude Code, a GPU, the footage —
are (a) developers who owe the world demo videos and (b), on new evidence,
**working video editors**, because Claude Code is escaping the developer
population into operators. For them the product is a **licensed Claude Code
plugin that runs entirely on their machine**: their Claude, their GPU, their
footage, our skills and scripts. Our cost of goods is approximately zero. Their
NDA footage never leaves the rig, which turns local-first from a liability into
the pitch.

There is no way to make it stop working when they stop paying, and we should not
try — the product requires the customer to own an AI that reads and edits code,
so any license check is one prompt away from removal. The subscription sells the
**stream**, not the snapshot: this stack rots (YouTube API, ffmpeg/driver traps,
Claude Code format changes, new pipelines), and every paying customer's weird
footage becomes a gotcha-library entry the cancelled copy never gets.

The cloud/thin-client version is real and technically close — but it is phase 2,
for the people without a GPU, not the wedge.

---

## 1. The distribution paradox, and where it flips

Naive answers all fail. A SaaS throws away what makes the tool good (the
conversational agent interface *is* the product). A public repo nobody can
install is not distribution. The install barrier is genuine: Python, a GPU,
ffmpeg, Claude Code.

It flips on one observation: there is an audience where install base and pain
**fully overlap**.

- **Developers who owe demo videos** — founders, devrel, indie hackers. They run
  Claude Code already. They own the GPU already. And the deepest, least contested
  pipeline in this repo (multicam: screen recording + phone take, never in sync)
  is exactly their problem. Their footage is often a pre-release product that
  legally cannot go to a SaaS cloud.
- **Video editors** — see §2, this is the newer and possibly larger read.

Adjacent proof that the shallow half of this is monetizable: Screen Studio and
Tella built real businesses just making screen recordings *pretty*. Nobody sells
making them *edited*.

## 2. Audience — the editor read

**The trigger observation (2026-08-27):** five SEO specialists, all heavy Claude
users; several vibe-code working internal SaaS apps; some carry *separate*
corporate and personal Claude Code subscriptions. That is not "SEO likes Claude."
It is Claude Code moving from developers to **operators** — tool-heavy
professionals whose job is repetitive digital production. SEO led because its work
is text-native. Video is the next domain over.

Which adoption traits transfer to editors:

| trait | transfers? | why it matters |
|---|---|---|
| Buys workflow tooling as a habit | **Yes** | The aescripts/preset/plugin economy is how editors have always worked. **AutoPod** charges a monthly fee for exactly the pass this repo automates (multicam switching + silence removal in Premiere) and sustains a business. Willingness to pay for *this pain* is proven. |
| Personal, out-of-pocket tooling spend | **Yes** | Freelancers carry tooling between clients; personal tooling *is* their edge. Same psychology as the second Claude subscription. |
| Owns the hardware | **Yes** | Editing rigs are GPU rigs. Our Windows+NVENC "limitation" describes the YouTube-economy editor's machine almost exactly. |
| Lives in a terminal | **No** | Their home is a timeline. This is the one to design around. |

**Consequence of the last row: work around the NLE, not against it.** The agent
does the pass everyone hates — sync, grouping, multicam switch, silence, captions
— and hands back a **timeline**, not only an mp4. Technically cheap: the cut
decisions are already frame-exact cut lists, so FCPXML/EDL/OTIO is serialization,
not research. It also defuses the "AI is replacing me" reflex this audience has on
a hair trigger: *the boring 80% is done, you do the taste part* reads as more
billable hours.

**Consequence for sequencing:** if editors are already in Claude Code, the first
revenue SKU needs **no infrastructure at all**. They have the environment *and*
the footage is born local on their NVMe, so the upload tax — the thin client's one
real constraint — is zero for them.

**This is still an anecdote about a different trade.** Validate deliberately,
one week, before building cloud plumbing:

1. **Five editor conversations.** Two screening questions: *"do you personally pay
   for Claude or ChatGPT?"* and *"what is the pass you would pay to never do
   again?"* (Prediction: sync and multicam grouping come up unprompted.)
2. **Post the debug-overlay video** — the editor that explains every cut on screen
   — to r/editors and the editing Discords. This audience will say loudly whether
   it reads as threat or tool, and craft receipts (the frame-scored benchmark) are
   the only marketing they respect.
3. **A ~$99 founding-editor beta** to whoever bites. Payment, not opinion, is the
   signal — and their weird footage hardens the gotcha library.

Green on two of three → licensed plugin + NLE export first, thin client second.

## 3. What we actually own

Not the scripts. Any agent can write ffmpeg scripts tomorrow. If copying the repo
killed the business, the business was already dead. What is genuinely ours:

- **The gotcha library.** Every trap in the README cost real hours and is
  invisible until it burns you (`aselect` passing every audio frame; the phone's
  lying rotation tag; `shortest=1` on the looped mask; never measuring silence on
  the rendered file; conform before measuring; NVENC not re-encoding an identical
  frame identically).
- **The verification discipline.** Nothing renders unproven; every script prices
  the decision first (`--list`, `--dry-run`, `--frame`).
- **The benchmark.** Frame-scored against professionally edited films: stage 1
  exact on four films, stage 2 at 73–87% agreement with the human editor from
  audio alone. Nobody else can show that.

Those three are also what a cancelled copy stops receiving. That is not a
coincidence — it is the business model (§5).

## 4. The offer: what the customer buys

Everything expensive is already the customer's. We sell the one layer that cannot
be bought anywhere else.

| layer | what | whose |
|---|---|---|
| Brain | Claude Code + their subscription | customer (pays Anthropic) |
| **Judgment** | **the skills — editing craft + gotcha library** | **ours — this is the product** |
| Hands | `scripts/` — the SDK Claude operates | ours, shipped in the plugin |
| Muscle | GPU, NVENC, disk, the footage | customer's rig |
| Runtime | Python venv, pinned ffmpeg, whisper/ONNX models | auto-installed by our setup |

**SKUs:**

- **Free** — public marketplace plugin: captions + shorts. Your GPU, no upload, no
  watermark, no minutes quota. The animated handle badge is default-on here and
  opt-out on paid — the "Sent from my iPhone" loop.
- **Pro (~$249–499/yr)** — private marketplace: multicam, dub, publish, name
  labels, cards/overlays, the gotcha library, NLE export, updates, support,
  Discord, and the onboarding course. Buyers: devrel teams, indie hackers, and
  **freelance editors** (sell shovels to the incumbent labor — an editor with this
  does several times the throughput at the same day rate).
- **Team seats** — expansion revenue. Companies buy licenses because companies get
  audited, even where individuals do not.
- **Cloud render (phase 2)** — for Mac/no-GPU users. Manifests up, mp4 down,
  metered. §10.

**Unit economics of Pro:** COGS ≈ 0. The customer pays Anthropic for inference,
owns the GPU, stores their own footage. Every SaaS competitor pays GPU + inference
per customer; we sell pure knowledge at a flat subscription.

**The honest trade, and say it on the pricing page:** we cannot meter usage; we
inherit support for heterogeneous Windows machines (mitigations: the doctor,
pinned ffmpeg, "run the doctor and paste the output"); and the customer's true
cost is *their* Claude subscription plus our license — a daily-use editor
realistically needs Claude Max, so all-in is roughly $150–250/mo. Still under an
hour of a professional's day rate. Say it plainly rather than letting them
discover the quota mid-week.

## 5. Why there is no kill switch — and what replaces it

**Question asked:** can we make it stop working if they stop paying?
**Answer: no, and do not spend a dollar trying.**

It would be DRM run against the customer's own AI. The product *requires* them to
own an agent that reads and edits code; that same agent strips any check — MCP,
API ping, signature, obfuscation — in one prompt. It is the only DRM arms race in
history where the crack tool is a system requirement. Compiling to binaries does
not save it either: that kills the actual product property, which is that their
Claude can maintain and extend the scripts locally. Every enforcement move makes
the product worse for payers and does nothing to non-payers.

**Invert it.** Cancelling should not *break* the product; it should mean losing
something real that is not the bits on disk. Three things qualify:

1. **The stream — because this stack rots, honestly and fast.** YouTube's API
   shifts and `yt-upload.py` breaks. Claude Code's skill/plugin format evolves. A
   new ffmpeg or NVIDIA driver introduces the next `aselect`-class trap. TTS
   backends drift. New pipelines ship. And every paying customer's odd footage
   becomes gotcha entries the cancelled copy never receives. The renewal is
   maintenance, not loyalty. Video tooling sits on more moving third-party ground
   than almost any category — that is the enforcement, and it is real.
2. **Support and belonging.** The buyer is a freelancer with a client deadline on
   Tuesday. Professionals do not run orphaned tooling on billable work. They pay
   for "somebody fixed it before my delivery" and the Discord where the fix
   appeared on Sunday night. This is exactly why the WordPress pro-plugin economy
   works while being *legally* copyable — GPL lets anyone redistribute ACF Pro or
   Gravity Forms, and it is still a large market, because the key gates updates
   and support, not execution.
3. **Server-side work — the only honest kill switches.** Cloud render. A hosted
   client-review link, if we ever want it. A license check guarding *our* compute
   cannot be stripped, because the work is not on their machine. Anything local:
   assume it is theirs forever, because it is.

**Then advertise the property we are afraid of.** "Perpetual fallback — cancel
anytime, keep everything you have" is the JetBrains model, adopted after their
subscription revolt, and it converts precisely the skeptic we are worried about.
For an audience courted with "no phone-home, footage never leaves your rig,"
rent-ware that dies on cancel would contradict our own pitch. Someone who pays six
months, cancels and keeps the snapshot is capped downside — they were never a
lifetime payer, and they gave us six months plus word of mouth. DRM loses more.

**The condition this model lives or dies on:** the stream must *visibly* live. A
changelog that ships something useful most weeks makes renewal a non-decision;
three quiet months teaches every customer that the snapshot was enough. If that
cadence is not sustainable, this is the wrong model — lead with the cloud tier and
meter the server instead. The choice is not philosophical; it is whether we are
willing to be the people who publish the fix every week.

## 6. Rejected options, with reasons

- **A shorts web SaaS.** Entrant #40 against Opus Clip, Submagic, Klap, Vizard in
  a freemium quota war funded by ad spend, with no distribution — and flattening
  the agent into buttons deletes the differentiation.
- **Leading with dub.** HeyGen/ElevenLabs own that narrative with lip-sync. Our
  cadence-preserving dub is a supporting act, not the poster.
- **Selling the raw repo.** Scripts are clonable; the license must bundle what is
  not — knowledge freshness, updates, benchmark, community.
- **Any local license enforcement.** See §5.
- **Auto-applying updates.** See §7 — an editor mid-project must not have the
  ground move under a render.
- **Silent prompt capture.** See §9 — it is the one move that can kill the company.

## 7. Delivery logistics: install, access, updates

### Three repos

| repo | visibility | contents |
|---|---|---|
| **dev** (this one) | private | experiments, dev history, benchmarks. Customers never see it. |
| **free marketplace** | public | `marketplace.json` + the free plugin (captions, shorts). The funnel. |
| **pro mirror** | private | same structure, full plugin. CI pushes from dev **on tagged releases only**. |

A Claude Code plugin marketplace is just a git repo with a `marketplace.json`;
customers run `/plugin marketplace add <org>/<repo>` then `/plugin install`. The
release gate into the pro mirror is the existing check suites (`check-script.py`,
`check-dub.py`, `check-multicam.py`) — one broken update costs more trust than
three good ones earn, and that test culture already exists here.

### Access: a GitHub invite *is* the license key

Do not build an auth system. Stripe checkout asks for their GitHub username → a
webhook worker (~100 lines) adds them to a team in our org → they accept the
invite → `/plugin marketplace add <org>/pro` works, because **their own git
credentials are the license check**. Cancel → webhook removes them → the next
update politely 403s and the installed snapshot keeps working forever. GitHub is
the CDN, the auth and the update server, at zero cost (a Free-plan org allows
unlimited collaborators on private repos).

Friction to watch: a non-developer editor needs a GitHub account and a one-time
`gh auth login` (~3 minutes; the setup skill can walk them through it). If
onboarding data shows drop-off there, v2 is a small gateway — a Cloudflare Worker
validating a license key and proxying git — so they clone
`https://key:<LICENSE>@get.<domain>/pro` with no GitHub at all. Build that when
the drop-off is *measured*.

### The install: a skill does it — that is the trick

Traditional products need bulletproof installers because no intelligence is
present at install time. Here the one guaranteed thing on every customer machine
is Claude. So the installer is `/setup`, wrapping the two halves that already
exist (`check-env.py` for diagnosis, `setup-python.ps1` for repair): run the
doctor → interpret → fix → verify. The PYTHONPATH war already fought is why this
can be reliable on a stranger's machine.

On codecs — there is nothing to install, and the landing page should say so,
because editors expect codec-pack hell. A static ffmpeg build contains every
decoder/encoder; NVENC ships inside the NVIDIA driver. `/setup` does:

1. Check Python, git, disk; install missing pieces via winget.
2. **Download our pinned ffmpeg build** (hosted by us, checksum-verified) into the
   plugin's own tool directory — never PATH, never the customer's ffmpeg. Half the
   documented traps are version-specific; pinning deletes that whole support
   category.
3. Probe GPU + driver version (NVENC has a minimum; the doctor names the fix
   instead of letting a render fail an hour in).
4. Pull ONNX models with checksums; whisper weights fetch on first use.
5. Walk the customer through their own keys (ElevenLabs, YouTube OAuth) into `.env`.
6. **Finish by burning captions onto a bundled 10-second sample and opening the
   mp4.** A rendered file inside ten minutes is the moment that converts.

### Updates: hook notifies, human decides, agent explains

A `SessionStart` hook does a cheap once-a-day check (cached HEAD comparison; never
blocks, never raises — same discipline as the statusline reader) and prints one
line: *"v1.4 available — fixes X — run `/update`."* **Notify, never auto-apply**:
an editor mid-project must not have the ground move under a render. This is the
existing `STALE` concept, pointed at the plugin itself.

Two touches that make updates a feature:

- **Stamp the plugin version into `project.json` on every render** (one line in
  `_project.record()`). Support gets "what version are you on" free;
  reproducibility survives updates.
- **Ship the changelog as a skill-readable file**, so after an update the
  customer's Claude answers *"does this affect my projects?"* — "this release
  changes caption layout; episodes 3 and 5 would render differently now." No other
  software category can do that, and it is what makes the stream visibly alive,
  which §5 rides on.

`/update` itself: fetch upstream → rebase the customer's `local/patches` branch
(§9) → have the agent resolve conflicts *semantically* → drop patches upstream has
absorbed → run the check suites before declaring success. **Software you have
modified that still updates cleanly** essentially does not exist elsewhere; it is
a headline feature that falls out of the git discipline we need anyway.

### Total infrastructure

Public marketplace repo, private mirror repo, one CI job (dev → mirror on tag,
gated by checks), one Stripe webhook worker (invite/revoke + welcome email), the
`/setup` skill, the `SessionStart` hook. No servers holding customer data, no
accounts system, no update CDN.

**First engineering step, before any business plumbing: run the whole path on a
clean Windows VM.** Fresh machine → install Claude Code → add marketplace →
`/setup` → test render. That produces the first ten gotchas of the *product* (as
opposed to the pipelines) and prices the support tail. Validate the private
marketplace auth flow end-to-end there too — the design matches how marketplaces
work, but the exact commands and edge cases (git on a bare Windows box,
credential prompts) should be proven on that VM, not trusted from this plan.

## 8. Working directories and routing

### Three locations, strictly separated

```
plugin root  (${CLAUDE_PLUGIN_ROOT})      scripts, skills, default configs, pinned ffmpeg,
                                          models. Updated by the marketplace. NEVER customer data.
the studio   (chosen at setup, e.g. D:\Studio)
                                          projects/<id>/, footage, renders, .env, workspace
                                          CLAUDE.md, pre-set permissions. The customer's world.
the pointer  (~\.instacut\config.json)    where the studio is, license, consent flags.
```

The separation makes updates safe (they cannot touch footage), uninstall harmless
(the studio survives), and per-client isolation possible later (NDA-separated
`Studio-ClientA` / `Studio-ClientB` off one plugin). Do not build multi-studio at
launch; do not design it away.

### Global capability, one canonical home, never forced

The plugin is global — skills load in every session anywhere. Video work gets one
home, chosen once at `/setup`, with the doctor *suggesting* it after probing
drives for space and speed (renders and scratch live there; a customer picking a
small system SSD is a support ticket waiting to happen).

We cannot force a working directory, so **route** instead, in three layers:

1. **Scripts resolve the studio themselves**: explicit flag → env var → pointer
   file → fail with a clear message. cwd stops mattering to correctness. This is
   the one real refactor the design needs: a small `_workspace.py` beside
   `_env.py` that every script resolves paths through.
2. **The `SessionStart` hook** notices a session started outside the studio and
   injects "the studio is at D:\Studio — video work goes there," so a session
   launched in Downloads still creates the project in the right place.
3. **Make being in the studio better.** Claude Code loads context and settings
   per-directory, so the studio ships with a `CLAUDE.md` and — critically — a
   `.claude/settings.json` with **pre-allowed permissions** for the plugin's
   scripts and ffmpeg. Outside, Claude asks permission for every invocation;
   inside, it just works. Forty permission prompts per session is the difference
   between a product and a demo. Setup installs these transparently and says so.

Make the studio a git repo at creation with this repo's ignore pattern: manifests,
`project.json` and `journal.md` tracked; `sources/ outputs/ temp/` ignored. The
customer gets version history on every editing decision, and it is the same
mechanism the auto-commit hook (§9) relies on.

**Config layering:** customers *will* customize caption presets, brands and card
templates, and those must survive updates. Studio-side `config/` shadows plugin
defaults — the same relationship `projects/` has to `config/` today. Their brand
kit lives in their studio; our defaults update underneath it.

### The launcher — sugar, never a requirement

- **`instacut` on PATH**: opens Claude in the studio. For terminal people.
- **A desktop shortcut for everyone else.** Windows passes files dragged onto a
  shortcut as arguments, so the editor **drags three camera files onto the icon**;
  the wrapper stages them into `studio\inbox\` and launches Claude with "new
  project from inbox." Footage to running session in one gesture, no cd, no paths
  typed. That single affordance bridges "Claude Code user" and "person who edits
  video for a living," and costs an afternoon.

It must stay optional — everything works from a bare `claude` in any folder
(layers 1–3 guarantee it). The moment the wrapper is *required*, we have built a
shell around Claude Code, and the premise is that Claude Code **is** the shell.

### Routing: how a plain request finds our scripts

Today, working inside this repo, plain prose picks the right script with no
explicit skill call. That is not folder magic — **it is `CLAUDE.md`**, auto-loaded
from the starting folder, whose pipeline map does the routing. Skills do a
different job: depth. Claude auto-invokes them when a task matches, invisibly.

Portable version of the same two tiers:

- **Catch-all = the hook, not a skill.** A hook's stdout is injected into context,
  and it can be as long as needed — the full equivalent of this repo's CLAUDE.md
  is ~4–5k tokens, a rounding error. Better than a static CLAUDE.md because it is
  **computed**: cwd holds video files or is the studio → inject the full map plus
  live state ("two projects in flight, episode-12 render is STALE"); unrelated
  coding folder → one breadcrumb line, because dumping 5k tokens of editing lore
  into every coding session on the machine would be obnoxious.
- **One skill per pipeline** — never called explicitly by anyone. Their job is
  craft: manifest keys, verification steps, gotchas. Without them the customer's
  Claude finds the scripts but re-derives every trap at the customer's expense.
  Skills load that depth only when the task needs it.
- **Skill descriptions are always in context** in every session regardless of
  folder — that is the mechanism by which "just say what you want" works. So the
  description lines are a routing table and must be **tested like code**: a
  20-phrase battery ("dub this", "make shorts", "remove the pauses") run from
  random folders, scoring whether the right pipeline fires. Release gate, same as
  `check-multicam`.

The real risk is not "skill not found" — it is Claude freelancing with raw ffmpeg
instead of our pipeline. The hook line plus sharp "Use when…" descriptions is what
prevents that.

### Writing CLAUDE.md into a customer's own folder

Legitimate, under one condition: the folder is a **workplace**, not just where
files landed.

- **Never write a copy of the map** — it goes stale on the next release. Write one
  import line (`@<plugin-path>/MAP.md`). The folder gets the full native
  experience and updates with the plugin.
- **One-off stray session** (Claude opened in Downloads next to two clips): write
  nothing, route into the studio. Littering every folder that touches a video is
  how products get uninstalled.
- **Recurring workplace:** this is the big case. Editors have rigid folder
  religions — per-client drives, structures their NLE depends on — and will not
  move footage into our studio. For them, `/setup --here` consecrates *their*
  folder: the import line, `.claude/settings.json` permissions, the `projects/`
  skeleton. The studio comes to the footage. The pointer file grows a list of
  workspaces.
- **Folder already has a CLAUDE.md:** ask first, always. If it is a git repo with
  a committed CLAUDE.md, an appended line lands in their next commit and announces
  itself to their whole team. Offer, show the line, let them place it.

## 9. The learning flywheel — learning from every client

The gotcha library only compounds if other people's footage feeds it.

**The landmine first: raw prompt capture can kill the company.** Prompts contain
transcript quotes, client names, "cut the part where the CEO mentions the
acquisition." Our whole differentiation is "no phone-home"; a plugin that silently
ships prompts home is spyware by that standard, and one Reddit thread ends the
brand. Prompts are also low-grade ore: what we want is not what users typed, it is
**what surprised their Claude** — which footage property broke which assumption,
and what fixed it.

**Mechanism: the skill file is a behavioral contract.** Their Claude follows our
skills the way our Claude follows this repo's. So behavior is written into skill
text, not enforced.

1. **The field journal.** Skills instruct: whenever a script fails, a workaround is
   found, or footage does something unexpected, write a structured gotcha entry
   locally — symptom, cause, fix, **no customer content**. This is our `journal.md`
   discipline shipped as product behavior, and it has **local value first** (their
   own future sessions read it). People do not maintain telemetry; they do maintain
   something that helps them next Tuesday.
2. **Local-branch discipline.** Never edit plugin scripts on `main` — commit to
   `local/patches` with the why in the message. **Needed regardless of learning**,
   because it solves a product-health problem: uncommitted drift makes `git pull`
   clobber or refuse. Branch + rebase means their patches survive our releases and
   Claude can drop a patch when upstream ships the real fix. Clean, attributed,
   explained diffs on every machine are the side effect.
3. **`/contribute`** — Claude assembles the local-branch diff, the matching field
   journal entries, and a scrubbed report of what happened (an agent is the best
   telemetry redactor ever built: "Hebrew captions broke RTL line-wrap" carries
   zero client information). **The user sees the exact payload before it goes.** On
   yes, it POSTs to a small intake endpoint and lands as an issue/PR in our private
   triage repo.

**Why an endpoint and not "push a branch to the shared repo":** every pro customer
can read the mirror, so per-customer branches there would expose customer A's
workflow to customer B. Cross-customer leakage is the same betrayal as phone-home,
one hop removed. GitHub-native customers can fork-and-PR as an alternative.

### Commits: the embedded need, and how to get the push

Committing is not telemetry we sneak in — it is a **functional requirement of
updating software the user has modified**. So the discipline sells itself, and the
line is clean: **commits serve them, the push serves us.** Commits can be
automatic; the push must stay consented, because diffs can embed client content (a
phrase anchor like `"where he says 'the Q3 numbers'"` is NDA material sitting in a
manifest).

Three instruction layers, strongest first:

1. **Hooks — for what must always happen. Do not instruct the model; execute.** A
   `Stop` hook fires when Claude finishes a turn: if `git status --porcelain` in
   the plugin root is dirty → ensure we are on `local/patches` (never main) →
   `git add -A && git commit`. Ten lines of PowerShell, registered as
   `"Stop": [{"hooks":[{"type":"command","command":"${CLAUDE_PLUGIN_ROOT}/hooks/autocommit.ps1"}]}]`.
   Every session ends clean; the model was never asked to remember anything.
2. **Session-start context injection — our CLAUDE.md equivalent.** A plugin cannot
   edit the user's CLAUDE.md, but `SessionStart` stdout *is* context: "you are
   carrying 3 local patches on `local/patches`; upstream has 2 updates; script
   changes auto-commit; propose `/contribute` when a fix looks general." Plus the
   real `CLAUDE.md` written into the studio at setup — belt and suspenders, both
   visible to the user.
3. **Skills — the judgment half.** What makes a good commit message, what belongs
   in the journal, when a fix is upstreamable vs. machine-specific, how to scrub a
   diff. Layer 1 captures; layer 3 decides quality.

**Getting the push** — timing, self-interest, reward, never automation:

- **Timing:** the hook sees unpushed commits and injects a nudge, so Claude asks at
  the moment of pride, payload assembled: "I fixed the rotation-tag handling today
  — send it upstream? Here is exactly what would be sent." One keystroke.
- **Self-interest, honestly stated:** every local patch is **rebase debt** the
  customer maintains through every update, forever. Claude can quantify it: "you
  are carrying four patches; two are general — upstream them and they become my
  problem instead of yours." A genuinely good deal, not a favor.
- **Reward:** changelog credit by name, and a free month per merged gotcha. Nearly
  free, converts customers into evangelists.

**Ship `check-script.py` and the check suites as part of the product**, and have
the skills hold their Claude's new scripts to our conventions. Contributions then
arrive pre-linted and pre-tested — mergeable rather than a triage burden — and
brand-new scripts (whole capabilities we never thought of) become the biggest
prize in the intake, not the messiest.

### Consent architecture

| tier | what | default |
|---|---|---|
| 0 | Support interactions ("run the doctor, paste the output") = a consented machine census. Discord users narrate their own edge cases. Design-partner beta customers on explicit "we watch you work" terms — the highest-fidelity learning available, and ~10 of them cover most of the gotcha distribution. | always |
| 1 | Update-check ping: plugin version, OS, GPU model. Documented in one sentence, off-switch provided. | on |
| 2 | Session summaries and `/contribute`. Asked once at `/setup`, **and still previewed at every send**. | opt-in |

Two-layer consent plus readable payloads is also marketing: **"telemetry you can
read."** It turns the NDA positioning from an obstacle into proof.

### Our side of the loop

Intake → triage → **generalize** (a customer's fix is usually too specific; the job
is turning the instance into the principle) → regression coverage in the `check-*`
suites → release → **credit**. Note the symmetry: those suites exist because *our*
Claude writes scripts; they are exactly the review gate for changes written by
*their* Claudes.

Compounding: weird footage → field journal → `/contribute` → generalized fix →
release → renewal justifies itself. That is §5's update stream with its supply
chain attached.

## 10. The thin client (phase 2)

**Technically closer than it looks, because you have been the thin client all
along.** You never touch ffmpeg or timelines — you type prose, the agent plans,
prices, renders and reports. So the UI that must move to the server is a chat box
and a preview player, not a video editor. That is the part that kills most
"desktop tool in the cloud" projects.

What is already server-ready without having been called that: everything is
**manifest-driven** (each request is a small JSON edit plus a re-run — an API, not
a UI); every script **prices and verifies before spending** (the exact guardrail
needed before an unwatched agent spends GPU money on a customer's file);
`project.json` + `journal.md` are already a **multi-tenant job model** with an
audit log; `_progress.py` sidecars already feed a progress bar; and the brain runs
headless via the Claude Agent SDK on Linux with the same skills and scripts.

**The one honest tax: moving bytes.** A 10-minute 4K phone take is 2–4 GB. Three
dodges, in order of power:

1. **Record in the client.** For demo videos the footage need not be uploaded if it
   is *born* in the client — browser screen+camera capture streams to storage while
   recording. Upload time: zero.
2. **Proxy-first.** All the thinking (transcription, sync, cut planning, shot
   detection) needs a 720p proxy, not the master. Client makes a ~200 MB proxy
   locally, uploads in a minute or two, the editing conversation starts immediately
   while the master trickles up. By approval time the master has arrived and the
   final NVENC pass runs at full res.
3. **Decisions travel light.** Manifests, cut lists and caption files are
   kilobytes; downstream egress is cheap on zero-egress storage.

**Architecture:** client (record / drop / chat / watch drafts) → API + job queue →
**two worker pools** → storage. The pools are the key split: **brain workers**
(cheap CPU boxes running the agent on proxies — ~85% of wall time) and **render
workers** (a few GPU boxes running the same scripts at full res, ~15× realtime).
They scale independently and the agent never holds a GPU while it thinks. Two
clients on one API: a **web client** for people who should never see Python, and
the **Claude Code plugin as a client** for developers (manifests up, mp4 down).

**Customer experience:** drop footage, get a link ten minutes later to a draft
*with the editor's notes* — "cut 49 s of pauses, went full-frame where the screen
froze, ended on 'Desktop Sharing' because you turn away right after." Reply in
plain words; a new draft arrives minutes later. The debug-overlay commentary
becomes the customer-facing trust artifact.

**Economics per 30-minute film:** a few dollars of Claude tokens for the decide
step, well under a dollar of GPU (rented ~$0.50–0.90/hr, or our own rig at first),
cents of storage. Roughly **$3–10 COGS against $30–300 of price**. The queue, not
the margin, is what needs tuning.

**Gap list:** Linux port (Python + ffmpeg/NVENC + faster-whisper + ONNX all run
there; it is paths and the `_env` bootstrap — days, not months), resumable uploads
to object storage, job queue, minimal web front, Stripe. The genuinely new
engineering is the **proxy-first conform** (plan on proxy, render on master,
assert frame counts — the conform-before-measuring discipline already covers the
dangerous half) and an **escalation queue**: when a script's assertions refuse a
weird file (bad rotation tag, VFR, mush sync peak), the job pauses for a human
instead of shipping garbage. Early on that human is us — which is also how the
gotcha library keeps compounding.

**Sequence:** one pipeline headless on one Linux GPU box end-to-end with no human
(1–2 weeks) → upload + chat relay + draft player → browser capture → payments.
Ship the multicam/demo pipeline first; captions and shorts come nearly free as the
free tier, being single-file and fully automatic.

## 11. Distribution tactics

- **The benchmark write-up** — "we rebuilt professionally edited films from their
  raw tapes and re-cut them frame-for-frame." HN-front-page shape, costs nothing.
- **The debug-overlay video** — an AI editor that *explains every cut on screen*.
  Nobody has that; it is inherently watchable, and it is a marketing asset
  disguised as a debug feature. Make it a series.
- **The badge as a viral loop** — free tier default-on, paid opt-out. Typeform's
  mechanic.
- **Dogfooding, always** — our own channel runs entirely on the tool, with the
  standing line "this video was edited, captioned, dubbed and uploaded by the thing
  it is about." Publish in three languages; every dub is content *and* demo.
- **Live theater** — edit an attendee's raw take on stage at a dev conference.
  Bring footage, leave with a film.
- **Marketplace position** — be *the* video plugin early. Category ownership is
  cheap right now and good skills get amplified.

## 12. Risks

- **Platform dependency.** Skills/plugins are a channel, not a moat. Keep the
  audience (channel, email list, Discord) independent of it. Mitigation: manifests
  and scripts are plain files another agent could operate if the ground shifts.
- **The stream must visibly live** (§5). This is the model's single point of
  failure.
- **"Works on my footage."** Real, and the reason the design-partner/service phase
  precedes self-serve.
- **Windows + NVIDIA lock.** Fits the podcast/YouTube-economy editor beachhead;
  excludes Mac/FCP until a VideoToolbox port earns its keep. Serve Mac via cloud
  render first.
- **Support tail on heterogeneous machines.** Mitigations: pinned ffmpeg, the
  doctor, version stamps in `project.json`.
- **Audience assumption unproven.** §2's three-step validation exists for this.

## 13. Build list (local-first SKU)

1. Clean-VM dry run of the whole install path — **do this first**.
2. Split public/pro marketplace repos; CI dev → mirror on tag, gated by check
   suites.
3. `/setup` skill (doctor + repair + models + keys + **sample render**).
4. Pinned ffmpeg build, hosted and checksummed.
5. `_workspace.py` — studio resolution via flag → env → pointer file.
6. Studio scaffolding: `CLAUDE.md`, `.claude/settings.json` permissions, git init +
   ignore pattern, config shadowing.
7. `SessionStart` hook: computed map injection, studio routing, update notice,
   patch/push nudges.
8. `Stop` hook: auto-commit to `local/patches`.
9. `/update`: fetch → rebase → semantic conflict resolution → drop absorbed
   patches → run checks.
10. `/contribute`: diff + journal + scrubbed report, previewed, POSTed to intake.
11. Timeline exporter (FCPXML/EDL/OTIO) from existing cut lists — **the one new
    capability the editor audience requires**.
12. Version stamp in `_project.record()`; skill-readable changelog.
13. Trigger-phrase battery as a release gate.
14. Stripe checkout + webhook worker (invite/revoke, welcome email).
15. Launcher: `instacut` on PATH + drag-and-drop desktop shortcut.
16. Landing page fronted by the debug-overlay video; Discord.

## 14. Open questions

- **Name.** The brief changed: this is not a "shorts/cut" tool, it is an
  editor-as-employee. That reopens the namespace the earlier search exhausted.
- **Will you be the face?** Content-led distribution needs one. If not, lean harder
  on the benchmark/HN and partner-led channels.
- **Hours per week available** — caps the design-partner/service load.
- **Price point** — $249 vs $499/yr; test against the editor cohort, remembering
  their all-in includes a Claude subscription.
- **Service tier, yes or no?** A productized "send raw footage, get a finished
  video in 24h" at $300–500/video or $1.5–3k/mo retainer proves willingness to pay,
  generates case studies and harvests edge-case footage — but it costs the hours
  in question above.

## Verify before relying

Competitor prices and business specifics quoted here (AutoPod, Screen Studio,
Tella, the WordPress plugin economy, JetBrains' fallback licence) are from general
knowledge as of early 2026 and are load-bearing for positioning, not for
engineering. Check them before they go on a pitch deck. The plugin/marketplace and
hook mechanics should be confirmed on the clean VM rather than trusted from this
document.
