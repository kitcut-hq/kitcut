---
name: lead-proposal
description: Write a proposal for a lead as a short, designed PDF in KitCut's brand — what is already made for them, a calendar of videos computed from THEIR event dates, two or three sizes of one campaign, how it runs and the next step. Use when asked for a proposal, a plan, an offer, a pitch deck or a PDF to send to a lead, a customer, a conference, an agency or a channel, when a sales call ended with "I'll send you a plan", or when an existing proposal needs its dates, options or prices changed.
---

# A proposal for a lead

A lead who has seen a demo does not need the tool described again. They need to
see what would be published, and on which day, against dates they already have.

```powershell
# from the repo root
python scripts/make-proposal.py --list
python scripts/make-proposal.py --spec projects/<id>/proposals/campaign.json --plan
python scripts/make-proposal.py --spec projects/<id>/proposals/campaign.json --pdf --preview
```

| | lives in | changing it |
|---|---|---|
| **shape** | `config/proposals/templates/campaign.html` | a different kind of proposal |
| **look** | `config/proposals/brands/kitcut.json` | a white-label proposal |
| **words** | the spec, `projects/<id>/proposals/*.json` | a different lead |

Start from `config/proposals/example/devdays.json`. The lead's spec and stills
stay in `projects/<id>/proposals/`, which git ignores: a lead's name and prices
are not tooling, and this repo is public.

## Before writing a word

1. **Read what was actually said.** If the call was not in English, the meeting
   notes are probably noise: one Ukrainian call came back as 25 garbled English
   fragments. Take the recording's audio and run
   `python scripts/transcribe-words.py <audio> --out <x>.json --language <code>`.
2. **Read their dates off their own site and FAQ**: the event days, when the
   agenda is published, how ticket prices move (by date or by quantity sold),
   open calls. The calendar is only as good as these.
3. **Make the examples first, in their look.** A proposal that opens on three
   finished videos with their speakers and their colours has already answered
   "let's see how it comes out". Check every name against its face before a
   frame goes on a page.

## What goes in it

- **Every option is a committed campaign.** Two or three sizes of the same
  thing, all running to their deadline on a calendar fixed at the start. Never
  a small free test followed by a decision date: a few posts on a channel with
  no video history give noisy numbers, and one weak week ends the deal. Numbers
  are looked at weekly to steer what is made next, not to decide whether to go on.
- **Recommend one**, and say why in a line. `"recommended": true` draws the flag.
- **Their dates in their colours, our videos in ours.** `client.accent` and
  `client.ink` mark only the lane of `kind: "client"` and the event week.
- **One next step with a date**, and the two or three facts needed from them.
- **Prices are the owner's decision.** Put in what was agreed on the call; if
  nothing was, say in your report that the figures are estimates.

## The calendar

An item is `{"date": ...}`, `{"from": ..., "to": ...}`, or counted from the
event: `{"days_before": 30}`, `{"days_after": 3}`, `{"event": true}`. Use
`days_before` for every countdown video so its label and its day cannot
disagree. `"done": true` marks a video that already exists.

Run `--plan` before printing. It lists every item with its weekday and days to
go and names what a page would hide: a video on a weekend, two of one lane on
one day, an item before the first week shown. `--pdf` refuses a calendar with
a problem.

Keep it to eight weeks or fewer across the page. A band that covers one week
wraps to four lines; let it span two.

## After printing

`--preview` writes each page as a PNG beside the PDF. **Look at all of them.**
The script already fails on a page that overflowed, a page without its title
and a fallback font, but not on a still cropped through a face or a label that
reads badly.

- Stills are cropped to fill. The cover's slots are square, 16:9, square; the
  cards of `ready` are square. Pad a wide still to a square in the film's own
  background colour rather than letting the sides go.
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
