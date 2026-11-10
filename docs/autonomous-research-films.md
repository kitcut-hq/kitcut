# Research films made by an agent, through the MCP

The goal (owner, 2026-10-22): "build everything to let ai agents using our mcp be able to create
such videos autonomously, with little or no human intervention. I'll want to have a scheduled task
that will daily check breaking news and create videos about that similar to this. We don't build
the scheduled tasks now but design, plan and build all needed for this."

"Such videos" is the Anthropic IPO film (studio-20261021-224924-xcvyhz): a research film on a name
people search for, its evidence on screen, every number checked, both sides, the open question.
It took a person and Claude Code a day: a pull test, nine research threads, a re-read of every key
page (it caught six wrong numbers), three documents, nine hand-made pictures, a pilot, then the
film. This document is how an agent does the same through kitcut.ai's MCP, unattended.

## The run, end to end

One run = one film or none. Each step says who does it: the **agent** (any assistant with web
search: a scheduled Claude task, Codex, a ChatGPT agent) or **KitCut** (a tool on kitcut.ai/mcp).

| # | step | who | tool |
|---|---|---|---|
| 0 | read the method | KitCut | `get_playbook research_film` (also an MCP prompt) |
| 1 | the channel's own pull: which searches brought views | KitCut | `get_youtube_views` (search terms) |
| 2 | candidates: the last 24-72 hours of news on the channel's beats | agent | its web search |
| 3 | the pull test: search demand rising, thin English supply on YouTube | agent | market-data MCP (`keyword_volume`, `search_videos`); a KitCut tool later |
| 4 | pick one, or none ("no film today" is a good outcome) | agent | |
| 5 | research in threads, a URL and an exact quote for every number | agent | its web search and fetch |
| 6 | write doc1 (fact sheet), doc2 (chart data), doc3 (script, word for word) | agent | the playbook's formats |
| 7 | check the documents: every spoken number backed by doc1, labels, lengths, "must not say" | KitCut | `check_research` |
| 8 | check the sources: each quote is on its page | KitCut | `check_sources` |
| 9 | fix what 7-8 found, then run them again; stop if a key number cannot be backed | agent | |
| 10 | make the film in the research project, with the three documents and the pages to photograph | KitCut | `make_film` (`documents`, `project`) |
| 11 | the studio holds vo.json to doc3 word for word, photographs the pages, draws charts from doc2, reviews its own film for glitches | KitCut | (inside the studio) |
| 12 | look at the finished film | agent | `get_film` (and later a story sheet) |
| 13 | publish: unlisted, or scheduled on the project's channel | KitCut | `publish_to_youtube` / the project's `auto_publish` |
| 14 | report: what was made, what was dropped and why | agent | |

The human's part, by choice: set up the project once (channel, auto-publish time, the beats), and
read the report. Nothing is public unless the project says so.

## What KitCut must provide (and what exists)

| need | state |
|---|---|
| the format, so every film's prompt is short | **exists**: a project whose brief is the format (`.claude/skills/topic-research/examples/project-brief.md`; the owner's "Research films", p-3nz7b3arw2). **Build**: `create_project` with `format: "research"` fills that brief for anyone |
| the method, readable by any agent | **build**: `get_playbook` tool + MCP prompt, from `lib/mcp/playbooks/research-film.md` (the topic-research skill rewritten for an agent with only web search and this MCP) |
| documents into a film without a person uploading them | **build**: `make_film` `documents: [{name, text}]` (up to 3, each up to 200,000 characters) |
| the narration said word for word | **exists** (2026-10-22): the studio finds an L01... script among the documents and holds vo.json to it |
| sources photographed by the studio | **exists** (2026-10-22): the page tool's `keep`, cookie dialogs, X posts, SEC; up to a page per 30 s of film. The script's stage directions name the URLs |
| a page read without cutting its lines | **exists**: `SK.read` |
| facts checked by a machine before credits are spent | **build**: `check_research` (documents) and `check_sources` (fetch each page, find each quote), studio-side in Python, proxied by the MCP |
| search demand and YouTube supply | **exists** in the market-data MCP (Google Ads + YouTube); a KitCut tool is phase 2 |
| the channel's own search terms | **exists** (2026-10-22): `get_youtube_views` `search_terms` |
| glitch review of the finished film | **exists**: the studio's review gate |
| the agent seeing the film | **phase 2**: a story sheet (frames + words) as an image from `get_film` |
| publishing without a person | **exists**: `publish_to_youtube` (unlisted default, `publish_at`), project `auto_publish` |
| a cap on spend | **exists**: credits; the routine checks `get_credits` and makes at most one film a run |

