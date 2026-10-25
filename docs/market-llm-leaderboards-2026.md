# LLM leaderboards (llm-stats.com, benchlm.ai): where their numbers come from, what they do with them, and what copying them takes

Researched 2026-10-25 from the two sites' own pages, data files, embedded page data and
methodology. Traffic comes from Similarweb (the owner's screenshots, September 2026) and OpenSEO
(DataForSEO). Findings only. Companion to `docs/market-ai-tldr-2026.md`, which covers the news
feed these two out-rank.

## The short answer

**Neither site runs the benchmarks its rankings are built on.** Both collect numbers other
people published and convert them to one scale. They combine them into one score with an
uncertainty band, then publish the result as thousands of pages and sell access to the data.

| | llm-stats.com | benchlm.ai |
|---|---|---|
| visits, Sep 2026 (Similarweb) | 1.216M | 1.242M |
| where the benchmark numbers come from | **~95% the labs' own claims** (system cards, launch posts, papers), each linked and flagged `self_reported` (99.3% across 15 major benchmarks) | **42% the labs' own claims, 46% independent evaluators** (Artificial Analysis 31%, Vals AI 6%, ARC Prize 3%, Epoch AI 3%, OpenRouter, Cursor, Terminal-Bench), 12% niche benchmark sites (top 60 models, 2,556 rows) |
| what it tests itself | no capability tests: 0 of 1,222 results on 15 major benchmarks are `verified`. Latency from its own playground/API traffic (most top models: zero to ten requests a week); arena votes (new submissions now closed, archive kept); prices "checked against observed billing data" | no model tests. One paid audit of 7 API gateways (900 requests each); speed is copied from Artificial Analysis |
| the composite | "LLM Stats Score v3.1": relative standing within each benchmark, combined across the catalogue, missing results not counted as losses, uncertainty kept | "BenchAlign v5.8": 58 weighted benchmarks in 8 categories, scored 0-100 with a 90% interval; positions with thin evidence are **estimated** from peers and lineage (137 of 224 ranked models) |
| pages | ~3,070 | ~290,900 (288,000 of them "X vs Y" comparisons) |
| how it makes money | custom evaluation projects, data labeling, a data API/MCP, a playground and an app builder (Huggle), sponsored slots. Backed by Y Combinator; two people; no revenue public | labelled sponsorships, a data API (Free / $49 / $249 a month), commercial display licences; data published CC BY-NC. One person; **$6,105 revenue all-time** to Aug 2026 (Stripe-verified) |

**Their job, step by step:**
1. Watch for new models.
2. Find each model's numbers: the lab's tables, the evaluators' leaderboards, the prices.
3. Match model identities across sources (one model, a dozen spellings and effort levels).
4. Normalise each benchmark: scale, direction, version and the effort setting it was run at.
5. Combine into a score that does not punish missing data, and attach an uncertainty band.
6. Publish leaderboards, model pages, benchmark pages, pricing pages and comparisons.
7. Sell the data or the evaluation expertise behind it.

Step 3-4 is the expensive part. llm-stats.com stores a human-readable `analysis_method` on
every number ("System Card Table 8.1.A. AA-Briefcase v1.1 Elo at max effort"). benchlm.ai
keeps 764 benchmark definitions with weights, successors and source links.

## Traffic

**Similarweb, September 2026, worldwide** (read off the owner's screenshots; bar values are
approximate):

| | llm-stats.com | benchlm.ai | ai-tldr.dev |
|---|---|---|---|
| visits | 1.216M | 1.242M | 58,860 |
| organic search | ~670k | ~950k | small |
| direct | ~440k | ~190k | small |
| referrals | ~55k | ~70k | 10.86% of its visits |
| social | ~15k | ~10k | 5.13% of its visits |
| paid search | buys non-branded terms | none visible | buys non-branded terms |
| display ads on the site | none detected | none detected | none detected (AdSense tag present) |

Countries for the three together: US 15.75%, Indonesia 6.23%, India 5.72%, Turkey 4.79%,
China 4.18%. Turkey (74%) and China (63%) lean to llm-stats.com. The named referrers lean to
benchlm.ai: yuque.antfin.com (Ant Group's document platform, 8.6% of the group's referrals,
75.5% to benchlm.ai), link.zhihu.com (5.85%, 88.4% to benchlm.ai) and kagi.com (5.38%, 74.3%
to benchlm.ai). ahrefs.com (2.37%) sends only to llm-stats.com.

**Where their search traffic lands** (OpenSEO, US, each site's top 40 keywords by estimated
traffic; DataForSEO's absolute numbers run ~45x below Similarweb, so read these as shares):

- **llm-stats.com** (4,185 keywords):
  - the leaderboard home page, 57%: "largest language model" 33k/mo, "llm leaderboard" 8.1k,
    "best ai models", "ai ranking";
  - `/llm-updates`, a release list, 23%: #1 for "newest ai", "new ai models", "latest model";
  - benchmark pages, 12%;
  - `/ai-news` 4%, `/leaderboards/*` 3%.
  - Model pages are 1,672 of its ranking keywords, but their top 20 bring ~2% of its traffic.
- **benchlm.ai** (3,769 keywords):
  - `/best/*` lists, 31%: "ai ranking", "chinese ai models", "best ai models right now";
  - blog posts, 23%: mostly "Claude Pro vs Max", ranking for "claude pro plan" 27k and
    "claude max";
  - provider pricing pages (`/anthropic`, `/google`, `/openai`), 29%: "claude api pricing"
    8.1k at #2;
  - the home page 10%, benchmark pages 5%, `/compare` 2%.
  - **The 288,000 comparison pages rank for only 889 keywords in DataForSEO's US data**, most
    of it the `/compare` hub and "chatgpt vs claude".
  - benchlm.ai's own analytics say more: comparison pages took at least 90,311 of its
    1,115,214 GA4 pageviews in September 1-28 (8%; its advertise page, archived 2026-10-05).
    That is the long tail a keyword database cannot see, and it is not nothing.

**Links** (OpenSEO, llm-stats.com only; benchlm.ai could not be run, the credits ran out):
- 36,735 backlinks from 5,122 referring domains, rank 57. The monthly trend series rose from
  311 referring domains (October 2025) to 2,430 (September 2026).
- Most come from small AI tool and aggregator sites citing it as their data source
  (llmpodium.com alone has 11,801 links, plus modelfit.io, modelverify.ai). Some are
  editorial: datacamp.com, huggingface.co, unite.ai, zenn.dev, csdn.net.
- Being the number other sites quote is its moat. It is earned, not built.

## llm-stats.com

**What it is:**
- An AI model leaderboard and comparison platform run by ZeroEval Inc. Its `llms.txt` says
  "Founded by Jonathan Chavez and Sebastian Crossa", and the contact email is
  `founders@zeroeval.com`.
- The Y Combinator listing (https://www.ycombinator.com/companies/llm-stats, a 2025 company,
  two people per its About page) calls it an "Independent AI evaluations lab" that "also run[s]
  independent evaluations". The data says otherwise (next sections). So does its developer
  page, which says "Scores are source-verified, not self-reported".
- History:
  - Domain registered 2024-08-09; the first real site was live 2024-09-12.
  - Its open data repo (github.com/JonathanChavezTamales/llm-leaderboard, CC BY 4.0) has been
    frozen as "DEPRECATED" since 2025-10-24.
  - In that repo, 2,206 of 2,224 score rows are `is_self_reported: true` and none is
    `verified_by_llmstats` (counted on a clone).
  - In November 2024 the founder wrote on Hacker News: "Medium term goal is to run the evals
    myself."
- The data API lives at `api.zeroeval.com`. The model list endpoint
  (`/leaderboard/models/list`) answers without a key.
- The services page says "LLM Stats is backed by Y Combinator."
- Built with Next.js behind Cloudflare.

**Pages (sitemaps):** 584 models, 761 benchmarks, 1,486 comparisons, 86 research/blog
posts, 66 organisations, 44 providers, 36 use-case pages ("best AI for lawyers / architects /
YouTube thumbnails / X-ray analysis"), plus leaderboards, arenas, `/llm-updates`, `/ai-news`
and `/ai-model-pricing-comparison`.

**Where each number comes from** (read from the data embedded in model pages). Every
benchmark row carries:

`benchmark_id, name, description, categories, modality, max_score, score, normalized_score,
verified, self_reported, self_reported_source, analysis_method, verification_date,
verification_notes`

- The 16 leaderboard models sampled carry 241 rows: 228 (94.6%) `self_reported: true`, 13
  with neither flag, none `verified: true`.
- The sources are the makers' own pages: openai.com 58, anthropic.com 55, huggingface.co 33,
  kimi.com 30, blog.google + deepmind.google 39, z.ai 7.
- The page says it in words: "Scores sourced from the model's scorecard, paper, or official
  blog posts". Its JSON-LD says "Capability scores are self-reported from the Claude Opus 5.5
  System Card (Table 8.1.A and §8) and the launch announcement".

Its methodology page lists four source types:
- "Provider-published pricing, checked against observed billing data";
- "Verified benchmark releases (lab-published or independently replicated). Unverified
  scores are flagged in the UI and excluded from composite indexes";
- "Live performance measurements collected consistently across supported providers";
- "Community arenas with quality controls".

In practice the published benchmark numbers are the labs' own. "Verified" is the labs'
publication, not a re-run.

**Its own data:**
- Model pages show latency p95, throughput and failed-request rate "from live model usage
  over the trailing 7 days". That traffic comes from its playground, its app builder and its
  API.
- Arena votes ranked chat, code, image and video models. "We're sunsetting new Arena
  submissions in favor of Playground"; the rankings stay as an archive.

**The score** ("LLM Stats Score v3.1", updated 2026-09-02):
- It compares relative performance within each eligible benchmark, then combines across them.
- "Missing results remain missing and are never turned into synthetic losses."
- Lab-reported values stay labelled. Category indexes cover Reasoning, Coding, Agent, Math,
  Long Context and Vision.
- The method is described in words only. The exact formula is shared "with researchers,
  customers, and partners when appropriate".

**Money:** the leaderboard sells the company. No revenue figure is public.
- `/services` sells custom evaluation suites ("a working evaluation suite in your stack. Not
  a benchmark report"), regression gates in CI and data labeling.
- Plus a Data API / MCP, a playground, an image generator and an app builder, Huggle
  (huggle.ai), linked from every model page ("Open in Huggle").
- No display ads.

## benchlm.ai

**What it is:**
- One person, "Guillaume" (@glevd, a paid-marketing and SEO consultant by background, in
  Canada per TrustMRR). Its About page says: "BenchLM does not run proprietary private
  evaluations."
- Domain registered 2025-08-12. The December 2025 homepage read "Vibe coded by @glevd" and
  showed 52 models. It relaunched around March 2026.
- Its own figures: 1,115,214 GA4 pageviews in September 1-28, 2026, up from 791,237 in
  August; 5,027 newsletter subscribers on September 29 (advertise page, archived 2026-10-05).
  Similarweb's 1.24M "visits" is higher than its own pageviews, so Similarweb likely overcounts
  it.
- Revenue verified through Stripe on TrustMRR (archived 2026-08-26): **$6,105 all-time, $18
  MRR**. A July 2026 for-sale listing there was reported at $119K; not re-verified.
- "BenchLM AI tracks 992 AI models across 706 benchmarks, 141 of them grouped into eight
  scoring categories."
- Author on `llms.txt`: @glevd on X.
- Next.js on Cloudflare Workers via OpenNext.
- Every page has a markdown mirror (`/md/...`, or `Accept: text/markdown`), and
  `llms-full.txt` is 1.4 MB.

**Pages (sitemaps), ~290,900 in total:**
- 993 models, 712 benchmarks, 237 providers, 157 pages, 123 model-update pages, 100 blog
  posts, 77 `/best/*` lists, 53 voice benchmarks;
- **~288,000 comparison pages** in 24 sitemaps: "every valid model pair is indexable and
  enters the sitemap automatically when a model is added";
- plus pricing pages per provider, plan pages (Claude, Copilot, ElevenLabs, Vercel), free
  tiers, inference hosts, media pricing, a 709-notice deprecation calendar, a token price
  index and citable statistics.

**Where each number comes from.** Every benchmark row on a model page names its source. Over
the top 60 ranked models (2,556 rows):

| source | rows | share |
|---|---|---|
| Artificial Analysis (artificialanalysis.ai) | 787 | 30.8% |
| the model makers (anthropic.com, openai.com, qwen.ai, deepmind.google, ai.meta.com, kimi.com, huggingface.co model cards, GitHub, arXiv) | 1,065 | 41.7% |
| Vals AI | 154 | 6.0% |
| ARC Prize | 76 | 3.0% |
| Epoch AI | 65 | 2.5% |
| OpenRouter, Cursor, Terminal-Bench | 91 | 3.6% |
| niche benchmark sites (mazebench, parsebench, extractbench, bughunt, frontierswe, Nous portal ...) | 318 | 12.4% |

- The data API page names its feeds: "141 Arena leaderboards, Epoch AI, BullshitBench v2,
  and tables from provider model cards".
- Speed (`speed.json`, 163 rows) is copied from Artificial Analysis' leaderboard. Prices are
  read from each provider's pages and 10 inference hosts, each with a read date.
- The data says what it is: Vals rows carry "Published leaderboard aggregates and evaluation
  settings only", and the confidence page separates "hand-entered public rows" from
  "inferred related rows".

**The score** ("BenchAlign v5.8"; `benchmarks.json` holds the weights). 58 of the 764
benchmarks are weighted, in 8 categories:

| category | benchmarks | heaviest weights |
|---|---|---|
| agentic | 21 | Terminal-Bench 4.0 / 2.1, BrowseComp, GDPval-AA 9% each |
| knowledge | 10 | HLE 44%, AA-Omniscience 17%, AA-HLE 11% |
| coding | 10 | SWE-bench Pro 26%, DeepSWE 15%, SciCode 10% |
| math | 5 | FrontierMath v2 T1-3 30%, AIME26 25%, HMMT Feb 2026 25% |
| reasoning | 5 | LongBench v2 25%, ARC-AGI-2 25%, MRCRv2 20% |
| multimodal | 4 | MMMU-Pro 40%, OfficeQA Pro 25% |
| instruction following | 2 | IFBench 70%, AA-IFBench 30% |
| multilingual | 1 | MMLU-ProX |

- Scores are 0-100 with a 90% interval. The #1 and #2 (Claude Opus 5.5 86.6, GPT-6.1 Sol
  84.2) are "tied within their 90% intervals".
- **Missing evidence is estimated, not left out.** "An Estimated position uses a learned
  blend of the model's own signals, its calibrated benchmark estimate, a reviewed lineage
  prior, the previous policy estimate, and eligible peers." Peers can carry up to 60% of the
  blend.
- 137 of the 224 ranked models are `estimated`; 87 are `supported`.
- The methodology publishes its own failed back-tests ("Three checks of 95th-percentile error
  still worsened").

**Money:**
- Data API at `data.benchlm.ai` (REST + MCP): Free (250 reads a month), Data Pro $49 a month
  (25,000 reads, 3 months of history), Research $249 a month (100,000 reads, all history).
- Paid plans "do not include a commercial display or redistribution permission". That is a
  separate agreement.
- The downloads (`/data/*.json`) are **CC BY-NC 4.0**: free for non-commercial use with a
  credit, a licence otherwise.
- No display ads.

## Do they test anything themselves?

**On capability, no.** Neither site runs a single benchmark that feeds its ranking.

**llm-stats.com:**
- Every benchmark page carries its own counters. Across 15 major benchmarks (GPQA, MMLU-Pro,
  AIME 2025, LiveCodeBench, SWE-bench Verified and Pro, Terminal-Bench 2, HumanEval, MMMU,
  MATH-500, IFEval, ARC-AGI-2, BrowseComp, SimpleQA, OSWorld), 1,222 results: **0
  `verified`, 1,213 (99.3%) `self_reported`**.
- The `verified` flag, `verification_date` and `verification_notes` fields exist, but are
  empty on all of them.
- What it does measure:
  - **Speed, latency and error rate "from live model usage over the trailing 7 days".** That
    means its own playground and API traffic, and the samples are tiny. Of 18 leaderboard
    models fetched on 2026-10-25, 14 had no requests at all in the window. Claude Opus 5.5
    showed 10 requests in one fetch and 3 (2 failed) in a later one. Gemini 3.7 Flash had 59,
    GPT-5.4 mini 2. A "p95 latency" from ten requests is not a measurement.
  - **Arena votes** (blind side-by-side, chat/code/image/video). New submissions are closed
    ("Arenas are moving to Playground"); the rankings remain as an archive.
  - **Custom evaluations for paying clients.** These are private and never reach the site.

**benchlm.ai:**
- No capability tests. Its one test of its own is the "OpenRouter alternatives" audit
  (2026-09-01): 7 gateways, "one identical workload (900 requests on each of the five scored
  platforms, 450 on Groq and Cerebras)", scored "from invoiced cost, p50/p95 latency,
  coverage, reliability, and update cadence".
- Its agent comparison says outright what was not tried: "Task-credit cost per job is
  untested", "Actual account charges are untested".
- Its speed data is Artificial Analysis'. Its own work is statistical: the composite, and the
  estimated positions for 137 of 224 ranked models.

**What a single headline number hides.** On GPT-6 Astra's ARC-AGI-3:
- OpenAI's launch table says **99.9%**, which is the number llm-stats.com shows ("Responses API
  harness with retained reasoning / compaction").
- ARC Prize ran it twice on its Semi-Private set
  (https://arcprize.org/results/openai-gpt-6-astra): **62.7%** with its standard harness at max
  reasoning, and **99.9%** with the provider-adapter harness at high reasoning (98.6% at max). So
  OpenAI's number was reproduced.
- benchlm.ai lists 62.7% for ARC-AGI-3, and 98.55% separately as "ARC-AGI-3 Provider Adapter".
- One model, one benchmark, 37 points apart **depending on the harness**. A page that shows one
  number without the setting tells the reader less than it seems to.

## Their gaps (where a site of ours could be better)

Measured on 2026-10-25 unless stated.

1. **Nobody independent runs the tests.**
   - Both sites publish other people's numbers. Lab numbers come from the lab's own harness,
     effort level and tool access, and the GPT-6 Astra case above shows how far the harness
     alone can move a score.
   - A fixed test set we run ourselves on every new model, the day it ships, would be the only
     original capability number either site would have to cite.
2. **The same benchmark name holds different tests.**
   - 86 (model, benchmark) pairs appear on both sites. 76 agree within half a point; **10
     differ**, by 1 to 64.5 points (and an Elo or rating filed against a percentage).
   - In each case the two sites took different variants of the "same" result:
     - with tools vs without (HLE: 28.2 vs 41.5 on GPT-5.4 mini);
     - partial vs strict scoring (OSWorld 2.0: 81.8 vs 48.7 on Claude Opus 5.5);
     - pass@5 vs pass@1 (ZEROBench on Kimi K3);
     - a search agent vs a plain model (SimpleQA on DeepSeek R1: 92.3 vs 27.8);
     - agent mode (SWE-bench Verified: 44.6 vs 57.6);
     - an Elo filed against a percentage (GDPval-AA, CodeForces).
   - The setting sits in a footnote field, not in the number a visitor reads. One setting per
     benchmark, shown next to the score, fixes that.
3. **They are slow and miss models.**
   - Of the named language-model releases in ai-tldr.dev's feed from the last 30 days (26),
     llm-stats.com lists 12 (46%), benchlm.ai 15 (58%), at least one of them 16 (62%).
   - Kimi K3.1 Pro (Moonshot's 3T-class model, live in its apps and API on 2026-10-23, open
     weights promised by November 4) was on neither two days later.
     Liquid's LFM2.5-24B-A2B, Mistral's Timestral and Z.ai's GLM-Legal were on neither after
     10-13 days.
   - The name matching is approximate and the feed includes niche models, so read these as
     ±10 points.
4. **Image, video, voice and music models are barely covered.**
   - The last 30 days' generation and speech releases, checked by hand:
     - **image and video:** FLUX 3 Image, FLUX 3 Image Klein, Krea 3, Qwen-Image-2.1-Turbo,
       Kandinsky 6.0 Video. On neither site, 0 of 5.
     - **voice and speech:** Eleven v4, Grok Voice 3.0, Block's Dessa, Mistral's Voxtral 3,
       Fish Audio Drama 3. benchlm.ai lists the first three; llm-stats.com none.
   - llm-stats.com's image/video arena is archived. benchlm.ai has 53 voice benchmark pages
     and media price lists, but no quality measurement of its own.
   - This is the gap closest to what this repo already does. It has measured, on real
     production briefs:
     - seven image models for character consistency: face-edit drift 0.2-3.5%, price per
       picture $0.019-0.136, one at 57 s a picture, one unusable;
     - 72 pictures on 8 models for $1.78;
     - TTS voices for transcription accuracy and speaker similarity to a narrator.
   - All three are in `docs/reference.md`. A "models for video makers" board built on tests
     like these has no competitor here.
5. **Speed and real cost are not really measured.**
   - llm-stats.com's latency rests on single-digit request counts, and benchlm.ai copies
     Artificial Analysis.
   - Neither measures **cost per finished task**. Reasoning models spend wildly different
     token counts on the same job, so list price per million tokens (what benchlm.ai's "score
     per output dollar" uses) is not what a task costs.
   - Running our own test set produces exactly that number as a by-product: tokens and dollars
     per task, per model.
6. **The ranking is opaque or partly estimated.** llm-stats.com describes its score in words
   and shares the formula only "with researchers, customers, and partners". 61% of
   benchlm.ai's ranked positions (137 of 224) are estimated from peers and lineage, and its own
   back-tests list where that fails.
7. **A third of benchlm.ai stands on a source that forbids it.** 31% of its score rows and all
   its speed data are Artificial Analysis'. The Artificial Analysis terms fetched (dated 2024)
   allow personal non-commercial use only and forbid building a competing site on it.
   benchlm.ai may hold a licence; nothing on its pages says so.
8. **No video.** Google puts three YouTube videos in the top seven organic results for "new ai
   models", and neither site makes any.

**What they do well, and we should match:**
- a source link on every number (both);
- the provider pricing pages and the `/best/*` slices people actually search for;
- markdown mirrors, `llms.txt` and open JSON for AI answer engines (benchlm.ai);
- a lineage of versions per model.

## What copying them takes

**The data, by source, and whether we may use it:**
- **The labs' own numbers** (system cards, launch posts, model cards on Hugging Face, papers).
  Facts on public pages. They are ~95% of llm-stats.com's rows and 42% of benchlm.ai's. Free
  to collect, as long as each is cited. This is the core.
- **Prices.** Public provider pages, the same.
- **Artificial Analysis** (31% of benchlm.ai's rows, all its speed data). Its terms (the
  copy fetched is dated 2024; a newer version or API terms may differ) grant "personal,
  noncommercial use" only. They forbid copying or republishing, and §2.2(c) says "you shall
  not access the Site in order to build a similar or competitive website, product, or
  service". **Do not build on it** without a licence.
- **Vals AI, Epoch AI, ARC Prize, LMArena and the niche benchmark sites.** Each has its own
  terms; check each one before using it. benchlm.ai records Vals' rows as "licenseGrantIncluded:
  false".
- **benchlm.ai's compiled data.** CC BY-NC: not for a commercial product.
- **llm-stats.com's API.** Open endpoints, but its terms were not checked. Treat it as theirs.

**The work, mapped onto what already exists here:**
1. **Watch for releases.** The ai-tldr-style sweep already does this (`docs/market-ai-tldr-2026.md`):
   it finds the model card the day it ships.
2. **Extract the benchmark table from each card with Claude.** Keep llm-stats.com's discipline:
   one row per number, with source URL, table/section, effort setting, and a
   `self_reported` flag. Run the same verify-the-URL step their news sweep runs.
3. **Normalise.** A benchmark registry (scale, direction, version, successor), a model
   identity map, and effort variants kept separate.
4. **Score.** A within-benchmark relative score that leaves missing data missing, with
   per-model coverage shown. Do not estimate ranks we cannot support: benchlm.ai's own
   back-tests show where that fails.
5. **Measure something ourselves.** llm-stats.com's latency comes from its own traffic and
   benchlm.ai has nothing original. A small fixed eval set run through each new model's API on
   release day would be the only number nobody else has.
6. **Publish few, strong pages.** The leaderboard, `/new-ai-models`, one pricing page per
   provider, the `/best/*` slices people search for, and one page per benchmark. Model pages
   come with it. Generate pairwise pages only for pairs people search; 288,000 of them earned
   benchlm.ai 889 keywords and 8% of its pageviews.

**Where a copy could beat them:**
- **Speed.** On 2026-10-25 neither sitemap listed Kimi K3.1 Pro, released two days earlier,
  although ai-tldr.dev's feed item for it already carried two benchmark scores. benchlm.ai
  already had Block's Dessa and the Nemotron 3.5 variants; llm-stats.com had neither.
  - A web search for "Kimi K3.1 Pro benchmarks" that day returned no page about K3.1 Pro at
    all, only Kimi K3 comparison pages: llm-stats.com, benchlm.ai, Roboflow's playground and
    orcarouter.ai. That is also where the pairwise pages earn their keep: they fill a results
    page when no exact page exists yet.
  - The first page with a new model's own numbers should take its "<model> benchmarks"
    searches in the days they peak.
- **Not leaning on Artificial Analysis.** benchlm.ai's composite and speed data stand on a
  source whose terms forbid exactly this use.
- **Video.** Google shows YouTube videos for "new ai models" (three in the top seven organic
  results); neither leaderboard makes any.

**Where they are hard to beat:**
- llm-stats.com's 5,122 referring domains are sites quoting its numbers. That takes a year of
  being the source.
- benchlm.ai's 764-benchmark registry, provenance per row, deprecation calendar and price
  history are months of careful curation.
- Both have a business behind the site (evaluation services; a data API), so the site does
  not need to earn on its own.
