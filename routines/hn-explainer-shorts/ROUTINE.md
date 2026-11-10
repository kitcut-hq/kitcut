# Routine: two or three explainer Shorts from Hacker News, every 12 hours, published by itself

The owner's ask (2026-11-01): every 12 hours, read Hacker News, find the top and fast-growing
topics, score each for a video, pick, and make each a **Short of 60 to 120 seconds** with KitCut that
answers "why" or "what it actually means", then **publish it on the KitCut YouTube channel**.

**The run decides and publishes by itself** (owner, 2026-11-04: "Update the routine to publish 2-3
shorts each trigger without my approval. Make it decide for me"). One scheduled run does all of it:

- **Scout**: steps 0 to 6, then **6c** (the shortlist goes to the ideas page as the record, which
  also keeps the next run from repeating a story; nobody is asked to pick).
- **Decide**: **6d** picks the topics and angles, **6b** checks the evidence behind them.
- **Make and publish**: 7, 8 and 9 for **two or three** films, public on the KitCut channel.
- **Tell the owner**: section 10, once, with the YouTube links.

No question to the owner anywhere in the run: where this file leaves a choice, make it, and say in
the report what you chose and why. The quality gates still stand: a film that fails a gate is not
made, even if that leaves fewer than two (say why in the notification); a weak film is worse than
none.

`MAKE.md` still works for a pick the owner makes by hand on the ideas page: it makes exactly that
pick, on top of what the run made.

The ideas page is `routines/hn-explainer-shorts/web/` (Vercel project `hn-ideas`).

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

**This is not a breaking-news desk.** The owner (2026-11-02): "its not only about breaking news
reporting. we are happy to hype as long as we contribute extra value". Riding a story everyone is
talking about is welcome; retelling it is not. What we sell is the part the coverage left out.

Three kinds of topic, all allowed:

| | breaking | hype | evergreen |
|---|---|---|---|
| shape | a searched name + a new event, hours to two days old | a story the whole internet is on right now, any age, while searches for it are still hot | a lasting "why X" / "what X actually means" about a searched name |
| demand | the name's monthly searches and how fast it climbs on HN | the name's searches, plus the views a day the big videos on it are still getting (they show the wave is still rising) | the question's own monthly searches |
| supply | English videos on the pair in the last 3 days: near zero is the opening | **crowded is fine**: judge the supply of OUR ANGLE, not of the story (see step 4) | videos on the question ranked by views: thin, old or poor is the opening |
| timing | now: hours matter | while the wave lasts (days) | no rush |

At most **one** evergreen a run.

---

## Settings

- KitCut project: **HN explainer Shorts**, `p-mlgnibpqat` (9:16, 60 to 120 s, collage, KitCut channel,
  its brief carries the whole format; `brief.md` beside this file is a copy).
- YouTube channel: **KitCut**, `UC2PK9SXpePZSRkT3LqiOgeg`. Publish **public** (owner, 2026-11-01:
  "we need auto publish too on the kitcut yt channel").
- Tools: the **KitCut** connector, the **Builders-HQ** connector (`keyword_volume`,
  `search_videos`), your own web search and fetch, Bash.

## 0. Before you start

1. `get_credits` (KitCut). Fewer than 400 credits (three films of up to 120 s): stop and say so.
2. `get_project p-mlgnibpqat`: its episodes are what earlier runs made. **Never make a topic
   again** that an episode of the last 14 days covers, unless something big and new happened to it
   (then say what).
3. `get_youtube_views` channel `UC2PK9SXpePZSRkT3LqiOgeg`, range 28: note the `search_terms`. A
   candidate near a term that already brings views has a proven audience here.
4. `get_playbook` (KitCut) once: sections 3 to 5 are how you research and check. This file only adds
   what is different for a Short.

## 1. Read Hacker News

```bash
python3 -I routines/hn-explainer-shorts/hn.py --wide
```

`--wide` lists every story of the last 48 hours with 5 or more points (about 300), not just the
front page. **Read all of it: points are not the signal.** On 2026-11-02 the front page's top
stories were HN meta and essays, while the stories that passed every test sat far down: OpenAI
ending unlimited ChatGPT prompts (40 points), Proton's CEO calling a security test "loser
thinking" (59 and 9 points), and the year's biggest crypto hack, Binance's $6.3B (20 points).

Stories ranked by points per hour, with points, comments, age and front-page rank. If it says HN
is unreachable from here, `WebFetch` the URLs it prints instead (the same public APIs).

## 2. Turn stories into candidates

**Never send a story that is already on the page.** First run `ssh kc-local hn-ideas-recent`: it
lists every topic sent in the last 7 days (with its HN links, and whether the owner skipped or
picked it). A story already there is dropped, unless something big and new happened to it; then
send it as a new topic that says what is new. (2026-11-02 the Sam Altman RAM story showed twice.)

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

### The stakes test (before any numbers)

A big searched name is not enough: "Postgres 19 is late" had an 823k-a-month name, a fresh angle
and good data, and the owner rejected it at once: "the update itself isnt significant. who care if
it is going to be released today or next week?" Every candidate gets one sentence in this exact
form:

> **[who]** now **[what changes for them]**

and passes only if all three hold:

1. **It changes something people care about**: their money, safety, privacy, job, rights, a
   product or service they use every day, or a war. "Postgres users now get version 19 three weeks
   later" fails; "everyone online now sees fewer russian bot posts, if the claim holds" (Yandex)
   passes; "every car in 5,000 US towns is now logged by a company a city could not switch off"
   passes.
2. **There is tension**: something broke, someone got caught, a big claim needs checking, one side
   is fighting another. A release, a launch, a benchmark, a niche product existing: no tension.
3. **Someone who is not a developer would tap it.** HN's readers care about release dates;
   YouTube's do not.

Write the sentence into the table. A candidate that fails is dropped here, whatever its numbers.

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
- big news channels with 1M+ on the same angle, or ten fresh explainers: that **angle** is
  crowded. **Do not drop the story: look for the angle they all left out.**

  **Finding the angle is judgement, not a checklist.** Read the titles and descriptions of the top
  videos and write down what they all already say. Then ask: *after watching all of them, what
  would a sharp viewer still want to know, that we can settle with evidence?* The answer differs
  with every story, and its shape is never fixed in advance. Shapes it has taken:
  - **checking a claim everyone repeats**: Yandex. The viral claim was "russian bots went quiet
    after the strike"; nobody had measured it; the film measured it (Cloudflare Radar, NetBlocks)
    and said what the data does not show. ChatGPT's December limits (2026-11-02) are the same shape:
    headlines said "the end of unlimited ChatGPT"; OpenAI's own help page says Instant chat "will
    not draw from your usage", and only the stronger models share a budget with Codex, so the film
    is "what it actually means" for a paying user;
  - **how something was even possible**: Binance's $6.3B hack (2026-11-02). Everyone told the
    night step by step (CNN 1.4M, IGR 1.2M, Gloam 844k, Coin Bureau 424k, DW, BBC); nobody asked
    how one engineer's laptop could be allowed to move $6.3 billion, or why it was Binance, the
    biggest and supposedly safest exchange (one 1.2k-view Short between them);
  - what it changes for the viewer, the number nobody put in scale, the precedent everyone forgot.

  Two things are never an angle: an answer everybody already knows ("it was North Korea"), and a
  retelling of what the top videos already told.

  **A recreation is a format of its own, for catastrophes, heists, crashes, attacks and killings**
  (owner, 2026-11-02: "a recreation of what happended might be a good format. it works for
  catastropes, kills etc"). It is not a retelling: it rebuilds the event step by step from its
  evidence, with times on screen, and shows the detail the news segments skipped. Binance is the
  model case: TRM Labs' on-chain record has Binance's own hot wallet signing 50 authorizations that
  handed it to a sweeper contract, emptied in 3 minutes 24 seconds, then swept six more times over
  the next three and a half hours, with no private key stolen. Choose it when such a primary record
  exists (on-chain data, flight or ship tracking, logs, court filings, official timelines).

  **Write the angle, and later the title, as the question or the recreation, never as a news
  summary** (owner, 2026-11-02: "the titles sound all like reprinting existing news. at least the
  first part. the second part that starts with why or what or explaining is better"). Not
  "Proton's CTO says most human code review will end. So who checks the code?" but "Who checks
  Proton's code now?"; not "Binance lost $6.3B to North Korea" but "Binance's $6.3B hack, recreated
  minute by minute". A hype story with a real angle is a **strong**
  pick: demand is at its peak and the big videos feed searches for the name. Supply is then
  counted for that angle's own question.
- **Bot channels do not count as supply, and they warn you.** Auto-made news Shorts (channels like
  "Daily Tech", "Shield Matrix", "Isetnews") cover HN's front page within hours and get 5 to 100
  views (measured 2026-11-02 on the Flock story: four of them, 5-11 views each). Ignore them when
  counting, but know that a headline retold in 40 seconds is already free: our film must carry what
  research found, not the headline.
- **Weigh supply against demand, not alone.** One 30k-view Short on a name searched a million times
  a month is still an open shelf (the Yandex film went up beside DW and 1M-subscriber channels and
  won on search); the same Short on a name searched 2,000 times is the whole market. Say which.

## 5. Value of the research

For each survivor, write: the **primary sources** you would use (the filing, the company's post,
the dataset, the dashboard, the court docket, the paper), and **the one sentence a viewer learns
that the headline did not tell them**. Score it 1 to 5. A 1 or 2 (research would only repeat the
headline, or there is no primary source) is dropped.

## 6. Shortlist

A table of every candidate, with columns: anchor, new thing, **stakes sentence**, **news date** (the event's own date,
not the HN post's age: HN often surfaces week-old news), kind, anchor searches/month, pair or
question searches, supply (videos on the angle, top views), value (1-5), verdict and why.

Two hard gates before the balance:
- **The title's first words are a searched name ≥ 10,000 a month**, and a viewer typing them would
  want this film. "Postgres" (823k) leads a Postgres-19 film; a film titled "Seoul Viosys..." (320)
  or "Rare-earth-free LEDs..." (50) has no searchers, even if "rare earth" (49.5k) is nearby. If the
  only big name is a loose neighbour of the story, it fails demand.
- **Breaking means the event is under 48 hours old.** Older news is hype (if searches and the big
  videos' views a day are still high) or evergreen; say which.
- **The angle adds something the top videos do not.** Write the angle as a question, and next to it
  what the top three videos on the story already say. If our film would say the same, drop it.

Then **shortlist three to six** by the balance of all three. If none passes, send none and say why.

**Print the whole table as a message**, so the run's log shows how the topics were chosen, and
repeat it in the report.

## 6c. Send the shortlist to the ideas page (the record)

The page leads with the question, not the metadata (owner, 2026-11-02: "focus more on the most core
and base question instead of un focusing on metadat"): for each topic write first its **one core
question**, the base question a curious viewer has, in plain words. Then, for each shortlisted topic, write **two or three angles**, each a different film that could be
made: its `format` (`explainer`, `recreation`, `claim check`, or another you can name), its `title`
written as the film's question or recreation (never a news summary), and `why`: one line on what
it shows that the top videos do not, with the number or document that would carry it if you know
it. Steps 2 to 5 are all the angles need; the research for the chosen ones comes in 6b and 7.

Then send the run, once, through kc-local (it holds the page's write token; nothing secret is in
this repository or the prompt):

```bash
ssh kc-local hn-ideas-post < run.json      # answers {"ok":true,"run_id":...,"ideas":N}
```

`run.json` (the `//` notes are for you; send plain JSON):

```json
{
  "run_at": "2026-11-02T14:02:00Z",
  "summary": "one or two sentences: what was hot, what was dropped and why",
  "ideas": [
    {
      "id": "binance",                       // short, unique in the run
      "topic": "Binance loses $6.3B in the largest crypto hack",
      "question": "How could one laptop move $6.3 billion out of the biggest exchange?",  // the ONE core question the story raises: the page shows it largest
      "kind": "breaking | hype | evergreen",
      "news_date": "Oct 29",                 // the event's own date
      "stakes": "[who] now [what changes for them]",
      "searches": "\"binance\" 3.4M/mo",
      "supply": "CNN 1.4M, Gloam 844k; nobody shows how the signer was made to sign",
      "hn": [{"title": "...", "url": "https://news.ycombinator.com/item?id=...", "points": 20}],
      "sources": [{"title": "TRM Labs", "url": "https://..."}],   // only pages you opened
      "angles": [
        {"id": "a1", "format": "recreation", "title": "Binance's $6.3B hack, recreated minute by minute",
         "why": "TRM's on-chain record: 50 signed authorizations, emptied in 3 min 24 s, no key stolen"}
      ]
    }
  ]
}
```

Every link must be one you actually opened in this run; never write a URL from memory. Do not
email or notify the owner here, and do not wait for a pick: go straight on to 6d. (Posting matters:
`hn-ideas-recent`, which the next run reads in step 2, only knows what was posted.)

## 6d. Decide: which two or three to make

Take the shortlist in order of the balance of demand, supply on the angle and value, and choose
**four** to check (fewer if fewer passed), each with the one angle the evidence can carry best
(a recreation where a primary record exists; a claim check where a big claim needs checking).
Rules for the choice:

- **different subjects**: never two films on one company or one story;
- **at most one evergreen**, and breaking or hype first: their searches fade, an evergreen keeps;
- prefer a candidate near a search term that already brings the channel views (step 0.3);
- prefer what can be shown: a primary page, a dataset, a filing; a story whose only source is a
  forum post or a tweet is checked last.

Then 6b on all four at once. **Make the STRONG ones, best first: three when three are STRONG, never
more.** If fewer than two come back STRONG, make only those (a MAYBE is never made) and say why in the
notification. Write each choice and the reason into the report.

## 6b. Quick research check, before anything is made

The owner (2026-11-02): "what if we do a shortlist using this algo and then a quick research check
if we can contribute and make a strong video before actually making it?" A topic can pass every
number and still have nothing behind its angle; finding that out costs minutes here and a film
later.

One sub-agent per shortlisted topic, all launched together, each about 15 tool calls (web search and
fetch, nothing else). Give each the story, what the top videos already say, and the candidate angle,
and ask it to find whether the evidence actually settles the angle's question, and to return:

```
ANGLE: the question the film answers (or the recreation it rebuilds), as a title would say it:
       no news summary in front
ANSWER IN ONE SENTENCE: what the evidence says
KEY EVIDENCE: 3-5 facts/numbers, each with source and URL, read on the page
WHAT THE TOP VIDEOS DON'T SAY: one line
THE MOMENT: the one fact or document the film is built around
GAPS/RISKS: unverified, claim-only, paywalled, legal
VERDICT: STRONG / MAYBE / NO, and why
```

The sub-agent may propose a better angle than the one it was given; take it if the evidence is
better. **Make only STRONG topics**: two or three, at most one evergreen (6d). A MAYBE is not made; a
NO is dropped. Print every brief in the log and in the report, the dropped ones too: they show what
the gate caught.

## 7. Research and write

One sub-agent per topic (Agent tool), all launched together, each carrying its own film through 7,
8 and 9 to a public Short (measured 2026-11-04: two such agents, about 40 minutes each, both live).
Brief each like a peer: the story, the angle, the sources already opened, what the top videos
already say, and the rules of this file and `MAKE.md` step 2 (real screenshots). Each follows the
playbook's sections 3 and 4 and writes the three documents:

- **doc1, the fact sheet**, the playbook's exact table shape: every number with its label, source,
  URL and the exact quote from the page. Primary sources first. `## Unconfirmed`, `## Commonly
  misreported`, `## The film must not say`.
- **doc2, the chart data**: at most one or two charts (a Short has no room for more). If there is no
  chart, still send doc2 with a one-line note "No chart in this film."
- **doc3, the script, word for word**, **60 to 120 seconds, as long as the evidence needs and never
  padded** (owner, 2026-11-02: "dont limit to 60 sec. if needed go up to 120s"): about 165 words a
  minute, so 150 to 330 words.
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

One page at a time; `reader` only (never `VideoMakers_io`, that is a signed-in X account).
**The `reader` browser is one window shared by every agent of the run** (2026-11-04: two makers
kept loading their pages over each other's). An agent checks `xb reader url` right before and
right after each `text` or `shot`, and keeps the result only when both name its page; it looks at
every screenshot before using it. This is
for public pages: never get around a paywall or a login, and never solve a CAPTCHA. A page that
still will not show its text is left out, or replaced by another page that says the same. Tell the
sub-agents this too.

Then each film's checks (the sub-agent runs them, and reports what they said):

1. `check_research` until clean. It gives the seconds; if it says more than 120, cut lines.
2. `check_sources` on doc1, 20 rows a call. Fix `number` (quote to the page's words), resolve
   `missing` and `unreadable` (another page, or drop the number and its lines).
3. If the number the film rests on cannot be backed, drop that topic and say why. Do not
   substitute a weaker topic in the same run unless it already passed steps 3 to 5.

## 8. Make the film

`make_film` for each, at once (the account makes two at a time; a third waits in its line):

- `project: "p-mlgnibpqat"`, `frame: "9:16"`, `look: "collage"`, `seconds`: what
  `check_research` said (a multiple of 5);
- `documents`: `[{name: "fact-sheet.md", text: doc1}, {name: "chart-data.md", text: doc2},
  {name: "script.md", text: doc3}]` in that order;
- `idea`: first line the film's question; then `LABEL: BREAKING` (news under two days old) or
  `LABEL: EXPLAINED`; `HEADLINE: <eight words or fewer>`; `DATA AS OF <date>`; the pages to
  photograph if not all are in doc3's directions; how to say any name the voice could get wrong.

Then follow both with `get_film` (`wait_seconds: 50`, again and again) until done; a film of a minute or two
takes about 15 to 30 minutes. **A film whose status is `cancelled` was stopped by a person: never make it again, and do not publish anything for that topic** (2026-11-02: the owner stopped two films and the run re-made both). A film that did not finish: read why; `remake_film` once only if the
reason was the studio's, not the documents'.

## 9. Publish (always public: no approval is asked)

For each finished film:

1. `get_film`: read its narration and look at what it reports. If a spoken line says something
   doc1 does not, do **not** publish it; say so in the report.
2. `publish_to_youtube`: `film`, `channel: "UC2PK9SXpePZSRkT3LqiOgeg"`, `privacy: "public"`,
   `thumbnail: "youtube"`, and your own
   - `title`: the question, the answer or the recreation, never a news summary ("Who checks
     Proton's code now?"), with the searched name in its first words, no claim the film
     does not support, ends with ` #shorts`, 70 characters at most before it;
   - `description`: two or three plain sentences of what the film finds, `Data as of <date>.`,
     then `Sources:` and one line per source (outlet, title, URL), then `Made with KitCut:
     https://kitcut.ai`;
   - `tags`: the anchor, the pair, the question forms.
3. `get_youtube_post` until it is live, for the video's link.

## 10. Tell the owner, then report

Once every film is live (or has failed a gate), tell the owner once, **both** ways (2026-11-02:
the push alone went unseen):

1. **Email** (Gmail connector, `send_message`) to alex@botmakers.net, subject `HN Shorts: <n>
   published`, a short plain body: one line per film with its title and its link as
   `https://youtube.com/shorts/<id>`; then one line per topic that was checked and not made, and
   why; then anything a person should look at; then https://hn-ideas-iota.vercel.app for the rest
   of the shortlist.
2. **PushNotification** with the count and the links.

A run that published nothing still notifies, saying why (no topic passed, credits, a tool down).

End the run with this, and nothing after it:

```
HN Shorts, <date> <time> UTC

| candidate | kind | stakes | anchor/mo | pair or question | supply on the angle | verdict |
|---|---|---|---|---|---|---|
...

Checked (6b): <topic: STRONG/MAYBE/NO, one line why>, ...
Published: <title> https://youtube.com/shorts/<id> (<seconds> s, film <link>), ...
Sent to the page: <n> ideas, <m> angles (the API's answer)
Look at: <anything a person should check>   (or "nothing")
Spent: <credits> credits, <search_videos queries> YouTube queries
```

## Never

- Asking the owner to approve or pick: the run decides (2026-11-04). More than three films a run;
  two films on one subject; a MAYBE made to reach two.
- `MAKE.md` making anything but the owner's pick.
- A film from a topic that failed a step.
- A number without a page you read and a quote you saw on it.
- Publishing a film whose narration says what doc1 does not.
- Anything but the KitCut channel; any channel but public there.
- Getting around a paywall or a login.
- Russian sources shown as neutral or admirable; party politics.
