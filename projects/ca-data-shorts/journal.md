# ca-data-shorts journal

## 2026-11-07, three California data Shorts for the KitCut channel

Owner asked for three very different viral Shorts about California / Los Angeles from raw data, on
real maps ("not some poor drawn maps"), the first published on @kitcut-hq, the others scheduled,
and all three on the KitCut Facebook Page. Owner's own pick of the angle for oil: people fear an
old well under their house; and the oil data should be reusable for other places.

What was made:
- `scripts/geo-layers.py` (new): real imagery + data as aligned layers. Bases: Sentinel-2
  cloudless 2016 (EOX, CC BY 4.0), USDA NAIP aerial (public domain), USGS tiles.
- Data (gitignored `sources/`): CalGEM WellSTAR LA County (24,333 records), USGS ComCat M2.5+
  since 1990 (47,714 in/near CA), 2020 Census tracts/counties/states from TIGERweb.
- Three films in KitCut project "California in Data" (p-kwc2omstqz), drawn look, 9:16, each with
  a word-for-word script, a fact sheet with a source and quote for every number, and the map
  pictures uploaded with role "show":
  - oil: studio-20261107-223048-azpu2m (80 s)
  - quakes: studio-20261107-223313-voaphm (75 s)
  - population: queued as 6af018046ffee3b8be2a9452 (70 s)
- Thumbnails: `thumbs/*.html` -> 1080x1920 JPGs (headless Chrome), from the real maps, no AI image.

Decisions:
- No Gemini thumbnails: an image model redraws the map; ours are the real data.
- Spoken numbers rounded ("more than twenty-four thousand"), exact numbers on screen.
- Oil: 1,192 wells in the Los Angeles City field, 856 still listed Idle (WellSTAR). The state's own
  2016 estimate (900 orphan wells in the City of LA, most buried) and the Controller's line that
  buried wells' mapped spots are "sometimes only approximate" carry the fear honestly; the film
  never says a given house has a well.
- A point-in-building count (LA County 2023 outlines) gave 2,677 wells inside a building outline,
  but 25 of 97 query batches failed: a floor, not used in the film.

For the next session: to make the oil film for another place, copy `geo-oil.json`, change the
CalGEM county (or another state's well registry), re-pick the close-ups with the density-hotspot
step (wells in tracts over 4,000 people/km2), and rewrite the script from the new numbers.

## 2026-11-07, late: published and scheduled

- Population film remade as studio-20261107-231433-ycrgw7: the first take (vgyrbf) stood still 16%
  of the time with the state small in black; the remake opens tight on the LA basin and zooms out,
  0% still. The quake film is 8% still (accepted); oil 1%.
- YouTube @kitcut-hq: oil TQhi03HegKQ public 2026-11-07 23:05 PT; quakes 1hmquRM6pYE scheduled
  2026-11-08 19:00 PT; population jMYs6epH0uk scheduled 2026-11-09 12:00 PT. Own thumbnails set.
- Facebook Page KitCut (Business Suite reels composer, Instagram unticked): oil posted 23:10 PT;
  quakes and population scheduled at the same times as YouTube. Uploaded as 720p copies under
  10 MB (the Chrome upload cap); the composer has no cover picker, the first frame is the cover.
  The page's file input only exists after a click: hook HTMLInputElement.prototype.click to keep
  it in the DOM, then file_upload to it.
