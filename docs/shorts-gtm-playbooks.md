# How the others got users — and which plays we can actually run

**Written** 2026-09-01, same research session as `docs/shorts-strategy.md`.
**Status:** research + recommendation. That document answered *is this a market
and who pays*. This one answers the question it left open: **what did the people
who won this market actually do to get users, and which of it transfers to a
tool that requires Claude Code, Python and a GPU?**

Read with `docs/product-strategy.md` §11 (distribution tactics), which this
grounds in evidence and, in two places, corrects.

---

## The one-page version

Six playbooks built the businesses in and around this category. Ranked by what
they'd cost us and what they'd return:

| play | who proved it | needs | can we run it? |
|---|---|---|---|
| **Affiliate army** | Submagic: 10,000 affiliates, 30% lifetime commission started **30 days** after first customer, ~$1.6M of $8M ARR, ~$45k/mo paid out | a 60-second self-serve signup | **No** — not until an install is one click |
| **Free-tool SEO** | Submagic: free tool pages → peak **9M monthly visits**; every rival runs "free YouTube Shorts maker" pages | a hosted, instant, no-install product | **No** — same reason |
| **Source-platform integrations** | OpusClip ingests from Zoom, Riverside, StreamYard, Twitch, Loom, Drive + Zapier; StreamYard published a joint case study | partnerships, a cloud endpoint | **Not yet** — phase-2 only |
| **Build in public** | Screen Studio: `#buildinpublic` brought the first 10 customers; sales tracked tweet reach; 3 founders → **8,000 customers in 9 months** as a *local desktop app* | a founder willing to be the face, daily, for a year | **Yes — if somebody says yes.** Highest-return play available to us |
| **Open-source alternative** | Plausible: HN front page → record traffic/signups → $1M ARR as the *privacy-friendly open alternative*. OpenCut: 45k stars as "open-source CapCut alternative". OpenShorts: 3.8k stars, MCP server, cloud upsell at $12/mo | a public repo and a phrase incumbents can't say | **Yes** — and it is the only way to meet a free floor instead of pretending it isn't there |
| **Marketplace + tutorial channels** | AutoPod and the aescripts economy: editors find tools on aescripts / Adobe Exchange and on tutorial channels (Premiere Basics, 585k subs) — not through ads | a plugin that fits an existing tool's shelf | **Yes** — this is the editor ICP's actual front door |

Plus one emerging channel nobody has taken: the **Claude Code plugin directory**
(official directory launched May 2026 with 55+ curated plugins; the repo passed
20k stars in four days; `claudemarketplaces.com` reports ~380k developer visits a
month; 2,000+ community skills). There is no serious video plugin on that shelf.

**And one demand pool nobody is serving on our economics: the clipping economy.**
Whop Clips has ~980k members, 6,800+ clipping products, and Content Rewards has
tracked **$2.58M paid to 8,466 earners** ($887k in February 2026 alone) at
$0.20–6 per 1,000 verified views, blending to about **$0.39 per 1,000**. These
people are paid per view, produce clips in volume, and — in the words of one
guide — *"grinding Whop volume through credit-metered cloud tools hand back a
slice of every payout."* Unmetered local rendering is not a privacy pitch to
them; it is their gross margin.

**The recommendation in one line:** run **three** plays and refuse the rest —
open-source core (meet the floor), build-in-public (the only channel that ever
worked for a local desktop tool), and marketplace placement (Claude Code now,
aescripts/Adobe Exchange when the timeline export exists) — with founder-led
support as the retention layer underneath all three.

---

## 1. Submagic: $0 → $1M ARR in 3 months, $8M in 2 years, bootstrapped

The most instructive case in the category, because there was no venture money to
explain it away.

- **Founder was an affiliate marketer before this.** He launched the affiliate
  program **within 30 days** of the first customer — not as a growth experiment
  but as the plan. 30% lifetime commissions. 10,000+ affiliates. ~$1.6M of the
  $8M ARR, ~$45k/month in payouts.
- **Free tools as an SEO surface**, spiking to ~9M monthly visits.
- **The CEO personally takes 5–6 user calls a day**, and has since founding.
- **Explicitly acquisition-only** for two and a half years — activation,
  retention and referral were never deeply optimized.

**What transfers:** the last two. Founder-led support at that intensity is
available to us and is already the shape of `product-strategy.md` §9's
design-partner tier — ten customers on "we watch you work" terms is the same
mechanism, and it feeds the gotcha library as well as the relationship. The
acquisition-only focus is the *discipline* lesson: one channel, executed past the
point of boredom, beat a portfolio of five.

**What does not transfer, and why it matters:** affiliates and free-tool SEO both
convert on *instant gratification* — a stranger clicks a creator's link, uploads a
file, sees a clip, pays. Our funnel currently ends at "install Python, have a
GPU, own a Claude subscription." **Every high-volume creator-tool play in this
category is incompatible with our install.** That is not a marketing failure to
fix with better copy; it is a structural fact that should decide the channel mix
rather than be fought.

