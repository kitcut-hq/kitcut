# What OpenSEO teaches KitCut

**Written** 2026-09-24, after installing OpenSEO's Claude Code plugin in a cloud
session and reading its repo (`every-app/open-seo`, plugin v1.0.0).
OpenSEO has already shipped what `docs/product-strategy.md` still plans: an
open-source tool sold as a Claude Code plugin, with a hosted service behind it.
This note records what it does, and what KitCut should copy or avoid. It has
findings only. Nothing here has been built yet.

## 1. Making it work: the install is a prompt, not a script

- **The installer is a pasted prompt that the agent runs.** The user pastes six
  numbered steps into the agent: check the agent, install the plugin, fall back
  to MCP + skills, sign in, reload and verify, hand off. The agent reads the
  client's own `--help` and docs to fill in the details. So a single text covers
  Claude Code, Codex, Cursor and "other agents". A `setup.ps1` could never do
  that. The prompt also lives in the repo as an internal skill
  (`.agents/skills/setup-openseo`), so it is versioned like code.
- **It keeps three states apart: installed, signed in, verified.** The prompt
  says that a connected server does not prove this session can call the tools,
  and it says "never claim verification before the free reads succeed". This is
  the check-env / render-status idea applied to onboarding. Our `setup` skill
  should report these three states separately.
- **Verifying costs nothing.** `whoami` and `list_projects` are free reads.
  Setup is told not to create anything or spend credits. It is the same rule as
  our `--list` and `--dry-run` modes, applied to the first five minutes.
- **The handoff has a fixed format**: at most 140 words, then a *Status*
  section, then a *Next* section with one recommended first workflow. The
  agent's last message works as a product surface.
- **Secrets never pass through chat or the repo.** OAuth comes first. An API
  key goes into the client's secret store or an environment variable. KitCut's
  `ELEVENLABS_API_KEY` and YouTube grant should follow the same rule, stated in
  the same words.
- **In a cloud container the install does not persist.** Here the plugin
  installed at user scope, which disappears with the container. OAuth also needs
  a browser. Any plan that says "customer runs `/plugin install`" needs a
  persistence answer for claude.ai/code users, such as project-scope settings
  or an environment setup script.

## 2. The concept: data plus judgement, sold to the customer's agent

- **The pitch is one sentence: "Without good data, your agent gives generic
  advice."** The customer already has the model. OpenSEO sells the input that
  the model cannot get on its own (DataForSEO, crawls, Search Console) and the
  skills that turn that input into a decision. KitCut's version would be:
  *without our pipelines, your agent can only describe an edit; with them, it
  renders one.*
- **One source of truth, two consumers.** The MCP server is the "hands"
  (tools). The skills are the "judgement": when to call which tool, what counts
  as evidence, how to write the report. The same skill files serve Claude Code,
  Codex and Cursor.
- **The skills read like our docs.** `seo-audit/SKILL.md` gives rules with
  reasons: "a failed lookup is unknown, not 'not in the first 20 results'",
  "provider traffic is an estimate, not measured visits", "a ranking claim needs
  a live check made during this audit". These are gotchas encoded as
  instructions, the same as our `## Gotchas` and known-issues register. It
  suggests our skill files are the right shape.
- **Project memory is a server-side store the agent reads on every run**
  (`get_project_context` / `update_project_context` plus an append-only
  research log). Spec 0010 describes the problem they had before it: memory
  scattered across the chat agent, local skill folders, and results that were
  thrown away, so every surface re-interviewed the user and paid research was
  bought twice. Our `project.json` + `journal.md` is the same idea, kept locally.
  Their "research log so the agent doesn't re-buy research" is the equivalent
  of our cached OCR and transcripts, applied to money.
- **Skills fail small and suggest the next skill.** Example: "If
  business_overview is empty, infer it, confirm in ONE question, write it back,
  continue. Suggest seo-project-setup at the end; never front-load the
  interview." Our pipelines should ask for the smallest missing input in the
  same way, instead of refusing until a full manifest exists.

