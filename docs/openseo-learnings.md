# What OpenSEO teaches KitCut

**Researched** 2026-09-24 from openseo.so, its public repo
(`github.com/every-app/open-seo`, MIT, v0.1.9, cloned and read), its own docs,
specs and blog, and two third-party write-ups (sources at the end). **Status:**
findings, plus a recommendation for each one. Nothing in here is built yet.

**Why this project in particular.** `docs/product-strategy.md` §2 says the
whole KitCut plan started from one observation: SEO specialists had become
heavy Claude Code users, and "Claude Code is moving from developers to
operators." OpenSEO is a product built for exactly those people, and it is a few
months further down the road we have planned. It sells *data and workflows
to the customer's own agent*. Our plan sells *scripts and craft to the
customer's own agent*. Where it has already tested something we have only
planned, we should use its result instead of reasoning it out again.

---

## The one-page version

| | OpenSEO | KitCut (as planned) |
|---|---|---|
| Brain | the customer's agent (Claude Code, Codex, Cursor, ChatGPT) | the customer's Claude Code |
| Judgment | 10 skills in a plugin | the skills + gotcha library |
| Hands | a **hosted** MCP server (`app.openseo.so/mcp`, OAuth) | `scripts/`, **local** |
| Muscle | DataForSEO, paid **per call** | the customer's GPU, **free per call** |
| Code | MIT, whole thing, including the hosted app | private dev repo, public free plugin, private pro mirror |
| Revenue | $10/mo = $10 of credits, then a **28 % markup on data**, which the README states | $249–499/yr licence for the update stream |
| Install | none (remote MCP) or `docker compose up` | Python + ffmpeg + GPU driver, done by `/setup` |

The most important difference is that **OpenSEO has something to meter and
we do not.** Every useful thing it does calls a paid API, so it can charge for
convenience with a transparent markup, give everything else away, and still
make money. Our muscle is the customer's own GPU, so there is no meter, which
is why our strategy has to sell the update stream instead. Most of the
lessons below come from that one fact.

---

## 1. Making it work — engineering patterns worth copying

**One repo, every agent host.** The plugin lives in `plugins/openseo/` and
comes with a manifest for each host: `.claude-plugin/plugin.json`,
`.cursor-plugin/plugin.json`, `.codex-plugin/plugin.json`, and a
`chatgpt-app-submission.json` for the ChatGPT app directory. A root
`.claude-plugin/marketplace.json` makes the repo itself a Claude Code
marketplace. Skills are also installable one at a time with
`npx skills add every-app/open-seo --skill <name>`. The skills the product
ships (`plugins/openseo/skills/`) are kept apart from the skills used to
develop it (`.agents/skills/`, `.claude/skills/`).
*For us:* our §7 describes the Claude Code marketplace only. Covering Codex
and Cursor costs only a manifest each, as long as the skills do not depend on
anything specific to Claude Code. Keep the skills we ship separate from our
dev skills from the start: `check-script`, `video-channel-audit` and the
benchmark harness are ours, not the customer's.

**Test the skill, not just the code.** Their `evaluate-skill` runs a candidate
skill in fresh, isolated `codex exec` sessions. Each session gets a frozen copy
of the skill (hash recorded), a new project seeded with a one-line brief, a
gateway that allows only a fixed list of MCP tools, the **same neutral prompt
for every variant**, and a **holdout site**. It then compares the reports
those sessions produced.
*For us:* this is the biggest gap. Every `check-*.py` tests the scripts; nothing
tests whether `video-shorts` or `video-tighten` still leads a fresh Claude to
a good cut. We already apply this rule to the switcher (a held-out segment is
"the only thing that tells a result from a fit"). Apply it to the skills too:
a frozen skill copy, a fresh session, a fixture project, and the score should
be something we already compute (`check-caption-space`, the `--list` runtime,
`compare-videos.py`).

