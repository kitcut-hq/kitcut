# AI/TLDR (ai-tldr.dev): how it is built, where its content comes from, where its traffic comes from

Researched 2026-10-25 from the site itself (its HTML, its public JSON APIs, its sitemaps, its
`/log/` page), OpenSEO (DataForSEO) for search and backlinks, the public web, and **a public
mirror of its source code** (next section). Findings only. Every number below names where it
was read.

## The source code is public (a third-party mirror)

The repo the site links to (`github.com/blackpc/ai-tldr`) now returns 404. The Wayback Machine
has it public on 2026-05-14 (418 commits, MIT licence, created 2026-04-11):
http://web.archive.org/web/20260514023528/https://github.com/blackpc/ai-tldr. A third-party
copy, **https://github.com/Jacobslh/ai-tldr**, carries the full history (1,432 commits,
2026-04-11 to 2026-08-12: ai-tldr-bot 1,201, Igor Makhtes 211, Daria Kushnareva 15). It is a
mirror and may disappear. Everything in this section was read from that copy's files; none of
its code was run.

**Five GitHub Actions workflows, each one `anthropics/claude-code-action@v1`:**

| workflow | schedule | model | job |
|---|---|---|---|
| `update-releases.yml` | `0 */2 * * *` (GitHub throttles it to every 4-5 h, their own notes say) | `claude-opus-5[1m]`, `--max-turns 6000`, a 30 min step timeout with one retry | the release sweep |
| `maintain-registry.yml` | daily 05:30 UTC | `claude-opus-5[1m]` | new models into the LLM registry, missing tools into the directory |
| `daily-digest.yml` | daily 09:00 UTC | `claude-sonnet-4-6`, 30 turns | writes the Buttondown email and sends it via its API |
| `propose-release.yml` | by hand (a name or URL) | `claude-sonnet-4-6` | the "manual-proposal" items |
| `agent-request.yml` | by hand (free-text change request) | `claude-sonnet-4-6` | opens a PR; how the collaborator adds sources and features |