## 2. OpusClip: venture-funded, and the plays money buys

- **Affiliates** here too — six figures in affiliate revenue, hundreds of active
  partners.
- **A permanent free tier** (60 min/month, no card) with watermarked exports —
  and clips that **expire after 3 days**, which shows up in the complaint
  literature as feeling deceptive. Worth noting as an anti-pattern: the artificial
  scarcity that converts also generates the reviews your competitors quote.
- **Integrations as distribution.** Ingest from YouTube, Zoom, Twitch, Loom,
  Drive, Vimeo, Rumble, Riverside, StreamYard, plus Zapier. This is the play with
  the deepest moat: **be where the footage is born.** StreamYard even published a
  joint "60% faster" case study.
- **Agency-facing content** ("how OpusClip helps agencies boost revenue 148%") —
  confirming that the clip-factory ICP from `shorts-strategy.md` §5 is where the
  incumbent also sees money.

**What transfers:** the *idea* of being where the footage is born — but our
version is the opposite geometry. Their integration is a cloud pulling from a
cloud; ours is that **the file is already on the disk we run on**. That is the
same insight with zero partnership cost, and it is the honest local-first pitch.

**What does not:** the integration list itself (needs cloud + BD), and the
watermark loop (`product-strategy.md` §11 proposes the handle badge as a viral
loop — keep it, but note that a badge on a *local* free tier is unenforceable by
design; treat it as a default, not a lock).

## 3. Screen Studio: the closest analogue we have

A **local desktop app**, no cloud, sold to the same broad audience, built by a
tiny team:

- `#buildinpublic` on Twitter brought the **first 10 customers**, at a time when
  posts were getting 0–2 likes. One well-known CEO's like turned into ~1,000 and
  three sales.
- The founder reports a **direct correlation between tweet reach and sales**;
  Twitter was by far the largest traffic source outside direct.
- Three founders, **8,000 customers in 9 months**.
- It later moved from a $229 lifetime licence to $29/mo or $108/yr — subscription
  drift under support load, which is the thing to plan for rather than be
  surprised by.

**This is the single most transferable case study in this document**, and it
turns `product-strategy.md` §14's open question — *"will you be the face?"* —
from a nice-to-have into the pivotal input. For a local-first tool with no
self-serve funnel, the founder's audience *is* the distribution. If the answer is
no, the plan must lean on open source and marketplaces instead, and should expect
to be slower.

## 4. AutoPod and the aescripts economy: how editors are actually reached

Editors do not find tools through ads. They find them:

- on **aescripts + aeplugins** (marketplace since 2008, the default shelf for
  Premiere/After Effects/Resolve tooling) and **Adobe Exchange**;
- through **tutorial channels** — Premiere Basics alone is 585k subscribers,
  publishing weekly workflow videos;
