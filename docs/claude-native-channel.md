# Is the Claude-native channel real, and can we market into it repeatedly?

**Written** 2026-09-01, same research session as `docs/shorts-strategy.md` and
`docs/shorts-gtm-playbooks.md`. **Status:** research + recommendation.

Two questions, asked in this order for a reason: **is there genuine pull for
Claude Code skills, plugins and Claude-native apps** — and, if we build on that
channel, **is there a way to market into it more than once?** A channel that
converts on launch day and never again is a lottery ticket, not a go-to-market.

---

## The one-page version

**Pull: yes, and it is not close.** Claude Code went $0 → $1B annualized in six
months and is reported at roughly **$8B annualized by May 2026**, holding ~54% of
the AI coding market and the top spot in the Pragmatic Engineer's February 2026
developer survey. The shelf is instrumented in public: `claude.com/plugins`
displays install counts, and the top entries read **1,134,112** (Frontend
Design), **1,009,371** (Superpowers) and **438,525** (Code Review). Anthropic's
official directory repo carries **35.8k stars and 4.0k forks**. r/ClaudeAI is at
~1.1M members. Million-install third-party plugins exist; this is a real
distribution surface, not a hopeful one.

**But the supply side is saturated and mispriced.** One directory alone indexes
**23,600+ skills, 12,800+ MCP servers and 2,700+ marketplaces** against ~380k
monthly visitors, ranking by install count and stars, and selling ad placements.
Paid skills exist at **$3.99–$14.99 each** (Claude Protocol, KissMySkills). The
lesson is a pricing one: **ship "a skill" and you will be priced like clip art.**
The official directory tells the same story from the other end — ~100 plugins,
about a third Anthropic's own and the rest **partners with real products**
(GitHub, Playwright, Supabase, Figma, Vercel, Linear, Sentry, Stripe, Firebase).
It is a partner shelf, not a hobby shelf, and that is the slot to aim at.

