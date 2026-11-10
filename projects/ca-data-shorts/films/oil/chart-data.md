# Map sheet: the pictures and where things are on them

Accent colour: amber #FFB020 (wells), with red #FF2A3D for active wells only. Background around maps: #070B12.

Every map is a REAL picture attached to this film, already rendered from the state's records. Never draw a map or a well yourself. All pictures of one view have the same size: stack them exactly (same x, y, width, height). u, v are fractions of a picture's width and height from its top-left.

## The pictures (attached uploads, in this order)

| upload | view | picture | size |
|---|---|---|---|
| up-wvu5ldidgtis | la | base: Sentinel-2 satellite of the LA basin, darkened | 2600 x 2239 |
| up-4dc35q6wj2av | la | layer: plugged wells, pale amber dots (17,763) | 2600 x 2239 |
| up-fxmwbicxp2y5 | la | layer: idle wells, orange dots (3,074) | 2600 x 2239 |
| up-v2dweou6o4ul | la | layer: active wells, red dots (3,272) | 2600 x 2239 |
| up-7773ilxc6b4l | westlake | base: aerial photo (NAIP) just west of downtown LA, homes visible | 2160 x 2006 |
| up-ozkmlidc5hds | westlake | layer: every recorded well here, amber dots (the Los Angeles City field) | 2160 x 2006 |
| up-v7ppwimb3yt4 | bhhs | base: aerial photo (NAIP) of Beverly Hills High School and Century City | 2160 x 2173 |
| up-l3zse4afictj | bhhs | layer: recorded wells here, amber dots | 2160 x 2173 |
| up-pnl3nvyhbhty | thums | base: aerial photo (NAIP) of Island White, one of the four THUMS oil islands off Long Beach | 2160 x 2126 |

Credits, small type at the bottom of each map: la: "Imagery: Sentinel-2 cloudless 2016, EOX (CC BY 4.0) · Wells: CalGEM WellSTAR". westlake, bhhs, thums: "Imagery: USDA NAIP / USGS · Wells: CalGEM WellSTAR".

## C1. Every oil well in LA County · L01, L02, L12, L13
Source line: "Source: CalGEM WellSTAR, 7 Nov 2026"
View `la`. Places (u, v):

| place | u | v |
|---|---|---|
| Downtown LA | 0.5376 | 0.2962 |
| Echo Park / Westlake (Los Angeles City field) | 0.5171 | 0.2686 |
| Beverly Hills High School | 0.2947 | 0.2810 |
| Long Beach / Signal Hill | 0.6471 | 0.7905 |
| THUMS islands | 0.6429 | 0.8863 |
| Santa Monica | 0.1857 | 0.3607 |
| LAX | 0.3029 | 0.5167 |

Counts on screen: 24,333 total; 17,763 plugged; 3,074 idle; 3,272 active.
How it moves: frame 0 shows all three layers on, the camera drifting over the basin and the big counter already reading 24,333; on L02 the plugged layer pulses while idle and active dim; on L03 the camera pushes fast into Echo Park / Westlake.

## C2. The Los Angeles City field · L04 to L09
Source line: "Source: CalGEM WellSTAR · CA Dept. of Conservation"
View `westlake`. The amber dots form a band across the middle of the picture (v about 0.45 to 0.65): that band is the field, under homes and apartments. Places: US-101 freeway u=0.6538 v=0.5750; Echo Park Lake u=0.4385 v=0.0950.

| number | label |
|---|---|
| 1,192 | wells in this field on the state's records |
| 856 | still listed as idle, not plugged |
| 500 | wells within four years of 1893 |
| 900 | orphan wells in the City of LA (state estimate, 2016) |

How it moves: the aerial photo first with no dots (houses, streets), then the wells layer sweeps on left to right; the camera travels along the band; 1,192 counts up, then 856 counts up beneath it.

## C3. Beverly Hills High School · L10
View `bhhs`. The 19 school-district wells are the tight cluster at u=0.736, v=0.475, beside the school's running track (the oval at about u=0.80, v=0.39). Ring the cluster, label "19 WELLS · BEVERLY HILLS HIGH". Number: 19.

## C4. THUMS · L11
View `thums`. Island White at u=0.50, v=0.52. Label "ISLAND WHITE · ONE OF FOUR OIL ISLANDS". The four names: Grissom, White, Chaffee, Freeman.
