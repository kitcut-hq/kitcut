# Map sheet: the pictures and where things are on them

Accent colour: amber #FFB347 (earthquakes), red #FF2A3D for the magnitude 6+ rings only. Background around maps: #070B12.

Every map is a REAL picture attached to this film, already rendered from the USGS catalog: one dot per earthquake, sized by magnitude. Never draw a map, a coastline, a fault or an earthquake dot yourself. All pictures of one view have the same size: stack them exactly (same x, y, width, height). u, v are fractions of a picture's width and height from its top-left.

## The pictures (attached uploads, in this order)

| upload | view | picture | size |
|---|---|---|---|
| up-3y33rtcopuau | california | base: Sentinel-2 satellite of California, darkened, land outside the state dimmed | 2160 x 2454 |
| up-2kruu4zuvgqc | california | layer: California's border, thin white line | 2160 x 2454 |
| up-z2yjkzfeuuui | california | layer: M2.5+ quakes 1990-1999 (20,872 dots) | 2160 x 2454 |
| up-vmc2iv3kigzz | california | layer: M2.5+ quakes 2000-2009 (9,521) | 2160 x 2454 |
| up-ff3zpd7kf32n | california | layer: M2.5+ quakes 2010-2019 (10,940) | 2160 x 2454 |
| up-6s374qlbqklb | california | layer: M2.5+ quakes 2020 to 6 Nov 2026 (6,381) | 2160 x 2454 |
| up-zigphxmzg6xq | california | layer: the 17 quakes of M6+, red discs | 2160 x 2454 |
| up-ermg7g7s6ho7 | la | base: Sentinel-2 satellite of the Los Angeles area, darkened | 2600 x 2093 |
| up-mmiez5lxhbkh | la | layer: every M2.5+ quake in this frame since 1990, amber dots | 2600 x 2093 |

Credit, small type at the bottom of every map: "Imagery: Sentinel-2 cloudless 2016, EOX (CC BY 4.0) · Earthquakes: USGS ComCat".

## C1. Every earthquake since 1990 · L01, L02, L03, L04, L08, L11
Source line: "Source: USGS ComCat, M2.5+, 1 Jan 1990 – 6 Nov 2026"
View `california`.

| decade layer | quakes |
|---|---|
| 1990s | 20,872 |
| 2000s | 9,521 |
| 2010s | 10,940 |
| 2020s (to 6 Nov 2026) | 6,381 |
| total | 47,714 |
| M6+ | 17 |
| M7+ | 4 |

Places (u, v):

| place | u | v |
|---|---|---|
| San Andreas fault, Parkfield | 0.3897 | 0.6569 |
| San Andreas fault, Carrizo Plain | 0.4533 | 0.7327 |
| San Andreas fault, near Palmdale | 0.6075 | 0.7928 |
| Northridge 1994 M6.7 | 0.5666 | 0.8264 |
| Ridgecrest 2019 M7.1 | 0.6543 | 0.6701 |
| Landers 1992 M7.3 | 0.7629 | 0.8277 |
| Hector Mine 1999 M7.1 | 0.7785 | 0.7879 |
| Petrolia 1992 M7.2 | 0.0346 | 0.1935 |
| Los Angeles | 0.5944 | 0.8426 |
| San Francisco | 0.2037 | 0.4647 |
| San Diego | 0.6953 | 0.9736 |

How it moves: frame 0 has every decade layer on, the camera drifting; on L02 the layers clear and come back one decade at a time while a year counter runs 1990 to 2026 and the total counts up; on L03 the camera glides along the bright line Parkfield → Carrizo Plain → Palmdale; on L04 the red M6+ layer pulses on.

## C2. Northridge · L05, L06, L07, L10
Source line: "Source: USGS · SCEDC (Caltech)"
View `la`. The bright cloud of dots over the San Fernando Valley is the Northridge sequence. Places: Northridge epicenter 1994 u=0.3087 v=0.3884; Downtown LA u=0.5000 v=0.5515; Santa Monica u=0.3400 v=0.5814; Long Beach u=0.5400 v=0.8308.

| number | label |
|---|---|
| 57 | deaths (USGS) |
| 20 billion | dollars of estimated losses (USGS) |
| 60% | LA region, M6.7+, 30 years from 2014 (USGS UCERF3) |
| 99% | all of California, M6.7+, 30 years from 2014 (more than) |

## C3. Ridgecrest and the weekly count · L08, L09
Source line: "Source: SCSN (Caltech/USGS)"

| number | label |
|---|---|
| 26,000 | aftershocks in about six weeks, 2019 (nearly) |
| 200 | earthquakes detected a week, Southern California (about) |
| 2 or 3 | felt a week |
