# The AI shorts/clipping market, researched 2026-09-01

Findings only. This document deliberately carries **no recommendation** — it was
commissioned to test, with evidence, whether targeting a single use case (shorts)
is viable in a saturated market. The conclusion is the reader's to draw; what is
recorded here is what the market actually looks like, with dates and sources, so
that a later decision argues with evidence rather than with priors.

Companion to `docs/product-strategy.md`, which predates this research and rejected
"a shorts web SaaS" on reasoning alone (§6, "entrant #40 in a freemium quota
war"). Some of that reasoning is now supported by measurement; some of it turns
out to have been aimed at the wrong risk. Both are noted inline.

**Method.** Three parallel research passes on 2026-09-01 — competitor health, GTM
playbooks, demand side — over vendor pricing pages, funding announcements,
Trustpilot/G2/Capterra primary reviews, GitHub API, and secondary aggregators.

**Read every number here with these caveats:**

- Most revenue figures are **GetLatka/Sacra estimates or founder self-reports**,
  not audited. They are directionally useful, not precise.
- **The category reviews itself.** Vizard, Submagic, Klap, SendShort, Ssemble,
  quso, ClipMe and OpenClip all publish "best clipping tools" and "X alternatives"
  listicles ranking themselves first. Where such a source is cited below it is
  because multiple competitors agree *against their own interest*.
- Reddit is poorly indexed by the search tooling available and direct fetches were
  blocked, so Reddit sentiment arrives through aggregators that quote it. Trustpilot,
  G2 and Capterra were read directly and carry more weight here.
- The Montage "state of AI clipping 2026" benchmark and the ClipMe "state of
  clipping" report are **vendor-run**. Their rankings are discounted; their
  cross-tool capability gaps are retained because independent testing agrees.

---

## Part 1 — The competitive field

### The leader, and where it is going

**OpusClip** raised **$20M from SoftBank Vision Fund 2 at a $215M valuation in
March 2025** (~$50M total raised), on roughly **$20M revenue in 2025** at 150% YoY,
10M+ users and 170M+ clips, with enterprise logos including HubSpot, Visa, Vox
Media and Juventus.
([Sacra](https://sacra.com/c/opusclip/),
[AOL/Fortune, Mar 2025](https://www.aol.com/ai-video-startup-opusclip-raises-160002794.html))

It hit **$1M ARR in 14 days** at launch.
([StartupSpells](https://startupspells.com/p/opusclip-ai-video-editing-tool-1m-arr-14-days))

The strategically important fact is what it did with the round — it is visibly
building **away from clipping**:

- **OpusSearch** (June 2025) — an "AI growth agent" that searches, reuses and
  monetizes a creator's back catalog.
  ([opus.pro](https://www.opus.pro/blog/opusclip-raises-a-new-round-of-funding-from-softbank-and-launches-opussearch))
- **Agent Opus** (Aug 2025) — generative end-to-end short-form creation from a
  prompt, link or blog post; Zapier integration Sept 2025.
  ([Sacra](https://sacra.com/c/opusclip/),
  [mer.vin, Jul 2026](https://mer.vin/2026/07/agent-opus-explained-opusclip-end-to-end-ai-video-agent/))
- 2026 positioning is now "**multi-model AI video platform**."
  ([opus.pro](https://www.opus.pro/blog/evolution-ai-models-multi-model-video-platforms-future))

Pricing: free 60 min/mo, then $15/$29 per month; **credits are source-upload
minutes and expire in 60 days**.

Sentiment splits sharply by venue: **G2 4.6–4.7** ([G2](https://www.g2.com/products/opus-clip/reviews))
against **Trustpilot 4.0 with ~20–22% one-star** across 478 reviews
([Trustpilot](https://www.trustpilot.com/review/opus.pro)).

### The body count since 2023

| Company | What happened | Date |
|---|---|---|
| **Munch** | Self-serve clipping product **shut down**; getmunch.com now redirects to Munch Studio, a done-for-you social service. Had raised **$7.2–9.2M against ~$2.8M revenue** with 25 staff. | product ended **2025-12-31** |
| **vidyo.ai → Quso.ai** | Rebranded and pivoted from clipping to "AI social media manager"; ~$3.7M revenue, 34 staff, 4M+ users. | Dec 2024 / Jan 2025 |
| **Chopcast** | Effectively dead — AppSumo buyers report signups closed and logins broken. | ~Apr 2025 |
| **Choppity** | Sold to a design influencer (Michael Wong). A creator buying a small tool, not a strategic exit. | Sept 2025 |
| **Dumme** | YC-backed, **$3.4M seed June 2023**, still waitlist-only as of Jan 2026. Never shipped publicly. | — |
| **AutoStreamPro** | Discontinued. | Jul 2026 |

Sources: [PRNewswire (Munch seed)](https://www.prnewswire.com/il/news-releases/ai-powered-automation-startup-for-social-media-munch-raises-7-2m-in-seed-funding-led-by-a-capital-301993626.html),
[GetLatka (Munch)](https://getlatka.com/companies/getmunch.com),
[OpenClip alternatives](https://openclip.app/alternatives/munch-alternatives),
[GetLatka (Quso)](https://getlatka.com/companies/quso.ai),
[AppSumo Chopcast reviews](https://appsumo.com/products/chopcast/reviews/),
[Choppity blog](https://www.choppity.com/blog/new-leadership-vision-and-future-for-choppity/),
[TechCrunch (Dumme)](https://techcrunch.com/2023/06/02/yc-backed-dumme-raises-3-4m-for-its-ai-video-editor-turns-long-form-youtube-videos-into-shorts).

**Tally: 3 pivots, 2–3 deaths, 1 micro-acquisition, and no successful strategic
exit anywhere in the category.**

Adjacent context: OpenAI **shut its Sora short-form video app on 2026-03-24** "as
company reels in costs" ([CNBC](https://www.cnbc.com/2026/03/24/openai-shutters-short-form-video-app-sora-as-company-reels-in-costs.html)),
and a broad AI application-layer shakeout is documented — roughly **95 shutdowns
and 101 acquisitions in 18 months** across AI tools
([Morningstar/Business Wire, Dec 2025](https://www.morningstar.com/news/business-wire/20251223595831/the-2025-startup-shutdown-more-capital-later-stages-and-the-first-ai-reckoning)).

### Who is actually healthy

The health outlier is **not a clipper**:

- **Submagic** (captions/effects) — **$8M ARR June 2025, bootstrapped, 13 people**
  (~$615K revenue per employee), on a 30%-lifetime affiliate engine. Reached $1M
  ARR in 90 days.
  ([GetLatka interview writeup](https://getlatka.com/blog/submagic-revenue-bootstrap-ceo),
  [Superframeworks](https://superframeworks.com/case-study/submagic))
- **Veed** — **$50M ARR by May 2026** (from $45M Oct 2025), 10M MAU. Clipping is
  one feature of a full editor. The healthiest company touching the space.
  ([GetLatka](https://getlatka.com/companies/veed), [Sacra](https://sacra.com/c/veed/))

The surviving independents are modest and mostly bootstrapped: Vizard (~$5.7M
est.), Spikes Studio (~$1.4M, ~13 people), Klap (~$440K–1M ARR, 4 people, Paris,
unfunded), 2short, SendShort, Wisecut, Pictory (~$3.9M est. on ~$2–4.7M raised),
Eddie AI (~$550K ARR, 5 people, pivoted to pay-as-you-go via an **MCP server** —
selling into editors' AI stacks rather than to creators), Peech ($14.3M raised
through Aug 2022, no news since — possible zombie).

**Crayo.ai** claims **$600K/mo SaaS plus ~$400K/mo courses, bootstrapped** by a
then-17-year-old founder — self-reported, unverified, and accompanied by a
Trustpilot 3.5/5 pattern of charged-after-cancellation, no-refund and unpaid-
affiliate complaints.
([Starter Story](https://www.starterstory.com/crayo-breakdown),
[Trustpilot](https://www.trustpilot.com/review/crayo.ai))

### The floor is now free

| Who | What shipped | When |
|---|---|---|
| **TikTok** | **Smart Split** in TikTok Studio Web — auto-cuts long video into vertical captioned clips, free | global rollout from **Oct 2025** |
| **YouTube** | "Edit with AI" for Shorts (15 countries); **killed viewer-facing Clips 2026-04-17** while adding creator-side **AI highlight suggestions** in Studio (English podcasts, US/CA first) — and explicitly pointed users at "third-party tools with more advanced clipping capabilities" | Nov 2025 – Apr 2026 |
| **Riverside** | Magic Clips **on the free plan** — clipping given away to sell recording ($29/mo Pro) | 2026 |
| **CapCut** | "Long Video to Shorts" inside the editor; fast but cuts mid-sentence. Pro **doubled $9.99 → $19.99 in May 2025**; June 2025 ToS perpetual-licence grab caused creator backlash | 2025–26 |
| **Descript** | Rebuilt around **Underlord**, an agentic co-editor; clips are one feature of "vibe editing" | 2025 |

Sources: [Metricool](https://metricool.com/tiktok-new-ai-tools/),
[Storrito](https://storrito.com/resources/tiktok-smart-split-ai-outline-how-it-works/),
[ppc.land, Apr 2026](https://ppc.land/youtube-kills-clips-and-bets-on-timestamp-sharing-in-2026/),
[Cleanvoice on Riverside](https://cleanvoice.ai/blog/riverside-review/),
[BIGVU on CapCut pricing](https://bigvu.tv/blog/capcut-free-vs-pro-what-2026s-restructure-actually-gives-you/),
[Descript](https://www.descript.com/blog/article/descript-season-6-meet-underlord).

Net: the basic transform — long video in, vertical captioned clips out — is priced
at **$0** by the platforms themselves. Their quality is mediocre and YouTube openly
defers to third parties, but the commodity floor is set.

---

## Part 2 — Go-to-market playbooks, by evidence of durability

### The constraint that governs all of them

- **15% monthly logo churn**, disclosed by the category's best operator
  (Submagic). That is ~6.7 months average lifetime → **LTV ≈ $130–200** on a
  $20–29 plan.
- **AI apps retain 21.1% annually vs 30.7% for non-AI apps**, across 3,500 apps.
  ([RevenueCat](https://www.revenuecat.com/blog/growth/ai-app-retention-study),
  [TechCrunch, Mar 2026](https://techcrunch.com/2026/03/10/ai-powered-apps-struggle-with-long-term-retention-new-report-shows/))
- $1M ARR in **14 days** (OpusClip) and **90 days** (Submagic) proves top-of-funnel
  is a commodity here.

**Consequence: "grew fast" is table stakes; retention is the binding constraint
for everyone in this category.**

### 1. Recurring-commission affiliates — the proven engine

The only paid channel whose CAC survives that churn.

| Vendor | Commission | Scale |
|---|---|---|
| Submagic | **30% lifetime**, incl. upsells and agency plans | 10,000+ affiliates, **~20% of revenue (~$1.6M ARR)**, ~$40K/mo in commissions |
| OpusClip | 25% recurring, **capped at the referred user's first 12 months** | — |
| Klap | 20–30% recurring | — |
| Crayo | — | ~$90K in its best month, zero ad spend |

([submagic.co/affiliate](https://www.submagic.co/affiliate),
[help.opus.pro](https://help.opus.pro/docs/article/affiliate-program-faq),
[klap.app/affiliate](https://klap.app/affiliate),
[TheCreatorsAI on Crayo](https://thecreatorsai.com/p/building-600kmo-saas-in-one-year))

**Why it works where ads don't:** a rev-share affiliate is pure variable CAC that
**shrinks automatically when the referred user churns** — the vendor carries no
retention risk. Against $130–200 LTV, fixed-cost sponsorships barely clear, which
is why nobody in the category leads with paid media (Submagic runs only $20–50K/mo
on paid, one specialist). Submagic's founder treats the affiliate corps as free
brand advertising. **Watch item:** OpusClip capping commissions at 12 months
versus Submagic's lifetime is the leading indicator of whether even variable CAC
is being squeezed.

**Side effect — the discovery layer is pay-to-play, end to end.** The SERP for
"best AI clipping tool 2026" is composed almost entirely of vendors reviewing
themselves and each other; "independent" directories are affiliate directories;
YouTube reviews carry affiliate links as standard. There is essentially **no
unpaid editorial voice** in this category. Because AI answer engines ingest those
listicles, the pay-to-play now extends into AI answers.

### 2. B2B / workflow embedding — best durability logic, least public proof

OpusClip Business (quote-priced, SSO, API, unlimited seats, dedicated queue) plus
the enterprise logos and the Zapier/agent moves; Vizard exposing **REST API from
its cheapest paid tier** with a custom Enterprise plan; Quso rebranding into an
agency social-suite; Munch abandoning self-serve for done-for-you service.

Enterprise-style workflow tools retain roughly an order of magnitude better
(GitHub Copilot ~1% monthly churn as the benchmark). **But no clipping pure-play
has published B2B revenue**, and the structural threat is that recording platforms
absorb the feature — Riverside's Magic Clips is free inside recording plans, with
API/SSO/SOC2 on custom-priced Business. For podcast agencies, clipping is becoming
a bundled feature of the recording platform rather than a standalone purchase.
([docs.vizard.ai/pricing](https://docs.vizard.ai/docs/pricing),
[eesel pricing analysis](https://www.eesel.ai/blog/opusclip-pricing))

### 3. High-intent SEO / AEO — converts; volume SEO is dead

The controlled experiment, disclosed by Submagic's founder: **free-tool pages
peaked over 1M monthly visitors and "conversion rate was really bad"** — wrong
intent — and Google then killed their YouTube-downloader pages outright. Every
vendor still runs programmatic "youtube to shorts" / "X alternative" pages, but
these are competitive conquesting, not volume.

2026 context: organic CTR down 61% on queries with AI Overviews (Ahrefs, Feb
2026); ~68% of searches end zero-click; but **AI-search referrals measure ~4.4x
the value of average organic** (Semrush).
([Position Digital](https://www.position.digital/blog/ai-seo-statistics/),
[Linvelo](https://linvelo.com/en/the-zero-click-crisis-2026-why-organic-visibility-is-declining-in-the-saas-industry-and-how-saas-seo-is-changing/))

### 4. The clipping economy (Whop) — real, growing, and it doesn't buy software

Mechanics: brands and creators fund campaigns; clippers are paid per verified
1,000 views at $0.20–$6 (~$1–1.25 typical).

- Mid-2025: **>$1.7M paid to 98,000+ creators**
- Feb 2026: **$887K paid in a single month**
- Apr 2026: **>$40K/day across ~1M videos/month**; Whop at a **$1.6B valuation**,
  3.5B clipped views/month
- Single-buyer datapoint: streamer N3on paid **$1.4M to 303 clippers over five
  weeks**

([ClipAffiliates](https://www.clipaffiliates.com/blog/is-whop-content-rewards-legit),
[Ascynd](https://ascynd.io/en/blog/whop-clipping),
[Forbes, 2026-04-26](https://www.forbes.com/sites/boazsobrado/2026/04/26/the-creator-of-clipping-who-powers-stakes-viral-machine/),
[ListenFirst](https://www.listenfirstmedia.com/what-marketers-need-to-know-about-the-clipping-economy/))

**The catch for tool vendors:** blended payout is ~**$0.39 per 1,000 views and
~$305 average lifetime earnings per clipper**. The median clipper cannot justify
$29/mo of per-minute credits, and the documented stack is *an AI clipper for the
first cut plus free CapCut for everything else*. Competitors already weaponize
this (Ssemble markets "1/4 the cost per clip" straight at clippers). It is a
marketing surface and a pricing threat, **not a revenue pool**.

### 5. Faceless-hustle marketing — fastest growth, worst health signals

Crayo built distribution first (~10M Snapchat followers, an 800K newsletter, 2M+
social), then pointed it at the product with zero ad spend; courses funnel into
the SaaS. Real revenue (~$1M/mo combined, self-reported), but the Trustpilot
pattern (no refunds, billing after cancellation, unpaid affiliates), the course
dependency, and the founder shifting his own attention to **Whop's Content
Rewards — the marketplace, not the tool** — all read as harvest mode.

### 6. Product Hunt — a one-time amplifier

Everyone launched; nobody attributes ongoing revenue to it. Submagic's #2 Product
of the Day mattered mainly because it revealed that its market was the US (80%+
of revenue, from a French company).

### 7. AppSumo lifetime deals — a negative signal

Run only by laggards: Wisecut (**still selling an LTD in 2026, seven years after
launch**), Reap, Vadoo AI, Hipclip (pulled). No category leader ran one. ~15% of
LTD tools shut down within 3–4 years, and per-minute GPU/API COGS make "lifetime"
mathematically toxic — AppSumo itself now publishes on how AI-era costs broke the
model.
([AppSumo Wisecut reviews](https://appsumo.com/products/wisecut/reviews/),
[AppSumo blog](https://appsumo.com/blog/lifetime-deals-in-ai-era))

### 8. Open source / local-first — traction without a business, and the open slot

Checked live via the GitHub API on 2026-09-01:

| Project | Stars | Status |
|---|---|---|
| RayVentura/ShortGPT | 7,908 | dormant — last push Feb 2025 |
| modelscope/FunClip (Alibaba) | 6,206 | active (v2.1.1, Aug 2026); a transcription clipper, not a shorts factory |
| Anil-matcha/AI-Youtube-Shorts-Generator | 4,802 | active (Jul 2026); pitch leads with "**no per-clip credits**" |
| **mutonby/openshorts** | 3,814 | very active; MIT self-host via Docker **+ cloud from $12/mo + an MCP server/API for agents** |
| ClipsAI/clipsai | 538 | dead since Jan 2024 |

19 repos sit under the [`opus-clip-alternative`](https://github.com/topics/opus-clip-alternative)
GitHub topic, most active through Aug–Sep 2026, several tagged "100% local."

**Pattern:** the 2023 wave (ShortGPT, ClipsAI) collected stars and died
unmonetized. The 2026 wave has exactly one credible attempt at a business —
**OpenShorts**, open-core with an agent/MCP angle, undercutting incumbents on
price and aimed at the segment cloud credits structurally cannot serve. Caveat:
its fork-to-star ratio (~1:3.8) is unusually high, so some traction may be
template-driven. **Nobody in this category has both traction and a business on the
local-first side.**

---

## Part 3 — The demand side

### Who pays

| Segment | Willingness to pay | Volume | Notes |
|---|---|---|---|
| **Agencies / SMMs** | Tool spend $29–$100+/mo per client, reselling into **$1,250–$25K/mo retainers** (most B2B buyers $3K–$8K) | Highest — "60 hrs/month" blows through every published tier | Most underserved payers: no tier covers them, refill pricing is quote-only, "credit shock" is reported |
| **B2B content teams** | Highest per seat; SSO/API/compliance | Webinars, demos, panels — steady weekly hours | Proven payers (HubSpot, Visa, Vox Media). Their raw material is **multi-speaker**, the format AI clips worst |
| **Whop-economy clippers** | Low per seat; cost-obsessed | Very high | Beginners $100–500/mo earnings, actives $500–$2K, top networks $30–40K/mo. Already on CapCut + open source |
| **Streamers** | ~$15–25/mo ceiling | High VOD hours | Eklipse **killed its free tier June 2026**; its 2025 shift to credits "pushed part of the community away" |
| **Podcasters** | Low — **~30% pay for any software at all**, avg $25/mo total | 1–4 hrs/wk | Sentiment: editor "fiddly", value questioned |
| **Coaches / course-sellers** | Buy **outcomes**, not tools: $150–$500/video UGC or $5K/mo agency for 12–20 clips | Low footage, high $/clip | Served by the agency segment |

Sources: [eesel pricing](https://www.eesel.ai/blog/opusclip-pricing),
[FORKOFF agency pricing](https://forkoff.xyz/blog/clipping/podcast-clipping-agency-pricing),
[Trends.vc clipping report](https://trends.vc/clipping-businesses-pay-per-view-distribution-clip-armies-view-verification/),
[Castos 2026](https://castos.com/podcast-cost/),
[Eklipse pricing](https://eklipse.gg/help/how-much-does-eklipse-premium-cost/),
[Funnl](https://funnl.ai/content-creation-services-pricing-what-small-businesses-actually-pay-in-2025/).

**Scale check on the headline user counts:** OpusClip's ~$20M revenue across 10M+
users is **~$2 per user per year**. The payers are a thin slice; the rest are free.

### Complaints, ranked by frequency

From Trustpilot opus.pro (4.0/5, 478 reviews, **20% one-star**), Trustpilot
klap.app (3.6/5, **36% one-star**), G2, Capterra, and Reddit via aggregators:

1. **Billing and credit-model hostility** — dominates one-star reviews. Charged
   after cancellation; **projects deleted 3 days after cancelling even with credits
   remaining**; credits expiring (60 days monthly, 12 months annual); no renewal
   reminders; users renewed while sitting on ~2,000 unused credits.
2. **The AI picks the wrong moments** — the top *functional* complaint. **20–40%
   of generated clips are discarded** in independent testing; multi-speaker
   accuracy **48–76%** vs 72–92% single-speaker; **no tool exceeded 35% accuracy
   on humor-driven clips**.
   ([BIGVU 14-day test, 2026-07-02](https://bigvu.tv/blog/opus-clip-tested-2026-where-ai-wins-40-percent-discard/),
   [Montage benchmark](https://montage.app/blog/state-of-ai-video-clipping-2026-benchmark-report) — vendor-run)
3. **Processing hangs and slow uploads** — "videos hang for hours, often never
   finish"; support unresponsive for 30+ hours.
4. **Virality scores don't predict** — low-scoring clips outperform "winners"; the
   score rewards provocative-but-off-topic moments.
5. **Clunky editor, basic controls paywalled.**
6. **Caption sameness** — "when every tool produces the same look, personal brand
   disappears into the feed."
7. **Privacy of unpublished footage** — essentially **absent** from shorts-tool
   review corpora.

**Unsolved by every current tool:**

- **Moment selection on humor and multi-speaker content.** Architecture-level:
  everyone runs the same transcribe → detect → reframe → caption pipeline.
  ([Forasoft engineering teardown, 2026](https://www.forasoft.com/learn/ai-for-video-engineering/articles-ai/opus-clip-descript-submagic-captions-ai-video-editor-tools-2026))
- **The per-minute credit model with expiry.** Structural to cloud COGS — no
  incumbent can defect from it.
- **Upload/processing latency on long files.** Same cause.

### The per-minute pricing pain, specifically

1 credit = 1 source minute regardless of output. A weekly 60-minute podcast is 240
credits/month — already past Starter (150) and 80% of Pro (300). An agency at 60
hrs/month has **no published tier at all**.

Price and quality do not correlate: Munch charged the most ($49/mo) with the worst
measured accuracy; Klap charges $12/mo and ranked third-best. That is what
commoditization looks like.

Where volume users go instead: **CapCut manual** and the **open-source stack**
above. So local processing is a genuine wedge for the cost-obsessed high-volume
tier — but note carefully that **GitHub stars are developers dodging a
subscription, not agencies signing cheques**. The wedge is *cost*; "local" is the
delivery mechanism for it, not the pitch.

### Does anyone care about local/private video processing?

**In the shorts segment: almost nobody.** Zero privacy complaints across the
OpusClip/Klap/Vizard review corpora. The footage is made to be published.

Where local/private video demand is real and paying:

- **Legal / law-enforcement redaction** — an established on-prem market.
  CaseGuard ("case files never leave your secure environment", CJIS/HIPAA); Secure
  Redact offers full on-prem, "preferred by many US agencies" for data
  sovereignty. **This is adjacent to this repo's pipeline-7 PII/blur tooling, not
  to shorts.**
  ([CaseGuard](https://caseguard.com/use-cases/law-enforcement/),
  [SecureRedact](https://www.secureredact.ai/us-law-enforcement))
- **EU data-residency procurement** — 40% of European organisations on sovereign
  cloud in 2025 (IDC), up from ~30%; OpenAI shipped EU residency because
  enterprise buyers demanded it. A procurement checkbox, not a creator desire.
- **Creative professionals with unreleased client work** — the **July 2025
  WeTransfer ToS backlash**, when uploads became AI-training fodder. WeTransfer
  reversed, but trust damage stuck. This is the one *creator-side* proof that
  "trains on my footage" moves users — and it moved them **between file-transfer
  tools, not to local software**.
- **Enterprises with internal footage** — served by secure *hosting* (Panopto,
  Vimeo Enterprise), not local *editing*. They demand compliant clouds.

**Net:** local-first as a **privacy** pitch does not sell shorts tooling. In
shorts it matters **economically** — it is the only way to deliver "no per-minute
meter, no upload wait, no projects held hostage," which are precisely the three
complaints cloud incumbents structurally cannot fix.

### The price umbrella: what humans charge

| Tier | 2026 rate |
|---|---|
| Fiverr budget floor | $5–15/short |
| Typical | $15–80/short |
| Growing channels | $40–120/video |
| Mid-market Upwork | $80–300/video |
| Hourly (intermediate) | $30–60/hr |
| Retainers | beginner $400–800/mo · intermediate $800–2,500 · expert $2,500–6,000+ |
| Top freelancers | $5K–10K/mo retainers ≈ $100–125/hr effective |

**Has AI compressed rates? At the bottom, yes; above it, not yet.** The $5–40/clip
tier "is getting hammered by AI — Opus Clip, VEED, and Fiverr's new AI Video Hub
(launched March 2026)"; hybrid workflows explicitly halve invoices ("from $50 per
Short to perhaps $25 for a 30-minute touch-up"). The **$3K+/mo agency retainer
floor is intact**.
([ChatCut](https://chatcut.io/blog/freelance-video-editing-platforms-2026),
[FluxNote](https://fluxnote.io/guides/how-much-to-pay-video-editor-youtube-shorts),
[Vidsteer](https://www.vidsteer.com/blog/video-editor-cost))

So the human-equivalent value of a finished clip is roughly **$25–120** against
$15–29/mo subscriptions. **Agencies arbitrage that gap rather than passing it on**
— which is exactly why they, not creators, are the segment with money.

### The quality ceiling

Consistent testimony that AI clippers are **draft machines, not finishers**:

- "Expect to discard 20–40% of what gets generated… a first-pass tool rather than
  set-and-forget" (BIGVU, Jul 2026)
- "Most podcasters treat OpusClip as an assistant… pick 2–5 strong clips, then fix
  captions, trim timing" — [The Podcast Host, 2025-12-16](https://www.thepodcasthost.com/recording-skills/can-opusclip-make-your-podcast-go-viral/),
  the most credible non-vendor voice found
- The converged 2026 workflow: "OpusClip to surface the moment, then CapCut or
  Submagic to finish it"; "do not publish the first draft untouched"
- OpusClip's own power users triage by virality score: >80 posts with minimal
  review, 40–79 gets manual editing, <40 discarded
- OpusClip staged a **human-editors-vs-Agent-Opus live competition on 2025-12-02**,
  framed as "or if the two should work together"
  ([Tubefilter, 2025-11-21](https://www.tubefilter.com/2025/11/21/opus-clip-agent-opus-competition/)).
  **No post-event PR claiming the AI won could be found** — a decisive win would
  have been marketed hard.

No serious 100k+ creator was found publicly shipping AI-clipper output untouched
as their main-brand shorts. The enterprise logos use it inside human-reviewed
workflows.

---

## Part 4 — The load-bearing facts

Carried forward from all three passes, in the order they change a decision:

1. **Demand is proven; retention is not.** $1M ARR in 14 days is achievable, and
   so is 15% monthly churn. Signups are a commodity. The category currently
   monetizes churn — affiliates, expiring credits, hustle funnels — rather than
   retention.
2. **The basic transform is now free** (TikTok Smart Split, YouTube Studio,
   Riverside), and **the leader is spending a SoftBank round building away from
   clipping.** When the $215M-valuation winner redefines itself as a "multi-model
   AI video platform," that is a read on the core product's commoditization clock —
   the same read Munch and vidyo.ai arrived at with less runway.
3. **Discovery is pay-to-play end to end**, and now inside AI answers too. Entering
   means paying the affiliate toll or arriving with independent distribution.
4. **Two positions the evidence repeatedly points at as open:**
   - **Flat-cost / local tooling for high-volume users** (agencies, clippers) — the
     segment per-minute cloud pricing structurally cannot serve, currently
     contested only at Docker-level open source.
   - **B2B / agency workflow embedding** with seats and API — the best retention
     logic in the category, unproven by any pure clipper, and at risk of being
     bundled away by Riverside/Descript.
5. **The hardest unsolved product problem in the category — multi-speaker moment
   selection — is this repo's multicam-switch problem wearing a different hat.**
   Nobody in the market publishes a frame-scored benchmark; this repo has one.
6. **The money is where the arbitrage is.** Agencies buy $15–29/mo tools and sell
   $25–120/clip human-equivalent work into $3K–8K/mo retainers. Creators are the
   loud segment; agencies are the paying one.

## Part 5 — What this research does not answer

- **Whether the agency tier will pay for a packaged local-first tool.** Nobody has
  proven it. The open-source traction is developers avoiding a subscription, which
  is not the same buyer.
- **Whether B2B clipping revenue exists at scale.** The evidence is directional
  (pricing pages, logos, integrations), never financial.
- **What OpusClip's Business tier actually earns**, and therefore whether the
  prosumer→B2B transition it is funding is working.
- **Real retention numbers for anyone but Submagic**, who volunteered his.
- **Whether the frame-scored benchmark advantage translates into a buying reason**
  for anyone outside professional editing.
- **How fast the free platform-native tools improve.** Their current mediocrity
  (CapCut cutting mid-sentence, YouTube podcasts-only in US/CA) is the whole
  breathing room, and it is not a durable assumption.

---

## Verify before relying

Everything above is dated 2026-09-01 and much of it moves quarterly. Before acting
on any single figure: re-check the funding/shutdown status of anyone named in Part
1, the affiliate commission terms in Part 2 (OpusClip's 12-month cap is the
tell-tale), and whether TikTok/YouTube have improved the free tier described in
Part 1. Prefer primary sources — pricing pages, Trustpilot, the GitHub API — over
the vendor listicles that dominate search results in this category.
