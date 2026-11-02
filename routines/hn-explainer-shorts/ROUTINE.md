# Routine: two explainer Shorts from Hacker News, every 12 hours

The owner's ask (2026-11-01): every 12 hours, read Hacker News, find the top and fast-growing
topics, score each for a video, pick **two**, and make each a **60-second Short** with KitCut that
answers "why" or "what it actually means", then **publish it on the KitCut YouTube channel**.

What a topic must have, all three at once:

1. **Demand pull.** People already search for its name.
2. **Thin supply.** YouTube does not already have it covered: a generic video about Nvidia gets no
   traffic, because everyone covers Nvidia.
3. **Research that adds a lot.** After research we can tell the viewer something the headline did
   not: a mechanism, a number, a consequence, what it changes for whom.

The model case is the **Yandex** film (`yrfpNa2HCzU`, KitCut channel, 15.9k views, 95% from
YouTube search). "Yandex" was a big search name for decades; "Yandex + Ukrainian drones" was new, so
nobody had a video on the pair; and the research (Cloudflare Radar, NetBlocks, what the data does
not show) was worth watching. Its top search terms were "yandex" (1,574 views) and "yandex data
center" (1,114). **An established name with a new event** is the pattern: the name brings the
searches, the newness empties the shelf, the research is the value.

Two kinds of topic, both allowed:

| | breaking | evergreen |
|---|---|---|
| shape | a searched name + a new event, hours to two days old | a lasting "why X" / "what X actually means" about a searched name |
| demand | the name's monthly searches (the pair is too new for any keyword data) and how fast it climbs on HN | the question's own monthly searches |
| supply | English videos on the pair in the last 3 days: near zero is the opening | videos on the question ranked by views: thin, old or poor is the opening |
| timing | now: hours matter, the big channels arrive a day later | no rush |

At most **one** evergreen a run, so a breaking story always has room.

---

## Settings

- KitCut project: **HN explainer Shorts**, `p-mlgnibpqat` (9:16, 60 s, collage, KitCut channel,
  its brief carries the whole format; `brief.md` beside this file is a copy).
- YouTube channel: **KitCut**, `UC2PK9SXpePZSRkT3LqiOgeg`. Publish **public** (owner, 2026-11-01:
  "we need auto publish too on the kitcut yt channel").
- Tools: the **KitCut** connector, the **Builders-HQ** connector (`keyword_volume`,
  `search_videos`), your own web search and fetch, Bash.

## 0. Before you start

1. `get_credits` (KitCut). Fewer than 300 credits: stop and say so.
2. `get_project p-mlgnibpqat`: its episodes are what earlier runs made. **Never make a topic
   again** that an episode of the last 14 days covers, unless something big and new happened to it
   (then say what).
3. `get_youtube_views` channel `UC2PK9SXpePZSRkT3LqiOgeg`, range 28: note the `search_terms`. A
   candidate near a term that already brings views has a proven audience here.
4. `get_playbook` (KitCut) once: sections 3 to 5 are how you research and check. This file only adds
   what is different for a 60-second Short.

## 1. Read Hacker News

```bash
python3 -I routines/hn-explainer-shorts/hn.py --limit 40
```

Stories ranked by points per hour, with points, comments, age and front-page rank. If it says HN
is unreachable from here, `WebFetch` the URLs it prints instead (the same public APIs).

## 2. Turn stories into candidates

Group stories about the same thing. Then, for each one that could be a film, write one line:
**anchor** (the established searched name: a company, product, place, law, technology), **the new
thing**, **the question** the film answers ("why", "what it actually means"), **kind** (breaking or
evergreen). Aim for 8 to 12 candidates.

Drop at once, with a word why:
- no searched anchor (a personal Show HN, an essay, a small project nobody has heard of);
- nothing to research (pure opinion, a rant, a link to a tool);
- party politics or a side in a political fight;
- anything that would show Russia, its companies or its people as neutral or admirable (the tech
  side of Russia's war on Ukraine is fine, told from Ukraine's side);
- a name that is the generic topic itself with no new angle ("AI", "Nvidia", "OpenAI" alone).

## 3. Demand

One `keyword_volume` call for every candidate, `language: "en"`, worldwide, `include_monthly:
true`: the bare anchor, the pair ("yandex drone"), and the question forms ("why is X", "what is X",
"X explained"). Read it as:

- **anchor ≥ 10,000 a month**: an established name. Under ~2,000: weak, unless the question form
  itself is searched.
- the pair or the question **rising** month on month (10x in a year is the best sign).
- Keyword Planner stops at the last full month, so a breaking pair shows nothing: that is normal,
  judge breaking demand by the anchor and by HN's points per hour.

## 4. Supply