Auth is `CLAUDE_CODE_OAUTH_TOKEN` from `claude setup-token`, so it runs on a **Claude
subscription, not metered API spend**. The sweep's allowed tools are `WebSearch, WebFetch,
Read, Write, Edit, Bash(bun:*|ls|cat|grep|rm)`, under `--permission-mode acceptEdits`. The
action only edits files. A later plain-shell step commits `src/data/releases.json` +
`sweeps.json` as `ai-tldr-bot`, pushes, and pings IndexNow. The push triggers a Cloudflare
rebuild. Before the agent runs, two non-AI steps refresh GitHub star counts and diff the
directory against GitHub's most-starred repos.

**The prompt is `prompts/update-releases.md`** (838 lines, `prompt-version: 6.10.0`; the feed
JSON still says 5.3.0). The agent never writes the feed directly. It writes `sweep-draft.json`,
`scripts/verify-draft.ts` fetches every URL and image and fails on any 4xx/5xx or non-image,
and `scripts/finalize-sweep.ts` removes duplicates by id, normalised id and URL and enforces
the 72 h cap. That is what "zero hallucination" means here: the links are checked by code.
The claims are not. Other files the agent reads: `SOUL.md` (persona), `SWEEP_MEMORY.md`
(52 KB: every failure and its fix, the agent's long-term memory), `GEO_AEO_PLAYBOOK.md`
(writing to be quoted by AI answer engines), `SEO.md`, `LEARN_TREE.md`. There are 22 scripts
in `scripts/` (`yt-rss-scan.ts`, `gh-repo-meta.ts`, `discover-landscape-gaps.ts`,
`prerender*.tsx`, `check-*.ts`, `ping-indexnow.ts`, ...).

**The inclusion bar, verbatim in substance.** All of: dated within 72 h; not a semantic
duplicate of anything already in the feed; "you would post about it today as a 'this just
shipped' tweet". Plus at least ONE of:
- on the HN front page (top 30) with ≥150 points;
- ≥2 tier-1 outlets in 48 h (Verge, Ars, TechCrunch, Bloomberg, The Information,
  Stratechery, The Register, The New Stack);
- GitHub trending with ≥500 stars in 7 days;
- top 10 on HF Papers or HF trending models;
- a post on a top-lab blog's official domain within 48 h;
- ≥500 upvotes on r/LocalLLaMA or r/MachineLearning.

"An empty sweep is success." 34% of the first 535 sweeps were empty (`SWEEP_MEMORY.md`
2026-06-17-A).

**The source order in the prompt:**
1. **First pass**, always:
   - lab blogs: anthropic.com/news, openai.com/index, deepmind.google, ai.meta.com/blog,
     x.ai/blog, mistral.ai/news, cohere.com/blog, qwen.ai, moonshot.ai, DeepSeek, Z.ai,
     MiniMax, Baidu ERNIE, ByteDance Seed;
   - github.com/trending?since=daily;
   - HF trending models and datasets, plus HF Papers top 10;
   - HN top 30 and Show HN;
   - `scripts/yt-rss-scan.ts`, 8 channel RSS feeds: Two Minute Papers, AI Explained, Yannic
     Kilcher, Fireship, Matthew Berman, Sam Witteveen, 1littlecoder, Wes Roth.
2. **Second pass**, only when the first found fewer than 2:
   - coding agents: Cursor, Claude Code, Windsurf, Cline, Aider, Continue, OpenCode and
     others;
   - Reddit r/LocalLLaMA and r/MachineLearning;
   - "influential voices": simonwillison.net, karpathy.ai, latent.space, interconnects.ai,
     lilianweng.github.io, eugeneyan.com, Import AI, The Batch;
   - benchmarks and tutorials.
3. **The AI-for-science lane**, at most 1-2 items a sweep: dated web searches (BCI,
   medical-imaging FDA clearances, protein design, genomics, pharma AI) plus named feeds:
   - news and journals: Nature subject pages, Nature Medicine, STAT News, neurosciencenews,
     EurekAlert, The Transmitter, Endpoints, Fierce Pharma, BioSpace;
   - lab and company blogs: Isomorphic, EvolutionaryScale, Arc, Recursion, Insilico, Absci,
     Hemispheric.
4. **Last resort**: tier-1 press, only to confirm.

**The directory and the registry** (`prompts/maintain-registry.md`, daily):
- For every maker, check its official model pages for something newer than the current
  entry. Add a registry tile and a detail file, with benchmarks and pricing only when sourced.
  The comparison table is transcribed from the maker's own launch chart.
- Missing tools come from `discover-landscape-gaps.ts`. It runs the GitHub search API over
  ~28 topics (`topic:llm`, `topic:rag`, `topic:ai-agents`, `topic:text-to-speech`, ...),
  sorted by stars, keeps repos above 15k stars, and drops awesome-lists and courses.
- Each tool page is written from the repo's README via the GitHub API ("ground every step in
  the project's own docs").
- That is why most tool pages never appeared in the feed.

## What it is

An AI-news site run end to end by an LLM agent. A GitHub Actions job (`github-actions-sweep`)
wakes every few hours, reads a fixed list of sources, decides what is new and important,
writes each item as structured JSON, and rebuilds a static site. Each item becomes a
"release" page. When it is an open-source repo, it also becomes a tool page in a 1,784-tool
directory. Around the feed sit three evergreen sections generated in bulk: a 730-article AI
encyclopedia, a 420-model LLM registry and a 159-person influencer list.

| | count | source |
|---|---|---|
| releases (feed items) | 1,992 | `/api/releases.json`, 2026-10-25 |
| tools in directory / with their own page | 1,784 / 1,370 | `/api/tools.json`, `sitemap-learn.xml` |
| learn articles | 730 (stats page says 652) | `sitemap-learn.xml` |
| model pages | 420 | `sitemap-models.xml` |
| indexable URLs in total | ~4,550 | sitemap index |
| feed started | April 2026 (5 back-dated items from 2024) | `publishDate` histogram |
| feed rate | ~70 items/week, 46 in the last 7 days | `/api/stats.json` |

## Structure

**Sections:** `/` (live feed, sized by importance), `/releases/<slug>/`, `/tools/` and
`/tools/<slug>/` (14 categories, 83 subcategories, `?cat=&sub=` filters), `/models/<slug>/`,
`/learn/<topic>/<sub>/<slug>/` plus `/learn/map/`, `/influencers/`, `/stats/` ("AI Release
Index": derived numbers with "Cite this" snippets, written as link bait), `/log/` (one entry per
sweep), `/advertise/`, `/promote/`, `/promote-your-app/` (a comparison page that ranks for
launch-site searches and sells its own card), `/embed` (a "releases this week" SVG badge),
`/watch`.

**Machine-readable surface (deliberate, for AI crawlers and links):** `robots.txt` allows every
AI bot by name; `llms.txt` and `llms-full.txt`; a free CC-BY JSON API at `/api/releases.json`
(7.2 MB, the whole feed), `/api/tools.json` and `/api/stats.json`; `/feed.xml` (Atom) and
`/feed.json`; a news sitemap. The SPA loads `/data/feed-manifest.json`, then monthly shards
`/data/feed/<yyyy-mm>-<hash>.json` and `/data/release/<id>.json`.

**Stack** (read off the HTML comments and the bundle): React SPA, Vite, Bun (`bun dev`), and
a `scripts/prerender.ts` that writes static HTML for every page. Each page carries its own
title, description, OG tags and JSON-LD, and its data is embedded as `<script
type="application/json" id="__LEARN_DATA__">` (tools, learn) or `__MODELS_DATA__`. The site
is served from Cloudflare. Images are mostly hotlinked
(`opengraph.githubassets.com` for repos, `i.ytimg.com` for videos, publisher CDNs). README
screenshots for tool pages are re-hosted as WebP under `/tools-media/`, and learn
illustrations under `/learn-media/`, credited to the site they came from.

**JSON-LD per template:** release → article; tool → `SoftwareSourceCode` + `HowTo` (from
"Getting started") + `BreadcrumbList`; model → specs/FAQ. The breadcrumb gives every tool page
four levels of internal links.

### The data model (what the agent writes)

A release item (`/api/releases.json`, top-level `promptVersion: "5.3.0"`, `source:
"github-actions-sweep"`):

`id, title, org, date, url (the primary source), summary, categories[], tags[], importance
(notable | major | seismic | rumor), explainer {tagline, whatIsIt, howItWorks, whyItMatters,
forWho, tryIt}, image {url, alt, fit}, links[] {label, url}, publishDate`, plus optional
`metrics` (GitHub stars, HN points, parameters, benchmark scores), `faq[]`, `quickFacts[]`,
`author {name, profileUrl}`, `benchmarks`, `pricing`. A few carry `notes` that state the
inclusion rule out loud: "On HN front page (190 points)", "Within 72h", "Top-list influential
voice".

A tool page: `name, repo, category/subcategory, tagline, seoTitle, metaDescription, overview[3
paragraphs], features[], media[] (README images, credited), gettingStarted {intro, steps[]
{heading, body, code}}, useCases[], language, license, changelog[] {date, note, releaseId}`.
It is an LLM rewrite of the repo's README and GitHub metadata. A page with a dated
`changelog` gets refreshed from the repo's GitHub releases. About 970 of the 1,370 tool pages
carry no `lastmod`; they look seeded in one batch, not grown from the feed. Only 270 of the
1,389 repos in the directory ever appeared as feed items.

A model page: `releaseDate, status, license, openWeights, modalities, contextWindow, maxOutput,
parameters, knowledgeCutoff, overview, strengths, useCases, pricing {input, output,
cachedInput, source}, apis[] {provider, modelId}, links[] (announcement, API docs, OpenRouter,
Artificial Analysis), faq[]`.

A learn article: `title, seoTitle, keywords[] (the search terms it targets), difficulty,
oneLiner, sections[] {blocks: p | list | callout | image}`. All 730 were generated in June 2026
(sitemap `lastmod`). They target head terms such as "faster whisper", "stop sequences", "local
embedding model", "tokens per second".

## Where the content comes from (every source)

The `/log/` page publishes what each sweep searched. 50 entries were read (2026-10-16 to
10-25). The counts are how many of those 50 sweeps name the source.

| source | how it is read | evidence |
|---|---|---|
| **Hacker News** front page / top 30, Show HN, "72h HN >150 points" | HN API | named in 47/50 sweeps; 349 feed items carry an "HN Discussion" link; Talorys came in this way (HN 209 points) |
| **Lab blogs**: Anthropic, OpenAI, Google/DeepMind, Mistral, DeepSeek, xAI, Kimi/Moonshot, MiniMax, Meta, NVIDIA, Qwen | fetches the newsroom pages (OpenAI and xAI often return 403) | 43/50; anthropic.com + claude.com 124 items, openai.com 59, blog.google 58 |
| **GitHub trending** | trending page | 42/50; github.com is the top primary-URL domain (317 items) |
| **Hugging Face** trending models, datasets, Papers (with upvotes) | HF API | 44/50; "#1 on HF Papers" used as a signal; HF upvotes stored as a metric |
| **YouTube**: 8 channel RSS feeds (`scripts/yt-rss-scan.ts`): Two Minute Papers, AI Explained, Yannic Kilcher, Fireship, Matthew Berman, Sam Witteveen, 1littlecoder, Wes Roth. Riley Brown, David Ondrej and DariaWithAI items came in by other routes | `youtube.com/feeds/videos.xml?channel_id=` | 45/50; 235 video items |
| **Coding-agent release notes**: Claude Code, Codex CLI, Cursor, Gemini CLI | GitHub releases / changelogs | 15/50 name Claude Code; one item per notable version |
| **Simon Willison's blog**, Interconnects, Latent Space, Stratechery, Terence Tao | RSS | simonwillison.net 56 items |
| **TechCrunch** (and The Register, CNBC, The Decoder) as secondary coverage | search / RSS | techcrunch.com 93 items; "Canva Craft had only one outlet" → it wants two outlets or a primary source |
| **arXiv** | via HF Papers and HN, not named as its own lane | arxiv.org 68 primary URLs |
| a **"bio/neuro" / AI-for-science** web search | search tool | 16/50 |
| **manual proposals** (security CVEs, a Vercel item) | a separate workflow that a human or form triggers | `source: "manual-proposal"` on 3 items |
| **GitHub API** (stars, license, language, releases) for tools; **OpenRouter** and **Artificial Analysis** plus each provider's pricing page for models | APIs | `metrics`, `pricing.source`, model `links` |

**Not used in practice:** X/Twitter is not a source at all. Reddit (r/LocalLLaMA,
r/MachineLearning, ≥500 upvotes) is in the prompt's second pass, but it appears in none of the
50 log entries. Reddit's API answers datacenter IPs with 403. The 159 influencer X accounts
are a static page, not a feed.

**Inclusion rules** (the log states them): fresh within **72 hours**; already covered → skip
(it de-duplicates against its own feed); needs a **signal**: HN front page / points, #1 on HF
Papers, GitHub trending, a top lab, or a top-list voice; **verify** with a primary source
("ships no code", "no released weights", "could not be verified" are all reasons to drop an
item); minor patch releases are skipped unless they change something users notice. Updates to
an existing item are written back to it rather than added as a new one ("Updated the Node.js
Brotli CVE item with Aikido's wider scope").

**Cadence:** the cron says every 2 hours. The log shows 48 sweeps in 8.5 days, one every
~4.2 hours, because GitHub throttles the schedule (their `SWEEP_MEMORY.md` says so). Sweeps
produce 0 to 4 items each. Median lag from source date to publish is 1 day, p90 2 days.

**Who writes it:** Claude Code in GitHub Actions, as the operator said on HN on 2026-04-13:
"self-updated, static website edited and curated by claude code cli using single single
scheduled github action workfow" (https://news.ycombinator.com/item?id=47753373). The
workflows and models are in the source-code section above.

## Traffic

**Organic search is small.** OpenSEO (DataForSEO, US, 2026-10-25; it runs ~45x low in
absolute terms, see below) puts it at **~675 visits a month** from **1,002 ranking keywords** (1,039 rows). Split of the estimated visits across
the top 100 keywords: **tools 222, releases 160, learn 99, home 97, models 76**. The best
earners are long-tail product names where it ranks #1-4 ("exllamav3", "google litert",
"xiaozhi-esp32 server", "cursor self-hosted", "vosk speech to text") and **AI Overview
citations** ("claude 3.5 sonnet api pricing", "stop sequences", "hf download model", "gpt 5
nano context window"). Brand terms ("ai tldr", "tldr ai newsletter") sit at #2-20; the term
belongs to the much bigger TLDR AI newsletter (tldr.tech/ai: 1.1M subscribers by its own
sign-up page, https://signup.tldr.tech/ai). Big head terms (sglang, faster
whisper, inflect, claude academy) rank 18-86 and bring almost nothing yet.

**Similarweb confirms the visit count, not the "readers".** Similarweb (the owner's screenshots,
September 2026, worldwide) counts **58,860 visits**, ~1,960 a day. That matches `/advertise/`'s
"2,000+ people read AI/TLDR every day" if "people" means visits. In the same view llm-stats.com
had 1.216M and benchlm.ai 1.242M. Within it, ai-tldr.dev has the highest share from referrals
(10.86%) and from social (5.13%) of the three. It also buys non-branded Google search ads,
which Similarweb shows next to llm-stats.com's.

OpenSEO's figure is DataForSEO's estimate of US Google clicks. It runs ~45x below Similarweb on
llm-stats.com (27.6k vs 1.216M) and benchlm.ai (25.2k vs 1.242M). Use it for ratios between
sites, not for absolute traffic. `/promote/` separately claims ~700 impressions and 15-20
clicks for a sponsored card on its first day. Beyond search, the visits come from:
- **Paid Google Ads.** The page loads a Google Ads conversion tag (`AW-17111366460`, a
  `conversion` event), so it buys clicks.
- **Its own link network** (next section). The network injects a "tldr-bar" banner linking
  ai-tldr.dev into every page of its sites.
- **The daily Buttondown newsletter** (`buttondown.com/ai-tldr`, "AI/TLDR Daily Digest").
  About 177 issues since 2026-04-20. "100+ subscribers" is self-reported on Indie Hackers.
- **AI assistants.** `llms.txt`, the open API and the bot-friendly `robots.txt` are aimed at
  being cited. Their `GEO_AEO_PLAYBOOK.md` says that, plus search, is the whole strategy.

**Social is close to zero:**
- Hacker News: 4 live submissions of ai-tldr.dev, 1-3 points each, all 13-15 April 2026, and
  about 10 more [dead].
- Product Hunt: 3 upvotes. LinkedIn: 11 followers. @DariaWithAI on X: 0 followers on
  2026-08-29.
- Reddit: no posts found.

**What they have disclosed:**
- An Indie Hackers post (2026-09-09): "1k daily unique visitors, 100+ newsletter subscribers".
  This comes from the search engine's summary only, because the page is behind a Cloudflare
  403 (https://www.indiehackers.com/product/ai-tldr).
- A LinkedIn post: "Around 2,000 of them now read it every day".
- None of it is checkable, and no revenue figure appears anywhere.

The operator's own analytics filter a bot. A crawler "on a residential proxy network loads a
page for under a second" from ~650 IPs a day since 2026-10-17 (HTML comment). So unfiltered
counts were inflated.

**Backlinks are mostly self-made.** OpenSEO: 4,039 backlinks from 412 referring domains (rank
48), growing from 20 domains in April to 297 in September. The top referrers are
`promptz2h.com` (752 links), `reactz2h.com` (748), `pythonz2h.com` (176), `buttondown.com`
(347, the site's own newsletter), and then **~58 `*.pages.dev` explainer sites among the top
100 of 354 referrers**, with generic names ("green-it-sustainable-computing", "understanding-zero-trust-architecture") at
10-27 links each. Fetched samples share the operator's analytics server
(`analytics.pomegra.io`, each with its own website id), link `pomegra.io`, and carry the same
injected ai-tldr.dev banner with keyword anchors ("daily AI summaries and latest machine
learning research"). That is a private link network under the operator's control, not earned
links. Earned links are the minority: mlflow.org (36), you.com, windowsforum.com,
smzdm.com, a few AI-news aggregators.

## Competitors and demand (OpenSEO, US, 2026-10-25)

**Who it competes with.** `find_serp_competitors` was run on 40 of the keywords ai-tldr.dev
ranks for. Reddit, GitHub, YouTube and Medium lead overall. The sites built like this one:

| domain | OpenSEO organic estimate / month (Similarweb Sep 2026, all visits) | keywords | wins with |
|---|---|---|---|
| **llm-stats.com** | **27,616** (1.216M) | 4,185 | a leaderboard home page ("largest language model" 33k, "llm leaderboard" 8.1k, "best ai model"); **one** release page, `/llm-updates`, #1 for "newest ai" 4.4k, "new ai models", "latest model"; `/ai-news` #1 for "llm news"; one page per benchmark ("swe bench verified", "osworld", "lmarena leaderboard") |
| **benchlm.ai** | **25,186** (1.242M) | 3,769 | provider pricing pages (`/anthropic/api-pricing` #2 for "claude api pricing" 8.1k; Google, OpenAI); `/best/<slice>` lists ("chinese ai models", "best ai models right now", "non-reasoning models"); a Claude Pro vs Max post; one page per benchmark |
| aireleasetracker.com | 826 | 369 | #1-4 for the "new ai releases" cluster |
| **ai-tldr.dev** | **675** (58,860) | 1,002 | long-tail tool names and AI Overview citations (above) |

The two registry sites get ~40x its search clicks (OpenSEO) and ~21x its visits (Similarweb).
llm-stats.com does it with fewer pages (~3,070 to its 4,550). benchlm.ai has ~290,000, but
288,000 of those are auto-generated comparisons that rank for only 889 keywords
(`docs/market-llm-leaderboards-2026.md`). Both answer high-volume comparison and pricing
searches on a few strong pages. ai-tldr.dev spreads
the same subject over 2,000 thin release pages, and those pages stop being searched within a
week. For the head term it wants, "new ai models", it is #5 behind llm-stats.com's single
`/llm-updates` page.

**Demand** (`get_keyword_metrics`, monthly US volume / keyword difficulty 0-100):

| keyword | volume | KD | | keyword | volume | KD |
|---|---|---|---|---|---|---|
| ai news | 90,500 | 86 | | claude api pricing | 8,100 | 15 |
| claude pricing | 40,500 | 34 | | llm leaderboard | 8,100 | 56 |
| ai tools | 40,500 | 63 | | ai benchmarks | 8,100 | 38 |
| what is an ai agent | 22,200 | 49 | | best ai tools | 6,600 | 28 |
| ai news today | 18,100 | 79 | | **claude code changelog** | **4,400** | **16** |
| what is mcp | 18,100 | 29 | | gemini api pricing | 4,400 | 21 |
| artificial analysis | 18,100 | 24 | | **claude code release notes** | **2,400** | **17** |
| what is rag | 12,100 | 42 | | deepseek pricing | 2,400 | 1 |
| new ai models / newest ai models | 1,900 each | 39 / 55 | | ai tools directory | 720 | 46 |
| new ai releases | 70 | 44 | | ai release tracker | 30 | - |

"ai newsletter" also reads 90,500, identical to "ai news". That looks like Google Ads grouping
the two terms, not real demand for the word "newsletter".

**Live SERPs** (top 10, desktop US):
- **"claude code changelog"** (4,400/mo, KD 16): the top 10 is builder.io's March round-up, a
  Reddit thread, a Medium post, a personal timeline page, GitHub issues and the @ClaudeCodeLog
  X account. No site has a page per version with what changed in plain English. ai-tldr.dev
  writes exactly those items and does not rank, because each version is a separate release URL
  with no hub page.
- **"new ai models"**: an AI Overview first, then three YouTube videos in the top seven
  organic results. Google shows video for this query.
- **"claude api pricing"**: Reddit, then benchlm.ai, then generic 2026 pricing blogs.
- **"ai tools directory"**: thin directories (yo.directory, theaidirectory.io, an awesome
  list). It is cheap to enter and worth little: 720/month.
- **"what is mcp"**: the official docs, stackoverflow.blog, Google Cloud, Anthropic. These are
  authority sites, so it is not winnable with a generated article.

OpenSEO cost: 166 credits for this section, 268 for the whole document. A domain overview is
14 credits, a 40-row ranked-keyword list ~20, a 40-keyword competitor comparison and 100 rows
of ranked keywords ~48 together, 5 SERPs plus 50 keyword metrics ~36.

## Money

- **Sponsored feed card, $20 once, never expires** (Dodo Payments). Live within a minute and
  labelled SPONSORED.
- **"AI Tools" article, $150.** A paid tool page, live in 2-4 hours.
- **Ads package, $250** (listed at $500). Top spot for a month plus site-wide ads.
- **Google AdSense** (`ca-pub-9843152248523780`).
- Buy Me a Coffee (`silver_d`).

## Operator

- **Igor Makhtes** (GitHub `blackpc`; LinkedIn lists Lema AI, Israel) built it. His GitHub
  profile's blog field is https://ai-tldr.dev/, and he wrote 211 of the commits.
- **Daria Kushnareva** merged 15 "agent-request" PRs (Jul-Aug 2026): the bio/neuro/pharma
  lane, a Google Ads sign-up conversion tag, and the operator's own shep.bot repos in the
  tools directory.
- **@DariaWithAI** on X is the contact page's "message me". It had 11 tweets, mostly replies
  to strangers with a link to the site.
- **Pen names on the marketing posts:**
  - "Alex Morgan" wrote a launch note on write.as and a "why I built it" post on mataroa ("costs
    me less than a coffee subscription"), and is the Product Hunt maker.
  - "Dr. Alex Turner" is the credited author of pythonz2h.com, and is also the HN account
    `dralexturner` that submitted ai-tldr.dev.
- **Pomegra** (pomegra.io, an AI-generated finance site, registered 2024 in Israel) has the
  same owner:
  - `blackpc` submitted it to HN, along with pythonz2h/reactz2h/promptz2h/dotnetz2h.
  - `pomegra.io/ai-digest` 307-redirects to ai-tldr.dev (checked 2026-10-25).
  - Its analytics server counts the site, the newsletter's open pixel and the whole link
    network.

## If we build one

What carries over directly:
1. **The sweep is one prompt, a fixed source list and two checker scripts.** That is
   `prompts/update-releases.md` + `verify-draft.ts` + `finalize-sweep.ts` in their repo. The
   agent drafts, code checks every link and image and de-duplicates, and a plain shell step
   commits.
   - It runs on `claude-code-action` with a subscription OAuth token, so the running cost is a
     Claude plan, not per-token API spend.
   - A scheduled Claude Code routine would do the same without GitHub's 2 h → 4-5 h throttle.
   - The `/log/` page (a public reason for every skip) is cheap and builds trust.
   - Their `SWEEP_MEMORY.md` is the part worth studying first: six months of failure modes
     already written down (empty sweeps, YouTube on CI, 403 lab blogs, hung actions).
2. **Structured JSON first, pages second.** One schema per template, prerendered with per-page
   meta and JSON-LD, plus an open JSON API, `llms.txt` and an Atom feed.
3. **Every feed item that is a repo spawns an evergreen page.** That is where its search
   traffic actually is (tools 34% of estimated visits), not in the news feed.
4. **Programmatic encyclopedia and registry pages** win AI Overview citations on exact
   questions (pricing, context window, "what is X").

What to do better than they do (the competitor numbers above):
5. **Hub pages, not only item pages.** One always-current `/new-ai-models/` page (llm-stats.com
   takes the "newest ai" cluster with one). One page per product changelog: "Claude Code
   changelog" (4,400/mo, KD 16, nobody owns it), Codex CLI, Cursor. Plus one pricing page per
   provider ("claude api pricing" 8,100, "gemini api pricing" 4,400, "deepseek pricing" KD 1).
   The sweep already produces the facts for all of these. They need a page that collects them.
6. **Leaderboard, "best of" and benchmark pages** bring ~72% of llm-stats.com's estimated
   traffic and ~48% of benchlm.ai's (measured on each site's top 40 keywords). benchlm.ai's
   provider pricing pages bring another 29%.

What not to copy:
- **The link network.** It is Google's "link spam" policy by the letter. It buys a site the
  manual action that would wipe the 1,000 keywords out.
- **Their content, wholesale.** The README declares the code MIT (there is no LICENSE file),
  and `llms.txt` calls the JSON feed "CC-BY". So reusing the code with the MIT notice, or the
  feed with attribution, is permitted. Republishing their pages would still make a duplicate
  site that Google folds into theirs. The sources above are the ones they read, so we can
  generate our own.
- **The "2,000 readers a day" pitch without our own measured numbers.** Their search traffic
  cannot support it.

Where they are weak: search traffic is tiny (~675/month), so it is not a moat. The brand term
"TLDR AI" belongs to tldr.tech. X is not read at all, and Reddit is in the prompt but blocked
in practice. YouTube RSS fails often (the log shows 404/500 on most channels in several
sweeps). Social reach is nil (0 X followers, 3 Product Hunt upvotes). Nothing is video, which is our lane: a
feed that ships a 60-second explainer per seismic release has no competitor here.
