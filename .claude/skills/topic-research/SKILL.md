---
name: topic-research
description: Find what a research or explainer video should be about, and research it the way KitCut's channels do - a name people already search, a question we can answer from primary data, thin English supply on YouTube, and a film that shows its evidence with critical thinking. Measures search demand and YouTube supply, shortlists topics with numbers, then runs the research as parallel threads (a source line for every number), checks the key facts on their original pages, gathers what people say on X, Reddit, Threads and Hacker News, and writes the fact sheet and chart data the film is made from. Use when asked what to make a video about, for video or topic ideas, for "grounded" or "trending" topics, to research a topic, story, company or claim for a film, for a fact sheet, or before writing the prompt of any research, explainer, "why" or news film.
---

# Researching a topic to cover

The channel's owner put the job this way (2026-10-21): "it MUST BE something where we can
actually research, aggregate information and provide value. it can be something with a 'why' or
'explained'", and "we position these videos as research with a critical thinking".

What the numbers on @kitcut-hq said that day is why this skill reads as it does:

| film | length | views | where they came from |
|---|---|---|---|
| Yandex data centers hit, its bot traffic went quiet (`yrfpNa2HCzU`) | 179 s | 15,931 | **14,855 of 15,586 from YouTube search** |
| What the Starlink Cut in Ukraine Actually Means (`x3jhFVfJ9EA`) | 17 min | 50 | published a day after CNN, CBS and the Daily Show had 1M+ each |
| If Russia Can't Ship the Diesel (`rEMaPdg4e5c`) | 8 min | ~100 | not a searched name |
| Why Stripe paid $7.5B for OpenRouter (`zskY4h5xu0o`) | 6 min | 135 | two months after the news |

Yandex worked because it was one of the first English videos on a viral claim tied to a name
searched 68 million times a month, it showed the measurement (Cloudflare Radar, NetBlocks), and it
said what the data does not show. The big channels came a day later (DW, UFD Tech 1.2M, Patrick
Boyle 1.1M). So: **a name people search, a question data can answer, thin supply, first.**

## Part 1: pick the topic (the pull test)

Do every step with numbers; a topic that fails one is dropped, and the report says which step it
failed.

1. **Read the channel first.** `get_youtube_views` (KitCut MCP) for the channel, 28 days: which
   videos grew, and their traffic sources. Search-led views are the ones this skill is chasing.
   For one video, `get_youtube_views` with `video`.
2. **Candidates.** The last 72 hours: `WebSearch` (mode extended) for the day's tech digests,
   the war's strikes and announcements, outages, filings, fact-checks of viral claims; the
   channel's own beats (what grew in step 1, and its follow-ups). Google Trends' trending RSS
   (`https://trends.google.com/trending/rss?geo=US`, also GB, CA, AU; `trends.py` here parses
   it) is mostly sports and celebrities, so use it to catch a spike, not to find a beat.
3. **Demand.** `keyword_volume` (market-data MCP), English, worldwide, `include_monthly: true`,
   every candidate phrase in one call: the bare name ("anthropic", "yandex"), the question forms
   ("is anthropic profitable", "why are data centers so loud", "how much water does ai use") and
   the news forms ("anthropic ipo"). The best sign is a question form that rose about 10x in a
   year. Keyword Planner ends at the last full month, so this week's spike is invisible there:
   for news, use step 4's views per day instead.
4. **Supply.** `search_videos`, `published_after` 7-14 days back, `order: viewCount`,
   `language: en`, up to five queries a call (each costs 100 of 10,000 daily units). Big answers
   come back as a saved file; `yt_supply.py <file>` prints them as one line each. Read it as:
   - thin English supply and real demand (views per day on the few that exist): a gap, go;
   - mainstream news with 1M+ a day on the same angle: saturated, unless we have data they lack;
   - nobody at all, even small channels: often no demand; check step 3 again.
5. **The data test.** Can the question be answered from primary material: a filing, a
   dashboard (Cloudflare Radar, NetBlocks), a dataset, a court docket, official statistics, the
   company's own page? If all there is is opinion, drop it: there is nothing for us to add.
6. **Fit and the hard rules.** The channel's audience (KitCut: AI and tech, and the tech side of
   Russia's war on Ukraine). Nothing Russian shown in a neutral or flattering light, war films
   openly pro-Ukrainian, no Russian state media as a source (memory: never-feature-russians,
   pro-ukrainian-not-neutral).
7. **Shortlist** three to five, each with: the search numbers, the supply numbers, the data we
   would use, timing (why now, how long the window is) and the risk. Say what was measured and
   dropped, and why, in one line each. Give the sources.

## Part 2: research the chosen topic

### Threads, in parallel