`search_videos`, at most **two calls of five queries** a run (each query costs 100 of the
connector's 10,000 daily units, shared with other work): `language: "en"`, `order: "viewCount"`,
`max: 10`. Breaking: the pair, `published_after` three days back. Evergreen: the question, no date
filter. For each, count the videos **actually on the angle** and note the top one's views and views
a day. Read it as:

- 0 to 2 on the angle, none above ~20k views: **open**.
- a few small ones that only repeat the headline: **open** (we bring the research).
- big news channels with 1M+ on the same angle, or ten fresh explainers: **crowded**, drop it.

## 5. Value of the research

For each survivor, write: the **primary sources** you would use (the filing, the company's post,
the dataset, the dashboard, the court docket, the paper), and **the one sentence a viewer learns
that the headline did not tell them**. Score it 1 to 5. A 1 or 2 (research would only repeat the
headline, or there is no primary source) is dropped.

## 6. Pick two

A table of every candidate, with columns: anchor, new thing, kind, anchor searches/month, pair or
question searches, supply (videos on the angle, top views), value (1-5), verdict and why. Pick the
best **two** by the balance of all three, at most one evergreen. If only one passes, make one; if
none passes, make none and say why. Never lower the bar to reach two.

## 7. Research and write (both topics in parallel)

One sub-agent per topic (Task tool), both launched together. Each follows the playbook's sections
3 and 4 and returns the three documents:

- **doc1, the fact sheet**, the playbook's exact table shape: every number with its label, source,
  URL and the exact quote from the page. Primary sources first. `## Unconfirmed`, `## Commonly
  misreported`, `## The film must not say`.
- **doc2, the chart data**: at most one or two charts (a Short has no room for more). If there is no
  chart, still send doc2 with a one-line note "No chart in this film."
- **doc3, the script, word for word**, for **about 60 seconds: 140 to 165 words** in 7 to 10 lines.
  L01 is the news (who did what, 14 words or fewer); L02 is the question ("So what does that
  actually mean?"); then three or four steps of evidence; then one line of what is not known; the
  last line is the open question. Each line's direction names what is on screen (which page, with
  its URL and `keep`, what is underlined; which chart; EXPLAINER and its small diagram).

**A page that will not load** (WebFetch or curl gets 403, an empty page, a "verify you are human"
wall, or a page that needs JavaScript): open it in the real browser on kc-local, the owner's
studio machine, which this environment reaches over ssh. It is a headed Edge (profile `reader`,
no sign-ins), so sites that refuse a headless fetch usually load (measured: fortune.com, 403 to
curl, loads there):

```bash
ssh kc-local 'xb reader open "https://fortune.com/..." >/dev/null; sleep 5; xb reader text' | head -c 20000
ssh kc-local 'xb reader url'      # where it actually landed
```

One page at a time; `reader` only (never `VideoMakers_io`, that is a signed-in X account). This is
for public pages: never get around a paywall or a login, and never solve a CAPTCHA. A page that
still will not show its text is left out, or replaced by another page that says the same. Tell the
sub-agents this too.

Then you (not the sub-agent) run the checks for each:

1. `check_research` until clean. It gives the seconds; if it says more than 75, cut lines.
2. `check_sources` on doc1, 20 rows a call. Fix `number` (quote to the page's words), resolve
   `missing` and `unreadable` (another page, or drop the number and its lines).
3. If the number the film rests on cannot be backed, drop that topic and say why. Do not
   substitute a weaker topic in the same run unless it already passed steps 3 to 5.

## 8. Make the films

`make_film` for each, at once (the account makes two at a time; a third waits in its line):

- `project: "p-mlgnibpqat"`, `frame: "9:16"`, `look: "collage"`, `seconds`: what
  `check_research` said (a multiple of 5);
- `documents`: `[{name: "fact-sheet.md", text: doc1}, {name: "chart-data.md", text: doc2},
  {name: "script.md", text: doc3}]` in that order;
- `idea`: first line the film's question; then `LABEL: BREAKING` (news under two days old) or
  `LABEL: EXPLAINED`; `HEADLINE: <eight words or fewer>`; `DATA AS OF <date>`; the pages to
  photograph if not all are in doc3's directions; how to say any name the voice could get wrong.

Then follow both with `get_film` (`wait_seconds: 50`, again and again) until done; a 60-second film
takes about 15 to 30 minutes. A film that did not finish: read why; `remake_film` once only if the
reason was the studio's, not the documents'.

## 9. Publish

For each finished film:

1. `get_film`: read its narration and look at what it reports. If a spoken line says something
   doc1 does not, do **not** publish it; say so in the report.
2. `publish_to_youtube`: `film`, `channel: "UC2PK9SXpePZSRkT3LqiOgeg"`, `privacy: "public"`,
   `thumbnail: "youtube"`, and your own
   - `title`: starts with the searched name, says the question or the answer, no claim the film
     does not support, ends with ` #shorts`, 70 characters at most before it;
   - `description`: two or three plain sentences of what the film finds, `Data as of <date>.`,
     then `Sources:` and one line per source (outlet, title, URL), then `Made with KitCut:
     https://kitcut.ai`;
   - `tags`: the anchor, the pair, the question forms.
3. `get_youtube_post` until it is live, for the video's link.

## 10. Report

End the run with this, and nothing after it:

```
HN explainer Shorts, <date> <time> UTC

| candidate | kind | anchor/mo | pair or question | supply on the angle | value | verdict |
|---|---|---|---|---|---|---|
...

Made:
1. <title> - why it won (the three numbers) - film <link> - YouTube <link>
2. ...

Dropped after research: <topic>: <why>   (or "none")
Look at: <anything a person should check>   (or "nothing")
Spent: <credits> credits, <search_videos queries> YouTube queries
```

## Never

- More than two films a run; a film from a topic that failed a step; lowering the bar to reach two.
- A number without a page you read and a quote you saw on it.
- Publishing a film whose narration says what doc1 does not.
- Anything but the KitCut channel; any channel but public there.
- Getting around a paywall or a login.
- Russian sources shown as neutral or admirable; party politics.
