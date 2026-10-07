# Etsy keyword research

Etsy's Shop Manager has a keyword tool, **Marketplace Insights**, with no export
and nine rows to a page. `etsy_insights.py` reads the same data the page reads,
for a list of search terms, and leaves it as CSV.

It is not video tooling and it does not use the repo's `.venv`: standard library
plus `curl`, run with any Python 3.10+.

```powershell
python market/etsy/etsy_insights.py check                                   # is the session alive, which shop
python market/etsy/etsy_insights.py terms --file market/etsy/seeds/video-services.txt --plan
python market/etsy/etsy_insights.py terms --file market/etsy/seeds/video-services.txt
python market/etsy/etsy_insights.py terms "video invitation" "santa video"  # or name them
python market/etsy/etsy_insights.py trend --file market/etsy/seeds/video-services.txt
python market/etsy/etsy_insights.py report
```

`terms` and `trend` cache one JSON per term under `data/` and skip what is
already there (`--refresh` fetches again), so a list can grow without paying for
the old terms twice. `--plan` prints the request count and stops. `report`
rebuilds the four CSVs from the whole cache:

| file | what |
|---|---|
| `data/seeds.csv` | each term looked up: searches in the last 30 days, competing listings, searches per 1,000 listings, conversion rating and exact rate, the median price band of recent purchases, week-on-week change |
| `data/similar.csv` | every term Etsy suggested for any seed ("Similar terms" and "Exploratory ideas"), merged, with the seeds that produced it |
| `data/listings.csv` | the 20 listings Etsy shows as the competition for each seed: title, price, shop, shop review count, Bestseller / Star Seller |
| `data/trend.csv` | twelve months of monthly searches per term, and the peak month |

## The session

The data belongs to a signed-in seller, so the tool needs that seller's cookie.
Put the request headers in `market/etsy/local/headers.txt`, one `name: value` a
line -- `cookie:` and `user-agent:` are what matter. Copy them from any
`www.etsy.com` request in the browser's DevTools (Network > Copy as cURL).
`local/` and `data/` are gitignored; the cookie is a login, treat it like one.

- The cookie's `session-binding-www` part expires after 16 minutes. It does not
  matter: Etsy re-issues it, and the session key beside it lasts months.
- Everything goes through `curl`. Etsy sits behind DataDome, which fingerprints
  the TLS handshake; `curl`'s passes for the Shop Manager pages and their JSON.
- The **public** pages (`etsy.com/search`, `/listing/...`) answer 403 with a
  captcha. Do not add them here; the top listings per term already come with the
  Insights page.
- Requests are spaced 1-3 seconds apart on purpose.

## What Etsy limits

A shop without Etsy Plus gets 15 lookups a week (`quotaData` on the results
page). Etsy Plus is unlimited: on 2026-10-07 a 58-term run on a Plus shop went
through with 6 lookups left on that counter. The tool stops with a message if
Etsy refuses a lookup. Which requests the counter counts was not measured.

A new term takes Etsy 15-25 seconds to answer (its "Exploratory ideas" list is
generated on demand), so 58 terms is about 20 minutes whatever the pacing.

`trend` answers for three terms a request, with monthly points for 365 days and
daily points for 30.

## Reading the numbers

- **searches** is Etsy's own count for the last 30 days, not an estimate.
- **listings** is how many listings answer that search: the competition.
- **conversion** is how often the search ends in a purchase, rated against all
  of Etsy (Very Low .. Very High); `conversion_pct` is the rate itself.
- **median price** is a band around the midpoint of recent *purchases* from that
  search. It says what buyers pay there, which is the number to price against.
- A term with no price band has too few purchases for Etsy to show one.