## Machine-checkable documents

The checks only work if the documents have a fixed shape. The playbook teaches it; `check_research`
says exactly what does not match.

- **doc1, the fact sheet.** Markdown tables with the columns `number | what | label | source | url |
  quote`. `label` is one of FILED, MEASURED, REPORTED, CLAIM, ESTIMATE (ESTIMATE rows say "our
  arithmetic" and need no quote). `url` is the page the number was read on; `quote` is the exact
  words on that page that carry the number. Sections "Unconfirmed", "Commonly misreported" and "The
  film must not say" (quoted phrases).
- **doc2, the chart data.** `## C1. <title> · L09, L11` sections, a `Source line:` and a table;
  every value also in doc1.
- **doc3, the script.** `- L01. *what is on screen*` then the spoken words in quotes (the format
  `scripts/_narration.py` reads). Numbers are spoken as words ("sixteen point three billion").

`check_research` reads all three and reports, without any AI:
- doc3 parses as a word-for-word script; its words, and the minutes it runs at ~165 words a minute;
- every number the narration says (spoken as words or digits) is in doc1, give or take rounding;
- every doc1 row has a label, a source, and (unless an ESTIMATE) a URL and a quote;
- no phrase from "The film must not say" is in the narration;
- every doc2 value is in doc1.

`check_sources` takes the doc1 rows (or any `[{url, quote}]`), fetches each page (plain fetch, then
a real browser for pages that refuse robots, public addresses only), and says per row: the quote is
there / something close is there (with the page's words) / not there / the page could not be read.
It caught nothing by itself that a person would not, but a person re-reading 60 pages is the hour
this replaces: on film 31 that re-read found six numbers that were wrong.

## The daily routine (designed, not scheduled)

`docs/routines/daily-research-film.md` is the prompt a scheduled agent will run each morning, with
the KitCut and market-data MCPs connected. It decides first whether there is a film today at all
(the pull test), makes at most one, publishes it unlisted (or into the project's auto-publish
slot), and ends with a short report. When the owner wants it on, it becomes a scheduled task
(claude.ai routine or the `schedule` skill) with that prompt.

## Phases

1. **Now:** `documents` on make_film; `get_playbook` + prompt; `format: "research"`;
   `check_research` and `check_sources` (studio + MCP); the routine prompt; this document.
2. **Next:** a story sheet in `get_film` for the agent to judge the film; a `topic_pull` tool in the
   KitCut MCP (search demand + YouTube supply) so an agent needs only one MCP; a structured `pages`
   list on make_film photographed before Claude starts.
3. **Later:** the research itself as a studio stage (parallel threads on kc-local), once two or three
   more films show which steps catch errors.

## Risks, said plainly

- **Speed vs truth.** Breaking news changes by the hour; a film made from the first reports can be
  wrong by evening. The routine prefers stories at least a few hours old with a primary source, and
  the brief says "DATA AS OF".
- **An agent's research is only as good as what it can read.** Paywalls and logins are not bypassed;
  a number only behind one is left out or labelled by the relay that reported it.
- **Cost.** A 10-minute film is 600 credits and about 2 hours of studio time; one a day is the cap
  the routine sets until the numbers say more is worth it.
- **Nothing public without a rule.** Uploads are unlisted unless the project's channel and
  auto-publish say otherwise.
