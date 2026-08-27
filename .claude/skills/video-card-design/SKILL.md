---
name: video-card-design
description: Design a card, stamp, slate or graphic to go on a video — an end card, an outro, a title card, a pull quote, a stat, a corner tag or a branded logo lockup — for any brand, from a spec rather than hand-written HTML. Produces a transparent PNG that video-image-overlay then burns onto the film. Use when asked to design or generate a card, stamp, slate, end card, title card, quote graphic or lower banner for a video, to make a graphic for a company or brand that has none here yet, to restyle an existing card, or to add a new card template or brand.
---

# Designing a card

The burn side (`video-image-overlay`) will put **any** PNG on a film. This skill
is where that PNG comes from when nobody has one.

```powershell
cd C:\instafill\video-editing

python scripts/make-card.py --list                      # templates, brands, styles
python scripts/make-card.py --spec projects/<id>/cards/outro.json --png
```

A card is three separable things, and keeping them separate is the whole point:

| | lives in | changing it |
|---|---|---|
| **shape** | `config/cards/templates/*.html` | makes it a different *kind* of card |
| **look** | `config/cards/brands/*.json` | makes it a different *company's* card |
| **words** | the spec, `projects/<id>/cards/*.json` | makes it a different *message* |

Never solve a design problem by editing a script. If the look is wrong, it is a
brand token; if the arrangement is wrong, it is a template; if the copy is
wrong, it is the spec.

## The spec

```json
{
  "template": "stacked-blocks",
  "brand": "instafill",
  "lines": [
    {"style": "kicker", "text": "ВІДЕО ЗІБРАНЕ ТУЛІНГОМ"},
    {"style": "hero",   "text": "INSTAFILL<span class='em'>.AI</span>"},
    {"style": "accent", "text": "@instafill_ai"}
  ]
}
```

`text` is **raw HTML**, which is how a single word gets the accent colour
(`<span class="em">`) or a line gets a deliberate break (`<br>`). Styles are
`kicker`, `hero`, `accent`, `body`, `ghost`; any line may override `size_px`,
`fill`, `colour` or `tracking_px` inline when one line genuinely needs it.

Specs go in `projects/<id>/cards/` and are **committed** — the spec is the
control, and the PNG regenerates from it into `temp/`.

## Choosing a template

| template | reach for it when | animate with |
|---|---|---|
| `stacked-blocks` | an end card that must feel designed; a brand statement | **wipe** — it is built for one: the reveal edge crosses each line's type and its fill together |
| `centred-lockup` | an outro, a thank-you, a CTA; anything calmer | fade |
| `corner-tag` | a persistent handle or URL that sits for a long stretch | fade, no treatment |
| `quote` | lifting a line the speaker just said onto the screen | fade or slide |
| `stat` | a number that deserves the screen — a price, a count, a percentage | fade |

A wipe wants internal edges to travel along. On a template whose fill is one
continuous panel (`centred-lockup`), a wipe reads as a sliding rectangle — use
a fade there.

## Adding a brand

Copy `config/cards/brands/mono.json` (the deliberately brand-neutral one) and
set the tokens. That is the entire job — every template picks them up:

`ink` the dark, `paper` the light, `accent` the one colour that carries the
brand, `accent_ink` what sits legibly **on** the accent, `muted` for secondary
type, `font_bold` / `font_regular` as repo-relative TTF paths, plus
`radius_px` and `tracking_px`.

Check the new brand against **every** template before using it —
`--template <each> --brand <new>` — because a palette that works on a slab can
fail on a shadowed quote where the type has no fill behind it.

## Adding a template

A template is one HTML file with a comment block at the top saying what it is
for (that first line is what `--list` prints). It receives the brand tokens and
`lines` and uses a very small mustache: `{{x}}` escaped, `{{{x}}}` raw,
`{{#x}}…{{/x}}` for a list or flag, `{{^x}}…{{/x}}` for its absence. There is
deliberately no logic beyond that — a card that needs an `if` wants its own
template.

Two rules a template must obey, both enforced downstream:

- **Never paint `html` or `body`.** The renderer checks the alpha afterwards
  and refuses a fully opaque shot, because that becomes a white slab on the
  film rather than a visible error.
- **Only the artwork is ink.** The PNG is cropped to its own alpha bbox, and
  that crop is what the overlay's `corner` and `width_frac` then size and
  place. Padding inside the page is fine — it is cropped away.

Fonts are injected as absolute `file:///` URLs because a generated page may be
written to a temp dir at any depth. A hand-written page in
`projects/<id>/assets/` uses a relative `@font-face` src instead; it lives at a
known depth and is committed.

## Designing well, on video specifically

- **Read the footage first.** `image-overlay.py --frame T` composites the card
  onto a real frame, treatment included, for free. Design against that, never
  against a white page. A card that is beautiful alone and illegible over the
  shot is a failed card.
- **A card over video needs its own ground.** Either a fill behind the type
  (`stacked-blocks`, `centred-lockup`) or a treatment under it (`background` on
  the overlay) or a shadow (`quote`, `stat`). Type alone on moving footage
  survives nothing.
- **Size with `width_frac`, not pixels.** It is a fraction of the frame, so one
  card fits a 1080p film and a 1080×1920 short. Check both if the card is for
  both.
- **Fewer lines.** Three is a card; five is a slide. The reference end card is
  three.
- **Match the channel.** Use the repo's own fonts and the accent already used
  by the captions, the badge and the lower third, or the film reads as two
  brands stapled together.
- **Check the language.** Montserrat covers Cyrillic; a font that does not will
  render tofu and nothing will warn you. Look at the PNG.

## Verifying

`--list` is free. `--png` costs a browser launch (about two seconds) and is
where a font, a colour or an overflow shows itself — **always look at the PNG**,
it is an image and you can read it directly. Then `--frame` over the real
footage before any encode.

The project folder rules apply as everywhere: read `projects/<id>/project.json`
first, and record what a script did not. Details in the `video-project` skill.
