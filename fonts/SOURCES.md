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

The woff2 files are the Latin subsets Google Fonts serves; a film that needs other scripts
should add that subset beside them. The `.ttf` files above are the complete fonts from
github.com/google/fonts (`ofl/<family>/`), not a subset: a Cyrillic-only woff2 has no digits
or Latin, and two faces under one family name without `unicode-range` do not merge on a
canvas -- the digits in "101" would fall back to a system font.