**Make the metered path the easiest path** (their spec 0002). Every DataForSEO
call goes through one client. The client checks the balance before the call and
records the cost the *provider actually reported* after it. Calling a raw helper
from feature code "should be treated as a billing bypass."
*For us:* this is the same idea as `_encode.py` and `check-script.py`'s spend
check. The things we pay for (ElevenLabs characters, YouTube quota, and cloud
render time in phase 2) should go through one wrapper in the same way, so the
free-mode requirement and the future meter both have one place to live.

**Error messages are addressed to the agent.** The reports spec says so
explicitly: "Error messages read as instructions, because agents see them
verbatim." Our refusals mostly work this way already (the doctor names the
cause). Make it a `check-script` judgement item.

**A papercut log, written at the moment it happens.** `.agents/PAPERCUTS.md`
holds small friction in the repo itself (a flaky command, a misleading error,
a stale pointer). Agents append to it as they hit it and keep working. Fixes
happen in a separate pass the user asks for. `docs/known-issues.md` covers
product limits, and this would cover repo friction. It is cheap, and it feeds
the gotcha library, which is the thing §3 says we own.

**Public design records, with the alternatives that lost.** `specs/00NN-*.md`
state what a feature does, how it works, and the alternatives considered and
why each one lost. They deliberately leave out costs, incidents and internal
infrastructure, and `maintainer-docs/` holds what is internal. *For us:* our
strategy and market research sit in `docs/` next to the user reference, in a
repo that `CLAUDE.md` calls public. Decide what the public free-plugin repo may
contain before it exists (see *Open questions*).

**A deliberately broken site to test against.** `badseo/` is a small site that
contains every defect the audit should find. It is their version of our
round-trip films. Our equivalent would be a committed set of small synthetic
files, each carrying one trap (a wrong rotation tag, a digitally silent track,
a VFR phone take, a Zoom `.tmp` stub), for `/setup` and the skill evals to
run against.

**Telemetry on self-hosted installs that collects failure names, not
content.** It sends counts and **the names and statuses of failed setup
checks, never values or error messages**, and nothing when the install is
idle. You opt out with `DO_NOT_TRACK=1`. *For us:* our §9 flywheel wants to
learn from strangers' machines without capturing prompts. This is a working,
published version: `check-env.py` check names and pass/fail, nothing else,
opt-out, and the policy written in the setup doc.

## 2. The concept and the paradigm

**"Without good data, your agent gives generic advice."** That line is the
whole pitch, and it is on every manifest. The product does not claim to be the
AI. It claims to be what makes the customer's AI competent. Ours in the same
form: *without our scripts, your agent hands you an ffmpeg command that drops
the audio.* Our gotcha library is the evidence for that claim.

**Advanced features become skills, not screens.** Their roadmap's *Not
planned* list says: "Keyword Gap Analysis Page — we will support this as a
skill." A planned community skill library holds the advanced workflows "so the
tool stays approachable to people new to SEO." *For us:* our core should stay
at the pipelines. Channel presets, niche workflows and a customer's house
style belong in a skill library that anyone can add to.

**Project memory, shared across surfaces** (spec 0010): one store per
project, with typed sections plus custom ones, and `updated_by` set to
`user|sam|mcp`, readable and editable by the human. They reached almost
exactly our `project.json` + `journal.md`, which is independent support that
the shape is right. Their addition worth copying is **who wrote it**. Our
journal records when something happened but not which surface or agent
wrote it.

**The agent's work ends in a saved report, not a chat reply** (spec 0012).
Every skill ends by saving one self-contained HTML page to the project, and the
agent answers with the link and a verdict. *For us:* a render already produces
a deliverable, but the *decision* behind it (why these cuts, what was removed,
which frames were blurred) lives only in the terminal. `redaction-review.py`
already works this way. Extending it gives every pipeline an edit report.

**Their "onboarding agent" is not an agent loop.** Spec 0005: "A guided
pipeline narrated live … mostly deterministic … a single LLM call at the end."
It feels like an agent because the steps stream. *For us:* this is the shape
of the thin client (§10), and it is much cheaper than an agent loop.