- in editor communities and round-up posts ("best multicam plugins for Premiere
  2026") that these marketplaces and channels feed.

AutoPod — a subscription plugin doing multicam switching, jump cuts and social
clips *inside* Premiere — lives on exactly this shelf. It is the closest
competitor to the paid SKU in `product-strategy.md`, and it reaches its buyers
without a paid-acquisition budget.

**What transfers:** once the **timeline export** exists (FCPXML/EDL/OTIO —
`shorts-strategy.md` §6 item 1), we are shelvable in the same aisle: not as a
Premiere plugin, but as "the thing that produces the timeline you open in
Premiere." A tutorial-channel collaboration is worth more than any ad here, and
costs a video.

## 5. Open source as the channel, not the giveaway

Three data points, one conclusion:

- **Plausible** reached $1M ARR as *the privacy-friendly open alternative to
  Google Analytics*, with Hacker News front pages producing record traffic and
  signup days. Privacy positioning + open source + HN is a proven combination —
  and it is our exact positioning, already validated in a different category.
- **OpenCut**: 45,000 stars simply for being "the open-source CapCut
  alternative." The phrase is the distribution.
- **OpenShorts**: 3.8k stars, MIT, self-host free, **MCP server**, cloud upsell
  from $12/mo — the open-core shape applied to our exact product, already running.
- `AI-Youtube-Shorts-Generator` names its competitors in the repo description
  ("open-source alternative to Opus Clip, Vidyo.ai, Klap & SubMagic"). GitHub
  search and SEO do the rest.

The open-core mechanics that show up repeatedly: the repo *is* the landing page;
users install locally to evaluate; the paid thing is what an individual cannot
self-run (managed service, team features, support, updates); the content flywheel
(write up every feature, document everything) collects the email list months
before there is anything to sell.

**Our version, and the one honest caveat.** We have something the pure-OSS
clippers do not: a **frame-scored benchmark against professionally edited films**
(`product-strategy.md` §3) and a verification discipline. "We rebuilt six
professionally edited multicam films from their raw tapes and re-cut them
frame-for-frame; here is the score" is an HN-shaped artefact that no clipping
repo can answer. The caveat is that open-sourcing the core means the free floor
gets our improvements too — which is only a loss if the paid layer is code. It
is not: it is the gotcha library, the update stream, support, and the pro
pipelines.

## 6. The marketplace nobody has claimed yet

- Anthropic's **official Claude Code plugin directory** launched 2026-05-22 with
  55+ curated plugins; the repo crossed **20,000 stars in four days**; `/plugin`
  ships a browsable catalog in the client.
- **claudemarketplaces.com** reports ~**380,000 developer visits per month** as a
  discovery surface; community marketplaces list 2,000+ skills.
- A marketplace is just a git repo with a manifest — zero infrastructure, which is
  already the plan in `product-strategy.md` §7.

**There is no serious video plugin on that shelf.** Category ownership is
currently free, the audience is exactly the population that already has Claude
Code and a GPU, and the install objection that kills every other channel does not
exist here — these users installed Python this morning. This is the one channel
where our friction is *not* friction.

Treat it as a channel, never a moat (§12 of the strategy doc already says this):
keep the email list and Discord independent of it.

## 7. The clipping economy: a demand pool aligned with our economics

The numbers again, because they reframe the ICP question: ~980k members in Whop
Clips; 6,800+ clipping products averaging ~800 members; **$2.58M tracked payouts
to 8,466 earners**, $887k in February 2026 alone; rates of $0.20–6 per 1,000
verified views blending to ~$0.39; and a tooling market where clipper products
sell for **$20–100 one-time**.

Why this matters: these are people whose revenue is **per view** and whose costs
are **per minute of cloud rendering**. Every credit-metered tool takes a slice of
a $0.39-per-1,000 business. An unmetered local renderer is the only tool shape
whose cost does not scale with their output.

Why to be careful before falling in love with it:

- They are price-sensitive at the $20–100 one-time level, not $499/yr.
- Most clip **other people's** content, which drags in the rights questions
  `shorts-strategy.md` §6 flags around link ingestion — we should never host that
  step, and should not build features that only make sense for it.
- Many are on laptops without an NVIDIA GPU, where local is *slower* (OpenShorts'
  own figures: ~50s cloud vs 5–8 min self-hosted).

**So: not the paying ICP, but the best free-tier population in existence for us.**
They are numerous, organized in findable communities, motivated by throughput,
and they will hammer the tool on footage we would never generate. That is the
free tier doing its real job — distribution and a gotcha-library supply chain —
while the paid SKU stays pointed at clip factories and editors.

## 8. AppSumo and lifetime deals — the one product shape where it is not suicide

The standard warning holds: AppSumo takes a large share (commonly cited around
70% of sale price), attracts refund-prone buyers, and generates a support tail
disproportionate to revenue. And specifically for this category, **video LTDs
always cap cloud rendering credits** because the seller's COGS is a GPU bill.

Ours is not. A local tool has COGS ≈ 0, so a lifetime deal costs us support and
nothing else — the one honest exception to the rule. This makes an LTD a
legitimate *cash-and-cohort* instrument (buy 500 users' footage-diversity and
feedback), but only after the install path survives a stranger's machine
(`product-strategy.md` §13 item 1, the clean-VM dry run). Running an LTD before
that would convert cash into support debt at an unknown exchange rate.

## 9. The pattern across all of them

1. **One channel, done past boredom.** Submagic: affiliates + free tools.
   Screen Studio: Twitter. AutoPod: the marketplace shelf. Plausible: HN + the
   privacy narrative. Nobody in this set won with a balanced portfolio.
2. **The channel was chosen to match the install.** Instant-web products chose
   instant-web channels (affiliates, SEO tools pages). The desktop product chose
   the founder's audience. The plugin chose the plugin shelf. **Our install
   dictates developer/marketplace/open-source channels — and forbids the two
   biggest plays in the category.**
3. **Founder-led support early, at an unreasonable intensity.** Five calls a day
   at Submagic; customer success as a named founder role at Screen Studio. It is
   both retention and, for us, the gotcha-library supply chain.
4. **A phrase that does the selling.** "Open-source CapCut alternative."
   "Privacy-friendly Google Analytics." The phrase is more valuable than the copy
   around it. Ours is not written yet, and `shorts-strategy.md` §7's positioning
   line is a paragraph, not a phrase. That is a gap worth closing before any
   launch.
5. **Every one of them shipped a free thing that was genuinely useful alone.**
   Not a trial — a permanent free tier or an open repo. Ours is planned
   (captions + shorts, `product-strategy.md` §4) and should stay planned.

## 10. The 90-day sequence this implies

Ordered so each step produces the input the next one needs. Nothing here needs
funding; the scarce resource is founder hours.

**Days 1–30 — make the install survivable and pick the phrase.**
1. Clean-VM dry run of the whole path (already build-list item 1; every channel
   below dies at a broken install).
2. Decide the face question. This is the fork: *yes* → build-in-public becomes
   the primary channel; *no* → open source + marketplaces carry it, and expect a
   slower curve.
3. Write the phrase. It has to be sayable by a stranger, and it has to be
   something Opus cannot say. Candidates from the research: *"the AI editor that
   shows its work"* (the debug overlay + review sheet), *"your footage never
   leaves your machine"* (true, and the OSS floor also says it), *"the edit is a
   file you own"* (the decision record — the least contested).

**Days 31–60 — claim the shelf and publish the receipt.**
4. Ship the free plugin to the Claude Code marketplace, and get listed in the
   community directories. Zero infrastructure, an audience with no install
   objection, and no incumbent.
5. Publish the benchmark write-up (HN-shaped) and the debug-overlay video. These
   are the only marketing this audience respects and both are already built as
   capabilities.
6. Open-source the core clipping path under MIT, in the same aisle as OpenShorts
   and AutoClip — and beat them on the thing they cannot copy quickly: the review
   sheet, quoted-speech boundaries, and per-clip re-render.

**Days 61–90 — go where the two ICPs actually are.**
7. Ten clip-factory conversations (the test in `shorts-strategy.md` §10), sourced
   from agency directories and the round-up posts, not cold ads.
8. One tutorial-channel collaboration aimed at editors, timed to the timeline
   export. A single video on a 100k+ editing channel outperforms any spend we
   could afford.
9. Seed the free tier into two or three clipping communities and *watch the
   support channel* — the point is footage diversity and gotchas, not revenue.

**Instrument three numbers and nothing else:** installs that reach a rendered
file (the only activation metric that matters for us), conversations booked with
clip factories, and paid pilots. Stars, impressions and signups are not evidence.

## 11. What would tell us the channel is wrong

- **The clean VM takes more than 20 minutes to a rendered sample** → every channel
  above leaks; fix the install before spending another hour on marketing.
- **The marketplace listing produces installs but no rendered files** → the
  friction is inside the product, not the funnel.
- **The HN/benchmark post lands and produces stars but zero conversations** →
  we're a project, not a product; the paid layer is unclear and needs the ICP
  work, not more content.
- **Editors respond to the tutorial video with "so it's AutoPod but I have to
  install Python"** → the timeline export is not enough differentiation and the
  editor SKU needs rethinking before more spend.
- **Nobody will be the face and the OSS channel stalls at ~500 stars** → accept a
  services-first path (the §14 open question in `product-strategy.md`) rather than
  buying attention we cannot sustain.

## Verify before relying

Submagic's affiliate figures (10k affiliates, ~$1.6M of ARR, ~$45k/mo), the 9M
monthly-visit peak and the $1M-in-3-months milestone come from founder interviews
and Latka's estimates — directionally reliable, not audited. OpusClip's affiliate
"six figures" is a vendor case study. Screen Studio's 8,000 customers in 9 months
is a Starter Story breakdown. The Claude Code directory counts (55+ plugins, 20k
stars in four days, 380k monthly directory visits, 2,000+ skills) are from
secondary blog coverage of a May 2026 launch and move fast — re-check before
quoting. Whop's clipping figures come from clipping-guide sites citing Whop's own
Content Rewards dashboards; the blended $0.39/1,000 is one site's calculation.
The AppSumo ~70% revenue-share figure is commonly cited by sellers, not published
terms — confirm against a current seller agreement before signing anything.

**Sources:** Superframeworks and firstmillion.club Submagic case studies;
Baremetrics *Founder Chats* with David Zitoun; getlatka profiles (Submagic,
OpusClip); Rewardful's OpusClip affiliate case study; opus.pro affiliate and
StreamYard partnership posts; eesel/Ssemble OpusClip pricing reviews; Indie
Hackers *#buildinpublic brought the first 10 customers for Screen Studio* and
Starter Story's Screen Studio breakdown; autopod.fm and aescripts.com
marketplace/author pages; PremiumBeat's Premiere tutorial-channel round-up;
plausible.io blog and Hacker News threads; GitHub — `mutonby/openshorts`,
`artbyjazi/autoclip`, OpenCut coverage; Claude Code plugin-directory guides
(claudecamp.ai, thepromptshelf.dev, claudemarketplaces.com); Whop clipping guides
(whoptrends.com, Ssemble, luvkaizen, openclip.app); AppSumo seller reviews
(SaasTrac, F3 Fund It).