One agent per thread, all launched in one message, running in the background. Split by question,
not by source. For a company or market story the threads that served (the Anthropic IPO film,
`projects/ai-shorts/research/31a`-`31i`):

- the subject's own numbers (filings, reported figures, its own claims);
- the comparison that gives scale (market caps, a whole index, peers);
- the size of the market or the problem;
- comparable events and what happened after (similar IPOs, past strikes, earlier outages);
- the physical constraints (chips, power, construction, logistics);
- unit economics or pricing (including any inconsistency the owner points at);
- legal, regulatory and governance exposure;
- what people say: X, Reddit, Threads, Hacker News, YouTube comments.

Each brief carries: today's date; the film's working question; what the other threads cover (so
they do not overlap); numbered questions; the labels, **MEASURED** (filings, official data,
market data), **REPORTED** (a named outlet citing documents), **ESTIMATE** (an analyst), **CLAIM**
(the company or a party to a dispute); the rules (a source line on every number, read pages with
WebFetch rather than trusting snippets, keep disagreements side by side, flag what could not be
confirmed, invent nothing); the output paths; and a return of at most 350-400 words. Ask for a
"Key numbers" table at the top, then sections, then **Could not confirm** and **Commonly
misreported**, and for 4-8 real pages that would make strong on-screen screenshots.

Files: `projects/<project>/research/<n><letter>-<slug>.md` (the next free story number) and
`projects/<project>/data/<n>/*.csv` with a `source_url` column on every row.