## 3. Distribution

**They asked before building.** The founder posted in r/TechSEO asking whether
an open-source tool built on DataForSEO would be useful, answered the
questions people raised about the data, and posted the first version **the
following week**. Later came #1 Product of the Day on Product Hunt, 15.8k
GitHub stars, and "3,000+ entrepreneurs" (their figure). *For us:* §2's plan
is to talk to five editors and post the debug-overlay video to r/editors.
OpenSEO shows that the post itself works as the validation, and that a
one-week gap between asking and shipping is normal.

**Every host's marketplace, and zero install where possible.** They are listed
in the Claude Code marketplace, the Cursor Marketplace, as a Codex plugin, in
the ChatGPT apps directory and on `npx skills`, and a hosted MCP with OAuth
means there is nothing to install. We cannot remove our install (the GPU is
the product), but the **free tier** (captions, shorts) could appear on every
marketplace with a `/setup` that does the install.

**Free tools are the SEO funnel, with a budget attached.** They run eight
single-purpose public pages (backlink checker, traffic checker, SERP
simulator…), each a search landing page, protected by Turnstile, 5
requests/IP/min, per-visitor call caps and **an atomic $100/day spend budget**
in a Durable Object that fails closed
(`maintainer-docs/FREE_TOOLS_PROTECTION.md`). *For us:* candidates that need
**no upload** fit here: a chapter auditor for any public YouTube channel
(`yt-audit-chapters.py` already does this and spends YouTube quota, so the
budget guard applies), a caption-preset previewer on a stock clip, and a
"price your pauses" calculator. Each would be a landing page for a query people
actually type.

**Shared output advertises the product.** A report's public link is wrapped in
a slim bar that says "Made with OpenSEO" with a "Try OpenSEO" button. It is the
same mechanism as our handle badge, applied to the *working document* instead
of the film. A shareable review page for a draft ("here's the cut, approve it")
would give us a second viral surface that a pro user would never switch off,
because they send it to *their* client.

**They earn from self-hosters too.** The DataForSEO link in the README carries
an affiliate tag. Someone who pays OpenSEO nothing still earns it a
commission. *For us:* ElevenLabs is the paid service our users need, so check
whether it runs an affiliate or partner programme before the free plugin
ships.

**They borrow credibility.** Their blog and strategy library are written by an
industry veteran (ex-Raven Tools, which competed with Moz) under his own name.
The founder has an About page with his face on it and does podcast interviews.
Our §11 relies on the benchmark to convince people. For a craft audience, a
named editor writing under their own name would add the human voice the
benchmark does not have.

## 4. What was eye-opening

**The buyer never used the incumbent.** Their paying customers are "not
professional SEOs … entrepreneurs doing SEO for the first time," and "they
aren't comparing against Semrush, because they've never used Semrush." The
blog's argument ("What Broke the $99 Ceiling") is that indie tools priced
under $99 died for a decade because *the price was never the constraint: the
10–20 hours a week of doing the work was*. Once agents made the work cheap,
the tool's price became the thing that matters.
*For us:* this challenges §2 directly. We bet on the **pro editor**, who
compares us to AutoPod and to their own skill. The equivalent of OpenSEO's
buyer is the **founder or small business that has never hired an editor** and
therefore compares us to nothing. That buyer owns footage and a Claude
subscription far more often than a GPU. That argues for bringing the thin
client (§10) forward, or for pricing that person out explicitly instead of by
accident.

**$10 a month, fully open source, and the markup printed in the README.**
"The way the hosted service makes money is by charging 28 % extra for every
request we make to DataForSEO." Being open, and letting anyone self-host,
works as their price ceiling, and they say so: "we cannot just keep charging
more and more." Our §5 already concluded that licence enforcement is
pointless. OpenSEO goes further and gives the code away, charging only where
a real cost passes through. Our cloud render (§10) is the one place with a
cost passing through. If it is ever built, *cost + a published markup* is a
tested model for it.

