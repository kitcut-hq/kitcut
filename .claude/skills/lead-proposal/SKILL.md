---
name: lead-proposal
description: Write a proposal for a lead as a short, designed PDF in KitCut's brand — what is already made for them, their own audience numbers and what a campaign would bring, the wheel of speakers and partners sharing videos about themselves, two or three sizes of one campaign, where each video runs, a day-by-day calendar computed from THEIR event dates, how it runs and the next step. Use when asked for a proposal, a plan, an offer, a pitch deck or a PDF to send to a lead, a customer, a conference, an agency or a channel, when a sales call ended with "I'll send you a plan", when asked to project views, reach or engagement for a lead from their current numbers, or when an existing proposal needs its dates, options or wording changed.
---

# A proposal for a lead

A lead who has seen a demo does not need the tool described again. They need to
see what would be published, on which day, against dates they already have, and
what it would bring them.

```powershell
# from the repo root
python scripts/make-proposal.py --list
python scripts/make-proposal.py --spec projects/<id>/proposals/campaign.json --plan
python scripts/make-proposal.py --spec projects/<id>/proposals/campaign.json --html-out projects/<id>/proposals/plan.html
python scripts/make-proposal.py --spec projects/<id>/proposals/campaign.json --pdf --preview
```

| | lives in | changing it |
|---|---|---|
| **shape** | `config/proposals/templates/campaign.html` | a different kind of proposal |
| **look** | `config/proposals/brands/kitcut.json` | a white-label proposal |
| **words** | the spec, `projects/<id>/proposals/*.json` | a different lead |

Start from `config/proposals/example/devdays.json`. The lead's spec and stills
stay in `projects/<id>/proposals/`, which git ignores: a lead's name is not
tooling, and this repo is public.

**Show the HTML first.** Write the page with `--html-out`, open it in the
browser, and stop. Print the PDF only after the owner has looked.

## Before writing a word

1. **Read what was actually said.** If the call was not in English, the meeting
   notes are probably noise: one Ukrainian call came back as 25 garbled English
   fragments. Take the recording's audio and run
   `python scripts/transcribe-words.py <audio> --out <x>.json --language <code>`.
2. **Read their dates off their own site and FAQ**: the event days, when the
   agenda is published, how ticket prices move, open calls, how many speakers
   are announced.
3. **Read their numbers off their own pages, today.** Followers on each
   channel; the reactions on their last ten posts, split into what the page
   wrote and what it reshared from people; the followers of their speakers and
   of their partners. A plain `curl` with a browser user agent reads LinkedIn
   company pages and most profiles (some answer 999, and it turns to 429 after
   a couple of dozen requests); Instagram gives its follower count only to a
   crawler user agent, in `og:description`; YouTube's channel page carries
   subscribers and views.
4. **Make the examples first, in their look**, and make them worth watching:
   facts about the person or the company, not a photo on a card. Verify every
   fact at its source and put the facts on top of the prompt. Check every name
   against its face before a frame goes on a page.

## What goes in it

- **Their own numbers make the case.** On the first lead the page had 2,383
  followers, eight of its speakers had 171,000 and eight partners 1.3 million;
  the page's own posts got 0-9 reactions and the attendees' posts it reshared
  got 12-48. So the argument was never "video on your page": it is videos that
  speakers and partners post themselves. Look for that gap before designing
  the options, and put what closes it in the recommended one.
- **Estimates name their source and stay estimates.** Impressions per video
  from a published median for accounts of that size, read at the source, not
  from a search summary; campaign totals with the assumption beside them
  ("if 30 speakers post"). **Do not forecast tickets or sponsors**: honest
  inputs give a small direct number, and the first weekly report would
  contradict a bigger one. Say each video gets its own link and the numbers
  are checked weekly.
- **Every option is a committed campaign.** Two or three sizes of the same
  thing, all running to their deadline on a calendar fixed at the start. Never
  a small free test followed by a decision date.
- **Recommend one**, and say why in a line. `"recommended": true` tints its
  column down the whole calendar.
- **No prices** unless the owner asks for them in the document.
- **Where each video runs**: place, shape (square, tall, wide), what goes
  there. Only promise a shape that exists: check which of the films can be
  made tall before putting them under Reels or Shorts.
- **One next step with a date**, and the two or three facts needed from them.
- **Our contact is hello@kitcut.ai.**

## The calendar

`timeline.plans` are the columns, `timeline.posts` the videos,
`timeline.marks` their dates. A post is `{"date": ...}` or counted from the
event (`{"days_before": 30}`, `{"days_after": 3}`); use `days_before` for
every countdown video so its label and its day cannot disagree. `in` names the
smallest plan that has the post.

Every date is a row, the empty ones too. Run `--plan` before anything else: it
lists every post with its weekday, days to go and plans, counts the posts per
plan, and names what a page would hide (a weekend, two posts of one plan on one
day, a post outside the dates shown). `--pdf` refuses a calendar with a problem.

Keep a post's label to one line: the calendar page is exactly as tall as its
rows, and a label that wraps twice pushes it onto a second sheet, which fails
the print.

## After printing

`--preview` writes each page as a PNG beside the PDF. **Look at all of them.**
The script already fails on a page that overflowed, a page without its title
and a fallback font, but not on a still cropped through a face, one person on
every still, or a label that reads badly.

- Stills are cropped to fill: cover slots are square, 16:9, square; `ready`
  cards are square; `loop` examples are 16:9.
- Links on the cards are live in the PDF. Open each one signed out first.
- Send the PDF, not the PNGs.

## Traps

- **A web font is not there when Chromium prints.** The first proposal came out
  in Segoe UI. A brand names local font files; the print fails if any other
  face is in the PDF.
- **The site's `Inter.woff2` and `Caveat.woff2` have no Cyrillic.** The brand
  uses `fonts/Inter-VF.ttf` and `fonts/Caveat-Cyrillic-VF.ttf`.
- **A page of fixed height clips what does not fit, silently.** The template's
  pages have a minimum height so the overflow becomes an extra sheet and fails
  the page count. Keep that when adding a section.
- **A multi-day date drawn as stubs of a bar reads as a glitch.** It is a
  tinted band in its column.
- **A search summary is not a source.** One "average impressions per personal
  post" figure appeared in two search summaries and on neither page they
  pointed to. Fetch the page, or the report's PDF, and quote from that.
