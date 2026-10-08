# Conference outreach

A conference organiser gets a film made for their own event, from their own
pages, with an offer to make more. This folder is the tracking half: the page
every lead lives on, and the tool that turns a list of conferences into leads.
The films are made by kitcut.ai's studio from the event templates.

It is not video tooling and it does not use the repo's `.venv`: standard library
only, run with any Python 3.10+.

| file | what |
|---|---|
| `conference-pipeline.html` | the pipeline page: every event, its stage, who to write to, its film, its email, what happened, and the owner's Approve / Hold / Skip and note. Published as a private Artifact with a database (`capabilities: {db: {}}`) |
| `leads_from_csv.py` | a contact list (CSV) -> one lead record per event, and the database batches that put them on the page |
| `local/` | the contact lists. Gitignored: other people's addresses |
| `data/` | the lead records and batches made from them. Gitignored |

```powershell
python market/outreach/leads_from_csv.py --plan                          # count, write nothing
python market/outreach/leads_from_csv.py                                 # local/contacts.csv -> data/
python market/outreach/leads_from_csv.py --csv <more.csv> --have data/on-page.txt
```

The list's columns are `Event`, `When / Where`, `Email` (several separated by
`;`), `Notes`, and optionally `Organiser`. `--plan` prints how many events have
an address, how many organisers that is (one organiser with three events is one
inbox, not three emails) and how many have only a form or a phone number.
`--have` takes the lead ids already on the page, so a longer list adds its new
events and never resets one that has been worked.

## The page

One document per event in the collection `leads`; the document id is the event's
name as a slug. The session that works the leads reads and writes them through
the Artifact tool's database actions, always with the version it last read.

| field | written by | what |
|---|---|---|
| `event`, `org`, `org_key`, `when`, `date_sort`, `emails`, `audience`, `access_note` | the tool | the list's row; `access_note` is the way in when there is no address |
| `stage` | the session (the owner may change it) | `new`, `blocked` (no address), `research`, `filming`, `review`, `sent`, `replied`, `talking`, `won`, `lost` |
| `contact_name`, `contact_role` | the session | the person found for this event |
| `template`, `film_id`, `film_url`, `film_minutes`, `film_note` | the session | `film_url` is the film's share page, which opens without signing in |
| `email_subject`, `email_body`, `sent_at`, `sent_to`, `sent_from`, `gmail_thread` | the session | the email as sent |
| `next_step`, `next_date`, `log` | the session | `log` is `[{at, text}]`, oldest first |
| `decision`, `owner_note` | **the owner, on the page** | `approved`, `hold` or `skip`, and a note. Read both before every step on a lead |

Nothing is sent to an organiser without `decision: approved` on that lead or the
owner's word in the session.

## Working one lead

1. **Read the event's own pages** for what is announced today, and pick the film
   by the stage the event is in:

   | the event has | template |
   |---|---|
   | speakers announced | `conference-speaker-promo` |
   | a call for speakers or papers still open | `call-for-speakers` |
   | a date and little else | `event-countdown` |
   | last year's numbers | `conference-in-numbers` |
   | a published programme | `conference-agenda` |

2. **Write a short prompt**: the event's name, its page, and the facts that
   matter (dates, venue, the speakers to feature, the deadline). Say what the
   page does *not* give, so nothing is invented to fill a slot.
3. **Make the film** in the owner's account, link-only, from a checkout of the
   site's repository at its current release:
   `node --env-file=.env scripts/film.mjs make --as <owner> --template <slug> --prompt-file <f.md> --unlisted --studio-env <this repo's .env>`,
   then `bash studio/deploy/ops.sh watch <film-id>`.
4. **Check it before it goes anywhere.** On the studio, the film's
   `content.json` holds every word it shows and `web/sources.json` every page
   and picture it took: check each fact against the event's page and each
   person's picture against where it came from. Then look at stills of the
   whole film.
5. **The link to send** is the film's share page (`og:url` of its page on the
   site). Open it signed out first.
6. **The email**: the film's link, what is in it and that all of it comes from
   their own pages, that they may use it, the offer to make more within a day,
   a request for the right person if this is the wrong desk, and a line that
   says how to stop hearing from us. One organiser, one email.
7. **Write the lead**: the stage, the film, the email as sent, the date of the
   follow-up, a line in the log.

## What the first list taught (2026-10-08, 52 events)

- **Most events had no speakers yet.** Six of the seven checked were next
  year's, still collecting proposals. A speaker promo needs speakers; the call
  for speakers, the countdown and the numbers templates do not.
- **A list of programme contacts is not a list of buyers.** 35 of 52 events had
  an address (31 organisers), and those were agenda, sponsorship, exhibitor and
  registration desks. Ask for the marketing lead in the email, and look for one
  before the next batch.
- **Some sites refuse automated reading.** An organiser's main site may, while
  its registration or conference site does not; the studio found its way round
  by itself, and the speakers' own organisations had their photos.
- **A countdown ages by the day.** A film that says "8 days left" is right for
  one day: say so in the email and offer the cut for the day they post.
- **Time**: a 26-second speaker promo took 9.8 minutes and a 90-second call for
  speakers 14 minutes, both right the first time, with the logo, colours and
  photos found by the studio. Reading the event's pages and checking the film
  is the rest of a lead: about as long again.

Still open: the emails carry no postal address, and the offer names no price.