**Hacker News: a real, recurring surface — but it rewards the write-up, not the
listing.** Show HN has been full of Claude Code skills and plugins, and the
recurring threads ("Claude Code as a daily driver: CLAUDE.md, skills, subagents,
plugins, MCPs") converge on exactly our thesis: teams want repeatable workflows
encoded as skills. Plausible's $1M ARR came from HN front pages earned by
*articles*, not by product pages. Our HN asset is the frame-scored benchmark,
not the plugin listing.

**Product Hunt: thin. Do not build on it.** Searching the category surfaces
directories *of* skills and skills *about* Product Hunt — not Claude-native apps
winning Product of the Day. It is a one-shot, low-signal launch here. Use it once
if it is free; never plan around it.

**The repeat problem, and the answer.** A single-purpose shorts app can be
launched once. This repo is **eight discrete, demoable jobs** — captions, shorts,
dub, multicam PiP, multicam switch, silent-screencast redaction, name
labels/cards, publish — each with its own demo, its own listing, its own audience
and its own write-up. That is the structural answer: **one pipeline, one launch,
repeatedly**, on top of a release cadence the business model already requires for
renewals (`product-strategy.md` §5). Two content lines run in parallel forever:
the **benchmark series** (rebuild a channel's film from rebuilt tapes, score it
frame by frame — the `video-channel-audit` skill already does this, six films
deep) and the **debug-overlay series** (an editor that explains every cut on
screen). Both double as sales: each benchmark names a channel we could approach.

---

## 1. The demand evidence, with confidence marked

| fact | figure | confidence |
|---|---|---|
| Claude Code revenue | $0 → $1B annualized in 6 months; ~$2.5B (Feb 2026) → ~$8B (May 2026) annualized | **low-medium** — stat-aggregator sites, not filings; directionally consistent across several |
| Market position | ~54% of the AI coding market; most-used AI coding tool in Pragmatic Engineer's Feb 2026 survey (906 devs, 46% "most loved") | **medium** |
| Usage depth | ~4% of all public GitHub commits; average user ~20 h/week in the tool | **low-medium** |
| Official directory | `anthropics/claude-plugins-official`: **35.8k stars, 4.0k forks**, 949 issues; submission form; "Anthropic verified" badge = extra quality/safety review | **high** (read directly) |
| Shelf composition | ~100 plugins, ~33 Anthropic + ~68 partner (GitHub, Playwright, Supabase, Figma, Vercel, Linear, Sentry, Stripe, Firebase) | **medium** |
| Install counts | Frontend Design 1,134,112 · Superpowers 1,009,371 · Code Review 438,525 | **high** (shown on the directory) |
| Community scale | claudemarketplaces.com: 23,600+ skills, 12,800+ MCP servers, 2,700+ marketplaces, ~380k monthly visitors, ranking by installs/stars/usage, paid placements sold | **medium** (self-reported) |
| Audience | r/ClaudeAI ~1.1M members; ecosystem newsletters at 15k+ subs publishing "best Claude Code skills" rankings; Udemy agentic-AI course at 69k students | **medium** |
| Paid skills market | KissMySkills 1,000+ skills at $14.99; Claude Protocol 501 at $3.99; Agent37/Agensi handling payments and security scanning | **medium** |

**Read of it:** the demand side dwarfs the shorts category (`shorts-strategy.md`
§1 put the whole clipping-SaaS category at maybe $50–100M ARR; the plugin shelf
sits on top of an $8B-annualized tool). The scarce resource is not users — it is
**attention against 23,600 skills**, and **a price above clip-art**.

## 2. The three things this changes about how we package

1. **We are a partner-shelf product, not a skill.** The official directory's
   non-Anthropic entries are companies with products behind them. Package as the
   studio (plugin + scripts + pinned ffmpeg + models + support), listed once, with
   the skills as its *contents* — never sold as loose skills at $14.99.
2. **The plugin `name` is immutable once published.** The directory README is
   explicit: `name` can never change, only `displayName`. `product-strategy.md`
   §14 lists the name as an open question — it now has a hard deadline, which is
   *before the first publish*, not after traction.
3. **Skills load lazily** (name first, body only when the task matches). That is
   what makes the "one pipeline, one launch" engine technically viable: we can
   carry eight pipelines' worth of craft without a context tax on every session.
   It also raises the stakes on the description lines — they are the routing
   table, and `product-strategy.md` §8 already makes testing them a release gate.

## 3. Hacker News and Product Hunt, specifically

**Hacker News — yes, recurring, but earn it with an artifact.**
Show HN has carried a steady stream of Claude Code skills and plugins; the
long-running discussion threads are about where to store agent-operating
knowledge and how to encode repeatable workflows — our exact subject matter.
Plausible is the template: HN front pages from *written pieces*, producing record
traffic and signup days, on a privacy-first open-source positioning nearly
identical to ours.

What we would post, in order of strength:

- **"We rebuilt six professionally edited films from their raw tapes and re-cut
  them frame-for-frame — here are the scores, including where we lose."** The
  honest failure numbers (stage 2 at 45–50% where the editor does not follow the
  voice) are what make it credible on HN.
- **"An AI editor that explains every cut on screen"** — the debug overlay.
- **"Why a user-level PYTHONPATH segfaulted Python and what it taught us about
  shipping local AI tooling"** — the gotcha library's origin story is the
  HN-native genre.

**Product Hunt — thin, one-shot.** The Claude-native launches that surface are
directories *of* skills and skills *about* PH. Treat it as a free coupon: launch
once, expect a spike and no compounding, and never let it set the roadmap.

## 4. The repeatable engine — six surfaces, ranked by durability

1. **Ship-and-say-so.** The directories rank by installs and usage; the ecosystem
   newsletters and YouTube channels hunt for what is new and updated. A weekly-ish
   release with a written changelog *is* the marketing. **This is the same
   requirement `product-strategy.md` §5 identified for renewals** — one cadence
   serving retention and acquisition. Its single point of failure is also shared:
   three quiet months and both die.
2. **One pipeline, one launch.** Eight jobs already exist; each is a launch with
   its own demo, listing keywords, audience and write-up. Then each new pipeline,
   template pack, brand pack and NLE export target is another. A single-purpose
   clipper cannot do this — it has one story and must repeat it louder.
3. **The benchmark series.** `video-channel-audit` industrialises it: take a
   published multicam film, rebuild the tapes, re-cut, score frame by frame,
   publish the gaps honestly. Six films in. Every new one is a post, a regression
   test, and a warm introduction to that channel. Content that is also QA is
   content we will actually keep producing.
4. **The debug-overlay series.** Watchable by construction, unique in the market,
   and free — it is a debug feature we already ship.
5. **Dogfooding.** Our own channel edited, captioned, dubbed and uploaded by the
   tool, with the standing line saying so; three languages via the dub, so every
   localisation is both reach and demo.
6. **Paid placement.** The directories sell prominence. A knob to test with $200,
   never a strategy.

**What we deliberately do not do here:** buy attention in the creator-tool
paid-acquisition war (`shorts-gtm-playbooks.md` §2), or run affiliate/free-tool
SEO funnels that require a 60-second self-serve install we do not have.

## 5. Metrics that mean something on this channel

- **Installs that reach a rendered file.** Installs are the public leaderboard and
  compound into ranking, but a plugin installed and never run is a vanity number.
  Instrument the first render, not the install.
- **Second-session rate.** The honest test of whether a Claude-native tool is a
  toy: did they come back with their own footage?
- **Conversations booked** off a benchmark post. Stars are not evidence
  (`shorts-gtm-playbooks.md` §10).
- **Time-to-first-render on a stranger's machine**, from the clean-VM run. Every
  channel above leaks through this number.

## 6. Risks specific to this channel

- **It is a channel, not a moat** (`product-strategy.md` §12). Keep the list,
  Discord and channel independent of the shelf.
- **Discovery saturation.** 23,600 skills and 2,700 marketplaces already. Being
  *the* video plugin is available now precisely because nobody has taken it; that
  window is measured in months.
- **The shelf may formalise into pay-to-play.** Directories already sell ads;
  partner shelves historically drift toward paid placement.
- **First-party risk.** Anthropic ships fast and Cowork is already a second
  surface ("Works with Cowork" filtering on the directory) aimed at non-developer
  operators — which is, notably, *our editor audience without a terminal*, and
  therefore an opportunity before it is a threat. What would not be recoverable is
  a first-party video pipeline; the defence is the gotcha library and the
  benchmark, never the code.
- **Skill-priced expectations.** A market where skills sell at $3.99 will resist a
  $499/yr studio unless the packaging, the install experience and the support
  visibly belong to a different category.
- **The cadence is load-bearing twice over.** If shipping stalls, the channel and
  the renewal argument fail together. Decide honestly whether a weekly release is
  sustainable *before* betting both on it.

## 7. What to do, in order

1. **Name it now** — the plugin name is immutable, and every listing, URL and
   directory entry inherits it.
2. **Clean-VM install run** (already build-list item 1). Nothing below survives a
   broken install.
3. **Publish the free plugin** (captions + shorts) and get listed on the community
   directories immediately; submit to the official directory once the check suites
   and the VM run make the quality claim defensible, aiming for the *verified*
   badge rather than a bare listing.
4. **Set the cadence and announce it** — a release most weeks, each with a written
   changelog entry that is also a post. This is the engine; everything else is
   fuel.
5. **Start the two serial content lines** — one benchmark write-up and one
   debug-overlay video per month, both of which fall out of work we do anyway.
6. **Launch each pipeline separately** rather than announcing "a video studio"
   once. Eight launches beat one.
7. **Instrument first-render, not installs**, and review at 90 days against
   `shorts-gtm-playbooks.md` §11's kill criteria.

## Verify before relying

Claude Code's revenue and market-share figures come from stat-aggregator blogs,
not from Anthropic; treat them as directional. Install counts, the official
directory's star/fork counts, the immutable-`name` rule and the submission/verify
process were read directly off `claude.com/plugins` and
`anthropics/claude-plugins-official` on 2026-09-01 and are the most reliable
numbers here — and the fastest-moving. claudemarketplaces.com's 380k monthly
visitors and its 23,600/12,800/2,700 counts are self-reported by a site that also
sells placement. Paid-skill prices were read off marketplace round-ups, not
checkout pages. The Product Hunt read is an absence of evidence rather than
evidence of absence: it means no Claude-native app launch was prominent enough to
surface, which is itself the argument for not planning around it.

**Sources:** claude.com/plugins; github.com/anthropics/claude-plugins-official;
claudemarketplaces.com; Claude Code statistics round-ups (gradually.ai,
serpsculpt, aeovision, businessofapps); Pragmatic Engineer survey coverage;
claudecamp.ai and thepromptshelf.dev directory guides; agent37.com and
kissmyskills.com skill-monetization write-ups; jeremylongshore/tons-of-skills
marketplace; Hacker News threads on Claude Code as a daily driver and on Agent
Skills; Product Hunt listings for Claude Skills Hub and Agent Skills;
r/ClaudeAI subreddit stats; ecosystem newsletters (buildtolaunch, sidsaladi,
boringbot).
