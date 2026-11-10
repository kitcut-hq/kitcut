# Routine: one research film a day, from the news (designed, not scheduled)

The prompt a scheduled agent runs each morning once the owner turns it on
(`docs/autonomous-research-films.md`). Connectors it needs: **KitCut** (kitcut.ai/mcp, signed in as
the owner) and **market-data** (search volume and YouTube search); its own web search and fetch.
Permissions: approve tools automatically, since nobody is there to click. To turn it on: a claude.ai
scheduled task (Scheduled → New task → these instructions, daily at 07:00 Pacific), or the
`schedule` skill from Claude Code. Nothing below is scheduled yet.

---

You make at most one research film today for the KitCut project "Research films", or none.

1. Call `get_playbook` (KitCut) and follow it exactly; this note only adds today's settings.
2. The beat: AI companies and products, chips and data centers, big tech money (IPOs, valuations,
   filings), and the internet's infrastructure. Topics the project's channel already gets search
   views for (`get_youtube_views` search_terms) come first.
3. Use the market-data tools for the pull test: `keyword_volume` (English, worldwide, monthly) on
   the bare name and its question forms, and `search_videos` for this week's English supply.
   Write the numbers down; a topic without rising demand or with a crowded week is dropped.
4. Research until every number the film rests on has a page and a quote. Prefer primary sources
   (filings, official posts and data). Leave out what you cannot read.
5. Run `check_research` until it is clean, and `check_sources` over every row. If a number the
   question rests on does not hold, stop: no film today.
6. `get_credits` first: if fewer than 700 credits are left, stop and say so.
7. Make the film: `make_film` with the project, the three documents, the seconds `check_research`
   gave, look collage. Then follow it with `get_film` until it is done (it can take 1-3 hours).
8. Publish **unlisted** on the project's channel (`draft_youtube_post`, then `publish_to_youtube`
   with privacy unlisted). Never public: the owner makes it public after watching.
9. Reply with the playbook's five-line report, plus the film's link and the video's link.

Never: more than one film; a film when nothing passed; a number without its page; anything public;
Russian sources presented as neutral or admirable; party politics.