**The web-search budget is shared and small.** A session has 200 WebSearch calls for itself and
every agent it starts; on 2026-10-21 nine threads used them up in about twenty minutes, and the
last threads finished on WebFetch alone. Tell each thread to search a few times, then read known
pages and APIs directly (EDGAR full-text search, the Hacker News Algolia API, a company's own
newsroom, an outlet's article URL), and to say in its file what it could not search for.

### What people say

Briefs for the social thread name the routes that work, because the obvious ones are blocked:

- **Hacker News**: the Algolia API needs no login (`https://hn.algolia.com/api/v1/search?query=...&tags=story`, `&tags=comment`).
- **Reddit**: Chrome's extension refuses reddit.com and the search tool blocks it. Try
  `search.json` with a browser User-Agent via curl, then the archives
  (`arctic-shift.photon-reddit.com/api/posts/search`, `api.pullpush.io/reddit/search/submission/`).
- **X**: WebSearch `site:x.com`, then WebFetch the status page or an `xcancel.com` mirror.
- **Threads**: WebSearch `site:threads.net` / `threads.com`, then the post page.
- **YouTube**: `video_comments` (market-data MCP) on the topic's biggest videos.

Verbatim text only, with author, date, engagement and URL; a post seen only in a search snippet
is marked SNIPPET-ONLY and never shown on screen.

### Check it yourself

Agents misread. Two that reached a fact sheet before a check caught them: "21,949 drones in all of
2025" (a misreading) and a fact sheet saying refining held "5.1 to 5.5" when its own data file's
low was 4.9. So, before anything is written for the film:

- re-open the original page of **every number that will be spoken or drawn**, and of every
  quote; prefer the primary document over a relay (a filing over an article about it);
- check the fact sheet's prose against its own CSVs;
- check dates against the event, not the article ("recently" is not "the day of the deal");
- note which outlets and people may be named on screen (a source line once named a Moscow-titled
  outlet and cost a re-render);
- **measure a comparison the way its source measures it.** Jay Ritter's table of IPO returns by
  price-to-sales uses the trailing twelve months of sales in the prospectus: Anthropic at $2T is
  ~30x on its latest quarter annualised (Ritter's 20-40x band, -16% against the market) but ~100x
  his way (the >40x band, -58.5%). Quoting the scary band against the friendly multiple is the
  kind of error a critical film cannot make.

### The two documents the film is made from

- `projects/<project>/facts/<n>-<slug>.md`, the **fact sheet**: every number with its label and
  source line; the quotes, verbatim, with who said them and where; **Unconfirmed / not known**;
  **Commonly misreported**; **The film must not say**; the outlets and people allowed on screen.
- `projects/<project>/facts/<n>-<slug>-data.md`, the **chart data**: every value a chart draws,
  with its unit, period and source line, ready to be typed into a chart. Charts by period end on
  whole periods (a partial year once made a rise look like a fall).

### Pictures: capturing the real pages

The screenshots skill's `shoot.mjs` (headless Edge) takes them; keep the raw shots in
`projects/<project>/logos/src/<n>/` and the finished pictures in `logos/`. What cost time on
2026-10-21:

- **Take the viewport, crop by eye.** Clipping to `h1` on a page that is still laying out returns
  a sliver; a full viewport shot cropped with PIL afterwards does not. Keep the masthead and the
  date line in the crop; cut ads and cookie banners out (click "accept" in `steps` when a dialog
  covers the page).
- **SEC filings refuse headless browsers** ("Undeclared Automated Tool"). Download with curl and a
  declared user agent (`-A "<org> research <contact address>"`), then shoot the local file. In
  inline-XBRL filings, find the text node and climb to the block that holds both phrases you want;
  a prospectus laid out with absolute positioning will not crop by element, so show its sentence as
  a big-number card credited to the filing instead.
- **Some news sites block headless browsers** (Investing.com, several finance sites: 403). Find
  the same report on a relay that renders (TNW, Reuters via Euronext, Yahoo Finance).
- **X posts** render logged out at `https://platform.twitter.com/embed/Tweet.html?id=<id>` (clip
  `article`); `api.fxtwitter.com/status/<id>` gives the exact text and counts. Hacker News pages
  render clean.
- **Boards, not slides of tiny pages.** Several sources go on one board as real crops on paper,
  each with a credit line: `boards.py` here, from a JSON spec. Stack wide crops in rows; render at
  3840x2160 as JPEG so the film can zoom into one card and stay sharp.
- **The studio takes 9 pictures and 3 text files a film**, each under 4.4 MB. Pictures are
  upload1..upload9 in the order attached; text files become doc1..doc3 in their order. A research
  film's picture budget usually goes: three opening pages, then one board per section.

## Part 3: hand it to the film

The prompt that made the Yandex film is in its record (`get_film studio-20261011-203316-ijrecx`,
`idea_full`); start from it. What carries over:

- **Title starts with the searched name** ("Yandex data centers hit ...", "Anthropic's IPO ...").
- **The opening is the hook.** At 0.0 s the news is on screen: a strap, the film's own headline
  in very large type, and the real source pages piling in, one every two seconds, each named in
  the lower third. The first sentence is the news; the second is why a viewer should stay. In the
  first ten seconds, add a number that surprises and say the question the film will answer, so
  the viewer has a reason to stay to the end. Never open on a mystery, a clue or a scene-setter.
- **"Here's what we know"**, one fact at a time, each with its proof on screen as it is said.
- **Nothing static** (memory: long-films-must-move-too). Charts are built on screen: bars grow,
  lines draw left to right, figures count up as they are said; pages sit under a slow push or
  drift, and the camera moves onto the line being read. Nothing fancy: the motion serves the
  number.
- **Critical thinking, said out loud**: the strongest case on each side, CLAIM / ESTIMATE labels
  on screen, "what the data does not show", and what would change the conclusion.
- **The end** is the open question, nothing after it. No music; the voice as in the Yandex prompt
  (Orus, "Confident and engaged, like a reporter walking a viewer through evidence").
- Real pictures only, never drawn stand-ins; screenshots cropped so masthead and headline are
  whole and readable on a phone.
- Length: what the evidence needs, usually 3-6 minutes. The 17-minute film did not fail on
  length alone, but nothing so far says longer earns more. Count the narration's words: the
  reporter voice runs about 165-175 a minute, so 1,000 words is about six minutes; ask the studio
  for a few seconds more than that, since it refuses a film shorter than its sound.
- **Write the narration yourself, word for word,** as a third document (doc3: the running order,
  one line per spoken sentence, with what is on screen during it), and tell the studio to use it
  exactly. That is how every spoken number stays the checked one and the hooks land where planned.
  `examples/` here holds the whole set from the Anthropic IPO film (2026-10-21): `prompt.md`,
  `fact-sheet.md` (doc1), `chart-data.md` (doc2, with how each chart moves), `running-order.md`
  (doc3) and `board-spec.json`. Copy their shape, not their facts.
- A new format gets a 20-45 s pilot of its opening first (memory: raw-cut-before-full-production).
- Before the owner sees it: the `video-review` skill with a fresh agent, and every spoken line
  read against the fact sheet.

## Part 4: record

A dated entry in `projects/<project>/journal.md` (what was researched, what was checked by hand,
what was left out and why), and a memory when the owner says something new about how topics are
chosen. Publish timing matters more than polish for a news-led topic: say so when proposing.

## Files here

- `yt_supply.py <saved search_videos result>`: one line per video (views, views a day, date,
  length, language, channel, title), per query, from a result the tool saved to a file.
- `trends.py [GEO ...]`: Google Trends' trending searches now, with traffic and the top news
  headline, for the given countries (default US GB CA AU).

- `boards.py <spec.json>`: real screenshots laid out as a board, a credit line under each card
  (spec format in its docstring). Needs Pillow: run it with the repo's `.venv` Python.

The first two are stdlib Python; run them with `python -I`.