**They stopped taking PRs.** Around 60 external pull requests piled up, and the
founder "declared bankruptcy on the queue." `CONTRIBUTING.md`: no merges,
because AI-written PRs are hard to evaluate and a popular repo attracts
malicious ones. A clear issue "is worth its weight in gold," written with a
`/simple-issue-description` skill so every issue arrives in the same format,
and a demo video counts as proof the change was actually tested. *For us:* our
§9 flywheel wants customers' Claudes to push branches. OpenSEO's experience says
to take **structured reports** (a gotcha, a failing footage property) and let
our own agent write the fix. That also removes most of the consent and
security risk §9 worries about.

**Spending by an agent is the risk critics point to.** The main third-party
review's objection was "an agent holding a DataForSEO key can spend your money
in a loop with no malice at all." Our "every script prices the decision first"
rule (`--list`, `--dry-run`, the free-mode check) answers exactly that, and we
have not been advertising it.

**It is fragile in places.** The project is on version 0.1.x, one person
wrote almost every recent commit, and there are 46 open PRs against 39 merged.
Reviewers advise pinning the image tag and keeping it "off client work until
it reaches 1.0." The traction came *despite* this, which suggests being first
in a category counts for more than being complete.

---

## Recommendations, cheapest first

1. **A skill evaluation harness**: frozen skill copy, fresh session, fixture
   project, neutral prompt, holdout, scored with the checks we already have.
   It is the largest gap this comparison exposed.
2. **`PAPERCUTS.md` + a papercuts skill** for repo friction, kept separate
   from `known-issues.md`.
3. **One wrapper for every paid call** (ElevenLabs, YouTube quota), on the
   `_encode.py` model, so the free mode and a future meter share one gate.
4. **An `updated_by` on journal lines and `project.json` writes.**
5. **Manifests for Codex and Cursor** next to the Claude Code one when the free
   plugin ships, with shipped skills kept apart from dev skills.
6. **A trap-fixture set** (our `badseo`) for `/setup` and the skill evals.
7. **One free, no-upload web tool** (the chapter auditor) with a hard daily
   budget, as the first SEO landing page.
8. **Revisit §2's buyer.** Put the "never hired an editor" founder next to the
   pro editor in the week of validation conversations, and ask both whether
   they own an NVIDIA GPU.

## Open questions

- **Is this repo public?** `CLAUDE.md` says so. If it is, `product-strategy.md`,
  `market-shorts-2026.md` and this file are published strategy. OpenSEO keeps
  its design records public and its costs and incidents out of them. Decide
  which of ours belongs where before the free-plugin repo is cut.
- **Open source the scripts?** OpenSEO shows that giving away all the code
  can work when something is metered. We have no meter until the cloud render
  exists, so this stays a phase-2 question, not a reversal of §5.

## Sources

- [openseo.so](https://openseo.so/), [Why OpenSEO is open source](https://openseo.so/open-source-seo)
- [every-app/open-seo](https://github.com/every-app/open-seo): README, `CONTRIBUTING.md`, `specs/0002`, `0005`, `0010`, `0012`, `0014`, `maintainer-docs/FREE_TOOLS_PROTECTION.md`, `.agents/skills/evaluate-skill`, `web/content/marketing/{about,why-openseo,roadmap}`, `web/content/blogs/what-broke-the-99-dollar-ceiling.md`, `release-notes/`
- [Botmonster: "OpenSEO is the open source Ahrefs with a data bill attached"](https://botmonster.com/self-hosting/openseo-open-source-seo-tool-dataforseo-cost/): costs, maturity, agent-spend critique
- [CoddyKit write-up](https://www.coddykit.com/pages/blog-detail?id=513046&slug=openseo-the-open-source-seo-tool-with-15-800-github-stars-that-s-replacing-semru): star count
- [microsaasexamples: OpenSEO](https://www.microsaasexamples.com/p/openseo)
