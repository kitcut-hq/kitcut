# Fonts

All are SIL Open Font License 1.1 (text in OFL.txt), from Google Fonts.

| file | family | used by |
|---|---|---|
| Montserrat-Bold.ttf, Montserrat-Medium.ttf | Montserrat | caption presets, badges |
| Caveat.woff2 (variable 400-700) | Caveat | sketch films, crayon look |
| PatrickHand-400.woff2 | Patrick Hand | sketch films, crayon look |
| Poppins-500/600/700.woff2 | Poppins | sketch films, clean look |
| Inter.woff2 (variable 100-900) | Inter | sketch films, clean look |
| Caveat-Cyrillic-VF.ttf (variable 400-700, full glyph set) | Caveat | sketch films in Ukrainian (crayon look) |
| BalsamiqSans-Regular.ttf, BalsamiqSans-Bold.ttf (full glyph set) | Balsamiq Sans | sketch films in Ukrainian: friendly, legible print for children |
| InstrumentSerif-Regular.ttf, InstrumentSerif-Italic.ttf (full glyph set) | Instrument Serif | the jelly example's editorial type ("Melon / Jelly."); the italic is registered as its own family, `Instrument Serif Italic`, since the bundler's @font-face carries no style |
| AbrilFatface-Regular.ttf | Abril Fatface | collage films: headlines (Latin only) |
| UnifrakturMaguntia-Book.ttf | UnifrakturMaguntia | collage films: newspaper mastheads (Latin only) |
| Oswald-VF.ttf (variable 200-700) | Oswald | collage films: tape labels, chapter tags, ruler (Latin and Cyrillic) |
| OldStandard-Regular.ttf, OldStandard-Bold.ttf, OldStandard-Italic.ttf | Old Standard TT | collage films: body type, datelines, newsprint (Latin and Cyrillic) |
| PlayfairDisplay-VF.ttf, PlayfairDisplay-Italic-VF.ttf (variable 400-900) | Playfair Display | collage films: italic kickers, heavy display type in Cyrillic |
| CourierPrime-Regular.ttf, CourierPrime-Bold.ttf | Courier Prime | collage films: typewriter notes (Latin only) |
| Anton-Regular.ttf | Anton | thumbnails; collage films: condensed labels (Latin only) |
| IBMPlexMono-Regular.ttf, IBMPlexMono-Bold.ttf | IBM Plex Mono | collage films: a typewriter line in Cyrillic, where Courier Prime has no letters (Latin and Cyrillic) |

The collage fonts are the complete `.ttf` files from github.com/google/fonts (`ofl/<family>/`),
fetched 2026-09-28; the variable ones are renamed from `<Family>[wght].ttf` to `<Family>-VF.ttf`.
An italic face of a family goes in a manifest with `"style": "italic"`. IBM Plex Mono came
from the same place on 2026-09-29.

**Cyrillic in collage films.** Measured with fontTools over the Ukrainian alphabet (66 letters
and the apostrophe): Abril Fatface, Anton, Courier Prime and UnifrakturMaguntia have none of
it; Oswald, Old Standard TT, Playfair Display and IBM Plex Mono have all of it. So
`sketch/collage.js` sets a line with Cyrillic letters in a stand-in (`SK.NO_CYRILLIC`,
`SK.face`): Abril Fatface as Playfair Display 900, Anton as Oswald 700, UnifrakturMaguntia
as Old Standard TT 700 (a face first cut for Russian printing), Courier Prime as IBM Plex
Mono. `scripts/check-sketch.py` holds that table to these files.

The woff2 files are the Latin subsets Google Fonts serves; a film that needs other scripts
should add that subset beside them. The `.ttf` files above are the complete fonts from
github.com/google/fonts (`ofl/<family>/`), not a subset: a Cyrillic-only woff2 has no digits
or Latin, and two faces under one family name without `unicode-range` do not merge on a
canvas -- the digits in "101" would fall back to a system font.
