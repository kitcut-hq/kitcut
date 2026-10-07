---
name: etsy-keywords
description: Research Etsy search demand with the seller's own Marketplace Insights data — searches per term, competing listings, conversion rating, the price buyers actually pay, the top competing listings and twelve months of seasonality — and export Etsy's "Similar search terms" lists, which the Shop Manager page will not. Use when asked for Etsy keywords, what to list or sell on Etsy, how a term performs on Etsy, to download or export Etsy search terms, to price an Etsy listing, or to choose titles and tags for one.
---

# Etsy keyword research

`market/etsy/etsy_insights.py` reads Etsy's Marketplace Insights (Shop Manager)
for a list of terms. `market/etsy/README.md` is the reference: commands, files,
what each column means, what Etsy limits. This is the procedure.

## 1. Get a session

The tool needs the seller's cookie in `market/etsy/local/headers.txt`
(gitignored). Run `python market/etsy/etsy_insights.py check` first. If it says
signed out, ask for a fresh "Copy as cURL" of any www.etsy.com request and write
its `cookie:` and `user-agent:` lines to that file with the Write tool — never
put the cookie on a command line. The session key lasts months, so an old
headers file usually still works.

The data lives beside the tool, in `market/etsy/data/` of whichever checkout or
worktree ran it. Look for an existing `data/` before fetching again.

## 2. Seed wide, then follow what Etsy says

Write the seeds to `market/etsy/seeds/<topic>.txt` (committed: the list is the
method). Seed the *format*, the *occasion* and the *buyer's word* separately —
"video invitation", "birthday invitation", "evite" are three markets, not one.

```powershell
python market/etsy/etsy_insights.py terms --file market/etsy/seeds/<topic>.txt --plan
python market/etsy/etsy_insights.py terms --file market/etsy/seeds/<topic>.txt
python market/etsy/etsy_insights.py report
```

Then read `data/similar.csv`: the terms Etsy suggests that you did not think of
are the point of the exercise. Add the promising ones to the seed file and run
`terms` again (cached terms are skipped). Two rounds is usually enough.

## 3. Seasonality before advice

```powershell
python market/etsy/etsy_insights.py trend --file market/etsy/seeds/<topic>.txt
python market/etsy/etsy_insights.py report
```

A term's 30-day number is one month. Read `data/trend.csv` before calling
anything big or small: Santa and Christmas terms are near zero for nine months.

## 4. Read it like a seller, not like an SEO

- **Price band first.** `median_price_low/high` is what buyers *pay* in that
  search. A huge term with a $2 band is a template market; a made-to-order
  product priced at $25 does not belong in it, whatever the volume.
- **Conversion rating second.** "Very Low" on a broad term means browsing.
- **Then searches against listings.** `searches_per_1000_listings` ranks how
  crowded a term is; under about 20 is a wall of competitors.
- **Then `data/listings.csv`.** Who holds the page: instant-download templates
  or made-to-order work, at what price, with how many reviews.
- Licensed characters (Bluey, Paw Patrol, Disney) show up in the suggestions
  with good numbers. They are other people's trademarks; leave them out.

## Traps

- The public pages (`etsy.com/search`, `/listing/...`) answer 403 with a
  captcha. The tool does not touch them; do not try with curl.
- A shop without Etsy Plus gets 15 lookups a week; the tool stops when Etsy
  refuses one. New terms take 15-25 s each on Etsy's side: run `terms` in the
  background and `trend` (seconds) while it works.
- The numbers are Etsy-only. Google demand for the same phrase is a different
  market; `docs/market-templates-2026.md` has those.