## 3. Distribution

- **The marketplace is the git repo itself.** `.claude-plugin/marketplace.json`
  sits at the root of the open-source app repo and points at
  `./plugins/openseo`. The install is two commands:
  `/plugin marketplace add every-app/open-seo` and
  `/plugin install openseo@openseo`. This matches our §"free marketplace" plan
  and shows it works without a separate repo.
- **One plugin folder carries three client manifests.** `.claude-plugin/`,
  `.codex-plugin/` (with `interface.defaultPrompt` starter prompts, privacy/ToS
  URLs and a category) and `.cursor-plugin/`, plus a ChatGPT app submission
  JSON at the root. The skills are written once and shipped to four stores.
- **Codex copies the plugin folder and skips symlinks**, so the skills are
  real copies made by `scripts/sync-plugin-skills.mjs` from
  `.agents/skills/*`. CI re-runs the sync and diffs the result, so a stale copy
  fails the build instead of shipping. We would hit the same problem the first
  time we try to symlink `scripts/` into a plugin root.
- **Public skills and internal skills sit side by side**, separated by
  `metadata: internal: true` and an explicit allow-list in the sync script. The
  setup prompt says "do not copy internal repository skills". Our maintainer
  skills (`check-script`, `video-channel-audit`) need the same separation
  before any plugin ships.
- **The business model is open source, self-host with your own key, or $10/mo
  hosted.** Self-hosters pay DataForSEO directly. The hosted plan sells
  convenience plus metered data. That is close to our "sell the stream, not the
  snapshot" argument, except that their cost of goods is not zero.
- **Content marketing is a library of expert-quote articles that teach the
  habit the product needs.** One example: "Skills, memory and the trace: make
  the good run repeatable". The articles sell the workflow, and the product is
  the obvious way to follow it.

## 4. Eye-opening

- **The installer can be pasted into any agent, including one whose name the
  vendor does not know.** The agent is told to identify itself, read its own
  docs, preserve other integrations, avoid duplicates, and ask the user only
  for what it cannot do. That is a cross-agent installer with no code in it.
  KitCut's install today is a PowerShell script plus a skill. A pasted
  "Set up KitCut in this agent" prompt could cover Claude Code, Codex and
  Cursor for the cost of writing one document.
- **They evaluate skills like code.** `.agents/skills/evaluate-skill` runs a
  candidate skill in fresh, isolated sessions that see only the skill file, a
  one-line brief and a locked-down local MCP. It includes a holdout site. It
  scores the reports that come back. This is our "measure a proposal before
  adopting it" rule, applied to the prompts themselves. Our skills have never
  been evaluated this way. `claude plugin eval` now exists for exactly this.
- **The project is written for agents first.** `AGENTS.md`, numbered specs
  with status lines ("Proposed… Update: what shipped is…"), runbooks, and a
  `papercuts` skill. The specs record where the shipped code diverged from the
  plan, which is the discipline our journal asks of us.
- **Their onboarding "agent" is not an agent loop.** Spec 0005 says it is "a
  guided pipeline narrated live": deterministic steps, then one LLM call at the
  end. The agent-like feel comes from the streaming, not from autonomy. Our
  `screencast-pipeline.py` has the same shape and could be presented the same
  way.

## What to do with this

The candidates, in the order they pay off. None is started:

1. Write a "Set up KitCut in this agent" prompt as an internal skill, modelled
   on OpenSEO's six steps. It would report installed, env-ok (`check-env.py`)
   and verified (a colour-bars render) as separate states.
2. Put `marketplace.json` at the repo root and add a `plugins/kitcut/` folder
   with a sync script plus a CI diff. Mark maintainer skills internal.
3. Add skill evaluations: fresh session, frozen footage, scored output. Compare
   before and after any skill edit.
